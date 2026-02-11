"""Unit tests for system CLI commands."""

import json
from typing import Any, Dict, List

import click
import pytest
from click.testing import CliRunner

from slcli.system_click import (
    _LIST_PROJECTION,
    _build_job_filter,
    _build_system_filter,
    _calculate_column_widths,
    _calculate_job_column_widths,
    _escape_filter_value,
    _filter_by_package,
    _get_system_grains,
    _get_system_state,
    _parse_properties,
    _parse_systems_response,
    _query_all_items,
    register_system_commands,
)


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
            raise Exception(f"HTTP error {self.status_code}")


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
        assert 'alias.Contains("PXI")' in captured_payloads[0].get("filter", "")

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
        assert 'connected.data.state = "CONNECTED"' in captured_payloads[0].get("filter", "")

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
        assert 'grains.data.kernel.Contains("Windows")' in captured_payloads[0].get("filter", "")

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
        assert 'grains.data.host.Contains("PXI")' in captured_payloads[0].get("filter", "")

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
        assert 'workspace = "ws-1"' in captured_payloads[0].get("filter", "")

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
        assert 'keywords.data.Contains("production")' in captured_payloads[0].get("filter", "")

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
        assert 'properties.data.Location = "Building 5"' in captured_payloads[0].get("filter", "")

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

    def test_list_table_pagination_prompt(self, monkeypatch: Any, runner: CliRunner) -> None:
        """Test that table pagination shows more-available prompt when page is full."""
        patch_keyring(monkeypatch)

        call_count = 0

        def mock_post(*a: Any, **kw: Any) -> Any:
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                # Return exactly take (25) items so pagination triggers
                return MockResponse({"data": [SAMPLE_SYSTEM] * 25})
            return MockResponse({"data": []})

        monkeypatch.setattr("slcli.system_click.make_api_request", mock_post)
        monkeypatch.setattr("slcli.system_click.get_workspace_map", lambda: {})

        cli = make_cli()
        result = runner.invoke(cli, ["system", "list", "-f", "table"], input="n\n")
        assert result.exit_code == 0
        assert "Showing 25 systems" in result.output
        assert "More results may be available" in result.output


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
        assert "Connected:" in result.output
        assert "Disconnected:" in result.output
        assert "Virtual:" in result.output
        assert "Total:" in result.output

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
        result = runner.invoke(cli, ["system", "remove", "minion-PXI-1234"], input="n\n")
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
        result = runner.invoke(cli, ["system", "job", "list", "-f", "table"], input="n\n")
        assert result.exit_code == 0
        assert "Showing 25 jobs" in result.output
        assert "More results may be available" in result.output


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
