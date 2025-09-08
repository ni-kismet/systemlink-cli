"""Tests for system trust store injection utilities."""

from __future__ import annotations

import importlib
import sys
import types
from typing import List

import pytest


def _make_dummy_truststore(inject_side_effect=None):
    mod = types.ModuleType("truststore")
    called: List[bool] = []

    def inject_into_requests():  # type: ignore
        if inject_side_effect:
            raise inject_side_effect
        called.append(True)

    mod.inject_into_requests = inject_into_requests  # type: ignore[attr-defined]
    mod._called = called  # type: ignore[attr-defined]
    return mod


def test_injection_success(monkeypatch):
    dummy = _make_dummy_truststore()
    monkeypatch.setitem(sys.modules, "truststore", dummy)
    from slcli import ssl_trust

    importlib.reload(ssl_trust)
    ssl_trust.inject_os_trust()
    assert dummy._called, "truststore.inject_into_requests should have been called"


def test_injection_disabled(monkeypatch):
    dummy = _make_dummy_truststore()
    monkeypatch.setitem(sys.modules, "truststore", dummy)
    monkeypatch.setenv("SLCLI_DISABLE_OS_TRUST", "1")
    from slcli import ssl_trust

    importlib.reload(ssl_trust)
    ssl_trust.inject_os_trust()
    assert not dummy._called, "Injection should be skipped when disabled"


def test_injection_force_failure(monkeypatch):
    dummy = _make_dummy_truststore(inject_side_effect=RuntimeError("boom"))
    monkeypatch.setitem(sys.modules, "truststore", dummy)
    monkeypatch.setenv("SLCLI_FORCE_OS_TRUST", "1")
    from slcli import ssl_trust

    importlib.reload(ssl_trust)
    with pytest.raises(RuntimeError):
        ssl_trust.inject_os_trust()
