"""Tests for profile-explicit migration connections."""

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import click
import pytest
from requests.adapters import HTTPAdapter

from slcli.migration.connection import MigrationConnection, resolve_migration_connection
from slcli.pkce import PkceError
from slcli.profiles import Profile, ProfileConfig
from slcli.utils import get_auth_resolution, get_ssl_verify


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
    monkeypatch.setenv("SLCLI_WEB_URL", "https://environment-web")
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


def test_source_tls_opt_out_does_not_reach_destination(monkeypatch: pytest.MonkeyPatch) -> None:
    """An insecure source profile, even when active, leaves the destination verified."""
    monkeypatch.delenv("SLCLI_SSL_VERIFY", raising=False)
    monkeypatch.setattr("slcli.ssl_trust.get_managed_trust_path", lambda _url: None)
    for name in ("REQUESTS_CA_BUNDLE", "SSL_CERT_FILE"):
        monkeypatch.delenv(name, raising=False)
    source = Profile("source", server="https://old", api_key="a", ssl_verify=False)
    config = _config(
        source, Profile("destination", server="https://new", api_key="b"), current="source"
    )
    monkeypatch.setattr("slcli.profiles.get_active_profile", lambda: source)

    assert resolve_migration_connection("source", config).ssl_verify is False
    assert resolve_migration_connection("destination", config).ssl_verify is True
    assert get_ssl_verify("https://old/nitag/v2") is False
    assert get_ssl_verify("https://new") is True


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
        monkeypatch.setattr("slcli.pkce.get_pkce_access_token", lambda *args: "token")

        connection = resolve_migration_connection("source", _config(self.PROFILE))

        assert connection.base_url == "https://web.source"
        assert connection.headers["Authorization"] == "Bearer token"
        assert "x-ni-api-key" not in connection.headers

    def test_refresh_failure_requires_login(self, monkeypatch: Any) -> None:
        """An expired token that cannot be refreshed directs the user to log in."""

        def refresh_fails(*args: object, **kwargs: object) -> None:
            raise PkceError("expired")

        monkeypatch.setattr("slcli.pkce.get_pkce_access_token", lambda *args: None)
        monkeypatch.setattr("slcli.pkce.refresh_pkce_credentials", refresh_fails)

        with pytest.raises(click.ClickException, match="slcli login --profile source"):
            resolve_migration_connection("source", _config(self.PROFILE))


def test_os_api_key_uses_profile_identity(monkeypatch: pytest.MonkeyPatch) -> None:
    """Explicit and ambient auth share OS credential lookup, not plaintext metadata."""
    profile = Profile(
        "renamed", server="https://source", credential_id="stable-id", credential_store="os"
    )
    read = MagicMock(return_value="stored-key")
    monkeypatch.setattr("slcli.credentials.get_credential", read)
    monkeypatch.setattr("slcli.profiles.get_active_profile", lambda: profile)
    monkeypatch.setenv("SLCLI_API_KEY", "environment-key")

    connection = resolve_migration_connection("renamed", _config(profile))

    assert connection.headers["x-ni-api-key"] == "stored-key"
    read.assert_called_once_with("stable-id", "api-key")
    assert get_auth_resolution().value == "environment-key"
    read.reset_mock()
    monkeypatch.delenv("SLCLI_API_KEY")
    assert get_auth_resolution().value == "stored-key"
    read.assert_called_once_with("stable-id", "api-key")


@pytest.mark.parametrize("missing", [False, True])
def test_os_api_key_failure_is_reported(monkeypatch: pytest.MonkeyPatch, missing: bool) -> None:
    """Missing and inaccessible stored API keys produce actionable errors."""
    from slcli.credentials import CredentialStoreError

    read = MagicMock(return_value=None)
    if not missing:
        read.side_effect = CredentialStoreError("credential store locked")
    monkeypatch.setattr("slcli.credentials.get_credential", read)
    profile = Profile("source", server="https://source", credential_store="os")

    with pytest.raises(
        click.ClickException, match="does not define an API key" if missing else "store locked"
    ):
        resolve_migration_connection("source", _config(profile))


