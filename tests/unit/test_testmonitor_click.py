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
    """Test result list with --summary flag in JSON format."""
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
                        "status": {"statusType": "PASSED"},
                        "startedAt": "2024-01-12T10:00:00.000Z",
                        "totalTimeInSeconds": 12.3,
                    },
                    {
                        "id": "res-2",
                        "programName": "Diagnostics",
                        "serialNumber": "abc-124",
                        "status": {"statusType": "PASSED"},
                        "startedAt": "2024-01-12T11:00:00.000Z",
                        "totalTimeInSeconds": 8.5,
                    },
                    {
                        "id": "res-3",
                        "programName": "Calibration",
                        "serialNumber": "abc-125",
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
    result = runner.invoke(cli, ["testmonitor", "result", "list", "--format", "json", "--summary"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert "total" in data
    assert data["total"] == 3
    assert "groups" in data


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


def test_parse_natural_date_yesterday() -> None:
    """Test natural date parsing for 'yesterday'."""
    from slcli.testmonitor_click import _parse_natural_date

    result = _parse_natural_date("yesterday")
    # Result should be a date string, just verify it's not the input
    assert result != "yesterday"
    # Should be in ISO format (YYYY-MM-DD or similar)
    assert "T" in result or "-" in result


def test_parse_natural_date_weeks_ago() -> None:
    """Test natural date parsing for 'X weeks ago'."""
    from slcli.testmonitor_click import _parse_natural_date

    result = _parse_natural_date("2 weeks ago")
    assert result != "2 weeks ago"
    assert "T" in result or "-" in result


def test_parse_natural_date_quarters_ago() -> None:
    """Test natural date parsing for 'X quarters ago'."""
    from slcli.testmonitor_click import _parse_natural_date

    result = _parse_natural_date("3 quarters ago")
    assert result != "3 quarters ago"
    assert "T" in result or "-" in result


def test_parse_natural_date_invalid() -> None:
    """Test natural date parsing with invalid input."""
    from slcli.testmonitor_click import _parse_natural_date

    # Should return original on invalid input
    result = _parse_natural_date("invalid-date")
    assert result == "invalid-date"


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
