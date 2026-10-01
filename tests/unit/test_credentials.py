"""Unit tests for operating-system credential storage."""

import json
import subprocess
from typing import Any
from unittest.mock import MagicMock

import pytest

from slcli import credentials


def test_macos_set_keeps_secret_out_of_process_arguments(monkeypatch: Any) -> None:
    """The macOS credential is sent over stdin and allows same-user processes."""
    run = MagicMock(return_value=subprocess.CompletedProcess([], 0, "", ""))
    monkeypatch.setattr(credentials, "_security_executable", lambda: "/usr/bin/security")
    monkeypatch.setattr(credentials.subprocess, "run", run)

    credentials._macos_set("profile-id", "api-key", "secret with spaces")

    args, kwargs = run.call_args
    assert args[0] == ["/usr/bin/security", "-i"]
    assert "-A" in kwargs["input"]
    assert "secret with spaces" in kwargs["input"]
    assert "secret with spaces" not in args[0]


def test_macos_get_returns_missing_item_as_none(monkeypatch: Any) -> None:
    """A missing macOS Keychain item is not an access failure."""
    monkeypatch.setattr(credentials, "_security_executable", lambda: "/usr/bin/security")
    monkeypatch.setattr(
        credentials.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            [],
            44,
            "",
            "security: SecKeychainSearchCopyNext: The specified item could not be found.",
        ),
    )

    assert credentials._macos_get("profile-id", "api-key") is None


def test_macos_locked_keychain_error_suggests_unlock(monkeypatch: Any) -> None:
    """A locked Keychain has a concrete recovery command in its error."""
    monkeypatch.setattr(credentials, "_security_executable", lambda: "/usr/bin/security")
    monkeypatch.setattr(
        credentials.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess(
            [], 36, "", "security: User interaction is not allowed."
        ),
    )

    with pytest.raises(credentials.CredentialStoreError, match="security unlock-keychain"):
        credentials._macos_get("profile-id", "api-key")


@pytest.mark.parametrize("operation", ["_macos_get", "_macos_set", "_macos_delete"])
def test_macos_operations_report_keychain_errors(monkeypatch: Any, operation: str) -> None:
    """Security command failures are surfaced without exposing credential values."""
    monkeypatch.setattr(credentials, "_security_executable", lambda: "/usr/bin/security")
    monkeypatch.setattr(
        credentials.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 1, "", "access denied"),
    )

    with pytest.raises(credentials.CredentialStoreError, match="access denied"):
        if operation == "_macos_set":
            credentials._macos_set("profile-id", "api-key", "secret")
        else:
            getattr(credentials, operation)("profile-id", "api-key")


def test_macos_reads_and_deletes_existing_credential(monkeypatch: Any) -> None:
    """A successful Keychain read strips only the command's trailing newline."""
    run = MagicMock(return_value=subprocess.CompletedProcess([], 0, "secret value\n", ""))
    monkeypatch.setattr(credentials, "_security_executable", lambda: "/usr/bin/security")
    monkeypatch.setattr(credentials.subprocess, "run", run)

    assert credentials._macos_get("profile-id", "api-key") == "secret value"
    credentials._macos_delete("profile-id", "api-key")
    assert run.call_args.args[0][-1] == "profile:profile-id:api-key"


@pytest.mark.parametrize("operation", ["_macos_get", "_macos_set", "_macos_delete"])
def test_macos_launch_failure_uses_store_error(monkeypatch: Any, operation: str) -> None:
    """OS launch errors follow the same controlled error path as backend failures."""
    monkeypatch.setattr(credentials, "_security_executable", lambda: "/usr/bin/security")
    monkeypatch.setattr(credentials.subprocess, "run", MagicMock(side_effect=PermissionError()))

    with pytest.raises(credentials.CredentialStoreUnavailable, match="Could not launch"):
        if operation == "_macos_set":
            credentials._macos_set("profile-id", "api-key", "secret")
        else:
            getattr(credentials, operation)("profile-id", "api-key")


