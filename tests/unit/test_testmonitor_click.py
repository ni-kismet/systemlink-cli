"""Unit tests for test monitor CLI commands."""

import json
from typing import Any, Dict, List, Optional
from unittest.mock import patch

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


def test_list_products_empty_results(monkeypatch: Any, runner: CliRunner) -> None:
    """Test product list with no results."""
    patch_keyring(monkeypatch)

    def mock_request(
        method: str,
        url: str,
        payload: Optional[Dict[str, Any]] = None,
        **_: Any,
    ) -> Any:
        return MockResponse({"products": []})

    monkeypatch.setattr("slcli.testmonitor_click.make_api_request", mock_request)
    monkeypatch.setattr("slcli.testmonitor_click.get_workspace_map", lambda: {})

    cli = make_cli()
    result = runner.invoke(cli, ["testmonitor", "product", "list"])

    assert result.exit_code == 0
    assert "No products found" in result.output


def test_list_results_empty_results(monkeypatch: Any, runner: CliRunner) -> None:
    """Test test result list with no results."""
    patch_keyring(monkeypatch)

    def mock_request(
        method: str,
        url: str,
        payload: Optional[Dict[str, Any]] = None,
        **_: Any,
    ) -> Any:
        return MockResponse({"results": []})

    monkeypatch.setattr("slcli.testmonitor_click.make_api_request", mock_request)
    monkeypatch.setattr("slcli.testmonitor_click.get_workspace_map", lambda: {})

    cli = make_cli()
    result = runner.invoke(cli, ["testmonitor", "result", "list"])

    assert result.exit_code == 0
    assert "No test results found" in result.output


def test_list_products_order_by(monkeypatch: Any, runner: CliRunner) -> None:
    """Test product list with order-by parameter."""
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
                        "name": "Product-A",
                        "partNumber": "123",
                        "family": "Test",
                    }
                ]
            }
        )

    monkeypatch.setattr("slcli.testmonitor_click.make_api_request", mock_request)
    monkeypatch.setattr("slcli.testmonitor_click.get_workspace_map", lambda: {})

    cli = make_cli()
    result = runner.invoke(
        cli, ["testmonitor", "product", "list", "--order-by", "NAME", "--format", "json"]
    )

    assert result.exit_code == 0
    assert captured_payloads
    assert captured_payloads[0].get("orderBy") == "NAME"


