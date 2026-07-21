"""Tests for system trust store injection utilities."""

from __future__ import annotations

import importlib
import sys
import types
from typing import Any, List

import pytest


def _make_dummy_truststore(inject_side_effect: Any = None) -> Any:
    mod = types.ModuleType("truststore")
    called: List[bool] = []

    def inject_into_requests() -> None:  # type: ignore
        if inject_side_effect:
            raise inject_side_effect
        called.append(True)

    mod.inject_into_requests = inject_into_requests  # type: ignore[attr-defined]
    mod._called = called  # type: ignore[attr-defined]
    return mod


def test_injection_success(monkeypatch: Any) -> None:
    dummy = _make_dummy_truststore()
    monkeypatch.setitem(sys.modules, "truststore", dummy)
    from slcli import ssl_trust

    importlib.reload(ssl_trust)
    ssl_trust.inject_os_trust()
    assert dummy._called, "truststore.inject_into_requests should have been called"


def test_injection_disabled(monkeypatch: Any) -> None:
    dummy = _make_dummy_truststore()
    monkeypatch.setitem(sys.modules, "truststore", dummy)
    monkeypatch.setenv("SLCLI_DISABLE_OS_TRUST", "1")
    from slcli import ssl_trust

    importlib.reload(ssl_trust)
    ssl_trust.inject_os_trust()
    assert not dummy._called, "Injection should be skipped when disabled"


def test_injection_force_failure(monkeypatch: Any) -> None:
    dummy = _make_dummy_truststore(inject_side_effect=RuntimeError("boom"))
    monkeypatch.setitem(sys.modules, "truststore", dummy)
    monkeypatch.setenv("SLCLI_FORCE_OS_TRUST", "1")
    from slcli import ssl_trust

    importlib.reload(ssl_trust)
    with pytest.raises(RuntimeError):
        ssl_trust.inject_os_trust()


def test_server_origin_normalization() -> None:
    """Managed trust should normalize default ports and reject non-HTTPS URLs."""
    from slcli.ssl_trust import get_ssl_server_origin

    assert get_ssl_server_origin("https://Example.com/path") == "https://example.com:443"
    assert get_ssl_server_origin("https://example.com:8443") == "https://example.com:8443"
    with pytest.raises(ValueError, match="HTTPS"):
        get_ssl_server_origin("http://example.com")


def test_managed_certificate_persistence_is_origin_scoped(monkeypatch: Any, tmp_path: Any) -> None:
    """Managed certificates should persist securely and only match their origin."""
    from slcli.ssl_trust import (
        ServerCertificate,
        get_managed_trust_path,
        get_managed_trust_records,
        remove_managed_trust,
        save_managed_certificate,
    )

    config_file = tmp_path / "config.json"
    monkeypatch.setattr(
        "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
    )
    certificate = ServerCertificate(
        origin="https://example.com:443",
        pem=b"-----BEGIN CERTIFICATE-----\nfixture\n-----END CERTIFICATE-----\n",
        fingerprint="A" * 64,
        subject="commonName=example.com",
        issuer="commonName=example.com",
        sans=["example.com"],
        not_before="2026-01-01T00:00:00+00:00",
        not_after="2027-01-01T00:00:00+00:00",
        self_signed=True,
    )

    path = save_managed_certificate(certificate)
    assert path.read_bytes() == certificate.pem
    assert path.stat().st_mode & 0o777 == 0o600
    assert get_managed_trust_path("https://example.com/path") == path
    assert get_managed_trust_path("https://other.example.com") is None
    assert get_managed_trust_records()[0]["fingerprint"] == "A" * 64
    assert remove_managed_trust("https://example.com") is True
    assert get_managed_trust_path("https://example.com") is None
