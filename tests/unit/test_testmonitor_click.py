"""Unit tests for test monitor CLI commands."""

import json
from typing import Any, Dict, List, Optional

import click
import pytest
from click.testing import CliRunner

from slcli.testmonitor_click import register_testmonitor_commands


def patch_keyring(monkeypatch: Any) -> None:
    """Patch keyring to return test values."""
    monkeypatch.setattr(
        "slcli.utils.keyring.get_password",
        lambda service, key: "test-key" if key == "SYSTEMLINK_API_KEY" else "https://test.com",
    )


def make_cli() -> click.Group:
    """Create CLI instance with test monitor commands for testing."""

    @click.group()
    def test_cli() -> None:
        pass

    register_testmonitor_commands(test_cli)
    return test_cli


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


class MockResponse:
    """Mock response class for requests."""

    def __init__(self, json_data: Any, status_code: int = 200) -> None:
        """Initialize a mock response.

        Args:
            json_data: JSON payload to return from json().
            status_code: HTTP status code to simulate.
        """
        self._json_data = json_data
        self.status_code = status_code

    def json(self) -> Any:
        return self._json_data

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise Exception(f"HTTP error {self.status_code}")


# --- Product list tests ---


def test_list_products_filters(monkeypatch: Any, runner: CliRunner) -> None:
    """Test product list filter building and substitutions."""
    patch_keyring(monkeypatch)

    captured_payloads: List[Dict[str, Any]] = []

    def mock_request(
        method: str,
        url: str,
        payload: Optional[Dict[str, Any]] = None,
        **_: Any,
    ) -> Any:
        if payload:
            captured_payloads.append(payload)
        return MockResponse(
            {
                "products": [
                    {
                        "id": "prod-1",
                        "name": "cRIO-9030",
                        "partNumber": "156502A-11L",
                        "family": "cRIO",
                        "updatedAt": "2024-01-10T12:30:00.000Z",
                        "workspace": "ws-1",
                    }
                ]
            }
        )

    monkeypatch.setattr("slcli.testmonitor_click.make_api_request", mock_request)
    monkeypatch.setattr("slcli.testmonitor_click.get_workspace_map", lambda: {"ws-1": "Dev"})

    cli = make_cli()
    result = runner.invoke(
        cli,
        [
            "testmonitor",
            "product",
            "list",
            "--name",
            "cRIO",
            "--workspace",
            "Dev",
            "--filter",
            "family == @0",
            "--substitution",
            "cRIO",
        ],
    )

    assert result.exit_code == 0
    assert "cRIO-9030" in result.output
    assert captured_payloads
    payload = captured_payloads[0]
    assert "name.Contains(@0)" in payload.get("filter", "")
    assert "family == @2" in payload.get("filter", "")
    assert "workspace == @1" in payload.get("filter", "")
    assert payload.get("substitutions") == ["cRIO", "ws-1", "cRIO"]