def test_list_results_order_by(monkeypatch: Any, runner: CliRunner) -> None:
    """Test test result list with order-by parameter."""
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
                        "programName": "Test",
                        "status": {"statusType": "PASSED"},
                    }
                ]
            }
        )

    monkeypatch.setattr("slcli.testmonitor_click.make_api_request", mock_request)
    monkeypatch.setattr("slcli.testmonitor_click.get_workspace_map", lambda: {})

    cli = make_cli()
    result = runner.invoke(
        cli,
        [
            "testmonitor",
            "result",
            "list",
            "--order-by",
            "STARTED_AT",
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0
    assert captured_payloads
    assert captured_payloads[0].get("orderBy") == "STARTED_AT"


def test_list_products_descending_ascending(monkeypatch: Any, runner: CliRunner) -> None:
    """Test product list with descending/ascending parameters."""
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
        return MockResponse({"products": []})

    monkeypatch.setattr("slcli.testmonitor_click.make_api_request", mock_request)
    monkeypatch.setattr("slcli.testmonitor_click.get_workspace_map", lambda: {})

    cli = make_cli()

    # Test ascending
    result = runner.invoke(
        cli, ["testmonitor", "product", "list", "--ascending", "--format", "json"]
    )
    assert result.exit_code == 0
    assert captured_payloads[-1].get("descending") is False

    # Test descending (default)
    result = runner.invoke(cli, ["testmonitor", "product", "list", "--format", "json"])
    assert result.exit_code == 0
    assert captured_payloads[-1].get("descending") is True


def test_list_results_descending_ascending(monkeypatch: Any, runner: CliRunner) -> None:
    """Test test result list with descending/ascending parameters."""
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
        return MockResponse({"results": []})

    monkeypatch.setattr("slcli.testmonitor_click.make_api_request", mock_request)
    monkeypatch.setattr("slcli.testmonitor_click.get_workspace_map", lambda: {})

    cli = make_cli()

    # Test ascending
    result = runner.invoke(
        cli, ["testmonitor", "result", "list", "--ascending", "--format", "json"]
    )
    assert result.exit_code == 0
    assert captured_payloads[-1].get("descending") is False

    # Test descending (default)
    result = runner.invoke(cli, ["testmonitor", "result", "list", "--format", "json"])
    assert result.exit_code == 0
    assert captured_payloads[-1].get("descending") is True


def test_list_results_product_filter_with_substitution(monkeypatch: Any, runner: CliRunner) -> None:
    """Test test result list with product-filter and product-substitution."""
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
                        "programName": "Test",
                        "status": {"statusType": "PASSED"},
                    }
                ]
            }
        )

    monkeypatch.setattr("slcli.testmonitor_click.make_api_request", mock_request)
    monkeypatch.setattr("slcli.testmonitor_click.get_workspace_map", lambda: {})

    cli = make_cli()
    result = runner.invoke(
        cli,
        [
            "testmonitor",
            "result",
            "list",
            "--product-filter",
            "partNumber == @0",
            "--product-substitution",
            "cRIO-9030",
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0
    assert captured_payloads
    payload = captured_payloads[0]
    assert "productFilter" in payload
    assert payload["productFilter"] == "partNumber == @0"
    assert payload.get("productSubstitutions") == ["cRIO-9030"]


def test_list_products_error_handling(monkeypatch: Any, runner: CliRunner) -> None:
    """Test product list error handling."""
    patch_keyring(monkeypatch)

    def mock_request(
        method: str,
        url: str,
        payload: Optional[Dict[str, Any]] = None,
        **_: Any,
    ) -> Any:
        raise Exception("API Error")

    monkeypatch.setattr("slcli.testmonitor_click.make_api_request", mock_request)
    monkeypatch.setattr("slcli.testmonitor_click.get_workspace_map", lambda: {})

    cli = make_cli()
    result = runner.invoke(cli, ["testmonitor", "product", "list"])

    assert result.exit_code != 0
    assert "API Error" in result.output or "Error" in result.output


def test_list_results_error_handling(monkeypatch: Any, runner: CliRunner) -> None:
    """Test test result list error handling."""
    patch_keyring(monkeypatch)

    def mock_request(
        method: str,
        url: str,
        payload: Optional[Dict[str, Any]] = None,
        **_: Any,
    ) -> Any:
        raise Exception("API Error")

    monkeypatch.setattr("slcli.testmonitor_click.make_api_request", mock_request)
    monkeypatch.setattr("slcli.testmonitor_click.get_workspace_map", lambda: {})

    cli = make_cli()
    result = runner.invoke(cli, ["testmonitor", "result", "list"])

    assert result.exit_code != 0
    assert "API Error" in result.output or "Error" in result.output


def test_get_product_json(monkeypatch: Any, runner: CliRunner) -> None:
    """Test retrieving product details in JSON format."""
    patch_keyring(monkeypatch)

    product_data = {
        "id": "prod-123",
        "name": "Test Product",
        "partNumber": "TP-001",
        "family": "TestFamily",
        "workspace": "ws-456",
        "updatedAt": "2026-02-05T10:30:00Z",
        "keywords": ["test", "mock"],
        "properties": {"revision": "A", "status": "active"},
    }

    def mock_request(method: str, url: str, **_: Any) -> Any:
        resp: Any = MockResponse(product_data)
        return resp

    monkeypatch.setattr("slcli.testmonitor_click.make_api_request", mock_request)
    monkeypatch.setattr(
        "slcli.testmonitor_click.get_workspace_display_name",
        lambda ws: "Production",
    )

    cli = make_cli()
    result = runner.invoke(cli, ["testmonitor", "product", "get", "prod-123", "--format", "json"])

    assert result.exit_code == 0
    output_data = json.loads(result.output)
    assert output_data["name"] == "Test Product"
    assert output_data["partNumber"] == "TP-001"


def test_get_product_table(monkeypatch: Any, runner: CliRunner) -> None:
    """Test retrieving product details in table format."""
    patch_keyring(monkeypatch)

    product_data = {
        "id": "prod-123",
        "name": "Test Product",
        "partNumber": "TP-001",
        "family": "TestFamily",
        "workspace": "ws-456",
        "updatedAt": "2026-02-05T10:30:00Z",
        "keywords": ["test", "mock"],
        "properties": {"revision": "A"},
    }

    def mock_request(method: str, url: str, **_: Any) -> Any:
        resp: Any = MockResponse(product_data)
        return resp

    monkeypatch.setattr("slcli.testmonitor_click.make_api_request", mock_request)
    monkeypatch.setattr(
        "slcli.testmonitor_click.get_workspace_display_name",
        lambda ws: "Production",
    )

    cli = make_cli()
    result = runner.invoke(cli, ["testmonitor", "product", "get", "prod-123"])

    assert result.exit_code == 0
    assert "Test Product" in result.output
    assert "TP-001" in result.output
    assert "TestFamily" in result.output


def test_get_result_json_with_steps(monkeypatch: Any, runner: CliRunner) -> None:
    """Test retrieving result details with steps in JSON format."""
    patch_keyring(monkeypatch)

    result_data = {
        "id": "result-789",
        "status": {"statusType": "PASSED", "statusName": "Passed"},
        "programName": "Calibration",
        "partNumber": "XYZ-001",
        "serialNumber": "SN123456",
        "startedAt": "2026-02-05T10:30:00Z",
        "updatedAt": "2026-02-05T10:35:42Z",
        "systemId": "sys-abc",
        "hostName": "test-station-01",
        "operator": "engineer@test.com",
        "totalTimeInSeconds": 342.5,
        "workspace": "ws-456",
    }

    steps_data = {
        "steps": [
            {
                "name": "DMM Voltage Test",
                "stepType": "NumericLimitTest",
                "stepId": "step-001",
                "resultId": "result-789",
                "path": ["Setup", "DMM Tests", "Voltage"],
                "status": {"statusType": "PASSED", "statusName": "Passed"},
                "totalTimeInSeconds": 5.2,
                "outputs": [{"name": "Voltage", "value": 5.01}],
                "dataModel": "TestStand",
            }
        ]
    }

    call_count = 0

    def mock_request(method: str, url: str, **_: Any) -> Any:
        nonlocal call_count
        call_count += 1
        if "results" in url and call_count == 1:
            return MockResponse(result_data)
        elif "query-steps" in url:
            return MockResponse(steps_data)
        return MockResponse({})

    monkeypatch.setattr("slcli.testmonitor_click.make_api_request", mock_request)

    cli = make_cli()
    result = runner.invoke(
        cli, ["testmonitor", "result", "get", "result-789", "--include-steps", "--format", "json"]
    )

    assert result.exit_code == 0
    output_data = json.loads(result.output)
    assert output_data["programName"] == "Calibration"
    assert "steps" in output_data
    assert len(output_data["steps"]) == 1
    assert output_data["steps"][0]["name"] == "DMM Voltage Test"


def test_get_result_table_with_measurements(monkeypatch: Any, runner: CliRunner) -> None:
    """Test retrieving result details with measurements in table format."""
    patch_keyring(monkeypatch)

    result_data = {
        "id": "result-789",
        "status": {"statusType": "PASSED", "statusName": "Passed"},
        "programName": "Calibration",
        "partNumber": "XYZ-001",
        "serialNumber": "SN123456",
        "startedAt": "2026-02-05T10:30:00Z",
        "updatedAt": "2026-02-05T10:35:42Z",
        "systemId": "sys-abc",
        "hostName": "test-station-01",
        "operator": "engineer@test.com",
        "totalTimeInSeconds": 342.5,
        "workspace": "ws-456",
    }

    steps_data = {
        "steps": [
            {
                "name": "DMM Voltage Test",
                "stepType": "NumericLimitTest",
                "stepId": "step-001",
                "resultId": "result-789",
                "path": ["Setup", "DMM Tests", "Voltage"],
                "status": {"statusType": "PASSED", "statusName": "Passed"},
                "totalTimeInSeconds": 5.2,
                "outputs": [
                    {"name": "Voltage", "value": 5.01},
                    {"name": "Current", "value": 1.23},
                ],
                "dataModel": "TestStand",
            }
        ]
    }

    call_count = 0

    def mock_request(method: str, url: str, **_: Any) -> Any:
        nonlocal call_count
        call_count += 1
        if "results" in url and call_count == 1:
            return MockResponse(result_data)
        elif "query-steps" in url:
            return MockResponse(steps_data)
        return MockResponse({})

    monkeypatch.setattr("slcli.testmonitor_click.make_api_request", mock_request)

    cli = make_cli()
    result = runner.invoke(
        cli,
        [
            "testmonitor",
            "result",
            "get",
            "result-789",
            "--include-steps",
            "--include-measurements",
        ],
    )

    assert result.exit_code == 0
    assert "Calibration" in result.output
    assert "PASSED" in result.output
    assert "DMM Voltage Test" in result.output
    assert "Voltage" in result.output
    assert "5.01" in result.output or "5.0" in result.output
    assert "Current" in result.output
    assert "1.23" in result.output or "1.2" in result.output


def test_get_result_error_handling(monkeypatch: Any, runner: CliRunner) -> None:
    """Test get result error handling."""
    patch_keyring(monkeypatch)

    def mock_request(method: str, url: str, **_: Any) -> Any:
        raise Exception("API Error")

    monkeypatch.setattr("slcli.testmonitor_click.make_api_request", mock_request)

    cli = make_cli()
    result = runner.invoke(cli, ["testmonitor", "result", "get", "result-789"])

    assert result.exit_code != 0
    assert "API Error" in result.output or "Error" in result.output


# --- Phase 3: Summary and grouping tests ---


def test_list_products_with_summary_flag_json(monkeypatch: Any, runner: CliRunner) -> None:
    """Test product list with --summary flag in JSON format."""
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
                        "family": "cRIO",
                        "partNumber": "156502A-11L",
                        "workspace": "ws-1",
                    },
                    {
                        "id": "prod-2",
                        "name": "cRIO-9050",
                        "family": "cRIO",
                        "partNumber": "157452-01",
                        "workspace": "ws-1",
                    },
                    {
                        "id": "prod-3",
                        "name": "myRIO-1900",
                        "family": "myRIO",
                        "partNumber": "784026-01",
                        "workspace": "ws-1",
                    },
                ]
            }
        )

    monkeypatch.setattr("slcli.testmonitor_click.make_api_request", mock_request)
    monkeypatch.setattr("slcli.testmonitor_click.get_workspace_map", lambda: {"ws-1": "Dev"})

    cli = make_cli()
    result = runner.invoke(cli, ["testmonitor", "product", "list", "--format", "json", "--summary"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "total" in data
    assert data["total"] == 3
    assert "families" in data
    # Verify we have 2 distinct families (cRIO and myRIO)
    assert data["families"] == 2


def test_list_products_with_summary_flag_table(monkeypatch: Any, runner: CliRunner) -> None:
    """Test product list with --summary flag in table format."""
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
                        "family": "cRIO",
                        "partNumber": "156502A-11L",
                        "workspace": "ws-1",
                        "updatedAt": "2024-01-10T12:00:00.000Z",
                    },
                    {
                        "id": "prod-2",
                        "name": "cRIO-9050",
                        "family": "cRIO",
                        "partNumber": "157452-01",
                        "workspace": "ws-1",
                        "updatedAt": "2024-01-11T12:00:00.000Z",
                    },
                    {
                        "id": "prod-3",
                        "name": "myRIO-1900",
                        "family": "myRIO",
                        "partNumber": "784026-01",
                        "workspace": "ws-1",
                        "updatedAt": "2024-01-12T12:00:00.000Z",
                    },
                ]
            }
        )

    monkeypatch.setattr("slcli.testmonitor_click.make_api_request", mock_request)
    monkeypatch.setattr("slcli.testmonitor_click.get_workspace_map", lambda: {"ws-1": "Dev"})

    cli = make_cli()
    result = runner.invoke(cli, ["testmonitor", "product", "list", "--summary"])

    assert result.exit_code == 0
    assert "Product Summary Statistics" in result.output
    assert "Total Products: 3" in result.output
    assert "Families:" in result.output