def test_macos_delete_ignores_missing_credential(monkeypatch: Any) -> None:
    """Deleting an already absent Keychain item is idempotent."""
    monkeypatch.setattr(credentials, "_security_executable", lambda: "/usr/bin/security")
    monkeypatch.setattr(
        credentials.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 44, "", ""),
    )

    credentials._macos_delete("profile-id", "api-key")


def test_file_credentials_round_trip(monkeypatch: Any) -> None:
    """File storage reads and updates both API keys and bundled PKCE credentials."""
    config = MagicMock()
    profile = MagicMock(api_key="", pkce_credentials={})
    monkeypatch.setattr(credentials, "_find_profile", lambda _profile_id: (config, profile))

    assert credentials.get_credential("profile-id", "api-key", "file") is None
    assert credentials.get_credential("profile-id", "pkce", "file") is None
    credentials.set_credential("profile-id", "api-key", "secret", "file")
    credentials.set_credential("profile-id", "pkce", '{"access_token": "token"}', "file")
    assert credentials.get_credential("profile-id", "api-key", "file") == "secret"
    assert json.loads(credentials.get_credential("profile-id", "pkce", "file") or "") == {
        "access_token": "token"
    }
    credentials.delete_credential("profile-id", "api-key", "file")
    credentials.delete_credential("profile-id", "pkce", "file")
    assert profile.api_key == ""
    assert profile.pkce_credentials == {}
    assert config.save.call_count == 4


@pytest.mark.parametrize("value", ["not json", "[]"])
def test_file_rejects_invalid_pkce_bundle(monkeypatch: Any, value: str) -> None:
    """Only JSON objects can be saved as file-backed PKCE credentials."""
    config = MagicMock()
    monkeypatch.setattr(credentials, "_find_profile", lambda _profile_id: (config, MagicMock()))

    with pytest.raises(credentials.CredentialStoreError, match="bundle is invalid"):
        credentials.set_credential("profile-id", "pkce", value, "file")
    config.save.assert_not_called()


@pytest.mark.parametrize("operation", ["set", "delete"])
def test_file_save_failure_uses_store_error(monkeypatch: Any, operation: str) -> None:
    """File persistence errors do not escape the credential-store error contract."""
    config = MagicMock()
    config.save.side_effect = RuntimeError("disk full")
    monkeypatch.setattr(credentials, "_find_profile", lambda _profile_id: (config, MagicMock()))

    with pytest.raises(credentials.CredentialStoreError, match="config file"):
        if operation == "set":
            credentials.set_credential("profile-id", "pkce", "{}", "file")
        else:
            credentials.delete_credential("profile-id", "pkce", "file")


def test_get_credential_is_cached_and_invalidated_after_set(monkeypatch: Any) -> None:
    """Repeated reads avoid backend calls and writes clear cached values."""
    backend = MagicMock()
    backend.get_password.side_effect = ["first", "second"]
    monkeypatch.setattr(credentials.platform, "system", lambda: "Linux")
    monkeypatch.setattr(credentials, "_get_keyring_module", lambda: backend)
    credentials._cached_get.cache_clear()

    assert credentials.get_credential("profile-id", "api-key") == "first"
    assert credentials.get_credential("profile-id", "api-key") == "first"
    assert backend.get_password.call_count == 1

    credentials.set_credential("profile-id", "api-key", "replacement")
    assert credentials.get_credential("profile-id", "api-key") == "second"
    assert backend.set_password.call_count == 1
    assert backend.get_password.call_count == 2


