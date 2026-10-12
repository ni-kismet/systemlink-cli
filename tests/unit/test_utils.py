"""Test utilities for slcli unit tests."""

import json
from pathlib import Path
from typing import Any, Callable, Dict
from unittest.mock import MagicMock, patch

import click
import pytest


def patch_keyring(monkeypatch: Any, platform: str = "SLE") -> None:
    """Set the environment-based configuration used by CLI tests.

    Args:
        monkeypatch: pytest monkeypatch fixture
        platform: Platform type - "SLE" (default) or "SLS"
    """
    monkeypatch.setenv("SLCLI_API_URL", "http://localhost:8000")
    monkeypatch.setenv("SLCLI_API_KEY", "dummy-api-key")
    monkeypatch.setenv("SLCLI_PLATFORM", platform)


def test_escape_filter_value_escapes_backslashes_before_quotes() -> None:
    """Filter values cannot terminate a quoted literal after a backslash."""
    from slcli.utils import escape_filter_value

    assert escape_filter_value('fixture\\" or AssetType = "SYSTEM') == (
        'fixture\\\\\\" or AssetType = \\"SYSTEM'
    )


def test_get_web_url_derives_from_api_url_without_profile(monkeypatch: Any) -> None:
    """get_web_url derives the web URL when no profile provides one."""
    from slcli.utils import get_web_url

    monkeypatch.setenv("SLCLI_API_URL", "https://dev-api.lifecyclesolutions.ni.com")
    monkeypatch.delenv("SLCLI_WEB_URL", raising=False)
    monkeypatch.setattr("slcli.profiles.get_active_profile", lambda: None)
    assert get_web_url() == "https://dev-api.lifecyclesolutions.ni.com"


