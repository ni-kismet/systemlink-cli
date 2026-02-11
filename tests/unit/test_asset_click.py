"""Unit tests for asset CLI commands."""

import json
from typing import Any, Dict, List, Optional

import click
import pytest
from click.testing import CliRunner

from slcli.asset_click import (
    _build_asset_filter,
    _escape_filter_value,
    _get_asset_location_display,
    _parse_properties,
    _query_all_assets,
    _summarize_assets,
    register_asset_commands,
)


def patch_keyring(monkeypatch: Any) -> None:
    """Patch keyring to return test values."""
    monkeypatch.setattr(
        "slcli.utils.keyring.get_password",
        lambda service, key: ("test-key" if key == "SYSTEMLINK_API_KEY" else "https://test.com"),
    )


def make_cli() -> click.Group:
    """Create CLI instance with asset commands for testing."""

    @click.group()
    def test_cli() -> None:
        pass

    register_asset_commands(test_cli)
    return test_cli


@pytest.fixture
def runner() -> CliRunner:
    """Create a CliRunner for tests."""
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
        """Return the JSON data."""
        return self._json_data

    def raise_for_status(self) -> None:
        """Raise on HTTP error status."""
        if self.status_code >= 400:
            raise Exception(f"HTTP error {self.status_code}")


SAMPLE_ASSET: Dict[str, Any] = {
    "id": "asset-1",
    "name": "NI PXIe-6368",
    "modelName": "PXIe-6368",
    "modelNumber": "PXIe-6368",
    "serialNumber": "01BB877A",
    "vendorName": "NI",
    "vendorNumber": "V001",
    "partNumber": "A1234",
    "busType": "PCI_PXI",
    "assetType": "GENERIC",
    "firmwareVersion": "A1",
    "hardwareVersion": "12A",
    "calibrationStatus": "OK",
    "workspace": "ws-1",
    "location": {
        "minionId": "minion-A",
        "physicalLocation": "",
        "slotNumber": 2,
        "state": {
            "assetPresence": "PRESENT",
            "systemConnection": "CONNECTED",
        },
    },
    "keywords": ["Keyword1", "Keyword2"],
    "properties": {"Key1": "Value1"},
}

SAMPLE_ASSET_2: Dict[str, Any] = {
    "id": "asset-2",
    "name": "NI PXI-4071",
    "modelName": "PXI-4071",
    "serialNumber": "02CC999B",
    "busType": "PCI_PXI",
    "assetType": "GENERIC",
    "calibrationStatus": "PAST_RECOMMENDED_DUE_DATE",
    "workspace": "ws-2",
    "location": {
        "minionId": "minion-B",
        "slotNumber": 5,
        "state": {
            "assetPresence": "PRESENT",
            "systemConnection": "CONNECTED",
        },
    },
}


# =============================================================================
# Helper function tests
# =============================================================================


class TestEscapeFilterValue:
    """Tests for _escape_filter_value."""

    def test_escapes_double_quotes(self) -> None:
        """Test that double quotes are escaped."""
        assert _escape_filter_value('value"with"quotes') == 'value\\"with\\"quotes'

    def test_no_quotes(self) -> None:
        """Test that plain strings pass through unchanged."""
        assert _escape_filter_value("simple") == "simple"

    def test_empty_string(self) -> None:
        """Test that empty strings pass through."""
        assert _escape_filter_value("") == ""


class TestBuildAssetFilter:
    """Tests for _build_asset_filter."""

    def test_no_filters_returns_none(self) -> None:
        """Test that no filters returns None."""
        assert _build_asset_filter() is None

    def test_model_filter(self) -> None:
        """Test model name filter uses Contains."""
        result = _build_asset_filter(model="PXI-4071")
        assert result == 'ModelName.Contains("PXI-4071")'

    def test_serial_number_filter(self) -> None:
        """Test serial number filter uses exact match."""
        result = _build_asset_filter(serial_number="01BB877A")
        assert result == 'SerialNumber = "01BB877A"'

    def test_bus_type_filter(self) -> None:
        """Test bus type filter."""
        result = _build_asset_filter(bus_type="PCI_PXI")
        assert result == 'BusType = "PCI_PXI"'

    def test_asset_type_filter(self) -> None:
        """Test asset type filter."""
        result = _build_asset_filter(asset_type="DEVICE_UNDER_TEST")
        assert result == 'AssetType = "DEVICE_UNDER_TEST"'

    def test_calibration_status_filter(self) -> None:
        """Test calibration status filter."""
        result = _build_asset_filter(calibration_status="OK")
        assert result == 'CalibrationStatus = "OK"'

    def test_connected_filter(self) -> None:
        """Test connected flag adds SystemConnection and AssetPresence."""
        result = _build_asset_filter(connected=True)
        assert result is not None
        assert 'SystemConnection = "CONNECTED"' in result
        assert 'AssetPresence = "PRESENT"' in result

    def test_workspace_filter(self) -> None:
        """Test workspace filter."""
        result = _build_asset_filter(workspace_id="ws-123")
        assert result == 'Workspace = "ws-123"'

    def test_custom_filter(self) -> None:
        """Test custom filter passthrough."""
        result = _build_asset_filter(custom_filter='VendorName = "NI"')
        assert result == 'VendorName = "NI"'

    def test_combined_filters(self) -> None:
        """Test multiple filters are joined with 'and'."""
        result = _build_asset_filter(model="PXI", bus_type="USB")
        assert result is not None
        assert 'ModelName.Contains("PXI")' in result
        assert 'BusType = "USB"' in result
        assert " and " in result

    def test_escapes_model_injection(self) -> None:
        """Test that injection in model values is escaped."""
        result = _build_asset_filter(model='PXI") or (1=1) and ("')
        assert result is not None
        assert '\\"' in result


