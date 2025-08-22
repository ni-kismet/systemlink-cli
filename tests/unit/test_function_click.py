"""Tests for function CLI commands (unified v2 API)."""

from __future__ import annotations

import json
from typing import Any, Dict, List

import click
import pytest
from click.testing import CliRunner

from slcli.function_click import register_function_commands
from .test_utils import patch_keyring


def make_cli():  # type: ignore[no-untyped-def]
    """Create a minimal CLI registering only function commands for isolated tests."""

    @click.group()
    def cli():  # type: ignore[no-untyped-def]
        pass

    register_function_commands(cli)
    return cli


@pytest.fixture
def runner():  # type: ignore[no-untyped-def]
    return CliRunner()


class _MockResponse:
    """Simple mock of requests.Response for JSON interactions."""

    def __init__(self, data: Dict[str, Any], status_code: int = 200):
        self._data = data
        self.status_code = status_code

    def json(self) -> Dict[str, Any]:  # noqa: D401
        return self._data

    def raise_for_status(self) -> None:  # noqa: D401
        if self.status_code >= 400:
            raise Exception("HTTP error")

    @property
    def text(self) -> str:  # noqa: D401
        return json.dumps(self._data) if self._data else ""


def test_function_list_functions_json(monkeypatch: Any, runner: CliRunner) -> None:
    """List functions across multiple pages and verify JSON aggregation."""
    patch_keyring(monkeypatch)

    # Two paginated responses
    paged_responses: List[Dict[str, Any]] = [
        {
            "functions": [
                {
                    "id": "func-1",
                    "name": "Adder",
                    "version": "1.0.0",
                    "workspaceId": "ws1",
                    "createdAt": "2024-01-01T00:00:00Z",
                    "interface": {"entrypoint": "adder"},
                }
            ],
            "continuationToken": "next-token",
        },
        {
            "functions": [
                {
                    "id": "func-2",
                    "name": "Multiplier",
                    "version": "1.0.0",
                    "workspaceId": "ws1",
                    "createdAt": "2024-01-02T00:00:00Z",
                    "interface": {"entrypoint": "mult"},
                }
            ]
        },
    ]

    def mock_make_api_request(
        method: str, url: str, payload=None, headers=None, handle_errors=True
    ):  # noqa: D401
        if "query-functions" in url:
            return _MockResponse(paged_responses.pop(0))
        if url.endswith("/niuser/v1/workspaces?take=1000"):
            return _MockResponse({"workspaces": [{"id": "ws1", "name": "Default"}]})
        raise AssertionError(f"Unexpected URL {url}")

    monkeypatch.setattr("slcli.function_click.make_api_request", mock_make_api_request)
    # Patch workspace map retrieval (indirect path inside utils)
    monkeypatch.setattr("slcli.function_click.get_workspace_map", lambda: {"ws1": "Default"})

    cli = make_cli()
    result = runner.invoke(cli, ["function", "manage", "list", "--format", "json"])

    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert len(data) == 2
    names = {d["name"] for d in data}
    assert {"Adder", "Multiplier"} == names


def test_function_get_function_json(monkeypatch: Any, runner: CliRunner) -> None:
    """Get a single function by ID and verify JSON output."""
    patch_keyring(monkeypatch)

    def mock_make_api_request(
        method: str, url: str, payload=None, headers=None, handle_errors=True
    ):  # noqa: D401
        if "/functions/func-1" in url and method == "GET":
            return _MockResponse(
                {
                    "id": "func-1",
                    "name": "Adder",
                    "workspaceId": "ws1",
                    "version": "1.0.0",
                    "interface": {"entrypoint": "adder"},
                }
            )
        if url.endswith("/niuser/v1/workspaces?take=1000"):
            return _MockResponse({"workspaces": [{"id": "ws1", "name": "Default"}]})
        raise AssertionError(f"Unexpected URL {url}")

    monkeypatch.setattr("slcli.function_click.make_api_request", mock_make_api_request)
    monkeypatch.setattr("slcli.function_click.get_workspace_map", lambda: {"ws1": "Default"})

    cli = make_cli()
    result = runner.invoke(
        cli,
        ["function", "manage", "get", "--id", "func-1", "--format", "json"],
    )
    assert result.exit_code == 0, result.output
    obj = json.loads(result.output)
    assert obj["id"] == "func-1"
    assert obj["interface"]["entrypoint"] == "adder"


