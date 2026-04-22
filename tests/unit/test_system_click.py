"""Unit tests for system CLI commands."""

import json
from typing import Any, Dict, List
from unittest.mock import patch

import click
import pytest
from click.testing import CliRunner
from slcli.system_click import (
    _LIST_PROJECTION,
    _SLIM_LIST_PROJECTION,
    _build_job_filter,
    _build_system_filter,
    _calculate_column_widths,
    _calculate_job_column_widths,
    _compare_assets,
    _compare_packages,
    _escape_filter_value,
    _fetch_alarms_for_system,
    _fetch_assets_for_system,
    _fetch_recent_jobs_for_system,
    _fetch_results_for_system,
    _fetch_workitems_for_system,
    _filter_by_package,
    _get_packages,
    _get_system_grains,
    _get_system_state,
    _parse_properties,
    _parse_systems_response,
    _query_all_items,
    register_system_commands,
)
from slcli.system_query_utils import build_materialized_system_search_filter
from slcli.utils import ExitCodes


def patch_keyring(monkeypatch: Any) -> None:
    """Patch keyring to return test values."""
    monkeypatch.setattr(
        "slcli.utils.keyring.get_password",
        lambda service, key: ("test-key" if key == "SYSTEMLINK_API_KEY" else "https://test.com"),
    )


def make_cli() -> click.Group:
    """Create CLI instance with system commands for testing."""

    @click.group()
    def test_cli() -> None:
        pass

    register_system_commands(test_cli)
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
        self.content = b""

    def json(self) -> Any:
        """Return the JSON data."""
        return self._json_data

    def raise_for_status(self) -> None:
        """Raise on HTTP error status."""
        if self.status_code >= 400:
            import requests

            resp = requests.models.Response()
            resp.status_code = self.status_code
            raise requests.HTTPError(f"HTTP error {self.status_code}", response=resp)


SAMPLE_SYSTEM: Dict[str, Any] = {
    "id": "minion-PXI-1234",
    "alias": "PXI Controller A",
    "workspace": "ws-1",
    "scanCode": "",
    "createdTimestamp": "2024-01-15T10:30:00Z",
    "lastUpdatedTimestamp": "2024-01-20T14:00:00Z",
    "connected": {
        "data": {
            "state": "CONNECTED",
        },
        "lastPresentTimestamp": "2024-01-20T14:00:00Z",
    },
    "grains": {
        "data": {
            "kernel": "Windows",
            "osversion": "10.0.19045",
            "host": "DESKTOP-PXI1234",
            "cpuarch": "x86_64",
            "deviceclass": "Desktop",
        },
    },
    "keywords": {
        "data": ["production", "lab-A"],
    },
    "properties": {
        "data": {
            "Location": "Building 5",
            "Owner": "Team Alpha",
        },
    },
    "packages": {
        "data": {
            "ni-daqmx": {
                "displayname": "NI-DAQmx",
                "displayversion": "2024Q1",
                "version": "24.1.0",
                "group": "NI",
                "arch": "x64",
            },
            "ni-visa": {
                "displayname": "NI-VISA",
                "displayversion": "2024Q1",
                "version": "24.1.0",
                "group": "NI",
                "arch": "x64",
            },
        },
    },
    "feeds": {
        "data": {
            "https://feeds.example.com": [
                {
                    "name": "Main Feed",
                    "enabled": True,
                    "uri": "https://feeds.example.com/main",
                },
            ],
        },
    },
}

SAMPLE_SYSTEM_2: Dict[str, Any] = {
    "id": "minion-RT-5678",
    "alias": "cRIO Controller B",
    "workspace": "ws-2",
    "createdTimestamp": "2024-02-01T09:00:00Z",
    "lastUpdatedTimestamp": "2024-02-10T11:00:00Z",
    "connected": {
        "data": {
            "state": "DISCONNECTED",
        },
    },
    "grains": {
        "data": {
            "kernel": "Linux",
            "osversion": "4.14",
            "host": "crio-5678",
            "cpuarch": "armv7l",
            "deviceclass": "Embedded",
        },
    },
    "keywords": {
        "data": [],
    },
    "properties": {
        "data": {},
    },
}

SAMPLE_JOB: Dict[str, Any] = {
    "jid": "20240120140000123456",
    "id": "minion-PXI-1234",
    "state": "SUCCEEDED",
    "createdTimestamp": "2024-01-20T14:00:00Z",
    "lastUpdatedTimestamp": "2024-01-20T14:01:00Z",
    "dispatchedTimestamp": "2024-01-20T14:00:01Z",
    "config": {
        "tgt": ["minion-PXI-1234"],
        "fun": ["pkg.install"],
    },
    "result": {
        "retcode": [0],
        "return": ["Package installed successfully"],
        "success": [True],
    },
}


# =============================================================================
# Helper function tests
# =============================================================================


class TestEscapeFilterValue:
    """Tests for _escape_filter_value helper."""

    def test_no_special_chars(self) -> None:
        """Test passthrough when no special characters."""
        assert _escape_filter_value("simple") == "simple"

    def test_escape_double_quotes(self) -> None:
        """Test double quote escaping."""
        assert _escape_filter_value('val"ue') == 'val\\"ue'

    def test_empty_string(self) -> None:
        """Test empty string passthrough."""
        assert _escape_filter_value("") == ""


class TestParseProperties:
    """Tests for _parse_properties helper."""

    def test_single_property(self) -> None:
        """Test parsing a single property."""
        result = _parse_properties(("key=value",))
        assert result == {"key": "value"}

    def test_multiple_properties(self) -> None:
        """Test parsing multiple properties."""
        result = _parse_properties(("key1=val1", "key2=val2"))
        assert result == {"key1": "val1", "key2": "val2"}

    def test_value_with_equals(self) -> None:
        """Test property where value contains '='."""
        result = _parse_properties(("key=val=ue",))
        assert result == {"key": "val=ue"}

    def test_invalid_format_exits(self) -> None:
        """Test that invalid format causes sys.exit."""
        with pytest.raises(SystemExit):
            _parse_properties(("no_equals_sign",))


class TestGetSystemState:
    """Tests for _get_system_state helper."""

    def test_connected_state(self) -> None:
        """Test extracting CONNECTED state."""
        assert _get_system_state(SAMPLE_SYSTEM) == "CONNECTED"

    def test_disconnected_state(self) -> None:
        """Test extracting DISCONNECTED state."""
        assert _get_system_state(SAMPLE_SYSTEM_2) == "DISCONNECTED"

    def test_missing_connected(self) -> None:
        """Test missing connected field returns UNKNOWN."""
        assert _get_system_state({}) == "UNKNOWN"

    def test_missing_data(self) -> None:
        """Test missing data field returns UNKNOWN."""
        assert _get_system_state({"connected": {}}) == "UNKNOWN"

    def test_missing_state(self) -> None:
        """Test missing state field returns UNKNOWN."""
        assert _get_system_state({"connected": {"data": {}}}) == "UNKNOWN"


class TestGetSystemGrains:
    """Tests for _get_system_grains helper."""

    def test_has_grains(self) -> None:
        """Test extracting grains from a system."""
        grains = _get_system_grains(SAMPLE_SYSTEM)
        assert grains["kernel"] == "Windows"
        assert grains["host"] == "DESKTOP-PXI1234"

    def test_missing_grains(self) -> None:
        """Test missing grains returns empty dict."""
        assert _get_system_grains({}) == {}

    def test_missing_grains_data(self) -> None:
        """Test missing grains data returns empty dict."""
        assert _get_system_grains({"grains": {}}) == {}


class TestFilterByPackage:
    """Tests for _filter_by_package helper."""

    def test_exact_match(self) -> None:
        """Test exact package name match."""
        result = _filter_by_package([SAMPLE_SYSTEM], "ni-daqmx")
        assert len(result) == 1

    def test_contains_match(self) -> None:
        """Test contains match (case-insensitive)."""
        result = _filter_by_package([SAMPLE_SYSTEM], "daqmx")
        assert len(result) == 1

    def test_case_insensitive(self) -> None:
        """Test case-insensitive matching."""
        result = _filter_by_package([SAMPLE_SYSTEM], "NI-DAQMX")
        assert len(result) == 1

    def test_no_match(self) -> None:
        """Test no matching package returns empty."""
        result = _filter_by_package([SAMPLE_SYSTEM], "nonexistent-pkg")
        assert len(result) == 0

    def test_system_without_packages(self) -> None:
        """Test system with no package data."""
        result = _filter_by_package([SAMPLE_SYSTEM_2], "ni-daqmx")
        assert len(result) == 0

    def test_mixed_results(self) -> None:
        """Test filtering a mix of systems."""
        result = _filter_by_package([SAMPLE_SYSTEM, SAMPLE_SYSTEM_2], "ni-daqmx")
        assert len(result) == 1
        assert result[0]["id"] == "minion-PXI-1234"


class TestBuildSystemFilter:
    """Tests for _build_system_filter helper."""

    def test_no_filters(self) -> None:
        """Test no filters returns None."""
        assert _build_system_filter() is None

    def test_alias_filter(self) -> None:
        """Test alias filter uses Contains."""
        result = _build_system_filter(alias="PXI")
        assert result == 'alias.Contains("PXI")'

    def test_state_filter(self) -> None:
        """Test state filter uses exact match."""
        result = _build_system_filter(state="CONNECTED")
        assert result == 'connected.data.state = "CONNECTED"'

    def test_os_filter(self) -> None:
        """Test OS filter uses kernel Contains."""
        result = _build_system_filter(os_filter="Windows")
        assert result == 'grains.data.kernel.Contains("Windows")'

    def test_host_filter(self) -> None:
        """Test host filter uses Contains."""
        result = _build_system_filter(host="PXI")
        assert result == 'grains.data.host.Contains("PXI")'

    def test_keyword_filter(self) -> None:
        """Test keyword filter uses Contains."""
        result = _build_system_filter(has_keyword=("production",))
        assert result == 'keywords.data.Contains("production")'

    def test_multiple_keywords(self) -> None:
        """Test multiple keywords joined with and."""
        result = _build_system_filter(has_keyword=("production", "lab-A"))
        assert result is not None
        assert 'keywords.data.Contains("production")' in result
        assert 'keywords.data.Contains("lab-A")' in result
        assert " and " in result

    def test_property_filter(self) -> None:
        """Test property filter uses exact match."""
        result = _build_system_filter(property_filters=("Location=Building 5",))
        assert result == 'properties.data.Location = "Building 5"'

    def test_property_filter_missing_equals(self) -> None:
        """Test property filter without '=' raises SystemExit."""
        with pytest.raises(SystemExit):
            _build_system_filter(property_filters=("InvalidProp",))

    def test_property_filter_invalid_key(self) -> None:
        """Test property filter with unsafe key raises SystemExit."""
        with pytest.raises(SystemExit):
            _build_system_filter(property_filters=('"; DROP TABLE--=bad',))

    def test_materialized_property_filter_invalid_key(self) -> None:
        """Test materialized property filter shares the same key validation."""
        with pytest.raises(SystemExit):
            build_materialized_system_search_filter(property_filters=('"; DROP TABLE--=bad',))

    def test_workspace_filter(self) -> None:
        """Test workspace filter."""
        result = _build_system_filter(workspace_id="ws-1")
        assert result == 'workspace = "ws-1"'

    def test_custom_filter(self) -> None:
        """Test custom filter passed through."""
        result = _build_system_filter(custom_filter='grains.data.kernel = "Linux"')
        assert result == 'grains.data.kernel = "Linux"'

    def test_combined_filters(self) -> None:
        """Test multiple filters combined with and."""
        result = _build_system_filter(alias="PXI", state="CONNECTED")
        assert result is not None
        assert 'alias.Contains("PXI")' in result
        assert 'connected.data.state = "CONNECTED"' in result
        assert " and " in result

    def test_filter_value_escaping(self) -> None:
        """Test filter values with quotes are escaped."""
        result = _build_system_filter(alias='PXI"test')
        assert result == 'alias.Contains("PXI\\"test")'


