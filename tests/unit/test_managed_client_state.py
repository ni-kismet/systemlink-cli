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


def test_state_store_rejects_master_identity_change(tmp_path: Path) -> None:
    """A changed master identity requires an explicit reset."""
    store = StateStore(tmp_path / "minion")
    store.load_or_create_identity("slcli-test-001")
    store.record_master_identity("master-a")

    with pytest.raises(MasterIdentityChangedError, match="identity changed"):
        store.record_master_identity("master-b")


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


def test_windows_state_permissions_remove_inheritance(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Windows state paths grant access only to the current user."""
    calls: list[tuple[list[str], dict[str, Any]]] = []

    def run(command: list[str], **kwargs: Any) -> None:
        calls.append((command, kwargs))

    monkeypatch.setattr(state_module.os, "name", "nt")
    monkeypatch.setattr(state_module.getpass, "getuser", lambda: "test-user")
    monkeypatch.setattr(state_module.subprocess, "run", run)

    StateStore._restrict_permissions(tmp_path / "state", 0o700)

    assert calls == [
        (
            [
                "icacls",
                str(tmp_path / "state"),
                "/reset",
                "/inheritance:r",
                "/grant:r",
                "test-user:F",
            ],
            {"check": True, "capture_output": True, "text": True},
        )
    ]


def test_windows_state_permissions_fail_closed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """An ACL failure prevents use of unprotected state."""
    monkeypatch.setattr(state_module.os, "name", "nt")
    monkeypatch.setattr(state_module.getpass, "getuser", lambda: "test-user")

    def run(command: list[str], **kwargs: Any) -> None:
        raise subprocess.CalledProcessError(1, command)

    monkeypatch.setattr(state_module.subprocess, "run", run)

    with pytest.raises(StateError, match="Unable to protect isolated state"):
        StateStore._restrict_permissions(tmp_path / "state", 0o700)
