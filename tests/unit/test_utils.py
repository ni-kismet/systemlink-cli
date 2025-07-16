"""Test utilities for slcli unit tests."""


def patch_keyring(monkeypatch):
    import keyring

    def get_password(service, key):
        if key == "SYSTEMLINK_API_URL":
            return "http://localhost:8000"
        return "dummy-api-key"

    monkeypatch.setattr(keyring, "get_password", get_password)
    monkeypatch.setattr(keyring, "set_password", lambda *a, **kw: None)
    monkeypatch.setattr(keyring, "delete_password", lambda *a, **kw: None)
