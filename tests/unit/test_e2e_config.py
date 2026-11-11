"""Tests for E2E configuration loading behavior."""

import importlib
import json
import subprocess
from typing import Any, Dict, List

import pytest

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


def test_e2e_config_uses_flat_file_workspace(monkeypatch: Any) -> None:
    """A workspace specified in the local config is not replaced by the default."""
    monkeypatch.delenv("SLCLI_E2E_BASE_URL", raising=False)
    monkeypatch.delenv("SLCLI_E2E_API_KEY", raising=False)
    monkeypatch.delenv("SLCLI_E2E_WORKSPACE", raising=False)
    monkeypatch.setattr(
        e2e_conftest,
        "_load_config_file",
        lambda: {
            "base_url": "https://example.invalid",
            "api_key": "test",
            "workspace": "SLCLI-Test",
        },
    )

    assert _load_fixture_config()["workspace"] == "SLCLI-Test"


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


def test_explicit_platform_requires_e2e_credentials() -> None:
    """An explicitly selected platform cannot use an unrelated active profile."""
    fixture_function = getattr(e2e_conftest.cli_runner, "__wrapped__")
    with pytest.raises(pytest.fail.Exception, match="SLS E2E base URL and API key"):
        fixture_function({}, "sls")


@pytest.mark.parametrize("names", [[], ["Other"], ["SLCLI-Test"]])
def test_configured_workspace_does_not_fall_back(monkeypatch: Any, names: List[str]) -> None:
    """A missing test workspace never redirects mutations to another workspace."""
    result = subprocess.CompletedProcess(
        args=[], returncode=0, stdout=json.dumps([{"name": n} for n in names]), stderr=""
    )
    monkeypatch.setattr(e2e_conftest, "_make_cli_runner", lambda *args: lambda _: result)
    fixture_function = getattr(e2e_conftest.configured_workspace, "__wrapped__")
    config = {"sls": {"workspace": "SLCLI-Test"}}

    if names == ["SLCLI-Test"]:
        assert fixture_function(config, "sls") == "SLCLI-Test"
    else:
        with pytest.raises(pytest.fail.Exception):
            fixture_function(config, "sls")


def test_sle_workspace_fallback_is_preserved(monkeypatch: Any) -> None:
    """SLE tests continue to use an accessible workspace if the default is missing."""
    result = subprocess.CompletedProcess(
        args=[], returncode=0, stdout='[{"name":"Other"}]', stderr=""
    )
    monkeypatch.setattr(e2e_conftest, "_make_cli_runner", lambda *args: lambda _: result)
    fixture_function = getattr(e2e_conftest.configured_workspace, "__wrapped__")

    assert fixture_function({"sle": {"workspace": "Default"}}, "sle") == "Other"