class TestBuildJobFilter:
    """Tests for _build_job_filter helper."""

    def test_no_filters(self) -> None:
        """Test no filters returns None."""
        assert _build_job_filter() is None

    def test_system_id_filter(self) -> None:
        """Test system ID filter uses exact match."""
        result = _build_job_filter(system_id="minion-PXI-1234")
        assert result == 'id = "minion-PXI-1234"'

    def test_state_filter(self) -> None:
        """Test state filter uses exact match."""
        result = _build_job_filter(state="SUCCEEDED")
        assert result == 'state = "SUCCEEDED"'

    def test_function_filter(self) -> None:
        """Test function filter uses Contains."""
        result = _build_job_filter(function="pkg.install")
        assert result == 'config.fun.Contains("pkg.install")'

    def test_combined_filters(self) -> None:
        """Test multiple filters combined with and."""
        result = _build_job_filter(state="FAILED", function="pkg")
        assert result is not None
        assert 'state = "FAILED"' in result
        assert 'config.fun.Contains("pkg")' in result
        assert " and " in result


class TestCalculateColumnWidths:
    """Tests for _calculate_column_widths helper."""

    def test_returns_six_columns(self) -> None:
        """Test that six column widths are returned."""
        widths = _calculate_column_widths()
        assert len(widths) == 6

    def test_fixed_columns_have_expected_widths(self) -> None:
        """Test that fixed columns have their expected widths."""
        widths = _calculate_column_widths()
        # Alias, Host, State, OS, Workspace are fixed
        assert widths[0] == 24  # Alias
        assert widths[1] == 18  # Host
        assert widths[2] == 14  # State
        assert widths[3] == 10  # OS
        assert widths[4] == 16  # Workspace

    def test_id_column_has_minimum_width(self) -> None:
        """Test that ID column has at least minimum width."""
        widths = _calculate_column_widths()
        assert widths[5] >= 20


class TestListProjection:
    """Tests for projection constant."""

    def test_projection_includes_required_fields(self) -> None:
        """Test that projection includes all fields needed for display."""
        assert "id" in _LIST_PROJECTION
        assert "alias" in _LIST_PROJECTION
        assert "workspace" in _LIST_PROJECTION
        assert "connected" in _LIST_PROJECTION
        assert "state" in _LIST_PROJECTION
        assert "grains" in _LIST_PROJECTION
        assert "kernel" in _LIST_PROJECTION
        assert "host" in _LIST_PROJECTION
        assert "keywords" in _LIST_PROJECTION
        assert "packages" in _LIST_PROJECTION


# =============================================================================
# Query helper tests
# =============================================================================


class TestQueryAllItems:
    """Tests for _query_all_items pagination helper."""

    _URL = "https://test.com/nisysmgmt/v1/query-systems"

    def test_single_page(self, monkeypatch: Any) -> None:
        """Test fetching systems that fit in one page."""
        patch_keyring(monkeypatch)

        systems = [SAMPLE_SYSTEM, SAMPLE_SYSTEM_2]

        def mock_post(*a: Any, **kw: Any) -> Any:
            return MockResponse({"data": systems, "count": 2})

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_post)

        result = _query_all_items(self._URL, None, None, _parse_systems_response, take=100)
        assert len(result) == 2
        assert result[0]["id"] == "minion-PXI-1234"

    def test_empty_results(self, monkeypatch: Any) -> None:
        """Test empty response returns empty list."""
        patch_keyring(monkeypatch)

        def mock_post(*a: Any, **kw: Any) -> Any:
            return MockResponse({"data": [], "count": 0})

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_post)

        result = _query_all_items(self._URL, None, None, _parse_systems_response)
        assert result == []

    def test_with_filter(self, monkeypatch: Any) -> None:
        """Test that filter is passed to API."""
        patch_keyring(monkeypatch)
        captured_payloads: List[Dict[str, Any]] = []

        def mock_post(*a: Any, **kw: Any) -> Any:
            captured_payloads.append(kw.get("payload", {}))
            return MockResponse({"data": [SAMPLE_SYSTEM], "count": 1})

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_post)

        _query_all_items(
            self._URL,
            'connected.data.state = "CONNECTED"',
            None,
            _parse_systems_response,
            take=100,
        )
        assert captured_payloads[0]["filter"] == 'connected.data.state = "CONNECTED"'

    def test_respects_take_limit(self, monkeypatch: Any) -> None:
        """Test that take limit is respected."""
        patch_keyring(monkeypatch)

        systems = [SAMPLE_SYSTEM] * 50

        def mock_post(*a: Any, **kw: Any) -> Any:
            return MockResponse({"data": systems, "count": 100})

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_post)

        result = _query_all_items(self._URL, None, None, _parse_systems_response, take=10)
        assert len(result) == 10

    def test_list_response_format(self, monkeypatch: Any) -> None:
        """Test handling of list response format."""
        patch_keyring(monkeypatch)

        def mock_post(*a: Any, **kw: Any) -> Any:
            return MockResponse(
                [
                    {"data": SAMPLE_SYSTEM, "count": 2},
                    {"data": SAMPLE_SYSTEM_2, "count": 2},
                ]
            )

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_post)

        result = _query_all_items(self._URL, None, None, _parse_systems_response, take=10)
        assert len(result) == 2


# =============================================================================
# Command tests
# =============================================================================


