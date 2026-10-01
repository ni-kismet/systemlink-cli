"""Profile credential replacement and persistence."""

import json
from dataclasses import replace
from typing import Optional
from uuid import uuid4

from .credentials import (
    PENDING_DELETIONS_SETTING,
    CredentialStoreError,
    finish_pending_profile_deletion,
    set_credential,
)
from .profiles import Profile, ProfileConfig


class ProfileCredentialError(RuntimeError):
    """A profile credential change could not be completed."""

    def __init__(self, message: str, warnings: Optional[list[str]] = None) -> None:
        """Keep nonfatal warnings available when persistence subsequently fails."""
        super().__init__(message)
        self.warnings = warnings or []


class _ProfileSaveError(RuntimeError):
    def __init__(
        self,
        error: RuntimeError,
        cleanup_failures: list[str],
        rollback_error: Optional[RuntimeError] = None,
    ) -> None:
        super().__init__(str(error))
        self.error = error
        self.cleanup_failures = cleanup_failures
        self.rollback_error = rollback_error


def _deletion_record(profile: Profile) -> dict[str, str]:
    return {
        "id": profile.credential_id,
        "name": profile.name,
        "store": "os",
        "auth-mode": profile.auth_mode,
    }


def _remove_staged_credentials(
    config: ProfileConfig,
    staged: list[tuple[Profile, str]],
    persist_failures: bool = True,
) -> list[str]:
    from .credentials import delete_credential

    failures = []
    for profile, credential in staged:
        try:
            delete_credential(profile.credential_id, credential)
        except CredentialStoreError as exc:
            failures.append(f"{profile.credential_id}: {exc}")
            record = _deletion_record(profile)
            records = config.settings.setdefault(PENDING_DELETIONS_SETTING, [])
            if record not in records:
                records.append(record)
    if failures and persist_failures:
        try:
            config.save()
        except RuntimeError as exc:
            failures.append(f"Could not persist cleanup records: {exc}")
    return failures


def _finish_replacements(config: ProfileConfig, records: list[dict[str, str]]) -> list[str]:
    warnings = []
    for record in records:
        try:
            finish_pending_profile_deletion(config, record)
        except (CredentialStoreError, RuntimeError) as exc:
            warnings.append(
                f"Could not remove replaced credentials: {exc}. "
                "Retry cleanup with 'slcli config cleanup'."
            )
    return warnings


def _persist_replacements(
    config: ProfileConfig,
    replacements: dict[str, Profile],
    staged: list[tuple[Profile, str]],
    current_profile: Optional[str],
) -> list[str]:
    originals = {name: config.get_profile(name) for name in replacements}
    previous_current = config.current_profile
    replacement_records = []
    for name, profile in replacements.items():
        original = originals[name]
        if original and original.credential_store == "os":
            record = _deletion_record(original)
            records = config.settings.setdefault(PENDING_DELETIONS_SETTING, [])
            if record not in records:
                records.append(record)
                replacement_records.append(record)
        config.profiles[name] = profile
    config.current_profile = current_profile
    try:
        config.save()
    except RuntimeError as exc:
        for name, original in originals.items():
            if original is None:
                config.profiles.pop(name, None)
            else:
                config.profiles[name] = original
        config.current_profile = previous_current
        for record in replacement_records:
            config.settings[PENDING_DELETIONS_SETTING].remove(record)
        if not config.settings.get(PENDING_DELETIONS_SETTING):
            config.settings.pop(PENDING_DELETIONS_SETTING, None)
        failures = _remove_staged_credentials(config, staged, persist_failures=False)
        rollback_error = None
        try:
            config.save()
        except RuntimeError as rollback_exc:
            rollback_error = rollback_exc
        raise _ProfileSaveError(exc, failures, rollback_error) from exc
    return _finish_replacements(config, replacement_records)


