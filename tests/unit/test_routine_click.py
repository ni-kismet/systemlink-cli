"""Unit tests for routine_click.py."""

import json
from typing import Any, Dict, Optional
from unittest.mock import MagicMock, patch

import click
import pytest
from click.testing import CliRunner

from slcli.routine_click import register_routine_commands
from slcli.utils import ExitCodes


def make_cli() -> click.Group:
    """Create a test CLI with routine commands registered."""

    @click.group()
    def test_cli() -> None:
        pass

    register_routine_commands(test_cli)
    return test_cli


class MockResponse:
    """Mock HTTP response for testing."""

    def __init__(
        self,
        json_data: Optional[Dict[str, Any]] = None,
        status_code: int = 200,
    ) -> None:
        """Initialize mock response.

        Args:
            json_data: The JSON data to return from json().
            status_code: The HTTP status code.
        """
        self._json_data = json_data or {}
        self._status_code = status_code

    def json(self) -> Dict[str, Any]:
        """Return json data."""
        return self._json_data

    @property
    def status_code(self) -> int:
        """Return status code."""
        return self._status_code

    def raise_for_status(self) -> None:
        """Raise if status >= 400."""
        if self._status_code >= 400:
            from requests.exceptions import HTTPError

            exc = HTTPError(f"HTTP {self._status_code}")
            exc.response = self  # type: ignore
            raise exc


@pytest.fixture(autouse=True)
def mock_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    """Patch get_base_url and get_workspace_map to avoid hitting keyring or network."""
    monkeypatch.setattr("slcli.routine_click.get_base_url", lambda: "http://localhost:8000")
    monkeypatch.setattr(
        "slcli.routine_click.get_workspace_map",
        lambda: {"ws-1": "Default", "ws-2": "Analytics"},
    )
    # resolve_workspace_filter and filter_by_workspace use the mocked workspace_map
    # through get_workspace_map(), so no separate mock is needed.


# ---------------------------------------------------------------------------
# Shared fixture data
# ---------------------------------------------------------------------------

V2_ROUTINE = {
    "id": "abc-123",
    "name": "My v2 routine",
    "description": "Test routine",
    "enabled": True,
    "workspace": "ws-1",
    "event": {"type": "tag", "triggers": []},
    "actions": [{"type": "alarm", "configuration": {}}],
    "createdBy": "user1",
    "updatedBy": "user1",
    "created": "2026-01-01T00:00:00Z",
    "updated": "2026-01-01T00:00:00Z",
}

V1_ROUTINE = {
    "id": "def-456",
    "name": "My v1 routine",
    "description": "Notebook routine",
    "enabled": False,
    "workspace": "ws-2",
    "type": "SCHEDULED",
    "execution": {"type": "NOTEBOOK", "definition": {"notebookId": "nb-001"}},
    "schedule": {"startTime": "2026-01-01T00:00:00Z", "repeat": "HOUR"},
}


# =============================================================================
# list
# =============================================================================


@patch("slcli.routine_click.make_api_request")
def test_list_v2_table(mock_request: MagicMock) -> None:
    """Test routine list with v2 API in table format."""
    mock_request.return_value = MockResponse(json_data={"routines": [V2_ROUTINE]})

    cli = make_cli()
    runner = CliRunner()
    result = runner.invoke(cli, ["routine", "list", "--api-version", "v2", "--format", "table"])

    assert result.exit_code == 0
    assert "My v2 routine" in result.output


