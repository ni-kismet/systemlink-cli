"""Tests for E2E configuration loading behavior."""

import importlib
from typing import Any, Dict

e2e_conftest: Any = importlib.import_module("tests.e2e.conftest")


def _load_fixture_config() -> Dict[str, Any]:
    """Call the underlying E2E config fixture function."""
    fixture_function = getattr(e2e_conftest.e2e_config, "__wrapped__")
    return fixture_function()


def test_e2e_config_env_overrides_multi_platform_values(monkeypatch: Any) -> None:
    """Environment overrides apply when the config contains platform sections."""
    monkeypatch.setattr(
        e2e_conftest,
        "_load_config_file",
        lambda: {"sle": {"base_url": "https://example.invalid"}, "timeout": 30, "cleanup": True},
    )
    monkeypatch.setenv("SLCLI_E2E_TIMEOUT", "120")
    monkeypatch.setenv("SLCLI_E2E_CLEANUP", "false")

    config = _load_fixture_config()

    assert config["timeout"] == 120
    assert config["cleanup"] is False
