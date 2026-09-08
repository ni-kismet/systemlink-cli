"""Tests for E2E configuration loading behavior."""

import importlib
import subprocess
from typing import Any, Dict, List

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


def test_cli_runner_retries_rate_limited_command(monkeypatch: Any) -> None:
    """The E2E runner retries transient HTTP 429 responses."""
    rate_limited = subprocess.CompletedProcess(
        args=[], returncode=1, stdout="", stderr="429 Client Error: Too Many Requests"
    )
    success = subprocess.CompletedProcess(args=[], returncode=0, stdout="[]", stderr="")
    run_results = iter([rate_limited, success])
    sleeps: List[int] = []
    monkeypatch.setattr(e2e_conftest.subprocess, "run", lambda *args, **kwargs: next(run_results))
    monkeypatch.setattr(e2e_conftest.time, "sleep", sleeps.append)

    result = e2e_conftest._make_cli_runner({})(["user", "list"])

    assert result is success
    assert sleeps == [1]