def test_list_products_json_output(monkeypatch: Any, runner: CliRunner) -> None:
    """Test product list JSON output."""
    patch_keyring(monkeypatch)

    def mock_request(
        method: str,
        url: str,
        payload: Optional[Dict[str, Any]] = None,
        **_: Any,
    ) -> Any:
        return MockResponse(
            {
                "products": [
                    {
                        "id": "prod-1",
                        "name": "cRIO-9030",
                        "partNumber": "156502A-11L",
                        "family": "cRIO",
                        "workspace": "ws-1",
                    }
                ]
            }
        )

    monkeypatch.setattr("slcli.testmonitor_click.make_api_request", mock_request)
    monkeypatch.setattr("slcli.testmonitor_click.get_workspace_map", lambda: {"ws-1": "Dev"})

    cli = make_cli()
    result = runner.invoke(cli, ["testmonitor", "product", "list", "--format", "json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 1
    assert data[0]["id"] == "prod-1"


# --- Result list tests ---


def test_list_results_filters(monkeypatch: Any, runner: CliRunner) -> None:
    """Test test result list filter building and substitutions."""
    patch_keyring(monkeypatch)

    captured_payloads: List[Dict[str, Any]] = []

    def mock_request(
        method: str,
        url: str,
        payload: Optional[Dict[str, Any]] = None,
        **_: Any,
    ) -> Any:
        if payload:
            captured_payloads.append(payload)
        return MockResponse(
            {
                "results": [
                    {
                        "id": "res-1",
                        "programName": "Calibration",
                        "partNumber": "cRIO-9030",
                        "serialNumber": "abc-123",
                        "startedAt": "2024-01-12T10:00:00.000Z",
                        "totalTimeInSeconds": 12.3,
                        "status": {"statusType": "PASSED"},
                    }
                ]
            }
        )

    monkeypatch.setattr("slcli.testmonitor_click.make_api_request", mock_request)
    monkeypatch.setattr("slcli.testmonitor_click.get_workspace_map", lambda: {"ws-1": "Dev"})

    cli = make_cli()
    result = runner.invoke(
        cli,
        [
            "testmonitor",
            "result",
            "list",
            "--status",
            "passed",
            "--program-name",
            "Calibration",
            "--workspace",
            "Dev",
        ],
    )

    assert result.exit_code == 0
    assert "Calibration" in result.output
    assert captured_payloads
    payload = captured_payloads[0]
    filter_expr = payload.get("filter", "")
    assert "status.statusType == @0" in filter_expr
    assert "programName.Contains(@1)" in filter_expr
    assert "workspace == @2" in filter_expr
    assert payload.get("substitutions") == ["PASSED", "Calibration", "ws-1"]


def test_list_results_json_output(monkeypatch: Any, runner: CliRunner) -> None:
    """Test test result list JSON output."""
    patch_keyring(monkeypatch)

    def mock_request(
        method: str,
        url: str,
        payload: Optional[Dict[str, Any]] = None,
        **_: Any,
    ) -> Any:
        return MockResponse(
            {
                "results": [
                    {
                        "id": "res-1",
                        "programName": "Calibration",
                        "status": {"statusType": "PASSED"},
                    }
                ]
            }
        )

    monkeypatch.setattr("slcli.testmonitor_click.make_api_request", mock_request)
    monkeypatch.setattr("slcli.testmonitor_click.get_workspace_map", lambda: {"ws-1": "Dev"})

    cli = make_cli()
    result = runner.invoke(cli, ["testmonitor", "result", "list", "--format", "json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 1
    assert data[0]["id"] == "res-1"


def test_product_list_take_parameter(monkeypatch: Any, runner: CliRunner) -> None:
    """Test that take parameter is correctly passed to API request."""
    patch_keyring(monkeypatch)

    captured_payloads: List[Dict[str, Any]] = []

    def mock_request(
        method: str,
        url: str,
        payload: Optional[Dict[str, Any]] = None,
        **_: Any,
    ) -> Any:
        if payload:
            captured_payloads.append(payload)
        return MockResponse(
            {"products": [{"id": f"prod-{i}", "name": f"Product-{i}"} for i in range(50)]}
        )

    monkeypatch.setattr("slcli.testmonitor_click.make_api_request", mock_request)
    monkeypatch.setattr("slcli.testmonitor_click.get_workspace_map", lambda: {})

    cli = make_cli()
    result = runner.invoke(cli, ["testmonitor", "product", "list", "--take", "10"])

    assert result.exit_code == 0
    assert captured_payloads
    assert captured_payloads[0]["take"] == 10


def test_result_list_take_parameter(monkeypatch: Any, runner: CliRunner) -> None:
    """Test that take parameter is correctly passed to API request for results."""
    patch_keyring(monkeypatch)

    captured_payloads: List[Dict[str, Any]] = []

    def mock_request(
        method: str,
        url: str,
        payload: Optional[Dict[str, Any]] = None,
        **_: Any,
    ) -> Any:
        if payload:
            captured_payloads.append(payload)
        return MockResponse(
            {"results": [{"id": f"res-{i}", "programName": f"Program-{i}"} for i in range(50)]}
        )

    monkeypatch.setattr("slcli.testmonitor_click.make_api_request", mock_request)
    monkeypatch.setattr("slcli.testmonitor_click.get_workspace_map", lambda: {})

    cli = make_cli()
    result = runner.invoke(cli, ["testmonitor", "result", "list", "--take", "15"])

    assert result.exit_code == 0
    assert captured_payloads
    assert captured_payloads[0]["take"] == 15