@pytest.mark.parametrize(
    "legacy_env", ["SYSTEMLINK_API_URL", "SYSTEMLINK_WEB_URL", "SYSTEMLINK_API_KEY"]
)
def test_legacy_environment_aliases_do_not_override_profiles(
    monkeypatch: pytest.MonkeyPatch, legacy_env: str
) -> None:
    """Removed environment aliases cannot supply URLs or authentication credentials."""
    from slcli.profiles import Profile
    from slcli.utils import (
        ResolvedAuth,
        ResolvedConfigValue,
        get_auth_resolution,
        get_base_url_resolution,
        get_web_url_resolution,
    )

    for name in ("SLCLI_API_URL", "SLCLI_WEB_URL", "SLCLI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv(legacy_env, "legacy-value")
    monkeypatch.setattr(
        "slcli.profiles.get_active_profile",
        lambda: Profile(
            name="saved",
            server="https://api.example.com",
            web_url="https://web.example.com",
            api_key="profile-key",
            credential_store="file",
        ),
    )
    resolvers: dict[str, Callable[[], ResolvedAuth | ResolvedConfigValue]] = {
        "SYSTEMLINK_API_URL": get_base_url_resolution,
        "SYSTEMLINK_WEB_URL": get_web_url_resolution,
        "SYSTEMLINK_API_KEY": get_auth_resolution,
    }
    expected = {
        "SYSTEMLINK_API_URL": "https://api.example.com",
        "SYSTEMLINK_WEB_URL": "https://web.example.com",
        "SYSTEMLINK_API_KEY": "profile-key",
    }

    resolved = resolvers[legacy_env]()

    assert resolved.value == expected[legacy_env]
    assert resolved.source == (
        "profile:saved:file" if legacy_env.endswith("API_KEY") else "profile:saved"
    )


def test_legacy_api_key_does_not_override_pkce_routes(monkeypatch: pytest.MonkeyPatch) -> None:
    """Ignored legacy API keys cannot switch a PKCE profile to API-key routes."""
    from slcli.profiles import Profile
    from slcli.utils import get_base_url

    for name in ("SLCLI_API_URL", "SLCLI_WEB_URL", "SLCLI_API_KEY"):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("SYSTEMLINK_API_KEY", "legacy-value")
    monkeypatch.setattr(
        "slcli.profiles.get_active_profile",
        lambda: Profile(
            name="saved",
            server="https://api.example.com",
            web_url="https://web.example.com",
            auth_mode="pkce",
        ),
    )

    assert get_base_url() == "https://web.example.com"


def test_api_key_resolution_prefers_slcli_env_override(monkeypatch: Any, tmp_path: Path) -> None:
    """SLCLI_API_KEY overrides profile values regardless of removed aliases."""
    from slcli.utils import get_api_key_resolution

    config_file = tmp_path / "config.json"
    config_data: Dict[str, Any] = {
        "current-profile": "default",
        "profiles": {
            "default": {
                "server": "https://test.example.com",
                "api-key": "profile-key",
            }
        },
    }
    config_file.write_text(json.dumps(config_data))
    config_file.chmod(0o600)
    monkeypatch.setattr(
        "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
    )
    monkeypatch.setenv("SYSTEMLINK_API_KEY", "legacy-env-key")
    monkeypatch.setenv("SLCLI_API_KEY", "preferred-env-key")

    resolved = get_api_key_resolution()

    assert resolved.value == "preferred-env-key"
    assert resolved.source == "env:SLCLI_API_KEY"


@pytest.mark.parametrize("store", ["os", "file"])
def test_pkce_auth_resolution_returns_bearer_scheme(monkeypatch: Any, store: str) -> None:
    """PKCE profiles resolve to an access token and bearer scheme."""
    from slcli.profiles import Profile
    from slcli.utils import get_auth_resolution

    monkeypatch.setattr(
        "slcli.profiles.get_active_profile",
        lambda: Profile(
            name="pkce",
            server="https://api.example.com",
            auth_mode="pkce",
            pkce_client_id="client-id",
            credential_store=store,
        ),
    )
    monkeypatch.setattr(
        "slcli.pkce.resolve_pkce_token",
        lambda _profile, **_kwargs: MagicMock(access_token="access-token", source=f"{store}:pkce"),
    )

    resolved = get_auth_resolution()

    assert resolved.value == "access-token"
    assert resolved.source == f"profile:pkce:{store}:pkce"
    assert resolved.scheme == "bearer"


@pytest.mark.parametrize("store", ["os", "file"])
def test_pkce_refresh_source_includes_store(monkeypatch: Any, store: str) -> None:
    """Refreshed PKCE tokens retain the source store in their label."""
    from slcli.profiles import Profile
    from slcli.utils import get_auth_resolution

    monkeypatch.setattr(
        "slcli.profiles.get_active_profile",
        lambda: Profile(
            name="pkce",
            server="https://api.example.com",
            web_url="https://web.example.com",
            auth_mode="pkce",
            pkce_client_id="client-id",
            credential_store=store,
        ),
    )
    monkeypatch.setattr(
        "slcli.pkce.resolve_pkce_token",
        lambda _profile, **_kwargs: MagicMock(
            access_token="refreshed-token", source=f"{store}:pkce-refresh"
        ),
    )

    resolved = get_auth_resolution()

    assert resolved.value == "refreshed-token"
    assert resolved.source == f"profile:pkce:{store}:pkce-refresh"


@pytest.mark.parametrize("store", ["os", "file"])
@pytest.mark.parametrize("token_type", ["pkce", "pkce-refresh"])
def test_pkce_source_description_includes_store(store: str, token_type: str) -> None:
    """Info labels identify both token type and credential storage."""
    from slcli.credentials import describe_credential_store
    from slcli.utils import describe_config_source

    label = "refreshed PKCE token" if token_type == "pkce-refresh" else "PKCE bearer token"
    assert describe_config_source(f"profile:dev:{store}:{token_type}") == (
        f"Profile 'dev' ({label} in {describe_credential_store(store)})"
    )


def test_api_key_override_does_not_resolve_pkce(monkeypatch: Any) -> None:
    """Environment authentication leaves profile credentials entirely untouched."""
    from slcli.utils import get_auth_resolution

    resolver = MagicMock(side_effect=AssertionError("PKCE must remain lazy"))
    monkeypatch.setenv("SLCLI_API_KEY", "override")
    monkeypatch.setattr("slcli.pkce.resolve_pkce_token", resolver)
    monkeypatch.setattr("slcli.profiles.get_active_profile", resolver)

    result = get_auth_resolution()

    assert result.value == "override"
    assert result.scheme == "api-key"
    resolver.assert_not_called()


@pytest.mark.parametrize("emit_error", [True, False])
def test_pkce_resolution_error_is_translated(monkeypatch: Any, emit_error: bool) -> None:
    """The auth caller preserves PKCE errors and forwards the guidance preference."""
    from slcli.pkce import PkceError
    from slcli.profiles import Profile
    from slcli.utils import get_auth_resolution

    profile = Profile(name="test", server="https://api.example", auth_mode="pkce")
    resolver = MagicMock(side_effect=PkceError("login guidance"))
    monkeypatch.setattr("slcli.profiles.get_active_profile", lambda: profile)
    monkeypatch.setattr("slcli.pkce.resolve_pkce_token", resolver)

    with pytest.raises(click.ClickException, match="login guidance"):
        get_auth_resolution(emit_error=emit_error)

    resolver.assert_called_once_with(profile, emit_error=emit_error)


def test_get_auth_headers_uses_only_bearer_header() -> None:
    """Bearer requests must not also send the API-key header."""
    from slcli.utils import get_auth_headers

    headers = get_auth_headers("access-token", "bearer", "application/json")

    assert headers["Authorization"] == "Bearer access-token"
    assert "x-ni-api-key" not in headers
    assert headers["Content-Type"] == "application/json"


def test_get_headers_uses_resolved_bearer_scheme(monkeypatch: Any) -> None:
    """Shared request headers follow the resolved PKCE authentication scheme."""
    from slcli.utils import ResolvedAuth, get_headers

    monkeypatch.setattr(
        "slcli.utils.get_auth_resolution",
        lambda: ResolvedAuth("access-token", "profile:pkce:pkce", "bearer"),
    )

    headers = get_headers()

    assert headers == {
        "Authorization": "Bearer access-token",
        "User-Agent": "SystemLink-CLI/1.0 (cross-platform)",
    }


def test_get_base_url_uses_web_url_for_pkce_profile(monkeypatch: Any) -> None:
    """Commands use the Web Server root when the active profile uses PKCE."""
    from slcli.profiles import Profile
    from slcli.utils import get_base_url

    monkeypatch.setenv("SLCLI_API_URL", "https://api.example.com")
    monkeypatch.setenv("SLCLI_WEB_URL", "https://web.example.com")
    monkeypatch.delenv("SLCLI_API_KEY", raising=False)
    monkeypatch.delenv("SYSTEMLINK_API_KEY", raising=False)
    monkeypatch.setattr(
        "slcli.profiles.get_active_profile",
        lambda: Profile(name="pkce", server="https://api.example.com", auth_mode="pkce"),
    )

    assert get_base_url() == "https://web.example.com"


def test_api_key_override_keeps_api_url_for_pkce_profile(monkeypatch: Any) -> None:
    """An explicit API-key environment override retains API routing."""
    from slcli.profiles import Profile
    from slcli.utils import get_base_url

    monkeypatch.setenv("SLCLI_API_URL", "https://api.example.com")
    monkeypatch.setenv("SLCLI_WEB_URL", "https://web.example.com")
    monkeypatch.setenv("SLCLI_API_KEY", "api-key-override")
    monkeypatch.setattr(
        "slcli.profiles.get_active_profile",
        lambda: Profile(name="pkce", server="https://api.example.com", auth_mode="pkce"),
    )

    assert get_base_url() == "https://api.example.com"


def test_get_route_url_selects_web_url(monkeypatch: Any) -> None:
    """Web route URLs use the configured Web Server host."""
    from slcli.utils import get_route_url

    monkeypatch.setenv("SLCLI_API_URL", "https://api.example.com")
    monkeypatch.setenv("SLCLI_WEB_URL", "https://web.example.com/")

    assert get_route_url("/niauth/v1/auth", target="web") == (
        "https://web.example.com/niauth/v1/auth"
    )


def test_get_route_url_api_target_keeps_literal_api_url_for_pkce(monkeypatch: Any) -> None:
    """Explicit API routes remain on the API host when PKCE changes the command root."""
    from slcli.profiles import Profile
    from slcli.utils import get_route_url

    monkeypatch.setenv("SLCLI_API_URL", "https://api.example.com")
    monkeypatch.setenv("SLCLI_WEB_URL", "https://web.example.com")
    monkeypatch.setattr(
        "slcli.profiles.get_active_profile",
        lambda: Profile(name="pkce", server="https://api.example.com", auth_mode="pkce"),
    )

    assert get_route_url("/api/v1/resource", target="api") == (
        "https://api.example.com/api/v1/resource"
    )


def test_get_route_url_rejects_unknown_target() -> None:
    """Route construction should fail closed for an unsupported target."""
    from slcli.utils import get_route_url

    with pytest.raises(ValueError, match="Unsupported route target"):
        get_route_url("/niauth/v1/auth", target="other")  # type: ignore[arg-type]


def test_make_web_request_uses_explicit_bearer_credential(monkeypatch: Any) -> None:
    """Web requests can use a freshly issued bearer token before profile save."""
    from slcli.utils import make_web_request

    monkeypatch.setenv("SLCLI_WEB_URL", "https://web.example.com")
    response = MagicMock()
    response.raise_for_status = MagicMock()

    with patch("requests.get", return_value=response) as mock_get:
        result = make_web_request(
            "GET",
            "/niauth/v1/auth",
            credential="access-token",
            auth_scheme="bearer",
        )

    assert result is response
    call_kwargs = mock_get.call_args.kwargs
    assert mock_get.call_args.args[0] == "https://web.example.com/niauth/v1/auth"
    assert call_kwargs["headers"]["Authorization"] == "Bearer access-token"
    assert "x-ni-api-key" not in call_kwargs["headers"]


def test_base_url_resolution_strips_trailing_slash_from_env(monkeypatch: Any) -> None:
    """Base URL env overrides should normalize a trailing slash."""
    from slcli.utils import get_base_url_resolution

    monkeypatch.setenv("SLCLI_API_URL", "https://env.example.com/")

    resolved = get_base_url_resolution()

    assert resolved.value == "https://env.example.com"
    assert resolved.source == "env:SLCLI_API_URL"


def test_base_url_resolution_reports_profile_source(monkeypatch: Any, tmp_path: Path) -> None:
    """Base URL resolution should report the active profile when no env override exists."""
    from slcli.utils import get_base_url_resolution

    config_file = tmp_path / "config.json"
    config_data: Dict[str, Any] = {
        "current-profile": "dev",
        "profiles": {
            "dev": {
                "server": "https://dev.example.com/",
                "api-key": "profile-key",
            }
        },
    }
    config_file.write_text(json.dumps(config_data))
    config_file.chmod(0o600)
    monkeypatch.setattr(
        "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
    )

    resolved = get_base_url_resolution()

    assert resolved.value == "https://dev.example.com"
    assert resolved.source == "profile:dev"


def test_profile_source_encoding_disambiguates_colon_in_profile_name(monkeypatch: Any) -> None:
    """A colon in the profile name cannot be mistaken for a credential-store suffix."""
    from slcli.profiles import Profile
    from slcli.utils import describe_config_source, get_base_url_resolution

    monkeypatch.delenv("SLCLI_API_URL", raising=False)
    monkeypatch.delenv("SYSTEMLINK_API_URL", raising=False)
    monkeypatch.setattr(
        "slcli.profiles.get_active_profile",
        lambda: Profile(name="team:os", server="https://api.example.com"),
    )

    resolved = get_base_url_resolution()

    assert resolved.source == "profile:team%3Aos"
    assert describe_config_source(resolved.source) == "Profile 'team:os'"


def test_plaintext_warning_save_failure_does_not_block_auth(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Failure to persist the advisory warning does not prevent credential use."""
    from types import SimpleNamespace

    from slcli.profiles import Profile, ProfileConfig
    from slcli.utils import get_auth_resolution

    config = ProfileConfig()
    save = MagicMock(side_effect=RuntimeError("config is read-only"))
    monkeypatch.setattr(
        ProfileConfig, "get_config_path", classmethod(lambda cls: tmp_path / "config.json")
    )
    monkeypatch.setattr(ProfileConfig, "load", classmethod(lambda cls: config))
    monkeypatch.setattr(ProfileConfig, "save", save)
    monkeypatch.setattr(
        "slcli.profiles.get_active_profile",
        lambda: Profile(name="dev", server="https://api.example.com", api_key="plain-key"),
    )
    monkeypatch.setattr(
        "slcli.utils.sys", SimpleNamespace(stderr=SimpleNamespace(isatty=lambda: True))
    )

    resolved = get_auth_resolution()

    assert resolved.value == "plain-key"
    save.assert_called_once()


def test_api_key_resolution_raises_single_click_exception_when_missing(monkeypatch: Any) -> None:
    """Missing API keys should raise one ClickException with the full guidance message."""
    from slcli.utils import get_api_key_resolution

    monkeypatch.delenv("SLCLI_API_KEY", raising=False)
    monkeypatch.delenv("SYSTEMLINK_API_KEY", raising=False)
    monkeypatch.setattr("slcli.profiles.get_active_profile", lambda: None)

    with pytest.raises(click.ClickException, match="SLCLI_API_KEY environment variable"):
        get_api_key_resolution()


def test_ssl_verify_uses_managed_certificate(monkeypatch: Any, tmp_path: Path) -> None:
    """The request verification setting should use an accepted server certificate."""
    from cryptography.hazmat.primitives import hashes, serialization
    from slcli.ssl_trust import ServerCertificate, save_managed_certificate
    from slcli.utils import get_ssl_verify
    from .test_ssl_trust import _make_ca

    monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    config_file = tmp_path / "config.json"
    monkeypatch.setattr(
        "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
    )
    trusted_certificate = _make_ca()
    certificate = ServerCertificate(
        origin="https://example.com:443",
        pem=trusted_certificate.public_bytes(serialization.Encoding.PEM),
        fingerprint=trusted_certificate.fingerprint(hashes.SHA256()).hex().upper(),
        subject="subject",
        issuer="issuer",
        sans=[],
        not_before="before",
        not_after="after",
        self_signed=True,
        trust_type="ca",
    )
    path = save_managed_certificate(certificate)

    assert get_ssl_verify("https://example.com") == str(path)

    monkeypatch.setenv("SSL_CERT_FILE", "/path/to/system-bundle.pem")
    assert get_ssl_verify("https://example.com") == str(path)

    monkeypatch.setenv("SLCLI_SSL_VERIFY", "false")
    assert get_ssl_verify("https://example.com") is False


def test_ssl_verify_prefers_os_trust_over_ssl_cert_file(monkeypatch: Any) -> None:
    """The OS trust store should not be replaced by a single SSL_CERT_FILE root."""
    from slcli.utils import get_ssl_verify

    monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)
    monkeypatch.setenv("SSL_CERT_FILE", "/path/to/corporate-root.pem")
    monkeypatch.setattr("slcli.ssl_trust.OS_TRUST_INJECTED", True)

    assert get_ssl_verify("https://example.com") is True