def test_list_results_with_summary_flag_json(monkeypatch: Any, runner: CliRunner) -> None:
    """Test result list with --summary flag in JSON format using efficient count queries."""
    patch_keyring(monkeypatch)

    def mock_request(
        method: str,
        url: str,
        payload: Optional[Dict[str, Any]] = None,
        json: Optional[Dict[str, Any]] = None,
        **_: Any,
    ) -> Any:
        # The new implementation makes separate count queries per status
        payload = payload or json
        if payload and payload.get("returnCount"):
            # Check which status type is being queried via substitutions
            subs = payload.get("substitutions", [])
            # First substitution could be from base filter, last one is the status
            if subs and "PASSED" in subs:
                return MockResponse({"totalCount": 2})
            elif subs and "FAILED" in subs:
                return MockResponse({"totalCount": 1})
            else:
                # Other status types have zero results
                return MockResponse({"totalCount": 0})

        # Fallback for non-count queries
        return MockResponse({"results": []})

    monkeypatch.setattr("slcli.testmonitor_click.make_api_request", mock_request)
    monkeypatch.setattr("slcli.testmonitor_click.get_workspace_map", lambda: {})

    cli = make_cli()
    result = runner.invoke(cli, ["testmonitor", "result", "list", "--format", "json", "--summary"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "total" in data
    assert data["total"] == 3
    assert "groups" in data
    # Verify grouping by status is correct (PASSED: 2, FAILED: 1)
    assert "PASSED" in data["groups"]
    assert data["groups"]["PASSED"] == 2
    assert "FAILED" in data["groups"]
    assert data["groups"]["FAILED"] == 1


def test_list_results_with_groupby_flag_json(monkeypatch: Any, runner: CliRunner) -> None:
    """Test result list with --group-by flag in JSON format."""
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
                        "startedAt": "2024-01-12T10:00:00.000Z",
                        "totalTimeInSeconds": 12.3,
                    },
                    {
                        "id": "res-2",
                        "programName": "Diagnostics",
                        "status": {"statusType": "PASSED"},
                        "startedAt": "2024-01-12T11:00:00.000Z",
                        "totalTimeInSeconds": 8.5,
                    },
                    {
                        "id": "res-3",
                        "programName": "Calibration",
                        "status": {"statusType": "FAILED"},
                        "startedAt": "2024-01-12T12:00:00.000Z",
                        "totalTimeInSeconds": 3.2,
                    },
                ]
            }
        )

    monkeypatch.setattr("slcli.testmonitor_click.make_api_request", mock_request)
    monkeypatch.setattr("slcli.testmonitor_click.get_workspace_map", lambda: {})

    cli = make_cli()
    result = runner.invoke(
        cli,
        ["testmonitor", "result", "list", "--format", "json", "--group-by", "programName"],
    )

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "total" in data
    assert data["total"] == 3
    assert "groups" in data
    # Verify grouping by programName is correct (Calibration: 2, Diagnostics: 1)
    assert "Calibration" in data["groups"]
    assert data["groups"]["Calibration"] == 2
    assert "Diagnostics" in data["groups"]
    assert data["groups"]["Diagnostics"] == 1