def test_windows_pkce_credentials_use_split_size_limited_items(monkeypatch: Any) -> None:
    """Windows PKCE values fit Credential Manager's per-item blob limit."""
    import keyring.errors

    class SizeLimitedKeyring:
        errors = keyring.errors

        def __init__(self) -> None:
            self.values: dict[tuple[str, str], str] = {}

        def set_password(self, service: str, account: str, password: str) -> None:
            if len(password.encode("utf-16-le")) > 2560:
                raise ValueError("credential blob exceeds 2560 bytes")
            self.values[(service, account)] = password

        def get_password(self, service: str, account: str) -> str | None:
            return self.values.get((service, account))

        def delete_password(self, service: str, account: str) -> None:
            try:
                del self.values[(service, account)]
            except KeyError as exc:
                raise keyring.errors.PasswordDeleteError() from exc

    backend = SizeLimitedKeyring()
    monkeypatch.setattr(credentials.platform, "system", lambda: "Windows")
    monkeypatch.setattr(credentials, "_get_keyring_module", lambda: backend)
    credentials._cached_get.cache_clear()
    bundle = {
        "access-token": "a" * 1250,
        "refresh-token": "r" * 1250,
        "access-expires-at": 1780000000.0,
    }
    serialized_bundle = json.dumps(bundle)
    assert len(serialized_bundle.encode("utf-16-le")) > 2560

    credentials.set_credential("profile-id", "pkce", serialized_bundle)

    assert len(backend.values) == 3
    assert all(len(value.encode("utf-16-le")) <= 2560 for value in backend.values.values())
    assert json.loads(credentials.get_credential("profile-id", "pkce") or "") == bundle

    credentials.delete_credential("profile-id", "pkce")
    assert backend.values == {}
    assert credentials.get_credential("profile-id", "pkce") is None

    credentials.set_credential("profile-id", "pkce", '{"access-token": "token"}')
    assert json.loads(credentials.get_credential("profile-id", "pkce") or "") == {
        "access-token": "token"
    }
    credentials.delete_credential("profile-id", "pkce")
    assert backend.values == {}


def test_linux_rejects_non_secret_service_backend(monkeypatch: Any) -> None:
    """Linux never selects an unencrypted fallback keyring backend implicitly."""
    import keyring

    monkeypatch.setattr(credentials.platform, "system", lambda: "Linux")
    monkeypatch.setattr(keyring, "get_keyring", lambda: object())

    with pytest.raises(credentials.CredentialStoreUnavailable, match="Secret Service"):
        credentials._get_keyring_module()


def test_linux_selects_secret_service_from_chainer(monkeypatch: Any) -> None:
    """An encrypted backend in a chain is selected without using plaintext fallbacks."""
    import keyring
    from keyring.backends.SecretService import Keyring
    from keyring.backends.chainer import ChainerBackend

    secret_service = object.__new__(Keyring)
    chainer = object.__new__(ChainerBackend)
    monkeypatch.setattr(ChainerBackend, "backends", [object(), secret_service])
    monkeypatch.setattr(credentials.platform, "system", lambda: "Linux")
    monkeypatch.setattr(keyring, "get_keyring", lambda: chainer)
    select = MagicMock()
    monkeypatch.setattr(keyring, "set_keyring", select)

    assert credentials._get_keyring_module() is keyring
    select.assert_called_once_with(secret_service)


def test_keyring_read_and_delete_errors(monkeypatch: Any) -> None:
    """Backend failures distinguish missing credentials from other failures."""
    import keyring.errors

    backend = MagicMock()
    backend.errors.PasswordDeleteError = keyring.errors.PasswordDeleteError
    monkeypatch.setattr(credentials.platform, "system", lambda: "Linux")
    monkeypatch.setattr(credentials, "_get_keyring_module", lambda: backend)
    credentials._cached_get.cache_clear()
    backend.get_password.side_effect = RuntimeError("backend read failure")
    with pytest.raises(credentials.CredentialStoreError, match="Could not read"):
        credentials.get_credential("profile-id", "api-key")

    backend.delete_password.side_effect = keyring.errors.PasswordDeleteError()
    credentials.delete_credential("profile-id", "api-key")
    backend.delete_password.side_effect = RuntimeError("backend delete failure")
    with pytest.raises(credentials.CredentialStoreError, match="Could not delete"):
        credentials.delete_credential("profile-id", "api-key")


def test_keyring_unavailable_on_write(monkeypatch: Any) -> None:
    """A missing keyring backend suggests file storage instead of leaking a traceback."""
    import keyring.errors

    backend = MagicMock()
    backend.errors.NoKeyringError = keyring.errors.NoKeyringError
    backend.set_password.side_effect = keyring.errors.NoKeyringError()
    monkeypatch.setattr(credentials.platform, "system", lambda: "Linux")
    monkeypatch.setattr(credentials, "_get_keyring_module", lambda: backend)

    with pytest.raises(credentials.CredentialStoreUnavailable, match="--credential-store file"):
        credentials.set_credential("profile-id", "api-key", "secret")


