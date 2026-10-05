"""Unit tests for isolated managed-client state."""

import json
import os
import stat
import subprocess
from pathlib import Path
from typing import Any

import pytest

from slcli.managed_client import state as state_module
from slcli.managed_client.models import MasterIdentityChangedError, StateError
from slcli.managed_client.state import StateStore


def test_state_store_preserves_identity_and_restricts_files(tmp_path: Path) -> None:
    """A reload keeps the same key and does not persist REST credentials."""
    store = StateStore(tmp_path / "minion")
    first = store.load_or_create_identity("slcli-test-001")
    second = store.load_or_create_identity("slcli-test-001")
    metadata = json.loads((tmp_path / "minion" / "metadata.json").read_text())

    assert first.public_key.public_numbers() == second.public_key.public_numbers()
    assert "api-key" not in metadata
    if os.name != "nt":
        assert stat.S_IMODE((tmp_path / "minion").stat().st_mode) == 0o700
        assert stat.S_IMODE((tmp_path / "minion" / "minion-key.pem").stat().st_mode) == 0o600


def test_state_store_restricts_existing_private_key(tmp_path: Path) -> None:
    """Reloading an identity restores owner-only private-key permissions."""
    if os.name == "nt":
        pytest.skip("POSIX mode bits are not available on Windows")
    store = StateStore(tmp_path / "minion")
    store.load_or_create_identity("slcli-test-001")
    private_key_path = tmp_path / "minion" / "minion-key.pem"
    private_key_path.chmod(0o644)

    store.load_or_create_identity("slcli-test-001")

    assert stat.S_IMODE(private_key_path.stat().st_mode) == 0o600


def test_state_store_rejects_different_minion_id(tmp_path: Path) -> None:
    """A state directory cannot be reused for another identity."""
    store = StateStore(tmp_path / "minion")
    store.load_or_create_identity("slcli-test-001")

    with pytest.raises(StateError, match="different minion ID"):
        store.load_or_create_identity("slcli-test-002")


def test_state_store_wraps_directory_creation_failure(tmp_path: Path) -> None:
    """A path that is already a file becomes a typed state error."""
    state_path = tmp_path / "not-a-directory"
    state_path.write_text("occupied")

    with pytest.raises(StateError, match="state directory"):
        StateStore(state_path).ensure_directory()


def test_state_store_rejects_master_identity_change(tmp_path: Path) -> None:
    """A changed master identity requires an explicit reset."""
    store = StateStore(tmp_path / "minion")
    store.load_or_create_identity("slcli-test-001")
    store.record_master_identity("master-a")

    with pytest.raises(MasterIdentityChangedError, match="identity changed"):
        store.record_master_identity("master-b")