def test_list_results_with_summary_flag_table(monkeypatch: Any, runner: CliRunner) -> None:
    """Test result list with --summary flag in table format."""
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
                        "serialNumber": "abc-123",
                        "partNumber": "cRIO-9030",
                        "status": {"statusType": "PASSED"},
                        "startedAt": "2024-01-12T10:00:00.000Z",
                        "totalTimeInSeconds": 12.3,
                    },
                    {
                        "id": "res-2",
                        "programName": "Diagnostics",
                        "serialNumber": "abc-124",
                        "partNumber": "cRIO-9030",
                        "status": {"statusType": "PASSED"},
                        "startedAt": "2024-01-12T11:00:00.000Z",
                        "totalTimeInSeconds": 8.5,
                    },
                    {
                        "id": "res-3",
                        "programName": "Calibration",
                        "serialNumber": "abc-125",
                        "partNumber": "cRIO-9030",
                        "status": {"statusType": "FAILED"},
                        "startedAt": "2024-01-12T12:00:00.000Z",
                        "totalTimeInSeconds": 3.2,
                    },
                ]
            }
        )

    monkeypatch.setattr("slcli.testmonitor_click.make_api_request", mock_request)
    monkeypatch.setattr("slcli.testmonitor_click.get_workspace_map", lambda: {})

    cli = make_cli()
    result = runner.invoke(cli, ["testmonitor", "result", "list", "--summary"])

    assert result.exit_code == 0
    assert "Test Results Summary" in result.output
    assert "Total Results: 3" in result.output


