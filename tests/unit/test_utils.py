"""Test utilities for slcli unit tests."""

import json
from pathlib import Path
from typing import Any, Dict

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

    monkeypatch.setenv("SLCLI_SSL_VERIFY", "false")
    assert get_ssl_verify("https://example.com") is False