def test_function_execute_sync_json(monkeypatch: Any, runner: CliRunner) -> None:
    """Execute a function synchronously and verify result output."""
    patch_keyring(monkeypatch)

    def mock_make_api_request(
        method: str, url: str, payload=None, headers=None, handle_errors=True
    ):  # noqa: D401
        if url.endswith("/functions/func-1/execute") and method == "POST":
            # Ensure async flag False for sync command and body wrapping
            assert isinstance(payload, dict) and payload.get("async") is False
            params = payload.get("parameters", {})
            # Legacy simple parameters should be wrapped inside body only
            assert params == {"body": {"a": 5, "b": 10}}
            return _MockResponse(
                {
                    "executionId": "exec-123",
                    "executionTime": 42,
                    "cachedResult": False,
                    "result": {"sum": 15},
                }
            )
        if url.endswith("/niuser/v1/workspaces?take=1000"):
            return _MockResponse({"workspaces": []})
        raise AssertionError(f"Unexpected URL {url}")

    monkeypatch.setattr("slcli.function_click.make_api_request", mock_make_api_request)
    monkeypatch.setattr("slcli.function_click.get_workspace_map", lambda: {})

    cli = make_cli()
    result = runner.invoke(
        cli,
        [
            "function",
            "execute",
            "sync",
            "--function-id",
            "func-1",
            "--parameters",
            '{"a": 5, "b": 10}',
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    data = json.loads(result.output)
    assert data["result"]["sum"] == 15


def test_function_execute_sync_defaults(monkeypatch: Any, runner: CliRunner) -> None:
    """Execute sync with no parameters should use embedded defaults {method:GET,path:/}."""
    patch_keyring(monkeypatch)

    def mock_make_api_request(
        method: str, url: str, payload=None, headers=None, handle_errors=True
    ):  # noqa: D401
        if url.endswith("/functions/func-1/execute") and method == "POST":
            assert isinstance(payload, dict)
            params = payload.get("parameters", {})
            assert params == {"method": "GET", "path": "/"}
            return _MockResponse(
                {
                    "executionId": "exec-000",
                    "executionTime": 1,
                    "cachedResult": False,
                    "result": {"ok": True},
                }
            )
        if url.endswith("/niuser/v1/workspaces?take=1000"):
            return _MockResponse({"workspaces": []})
        raise AssertionError(f"Unexpected URL {url}")

    monkeypatch.setattr("slcli.function_click.make_api_request", mock_make_api_request)
    monkeypatch.setattr("slcli.function_click.get_workspace_map", lambda: {})

    cli = make_cli()
    result = runner.invoke(
        cli,
        [
            "function",
            "execute",
            "sync",
            "--function-id",
            "func-1",
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 0, result.output
    out = json.loads(result.output)
    assert out["result"]["ok"] is True


## Async execution command removed; corresponding test deleted.


def test_function_get_function_table_interface_summary(monkeypatch: Any, runner: CliRunner) -> None:
    """Table output should include concise interface summary when endpoints exist."""
    patch_keyring(monkeypatch)

    def mock_make_api_request(
        method: str, url: str, payload=None, headers=None, handle_errors=True
    ):  # noqa: D401
        if "/functions/func-1" in url and method == "GET":
            return _MockResponse(
                {
                    "id": "func-1",
                    "name": "py-main",
                    "workspaceId": "ws1",
                    "version": "1.0.0",
                    "runtime": "wasm",
                    "interface": {
                        "endpoints": [
                            {
                                "path": "/",
                                "methods": ["GET"],
                                "description": "Return a random integer",
                            },
                            {
                                "path": "/stats",
                                "methods": ["POST"],
                                "description": "Compute basic statistics",
                            },
                        ],
                        "defaultPath": "/",
                    },
                }
            )
        if url.endswith("/niuser/v1/workspaces?take=1000"):
            return _MockResponse({"workspaces": [{"id": "ws1", "name": "Default"}]})
        raise AssertionError(f"Unexpected URL {url}")

    monkeypatch.setattr("slcli.function_click.make_api_request", mock_make_api_request)
    monkeypatch.setattr("slcli.function_click.get_workspace_map", lambda: {"ws1": "Default"})

    cli = make_cli()
    result = runner.invoke(cli, ["function", "manage", "get", "--id", "func-1"])  # table is default

    assert result.exit_code == 0, result.output
    output = result.output
    assert "Interface:" in output
    assert "Default Path:  /" in output
    assert "- GET / - Return a random integer" in output
    assert "- POST /stats - Compute basic statistics" in output