@patch("slcli.routine_click.make_api_request")
def test_list_v2_json(mock_request: MagicMock) -> None:
    """Test routine list with v2 API in JSON format."""
    mock_request.return_value = MockResponse(json_data={"routines": [V2_ROUTINE]})

    cli = make_cli()
    runner = CliRunner()
    result = runner.invoke(cli, ["routine", "list", "--api-version", "v2", "--format", "json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert isinstance(data, list)
    assert data[0]["id"] == "abc-123"


@patch("slcli.routine_click.make_api_request")
def test_list_v1_table(mock_request: MagicMock) -> None:
    """Test routine list with v1 API in table format."""
    mock_request.return_value = MockResponse(json_data={"routines": [V1_ROUTINE]})

    cli = make_cli()
    runner = CliRunner()
    result = runner.invoke(cli, ["routine", "list", "--api-version", "v1", "--format", "table"])

    assert result.exit_code == 0
    assert "My v1 routine" in result.output
    assert "SCHEDULED" in result.output


@patch("slcli.routine_click.make_api_request")
def test_list_empty(mock_request: MagicMock) -> None:
    """Test routine list when no routines exist."""
    mock_request.return_value = MockResponse(json_data={"routines": []})

    cli = make_cli()
    runner = CliRunner()
    result = runner.invoke(cli, ["routine", "list"])

    assert result.exit_code == 0
    assert "No routines found" in result.output


@patch("slcli.routine_click.make_api_request")
def test_list_enabled_filter(mock_request: MagicMock) -> None:
    """Test routine list with --enabled passes Enabled=true to the API."""
    mock_request.return_value = MockResponse(json_data={"routines": []})

    cli = make_cli()
    runner = CliRunner()
    runner.invoke(cli, ["routine", "list", "--enabled"])

    call_args = mock_request.call_args
    assert "Enabled=true" in call_args[0][1]


@patch("slcli.routine_click.make_api_request")
def test_list_disabled_filter(mock_request: MagicMock) -> None:
    """Test routine list with --disabled passes Enabled=false to the API."""
    mock_request.return_value = MockResponse(json_data={"routines": []})

    cli = make_cli()
    runner = CliRunner()
    runner.invoke(cli, ["routine", "list", "--disabled"])

    call_args = mock_request.call_args
    assert "Enabled=false" in call_args[0][1]


@patch("slcli.routine_click.make_api_request")
def test_list_default_no_enabled_filter(mock_request: MagicMock) -> None:
    """Test that by default no Enabled filter is sent, so both enabled and disabled are returned."""
    mock_request.return_value = MockResponse(json_data={"routines": []})

    cli = make_cli()
    runner = CliRunner()
    runner.invoke(cli, ["routine", "list"])

    call_args = mock_request.call_args
    assert "Enabled" not in call_args[0][1]


@patch("slcli.routine_click.make_api_request")
def test_list_take_limits_results(mock_request: MagicMock) -> None:
    """Test that --take limits the number of returned routines."""
    routines = [dict(V2_ROUTINE, id=f"id-{i}", name=f"Routine {i}") for i in range(10)]
    mock_request.return_value = MockResponse(json_data={"routines": routines})

    cli = make_cli()
    runner = CliRunner()
    result = runner.invoke(cli, ["routine", "list", "--format", "json", "--take", "3"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 3


@patch("slcli.routine_click.make_api_request")
def test_list_workspace_name_resolved(mock_request: MagicMock) -> None:
    """Test that workspace IDs are resolved to display names in table output."""
    mock_request.return_value = MockResponse(json_data={"routines": [V2_ROUTINE]})

    cli = make_cli()
    runner = CliRunner()
    result = runner.invoke(cli, ["routine", "list", "--format", "table"])

    assert result.exit_code == 0
    # workspace ID "ws-1" should appear as "Default"
    assert "Default" in result.output
    assert "ws-1" not in result.output


@patch("slcli.routine_click.make_api_request")
def test_list_name_filter_matches(mock_request: MagicMock) -> None:
    """Test that --filter returns only routines whose name contains the substring."""
    routines = [
        dict(V2_ROUTINE, id="id-1", name="CPU alarm"),
        dict(V2_ROUTINE, id="id-2", name="Memory alarm"),
        dict(V2_ROUTINE, id="id-3", name="Disk check"),
    ]
    mock_request.return_value = MockResponse(json_data={"routines": routines})

    cli = make_cli()
    runner = CliRunner()
    result = runner.invoke(cli, ["routine", "list", "--format", "json", "--filter", "alarm"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 2
    assert all("alarm" in r["name"].lower() for r in data)


@patch("slcli.routine_click.make_api_request")
def test_list_name_filter_case_insensitive(mock_request: MagicMock) -> None:
    """Test that --filter matching is case-insensitive."""
    routines = [
        dict(V2_ROUTINE, id="id-1", name="CPU Alarm"),
        dict(V2_ROUTINE, id="id-2", name="Disk check"),
    ]
    mock_request.return_value = MockResponse(json_data={"routines": routines})

    cli = make_cli()
    runner = CliRunner()
    result = runner.invoke(cli, ["routine", "list", "--format", "json", "--filter", "ALARM"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 1
    assert data[0]["id"] == "id-1"


@patch("slcli.routine_click.make_api_request")
def test_list_name_filter_no_match(mock_request: MagicMock) -> None:
    """Test that --filter with no matches shows 'No routines found'."""
    mock_request.return_value = MockResponse(
        json_data={"routines": [dict(V2_ROUTINE, name="CPU alarm")]}
    )

    cli = make_cli()
    runner = CliRunner()
    result = runner.invoke(cli, ["routine", "list", "--filter", "something-else"])

    assert result.exit_code == 0
    assert "No routines found" in result.output


@patch("slcli.routine_click.make_api_request")
def test_list_pagination_first_page_non_interactive(mock_request: MagicMock) -> None:
    """Test pagination shows first page and stops in non-interactive (non-TTY) mode."""
    routines = [dict(V2_ROUTINE, id=f"id-{i}", name=f"Routine {i}") for i in range(30)]
    mock_request.return_value = MockResponse(json_data={"routines": routines})

    cli = make_cli()
    runner = CliRunner()
    result = runner.invoke(cli, ["routine", "list", "--format", "table", "--take", "10"])

    assert result.exit_code == 0
    assert "Routine 0" in result.output
    # Pagination message should be shown since there are more items
    assert "Showing 10 of 30" in result.output


@patch("slcli.routine_click.make_api_request")
def test_list_pagination_all_fit_one_page(mock_request: MagicMock) -> None:
    """Test that no pagination prompt is shown when all results fit on one page."""
    routines = [dict(V2_ROUTINE, id=f"id-{i}", name=f"Routine {i}") for i in range(3)]
    mock_request.return_value = MockResponse(json_data={"routines": routines})

    cli = make_cli()
    runner = CliRunner()
    result = runner.invoke(cli, ["routine", "list", "--format", "table", "--take", "25"])

    assert result.exit_code == 0
    assert "Showing" not in result.output


@patch("slcli.routine_click.make_api_request")
def test_list_workspace_filter_by_name(mock_request: MagicMock) -> None:
    """Test --workspace filters routines by workspace name (client-side)."""
    routines = [
        dict(V2_ROUTINE, id="id-1", workspace="ws-1"),
        dict(V2_ROUTINE, id="id-2", workspace="ws-2"),
    ]
    mock_request.return_value = MockResponse(json_data={"routines": routines})
    cli = make_cli()
    runner = CliRunner()
    result = runner.invoke(cli, ["routine", "list", "--format", "json", "--workspace", "Default"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 1
    assert data[0]["id"] == "id-1"


@patch("slcli.routine_click.make_api_request")
def test_list_workspace_filter_by_id(mock_request: MagicMock) -> None:
    """Test --workspace filters routines by workspace ID (client-side)."""
    routines = [
        dict(V2_ROUTINE, id="id-1", workspace="ws-1"),
        dict(V2_ROUTINE, id="id-2", workspace="ws-2"),
    ]
    mock_request.return_value = MockResponse(json_data={"routines": routines})
    cli = make_cli()
    runner = CliRunner()
    result = runner.invoke(cli, ["routine", "list", "--format", "json", "--workspace", "ws-2"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 1
    assert data[0]["id"] == "id-2"


@patch("slcli.routine_click.make_api_request")
def test_list_workspace_table_shows_name(mock_request: MagicMock) -> None:
    """Test --workspace filter combined with table output shows workspace display name."""
    mock_request.return_value = MockResponse(
        json_data={"routines": [dict(V2_ROUTINE, workspace="ws-2")]}
    )
    cli = make_cli()
    runner = CliRunner()
    result = runner.invoke(
        cli, ["routine", "list", "--format", "table", "--workspace", "Analytics"]
    )
    assert result.exit_code == 0
    assert "Analytics" in result.output


@patch("slcli.routine_click.make_api_request")
def test_get_v2_json(mock_request: MagicMock) -> None:
    """Test routine get with v2 API returns JSON."""
    mock_request.return_value = MockResponse(json_data=V2_ROUTINE)

    cli = make_cli()
    runner = CliRunner()
    result = runner.invoke(cli, ["routine", "get", "abc-123", "--api-version", "v2"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["id"] == "abc-123"


@patch("slcli.routine_click.make_api_request")
def test_get_v1_json(mock_request: MagicMock) -> None:
    """Test routine get with v1 API returns JSON."""
    mock_request.return_value = MockResponse(json_data=V1_ROUTINE)

    cli = make_cli()
    runner = CliRunner()
    result = runner.invoke(cli, ["routine", "get", "def-456", "--api-version", "v1"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["id"] == "def-456"


# =============================================================================
# create
# =============================================================================


@patch("slcli.routine_click.make_api_request")
def test_create_v2_success(mock_request: MagicMock) -> None:
    """Test creating a v2 routine with required fields."""
    mock_request.return_value = MockResponse(
        json_data={"id": "new-id-123"},
        status_code=201,
    )

    cli = make_cli()
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "routine",
            "create",
            "--api-version",
            "v2",
            "--name",
            "My routine",
            "--event",
            '{"type":"tag","triggers":[]}',
            "--actions",
            '[{"type":"alarm","configuration":{}}]',
        ],
    )

    assert result.exit_code == 0
    assert "Routine created" in result.output
    assert "new-id-123" in result.output


@patch("slcli.routine_click.make_api_request")
def test_create_v1_scheduled_success(mock_request: MagicMock) -> None:
    """Test creating a v1 scheduled routine."""
    mock_request.return_value = MockResponse(
        json_data={"id": "v1-new-id"},
        status_code=201,
    )

    cli = make_cli()
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "routine",
            "create",
            "--api-version",
            "v1",
            "--name",
            "Notebook routine",
            "--type",
            "SCHEDULED",
            "--notebook-id",
            "nb-001",
            "--schedule",
            '{"startTime":"2026-01-01T00:00:00Z","repeat":"HOUR"}',
        ],
    )

    assert result.exit_code == 0
    assert "Routine created" in result.output


@patch("slcli.routine_click.make_api_request")
def test_create_v1_triggered_success(mock_request: MagicMock) -> None:
    """Test creating a v1 triggered routine."""
    mock_request.return_value = MockResponse(
        json_data={"id": "v1-trigger-id"},
        status_code=201,
    )

    cli = make_cli()
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "routine",
            "create",
            "--api-version",
            "v1",
            "--name",
            "File routine",
            "--type",
            "TRIGGERED",
            "--notebook-id",
            "nb-002",
            "--trigger",
            '{"source":"FILES","events":["CREATED"],"filter":"extension=\\".csv\\""}',
        ],
    )

    assert result.exit_code == 0
    assert "Routine created" in result.output


def test_create_v2_missing_event() -> None:
    """Test that create v2 fails when --event is missing."""
    cli = make_cli()
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "routine",
            "create",
            "--api-version",
            "v2",
            "--name",
            "Bad routine",
            "--actions",
            '[{"type":"alarm"}]',
        ],
    )

    assert result.exit_code == ExitCodes.INVALID_INPUT
    assert "--event is required" in result.output


def test_create_v2_missing_actions() -> None:
    """Test that create v2 fails when --actions is missing."""
    cli = make_cli()
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "routine",
            "create",
            "--api-version",
            "v2",
            "--name",
            "Bad routine",
            "--event",
            '{"type":"tag","triggers":[]}',
        ],
    )

    assert result.exit_code == ExitCodes.INVALID_INPUT
    assert "--actions is required" in result.output


def test_create_v1_missing_type() -> None:
    """Test that create v1 fails when --type is missing."""
    cli = make_cli()
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "routine",
            "create",
            "--api-version",
            "v1",
            "--name",
            "Bad routine",
            "--notebook-id",
            "nb-001",
        ],
    )

    assert result.exit_code == ExitCodes.INVALID_INPUT
    assert "--type is required" in result.output


def test_create_v1_missing_notebook_id() -> None:
    """Test that create v1 fails when --notebook-id is missing."""
    cli = make_cli()
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "routine",
            "create",
            "--api-version",
            "v1",
            "--name",
            "Bad routine",
            "--type",
            "SCHEDULED",
        ],
    )

    assert result.exit_code == ExitCodes.INVALID_INPUT
    assert "--notebook-id is required" in result.output


def test_create_v2_invalid_event_json() -> None:
    """Test that create v2 fails with invalid JSON for --event."""
    cli = make_cli()
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "routine",
            "create",
            "--api-version",
            "v2",
            "--name",
            "Bad routine",
            "--event",
            "not-valid-json",
            "--actions",
            '[{"type":"alarm"}]',
        ],
    )

    assert result.exit_code == ExitCodes.INVALID_INPUT
    assert "Invalid JSON" in result.output


