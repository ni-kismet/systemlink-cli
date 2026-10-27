"""Tests for profile-explicit migration connections."""

from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace
from typing import Dict, Optional
from unittest.mock import MagicMock

import click
import pytest
from requests.adapters import HTTPAdapter

from slcli.credentials import CredentialStoreError
from slcli.migration.connection import MigrationConnection, resolve_migration_connection
from slcli.pkce import PkceError
from slcli.profiles import Profile, ProfileConfig

PKCE_PROFILE = Profile(
    "source",
    server="https://api.source",
    web_url="https://web.source/",
    auth_mode="pkce",
    pkce_client_id="client",
    credential_id="stable-id",
    credential_store="file",
)


def _config(*profiles: Profile, current: Optional[str] = None) -> ProfileConfig:
    return ProfileConfig(current_profile=current, profiles={p.name: p for p in profiles})


def _auth_headers(connection: MigrationConnection) -> Dict[str, str]:
    return {
        name: value
        for name, value in connection.headers.items()
        if name in ("x-ni-api-key", "Authorization")
    }


@pytest.fixture(autouse=True)
def no_ambient_trust(monkeypatch: pytest.MonkeyPatch) -> None:
    """Start each test with plain certificate verification."""
    monkeypatch.setattr("slcli.ssl_trust.get_managed_trust_path", lambda _url: None)
    monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)


# Sessions


def test_session_carries_credentials_and_tls() -> None:
    """Sessions use the connection's headers and TLS, and repr hides secrets."""
    connection = MigrationConnection(
        "source", "https://source", {"x-ni-api-key": "secret"}, ssl_verify=False
    )

    session = connection.create_session()

    assert session.headers["x-ni-api-key"] == "secret"
    assert session.verify is False
    assert "secret" not in repr(connection)


def test_session_retries_transient_query_failures() -> None:
    """Read queries, including POST queries, retry throttling and server errors."""
    session = MigrationConnection("source", "https://source", {}).create_session()

    adapter = session.get_adapter("https://source")
    assert isinstance(adapter, HTTPAdapter)
    retry = adapter.max_retries
    assert retry.total == 5
    assert {429, 503} <= set(retry.status_forcelist or ())
    assert "POST" in (retry.allowed_methods or ())


# Profile selection


def test_uses_named_profile_not_current_profile_or_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """The current profile and server/credential env overrides do not apply."""
    monkeypatch.setenv("SLCLI_PROFILE", "default")
    monkeypatch.setenv("SLCLI_API_URL", "https://environment")
    monkeypatch.setenv("SLCLI_API_KEY", "environment-key")
    monkeypatch.setenv("SLCLI_WEB_URL", "https://environment-web")
    config = _config(
        Profile("default", server="https://default", api_key="default-key"),
        Profile("source", server="https://source/", api_key="source-key"),
        current="default",
    )

    connection = resolve_migration_connection("source", config)

    assert connection.profile_name == "source"
    assert connection.base_url == "https://source"
    assert _auth_headers(connection) == {"x-ni-api-key": "source-key"}


def test_missing_profile_does_not_fall_back() -> None:
    """A missing profile fails even when a current profile exists."""
    config = _config(Profile("default", server="https://default", api_key="key"), current="default")

    with pytest.raises(click.ClickException, match="Profile 'missing' not found"):
        resolve_migration_connection("missing", config)


@pytest.mark.parametrize(
    ("profile", "message"),
    [
        pytest.param(
            Profile("source", server="", api_key="key"),
            "does not define a server URL",
            id="no-server",
        ),
        pytest.param(
            Profile("source", server="https://source"),
            "does not define an API key",
            id="no-api-key",
        ),
        pytest.param(
            Profile("source", server="https://source", auth_mode="pkce"),
            "does not define a Web UI URL",
            id="pkce-no-web-url",
        ),
    ],
)
def test_rejects_incomplete_profile(profile: Profile, message: str) -> None:
    """Incomplete profiles fail with the missing setting."""
    with pytest.raises(click.ClickException, match=message):
        resolve_migration_connection("source", _config(profile))


# API-key authentication


def test_stored_api_key_is_read_by_credential_id(monkeypatch: pytest.MonkeyPatch) -> None:
    """A renamed profile finds its stored key by stable credential ID."""
    profile = Profile(
        "renamed", server="https://source", credential_id="stable-id", credential_store="os"
    )
    read = MagicMock(return_value="stored-key")
    monkeypatch.setattr("slcli.credentials.get_credential", read)

    connection = resolve_migration_connection("renamed", _config(profile))

    assert _auth_headers(connection) == {"x-ni-api-key": "stored-key"}
    read.assert_called_once_with("stable-id", "api-key")


