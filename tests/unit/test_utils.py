"""Test utilities for slcli unit tests."""


def patch_keyring(monkeypatch):
    import keyring

    monkeypatch.setattr(keyring, "get_password", lambda *a, **kw: "mocked-api-key")
    monkeypatch.setattr(keyring, "set_password", lambda *a, **kw: None)
    monkeypatch.setattr(keyring, "delete_password", lambda *a, **kw: None)
