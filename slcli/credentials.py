"""Access profile credentials through operating-system credential stores."""

from __future__ import annotations

import functools
import json
import platform
import shlex
import shutil
import subprocess
from typing import TYPE_CHECKING, Any, Optional

if TYPE_CHECKING:
    from .profiles import Profile, ProfileConfig

KEYRING_SERVICE = "systemlink-cli"
LEGACY_PKCE_CREDENTIALS = (
    "access-token",
    "refresh-token",
    "access-expires-at",
    "session-key",
    "session-expires-at",
)


class CredentialStoreError(RuntimeError):
    """Raised when an operating-system credential cannot be accessed."""


class CredentialStoreUnavailable(CredentialStoreError):
    """Raised when no supported operating-system credential store is available."""


def credential_account(profile_id: str, credential: str) -> str:
    """Return the account name for a profile credential."""
    return f"profile:{profile_id}:{credential}"


def describe_credential_store(store: str) -> str:
    """Return a user-facing name for a credential store."""
    if store == "file":
        return "config file"
    system = platform.system()
    if system == "Darwin":
        return "macOS Keychain"
    if system == "Windows":
        return "Windows Credential Manager"
    if system == "Linux":
        return "Secret Service"
    return "operating-system credential store"


def _security_executable() -> str:
    """Return the macOS Security CLI path or raise a helpful error."""
    executable = "/usr/bin/security"
    if not shutil.which(executable):
        raise CredentialStoreUnavailable("The macOS 'security' command is unavailable.")
    return executable


def _security_error(result: subprocess.CompletedProcess[str]) -> str:
    """Format a Security CLI failure without exposing command input."""
    details = result.stderr.strip() or result.stdout.strip()
    lowered = details.lower()
    if "interaction is not allowed" in lowered or ("keychain" in lowered and "locked" in lowered):
        return (
            "The macOS Keychain is locked or unavailable. Run 'security unlock-keychain' "
            "or set SLCLI_API_KEY."
        )
    return f"macOS Keychain operation failed: {details or 'security command returned an error'}"


def _macos_get(profile_id: str, credential: str) -> Optional[str]:
    """Read one generic password using the macOS Security CLI."""
    executable = _security_executable()
    result = subprocess.run(
        [
            executable,
            "find-generic-password",
            "-s",
            KEYRING_SERVICE,
            "-a",
            credential_account(profile_id, credential),
            "-w",
        ],
        capture_output=True,
        check=False,
        text=True,
    )
    details = result.stderr.lower()
    if result.returncode == 44 or "could not be found" in details or "item not found" in details:
        return None
    if result.returncode:
        raise CredentialStoreError(_security_error(result))
    return result.stdout.rstrip("\r\n") or None


def _macos_set(profile_id: str, credential: str, value: str) -> None:
    """Write a generic password without putting the secret in process arguments."""
    executable = _security_executable()
    command = " ".join(
        shlex.quote(argument)
        for argument in (
            "add-generic-password",
            "-U",
            "-A",
            "-s",
            KEYRING_SERVICE,
            "-a",
            credential_account(profile_id, credential),
            "-w",
            value,
        )
    )
    result = subprocess.run(
        [executable, "-i"],
        capture_output=True,
        check=False,
        input=f"{command}\n",
        text=True,
    )
    if result.returncode:
        raise CredentialStoreError(_security_error(result))


def _macos_delete_account(account: str) -> None:
    """Delete a generic password account from the macOS Keychain."""
    result = subprocess.run(
        [
            _security_executable(),
            "delete-generic-password",
            "-s",
            KEYRING_SERVICE,
            "-a",
            account,
        ],
        capture_output=True,
        check=False,
        text=True,
    )
    details = result.stderr.lower()
    if (
        result.returncode
        and result.returncode != 44
        and "could not be found" not in details
        and "item not found" not in details
    ):
        raise CredentialStoreError(_security_error(result))


def _macos_delete(profile_id: str, credential: str) -> None:
    """Delete a profile credential from the macOS Keychain."""
    _macos_delete_account(credential_account(profile_id, credential))


def _get_keyring_module() -> Any:
    """Return keyring only when it selected a supported encrypted backend."""
    try:
        import keyring

        backend = keyring.get_keyring()
    except Exception as exc:
        raise CredentialStoreUnavailable(
            "No operating-system credential store is available."
        ) from exc

    system = platform.system()
    backend_name = type(backend).__module__
    if system == "Linux" and backend_name == "keyring.backends.chainer":
        from keyring.backends.chainer import ChainerBackend

        assert isinstance(backend, ChainerBackend)
        for candidate in backend.backends:
            if "SecretService" in type(candidate).__module__:
                keyring.set_keyring(candidate)
                backend_name = type(candidate).__module__
                break
    if system == "Linux" and "SecretService" not in backend_name:
        raise CredentialStoreUnavailable(
            "Linux Secret Service is unavailable. Install and unlock a Secret Service, "
            "or use --credential-store file."
        )
    if system == "Windows" and "Windows" not in backend_name:
        raise CredentialStoreUnavailable(
            "Windows Credential Manager is unavailable. Use --credential-store file."
        )
    if system not in ("Linux", "Windows"):
        raise CredentialStoreUnavailable(
            f"No supported credential store is available on {system or 'this platform'}."
        )
    return keyring


