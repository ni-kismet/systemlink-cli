"""Behavior tests through the profile credential module's interface."""

from pathlib import Path
from typing import Iterator, Optional

import pytest

from slcli import credentials
from slcli.profile_credentials import (
    ProfileCredentialError,
    save_profile_credentials,
    secure_profile_credentials,
)
from slcli.profiles import Profile, ProfileConfig


@pytest.fixture
def config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> ProfileConfig:
    """Use an isolated config with an unrelated selected profile."""
    path = tmp_path / "config.json"
    monkeypatch.setattr(ProfileConfig, "get_config_path", classmethod(lambda cls: path))
    config = ProfileConfig(current_profile="other")
    config.add_profile(Profile(name="other", server="https://other.example.com", api_key="other"))
    config.save()
    return config


@pytest.fixture
def credential_store(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[dict[tuple[str, str], str]]:
    """Substitute native storage without replacing the credential module."""
    store: dict[tuple[str, str], str] = {}

    def get(profile_id: str, credential: str) -> Optional[str]:
        return store.get((profile_id, credential))

    def set_value(profile_id: str, credential: str, value: str) -> None:
        store[profile_id, credential] = value

    def delete(profile_id: str, credential: str) -> None:
        store.pop((profile_id, credential), None)

    monkeypatch.setattr(credentials.platform, "system", lambda: "Darwin")
    monkeypatch.setattr(credentials, "_macos_get", get)
    monkeypatch.setattr(credentials, "_macos_set", set_value)
    monkeypatch.setattr(credentials, "_macos_delete", delete)
    monkeypatch.setattr(credentials, "_macos_delete_account", lambda account: None)
    credentials._cached_get.cache_clear()
    yield store
    credentials._cached_get.cache_clear()


@pytest.mark.parametrize("auth_mode", ["api-key", "pkce"])
@pytest.mark.parametrize("original_store", ["file", "os"])
@pytest.mark.parametrize("set_current", [False, True])
def test_login_replaces_credentials_and_selects_profile(
    config: ProfileConfig,
    credential_store: dict[tuple[str, str], str],
    monkeypatch: pytest.MonkeyPatch,
    auth_mode: str,
    original_store: str,
    set_current: bool,
) -> None:
    """Persistence exposes the new credential and retires the previous ID."""
    original = Profile(
        name="dev",
        server="https://old.example.com",
        credential_store=original_store,
        api_key="old" if original_store == "file" else "",
    )
    config.add_profile(original)
    config.save()
    if original_store == "os":
        credential_store[(original.credential_id, "api-key")] = "old"

    def stage(profile_id: str, credential: str, value: str) -> None:
        assert ProfileConfig.load().profiles["dev"] == original
        if original_store == "os":
            assert credential_store[(original.credential_id, "api-key")] == "old"
        credential_store[(profile_id, credential)] = value

    monkeypatch.setattr(credentials, "_macos_set", stage)
    profile = Profile(
        name="dev",
        server="https://new.example.com",
        api_key="new-key" if auth_mode == "api-key" else "",
        credential_store="os",
        auth_mode=auth_mode,
        pkce_credentials=(
            {"access-token": "new-token", "refresh-token": None, "access-expires-at": None}
            if auth_mode == "pkce"
            else {}
        ),
    )

    assert save_profile_credentials(config, profile, set_current=set_current) == []

    saved = ProfileConfig.load()
    assert saved.current_profile == ("dev" if set_current else "other")
    assert saved.profiles["dev"].server == profile.server
    assert saved.profiles["dev"].credential_id != original.credential_id
    assert "new-key" not in ProfileConfig.get_config_path().read_text()
    assert "new-token" not in ProfileConfig.get_config_path().read_text()
    assert not any(profile_id == original.credential_id for profile_id, _ in credential_store)
    credential = "pkce" if auth_mode == "pkce" else "api-key"
    assert credentials.get_credential(profile.credential_id, credential) is not None
    assert credentials.PENDING_DELETIONS_SETTING not in saved.settings


def test_secure_batch_keeps_selection_and_stages_before_metadata(
    config: ProfileConfig,
    credential_store: dict[tuple[str, str], str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """All selected plaintext profiles stay persisted until staging succeeds."""
    selected = [
        Profile(name=name, server="https://example.com", api_key=name) for name in ("dev", "prod")
    ]
    for profile in selected:
        config.add_profile(profile)
    config.save()

    def stage(profile_id: str, credential: str, value: str) -> None:
        saved = ProfileConfig.load()
        assert all(saved.profiles[profile.name].api_key == profile.name for profile in selected)
        credential_store[(profile_id, credential)] = value

    monkeypatch.setattr(credentials, "_macos_set", stage)

    assert secure_profile_credentials(config, selected) == (["dev", "prod"], [])

    saved = ProfileConfig.load()
    assert saved.current_profile == "other"
    for original in selected:
        secured = saved.profiles[original.name]
        assert secured.credential_id != original.credential_id
        assert secured.api_key == ""
        assert secured.credential_store == "os"
        assert credentials.get_credential(secured.credential_id, "api-key") == original.api_key


@pytest.mark.parametrize("operation", ["login", "secure"])
@pytest.mark.parametrize("cleanup_fails", [False, True])
@pytest.mark.parametrize("original_store", ["file", "os"])
@pytest.mark.parametrize("auth_mode", ["api-key", "pkce"])
def test_failed_save_preserves_profile_and_tracks_failed_cleanup(
    config: ProfileConfig,
    credential_store: dict[tuple[str, str], str],
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
    cleanup_fails: bool,
    original_store: str,
    auth_mode: str,
) -> None:
    """Save failures preserve usable credentials and retryable cleanup records."""
    original = Profile(
        name="dev",
        server="https://old.example.com",
        api_key="old" if auth_mode == "api-key" else "",
        auth_mode=auth_mode,
        credential_store=original_store,
        pkce_credentials={"access-token": "old-token"} if auth_mode == "pkce" else {},
    )
    config.add_profile(original)
    config.save()
    save = ProfileConfig.save
    failed = False

    def fail_once(config: ProfileConfig) -> None:
        nonlocal failed
        if not failed:
            failed = True
            raise RuntimeError("disk full")
        save(config)

    def fail_cleanup(profile_id: str, credential: str) -> None:
        raise credentials.CredentialStoreError("locked")

    monkeypatch.setattr(ProfileConfig, "save", fail_once)
    if cleanup_fails:
        monkeypatch.setattr(credentials, "_macos_delete", fail_cleanup)

    with pytest.raises(ProfileCredentialError, match="Could not save"):
        if operation == "login":
            save_profile_credentials(
                config,
                Profile(
                    name="dev",
                    server="https://new.example.com",
                    api_key="new",
                    credential_store="os",
                    auth_mode=auth_mode,
                    pkce_credentials=(
                        {
                            "access-token": "new-token",
                            "refresh-token": None,
                            "access-expires-at": None,
                        }
                        if auth_mode == "pkce"
                        else {}
                    ),
                ),
                set_current=True,
            )
        else:
            secure_profile_credentials(config, [original])

    saved = ProfileConfig.load()
    assert saved.current_profile == "other"
    assert saved.profiles["dev"] == original
    assert config.profiles["dev"] == original
    pending = saved.settings.get(credentials.PENDING_DELETIONS_SETTING, [])
    if cleanup_fails:
        assert len(pending) == 1
        assert pending[0]["id"] != original.credential_id
        assert pending[0]["id"] in {profile_id for profile_id, _ in credential_store}
    else:
        assert pending == []
        assert credential_store == {}


@pytest.mark.parametrize("operation", ["login", "secure"])
def test_failed_rollback_reports_stranded_id_and_preserves_original(
    config: ProfileConfig,
    credential_store: dict[tuple[str, str], str],
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    """Compound failures retain usable metadata and identify the unreachable OS item."""
    original = Profile(name="dev", server="https://example.com", api_key="old")
    config.add_profile(original)
    config.save()

    def fail_save(config: ProfileConfig) -> None:
        raise RuntimeError("disk full")

    def fail_cleanup(profile_id: str, credential: str) -> None:
        raise credentials.CredentialStoreError("locked")

    monkeypatch.setattr(ProfileConfig, "save", fail_save)
    monkeypatch.setattr(credentials, "_macos_delete", fail_cleanup)
    with pytest.raises(ProfileCredentialError) as error:
        if operation == "login":
            save_profile_credentials(
                config,
                Profile(
                    name="dev", server="https://example.com", api_key="new", credential_store="os"
                ),
                set_current=True,
            )
        else:
            secure_profile_credentials(config, [original])

    saved = ProfileConfig.load()
    assert saved.profiles["dev"] == original
    assert saved.current_profile == "other"
    assert config.profiles["dev"] == original
    assert config.current_profile == "other"
    stranded_id = next(iter(credential_store))[0]
    assert stranded_id in str(error.value)
    assert "restore" in str(error.value)
    assert config.settings[credentials.PENDING_DELETIONS_SETTING][0]["id"] == stranded_id


def test_retirement_failure_keeps_successful_replacement(
    config: ProfileConfig,
    credential_store: dict[tuple[str, str], str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Retirement failure warns without rolling back a usable replacement."""
    original = Profile(name="dev", server="https://old.example.com", credential_store="os")
    config.add_profile(original)
    config.save()
    credential_store[(original.credential_id, "api-key")] = "old"

    def fail_cleanup(profile_id: str, credential: str) -> None:
        raise credentials.CredentialStoreError("locked")

    monkeypatch.setattr(credentials, "_macos_delete", fail_cleanup)
    profile = Profile(
        name="dev", server="https://new.example.com", api_key="new", credential_store="os"
    )

    warnings = save_profile_credentials(config, profile)

    assert len(warnings) == 1
    assert "Could not remove replaced credentials" in warnings[0]
    saved = ProfileConfig.load()
    assert saved.profiles["dev"].credential_id == profile.credential_id
    assert saved.settings[credentials.PENDING_DELETIONS_SETTING][0]["id"] == original.credential_id
    assert credentials.get_credential(profile.credential_id, "api-key") == "new"


@pytest.mark.parametrize("auth_mode", ["api-key", "pkce"])
@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_partial_login_write_is_removed_or_reachable_for_retry(
    config: ProfileConfig,
    credential_store: dict[tuple[str, str], str],
    monkeypatch: pytest.MonkeyPatch,
    auth_mode: str,
    cleanup_fails: bool,
) -> None:
    """Fallback keeps abandoned OS IDs separate from the usable file profile."""
    attempted: list[str] = []

    def partial_write(profile_id: str, credential: str, value: str) -> None:
        attempted.append(profile_id)
        credential_store[(profile_id, credential)] = value
        raise credentials.CredentialStoreError("partial write")

    def fail_cleanup(profile_id: str, credential: str) -> None:
        raise credentials.CredentialStoreError("locked")

    monkeypatch.setattr(credentials, "_macos_set", partial_write)
    if cleanup_fails:
        monkeypatch.setattr(credentials, "_macos_delete", fail_cleanup)
    profile = Profile(
        name="dev",
        server="https://example.com",
        api_key="new-key" if auth_mode == "api-key" else "",
        auth_mode=auth_mode,
        credential_store="os",
        pkce_credentials=(
            {"access-token": "new-token", "refresh-token": None, "access-expires-at": None}
            if auth_mode == "pkce"
            else {}
        ),
    )

    warnings = save_profile_credentials(config, profile)

    saved = ProfileConfig.load()
    assert saved.profiles["dev"].credential_store == "file"
    assert saved.profiles["dev"].credential_id != attempted[0]
    assert "storing this profile in the config file" in warnings[0]
    assert saved.profiles["dev"].api_key == profile.api_key
    assert saved.profiles["dev"].pkce_credentials == profile.pkce_credentials
    if cleanup_fails:
        assert saved.settings[credentials.PENDING_DELETIONS_SETTING][0]["id"] == attempted[0]
        assert "Retry cleanup" in warnings[1]
        monkeypatch.setattr(
            credentials,
            "_macos_delete",
            lambda profile_id, credential: credential_store.pop((profile_id, credential), None),
        )
        assert credentials.retry_pending_profile_deletions(saved) == ["dev"]
        assert ProfileConfig.load().profiles["dev"] == profile
    else:
        assert credentials.PENDING_DELETIONS_SETTING not in saved.settings
    assert credential_store == {}


@pytest.mark.parametrize("operation", ["login", "secure"])
def test_unavailable_store_preserves_each_operation_policy(
    config: ProfileConfig,
    credential_store: dict[tuple[str, str], str],
    monkeypatch: pytest.MonkeyPatch,
    operation: str,
) -> None:
    """Login permits warned file fallback while secure preserves plaintext on failure."""
    original = Profile(name="dev", server="https://old.example.com", api_key="old")
    config.add_profile(original)
    config.save()

    def unavailable(profile_id: str, credential: str, value: str) -> None:
        raise credentials.CredentialStoreUnavailable("unavailable")

    monkeypatch.setattr(credentials, "_macos_set", unavailable)
    if operation == "login":
        profile = Profile(
            name="dev", server="https://new.example.com", api_key="new", credential_store="os"
        )
        warnings = save_profile_credentials(config, profile)
        assert len(warnings) == 1
        assert "storing this profile in the config file" in warnings[0]
        assert ProfileConfig.load().profiles["dev"].api_key == "new"
        assert ProfileConfig.load().profiles["dev"].credential_store == "file"
    else:
        with pytest.raises(ProfileCredentialError, match="Could not secure"):
            secure_profile_credentials(config, [original])
        assert ProfileConfig.load().profiles["dev"] == original
    assert credential_store == {}