def test_state_store_replaces_metadata_atomically(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Metadata updates replace a flushed temporary file in the state directory."""
    store = StateStore(tmp_path / "minion")
    store.load_or_create_identity("slcli-test-001")
    calls: list[tuple[Path, Path]] = []
    replace = state_module.os.replace

    def record_replace(source: str | os.PathLike[str], target: str | os.PathLike[str]) -> None:
        calls.append((Path(source), Path(target)))
        replace(source, target)

    monkeypatch.setattr(state_module.os, "replace", record_replace)
    store.record_blackout_state(True)

    assert len(calls) == 1
    source, target = calls[0]
    assert source.parent == target.parent == tmp_path / "minion"
    assert source.name.startswith(".metadata-")
    assert source.suffix == ".tmp"
    assert target.name == "metadata.json"
    assert json.loads(target.read_text())["blackout"] is True


def test_state_store_reset_removes_only_managed_files(tmp_path: Path) -> None:
    """Reset clears identity material without deleting unrelated state."""
    store = StateStore(tmp_path / "minion")
    store.load_or_create_identity("slcli-test-001")
    unrelated = tmp_path / "minion" / "unrelated.txt"
    unrelated.write_text("keep")

    store.reset()

    assert unrelated.exists()
    assert not (tmp_path / "minion" / "metadata.json").exists()
    assert not (tmp_path / "minion" / "minion-key.pem").exists()


def test_windows_state_permissions_replace_acl(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Windows state paths use a protected ACL for the current user."""
    calls: list[tuple[list[str], dict[str, Any]]] = []

    system_root = tmp_path / "Windows"

    def completed_run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, "", "")

    with monkeypatch.context() as windows:
        windows.setattr(state_module.os, "name", "nt")
        windows.setenv("SystemRoot", str(system_root))
        windows.setattr(state_module.subprocess, "run", completed_run)
        StateStore._restrict_permissions(tmp_path / "state", 0o700)

    assert len(calls) == 1
    command, kwargs = calls[0]
    assert command == [
        str(system_root / "System32" / "WindowsPowerShell" / "v1.0" / "powershell.exe"),
        "-NoProfile",
        "-NonInteractive",
        "-Command",
        "-",
    ]
    assert kwargs["check"] is True
    assert kwargs["capture_output"] is True
    assert kwargs["text"] is True
    assert kwargs["input"] == state_module._WINDOWS_ACL_SCRIPT
    assert kwargs["input"].endswith("\n\n")
    assert kwargs["env"]["PSModulePath"] == str(
        system_root / "System32" / "WindowsPowerShell" / "v1.0" / "Modules"
    )
    assert kwargs["env"]["SLCLI_MANAGED_CLIENT_STATE_PATH"] == str(tmp_path / "state")
    assert "$acl = [System.Security.AccessControl.DirectorySecurity]::new()" in kwargs["input"]
    assert "$acl.SetAccessRuleProtection($true, $false)" in kwargs["input"]
    assert "$acl.AddAccessRule($accessRule)" in kwargs["input"]
    assert "[System.IO.Directory]::SetAccessControl($statePath, $acl)" in kwargs["input"]
    assert "Get-Acl" not in kwargs["input"]
    assert "icacls" not in kwargs["input"]