@functools.lru_cache(maxsize=128)
def _cached_get(profile_id: str, credential: str) -> Optional[str]:
    """Read and cache an OS credential for the life of this process."""
    system = platform.system()
    if system == "Darwin":
        return _macos_get(profile_id, credential)
    keyring = _get_keyring_module()
    try:
        return keyring.get_password(KEYRING_SERVICE, credential_account(profile_id, credential))
    except Exception as exc:
        raise CredentialStoreError("Could not read the credential from the OS store.") from exc


def _find_profile(profile_id: str) -> tuple[ProfileConfig, Profile]:
    """Find the configured profile associated with a stable credential ID."""
    from .profiles import ProfileConfig

    config = ProfileConfig.load()
    for profile in config.profiles.values():
        if profile.credential_id == profile_id:
            return config, profile
    raise CredentialStoreError("The profile for this credential no longer exists.")


def get_credential(profile_id: str, credential: str, store: str = "os") -> Optional[str]:
    """Return a cached credential from the selected store."""
    if store == "file":
        _config, profile = _find_profile(profile_id)
        if credential == "api-key":
            return profile.api_key or None
        if credential == "pkce":
            return json.dumps(profile.pkce_credentials) if profile.pkce_credentials else None
        return None
    return _cached_get(profile_id, credential)


def set_credential(profile_id: str, credential: str, value: str, store: str = "os") -> None:
    """Store a credential in the selected store."""
    if store == "file":
        config, profile = _find_profile(profile_id)
        if credential == "api-key":
            profile.api_key = value
        elif credential == "pkce":
            try:
                credentials = json.loads(value)
            except json.JSONDecodeError as exc:
                raise CredentialStoreError("The PKCE credential bundle is invalid.") from exc
            if not isinstance(credentials, dict):
                raise CredentialStoreError("The PKCE credential bundle is invalid.")
            profile.pkce_credentials = credentials
        else:
            raise CredentialStoreError(f"Unsupported file credential: {credential}")
        config.save()
    elif platform.system() == "Darwin":
        _macos_set(profile_id, credential, value)
    else:
        keyring = _get_keyring_module()
        try:
            keyring.set_password(KEYRING_SERVICE, credential_account(profile_id, credential), value)
        except Exception as exc:
            if isinstance(exc, keyring.errors.NoKeyringError):
                raise CredentialStoreUnavailable(
                    "No operating-system credential store is available. "
                    "Use --credential-store file."
                ) from exc
            raise CredentialStoreError("Could not write the credential to the OS store.") from exc
    _cached_get.cache_clear()


def delete_credential(profile_id: str, credential: str, store: str = "os") -> None:
    """Remove a credential from the selected store if it exists."""
    if store == "file":
        config, profile = _find_profile(profile_id)
        if credential == "api-key":
            profile.api_key = ""
        elif credential == "pkce":
            profile.pkce_credentials = {}
        config.save()
    elif platform.system() == "Darwin":
        _macos_delete(profile_id, credential)
    else:
        keyring = _get_keyring_module()
        try:
            keyring.delete_password(KEYRING_SERVICE, credential_account(profile_id, credential))
        except keyring.errors.PasswordDeleteError:
            pass
        except Exception as exc:
            raise CredentialStoreError(
                "Could not delete the credential from the OS store."
            ) from exc
    _cached_get.cache_clear()


def _delete_legacy_pkce_account(account: str) -> None:
    """Delete an obsolete per-token PKCE entry without reading it."""
    if platform.system() == "Darwin":
        _macos_delete_account(account)
        return

    keyring = _get_keyring_module()
    try:
        keyring.delete_password(KEYRING_SERVICE, account)
    except keyring.errors.PasswordDeleteError:
        pass
    except Exception as exc:
        raise CredentialStoreError("Could not delete an obsolete PKCE credential.") from exc


def delete_profile_credentials(
    profile_id: str,
    store: str,
    legacy_pkce_profile: Optional[str] = None,
    auth_mode: str = "api-key",
) -> None:
    """Delete current profile credentials and obsolete PKCE items when applicable."""
    if legacy_pkce_profile:
        for credential in LEGACY_PKCE_CREDENTIALS:
            try:
                _delete_legacy_pkce_account(f"PKCE:{legacy_pkce_profile}:{credential}")
            except CredentialStoreUnavailable:
                if store == "os":
                    raise
                break
    if store == "os":
        inactive_credential, active_credential = (
            ("api-key", "pkce") if auth_mode == "pkce" else ("pkce", "api-key")
        )
        delete_credential(profile_id, inactive_credential)
        delete_credential(profile_id, active_credential)