def test_unreadable_api_key_is_reported(monkeypatch: pytest.MonkeyPatch) -> None:
    """Credential store failures surface instead of looking like a missing key."""
    monkeypatch.setattr(
        "slcli.credentials.get_credential",
        MagicMock(side_effect=CredentialStoreError("credential store locked")),
    )
    profile = Profile("source", server="https://source", credential_store="os")

    with pytest.raises(click.ClickException, match="store locked"):
        resolve_migration_connection("source", _config(profile))


# PKCE authentication


def test_pkce_uses_web_route_and_bearer_token(monkeypatch: pytest.MonkeyPatch) -> None:
    """PKCE tokens authenticate against the Web Server route, not the API route."""
    monkeypatch.setattr("slcli.pkce.get_pkce_access_token", lambda *_args: "CACHED-TOKEN")

    connection = resolve_migration_connection("source", _config(PKCE_PROFILE))

    assert connection.base_url == "https://web.source"
    assert _auth_headers(connection) == {"Authorization": "Bearer CACHED-TOKEN"}


@pytest.mark.parametrize(
    ("profile_verify", "env_verify", "managed_trust", "expected"),
    [
        pytest.param(True, None, None, True, id="default"),
        pytest.param(False, None, None, False, id="profile-opt-out"),
        pytest.param(True, "false", None, False, id="env-opt-out"),
        pytest.param(True, None, "managed.pem", "managed.pem", id="managed-trust"),
    ],
)
def test_pkce_refresh_uses_profile_identity_and_tls(
    monkeypatch: pytest.MonkeyPatch,
    profile_verify: bool,
    env_verify: Optional[str],
    managed_trust: Optional[str],
    expected: object,
) -> None:
    """An expired token refreshes with the named profile's credentials and TLS policy."""
    if env_verify is not None:
        monkeypatch.setenv("SLCLI_SSL_VERIFY", env_verify)
    if managed_trust is not None:
        monkeypatch.setattr(
            "slcli.ssl_trust.get_managed_trust_path", lambda _url: Path(managed_trust)
        )
    profile = replace(PKCE_PROFILE, ssl_verify=profile_verify)
    refresh = MagicMock(return_value=SimpleNamespace(access_token="REFRESHED-TOKEN"))
    monkeypatch.setattr("slcli.pkce.get_pkce_access_token", lambda *_args: None)
    monkeypatch.setattr("slcli.pkce.refresh_pkce_credentials", refresh)

    connection = resolve_migration_connection("source", _config(profile))

    assert _auth_headers(connection) == {"Authorization": "Bearer REFRESHED-TOKEN"}
    assert connection.ssl_verify == expected
    refresh.assert_called_once_with(
        "stable-id", "https://web.source/", "client", "file", ssl_verify=expected
    )


def test_pkce_refresh_failure_requires_login(monkeypatch: pytest.MonkeyPatch) -> None:
    """A token that cannot be refreshed directs the user to log in again."""
    monkeypatch.setattr("slcli.pkce.get_pkce_access_token", lambda *_args: None)
    monkeypatch.setattr(
        "slcli.pkce.refresh_pkce_credentials", MagicMock(side_effect=PkceError("expired"))
    )

    with pytest.raises(click.ClickException, match="slcli login --profile source"):
        resolve_migration_connection("source", _config(PKCE_PROFILE))


# TLS


def test_tls_opt_out_applies_only_to_its_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    """An insecure source profile, even when active, leaves the destination verified."""
    source = Profile("source", server="https://old", api_key="a", ssl_verify=False)
    destination = Profile("destination", server="https://new", api_key="b")
    monkeypatch.setattr("slcli.profiles.get_active_profile", lambda: source)
    config = _config(source, destination, current="source")

    assert resolve_migration_connection("source", config).ssl_verify is False
    assert resolve_migration_connection("destination", config).ssl_verify is True


def test_tls_uses_managed_trust(monkeypatch: pytest.MonkeyPatch) -> None:
    """A certificate accepted for the profile's server is used for verification."""
    lookup = MagicMock(return_value=Path("managed.pem"))
    monkeypatch.setattr("slcli.ssl_trust.get_managed_trust_path", lookup)
    config = _config(Profile("source", server="https://source/", api_key="key"))

    assert resolve_migration_connection("source", config).ssl_verify == "managed.pem"
    lookup.assert_called_once_with("https://source")


@pytest.mark.parametrize(
    ("variable", "value", "expected"),
    [
        ("SLCLI_SSL_VERIFY", "false", False),
        ("REQUESTS_CA_BUNDLE", "corporate.pem", "corporate.pem"),
        ("SSL_CERT_FILE", "corporate.pem", "corporate.pem"),
    ],
)
def test_tls_honors_environment(
    monkeypatch: pytest.MonkeyPatch, variable: str, value: str, expected: object
) -> None:
    """TLS environment settings apply to migration connections like any CLI command."""
    monkeypatch.setattr("slcli.ssl_trust.OS_TRUST_INJECTED", False)
    monkeypatch.setenv(variable, value)
    config = _config(Profile("source", server="https://source", api_key="key"))

    assert resolve_migration_connection("source", config).ssl_verify == expected