# =============================================================================
# update
# =============================================================================


@patch("slcli.routine_click.make_api_request")
def test_update_v2_name(mock_request: MagicMock) -> None:
    """Test updating a v2 routine name."""
    mock_request.return_value = MockResponse(json_data={}, status_code=200)

    cli = make_cli()
    runner = CliRunner()
    result = runner.invoke(
        cli, ["routine", "update", "abc-123", "--api-version", "v2", "--name", "New name"]
    )

    assert result.exit_code == 0
    assert "Routine updated" in result.output
    payload = mock_request.call_args[1]["payload"]
    assert payload["name"] == "New name"


@patch("slcli.routine_click.make_api_request")
def test_update_v1_notebook_id(mock_request: MagicMock) -> None:
    """Test updating a v1 routine notebook ID."""
    mock_request.return_value = MockResponse(json_data={}, status_code=200)

    cli = make_cli()
    runner = CliRunner()
    result = runner.invoke(
        cli,
        [
            "routine",
            "update",
            "def-456",
            "--api-version",
            "v1",
            "--notebook-id",
            "nb-new",
        ],
    )

    assert result.exit_code == 0
    payload = mock_request.call_args[1]["payload"]
    assert payload["execution"]["definition"]["notebookId"] == "nb-new"


def test_update_no_fields() -> None:
    """Test that update fails when no fields are provided."""
    cli = make_cli()
    runner = CliRunner()
    result = runner.invoke(cli, ["routine", "update", "abc-123"])

    assert result.exit_code == ExitCodes.INVALID_INPUT
    assert "No update fields provided" in result.output