class TestGetAssetLocationDisplay:
    """Tests for _get_asset_location_display."""

    def test_no_location(self) -> None:
        """Test asset with no location returns empty string."""
        assert _get_asset_location_display({}) == ""

    def test_location_none(self) -> None:
        """Test asset with None location returns empty string."""
        assert _get_asset_location_display({"location": None}) == ""

    def test_minion_id_with_slot(self) -> None:
        """Test location with minionId and slot."""
        asset: Dict[str, Any] = {"location": {"minionId": "controller-1", "slotNumber": 3}}
        assert _get_asset_location_display(asset) == "controller-1 (Slot 3)"

    def test_physical_location_only(self) -> None:
        """Test physical location without minionId."""
        asset: Dict[str, Any] = {"location": {"minionId": "", "physicalLocation": "Lab A"}}
        assert _get_asset_location_display(asset) == "Lab A"

    def test_slot_only(self) -> None:
        """Test location with slot but no minionId or physical."""
        asset: Dict[str, Any] = {
            "location": {"minionId": "", "physicalLocation": "", "slotNumber": 7}
        }
        assert _get_asset_location_display(asset) == "Slot 7"


class TestSummarizeAssets:
    """Tests for _summarize_assets."""

    def test_empty_list(self) -> None:
        """Test summary of empty list."""
        result = _summarize_assets([])
        assert result["total"] == 0

    def test_counts_bus_types(self) -> None:
        """Test that bus types are counted."""
        result = _summarize_assets([SAMPLE_ASSET, SAMPLE_ASSET_2])
        assert result["busTypes"]["PCI_PXI"] == 2

    def test_counts_calibration_statuses(self) -> None:
        """Test that calibration statuses are counted."""
        result = _summarize_assets([SAMPLE_ASSET, SAMPLE_ASSET_2])
        assert result["calibrationStatuses"]["OK"] == 1
        assert result["calibrationStatuses"]["PAST_RECOMMENDED_DUE_DATE"] == 1

    def test_truncation_indicator(self) -> None:
        """Test truncation indicator when hitting max."""
        assets = [SAMPLE_ASSET] * 10
        result = _summarize_assets(assets, max_items=10)
        assert result["truncated"] is True


class TestParseProperties:
    """Tests for _parse_properties."""

    def test_parse_single_property(self) -> None:
        """Test parsing a single key=value property."""
        result = _parse_properties(("location=Lab A",))
        assert result == {"location": "Lab A"}

    def test_parse_multiple_properties(self) -> None:
        """Test parsing multiple properties."""
        result = _parse_properties(("key1=val1", "key2=val2"))
        assert result == {"key1": "val1", "key2": "val2"}

    def test_parse_property_with_equals_in_value(self) -> None:
        """Test that only the first = is used as delimiter."""
        result = _parse_properties(("expr=a=b",))
        assert result == {"expr": "a=b"}

    def test_parse_property_strips_whitespace(self) -> None:
        """Test that keys and values are stripped."""
        result = _parse_properties((" key = value ",))
        assert result == {"key": "value"}

    def test_parse_invalid_property_exits(self) -> None:
        """Test that invalid format exits with INVALID_INPUT."""
        with pytest.raises(SystemExit) as exc_info:
            _parse_properties(("badformat",))
        assert exc_info.value.code == 2  # ExitCodes.INVALID_INPUT

    def test_parse_empty_tuple(self) -> None:
        """Test parsing an empty tuple."""
        result = _parse_properties(())
        assert result == {}


