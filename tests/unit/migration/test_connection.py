"""Tests for profile-explicit migration connections."""

from typing import Any

import click
import pytest
from requests.adapters import HTTPAdapter

from slcli.migration import connection as connection_module
from slcli.migration.connection import MigrationConnection, resolve_migration_connection
from slcli.pkce import PkceError
from slcli.profiles import Profile, ProfileConfig


def test_session_carries_credentials_and_tls() -> None:
    """Clients inherit authentication and TLS from the profile-bound session."""
    connection = MigrationConnection("p", "https://source", {"x-ni-api-key": "secret"}, False)

    session = connection.create_session()

    assert session.headers["x-ni-api-key"] == "secret"
    assert session.verify is False
    assert "secret" not in repr(connection)


def test_session_retries_transient_failures() -> None:
    """Migration sessions retry throttling and server errors for read queries."""
    session = MigrationConnection("p", "https://source", {}).create_session()

    adapter = session.get_adapter("https://source")
    assert isinstance(adapter, HTTPAdapter)
    retry = adapter.max_retries
    assert retry.total == 5
    assert {429, 503} <= set(retry.status_forcelist or ())
    assert "POST" in (retry.allowed_methods or ())


def _config(*profiles: Profile, current: str = "") -> ProfileConfig:
    return ProfileConfig(current_profile=current or None, profiles={p.name: p for p in profiles})


def test_resolves_only_the_named_profile(monkeypatch: pytest.MonkeyPatch) -> None:
    """The current profile and environment overrides never contribute settings."""
    monkeypatch.setenv("SLCLI_PROFILE", "default")
    monkeypatch.setenv("SLCLI_API_URL", "https://environment")
    monkeypatch.setenv("SLCLI_API_KEY", "environment-key")
    monkeypatch.setenv("SLCLI_SSL_VERIFY", "true")
    config = _config(
        Profile("default", server="https://default", api_key="default-key"),
        Profile("source", server="https://source/", api_key="source-key", ssl_verify=False),
        current="default",
    )

    connection = resolve_migration_connection("source", config)

    assert connection.profile_name == "source"
    assert connection.base_url == "https://source"
    assert connection.headers["x-ni-api-key"] == "source-key"
    assert "Authorization" not in connection.headers
    assert connection.ssl_verify is False


def test_missing_profile_does_not_fall_back() -> None:
    """A missing profile fails even when a current profile exists."""
    config = _config(Profile("default", server="https://default", api_key="key"), current="default")

    with pytest.raises(click.ClickException, match="Profile 'missing' not found"):
        resolve_migration_connection("missing", config)


@pytest.mark.parametrize(
    ("profile", "message"),
    [
        (Profile("source", server="", api_key="key"), "does not define a server URL"),
        (Profile("source", server="https://source"), "does not define an API key"),
        (
            Profile("source", server="https://source", auth_mode="pkce"),
            "does not define a Web UI URL",
        ),
    ],
)
def test_rejects_incomplete_profile(profile: Profile, message: str) -> None:
    """Incomplete profiles fail with the missing setting."""
    with pytest.raises(click.ClickException, match=message):
        resolve_migration_connection("source", _config(profile))


class TestPkce:
    """PKCE profiles use their Web Server route and cached or refreshed tokens."""

    PROFILE = Profile(
        "source",
        server="https://api.source",
        web_url="https://web.source/",
        auth_mode="pkce",
        pkce_client_id="client",
    )

    def test_uses_web_route_and_bearer_token(self, monkeypatch: Any) -> None:
        """A cached token authenticates against the Web Server route."""
        monkeypatch.setattr(connection_module, "get_pkce_access_token", lambda name: "token")

        connection = resolve_migration_connection("source", _config(self.PROFILE))

        assert connection.base_url == "https://web.source"
        assert connection.headers["Authorization"] == "Bearer token"
        assert "x-ni-api-key" not in connection.headers

    def test_refresh_failure_requires_login(self, monkeypatch: Any) -> None:
        """An expired token that cannot be refreshed directs the user to log in."""

        def refresh_fails(*args: object) -> None:
            raise PkceError("expired")

        monkeypatch.setattr(connection_module, "get_pkce_access_token", lambda name: None)
        monkeypatch.setattr(connection_module, "refresh_pkce_credentials", refresh_fails)

        with pytest.raises(click.ClickException, match="slcli login --profile source"):
            resolve_migration_connection("source", _config(self.PROFILE))