# =============================================================================
# enable / disable
# =============================================================================


@patch("slcli.routine_click.make_api_request")
def test_enable_routine(mock_request: MagicMock) -> None:
    """Test enabling a routine."""
    mock_request.return_value = MockResponse(json_data={}, status_code=200)

    cli = make_cli()
    runner = CliRunner()
    result = runner.invoke(cli, ["routine", "enable", "abc-123"])

    assert result.exit_code == 0
    assert "Routine enabled" in result.output
    payload = mock_request.call_args[1]["payload"]
    assert payload == {"enabled": True}


@patch("slcli.routine_click.make_api_request")
def test_disable_routine(mock_request: MagicMock) -> None:
    """Test disabling a routine."""
    mock_request.return_value = MockResponse(json_data={}, status_code=200)

    cli = make_cli()
    runner = CliRunner()
    result = runner.invoke(cli, ["routine", "disable", "abc-123"])

    assert result.exit_code == 0
    assert "Routine disabled" in result.output
    payload = mock_request.call_args[1]["payload"]
    assert payload == {"enabled": False}


# =============================================================================
# delete
# =============================================================================


@patch("slcli.routine_click.make_api_request")
def test_delete_with_yes_flag(mock_request: MagicMock) -> None:
    """Test deleting a routine with --yes flag skips confirmation."""
    mock_request.return_value = MockResponse(json_data={}, status_code=204)

    cli = make_cli()
    runner = CliRunner()
    result = runner.invoke(cli, ["routine", "delete", "abc-123", "--yes"])

    assert result.exit_code == 0
    assert "Routine deleted" in result.output


@patch("slcli.routine_click.make_api_request")
def test_delete_v1_with_yes_flag(mock_request: MagicMock) -> None:
    """Test deleting a v1 routine with --yes flag."""
    mock_request.return_value = MockResponse(json_data={}, status_code=204)

    cli = make_cli()
    runner = CliRunner()
    result = runner.invoke(cli, ["routine", "delete", "def-456", "--api-version", "v1", "--yes"])

    assert result.exit_code == 0
    assert "Routine deleted" in result.output
    called_url = mock_request.call_args[0][1]
    assert "/v1/routines/def-456" in called_url


def test_delete_aborted_without_yes() -> None:
    """Test that delete prompts for confirmation and aborts when declined."""
    cli = make_cli()
    runner = CliRunner()
    result = runner.invoke(cli, ["routine", "delete", "abc-123"], input="n\n")

    assert result.exit_code != 0
    assert "Aborted" in result.output or result.exit_code == 1