def save_profile_credentials(
    config: ProfileConfig, profile: Profile, set_current: bool = False
) -> list[str]:
    """Stage credentials and persist a new or replacement login profile.

    Args:
        config: Configuration owning the profile and pending cleanup.
        profile: New profile containing the API key or PKCE bundle to store.
        set_current: Whether to select this profile after persistence.

    Returns:
        Nonfatal file-fallback or credential-cleanup warnings.

    Raises:
        ProfileCredentialError: Credential staging or profile persistence failed.
    """
    from .pkce import PkceError, save_pkce_credentials

    previous = config.get_profile(profile.name)
    if previous:
        profile.credential_id = (
            str(uuid4())
            if previous.credential_store == "os" or profile.credential_store == "os"
            else previous.credential_id
        )
    warnings: list[str] = []
    staged: list[tuple[Profile, str]] = []
    if profile.credential_store == "os":
        credential = "pkce" if profile.auth_mode == "pkce" else "api-key"
        staged.append((replace(profile), credential))
        try:
            if profile.auth_mode == "pkce" and profile.pkce_credentials:
                bundle = profile.pkce_credentials
                save_pkce_credentials(
                    profile.credential_id,
                    bundle["access-token"],
                    bundle["refresh-token"],
                    bundle["access-expires-at"],
                    "os",
                )
            elif profile.auth_mode == "api-key":
                set_credential(profile.credential_id, "api-key", profile.api_key, "os")
        except Exception as exc:
            failures = _remove_staged_credentials(config, staged, persist_failures=False)
            staged.clear()
            if not (
                isinstance(exc, CredentialStoreError)
                or (isinstance(exc, PkceError) and isinstance(exc.__cause__, CredentialStoreError))
            ):
                if failures:
                    try:
                        config.save()
                    except RuntimeError as save_exc:
                        failures.append(f"Could not persist cleanup records: {save_exc}")
                raise ProfileCredentialError(
                    f"Could not store credentials in the OS store: {exc}."
                    + (
                        f" Could not remove staged credentials: {', '.join(failures)}."
                        if failures
                        else ""
                    )
                ) from exc
            profile.credential_store = "file"
            profile.credential_id = str(uuid4())
            warnings.append(
                f"OS credential store unavailable ({exc}); "
                "storing this profile in the config file."
            )
            if failures:
                warnings.append(
                    f"Could not remove staged credentials: {', '.join(failures)}. "
                    "Retry cleanup with 'slcli config cleanup'."
                )
        else:
            profile.api_key = ""
            profile.pkce_credentials = {}
    try:
        warnings.extend(
            _persist_replacements(
                config,
                {profile.name: profile},
                staged,
                (
                    profile.name
                    if set_current or not config.current_profile
                    else config.current_profile
                ),
            )
        )
    except _ProfileSaveError as exc:
        if exc.rollback_error:
            if staged:
                message = (
                    f"Could not save the profile or restore the previous config: "
                    f"{exc.error}; {exc.rollback_error}. Credential ID: {profile.credential_id}."
                )
            else:
                message = (
                    f"Could not save the profile: {exc.error}. Could not restore previous profile: "
                    f"{exc.rollback_error}. Credential ID: {profile.credential_id}."
                )
        else:
            message = f"Could not save the profile: {exc.error}. The previous profile was restored."
            if exc.cleanup_failures:
                message = (
                    f"Could not save the profile: {exc.error}. The previous profile was "
                    "restored, but staged credentials could not be removed: "
                    f"{', '.join(exc.cleanup_failures)}. Retry cleanup with 'slcli config cleanup'."
                )
        raise ProfileCredentialError(message, warnings) from exc
    if (
        previous
        and previous.credential_store != "os"
        and previous.auth_mode == "pkce"
        and profile.auth_mode == "api-key"
    ):
        from .credentials import delete_legacy_pkce_credentials

        try:
            delete_legacy_pkce_credentials(profile.name, profile.credential_store)
        except CredentialStoreError as exc:
            warnings.append(f"Could not remove obsolete PKCE credentials: {exc}")
    return warnings


def secure_profile_credentials(
    config: ProfileConfig, profiles: list[Profile]
) -> tuple[list[str], list[str]]:
    """Move selected plaintext credentials to the OS store as one metadata update.

    Args:
        config: Configuration owning the selected profiles and pending cleanup.
        profiles: Profiles whose plaintext credentials should be secured.

    Returns:
        Sorted secured profile names and nonfatal cleanup warnings.

    Raises:
        ProfileCredentialError: Staging or metadata persistence failed.
    """
    pending: list[tuple[Profile, str, str]] = []
    for profile in profiles:
        if profile.api_key:
            pending.append((profile, "api-key", profile.api_key))
        if profile.pkce_credentials:
            pending.append((profile, "pkce", json.dumps(profile.pkce_credentials)))
    if not pending:
        return [], []

    originals = {profile.name: profile for profile, _, _ in pending}
    replacements = {
        name: replace(original, credential_id=str(uuid4()), credential_store="os")
        for name, original in originals.items()
    }
    staged: list[tuple[Profile, str]] = []
    try:
        for original, credential, value in pending:
            profile = replacements[original.name]
            staged.append((profile, credential))
            set_credential(profile.credential_id, credential, value, "os")
    except CredentialStoreError as exc:
        failures = _remove_staged_credentials(config, staged)
        raise ProfileCredentialError(
            f"Could not secure profile credentials: {exc}. "
            + (f"Could not remove staged credentials: {', '.join(failures)}." if failures else "")
        ) from exc

    for profile in replacements.values():
        profile.api_key = ""
        profile.pkce_credentials = {}
    try:
        warnings = _persist_replacements(config, replacements, staged, config.current_profile)
    except _ProfileSaveError as exc:
        raise ProfileCredentialError(
            f"Could not save secured profiles: {exc.error}. "
            + (
                f"Could not remove staged credentials: {', '.join(exc.cleanup_failures)}."
                if exc.cleanup_failures
                else ""
            )
            + (
                f" Could not restore previous config: {exc.rollback_error}."
                if exc.rollback_error
                else ""
            )
        ) from exc
    return sorted(replacements), warnings