@pytest.mark.parametrize("store", ["os", "file"])
@pytest.mark.parametrize("expired", [False, True])
@pytest.mark.parametrize("verify", [False, True])
def test_pkce_uses_selected_store_identity_and_tls(
    monkeypatch: pytest.MonkeyPatch, store: str, expired: bool, verify: bool
) -> None:
    """Migration uses shared PKCE caching/rotation with the profile's TLS policy."""
    profile = Profile(
        "renamed",
        server="https://api.source",
        web_url="https://web.source",
        auth_mode="pkce",
        pkce_client_id="client",
        credential_id="stable-id",
        credential_store=store,
        ssl_verify=verify,
    )
    read = MagicMock(
        return_value=json.dumps(
            {
                "access-token": "cached-token",
                "refresh-token": "old-refresh",
                "access-expires-at": 999.0 if expired else 4600.0,
            }
        )
    )
    write = MagicMock()
    response = MagicMock()
    response.json.return_value = {
        "access_token": "fresh-token",
        "refresh_token": "rotated-refresh",
        "expires_in": 3600,
    }
    post = MagicMock(return_value=response)
    monkeypatch.setattr("slcli.pkce.time.time", lambda: 1000.0)
    monkeypatch.setattr("slcli.pkce.get_credential", read)
    monkeypatch.setattr("slcli.pkce.set_credential", write)
    monkeypatch.setattr("slcli.pkce.requests.post", post)
    monkeypatch.setattr("slcli.ssl_trust.get_managed_trust_path", lambda _url: None)
    monkeypatch.setenv("SLCLI_API_KEY", "environment-key")
    monkeypatch.setenv("SLCLI_API_URL", "https://environment-api")
    monkeypatch.setenv("SLCLI_WEB_URL", "https://environment-web")
    monkeypatch.delenv("SLCLI_SSL_VERIFY", raising=False)
    monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)

    connection = resolve_migration_connection("renamed", _config(profile))

    assert connection.base_url == "https://web.source"
    assert connection.ssl_verify is verify
    assert connection.headers["Authorization"] == (
        "Bearer fresh-token" if expired else "Bearer cached-token"
    )
    read.assert_called_with("stable-id", "pkce", store)
    if expired:
        assert post.call_args.args == ("https://web.source/nitoken/v1/token",)
        assert post.call_args.kwargs["verify"] is verify
        assert post.call_args.kwargs["data"]["refresh_token"] == "old-refresh"
        assert write.call_args.args[:2] == ("stable-id", "pkce")
        assert write.call_args.args[3] == store
        assert json.loads(write.call_args.args[2])["refresh-token"] == "rotated-refresh"
    else:
        post.assert_not_called()
        write.assert_not_called()


def test_file_pkce_uses_persisted_profile_bundle(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """File-backed tokens are found by stable identity after a profile rename."""
    monkeypatch.setattr(
        ProfileConfig, "get_config_path", classmethod(lambda cls: tmp_path / "config.json")
    )
    profile = Profile(
        "renamed",
        server="https://api",
        web_url="https://web",
        auth_mode="pkce",
        credential_store="file",
        credential_id="stable-id",
        pkce_credentials={"access-token": "file-token"},
    )
    config = _config(profile)
    config.save()
    monkeypatch.setenv("SLCLI_PROFILE", "unrelated")

    connection = resolve_migration_connection("renamed", config)

    assert connection.headers["Authorization"] == "Bearer file-token"


@pytest.mark.parametrize("bundle", [None, "managed.pem"])
def test_migration_tls_shares_ambient_policy(monkeypatch: pytest.MonkeyPatch, bundle: Any) -> None:
    """Explicit connections share managed trust and the SLCLI_SSL_VERIFY override."""
    lookup = MagicMock(return_value=Path(bundle) if bundle else None)
    monkeypatch.setattr("slcli.ssl_trust.get_managed_trust_path", lookup)
    monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    monkeypatch.delenv("SLCLI_SSL_VERIFY", raising=False)
    config = _config(Profile("source", server="https://source/", api_key="key"))

    assert resolve_migration_connection("source", config).ssl_verify == (bundle or True)
    lookup.assert_called_once_with("https://source")
    monkeypatch.setenv("SLCLI_SSL_VERIFY", "false")
    assert resolve_migration_connection("source", config).ssl_verify is False


@pytest.mark.parametrize("variable", ["REQUESTS_CA_BUNDLE", "SSL_CERT_FILE"])
def test_migration_tls_supports_standard_ca_bundle(
    monkeypatch: pytest.MonkeyPatch, variable: str
) -> None:
    """Standard requests CA bundles remain supported for explicit connections."""
    for name in ("REQUESTS_CA_BUNDLE", "SSL_CERT_FILE", "SLCLI_SSL_VERIFY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv(variable, "corporate.pem")
    monkeypatch.setattr("slcli.ssl_trust.OS_TRUST_INJECTED", False)
    monkeypatch.setattr("slcli.ssl_trust.get_managed_trust_path", lambda _url: None)
    profile = Profile("source", server="http://source", api_key="key")

    assert resolve_migration_connection("source", _config(profile)).ssl_verify == "corporate.pem"