class TestListSystems:
    """Tests for 'system list' command."""

    def test_list_json_default_schema_is_slim(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Default JSON output uses the slim schema from search-systems."""
        patch_keyring(monkeypatch)

        def mock_post(*a: Any, **kw: Any) -> Any:
            return MockResponse(
                {
                    "systems": [
                        {
                            "id": "minion-PXI-1234",
                            "alias": "PXI Controller A",
                            "workspace": "ws-1",
                            "connected": "CONNECTED",
                            "advancedGrains": {
                                "host": "DESKTOP-PXI1234",
                                "os": "Windows",
                            },
                        }
                    ]
                }
            )

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_post)
        monkeypatch.setattr("slcli.system_click.get_workspace_map", lambda: {})

        cli = make_cli()
        result = runner.invoke(cli, ["system", "list", "-f", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data == [
            {
                "id": "minion-PXI-1234",
                "alias": "PXI Controller A",
                "workspace": "ws-1",
                "connected": "CONNECTED",
                "host": "DESKTOP-PXI1234",
                "kernel": "Windows",
            }
        ]

    def test_list_json(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test listing systems in JSON format."""
        patch_keyring(monkeypatch)

        def mock_post(*a: Any, **kw: Any) -> Any:
            return MockResponse({"data": [SAMPLE_SYSTEM, SAMPLE_SYSTEM_2], "count": 2})

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_post)
        monkeypatch.setattr("slcli.system_click.get_workspace_map", lambda: {})

        cli = make_cli()
        result = runner.invoke(cli, ["system", "list", "-f", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 2

    def test_list_table(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test listing systems in table format."""
        patch_keyring(monkeypatch)

        call_count = 0

        def mock_post(*a: Any, **kw: Any) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return MockResponse({"data": [SAMPLE_SYSTEM], "count": 1})
            return MockResponse({"data": [], "count": 0})

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_post)
        monkeypatch.setattr("slcli.system_click.get_workspace_map", lambda: {})

        cli = make_cli()
        result = runner.invoke(cli, ["system", "list", "-f", "table"])
        assert result.exit_code == 0
        assert "PXI Controller A" in result.output
        assert "Showing 1 systems" in result.output

    def test_list_with_alias_filter(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test listing with alias filter."""
        patch_keyring(monkeypatch)
        captured_payloads: List[Dict[str, Any]] = []

        call_count = 0

        def mock_post(*a: Any, **kw: Any) -> Any:
            nonlocal call_count
            call_count += 1
            captured_payloads.append(kw.get("payload", {}))
            if call_count == 1:
                return MockResponse({"data": [SAMPLE_SYSTEM], "count": 1})
            return MockResponse({"data": [], "count": 0})

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_post)
        monkeypatch.setattr("slcli.system_click.get_workspace_map", lambda: {})

        cli = make_cli()
        result = runner.invoke(cli, ["system", "list", "--alias", "PXI"])
        assert result.exit_code == 0
        assert 'alias:"*PXI*"' in captured_payloads[0].get("filter", "")

    def test_list_with_state_filter(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test listing with state filter."""
        patch_keyring(monkeypatch)
        captured_payloads: List[Dict[str, Any]] = []

        def mock_post(*a: Any, **kw: Any) -> Any:
            captured_payloads.append(kw.get("payload", {}))
            return MockResponse({"data": [SAMPLE_SYSTEM], "count": 1})

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_post)
        monkeypatch.setattr("slcli.system_click.get_workspace_map", lambda: {})

        cli = make_cli()
        result = runner.invoke(cli, ["system", "list", "-f", "json", "--state", "CONNECTED"])
        assert result.exit_code == 0
        assert 'connected:"CONNECTED"' in captured_payloads[0].get("filter", "")

    def test_list_with_os_filter(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test listing with OS filter."""
        patch_keyring(monkeypatch)
        captured_payloads: List[Dict[str, Any]] = []

        def mock_post(*a: Any, **kw: Any) -> Any:
            captured_payloads.append(kw.get("payload", {}))
            return MockResponse({"data": [SAMPLE_SYSTEM], "count": 1})

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_post)
        monkeypatch.setattr("slcli.system_click.get_workspace_map", lambda: {})

        cli = make_cli()
        result = runner.invoke(cli, ["system", "list", "-f", "json", "--os", "Windows"])
        assert result.exit_code == 0
        assert (
            '(advancedGrains.os:"*Windows*" OR minionDetails.osFullName:"*Windows*")'
            in captured_payloads[0].get("filter", "")
        )

    def test_list_with_host_filter(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test listing with host filter."""
        patch_keyring(monkeypatch)
        captured_payloads: List[Dict[str, Any]] = []

        def mock_post(*a: Any, **kw: Any) -> Any:
            captured_payloads.append(kw.get("payload", {}))
            return MockResponse({"data": [SAMPLE_SYSTEM], "count": 1})

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_post)
        monkeypatch.setattr("slcli.system_click.get_workspace_map", lambda: {})

        cli = make_cli()
        result = runner.invoke(cli, ["system", "list", "-f", "json", "--host", "PXI"])
        assert result.exit_code == 0
        assert (
            '(advancedGrains.host:"*PXI*" OR minionDetails.localhost:"*PXI*")'
            in captured_payloads[0].get("filter", "")
        )

    def test_list_with_has_package(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test listing with package filter (client-side)."""
        patch_keyring(monkeypatch)

        def mock_post(*a: Any, **kw: Any) -> Any:
            return MockResponse({"data": [SAMPLE_SYSTEM, SAMPLE_SYSTEM_2], "count": 2})

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_post)
        monkeypatch.setattr("slcli.system_click.get_workspace_map", lambda: {})

        cli = make_cli()
        result = runner.invoke(cli, ["system", "list", "-f", "json", "--has-package", "ni-daqmx"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1
        assert data[0]["id"] == "minion-PXI-1234"

    def test_list_with_workspace_filter(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test listing with workspace filter."""
        patch_keyring(monkeypatch)
        captured_payloads: List[Dict[str, Any]] = []

        def mock_post(*a: Any, **kw: Any) -> Any:
            captured_payloads.append(kw.get("payload", {}))
            return MockResponse({"data": [SAMPLE_SYSTEM], "count": 1})

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_post)
        monkeypatch.setattr("slcli.system_click.get_workspace_map", lambda: {"ws-1": "My WS"})

        cli = make_cli()
        result = runner.invoke(cli, ["system", "list", "-f", "json", "--workspace", "ws-1"])
        assert result.exit_code == 0
        assert 'workspace:"ws-1"' in captured_payloads[0].get("filter", "")

    def test_list_empty_json(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test listing when no systems found (JSON)."""
        patch_keyring(monkeypatch)

        def mock_post(*a: Any, **kw: Any) -> Any:
            return MockResponse({"data": [], "count": 0})

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_post)
        monkeypatch.setattr("slcli.system_click.get_workspace_map", lambda: {})

        cli = make_cli()
        result = runner.invoke(cli, ["system", "list", "-f", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data == []

    def test_list_empty_table(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test listing when no systems found (table)."""
        patch_keyring(monkeypatch)

        def mock_post(*a: Any, **kw: Any) -> Any:
            return MockResponse({"data": [], "count": 0})

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_post)
        monkeypatch.setattr("slcli.system_click.get_workspace_map", lambda: {})

        cli = make_cli()
        result = runner.invoke(cli, ["system", "list", "-f", "table"])
        assert result.exit_code == 0
        assert "No systems found" in result.output

    def test_list_api_error(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test list handles API errors gracefully."""
        patch_keyring(monkeypatch)

        def mock_post(*a: Any, **kw: Any) -> Any:
            raise Exception("Connection refused")

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_post)
        monkeypatch.setattr("slcli.system_click.get_workspace_map", lambda: {})

        cli = make_cli()
        result = runner.invoke(cli, ["system", "list", "-f", "json"])
        assert result.exit_code != 0

    def test_list_with_keyword_filter(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test listing with keyword filter."""
        patch_keyring(monkeypatch)
        captured_payloads: List[Dict[str, Any]] = []

        def mock_post(*a: Any, **kw: Any) -> Any:
            captured_payloads.append(kw.get("payload", {}))
            return MockResponse({"data": [SAMPLE_SYSTEM], "count": 1})

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_post)
        monkeypatch.setattr("slcli.system_click.get_workspace_map", lambda: {})

        cli = make_cli()
        result = runner.invoke(cli, ["system", "list", "-f", "json", "--has-keyword", "production"])
        assert result.exit_code == 0
        assert 'keywords:"production"' in captured_payloads[0].get("filter", "")

    def test_list_with_property_filter(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test listing with property filter."""
        patch_keyring(monkeypatch)
        captured_payloads: List[Dict[str, Any]] = []

        def mock_post(*a: Any, **kw: Any) -> Any:
            captured_payloads.append(kw.get("payload", {}))
            return MockResponse({"data": [SAMPLE_SYSTEM], "count": 1})

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_post)
        monkeypatch.setattr("slcli.system_click.get_workspace_map", lambda: {})

        cli = make_cli()
        result = runner.invoke(
            cli,
            [
                "system",
                "list",
                "-f",
                "json",
                "--property",
                "Location=Building 5",
            ],
        )
        assert result.exit_code == 0
        assert 'properties.Location:"Building 5"' in captured_payloads[0].get("filter", "")

    def test_list_with_custom_filter(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test listing with custom filter."""
        patch_keyring(monkeypatch)
        captured_payloads: List[Dict[str, Any]] = []

        def mock_post(*a: Any, **kw: Any) -> Any:
            captured_payloads.append(kw.get("payload", {}))
            return MockResponse({"data": [], "count": 0})

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_post)
        monkeypatch.setattr("slcli.system_click.get_workspace_map", lambda: {})

        cli = make_cli()
        custom = 'grains.data.kernel = "Linux"'
        result = runner.invoke(cli, ["system", "list", "-f", "json", "--filter", custom])
        assert result.exit_code == 0
        assert custom in captured_payloads[0].get("filter", "")

    def test_list_table_sends_projection(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test that table format list sends projection to reduce payload."""
        patch_keyring(monkeypatch)
        captured_payloads: List[Dict[str, Any]] = []

        def mock_post(*a: Any, **kw: Any) -> Any:
            captured_payloads.append(kw.get("payload", {}))
            return MockResponse({"data": [SAMPLE_SYSTEM], "count": 1})

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_post)
        monkeypatch.setattr("slcli.system_click.get_workspace_map", lambda: {})

        cli = make_cli()
        result = runner.invoke(cli, ["system", "list", "-f", "table"])
        assert result.exit_code == 0
        assert "projection" in captured_payloads[0]
        assert "id" in captured_payloads[0]["projection"]

    def test_list_json_sends_projection(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test that JSON format list also sends projection to reduce payload."""
        patch_keyring(monkeypatch)
        captured_payloads: List[Dict[str, Any]] = []

        def mock_post(*a: Any, **kw: Any) -> Any:
            captured_payloads.append(kw.get("payload", {}))
            return MockResponse({"data": [], "count": 0})

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_post)
        monkeypatch.setattr("slcli.system_click.get_workspace_map", lambda: {})

        cli = make_cli()
        result = runner.invoke(cli, ["system", "list", "-f", "json"])
        assert result.exit_code == 0
        assert "projection" in captured_payloads[0]
        assert "id" in captured_payloads[0]["projection"]

    def test_list_json_with_extended_field_uses_query_projection(
        self, monkeypatch: Any, runner: CliRunner
    ) -> None:
        """Requesting an extended JSON field forces the legacy query projection path."""
        patch_keyring(monkeypatch)
        captured_calls: List[Dict[str, Any]] = []
        projected_system = {
            "id": SAMPLE_SYSTEM["id"],
            "alias": SAMPLE_SYSTEM["alias"],
            "workspace": SAMPLE_SYSTEM["workspace"],
            "connected": SAMPLE_SYSTEM["connected"]["data"]["state"],
            "host": SAMPLE_SYSTEM["grains"]["data"]["host"],
            "kernel": SAMPLE_SYSTEM["grains"]["data"]["kernel"],
            "packages": SAMPLE_SYSTEM["packages"]["data"],
        }

        def mock_post(method: str, url: str, **kw: Any) -> Any:
            captured_calls.append({"method": method, "url": url, "payload": kw.get("payload", {})})
            return MockResponse({"data": [projected_system], "count": 1})

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_post)
        monkeypatch.setattr("slcli.system_click.get_workspace_map", lambda: {})

        cli = make_cli()
        result = runner.invoke(cli, ["system", "list", "-f", "json", "--field", "packages"])
        assert result.exit_code == 0
        assert "query-systems" in captured_calls[0]["url"]
        assert "packages.data as packages" in captured_calls[0]["payload"]["projection"]
        data = json.loads(result.output)
        assert "packages" in data[0]
        assert "osversion" not in data[0]

    def test_list_json_with_all_fields_uses_legacy_projection(
        self, monkeypatch: Any, runner: CliRunner
    ) -> None:
        """Requesting all JSON fields restores the full legacy list schema."""
        patch_keyring(monkeypatch)
        captured_calls: List[Dict[str, Any]] = []
        projected_system = {
            "id": SAMPLE_SYSTEM["id"],
            "alias": SAMPLE_SYSTEM["alias"],
            "workspace": SAMPLE_SYSTEM["workspace"],
            "connected": SAMPLE_SYSTEM["connected"]["data"]["state"],
            "host": SAMPLE_SYSTEM["grains"]["data"]["host"],
            "kernel": SAMPLE_SYSTEM["grains"]["data"]["kernel"],
            "osversion": SAMPLE_SYSTEM["grains"]["data"]["osversion"],
            "cpuarch": SAMPLE_SYSTEM["grains"]["data"]["cpuarch"],
            "deviceclass": SAMPLE_SYSTEM["grains"]["data"]["deviceclass"],
            "keywords": SAMPLE_SYSTEM["keywords"]["data"],
            "packages": SAMPLE_SYSTEM["packages"]["data"],
        }

        def mock_post(method: str, url: str, **kw: Any) -> Any:
            captured_calls.append({"method": method, "url": url, "payload": kw.get("payload", {})})
            return MockResponse({"data": [projected_system], "count": 1})

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_post)
        monkeypatch.setattr("slcli.system_click.get_workspace_map", lambda: {})

        cli = make_cli()
        result = runner.invoke(cli, ["system", "list", "-f", "json", "--all-fields"])
        assert result.exit_code == 0
        assert "query-systems" in captured_calls[0]["url"]
        assert captured_calls[0]["payload"]["projection"] == _LIST_PROJECTION
        data = json.loads(result.output)
        assert "packages" in data[0]
        assert "keywords" in data[0]
        assert "osversion" in data[0]

    def test_list_json_materialized_fallback_uses_slim_projection(
        self, monkeypatch: Any, runner: CliRunner
    ) -> None:
        """Default JSON fallback keeps the slim schema on servers without search-systems."""
        import requests

        patch_keyring(monkeypatch)
        captured_calls: List[Dict[str, Any]] = []
        projected_system = {
            "id": SAMPLE_SYSTEM["id"],
            "alias": SAMPLE_SYSTEM["alias"],
            "workspace": SAMPLE_SYSTEM["workspace"],
            "connected": SAMPLE_SYSTEM["connected"]["data"]["state"],
            "host": SAMPLE_SYSTEM["grains"]["data"]["host"],
            "kernel": SAMPLE_SYSTEM["grains"]["data"]["kernel"],
        }

        def mock_post(method: str, url: str, **kw: Any) -> Any:
            captured_calls.append({"method": method, "url": url, "payload": kw.get("payload", {})})
            if "materialized/search-systems" in url:
                response = requests.models.Response()
                response.status_code = 404
                raise requests.HTTPError("not found", response=response)
            return MockResponse({"data": [projected_system], "count": 1})

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_post)
        monkeypatch.setattr("slcli.system_click.get_workspace_map", lambda: {})

        cli = make_cli()
        result = runner.invoke(cli, ["system", "list", "-f", "json"])
        assert result.exit_code == 0
        assert "materialized/search-systems" in captured_calls[0]["url"]
        assert captured_calls[1]["payload"]["projection"] == _SLIM_LIST_PROJECTION
        data = json.loads(result.output)
        assert list(data[0].keys()) == ["id", "alias", "workspace", "connected", "host", "kernel"]

    def test_list_table_materialized_fallback_uses_slim_projection(
        self, monkeypatch: Any, runner: CliRunner
    ) -> None:
        """Table fallback uses the slim legacy projection needed for rendering only."""
        import requests

        patch_keyring(monkeypatch)
        captured_calls: List[Dict[str, Any]] = []
        projected_system = {
            "id": SAMPLE_SYSTEM["id"],
            "alias": SAMPLE_SYSTEM["alias"],
            "workspace": SAMPLE_SYSTEM["workspace"],
            "connected": SAMPLE_SYSTEM["connected"]["data"]["state"],
            "host": SAMPLE_SYSTEM["grains"]["data"]["host"],
            "kernel": SAMPLE_SYSTEM["grains"]["data"]["kernel"],
        }

        def mock_post(method: str, url: str, **kw: Any) -> Any:
            captured_calls.append({"method": method, "url": url, "payload": kw.get("payload", {})})
            if "materialized/search-systems" in url:
                response = requests.models.Response()
                response.status_code = 404
                raise requests.HTTPError("not found", response=response)
            return MockResponse({"data": [projected_system], "count": 1})

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_post)
        monkeypatch.setattr("slcli.system_click.get_workspace_map", lambda: {})

        cli = make_cli()
        result = runner.invoke(cli, ["system", "list", "-f", "table"])
        assert result.exit_code == 0
        assert "materialized/search-systems" in captured_calls[0]["url"]
        assert captured_calls[1]["payload"]["projection"] == _SLIM_LIST_PROJECTION
        assert "PXI Controller A" in result.output

    def test_list_fields_require_json_format(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Extended JSON field selection options are rejected for table output."""
        patch_keyring(monkeypatch)

        cli = make_cli()
        result = runner.invoke(cli, ["system", "list", "--field", "packages"])
        assert result.exit_code == ExitCodes.INVALID_INPUT
        assert "only supported with --format json" in result.output

    def test_list_table_pagination_prompt(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test that table pagination shows more-available prompt when page is full."""
        patch_keyring(monkeypatch)

        call_count = 0

        def mock_post(*a: Any, **kw: Any) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Return exactly take (100) items so pagination triggers
                return MockResponse({"data": [SAMPLE_SYSTEM] * 100})
            return MockResponse({"data": []})

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_post)
        monkeypatch.setattr("slcli.system_click.get_workspace_map", lambda: {})

        cli = make_cli()
        with patch("slcli.system_click.questionary.confirm") as mock_confirm:
            mock_confirm.return_value.ask.return_value = False
            result = runner.invoke(cli, ["system", "list", "-f", "table"])
        assert result.exit_code == 0
        assert "Showing 100 systems" in result.output


class TestGetSystem:
    """Tests for 'system get' command."""

    def test_get_json(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test getting a system in JSON format."""
        patch_keyring(monkeypatch)

        def mock_get(*a: Any, **kw: Any) -> Any:
            return MockResponse([SAMPLE_SYSTEM])

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_get)

        cli = make_cli()
        result = runner.invoke(cli, ["system", "get", "minion-PXI-1234", "-f", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["id"] == "minion-PXI-1234"
        # Packages should be stripped by default for JSON
        assert "packages" not in data

    def test_get_json_include_packages(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test getting a system with packages in JSON format."""
        patch_keyring(monkeypatch)

        def mock_get(*a: Any, **kw: Any) -> Any:
            return MockResponse([SAMPLE_SYSTEM])

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_get)

        cli = make_cli()
        result = runner.invoke(
            cli, ["system", "get", "minion-PXI-1234", "-f", "json", "--include-packages"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "packages" in data

    def test_get_json_include_feeds(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test getting a system with feeds in JSON format."""
        patch_keyring(monkeypatch)

        def mock_get(*a: Any, **kw: Any) -> Any:
            return MockResponse([SAMPLE_SYSTEM])

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_get)

        cli = make_cli()
        result = runner.invoke(
            cli, ["system", "get", "minion-PXI-1234", "-f", "json", "--include-feeds"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "feeds" in data

    def test_get_table(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test getting a system in table format."""
        patch_keyring(monkeypatch)

        def mock_get(*a: Any, **kw: Any) -> Any:
            return MockResponse([SAMPLE_SYSTEM])

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_get)
        monkeypatch.setattr("slcli.system_click.get_workspace_map", lambda: {})

        cli = make_cli()
        result = runner.invoke(cli, ["system", "get", "minion-PXI-1234"])
        assert result.exit_code == 0
        assert "PXI Controller A" in result.output
        assert "CONNECTED" in result.output
        assert "Windows" in result.output

    def test_get_table_with_packages(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test getting a system with packages in table format."""
        patch_keyring(monkeypatch)

        def mock_get(*a: Any, **kw: Any) -> Any:
            return MockResponse([SAMPLE_SYSTEM])

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_get)
        monkeypatch.setattr("slcli.system_click.get_workspace_map", lambda: {})

        cli = make_cli()
        result = runner.invoke(cli, ["system", "get", "minion-PXI-1234", "--include-packages"])
        assert result.exit_code == 0
        assert "Installed Packages" in result.output
        assert "NI-DAQmx" in result.output

    def test_get_table_with_feeds(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test getting a system with feeds in table format."""
        patch_keyring(monkeypatch)

        def mock_get(*a: Any, **kw: Any) -> Any:
            return MockResponse([SAMPLE_SYSTEM])

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_get)
        monkeypatch.setattr("slcli.system_click.get_workspace_map", lambda: {})

        cli = make_cli()
        result = runner.invoke(cli, ["system", "get", "minion-PXI-1234", "--include-feeds"])
        assert result.exit_code == 0
        assert "Configured Feeds" in result.output
        assert "Main Feed" in result.output

    def test_get_not_found(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test getting a nonexistent system."""
        patch_keyring(monkeypatch)

        def mock_get(*a: Any, **kw: Any) -> Any:
            return MockResponse([])

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_get)

        cli = make_cli()
        result = runner.invoke(cli, ["system", "get", "nonexistent"])
        assert result.exit_code != 0
        assert "not found" in result.output

    def test_get_api_error(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test get handles API errors gracefully."""
        patch_keyring(monkeypatch)

        def mock_get(*a: Any, **kw: Any) -> Any:
            raise Exception("Connection refused")

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_get)

        cli = make_cli()
        result = runner.invoke(cli, ["system", "get", "minion-PXI-1234"])
        assert result.exit_code != 0


class TestSystemSummary:
    """Tests for 'system summary' command."""

    def test_summary_json(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test summary in JSON format."""
        patch_keyring(monkeypatch)

        call_count = 0

        def mock_get(*a: Any, **kw: Any) -> Any:
            nonlocal call_count
            call_count += 1
            url = a[1] if len(a) > 1 else ""
            if "pending" in str(url):
                return MockResponse({"pendingCount": 3})
            return MockResponse(
                {
                    "connectedCount": 10,
                    "disconnectedCount": 5,
                    "virtualCount": 2,
                }
            )

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_get)

        cli = make_cli()
        result = runner.invoke(cli, ["system", "summary", "-f", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["connectedCount"] == 10
        assert data["disconnectedCount"] == 5
        assert data["virtualCount"] == 2
        assert data["pendingCount"] == 3
        assert data["totalCount"] == 20

    def test_summary_table(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test summary in table format."""
        patch_keyring(monkeypatch)

        def mock_get(*a: Any, **kw: Any) -> Any:
            url = a[1] if len(a) > 1 else ""
            if "pending" in str(url):
                return MockResponse({"pendingCount": 0})
            return MockResponse(
                {
                    "connectedCount": 10,
                    "disconnectedCount": 5,
                    "virtualCount": 2,
                }
            )

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_get)

        cli = make_cli()
        result = runner.invoke(cli, ["system", "summary"])
        assert result.exit_code == 0
        assert "Connected" in result.output
        assert "Disconnected" in result.output
        assert "Virtual" in result.output
        assert "Total" in result.output

    def test_summary_api_error(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test summary handles API errors gracefully."""
        patch_keyring(monkeypatch)

        def mock_get(*a: Any, **kw: Any) -> Any:
            raise Exception("Connection refused")

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_get)

        cli = make_cli()
        result = runner.invoke(cli, ["system", "summary"])
        assert result.exit_code != 0


class TestUpdateSystem:
    """Tests for 'system update' command."""

    def test_update_alias(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test updating a system's alias."""
        patch_keyring(monkeypatch)
        monkeypatch.setattr("slcli.profiles.is_active_profile_readonly", lambda: False)
        captured_payloads: List[Dict[str, Any]] = []

        def mock_patch(*a: Any, **kw: Any) -> Any:
            captured_payloads.append(kw.get("payload", {}))
            return MockResponse({}, status_code=204)

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_patch)

        cli = make_cli()
        result = runner.invoke(cli, ["system", "update", "minion-PXI-1234", "--alias", "New Name"])
        assert result.exit_code == 0
        assert captured_payloads[0]["alias"] == "New Name"

    def test_update_keywords(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test updating a system's keywords."""
        patch_keyring(monkeypatch)
        monkeypatch.setattr("slcli.profiles.is_active_profile_readonly", lambda: False)
        captured_payloads: List[Dict[str, Any]] = []

        def mock_patch(*a: Any, **kw: Any) -> Any:
            captured_payloads.append(kw.get("payload", {}))
            return MockResponse({}, status_code=204)

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_patch)

        cli = make_cli()
        result = runner.invoke(
            cli,
            [
                "system",
                "update",
                "minion-PXI-1234",
                "--keyword",
                "prod",
                "--keyword",
                "lab",
            ],
        )
        assert result.exit_code == 0
        assert captured_payloads[0]["keywords"] == ["prod", "lab"]

    def test_update_properties(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test updating a system's properties."""
        patch_keyring(monkeypatch)
        monkeypatch.setattr("slcli.profiles.is_active_profile_readonly", lambda: False)
        captured_payloads: List[Dict[str, Any]] = []

        def mock_patch(*a: Any, **kw: Any) -> Any:
            captured_payloads.append(kw.get("payload", {}))
            return MockResponse({}, status_code=204)

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_patch)

        cli = make_cli()
        result = runner.invoke(
            cli,
            [
                "system",
                "update",
                "minion-PXI-1234",
                "--property",
                "Owner=Team Beta",
            ],
        )
        assert result.exit_code == 0
        assert captured_payloads[0]["properties"] == {"Owner": "Team Beta"}

    def test_update_json_output(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test update with JSON output format."""
        patch_keyring(monkeypatch)
        monkeypatch.setattr("slcli.profiles.is_active_profile_readonly", lambda: False)

        def mock_patch(*a: Any, **kw: Any) -> Any:
            return MockResponse({}, status_code=204)

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_patch)

        cli = make_cli()
        result = runner.invoke(
            cli,
            [
                "system",
                "update",
                "minion-PXI-1234",
                "--alias",
                "New Name",
                "-f",
                "json",
            ],
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["id"] == "minion-PXI-1234"
        assert data["alias"] == "New Name"

    def test_update_no_fields(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test update with no fields specified."""
        patch_keyring(monkeypatch)
        monkeypatch.setattr("slcli.profiles.is_active_profile_readonly", lambda: False)

        cli = make_cli()
        result = runner.invoke(cli, ["system", "update", "minion-PXI-1234"])
        assert result.exit_code != 0
        assert "No fields specified" in result.output

    def test_update_api_error(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test update handles API errors gracefully."""
        patch_keyring(monkeypatch)
        monkeypatch.setattr("slcli.profiles.is_active_profile_readonly", lambda: False)

        def mock_patch(*a: Any, **kw: Any) -> Any:
            raise Exception("Forbidden")

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_patch)

        cli = make_cli()
        result = runner.invoke(cli, ["system", "update", "minion-PXI-1234", "--alias", "New"])
        assert result.exit_code != 0

    def test_update_workspace(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test updating a system's workspace."""
        patch_keyring(monkeypatch)
        monkeypatch.setattr("slcli.profiles.is_active_profile_readonly", lambda: False)
        captured_payloads: List[Dict[str, Any]] = []

        def mock_patch(*a: Any, **kw: Any) -> Any:
            captured_payloads.append(kw.get("payload", {}))
            return MockResponse({}, status_code=204)

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_patch)
        monkeypatch.setattr("slcli.system_click.get_workspace_map", lambda: {"ws-2": "Workspace 2"})

        cli = make_cli()
        result = runner.invoke(cli, ["system", "update", "minion-PXI-1234", "--workspace", "ws-2"])
        assert result.exit_code == 0
        assert captured_payloads[0]["workspace"] == "ws-2"


class TestRemoveSystem:
    """Tests for 'system remove' command."""

    def test_remove_with_force(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test removing a system with force flag."""
        patch_keyring(monkeypatch)
        monkeypatch.setattr("slcli.profiles.is_active_profile_readonly", lambda: False)
        captured_payloads: List[Dict[str, Any]] = []

        call_count = 0

        def mock_request(*a: Any, **kw: Any) -> Any:
            nonlocal call_count
            call_count += 1
            method = a[0] if a else ""
            if method == "GET":
                return MockResponse([SAMPLE_SYSTEM])
            captured_payloads.append(kw.get("payload", {}))
            return MockResponse({"removedIds": ["minion-PXI-1234"]})

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_request)

        cli = make_cli()
        result = runner.invoke(cli, ["system", "remove", "minion-PXI-1234", "--force"])
        assert result.exit_code == 0
        assert "removed" in result.output.lower() or "✓" in result.output

    def test_remove_confirmation_declined(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test removing a system with confirmation declined."""
        patch_keyring(monkeypatch)
        monkeypatch.setattr("slcli.profiles.is_active_profile_readonly", lambda: False)

        def mock_request(*a: Any, **kw: Any) -> Any:
            method = a[0] if a else ""
            if method == "GET":
                return MockResponse([SAMPLE_SYSTEM])
            return MockResponse({})

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_request)

        cli = make_cli()
        with patch("slcli.system_click.questionary.confirm") as mock_confirm:
            mock_confirm.return_value.ask.return_value = False
            result = runner.invoke(cli, ["system", "remove", "minion-PXI-1234"])
        assert "cancelled" in result.output.lower()

    def test_remove_with_failed_ids(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test removing a system that returns failed IDs."""
        patch_keyring(monkeypatch)
        monkeypatch.setattr("slcli.profiles.is_active_profile_readonly", lambda: False)

        def mock_request(*a: Any, **kw: Any) -> Any:
            method = a[0] if a else ""
            if method == "GET":
                return MockResponse([SAMPLE_SYSTEM])
            return MockResponse(
                {
                    "failedIds": [
                        {
                            "id": "minion-PXI-1234",
                            "error": {"message": "System is in use"},
                        }
                    ]
                }
            )

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_request)

        cli = make_cli()
        result = runner.invoke(cli, ["system", "remove", "minion-PXI-1234", "--force"])
        assert result.exit_code != 0


class TestSystemReport:
    """Tests for 'system report' command."""

    def test_report_software(self, monkeypatch: Any, runner: CliRunner, tmp_path: Any) -> None:
        """Test generating a software report."""
        patch_keyring(monkeypatch)
        monkeypatch.setattr("slcli.profiles.is_active_profile_readonly", lambda: False)
        captured_payloads: List[Dict[str, Any]] = []

        def mock_post(*a: Any, **kw: Any) -> Any:
            captured_payloads.append(kw.get("payload", {}))
            resp: Any = MockResponse({})
            resp.content = b"report-data-csv"
            return resp

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_post)

        output_file = str(tmp_path / "report.csv")
        cli = make_cli()
        result = runner.invoke(
            cli,
            ["system", "report", "--type", "SOFTWARE", "--output", output_file],
        )
        assert result.exit_code == 0
        assert "Report generated" in result.output or "✓" in result.output
        assert captured_payloads[0]["type"] == "SOFTWARE"

        with open(output_file, "rb") as f:
            assert f.read() == b"report-data-csv"

    def test_report_hardware_with_filter(
        self, monkeypatch: Any, runner: CliRunner, tmp_path: Any
    ) -> None:
        """Test generating a hardware report with filter."""
        patch_keyring(monkeypatch)
        monkeypatch.setattr("slcli.profiles.is_active_profile_readonly", lambda: False)
        captured_payloads: List[Dict[str, Any]] = []

        def mock_post(*a: Any, **kw: Any) -> Any:
            captured_payloads.append(kw.get("payload", {}))
            resp: Any = MockResponse({})
            resp.content = b"hardware-report"
            return resp

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_post)

        output_file = str(tmp_path / "hw_report.csv")
        cli = make_cli()
        result = runner.invoke(
            cli,
            [
                "system",
                "report",
                "--type",
                "HARDWARE",
                "--filter",
                'connected.data.state = "CONNECTED"',
                "--output",
                output_file,
            ],
        )
        assert result.exit_code == 0
        assert captured_payloads[0]["type"] == "HARDWARE"
        assert captured_payloads[0]["filter"] == 'connected.data.state = "CONNECTED"'

    def test_report_missing_output(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test report requires --output option."""
        patch_keyring(monkeypatch)

        cli = make_cli()
        result = runner.invoke(cli, ["system", "report", "--type", "SOFTWARE"])
        assert result.exit_code != 0

    def test_report_missing_type(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test report requires --type option."""
        patch_keyring(monkeypatch)

        cli = make_cli()
        result = runner.invoke(cli, ["system", "report", "--output", "foo.csv"])
        assert result.exit_code != 0


# =============================================================================
# Job command tests
# =============================================================================


class TestJobList:
    """Tests for 'system job list' command."""

    def test_list_json(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test listing jobs in JSON format."""
        patch_keyring(monkeypatch)

        def mock_post(*a: Any, **kw: Any) -> Any:
            return MockResponse({"data": [SAMPLE_JOB], "count": 1})

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_post)

        cli = make_cli()
        result = runner.invoke(cli, ["system", "job", "list", "-f", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert len(data) == 1

    def test_list_with_state_filter(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test listing jobs with state filter."""
        patch_keyring(monkeypatch)
        captured_payloads: List[Dict[str, Any]] = []

        def mock_post(*a: Any, **kw: Any) -> Any:
            captured_payloads.append(kw.get("payload", {}))
            return MockResponse({"data": [SAMPLE_JOB], "count": 1})

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_post)

        cli = make_cli()
        result = runner.invoke(cli, ["system", "job", "list", "-f", "json", "--state", "SUCCEEDED"])
        assert result.exit_code == 0
        assert 'state = "SUCCEEDED"' in captured_payloads[0].get("filter", "")

    def test_list_with_system_id_filter(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test listing jobs filtered by system ID."""
        patch_keyring(monkeypatch)
        captured_payloads: List[Dict[str, Any]] = []

        def mock_post(*a: Any, **kw: Any) -> Any:
            captured_payloads.append(kw.get("payload", {}))
            return MockResponse({"data": [SAMPLE_JOB], "count": 1})

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_post)

        cli = make_cli()
        result = runner.invoke(
            cli,
            [
                "system",
                "job",
                "list",
                "-f",
                "json",
                "--system-id",
                "minion-PXI-1234",
            ],
        )
        assert result.exit_code == 0
        assert 'id = "minion-PXI-1234"' in captured_payloads[0].get("filter", "")

    def test_list_empty(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test listing when no jobs found."""
        patch_keyring(monkeypatch)

        def mock_post(*a: Any, **kw: Any) -> Any:
            return MockResponse({"data": [], "count": 0})

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_post)

        cli = make_cli()
        result = runner.invoke(cli, ["system", "job", "list", "-f", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data == []

    def test_list_table_pagination_prompt(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test that table pagination shows more-available prompt when page is full."""
        patch_keyring(monkeypatch)

        call_count = 0

        def mock_post(*a: Any, **kw: Any) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return MockResponse({"data": [SAMPLE_JOB] * 25})
            return MockResponse({"data": []})

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_post)

        cli = make_cli()
        with patch("slcli.system_click.questionary.confirm") as mock_confirm:
            mock_confirm.return_value.ask.return_value = False
            result = runner.invoke(cli, ["system", "job", "list", "-f", "table"])
        assert result.exit_code == 0
        assert "Showing 25 jobs" in result.output


class TestCalculateJobColumnWidths:
    """Tests for _calculate_job_column_widths helper."""

    def test_returns_four_columns(self) -> None:
        """Test that four column widths are returned."""
        widths = _calculate_job_column_widths()
        assert len(widths) == 4

    def test_fixed_columns_have_expected_widths(self) -> None:
        """Test fixed column widths."""
        widths = _calculate_job_column_widths()
        assert widths[0] == 36  # Job ID
        assert widths[1] == 14  # State
        assert widths[2] == 24  # Created

    def test_target_column_has_minimum_width(self) -> None:
        """Test target column has minimum width."""
        widths = _calculate_job_column_widths()
        assert widths[3] >= 20


class TestJobGet:
    """Tests for 'system job get' command."""

    def test_get_json(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test getting a job in JSON format."""
        patch_keyring(monkeypatch)

        def mock_get(*a: Any, **kw: Any) -> Any:
            return MockResponse([SAMPLE_JOB])

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_get)

        cli = make_cli()
        result = runner.invoke(cli, ["system", "job", "get", "20240120140000123456", "-f", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["jid"] == "20240120140000123456"

    def test_get_table(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test getting a job in table format."""
        patch_keyring(monkeypatch)

        def mock_get(*a: Any, **kw: Any) -> Any:
            return MockResponse([SAMPLE_JOB])

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_get)

        cli = make_cli()
        result = runner.invoke(cli, ["system", "job", "get", "20240120140000123456"])
        assert result.exit_code == 0
        assert "SUCCEEDED" in result.output
        assert "pkg.install" in result.output

    def test_get_not_found(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test getting a nonexistent job."""
        patch_keyring(monkeypatch)

        def mock_get(*a: Any, **kw: Any) -> Any:
            return MockResponse([])

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_get)

        cli = make_cli()
        result = runner.invoke(cli, ["system", "job", "get", "nonexistent"])
        assert result.exit_code != 0
        assert "not found" in result.output


class TestJobSummary:
    """Tests for 'system job summary' command."""

    def test_summary_json(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test job summary in JSON format."""
        patch_keyring(monkeypatch)

        def mock_get(*a: Any, **kw: Any) -> Any:
            return MockResponse(
                {
                    "activeCount": 2,
                    "succeededCount": 50,
                    "failedCount": 3,
                }
            )

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_get)

        cli = make_cli()
        result = runner.invoke(cli, ["system", "job", "summary", "-f", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["activeCount"] == 2
        assert data["succeededCount"] == 50
        assert data["failedCount"] == 3
        assert data["totalCount"] == 55

    def test_summary_table(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test job summary in table format."""
        patch_keyring(monkeypatch)

        def mock_get(*a: Any, **kw: Any) -> Any:
            return MockResponse(
                {
                    "activeCount": 2,
                    "succeededCount": 50,
                    "failedCount": 3,
                }
            )

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_get)

        cli = make_cli()
        result = runner.invoke(cli, ["system", "job", "summary"])
        assert result.exit_code == 0
        assert "Active:" in result.output
        assert "Succeeded:" in result.output
        assert "Failed:" in result.output
        assert "Total:" in result.output


class TestJobCancel:
    """Tests for 'system job cancel' command."""

    def test_cancel_job(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test cancelling a job."""
        patch_keyring(monkeypatch)
        monkeypatch.setattr("slcli.profiles.is_active_profile_readonly", lambda: False)
        captured_payloads: List[Any] = []

        def mock_post(*a: Any, **kw: Any) -> Any:
            captured_payloads.append(kw.get("payload", {}))
            return MockResponse({})

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_post)

        cli = make_cli()
        result = runner.invoke(cli, ["system", "job", "cancel", "20240120140000123456"])
        assert result.exit_code == 0
        assert "cancelled" in result.output.lower() or "✓" in result.output

    def test_cancel_job_with_system_id(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test cancelling a job with system ID disambiguation."""
        patch_keyring(monkeypatch)
        monkeypatch.setattr("slcli.profiles.is_active_profile_readonly", lambda: False)
        captured_payloads: List[Any] = []

        def mock_post(*a: Any, **kw: Any) -> Any:
            captured_payloads.append(kw.get("payload", {}))
            return MockResponse({})

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_post)

        cli = make_cli()
        result = runner.invoke(
            cli,
            [
                "system",
                "job",
                "cancel",
                "20240120140000123456",
                "--system-id",
                "minion-PXI-1234",
            ],
        )
        assert result.exit_code == 0
        payload = captured_payloads[0]
        assert isinstance(payload, dict)
        jobs = payload["jobs"]
        assert jobs[0]["jid"] == "20240120140000123456"
        assert jobs[0]["systemId"] == "minion-PXI-1234"

    def test_cancel_api_error(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test cancel handles API errors gracefully."""
        patch_keyring(monkeypatch)
        monkeypatch.setattr("slcli.profiles.is_active_profile_readonly", lambda: False)

        def mock_post(*a: Any, **kw: Any) -> Any:
            raise Exception("Job not found")

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_post)

        cli = make_cli()
        result = runner.invoke(cli, ["system", "job", "cancel", "nonexistent"])
        assert result.exit_code != 0


# ------------------------------------------------------------------
# Related-resource fetch helper tests
# ------------------------------------------------------------------


class TestFetchAssetsForSystem:
    """Tests for _fetch_assets_for_system."""

    def test_returns_assets_and_total(self, monkeypatch: Any) -> None:
        """Test normal response parsing."""
        patch_keyring(monkeypatch)

        def mock_post(*a: Any, **kw: Any) -> Any:
            return MockResponse({"assets": [{"id": "a1", "name": "Asset1"}], "totalCount": 5})

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_post)
        assets, total = _fetch_assets_for_system("minion-1", 10)
        assert len(assets) == 1
        assert assets[0]["id"] == "a1"
        assert total == 5

    def test_empty_response(self, monkeypatch: Any) -> None:
        """Test empty asset list."""
        patch_keyring(monkeypatch)

        def mock_post(*a: Any, **kw: Any) -> Any:
            return MockResponse({"assets": [], "totalCount": 0})

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_post)
        assets, total = _fetch_assets_for_system("minion-1", 10)
        assert assets == []
        assert total == 0

    def test_null_total_count(self, monkeypatch: Any) -> None:
        """Test response where totalCount is null."""
        patch_keyring(monkeypatch)

        def mock_post(*a: Any, **kw: Any) -> Any:
            return MockResponse({"assets": [{"id": "a1"}], "totalCount": None})

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_post)
        assets, total = _fetch_assets_for_system("minion-1", 10)
        assert total == 1  # Falls back to len(assets)


class TestFetchAlarmsForSystem:
    """Tests for _fetch_alarms_for_system."""

    def test_returns_alarms_and_total(self, monkeypatch: Any) -> None:
        """Test normal response parsing."""
        patch_keyring(monkeypatch)

        def mock_post(*a: Any, **kw: Any) -> Any:
            return MockResponse(
                {
                    "alarmInstances": [{"id": "alarm-1", "severity": 3}],
                    "totalCount": 2,
                }
            )

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_post)
        alarms, total = _fetch_alarms_for_system("minion-1", 10)
        assert len(alarms) == 1
        assert total == 2

    def test_empty_response(self, monkeypatch: Any) -> None:
        """Test empty alarm list."""
        patch_keyring(monkeypatch)

        def mock_post(*a: Any, **kw: Any) -> Any:
            return MockResponse({"alarmInstances": [], "totalCount": 0})

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_post)
        alarms, total = _fetch_alarms_for_system("minion-1", 10)
        assert alarms == []
        assert total == 0


class TestFetchRecentJobsForSystem:
    """Tests for _fetch_recent_jobs_for_system."""

    def test_returns_jobs_and_total(self, monkeypatch: Any) -> None:
        """Test normal response parsing."""
        patch_keyring(monkeypatch)

        def mock_post(*a: Any, **kw: Any) -> Any:
            return MockResponse(
                {
                    "jobs": [{"jid": "j1", "state": "succeeded"}],
                    "totalCount": 10,
                }
            )

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_post)
        jobs, total = _fetch_recent_jobs_for_system("minion-1", 5)
        assert len(jobs) == 1
        assert total == 10


class TestFetchResultsForSystem:
    """Tests for _fetch_results_for_system."""

    def test_returns_results_and_total(self, monkeypatch: Any) -> None:
        """Test normal response parsing."""
        patch_keyring(monkeypatch)

        def mock_post(*a: Any, **kw: Any) -> Any:
            return MockResponse(
                {
                    "results": [{"id": "r1", "programName": "Test1"}],
                    "totalCount": 3,
                }
            )

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_post)
        results, total = _fetch_results_for_system("minion-1", 10)
        assert len(results) == 1
        assert total == 3


class TestFetchWorkitemsForSystem:
    """Tests for _fetch_workitems_for_system."""

    def test_returns_workitems_and_total(self, monkeypatch: Any) -> None:
        """Test normal response parsing."""
        patch_keyring(monkeypatch)

        def mock_post(*a: Any, **kw: Any) -> Any:
            return MockResponse(
                {
                    "workItems": [{"id": "wi1", "name": "Plan A"}],
                    "totalCount": 1,
                }
            )

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_post)
        workitems, total = _fetch_workitems_for_system("minion-1", 10, 30)
        assert len(workitems) == 1
        assert total == 1

    def test_empty_response(self, monkeypatch: Any) -> None:
        """Test empty work item list."""
        patch_keyring(monkeypatch)

        def mock_post(*a: Any, **kw: Any) -> Any:
            return MockResponse({"workItems": [], "totalCount": 0})

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_post)
        workitems, total = _fetch_workitems_for_system("minion-1", 10, 30)
        assert workitems == []
        assert total == 0

    def test_null_total_count(self, monkeypatch: Any) -> None:
        """Test response where totalCount is null."""
        patch_keyring(monkeypatch)

        def mock_post(*a: Any, **kw: Any) -> Any:
            return MockResponse({"workItems": [{"id": "wi1"}], "totalCount": None})

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_post)
        workitems, total = _fetch_workitems_for_system("minion-1", 10, 30)
        assert total == 1


# ------------------------------------------------------------------
# system get --include-* CLI integration tests
# ------------------------------------------------------------------


class TestGetSystemIncludeFlags:
    """Tests for system get --include-* options."""

    def _make_mock_api(self) -> Any:
        """Create a mock that dispatches based on URL."""

        def mock_request(method: str, url: str, **kw: Any) -> Any:
            if "/nisysmgmt/v1/systems" in url and "query-jobs" not in url:
                return MockResponse([SAMPLE_SYSTEM])
            if "/niapm/v1/query-assets" in url:
                return MockResponse({"assets": [{"id": "a1", "name": "DMM"}], "totalCount": 1})
            if "/nialarm/v1/query-instances-with-filter" in url:
                return MockResponse(
                    {
                        "alarmInstances": [{"id": "al1", "severity": 2}],
                        "totalCount": 1,
                    }
                )
            if "/nisysmgmt/v1/query-jobs" in url:
                return MockResponse(
                    {
                        "jobs": [{"jid": "j1", "state": "succeeded", "createdTimestamp": ""}],
                        "totalCount": 1,
                    }
                )
            if "/nitestmonitor/v2/query-results" in url:
                return MockResponse(
                    {
                        "results": [
                            {
                                "id": "r1",
                                "programName": "P1",
                                "status": {"statusType": "PASSED"},
                            }
                        ],
                        "totalCount": 1,
                    }
                )
            if "/niworkitem/v1/query-workitems" in url:
                return MockResponse(
                    {
                        "workItems": [{"id": "w1", "name": "Plan X"}],
                        "totalCount": 1,
                    }
                )
            # Fallback for workspace map
            return MockResponse({"workspaces": []})

        return mock_request

    def test_include_assets_json(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test --include-assets adds _assets key in JSON."""
        patch_keyring(monkeypatch)
        monkeypatch.setattr("slcli.system_click.make_api_request", self._make_mock_api())

        cli = make_cli()
        result = runner.invoke(
            cli, ["system", "get", "minion-PXI-1234", "-f", "json", "--include-assets"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "_assets" in data
        assert data["_assets"]["totalCount"] == 1
        assert data["_assets"]["items"][0]["id"] == "a1"

    def test_include_alarms_json(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test --include-alarms adds _alarms key in JSON."""
        patch_keyring(monkeypatch)
        monkeypatch.setattr("slcli.system_click.make_api_request", self._make_mock_api())

        cli = make_cli()
        result = runner.invoke(
            cli, ["system", "get", "minion-PXI-1234", "-f", "json", "--include-alarms"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "_alarms" in data
        assert data["_alarms"]["totalCount"] == 1

    def test_include_jobs_json(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test --include-jobs adds _jobs key in JSON."""
        patch_keyring(monkeypatch)
        monkeypatch.setattr("slcli.system_click.make_api_request", self._make_mock_api())

        cli = make_cli()
        result = runner.invoke(
            cli, ["system", "get", "minion-PXI-1234", "-f", "json", "--include-jobs"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "_jobs" in data
        assert data["_jobs"]["totalCount"] == 1

    def test_include_results_json(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test --include-results adds _results key in JSON."""
        patch_keyring(monkeypatch)
        monkeypatch.setattr("slcli.system_click.make_api_request", self._make_mock_api())

        cli = make_cli()
        result = runner.invoke(
            cli, ["system", "get", "minion-PXI-1234", "-f", "json", "--include-results"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "_results" in data
        assert data["_results"]["totalCount"] == 1

    def test_include_workitems_json(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test --include-workitems adds _workitems key in JSON."""
        patch_keyring(monkeypatch)
        monkeypatch.setattr("slcli.system_click.make_api_request", self._make_mock_api())

        cli = make_cli()
        result = runner.invoke(
            cli, ["system", "get", "minion-PXI-1234", "-f", "json", "--include-workitems"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "_workitems" in data
        assert data["_workitems"]["totalCount"] == 1

    def test_include_all_json(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test --include-all adds all related resource keys in JSON."""
        patch_keyring(monkeypatch)
        monkeypatch.setattr("slcli.system_click.make_api_request", self._make_mock_api())

        cli = make_cli()
        result = runner.invoke(
            cli, ["system", "get", "minion-PXI-1234", "-f", "json", "--include-all"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        # All sections present
        for key in ("_assets", "_alarms", "_jobs", "_results", "_workitems"):
            assert key in data, f"Missing key {key}"
        # Packages & feeds should be included by --include-all
        assert "packages" in data
        assert "feeds" in data

    def test_no_include_flags_no_related_keys(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test that without --include-* flags, no related-resource keys appear."""
        patch_keyring(monkeypatch)

        def mock_get(*a: Any, **kw: Any) -> Any:
            return MockResponse([SAMPLE_SYSTEM])

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_get)

        cli = make_cli()
        result = runner.invoke(cli, ["system", "get", "minion-PXI-1234", "-f", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        for key in ("_assets", "_alarms", "_jobs", "_results", "_workitems"):
            assert key not in data

    def test_include_assets_table(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test --include-assets renders a section in table mode."""
        patch_keyring(monkeypatch)
        monkeypatch.setattr("slcli.system_click.make_api_request", self._make_mock_api())
        monkeypatch.setattr("slcli.system_click.get_workspace_map", lambda: {})

        cli = make_cli()
        result = runner.invoke(cli, ["system", "get", "minion-PXI-1234", "--include-assets"])
        assert result.exit_code == 0
        assert "Assets (1)" in result.output

    def test_include_all_table(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test --include-all renders all sections in table mode."""
        patch_keyring(monkeypatch)
        monkeypatch.setattr("slcli.system_click.make_api_request", self._make_mock_api())
        monkeypatch.setattr("slcli.system_click.get_workspace_map", lambda: {})

        cli = make_cli()
        result = runner.invoke(cli, ["system", "get", "minion-PXI-1234", "--include-all"])
        assert result.exit_code == 0
        assert "Assets (1)" in result.output
        assert "Active Alarms (1)" in result.output
        assert "Recent Jobs (1)" in result.output
        assert "Test Results (1)" in result.output
        assert "Scheduled Work Items" in result.output

    def test_fetch_error_shows_warning_table(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test that a fetch failure shows a ✗ warning in table mode."""
        patch_keyring(monkeypatch)

        call_count = 0

        def mock_request(method: str, url: str, **kw: Any) -> Any:
            nonlocal call_count
            if "/nisysmgmt/v1/systems" in url and "query-jobs" not in url:
                return MockResponse([SAMPLE_SYSTEM])
            if "/niapm/v1/query-assets" in url:
                raise Exception("Service unavailable")
            return MockResponse({})

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_request)
        monkeypatch.setattr("slcli.system_click.get_workspace_map", lambda: {})

        cli = make_cli()
        result = runner.invoke(cli, ["system", "get", "minion-PXI-1234", "--include-assets"])
        assert result.exit_code == 0
        assert "Failed to load assets" in result.output

    def test_take_option(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test --take option is passed through."""
        patch_keyring(monkeypatch)
        captured_payloads: List[Dict[str, Any]] = []

        def mock_request(method: str, url: str, **kw: Any) -> Any:
            if "/nisysmgmt/v1/systems" in url and "query-jobs" not in url:
                return MockResponse([SAMPLE_SYSTEM])
            if "/niapm/v1/query-assets" in url:
                captured_payloads.append(kw.get("payload", kw.get("json", {})))
                return MockResponse({"assets": [], "totalCount": 0})
            return MockResponse({})

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_request)

        cli = make_cli()
        result = runner.invoke(
            cli,
            ["system", "get", "minion-PXI-1234", "-f", "json", "--include-assets", "-t", "5"],
        )
        assert result.exit_code == 0
        assert len(captured_payloads) == 1
        assert captured_payloads[0]["take"] == 5

    def test_fetch_error_json(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test fetch failure populates error field in JSON."""
        patch_keyring(monkeypatch)

        def mock_request(method: str, url: str, **kw: Any) -> Any:
            if "/nisysmgmt/v1/systems" in url and "query-jobs" not in url:
                return MockResponse([SAMPLE_SYSTEM])
            if "/niapm/v1/query-assets" in url:
                raise Exception("timeout")
            return MockResponse({})

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_request)

        cli = make_cli()
        result = runner.invoke(
            cli, ["system", "get", "minion-PXI-1234", "-f", "json", "--include-assets"]
        )
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert "_assets" in data
        assert data["_assets"]["error"] is not None
        assert "timeout" in data["_assets"]["error"]


class TestFetchAssetsProjection:
    """Tests for _fetch_assets_for_system helper."""

    def test_requests_slot_number_in_projection(self, monkeypatch: Any) -> None:
        """Test asset projection includes slotNumber for compare workflows."""
        patch_keyring(monkeypatch)

        captured_payload: Dict[str, Any] = {}

        def mock_request(method: str, url: str, **kw: Any) -> Any:
            assert method == "POST"
            assert "/niapm/v1/query-assets" in url
            captured_payload.update(kw.get("payload", {}))
            return MockResponse({"assets": [], "totalCount": 0})

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_request)

        assets, total = _fetch_assets_for_system("minion-1", 10)

        assert assets == []
        assert total == 0
        assert "location.slotNumber" in captured_payload["projection"]


# =============================================================================
# Compare helper tests
# =============================================================================


class TestGetPackages:
    """Tests for _get_packages helper."""

    def test_extracts_packages(self) -> None:
        """Test extracting packages from system data."""
        system: Dict[str, Any] = {
            "packages": {
                "data": {
                    "ni-daqmx": {"displayname": "NI-DAQmx", "version": "24.1.0"},
                },
            },
        }
        result = _get_packages(system)
        assert "ni-daqmx" in result
        assert result["ni-daqmx"]["version"] == "24.1.0"

    def test_empty_when_no_packages(self) -> None:
        """Test returns empty dict when no packages field."""
        assert _get_packages({}) == {}
        assert _get_packages({"packages": "invalid"}) == {}
        assert _get_packages({"packages": {"data": None}}) == {}


class TestComparePackages:
    """Tests for _compare_packages."""

    def test_identical_packages(self) -> None:
        """Test comparison when packages are identical."""
        pkgs: Dict[str, Dict[str, Any]] = {
            "ni-daqmx": {"displayname": "NI-DAQmx", "version": "24.1.0"},
        }
        result = _compare_packages(pkgs, dict(pkgs), "A", "B", "json")
        assert result["only_system_a"] == []
        assert result["only_system_b"] == []
        assert result["version_differences"] == []
        assert result["matching_count"] == 1

    def test_only_on_one_system(self) -> None:
        """Test packages present on only one system."""
        pkgs_a: Dict[str, Dict[str, Any]] = {
            "ni-daqmx": {"displayname": "NI-DAQmx", "version": "24.1.0"},
        }
        pkgs_b: Dict[str, Dict[str, Any]] = {
            "ni-visa": {"displayname": "NI-VISA", "version": "24.1.0"},
        }
        result = _compare_packages(pkgs_a, pkgs_b, "A", "B", "json")
        assert "ni-daqmx" in result["only_system_a"]
        assert "ni-visa" in result["only_system_b"]
        assert result["matching_count"] == 0

    def test_version_difference(self) -> None:
        """Test version differences detected."""
        pkgs_a: Dict[str, Dict[str, Any]] = {
            "ni-daqmx": {"displayname": "NI-DAQmx", "version": "24.1.0"},
        }
        pkgs_b: Dict[str, Dict[str, Any]] = {
            "ni-daqmx": {"displayname": "NI-DAQmx", "version": "23.8.0"},
        }
        result = _compare_packages(pkgs_a, pkgs_b, "A", "B", "json")
        assert len(result["version_differences"]) == 1
        assert result["version_differences"][0]["version_a"] == "24.1.0"
        assert result["version_differences"][0]["version_b"] == "23.8.0"

    def test_table_output_shows_differences(self) -> None:
        """Test table output contains difference markers."""
        pkgs_a: Dict[str, Dict[str, Any]] = {
            "ni-daqmx": {"displayname": "NI-DAQmx", "version": "24.1.0"},
            "only-a": {"displayname": "Only A", "version": "1.0"},
        }
        pkgs_b: Dict[str, Dict[str, Any]] = {
            "ni-daqmx": {"displayname": "NI-DAQmx", "version": "23.8.0"},
        }
        result = _compare_packages(pkgs_a, pkgs_b, "SysA", "SysB", "table")
        assert "only-a" in result["only_system_a"]


class TestCompareAssets:
    """Tests for _compare_assets."""

    def test_identical_assets(self) -> None:
        """Test comparison when assets are identical."""
        assets: List[Dict[str, Any]] = [
            {
                "name": "PXI-6255",
                "modelName": "PXI-6255",
                "vendorName": "NI",
                "location": {"slotNumber": 2},
            },
        ]
        result = _compare_assets(list(assets), list(assets), "A", "B", "json")
        assert result["only_system_a"] == []
        assert result["only_system_b"] == []
        assert result["slot_differences"] == []
        assert result["matching_count"] == 1

    def test_asset_only_on_one_system(self) -> None:
        """Test assets with mismatched model/vendor are listed as unique."""
        assets_a: List[Dict[str, Any]] = [
            {"name": "Card A", "modelName": "PXI-6255", "vendorName": "NI"},
        ]
        assets_b: List[Dict[str, Any]] = [
            {"name": "Card B", "modelName": "PXI-4130", "vendorName": "NI"},
        ]
        result = _compare_assets(assets_a, assets_b, "A", "B", "json")
        assert len(result["only_system_a"]) == 1
        assert result["only_system_a"][0]["model"] == "PXI-6255"
        assert len(result["only_system_b"]) == 1
        assert result["only_system_b"][0]["model"] == "PXI-4130"

    def test_slot_difference(self) -> None:
        """Test same model/vendor in different slots produces slot difference."""
        assets_a: List[Dict[str, Any]] = [
            {
                "name": "Card A",
                "modelName": "PXI-6255",
                "vendorName": "NI",
                "location": {"slotNumber": 2},
            },
        ]
        assets_b: List[Dict[str, Any]] = [
            {
                "name": "Card B",
                "modelName": "PXI-6255",
                "vendorName": "NI",
                "location": {"slotNumber": 5},
            },
        ]
        result = _compare_assets(assets_a, assets_b, "A", "B", "json")
        assert result["only_system_a"] == []
        assert result["only_system_b"] == []
        assert len(result["slot_differences"]) == 1
        assert result["slot_differences"][0]["slot_a"] == "2"
        assert result["slot_differences"][0]["slot_b"] == "5"

    def test_different_model_and_vendor(self) -> None:
        """Test different model/vendor pairs are listed as unique to each."""
        assets_a: List[Dict[str, Any]] = [
            {"name": "DAQ", "modelName": "PXI-6255", "vendorName": "NI"},
        ]
        assets_b: List[Dict[str, Any]] = [
            {"name": "DAQ", "modelName": "PXI-6368", "vendorName": "NI Corp"},
        ]
        result = _compare_assets(assets_a, assets_b, "A", "B", "json")
        assert len(result["only_system_a"]) == 1
        assert len(result["only_system_b"]) == 1
        assert result["matching_count"] == 0

    def test_count_mismatch_is_error(self) -> None:
        """Test same model/vendor with different counts is an error."""
        assets_a: List[Dict[str, Any]] = [
            {
                "name": "Card 1",
                "modelName": "PXI-6255",
                "vendorName": "NI",
                "location": {"slotNumber": 2},
            },
            {
                "name": "Card 2",
                "modelName": "PXI-6255",
                "vendorName": "NI",
                "location": {"slotNumber": 3},
            },
        ]
        assets_b: List[Dict[str, Any]] = [
            {
                "name": "Card 1",
                "modelName": "PXI-6255",
                "vendorName": "NI",
                "location": {"slotNumber": 2},
            },
        ]
        result = _compare_assets(assets_a, assets_b, "A", "B", "json")
        assert len(result["count_mismatches"]) == 1
        assert result["count_mismatches"][0]["model"] == "PXI-6255"

    def test_empty_assets(self) -> None:
        """Test comparing empty asset lists."""
        result = _compare_assets([], [], "A", "B", "json")
        assert result["only_system_a"] == []
        assert result["only_system_b"] == []
        assert result["slot_differences"] == []
        assert result["matching_count"] == 0

    def test_table_output_shows_sections(self) -> None:
        """Test table output includes unique and slot difference sections."""
        assets_a: List[Dict[str, Any]] = [
            {
                "name": "Card",
                "modelName": "PXI-6255",
                "vendorName": "NI",
                "location": {"slotNumber": 2},
            },
            {"name": "Extra", "modelName": "PXI-4130", "vendorName": "NI"},
        ]
        assets_b: List[Dict[str, Any]] = [
            {
                "name": "Card",
                "modelName": "PXI-6255",
                "vendorName": "NI",
                "location": {"slotNumber": 5},
            },
        ]
        # Call with table format to exercise output path
        result = _compare_assets(assets_a, assets_b, "SysA", "SysB", "table")
        assert len(result["only_system_a"]) == 1
        assert len(result["slot_differences"]) == 1


# =============================================================================
# Compare command integration tests
# =============================================================================


SAMPLE_SYSTEM_A: Dict[str, Any] = {
    "id": "sys-aaa",
    "alias": "System A",
    "packages": {
        "data": {
            "ni-daqmx": {
                "displayname": "NI-DAQmx",
                "displayversion": "2024Q1",
                "version": "24.1.0",
            },
            "ni-visa": {
                "displayname": "NI-VISA",
                "displayversion": "2024Q1",
                "version": "24.1.0",
            },
        },
    },
}

SAMPLE_SYSTEM_B: Dict[str, Any] = {
    "id": "sys-bbb",
    "alias": "System B",
    "packages": {
        "data": {
            "ni-daqmx": {
                "displayname": "NI-DAQmx",
                "displayversion": "2023Q4",
                "version": "23.8.0",
            },
            "ni-rfsa": {
                "displayname": "NI-RFSA",
                "displayversion": "2024Q1",
                "version": "24.1.0",
            },
        },
    },
}

SAMPLE_ASSETS_A: List[Dict[str, Any]] = [
    {
        "name": "PXI-6255",
        "modelName": "PXI-6255",
        "vendorName": "NI",
        "location": {"slotNumber": 2, "minionId": "sys-aaa"},
    },
]

SAMPLE_ASSETS_B: List[Dict[str, Any]] = [
    {
        "name": "PXI-6255",
        "modelName": "PXI-6255",
        "vendorName": "NI",
        "location": {"slotNumber": 5, "minionId": "sys-bbb"},
    },
    {
        "name": "PXI-4130",
        "modelName": "PXI-4130",
        "vendorName": "NI",
        "location": {"slotNumber": 3, "minionId": "sys-bbb"},
    },
]


class TestCompareCommand:
    """Tests for the system compare CLI command."""

    def test_compare_json_output(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test compare command with JSON output."""
        patch_keyring(monkeypatch)

        def mock_request(method: str, url: str, **kw: Any) -> Any:
            if method == "GET" and "id=sys-aaa" in url:
                return MockResponse([SAMPLE_SYSTEM_A])
            if method == "GET" and "id=sys-bbb" in url:
                return MockResponse([SAMPLE_SYSTEM_B])
            if method == "POST" and "query-assets" in url:
                payload = kw.get("payload", {})
                filt = payload.get("filter", "")
                if "sys-aaa" in filt:
                    return MockResponse({"assets": SAMPLE_ASSETS_A, "totalCount": 1})
                if "sys-bbb" in filt:
                    return MockResponse({"assets": SAMPLE_ASSETS_B, "totalCount": 2})
                return MockResponse({"assets": [], "totalCount": 0})
            return MockResponse({})

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_request)

        cli = make_cli()
        result = runner.invoke(cli, ["system", "compare", "sys-aaa", "sys-bbb", "-f", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["system_a"]["id"] == "sys-aaa"
        assert data["system_b"]["id"] == "sys-bbb"

        # Software comparison
        sw = data["software"]
        assert "ni-visa" in sw["only_system_a"]
        assert "ni-rfsa" in sw["only_system_b"]
        assert len(sw["version_differences"]) == 1
        assert sw["version_differences"][0]["package"] == "NI-DAQmx"

        # Asset comparison — PXI-6255 same model/vendor, different slot → slot diff
        # PXI-4130 only on B → only_system_b
        assets = data["assets"]
        assert len(assets["only_system_b"]) == 1
        assert assets["only_system_b"][0]["model"] == "PXI-4130"
        assert len(assets["slot_differences"]) == 1
        assert assets["slot_differences"][0]["model"] == "PXI-6255"
        assert assets["slot_differences"][0]["slot_a"] == "2"
        assert assets["slot_differences"][0]["slot_b"] == "5"

    def test_compare_table_output(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test compare command with table output."""
        patch_keyring(monkeypatch)

        def mock_request(method: str, url: str, **kw: Any) -> Any:
            if method == "GET" and "id=sys-aaa" in url:
                return MockResponse([SAMPLE_SYSTEM_A])
            if method == "GET" and "id=sys-bbb" in url:
                return MockResponse([SAMPLE_SYSTEM_B])
            if method == "POST" and "query-assets" in url:
                return MockResponse({"assets": [], "totalCount": 0})
            return MockResponse({})

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_request)

        cli = make_cli()
        result = runner.invoke(cli, ["system", "compare", "sys-aaa", "sys-bbb"])
        assert result.exit_code == 0
        assert "System A" in result.output
        assert "System B" in result.output
        assert "Software Comparison" in result.output
        assert "Asset Comparison" in result.output

    def test_compare_resolves_by_alias(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test compare resolves systems by alias."""
        patch_keyring(monkeypatch)

        call_log: List[Dict[str, Any]] = []

        def mock_request(method: str, url: str, **kw: Any) -> Any:
            call_log.append({"method": method, "url": url, "kw": kw})
            # ID lookup fails
            if method == "GET" and "/systems?" in url:
                return MockResponse([], status_code=404)
            # Alias query succeeds
            if method == "POST" and "query-systems" in url:
                payload = kw.get("payload", {})
                filt = payload.get("filter", "")
                if "System A" in filt:
                    return MockResponse({"data": [SAMPLE_SYSTEM_A]})
                if "System B" in filt:
                    return MockResponse({"data": [SAMPLE_SYSTEM_B]})
            if method == "POST" and "query-assets" in url:
                return MockResponse({"assets": [], "totalCount": 0})
            return MockResponse({})

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_request)

        cli = make_cli()
        result = runner.invoke(cli, ["system", "compare", "System A", "System B", "-f", "json"])
        assert result.exit_code == 0

    def test_compare_system_not_found(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test compare exits when system is not found."""
        patch_keyring(monkeypatch)

        def mock_request(method: str, url: str, **kw: Any) -> Any:
            if method == "GET":
                return MockResponse([], status_code=404)
            if method == "POST" and "query-systems" in url:
                return MockResponse({"data": []})
            return MockResponse({})

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_request)

        cli = make_cli()
        result = runner.invoke(cli, ["system", "compare", "nonexistent", "also-gone"])
        assert result.exit_code != 0

    def test_compare_identical_systems(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test comparing a system with itself shows no differences."""
        patch_keyring(monkeypatch)

        def mock_request(method: str, url: str, **kw: Any) -> Any:
            if method == "GET" and "/systems?" in url:
                return MockResponse([SAMPLE_SYSTEM_A])
            if method == "POST" and "query-assets" in url:
                return MockResponse({"assets": SAMPLE_ASSETS_A, "totalCount": 1})
            return MockResponse({})

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_request)

        cli = make_cli()
        result = runner.invoke(cli, ["system", "compare", "sys-aaa", "sys-aaa", "-f", "json"])
        assert result.exit_code == 0
        data = json.loads(result.output)
        assert data["software"]["version_differences"] == []
        assert data["assets"]["only_system_a"] == []
        assert data["assets"]["only_system_b"] == []
        assert data["assets"]["slot_differences"] == []

    def test_compare_auth_error_propagates(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test that auth errors during resolve are not masked as 'not found'."""
        patch_keyring(monkeypatch)

        def mock_request(method: str, url: str, **kw: Any) -> Any:
            if method == "GET" and "/systems?" in url:
                return MockResponse({"error": "Unauthorized"}, status_code=401)
            return MockResponse({})

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_request)

        cli = make_cli()
        result = runner.invoke(cli, ["system", "compare", "sys-aaa", "sys-bbb"])
        assert result.exit_code != 0
        # Should NOT say "System not found" — it's an auth error
        assert "System not found" not in result.output
