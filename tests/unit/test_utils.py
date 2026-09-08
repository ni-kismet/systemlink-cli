"""Test utilities for slcli unit tests."""

import json
from pathlib import Path
from typing import Any, Dict
from unittest.mock import MagicMock, patch

import click
import pytest


def patch_keyring(monkeypatch: Any, platform: str = "SLE") -> None:
    """Patch keyring to return a mock configuration.

    Args:
        monkeypatch: pytest monkeypatch fixture
        platform: Platform type - "SLE" (default) or "SLS"
    """
    import keyring

    config = {
        "api_url": "http://localhost:8000",
        "api_key": "dummy-api-key",
        "platform": platform,
    }

    def get_password(service: str, key: str) -> str:
        if key == "SYSTEMLINK_CONFIG":
            return json.dumps(config)
        if key == "SYSTEMLINK_API_URL":
            return "http://localhost:8000"
        return "dummy-api-key"

    monkeypatch.setattr(keyring, "get_password", get_password)
    monkeypatch.setattr(keyring, "set_password", lambda *a, **kw: None)
    monkeypatch.setattr(keyring, "delete_password", lambda *a, **kw: None)


def test_escape_filter_value_escapes_backslashes_before_quotes() -> None:
    """Filter values cannot terminate a quoted literal after a backslash."""
    from slcli.utils import escape_filter_value

    assert escape_filter_value('fixture\\" or AssetType = "SYSTEM') == (
        'fixture\\\\\\" or AssetType = \\"SYSTEM'
    )


def test_get_web_url_ignores_keyring_backend_errors_when_api_url_is_set(
    monkeypatch: Any,
) -> None:
    """get_web_url should derive from the API URL when keyring is unavailable."""
    import keyring
    from keyring.errors import NoKeyringError

    from slcli.utils import get_web_url

    monkeypatch.setenv("SYSTEMLINK_API_URL", "https://dev-api.lifecyclesolutions.ni.com")
    monkeypatch.delenv("SYSTEMLINK_WEB_URL", raising=False)
    monkeypatch.setattr("slcli.profiles.get_active_profile", lambda: None)
    monkeypatch.setattr("slcli.utils._get_keyring_config", lambda: {})

    def raise_no_backend(*args: Any, **kwargs: Any) -> str:
        raise NoKeyringError("No backend available")

    monkeypatch.setattr(keyring, "get_password", raise_no_backend)

    assert get_web_url() == "https://dev-api.lifecyclesolutions.ni.com"


def test_api_key_resolution_prefers_slcli_env_alias(monkeypatch: Any, tmp_path: Path) -> None:
    """SLCLI_API_KEY should win over legacy env vars and profile values."""
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


def test_pkce_auth_resolution_returns_bearer_scheme(monkeypatch: Any) -> None:
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
        ),
    )
    monkeypatch.setattr("slcli.pkce.get_pkce_access_token", lambda _profile: "access-token")

    resolved = get_auth_resolution()

    assert resolved.value == "access-token"
    assert resolved.source == "profile:pkce:pkce"
    assert resolved.scheme == "bearer"


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


def test_api_key_resolution_raises_single_click_exception_when_missing(monkeypatch: Any) -> None:
    """Missing API keys should raise one ClickException with the full guidance message."""
    from slcli.utils import get_api_key_resolution

    monkeypatch.delenv("SLCLI_API_KEY", raising=False)
    monkeypatch.delenv("SYSTEMLINK_API_KEY", raising=False)
    monkeypatch.setattr("slcli.utils._get_keyring_config", lambda: {})
    monkeypatch.setattr("slcli.utils.keyring.get_password", lambda *_args, **_kwargs: None)
    monkeypatch.setattr("slcli.profiles.get_active_profile", lambda: None)

    with pytest.raises(click.ClickException, match="SLCLI_API_KEY environment variable"):
        get_api_key_resolution()


def test_ssl_verify_uses_managed_certificate(monkeypatch: Any, tmp_path: Path) -> None:
    """The request verification setting should use an accepted server certificate."""
    from slcli.ssl_trust import ServerCertificate, save_managed_certificate
    from slcli.utils import get_ssl_verify

    monkeypatch.delenv("REQUESTS_CA_BUNDLE", raising=False)
    monkeypatch.delenv("SSL_CERT_FILE", raising=False)
    config_file = tmp_path / "config.json"
    monkeypatch.setattr(
        "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
    )
    certificate = ServerCertificate(
        origin="https://example.com:443",
        pem=b"pem",
        fingerprint="B" * 64,
        subject="subject",
        issuer="issuer",
        sans=[],
        not_before="before",
        not_after="after",
        self_signed=False,
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