def test_summarize_results_empty_list() -> None:
    """Test summarize results with empty list."""
    from slcli.testmonitor_click import _summarize_results

    result = _summarize_results([], "status")
    assert result["total"] == 0
    assert result.get("groups", {}) == {}


def test_summarize_products_empty_list() -> None:
    """Test summarize products with empty list."""
    from slcli.testmonitor_click import _summarize_products

    result = _summarize_products([])
    assert result["total"] == 0
    assert result["families"] == 0


# --- Product create tests ---


def test_create_product_basic(monkeypatch: Any, runner: CliRunner) -> None:
    """Test creating a product with required part number."""
    patch_keyring(monkeypatch)

    captured: Dict[str, Any] = {}

    def mock_request(
        method: str, url: str, payload: Optional[Dict[str, Any]] = None, **_: Any
    ) -> Any:
        captured["method"] = method
        captured["url"] = url
        captured["payload"] = payload
        return MockResponse(
            {
                "products": [
                    {
                        "id": "prod-new-1",
                        "name": "cRIO-9030",
                        "partNumber": "156502A-11L",
                        "family": "cRIO",
                        "workspace": "ws-1",
                    }
                ]
            },
            status_code=201,
        )

    monkeypatch.setattr("slcli.testmonitor_click.make_api_request", mock_request)
    monkeypatch.setattr("slcli.testmonitor_click.get_workspace_map", lambda: {})
    monkeypatch.setattr("slcli.profiles.is_active_profile_readonly", lambda: False)

    cli = make_cli()
    result = runner.invoke(
        cli,
        [
            "testmonitor",
            "product",
            "create",
            "--part-number",
            "156502A-11L",
            "--name",
            "cRIO-9030",
            "--family",
            "cRIO",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Product created" in result.output
    assert "prod-new-1" in result.output
    assert captured["method"] == "POST"
    assert "/products" in captured["url"]
    assert captured["payload"]["products"][0]["partNumber"] == "156502A-11L"
    assert captured["payload"]["products"][0]["name"] == "cRIO-9030"


def test_create_product_json_output(monkeypatch: Any, runner: CliRunner) -> None:
    """Test creating a product with JSON format output."""
    patch_keyring(monkeypatch)

    created_product = {
        "id": "prod-new-2",
        "name": "cRIO-9030",
        "partNumber": "156502A-12L",
        "workspace": "ws-1",
    }

    def mock_request(
        method: str, url: str, payload: Optional[Dict[str, Any]] = None, **_: Any
    ) -> Any:
        return MockResponse({"products": [created_product]}, status_code=201)

    monkeypatch.setattr("slcli.testmonitor_click.make_api_request", mock_request)
    monkeypatch.setattr("slcli.testmonitor_click.get_workspace_map", lambda: {})
    monkeypatch.setattr("slcli.profiles.is_active_profile_readonly", lambda: False)

    cli = make_cli()
    result = runner.invoke(
        cli,
        ["testmonitor", "product", "create", "--part-number", "156502A-12L", "--format", "json"],
    )

    assert result.exit_code == 0, result.output
    output = json.loads(result.output)
    assert output["id"] == "prod-new-2"
    assert output["partNumber"] == "156502A-12L"


def test_create_product_with_keywords_and_properties(monkeypatch: Any, runner: CliRunner) -> None:
    """Test creating a product with keywords and properties."""
    patch_keyring(monkeypatch)

    captured: Dict[str, Any] = {}

    def mock_request(
        method: str, url: str, payload: Optional[Dict[str, Any]] = None, **_: Any
    ) -> Any:
        captured["payload"] = payload
        return MockResponse(
            {"products": [{"id": "prod-kwp", "partNumber": "PN-001"}]},
            status_code=201,
        )

    monkeypatch.setattr("slcli.testmonitor_click.make_api_request", mock_request)
    monkeypatch.setattr("slcli.testmonitor_click.get_workspace_map", lambda: {})
    monkeypatch.setattr("slcli.profiles.is_active_profile_readonly", lambda: False)

    cli = make_cli()
    result = runner.invoke(
        cli,
        [
            "testmonitor",
            "product",
            "create",
            "--part-number",
            "PN-001",
            "--keyword",
            "kw1",
            "--keyword",
            "kw2",
            "--property",
            "owner=team-a",
            "--property",
            "region=us",
        ],
    )

    assert result.exit_code == 0, result.output
    product_obj = captured["payload"]["products"][0]
    assert product_obj["keywords"] == ["kw1", "kw2"]
    assert product_obj["properties"] == {"owner": "team-a", "region": "us"}


def test_create_product_invalid_property_format(monkeypatch: Any, runner: CliRunner) -> None:
    """Test that an invalid property format exits with an error."""
    patch_keyring(monkeypatch)
    monkeypatch.setattr("slcli.profiles.is_active_profile_readonly", lambda: False)

    cli = make_cli()
    result = runner.invoke(
        cli,
        [
            "testmonitor",
            "product",
            "create",
            "--part-number",
            "PN-001",
            "--property",
            "bad-format",
        ],
    )

    assert result.exit_code != 0
    assert "KEY=VALUE" in result.output


def test_create_product_missing_part_number(monkeypatch: Any, runner: CliRunner) -> None:
    """Test that missing --part-number causes a usage error."""
    patch_keyring(monkeypatch)
    monkeypatch.setattr("slcli.profiles.is_active_profile_readonly", lambda: False)

    cli = make_cli()
    result = runner.invoke(cli, ["testmonitor", "product", "create"])

    assert result.exit_code != 0


# --- Product update tests ---


def test_update_product_basic(monkeypatch: Any, runner: CliRunner) -> None:
    """Test updating a product name and family."""
    patch_keyring(monkeypatch)

    captured: Dict[str, Any] = {}

    def mock_request(
        method: str, url: str, payload: Optional[Dict[str, Any]] = None, **_: Any
    ) -> Any:
        captured["method"] = method
        captured["url"] = url
        captured["payload"] = payload
        return MockResponse(
            {
                "products": [
                    {
                        "id": "prod-1",
                        "name": "cRIO-Updated",
                        "partNumber": "156502A-11L",
                    }
                ]
            }
        )

    monkeypatch.setattr("slcli.testmonitor_click.make_api_request", mock_request)
    monkeypatch.setattr("slcli.testmonitor_click.get_workspace_map", lambda: {})
    monkeypatch.setattr("slcli.profiles.is_active_profile_readonly", lambda: False)

    cli = make_cli()
    result = runner.invoke(
        cli,
        [
            "testmonitor",
            "product",
            "update",
            "prod-1",
            "--name",
            "cRIO-Updated",
            "--family",
            "NewFamily",
        ],
    )

    assert result.exit_code == 0, result.output
    assert "Product updated" in result.output
    assert "prod-1" in result.output
    assert captured["method"] == "POST"
    assert "/update-products" in captured["url"]
    assert captured["payload"]["products"][0]["id"] == "prod-1"
    assert captured["payload"]["products"][0]["name"] == "cRIO-Updated"
    assert captured["payload"]["replace"] is False


def test_update_product_with_replace_flag(monkeypatch: Any, runner: CliRunner) -> None:
    """Test updating a product with --replace flag sets replace=True in payload."""
    patch_keyring(monkeypatch)

    captured: Dict[str, Any] = {}

    def mock_request(
        method: str, url: str, payload: Optional[Dict[str, Any]] = None, **_: Any
    ) -> Any:
        captured["payload"] = payload
        return MockResponse({"products": [{"id": "prod-1", "name": "Updated", "partNumber": "PN"}]})

    monkeypatch.setattr("slcli.testmonitor_click.make_api_request", mock_request)
    monkeypatch.setattr("slcli.testmonitor_click.get_workspace_map", lambda: {})
    monkeypatch.setattr("slcli.profiles.is_active_profile_readonly", lambda: False)

    cli = make_cli()
    result = runner.invoke(
        cli,
        ["testmonitor", "product", "update", "prod-1", "--name", "Updated", "--replace"],
    )

    assert result.exit_code == 0, result.output
    assert captured["payload"]["replace"] is True


def test_update_product_json_output(monkeypatch: Any, runner: CliRunner) -> None:
    """Test update product JSON format output."""
    patch_keyring(monkeypatch)

    updated_product = {"id": "prod-1", "name": "Updated", "partNumber": "PN-002"}

    def mock_request(
        method: str, url: str, payload: Optional[Dict[str, Any]] = None, **_: Any
    ) -> Any:
        return MockResponse({"products": [updated_product]})

    monkeypatch.setattr("slcli.testmonitor_click.make_api_request", mock_request)
    monkeypatch.setattr("slcli.testmonitor_click.get_workspace_map", lambda: {})
    monkeypatch.setattr("slcli.profiles.is_active_profile_readonly", lambda: False)

    cli = make_cli()
    result = runner.invoke(
        cli,
        ["testmonitor", "product", "update", "prod-1", "--name", "Updated", "--format", "json"],
    )

    assert result.exit_code == 0, result.output
    output = json.loads(result.output)
    assert output["id"] == "prod-1"
    assert output["name"] == "Updated"


# --- Product delete tests ---


def test_delete_product_single(monkeypatch: Any, runner: CliRunner) -> None:
    """Test deleting a single product (uses DELETE single endpoint)."""
    patch_keyring(monkeypatch)

    captured: Dict[str, Any] = {}

    def mock_request(
        method: str, url: str, payload: Optional[Dict[str, Any]] = None, **_: Any
    ) -> Any:
        captured["method"] = method
        captured["url"] = url
        return MockResponse({}, status_code=204)

    monkeypatch.setattr("slcli.testmonitor_click.make_api_request", mock_request)
    monkeypatch.setattr("slcli.profiles.is_active_profile_readonly", lambda: False)

    cli = make_cli()
    result = runner.invoke(cli, ["testmonitor", "product", "delete", "--yes", "prod-1"])

    assert result.exit_code == 0, result.output
    assert "deleted successfully" in result.output
    assert captured["method"] == "DELETE"
    assert "products/prod-1" in captured["url"]


def test_delete_product_multiple(monkeypatch: Any, runner: CliRunner) -> None:
    """Test deleting multiple products (uses bulk delete endpoint)."""
    patch_keyring(monkeypatch)

    captured: Dict[str, Any] = {}

    def mock_request(
        method: str, url: str, payload: Optional[Dict[str, Any]] = None, **_: Any
    ) -> Any:
        captured["method"] = method
        captured["url"] = url
        captured["payload"] = payload
        return MockResponse({"ids": ["prod-1", "prod-2"], "failed": []})

    monkeypatch.setattr("slcli.testmonitor_click.make_api_request", mock_request)
    monkeypatch.setattr("slcli.profiles.is_active_profile_readonly", lambda: False)

    cli = make_cli()
    result = runner.invoke(cli, ["testmonitor", "product", "delete", "--yes", "prod-1", "prod-2"])

    assert result.exit_code == 0, result.output
    assert "Deleted" in result.output
    assert captured["method"] == "POST"
    assert "delete-products" in captured["url"]
    assert set(captured["payload"]["ids"]) == {"prod-1", "prod-2"}


def test_delete_product_confirmation_aborted(monkeypatch: Any, runner: CliRunner) -> None:
    """Test that declining the confirmation prompt aborts deletion."""
    patch_keyring(monkeypatch)
    monkeypatch.setattr("slcli.profiles.is_active_profile_readonly", lambda: False)

    cli = make_cli()
    with patch("slcli.testmonitor_click.questionary.confirm") as mock_confirm:
        mock_confirm.return_value.ask.return_value = False
        result = runner.invoke(cli, ["testmonitor", "product", "delete", "prod-1"])

    assert result.exit_code == 0
    assert "Aborted" in result.output


def test_delete_product_multiple_partial_failure(monkeypatch: Any, runner: CliRunner) -> None:
    """Test bulk delete with partial failure reports failures."""
    patch_keyring(monkeypatch)

    def mock_request(
        method: str, url: str, payload: Optional[Dict[str, Any]] = None, **_: Any
    ) -> Any:
        return MockResponse({"ids": ["prod-1"], "failed": ["prod-2"]})

    monkeypatch.setattr("slcli.testmonitor_click.make_api_request", mock_request)
    monkeypatch.setattr("slcli.profiles.is_active_profile_readonly", lambda: False)

    cli = make_cli()
    result = runner.invoke(cli, ["testmonitor", "product", "delete", "--yes", "prod-1", "prod-2"])

    assert result.exit_code != 0
