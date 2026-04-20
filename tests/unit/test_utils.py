"""Test utilities for slcli unit tests."""

import json
from typing import Any


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