def test_delete_profile_credentials_removes_legacy_pkce_items(monkeypatch: Any) -> None:
    """Profile cleanup deletes old token entries without reading them."""
    backend = MagicMock()
    monkeypatch.setattr(credentials.platform, "system", lambda: "Linux")
    monkeypatch.setattr(credentials, "_get_keyring_module", lambda: backend)

    credentials.delete_profile_credentials("profile-id", "os", "dev", "pkce")

    deleted_accounts = [call.args[1] for call in backend.delete_password.call_args_list]
    assert deleted_accounts == [
        "PKCE:dev:access-token",
        "PKCE:dev:refresh-token",
        "PKCE:dev:access-expires-at",
        "PKCE:dev:session-key",
        "PKCE:dev:session-expires-at",
        "profile:profile-id:api-key",
        "profile:profile-id:pkce",
    ]
    backend.get_password.assert_not_called()


def test_delete_api_key_profile_also_removes_legacy_pkce_items(monkeypatch: Any) -> None:
    """A PKCE-to-API-key transition does not skip old per-token accounts."""
    backend = MagicMock()
    monkeypatch.setattr(credentials.platform, "system", lambda: "Linux")
    monkeypatch.setattr(credentials, "_get_keyring_module", lambda: backend)

    credentials.delete_profile_credentials("profile-id", "os", "dev", "api-key")

    deleted = [call.args[1] for call in backend.delete_password.call_args_list]
    assert deleted[:5] == [
        f"PKCE:dev:{credential}" for credential in credentials.LEGACY_PKCE_CREDENTIALS
    ]
    assert deleted[-2:] == ["profile:profile-id:pkce", "profile:profile-id:api-key"]


def test_delete_api_key_profile_removes_active_credential_last(monkeypatch: Any) -> None:
    """API-key profile cleanup removes inactive PKCE data before the API key."""
    backend = MagicMock()
    monkeypatch.setattr(credentials.platform, "system", lambda: "Linux")
    monkeypatch.setattr(credentials, "_get_keyring_module", lambda: backend)

    credentials.delete_profile_credentials("profile-id", "os")

    deleted_accounts = [call.args[1] for call in backend.delete_password.call_args_list]
    assert deleted_accounts == [
        "profile:profile-id:pkce",
        "profile:profile-id:api-key",
    ]


def test_delete_file_profile_without_legacy_os_store(monkeypatch: Any) -> None:
    """A file-backed profile can be removed when legacy OS storage is unavailable."""
    monkeypatch.setattr(credentials.platform, "system", lambda: "Linux")
    monkeypatch.setattr(
        credentials,
        "_get_keyring_module",
        MagicMock(side_effect=credentials.CredentialStoreUnavailable("no store")),
    )

    credentials.delete_profile_credentials("profile-id", "file", "dev")

    with pytest.raises(credentials.CredentialStoreUnavailable):
        credentials.delete_profile_credentials("profile-id", "os", "dev")


def test_pending_cleanup_preserves_active_profile_credential(monkeypatch: Any) -> None:
    """A stale deletion record cannot remove credentials still used by a profile."""
    from slcli.profiles import Profile, ProfileConfig

    record = {"id": "active-id", "name": "dev", "store": "os", "auth-mode": "api-key"}
    config = ProfileConfig(
        profiles={
            "dev": Profile(name="dev", server="https://example.com", credential_id="active-id")
        },
        settings={credentials.PENDING_DELETIONS_SETTING: [record]},
    )
    delete = MagicMock()
    monkeypatch.setattr(credentials, "delete_profile_credentials", delete)

    with pytest.raises(credentials.CredentialStoreError, match="active profile"):
        credentials.finish_pending_profile_deletion(config, record)

    delete.assert_not_called()
    assert config.settings[credentials.PENDING_DELETIONS_SETTING] == [record]