class TestQueryAllAssets:
    """Tests for _query_all_assets pagination logic."""

    def test_single_page(self, monkeypatch: Any) -> None:
        """Test fetching when all assets fit in a single page."""
        patch_keyring(monkeypatch)
        assets = [SAMPLE_ASSET, SAMPLE_ASSET_2]

        def mock_request(
            method: str,
            url: str,
            payload: Optional[Dict[str, Any]] = None,
            **_: Any,
        ) -> Any:
            return MockResponse({"assets": assets, "totalCount": 2})

        monkeypatch.setattr("slcli.asset_click.make_api_request", mock_request)

        result = _query_all_assets(None, None, False, take=100)
        assert len(result) == 2
        assert result[0]["id"] == "asset-1"
        assert result[1]["id"] == "asset-2"

    def test_multi_page_accumulation(self, monkeypatch: Any) -> None:
        """Test that multiple pages are accumulated correctly."""
        patch_keyring(monkeypatch)
        page1 = [{"id": f"asset-{i}"} for i in range(1000)]
        page2 = [{"id": f"asset-{i}"} for i in range(1000, 1500)]

        call_count = 0

        def mock_request(
            method: str,
            url: str,
            payload: Optional[Dict[str, Any]] = None,
            **_: Any,
        ) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return MockResponse({"assets": page1, "totalCount": 1500})
            return MockResponse({"assets": page2, "totalCount": 1500})

        monkeypatch.setattr("slcli.asset_click.make_api_request", mock_request)

        result = _query_all_assets(None, None, False, take=10000)
        assert len(result) == 1500
        assert call_count == 2

    def test_take_cap_truncates_results(self, monkeypatch: Any) -> None:
        """Test that results are truncated at the take limit."""
        patch_keyring(monkeypatch)
        all_items = [{"id": f"asset-{i}"} for i in range(1000)]

        def mock_request(
            method: str,
            url: str,
            payload: Optional[Dict[str, Any]] = None,
            **_: Any,
        ) -> Any:
            take = payload.get("take", 1000) if payload else 1000
            return MockResponse({"assets": all_items[:take], "totalCount": 1000})

        monkeypatch.setattr("slcli.asset_click.make_api_request", mock_request)

        result = _query_all_assets(None, None, False, take=50)
        assert len(result) == 50

    def test_early_exit_on_short_page(self, monkeypatch: Any) -> None:
        """Test that pagination stops when a page returns fewer items than requested."""
        patch_keyring(monkeypatch)

        call_count = 0

        def mock_request(
            method: str,
            url: str,
            payload: Optional[Dict[str, Any]] = None,
            **_: Any,
        ) -> Any:
            nonlocal call_count
            call_count += 1
            # Return only 3 items — less than batch_size, signals last page
            return MockResponse({"assets": [{"id": f"a-{i}"} for i in range(3)], "totalCount": 3})

        monkeypatch.setattr("slcli.asset_click.make_api_request", mock_request)

        result = _query_all_assets(None, None, False, take=10000)
        assert len(result) == 3
        assert call_count == 1  # Should not make a second request

    def test_empty_result(self, monkeypatch: Any) -> None:
        """Test handling of empty results."""
        patch_keyring(monkeypatch)

        def mock_request(
            method: str,
            url: str,
            payload: Optional[Dict[str, Any]] = None,
            **_: Any,
        ) -> Any:
            return MockResponse({"assets": [], "totalCount": 0})

        monkeypatch.setattr("slcli.asset_click.make_api_request", mock_request)

        result = _query_all_assets(None, None, False)
        assert result == []

    def test_filter_and_order_passed_to_api(self, monkeypatch: Any) -> None:
        """Test that filter, orderBy, and calibratableOnly are sent in payload."""
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
            return MockResponse({"assets": [], "totalCount": 0})

        monkeypatch.setattr("slcli.asset_click.make_api_request", mock_request)

        _query_all_assets(
            filter_expr='BusType = "USB"',
            order_by="ID",
            descending=True,
            calibratable_only=True,
        )
        assert len(captured_payloads) == 1
        p = captured_payloads[0]
        assert p["filter"] == 'BusType = "USB"'
        assert p["orderBy"] == "ID"
        assert p["descending"] is True
        assert p["calibratableOnly"] is True


# =============================================================================
# asset list command tests
# =============================================================================


