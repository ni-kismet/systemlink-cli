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


def test_macos_delete_ignores_missing_credential(monkeypatch: Any) -> None:
    """Deleting an already absent Keychain item is idempotent."""
    monkeypatch.setattr(credentials, "_security_executable", lambda: "/usr/bin/security")
    monkeypatch.setattr(
        credentials.subprocess,
        "run",
        lambda *_args, **_kwargs: subprocess.CompletedProcess([], 44, "", "item not found"),
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


def test_linux_rejects_non_secret_service_backend(monkeypatch: Any) -> None:
    """Linux never selects an unencrypted fallback keyring backend implicitly."""
    import keyring

    monkeypatch.setattr(credentials.platform, "system", lambda: "Linux")
    monkeypatch.setattr(keyring, "get_keyring", lambda: object())

    with pytest.raises(credentials.CredentialStoreUnavailable, match="Secret Service"):
        credentials._get_keyring_module()


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

    credentials.delete_profile_credentials("profile-id", "os", "dev")

    deleted_accounts = [call.args[1] for call in backend.delete_password.call_args_list]
    assert deleted_accounts == [
        "profile:profile-id:api-key",
        "profile:profile-id:pkce",
        "PKCE:dev:access-token",
        "PKCE:dev:refresh-token",
        "PKCE:dev:access-expires-at",
        "PKCE:dev:session-key",
        "PKCE:dev:session-expires-at",
    ]
    backend.get_password.assert_not_called()