def test_windows_powershell_environment_replaces_module_path_case_insensitively(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Inherited PSModulePath variants do not survive in the child environment."""
    system_root = str(tmp_path / "Windows")
    monkeypatch.setattr(
        state_module.os,
        "environ",
        {
            "SystemRoot": system_root,
            "pSmOdUlEpAtH": "inherited-modules",
            "PSMODULEPATH": "another-inherited-value",
        },
    )

    environment = state_module._windows_powershell_environment()

    assert [name for name in environment if name.casefold() == "psmodulepath"] == ["PSModulePath"]
    assert environment["PSModulePath"] == os.path.join(
        system_root, "System32", "WindowsPowerShell", "v1.0", "Modules"
    )


@pytest.mark.parametrize("initialize_identity", [False, True])
def test_windows_state_permissions_fail_closed(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    initialize_identity: bool,
) -> None:
    """A failed ACL replacement stops identity writes."""
    store = StateStore(tmp_path / "state")
    commands: list[list[str]] = []

    def run(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        assert kwargs["check"] is True
        assert kwargs["capture_output"] is True
        assert kwargs["text"] is True
        raise subprocess.CalledProcessError(1, command)

    message = "state directory" if initialize_identity else "Unable to protect isolated state"
    with monkeypatch.context() as windows:
        windows.setattr(state_module.os, "name", "nt")
        windows.setenv("SystemRoot", str(tmp_path / "Windows"))
        windows.setattr(state_module.subprocess, "run", run)
        with pytest.raises(StateError, match=message) as caught:
            if initialize_identity:
                store.load_or_create_identity("slcli-test-001")
            else:
                store._restrict_permissions(store.state_dir, 0o700)

    cause = caught.value.__cause__
    if initialize_identity:
        assert isinstance(cause, StateError)
        cause = cause.__cause__
        assert store.state_dir.exists()
        assert list(store.state_dir.iterdir()) == []
    assert isinstance(cause, subprocess.CalledProcessError)
    assert len(commands) == 1
    assert commands[0][-2:] == ["-Command", "-"]


@pytest.mark.parametrize("target_type", ["directory", "file"])
@pytest.mark.skipif(os.name != "nt", reason="Windows ACLs require Windows")
def test_windows_state_permissions_remove_explicit_grants(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, target_type: str
) -> None:
    """Replacing a file or directory ACL removes unrelated explicit grants on Windows."""
    state_path = tmp_path / "state"
    if target_type == "directory":
        state_path.mkdir()
    else:
        state_path.write_text("state")
    system_root = os.environ["SystemRoot"]
    icacls = os.path.join(system_root, "System32", "icacls.exe")
    powershell = os.path.join(
        system_root, "System32", "WindowsPowerShell", "v1.0", "powershell.exe"
    )
    environment = state_module._windows_powershell_environment()
    environment["SLCLI_MANAGED_CLIENT_STATE_PATH"] = str(state_path)

    subprocess.run(
        [icacls, str(state_path), "/grant", "*S-1-1-0:(R)"],
        check=True,
        capture_output=True,
        text=True,
    )
    inspect_command = [powershell, "-NoProfile", "-NonInteractive", "-Command", "-"]
    explicit_grant_check = """
$acl = Get-Acl -LiteralPath $env:SLCLI_MANAGED_CLIENT_STATE_PATH
$rules = @($acl.Access)
$rules | ForEach-Object {
    Write-Output ("ACL identity={0}, inherited={1}, rights={2}" -f $_.IdentityReference.Value, $_.IsInherited, $_.FileSystemRights)
}
$everyone = @($rules | Where-Object {
    $_.IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value -eq 'S-1-1-0'
})
if ($everyone.Count -eq 0) { exit 1 }

"""
    explicit_grant_result = subprocess.run(
        inspect_command,
        check=False,
        capture_output=True,
        text=True,
        input=explicit_grant_check,
        env=environment,
    )
    assert explicit_grant_result.returncode == 0, (
        explicit_grant_result.stdout + explicit_grant_result.stderr
    )

    original_run = subprocess.run

    def fail_acl_update(command: list[str], **kwargs: Any) -> subprocess.CompletedProcess[str]:
        if kwargs.get("input") == state_module._WINDOWS_ACL_SCRIPT:
            raise subprocess.CalledProcessError(1, command)
        return original_run(command, **kwargs)

    with monkeypatch.context() as failing_update:
        failing_update.setattr(state_module.subprocess, "run", fail_acl_update)
        with pytest.raises(StateError, match="Unable to protect isolated state"):
            StateStore._restrict_permissions(state_path, 0o700)

    explicit_grant_after_failure = subprocess.run(
        inspect_command,
        check=False,
        capture_output=True,
        text=True,
        input=explicit_grant_check,
        env=environment,
    )
    assert explicit_grant_after_failure.returncode == 0, (
        explicit_grant_after_failure.stdout + explicit_grant_after_failure.stderr
    )

    StateStore._restrict_permissions(state_path, 0o700)

    protected_acl_check = """
$acl = Get-Acl -LiteralPath $env:SLCLI_MANAGED_CLIENT_STATE_PATH
$sid = [System.Security.Principal.WindowsIdentity]::GetCurrent().User.Value
$rules = @($acl.Access)
Write-Output ("ACL protected={0}, ruleCount={1}, expectedSID={2}" -f $acl.AreAccessRulesProtected, $rules.Count, $sid)
$rules | ForEach-Object {
    Write-Output ("ACL identity={0}, inherited={1}, rights={2}" -f $_.IdentityReference.Value, $_.IsInherited, $_.FileSystemRights)
}
if (-not $acl.AreAccessRulesProtected -or $rules.Count -ne 1) { exit 1 }
if ($rules[0].IdentityReference.Translate([System.Security.Principal.SecurityIdentifier]).Value -ne $sid) { exit 2 }
if ($rules[0].FileSystemRights -ne [System.Security.AccessControl.FileSystemRights]::FullControl) {
    exit 3
}

"""
    protected_acl_result = subprocess.run(
        inspect_command,
        check=False,
        capture_output=True,
        text=True,
        input=protected_acl_check,
        env=environment,
    )
    assert protected_acl_result.returncode == 0, (
        protected_acl_result.stdout + protected_acl_result.stderr
    )


def test_state_store_wraps_non_json_asset_values(tmp_path: Path) -> None:
    """MessagePack-valid bytes cannot escape metadata serialization as TypeError."""
    store = StateStore(tmp_path / "minion")

    with pytest.raises(StateError, match="Unable to write isolated minion metadata"):
        store.record_asset_records([{"name": "asset-1", "model_name": b"binary"}])
