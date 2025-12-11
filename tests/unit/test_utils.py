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