class TestListAssets:
    """Tests for the asset list command."""

    def test_list_assets_table(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test listing assets in table format."""
        patch_keyring(monkeypatch)

        def mock_request(
            method: str,
            url: str,
            payload: Optional[Dict[str, Any]] = None,
            **_: Any,
        ) -> Any:
            return MockResponse({"assets": [SAMPLE_ASSET], "totalCount": 1})

        monkeypatch.setattr("slcli.asset_click.make_api_request", mock_request)
        monkeypatch.setattr("slcli.asset_click.get_workspace_map", lambda: {"ws-1": "Dev"})

        cli = make_cli()
        result = runner.invoke(cli, ["asset", "list"])
        assert result.exit_code == 0
        assert "PXIe-6368" in result.output

    def test_list_assets_json(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test listing assets in JSON format."""
        patch_keyring(monkeypatch)

        call_count = 0

        def mock_request(
            method: str,
            url: str,
            payload: Optional[Dict[str, Any]] = None,
            **_: Any,
        ) -> Any:
            nonlocal call_count
            call_count += 1
            # First call is _warn_if_large_dataset (take=1)
            if payload and payload.get("take") == 1:
                return MockResponse({"assets": [], "totalCount": 1})
            return MockResponse({"assets": [SAMPLE_ASSET, SAMPLE_ASSET_2], "totalCount": 2})

        monkeypatch.setattr("slcli.asset_click.make_api_request", mock_request)
        monkeypatch.setattr("slcli.asset_click.get_workspace_map", lambda: {"ws-1": "Dev"})

        cli = make_cli()
        result = runner.invoke(cli, ["asset", "list", "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 2
        assert data[0]["id"] == "asset-1"

    def test_list_assets_with_model_filter(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test that --model option builds correct filter."""
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
            return MockResponse({"assets": [SAMPLE_ASSET], "totalCount": 1})

        monkeypatch.setattr("slcli.asset_click.make_api_request", mock_request)
        monkeypatch.setattr("slcli.asset_click.get_workspace_map", lambda: {"ws-1": "Dev"})

        cli = make_cli()
        result = runner.invoke(cli, ["asset", "list", "--model", "PXI-4071"])
        assert result.exit_code == 0
        assert any(
            'ModelName.Contains("PXI-4071")' in p.get("filter", "") for p in captured_payloads
        )

    def test_list_assets_with_connected_flag(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test that --connected option builds correct filter."""
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
            return MockResponse({"assets": [], "totalCount": 0})

        monkeypatch.setattr("slcli.asset_click.make_api_request", mock_request)
        monkeypatch.setattr("slcli.asset_click.get_workspace_map", lambda: {})

        cli = make_cli()
        result = runner.invoke(cli, ["asset", "list", "--connected"])
        assert result.exit_code == 0
        assert any(
            "CONNECTED" in p.get("filter", "") and "PRESENT" in p.get("filter", "")
            for p in captured_payloads
        )

    def test_list_assets_with_bus_type(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test --bus-type option."""
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
            return MockResponse({"assets": [], "totalCount": 0})

        monkeypatch.setattr("slcli.asset_click.make_api_request", mock_request)
        monkeypatch.setattr("slcli.asset_click.get_workspace_map", lambda: {})

        cli = make_cli()
        result = runner.invoke(cli, ["asset", "list", "--bus-type", "USB"])
        assert result.exit_code == 0
        assert any('BusType = "USB"' in p.get("filter", "") for p in captured_payloads)

    def test_list_assets_with_workspace_filter(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test --workspace resolves name to ID."""
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
            return MockResponse({"assets": [], "totalCount": 0})

        monkeypatch.setattr("slcli.asset_click.make_api_request", mock_request)
        monkeypatch.setattr(
            "slcli.asset_click.get_workspace_map",
            lambda: {"ws-1": "Production"},
        )

        cli = make_cli()
        result = runner.invoke(cli, ["asset", "list", "--workspace", "Production"])
        assert result.exit_code == 0
        assert any('Workspace = "ws-1"' in p.get("filter", "") for p in captured_payloads)

    def test_list_assets_with_custom_filter(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test --filter option passes through custom expression."""
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
            return MockResponse({"assets": [], "totalCount": 0})

        monkeypatch.setattr("slcli.asset_click.make_api_request", mock_request)
        monkeypatch.setattr("slcli.asset_click.get_workspace_map", lambda: {})

        cli = make_cli()
        custom = 'VendorName = "NI"'
        result = runner.invoke(cli, ["asset", "list", "--filter", custom])
        assert result.exit_code == 0
        assert any(custom in p.get("filter", "") for p in captured_payloads)

    def test_list_assets_summary_json(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test --summary flag with JSON output."""
        patch_keyring(monkeypatch)

        def mock_request(
            method: str,
            url: str,
            payload: Optional[Dict[str, Any]] = None,
            **_: Any,
        ) -> Any:
            return MockResponse({"assets": [SAMPLE_ASSET, SAMPLE_ASSET_2], "totalCount": 2})

        monkeypatch.setattr("slcli.asset_click.make_api_request", mock_request)
        monkeypatch.setattr("slcli.asset_click.get_workspace_map", lambda: {"ws-1": "Dev"})

        cli = make_cli()
        result = runner.invoke(cli, ["asset", "list", "--summary", "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["total"] == 2
        assert "busTypes" in data

    def test_list_assets_summary_table(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test --summary flag with table output."""
        patch_keyring(monkeypatch)

        def mock_request(
            method: str,
            url: str,
            payload: Optional[Dict[str, Any]] = None,
            **_: Any,
        ) -> Any:
            return MockResponse({"assets": [SAMPLE_ASSET], "totalCount": 1})

        monkeypatch.setattr("slcli.asset_click.make_api_request", mock_request)
        monkeypatch.setattr("slcli.asset_click.get_workspace_map", lambda: {"ws-1": "Dev"})

        cli = make_cli()
        result = runner.invoke(cli, ["asset", "list", "--summary"])
        assert result.exit_code == 0
        assert "Asset Summary Statistics:" in result.output
        assert "Total Assets: 1" in result.output

    def test_list_assets_order_by(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test --order-by and --ascending options."""
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
            return MockResponse({"assets": [], "totalCount": 0})

        monkeypatch.setattr("slcli.asset_click.make_api_request", mock_request)
        monkeypatch.setattr("slcli.asset_click.get_workspace_map", lambda: {})

        cli = make_cli()
        result = runner.invoke(
            cli,
            ["asset", "list", "--order-by", "ID", "--ascending"],
        )
        assert result.exit_code == 0
        assert any(
            p.get("orderBy") == "ID" and p.get("descending") is False for p in captured_payloads
        )

    def test_list_assets_calibratable_flag(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test --calibratable flag sets calibratableOnly."""
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
            return MockResponse({"assets": [], "totalCount": 0})

        monkeypatch.setattr("slcli.asset_click.make_api_request", mock_request)
        monkeypatch.setattr("slcli.asset_click.get_workspace_map", lambda: {})

        cli = make_cli()
        result = runner.invoke(cli, ["asset", "list", "--calibratable"])
        assert result.exit_code == 0
        assert any(p.get("calibratableOnly") is True for p in captured_payloads)

    def test_list_assets_empty(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test listing assets when none exist."""
        patch_keyring(monkeypatch)

        def mock_request(
            method: str,
            url: str,
            payload: Optional[Dict[str, Any]] = None,
            **_: Any,
        ) -> Any:
            return MockResponse({"assets": [], "totalCount": 0})

        monkeypatch.setattr("slcli.asset_click.make_api_request", mock_request)
        monkeypatch.setattr("slcli.asset_click.get_workspace_map", lambda: {})

        cli = make_cli()
        result = runner.invoke(cli, ["asset", "list"])
        assert result.exit_code == 0
        assert "No assets found" in result.output

    def test_list_assets_api_error(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test that API errors are handled gracefully."""
        patch_keyring(monkeypatch)

        def mock_request(
            method: str,
            url: str,
            payload: Optional[Dict[str, Any]] = None,
            **_: Any,
        ) -> Any:
            raise Exception("Network connection failed")

        monkeypatch.setattr("slcli.asset_click.make_api_request", mock_request)
        monkeypatch.setattr("slcli.asset_click.get_workspace_map", lambda: {})

        cli = make_cli()
        result = runner.invoke(cli, ["asset", "list"])
        assert result.exit_code != 0


# =============================================================================
# asset get command tests
# =============================================================================


class TestGetAsset:
    """Tests for the asset get command."""

    def test_get_asset_table(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test getting asset details in table format."""
        patch_keyring(monkeypatch)

        def mock_request(
            method: str,
            url: str,
            payload: Optional[Dict[str, Any]] = None,
            **_: Any,
        ) -> Any:
            return MockResponse(SAMPLE_ASSET)

        monkeypatch.setattr("slcli.asset_click.make_api_request", mock_request)
        monkeypatch.setattr("slcli.asset_click.get_workspace_map", lambda: {"ws-1": "Dev"})

        cli = make_cli()
        result = runner.invoke(cli, ["asset", "get", "asset-1"])
        assert result.exit_code == 0
        assert "NI PXIe-6368" in result.output
        assert "01BB877A" in result.output
        assert "PCI_PXI" in result.output
        assert "Keyword1" in result.output
        assert "Key1: Value1" in result.output

    def test_get_asset_json(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test getting asset details in JSON format."""
        patch_keyring(monkeypatch)

        def mock_request(
            method: str,
            url: str,
            payload: Optional[Dict[str, Any]] = None,
            **_: Any,
        ) -> Any:
            return MockResponse(SAMPLE_ASSET)

        monkeypatch.setattr("slcli.asset_click.make_api_request", mock_request)
        monkeypatch.setattr("slcli.asset_click.get_workspace_map", lambda: {"ws-1": "Dev"})

        cli = make_cli()
        result = runner.invoke(cli, ["asset", "get", "asset-1", "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["id"] == "asset-1"

    def test_get_asset_with_calibration(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test --include-calibration fetches calibration history."""
        patch_keyring(monkeypatch)

        def mock_request(
            method: str,
            url: str,
            payload: Optional[Dict[str, Any]] = None,
            **_: Any,
        ) -> Any:
            if "calibration" in url:
                return MockResponse(
                    {
                        "calibrationHistory": [
                            {"date": "2025-06-15", "entryType": "AUTOMATIC"},
                        ]
                    }
                )
            return MockResponse(SAMPLE_ASSET)

        monkeypatch.setattr("slcli.asset_click.make_api_request", mock_request)
        monkeypatch.setattr("slcli.asset_click.get_workspace_map", lambda: {"ws-1": "Dev"})

        cli = make_cli()
        result = runner.invoke(cli, ["asset", "get", "asset-1", "--include-calibration"])
        assert result.exit_code == 0
        assert "Calibration History:" in result.output
        assert "2025-06-15" in result.output

    def test_get_asset_not_found(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test error handling for non-existent asset."""
        patch_keyring(monkeypatch)

        def mock_request(
            method: str,
            url: str,
            payload: Optional[Dict[str, Any]] = None,
            **_: Any,
        ) -> Any:
            raise Exception("Resource not found: asset-999")

        monkeypatch.setattr("slcli.asset_click.make_api_request", mock_request)

        cli = make_cli()
        result = runner.invoke(cli, ["asset", "get", "asset-999"])
        assert result.exit_code != 0
        assert "not found" in result.output.lower()


# =============================================================================
# asset summary command tests
# =============================================================================


class TestAssetSummary:
    """Tests for the asset summary command."""

    def test_summary_table(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test summary in table format."""
        patch_keyring(monkeypatch)

        summary_data: Dict[str, Any] = {
            "total": 17,
            "active": 12,
            "notActive": 5,
            "inUse": 10,
            "notInUse": 7,
            "withAlarms": 3,
            "approachingRecommendedDueDate": 3,
            "pastRecommendedDueDate": 4,
            "outForCalibration": 2,
            "totalCalibrated": 7,
        }

        def mock_request(
            method: str,
            url: str,
            payload: Optional[Dict[str, Any]] = None,
            **_: Any,
        ) -> Any:
            return MockResponse(summary_data)

        monkeypatch.setattr("slcli.asset_click.make_api_request", mock_request)

        cli = make_cli()
        result = runner.invoke(cli, ["asset", "summary"])
        assert result.exit_code == 0
        assert "Total Assets: 17" in result.output
        assert "Active (in connected system): 12" in result.output
        assert "Not Active: 5" in result.output
        assert "In Use: 10" in result.output
        assert "With Alarms: 3" in result.output
        assert "Approaching Due Date: 3" in result.output
        assert "Past Due Date: 4" in result.output
        assert "Out for Calibration: 2" in result.output

    def test_summary_json(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test summary in JSON format."""
        patch_keyring(monkeypatch)

        summary_data: Dict[str, Any] = {
            "total": 17,
            "active": 12,
            "notActive": 5,
        }

        def mock_request(
            method: str,
            url: str,
            payload: Optional[Dict[str, Any]] = None,
            **_: Any,
        ) -> Any:
            return MockResponse(summary_data)

        monkeypatch.setattr("slcli.asset_click.make_api_request", mock_request)

        cli = make_cli()
        result = runner.invoke(cli, ["asset", "summary", "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["total"] == 17

    def test_summary_api_error(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test error handling for summary endpoint."""
        patch_keyring(monkeypatch)

        def mock_request(
            method: str,
            url: str,
            payload: Optional[Dict[str, Any]] = None,
            **_: Any,
        ) -> Any:
            raise Exception("Permission denied")

        monkeypatch.setattr("slcli.asset_click.make_api_request", mock_request)

        cli = make_cli()
        result = runner.invoke(cli, ["asset", "summary"])
        assert result.exit_code != 0


# =============================================================================
# asset calibration command tests
# =============================================================================


class TestAssetCalibration:
    """Tests for the asset calibration command."""

    def test_calibration_table(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test calibration history in table format."""
        patch_keyring(monkeypatch)

        cal_data: Dict[str, Any] = {
            "calibrationHistory": [
                {
                    "date": "2025-06-15T10:00:00Z",
                    "entryType": "AUTOMATIC",
                    "isLimited": False,
                    "resolvedDueDate": "2026-06-15T00:00:00Z",
                    "recommendedInterval": 12,
                    "comments": "Passed all checks",
                },
            ],
            "totalCount": 1,
        }

        def mock_request(
            method: str,
            url: str,
            payload: Optional[Dict[str, Any]] = None,
            **_: Any,
        ) -> Any:
            return MockResponse(cal_data)

        monkeypatch.setattr("slcli.asset_click.make_api_request", mock_request)

        cli = make_cli()
        result = runner.invoke(cli, ["asset", "calibration", "asset-1"])
        assert result.exit_code == 0
        assert "AUTOMATIC" in result.output

    def test_calibration_json(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test calibration history in JSON format."""
        patch_keyring(monkeypatch)

        cal_data: Dict[str, Any] = {
            "calibrationHistory": [
                {
                    "date": "2025-06-15",
                    "entryType": "MANUAL",
                    "isLimited": True,
                },
            ],
        }

        def mock_request(
            method: str,
            url: str,
            payload: Optional[Dict[str, Any]] = None,
            **_: Any,
        ) -> Any:
            return MockResponse(cal_data)

        monkeypatch.setattr("slcli.asset_click.make_api_request", mock_request)

        cli = make_cli()
        result = runner.invoke(cli, ["asset", "calibration", "asset-1", "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["entryType"] == "MANUAL"

    def test_calibration_empty(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test empty calibration history."""
        patch_keyring(monkeypatch)

        def mock_request(
            method: str,
            url: str,
            payload: Optional[Dict[str, Any]] = None,
            **_: Any,
        ) -> Any:
            return MockResponse({"calibrationHistory": []})

        monkeypatch.setattr("slcli.asset_click.make_api_request", mock_request)

        cli = make_cli()
        result = runner.invoke(cli, ["asset", "calibration", "asset-1"])
        assert result.exit_code == 0
        assert "No calibration history found" in result.output


# =============================================================================
# asset location-history command tests
# =============================================================================


class TestAssetLocationHistory:
    """Tests for the asset location-history command."""

    def test_location_history_table(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test location history in table format."""
        patch_keyring(monkeypatch)

        loc_data: Dict[str, Any] = {
            "connectionHistory": [
                {
                    "timestamp": "2025-12-01T10:30:00Z",
                    "minionId": "controller-1",
                    "slotNumber": 2,
                    "systemConnection": "CONNECTED",
                    "assetPresence": "PRESENT",
                },
            ],
        }

        def mock_request(
            method: str,
            url: str,
            payload: Optional[Dict[str, Any]] = None,
            **_: Any,
        ) -> Any:
            return MockResponse(loc_data)

        monkeypatch.setattr("slcli.asset_click.make_api_request", mock_request)

        cli = make_cli()
        result = runner.invoke(cli, ["asset", "location-history", "asset-1"])
        assert result.exit_code == 0
        assert "controller-1" in result.output
        assert "CONNECTED" in result.output

    def test_location_history_json(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test location history in JSON format."""
        patch_keyring(monkeypatch)

        loc_data: Dict[str, Any] = {
            "connectionHistory": [
                {
                    "timestamp": "2025-12-01T10:30:00Z",
                    "minionId": "ctrl-1",
                    "slotNumber": 3,
                    "systemConnection": "CONNECTED",
                    "assetPresence": "PRESENT",
                },
            ],
        }

        def mock_request(
            method: str,
            url: str,
            payload: Optional[Dict[str, Any]] = None,
            **_: Any,
        ) -> Any:
            return MockResponse(loc_data)

        monkeypatch.setattr("slcli.asset_click.make_api_request", mock_request)

        cli = make_cli()
        result = runner.invoke(cli, ["asset", "location-history", "asset-1", "--format", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["minionId"] == "ctrl-1"

    def test_location_history_with_date_range(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test --from and --to date range options."""
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
            return MockResponse({"connectionHistory": []})

        monkeypatch.setattr("slcli.asset_click.make_api_request", mock_request)

        cli = make_cli()
        result = runner.invoke(
            cli,
            [
                "asset",
                "location-history",
                "asset-1",
                "--from",
                "2025-12-01T00:00:00Z",
                "--to",
                "2025-12-02T00:00:00Z",
            ],
        )
        assert result.exit_code == 0
        assert any(
            p.get("startTimestamp") == "2025-12-01T00:00:00Z"
            and p.get("endTimestamp") == "2025-12-02T00:00:00Z"
            for p in captured_payloads
        )

    def test_location_history_empty(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test empty location history."""
        patch_keyring(monkeypatch)

        def mock_request(
            method: str,
            url: str,
            payload: Optional[Dict[str, Any]] = None,
            **_: Any,
        ) -> Any:
            return MockResponse({"connectionHistory": []})

        monkeypatch.setattr("slcli.asset_click.make_api_request", mock_request)

        cli = make_cli()
        result = runner.invoke(cli, ["asset", "location-history", "asset-1"])
        assert result.exit_code == 0
        assert "No location history found" in result.output


# =============================================================================
# asset create command tests
# =============================================================================


class TestCreateAsset:
    """Tests for the asset create command."""

    def test_create_asset_success(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test creating an asset successfully."""
        patch_keyring(monkeypatch)

        captured_payloads: List[Any] = []

        def mock_request(
            method: str,
            url: str,
            payload: Any = None,
            **_: Any,
        ) -> Any:
            if payload:
                captured_payloads.append(payload)
            return MockResponse([{"id": "new-asset-1", "modelName": "PXI-4071"}])

        monkeypatch.setattr("slcli.asset_click.make_api_request", mock_request)
        monkeypatch.setattr("slcli.asset_click.get_workspace_map", lambda: {})
        monkeypatch.setattr("slcli.profiles.is_active_profile_readonly", lambda: False)

        cli = make_cli()
        result = runner.invoke(
            cli,
            [
                "asset",
                "create",
                "--model-name",
                "PXI-4071",
                "--serial-number",
                "SN-123",
                "--bus-type",
                "PCI_PXI",
            ],
        )
        assert result.exit_code == 0
        assert "✓" in result.output
        assert captured_payloads
        created = captured_payloads[0]
        assert isinstance(created, dict)
        assert created["assets"][0]["modelName"] == "PXI-4071"
        assert created["assets"][0]["serialNumber"] == "SN-123"
        assert created["assets"][0]["busType"] == "PCI_PXI"

    def test_create_asset_json_output(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test create with JSON output."""
        patch_keyring(monkeypatch)

        def mock_request(
            method: str,
            url: str,
            payload: Any = None,
            **_: Any,
        ) -> Any:
            return MockResponse([{"id": "new-1", "modelName": "DMM"}])

        monkeypatch.setattr("slcli.asset_click.make_api_request", mock_request)
        monkeypatch.setattr("slcli.asset_click.get_workspace_map", lambda: {})
        monkeypatch.setattr("slcli.profiles.is_active_profile_readonly", lambda: False)

        cli = make_cli()
        result = runner.invoke(
            cli,
            ["asset", "create", "--model-name", "DMM", "--format", "json"],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data[0]["id"] == "new-1"

    def test_create_asset_with_keywords_and_properties(
        self, monkeypatch: Any, runner: CliRunner
    ) -> None:
        """Test creating asset with keywords and properties."""
        patch_keyring(monkeypatch)

        captured_payloads: List[Any] = []

        def mock_request(
            method: str,
            url: str,
            payload: Any = None,
            **_: Any,
        ) -> Any:
            if payload:
                captured_payloads.append(payload)
            return MockResponse([{"id": "new-2"}])

        monkeypatch.setattr("slcli.asset_click.make_api_request", mock_request)
        monkeypatch.setattr("slcli.asset_click.get_workspace_map", lambda: {})
        monkeypatch.setattr("slcli.profiles.is_active_profile_readonly", lambda: False)

        cli = make_cli()
        result = runner.invoke(
            cli,
            [
                "asset",
                "create",
                "--model-name",
                "Test",
                "--keyword",
                "tag1",
                "--keyword",
                "tag2",
                "--property",
                "location=Lab A",
                "--property",
                "owner=Team1",
            ],
        )
        assert result.exit_code == 0
        assert captured_payloads
        created = captured_payloads[0]["assets"][0]
        assert created["keywords"] == ["tag1", "tag2"]
        assert created["properties"]["location"] == "Lab A"

    def test_create_asset_invalid_property(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test creating asset with invalid property format."""
        patch_keyring(monkeypatch)
        monkeypatch.setattr("slcli.asset_click.get_workspace_map", lambda: {})
        monkeypatch.setattr("slcli.profiles.is_active_profile_readonly", lambda: False)

        cli = make_cli()
        result = runner.invoke(
            cli,
            [
                "asset",
                "create",
                "--model-name",
                "Test",
                "--property",
                "badformat",
            ],
        )
        assert result.exit_code != 0
        assert "Invalid property format" in result.output

    def test_create_asset_readonly_blocked(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test that create is blocked in readonly mode."""
        patch_keyring(monkeypatch)
        monkeypatch.setattr("slcli.profiles.is_active_profile_readonly", lambda: True)

        cli = make_cli()
        result = runner.invoke(cli, ["asset", "create", "--model-name", "Test"])
        assert result.exit_code != 0
        assert "readonly" in result.output.lower()


# =============================================================================
# asset update command tests
# =============================================================================


class TestUpdateAsset:
    """Tests for the asset update command."""

    def test_update_asset_success(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test updating an asset successfully."""
        patch_keyring(monkeypatch)

        captured_payloads: List[Any] = []

        def mock_request(
            method: str,
            url: str,
            payload: Any = None,
            **_: Any,
        ) -> Any:
            if payload:
                captured_payloads.append(payload)
            return MockResponse({})

        monkeypatch.setattr("slcli.asset_click.make_api_request", mock_request)
        monkeypatch.setattr("slcli.profiles.is_active_profile_readonly", lambda: False)

        cli = make_cli()
        result = runner.invoke(
            cli,
            [
                "asset",
                "update",
                "asset-1",
                "--name",
                "New Name",
                "--serial-number",
                "SN-999",
            ],
        )
        assert result.exit_code == 0
        assert "✓" in result.output
        assert captured_payloads
        updated = captured_payloads[0]["assets"][0]
        assert updated["id"] == "asset-1"
        assert updated["name"] == "New Name"
        assert updated["serialNumber"] == "SN-999"

    def test_update_asset_json_output(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test update with JSON output."""
        patch_keyring(monkeypatch)

        def mock_request(
            method: str,
            url: str,
            payload: Any = None,
            **_: Any,
        ) -> Any:
            return MockResponse({"updated": True})

        monkeypatch.setattr("slcli.asset_click.make_api_request", mock_request)
        monkeypatch.setattr("slcli.profiles.is_active_profile_readonly", lambda: False)

        cli = make_cli()
        result = runner.invoke(
            cli,
            [
                "asset",
                "update",
                "asset-1",
                "--name",
                "Updated",
                "--format",
                "json",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["updated"] is True

    def test_update_asset_readonly_blocked(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test that update is blocked in readonly mode."""
        patch_keyring(monkeypatch)
        monkeypatch.setattr("slcli.profiles.is_active_profile_readonly", lambda: True)

        cli = make_cli()
        result = runner.invoke(cli, ["asset", "update", "asset-1", "--name", "X"])
        assert result.exit_code != 0
        assert "readonly" in result.output.lower()


# =============================================================================
# asset delete command tests
# =============================================================================


class TestDeleteAsset:
    """Tests for the asset delete command."""

    def test_delete_asset_with_force(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test deleting an asset with --force."""
        patch_keyring(monkeypatch)

        captured_payloads: List[Any] = []

        def mock_request(
            method: str,
            url: str,
            payload: Any = None,
            **_: Any,
        ) -> Any:
            if payload:
                captured_payloads.append(payload)
            if "/assets/" in url and "delete" not in url:
                return MockResponse(SAMPLE_ASSET)
            return MockResponse({})

        monkeypatch.setattr("slcli.asset_click.make_api_request", mock_request)
        monkeypatch.setattr("slcli.profiles.is_active_profile_readonly", lambda: False)

        cli = make_cli()
        result = runner.invoke(cli, ["asset", "delete", "asset-1", "--force"])
        assert result.exit_code == 0
        assert "✓" in result.output
        assert any(isinstance(p, dict) and p.get("ids") == ["asset-1"] for p in captured_payloads)

    def test_delete_asset_cancelled(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test that delete is cancelled when user says no."""
        patch_keyring(monkeypatch)

        def mock_request(
            method: str,
            url: str,
            payload: Any = None,
            **_: Any,
        ) -> Any:
            return MockResponse(SAMPLE_ASSET)

        monkeypatch.setattr("slcli.asset_click.make_api_request", mock_request)
        monkeypatch.setattr("slcli.profiles.is_active_profile_readonly", lambda: False)

        cli = make_cli()
        result = runner.invoke(cli, ["asset", "delete", "asset-1"], input="n\n")
        assert "cancelled" in result.output.lower()

    def test_delete_asset_readonly_blocked(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test that delete is blocked in readonly mode."""
        patch_keyring(monkeypatch)
        monkeypatch.setattr("slcli.profiles.is_active_profile_readonly", lambda: True)

        cli = make_cli()
        result = runner.invoke(cli, ["asset", "delete", "asset-1", "--force"])
        assert result.exit_code != 0
        assert "readonly" in result.output.lower()
