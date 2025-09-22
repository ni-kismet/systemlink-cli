"""Test utilities for slcli unit tests."""

from typing import Any


def patch_keyring(monkeypatch: Any) -> None:
    import keyring

    def get_password(service: str, key: str) -> str:
        if key == "SYSTEMLINK_API_URL":
            return "http://localhost:8000"
        return "dummy-api-key"

    monkeypatch.setattr(keyring, "get_password", get_password)
    monkeypatch.setattr(keyring, "set_password", lambda *a, **kw: None)
    monkeypatch.setattr(keyring, "delete_password", lambda *a, **kw: None)
