"""Unit tests for slcli workitem commands."""

import json
from typing import Any, Dict, List

import click
import pytest
from click.testing import CliRunner

from slcli.utils import ExitCodes
from slcli.workitem_click import (
    _fetch_workitems_page,
    _query_all_templates,
    _query_all_workitems,
    register_workitem_commands,
)
from .test_utils import patch_keyring


def make_cli() -> click.Group:
    """Create a minimal CLI for testing."""

    @click.group()
    def cli() -> None:
        pass

    register_workitem_commands(cli)
    return cli


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_workitem(
    wi_id: str = "1000",
    name: str = "Battery Cycle Test",
    wi_type: str = "testplan",
    state: str = "NEW",
    workspace: str = "ws1",
) -> Dict[str, Any]:
    return {
        "id": wi_id,
        "name": name,
        "type": wi_type,
        "state": state,
        "substate": state,
        "workspace": workspace,
        "assignedTo": None,
        "createdAt": "2026-01-01T00:00:00Z",
        "updatedAt": "2026-01-01T00:00:00Z",
    }


def _make_template(
    tmpl_id: str = "2000",
    name: str = "Battery Test Template",
    wi_type: str = "testplan",
    group: str = "Functional",
    workspace: str = "ws1",
) -> Dict[str, Any]:
    return {
        "id": tmpl_id,
        "name": name,
        "type": wi_type,
        "templateGroup": group,
        "workspace": workspace,
        "createdAt": "2026-01-01T00:00:00Z",
        "updatedAt": "2026-01-01T00:00:00Z",
    }


# ---------------------------------------------------------------------------
# workitem list
# ---------------------------------------------------------------------------


def test_list_workitems_table(monkeypatch: Any, runner: CliRunner) -> None:
    """List work items returns a table."""
    patch_keyring(monkeypatch)

    items = [_make_workitem()]

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"workItems": items}

        return R()

    monkeypatch.setattr("requests.post", mock_post)
    monkeypatch.setattr("slcli.workitem_click.get_workspace_map", lambda: {"ws1": "Default"})

    cli = make_cli()
    result = runner.invoke(cli, ["workitem", "list"])
    assert result.exit_code == 0
    assert "Battery Cycle Test" in result.output
    assert "NEW" in result.output


def test_list_workitems_json(monkeypatch: Any, runner: CliRunner) -> None:
    """List work items with --format json returns JSON array."""
    patch_keyring(monkeypatch)

    items = [_make_workitem()]

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"workItems": items}

        return R()

    monkeypatch.setattr("requests.post", mock_post)
    monkeypatch.setattr("slcli.workitem_click.get_workspace_map", lambda: {"ws1": "Default"})

    cli = make_cli()
    result = runner.invoke(cli, ["workitem", "list", "--format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert isinstance(data, list)
    assert data[0]["id"] == "1000"


def test_list_workitems_state_filter(monkeypatch: Any, runner: CliRunner) -> None:
    """--state flag is included in payload filter."""
    patch_keyring(monkeypatch)

    captured: List[Any] = []

    def mock_post(url: str, *a: Any, **kw: Any) -> Any:
        captured.append(kw.get("json") or (a[0] if a else {}))

        class R:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"workItems": []}

        return R()

    monkeypatch.setattr("requests.post", mock_post)
    monkeypatch.setattr("slcli.workitem_click.get_workspace_map", lambda: {})

    cli = make_cli()
    result = runner.invoke(cli, ["workitem", "list", "--state", "NEW", "--format", "json"])
    assert result.exit_code == 0
    # Verify the filter payload contains the state substitution
    assert any("filter" in (p or {}) for p in captured)


def test_list_workitems_empty(monkeypatch: Any, runner: CliRunner) -> None:
    """Empty work items list shows informational message."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"workItems": []}

        return R()

    monkeypatch.setattr("requests.post", mock_post)
    monkeypatch.setattr("slcli.workitem_click.get_workspace_map", lambda: {})

    cli = make_cli()
    result = runner.invoke(cli, ["workitem", "list"])
    assert result.exit_code == 0
    assert "No work items found" in result.output


def test_list_workitems_shows_pagination_prompt(monkeypatch: Any, runner: CliRunner) -> None:
    """Server-side pagination: prompt is shown when a full page + token is returned."""
    patch_keyring(monkeypatch)

    call_count: List[int] = [0]

    def mock_post(*a: Any, **kw: Any) -> Any:
        call_count[0] += 1

        class R:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                # First call: full page of 5 items + continuation token
                if call_count[0] == 1:
                    return {
                        "workItems": [_make_workitem(wi_id=str(i)) for i in range(5)],
                        "continuationToken": "next-page-token",
                    }
                return {"workItems": []}

        return R()

    monkeypatch.setattr("requests.post", mock_post)
    monkeypatch.setattr("slcli.workitem_click.get_workspace_map", lambda: {"ws1": "Default"})

    cli = make_cli()
    # User declines to fetch another page
    result = runner.invoke(cli, ["workitem", "list", "--take", "5"], input="n\n")
    assert result.exit_code == 0
    assert "Showing 5 work item(s). More may be available." in result.output
    assert call_count[0] == 1  # second page never fetched


def test_list_workitems_stale_token_no_prompt(monkeypatch: Any, runner: CliRunner) -> None:
    """Stale token (fewer items than take) never triggers the pagination prompt."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                # 3 items returned when take=5 → stale token should be discarded
                return {
                    "workItems": [_make_workitem(wi_id=str(i)) for i in range(3)],
                    "continuationToken": "stale-token",
                }

        return R()

    monkeypatch.setattr("requests.post", mock_post)
    monkeypatch.setattr("slcli.workitem_click.get_workspace_map", lambda: {"ws1": "Default"})

    cli = make_cli()
    result = runner.invoke(cli, ["workitem", "list", "--take", "5"])
    assert result.exit_code == 0
    assert "More may be available" not in result.output


def test_fetch_workitems_page_discards_stale_token(monkeypatch: Any) -> None:
    """_fetch_workitems_page discards token when page size < take (stale-token guard)."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {
                    "workItems": [_make_workitem()],  # 1 item, take=5
                    "continuationToken": "stale-token",
                }

        return R()

    monkeypatch.setattr("requests.post", mock_post)

    items, next_token = _fetch_workitems_page(None, None, None, 5, None)
    assert len(items) == 1
    assert next_token is None  # stale token discarded


def test_fetch_workitems_page_keeps_valid_token(monkeypatch: Any) -> None:
    """_fetch_workitems_page preserves token when a full page is returned."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {
                    "workItems": [_make_workitem(wi_id=str(i)) for i in range(5)],
                    "continuationToken": "valid-token",
                }

        return R()

    monkeypatch.setattr("requests.post", mock_post)

    items, next_token = _fetch_workitems_page(None, None, None, 5, None)
    assert len(items) == 5
    assert next_token == "valid-token"


def test_query_all_workitems_max_items_caps_results(monkeypatch: Any) -> None:
    """_query_all_workitems max_items parameter caps pagination regardless of stale tokens."""
    patch_keyring(monkeypatch)

    call_count: List[int] = [0]

    def mock_post(*a: Any, **kw: Any) -> Any:
        call_count[0] += 1

        class R:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {
                    "workItems": [_make_workitem(wi_id=str(call_count[0] * 10))],
                    "continuationToken": "stale-token",
                }

        return R()

    monkeypatch.setattr("requests.post", mock_post)

    items = _query_all_workitems(max_items=3)
    assert len(items) == 3
    assert call_count[0] == 3


def test_query_all_templates_max_items_caps_results(monkeypatch: Any) -> None:
    """_query_all_templates max_items parameter caps pagination regardless of stale tokens."""
    patch_keyring(monkeypatch)

    call_count: List[int] = [0]

    def mock_post(*a: Any, **kw: Any) -> Any:
        call_count[0] += 1

        class R:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {
                    "workItemTemplates": [_make_template(tmpl_id=str(call_count[0] * 10))],
                    "continuationToken": "stale-token",
                }

        return R()

    monkeypatch.setattr("requests.post", mock_post)

    items = _query_all_templates(max_items=2)
    assert len(items) == 2
    assert call_count[0] == 2


def test_list_workitems_empty_page_stops_loop(monkeypatch: Any, runner: CliRunner) -> None:
    """An empty page halts pagination even when a continuation token is returned."""
    patch_keyring(monkeypatch)

    call_count: List[int] = [0]

    def mock_post(*a: Any, **kw: Any) -> Any:
        call_count[0] += 1

        class R:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                # First call returns items; subsequent calls return an empty page
                # but still include a continuation token (the bug scenario).
                if call_count[0] == 1:
                    return {
                        "workItems": [_make_workitem()],
                        "continuationToken": "buggy-token",
                    }
                return {"workItems": [], "continuationToken": "buggy-token"}

        return R()

    monkeypatch.setattr("requests.post", mock_post)
    monkeypatch.setattr("slcli.workitem_click.get_workspace_map", lambda: {"ws1": "Default"})

    cli = make_cli()
    result = runner.invoke(cli, ["workitem", "list", "--format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    # Should only contain the single item from the first page
    assert len(data) == 1
    # Loop must have stopped after the empty page (2 calls total, not infinite)
    assert call_count[0] == 2


def test_list_templates_empty_page_stops_loop(monkeypatch: Any, runner: CliRunner) -> None:
    """An empty template page halts pagination even with a stale continuation token."""
    patch_keyring(monkeypatch)

    call_count: List[int] = [0]

    def mock_post(*a: Any, **kw: Any) -> Any:
        call_count[0] += 1

        class R:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                if call_count[0] == 1:
                    return {
                        "workItemTemplates": [_make_template()],
                        "continuationToken": "buggy-token",
                    }
                return {"workItemTemplates": [], "continuationToken": "buggy-token"}

        return R()

    monkeypatch.setattr("requests.post", mock_post)
    monkeypatch.setattr("slcli.workitem_click.get_workspace_map", lambda: {"ws1": "Default"})

    cli = make_cli()
    result = runner.invoke(cli, ["workitem", "template", "list", "--format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 1
    assert call_count[0] == 2

    # ---------------------------------------------------------------------------
    # workitem get
    # ---------------------------------------------------------------------------
    # Get a work item by ID renders key fields.
    patch_keyring(monkeypatch)

    item = _make_workitem()

    def mock_get(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return item

        return R()

    monkeypatch.setattr("requests.get", mock_get)
    monkeypatch.setattr("slcli.workitem_click.get_workspace_map", lambda: {"ws1": "Default"})

    cli = make_cli()
    result = runner.invoke(cli, ["workitem", "get", "1000"])
    assert result.exit_code == 0
    assert "Battery Cycle Test" in result.output
    assert "NEW" in result.output


def test_get_workitem_json(monkeypatch: Any, runner: CliRunner) -> None:
    """Get a work item with --format json returns raw JSON."""
    patch_keyring(monkeypatch)

    item = _make_workitem()

    def mock_get(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return item

        return R()

    monkeypatch.setattr("requests.get", mock_get)
    monkeypatch.setattr("slcli.workitem_click.get_workspace_map", lambda: {"ws1": "Default"})

    cli = make_cli()
    result = runner.invoke(cli, ["workitem", "get", "1000", "--format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["id"] == "1000"


# ---------------------------------------------------------------------------
# workitem create
# ---------------------------------------------------------------------------


def test_create_workitem_success(monkeypatch: Any, runner: CliRunner) -> None:
    """Create a work item with basic flags returns success message."""
    patch_keyring(monkeypatch)

    created = _make_workitem()

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 201
            text = json.dumps({"createdWorkItems": [created]})

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"createdWorkItems": [created]}

        return R()

    monkeypatch.setattr("requests.post", mock_post)

    cli = make_cli()
    result = runner.invoke(
        cli,
        ["workitem", "create", "--name", "Battery Test", "--type", "testplan"],
    )
    assert result.exit_code == 0
    assert "created" in result.output.lower()


def test_create_workitem_readonly_mode(monkeypatch: Any, runner: CliRunner) -> None:
    """Create is blocked in readonly mode."""
    patch_keyring(monkeypatch)

    monkeypatch.setattr(
        "slcli.utils.check_readonly_mode",
        lambda *a, **kw: (_ for _ in ()).throw(SystemExit(ExitCodes.PERMISSION_DENIED)),
    )

    cli = make_cli()
    result = runner.invoke(cli, ["workitem", "create", "--name", "x"])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# workitem update
# ---------------------------------------------------------------------------


def test_update_workitem_success(monkeypatch: Any, runner: CliRunner) -> None:
    """Update a work item by ID succeeds."""
    patch_keyring(monkeypatch)

    updated = _make_workitem(state="IN_PROGRESS")

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200
            text = json.dumps({"updatedWorkItems": [updated]})

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"updatedWorkItems": [updated]}

        return R()

    monkeypatch.setattr("requests.post", mock_post)

    cli = make_cli()
    result = runner.invoke(cli, ["workitem", "update", "1000", "--state", "IN_PROGRESS"])
    assert result.exit_code == 0
    assert "updated" in result.output.lower()


# ---------------------------------------------------------------------------
# workitem delete
# ---------------------------------------------------------------------------


def test_delete_workitem_success(monkeypatch: Any, runner: CliRunner) -> None:
    """Delete a work item with --yes skips confirmation."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200
            text = json.dumps({"deletedWorkItemIds": ["1000"], "failedWorkItemIds": []})

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"deletedWorkItemIds": ["1000"], "failedWorkItemIds": []}

        return R()

    monkeypatch.setattr("requests.post", mock_post)

    cli = make_cli()
    result = runner.invoke(cli, ["workitem", "delete", "1000", "--yes"])
    assert result.exit_code == 0
    assert "1000" in result.output


def test_delete_workitem_no_confirmation(monkeypatch: Any, runner: CliRunner) -> None:
    """Delete aborts when user declines confirmation."""
    patch_keyring(monkeypatch)

    cli = make_cli()
    result = runner.invoke(cli, ["workitem", "delete", "1000"], input="n\n")
    assert result.exit_code == 0
    assert "Aborted" in result.output


# ---------------------------------------------------------------------------
# workitem execute
# ---------------------------------------------------------------------------


def test_execute_workitem_success(monkeypatch: Any, runner: CliRunner) -> None:
    """Execute an action on a work item."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200
            text = json.dumps({"result": {"type": "MANUAL"}})

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"result": {"type": "MANUAL"}}

        return R()

    monkeypatch.setattr("requests.post", mock_post)

    cli = make_cli()
    result = runner.invoke(cli, ["workitem", "execute", "1000", "--action", "START"])
    assert result.exit_code == 0
    assert "START" in result.output


def test_execute_workitem_requires_action(monkeypatch: Any, runner: CliRunner) -> None:
    """Execute command requires --action option."""
    patch_keyring(monkeypatch)

    cli = make_cli()
    result = runner.invoke(cli, ["workitem", "execute", "1000"])
    assert result.exit_code != 0


# ---------------------------------------------------------------------------
# workitem schedule
# ---------------------------------------------------------------------------


def test_schedule_workitem_success(monkeypatch: Any, runner: CliRunner) -> None:
    """Schedule a work item with a start time."""
    patch_keyring(monkeypatch)

    scheduled = _make_workitem(state="SCHEDULED")

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200
            text = json.dumps({"scheduledWorkItems": [scheduled]})

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"scheduledWorkItems": [scheduled]}

        return R()

    monkeypatch.setattr("requests.post", mock_post)

    cli = make_cli()
    result = runner.invoke(
        cli,
        ["workitem", "schedule", "1000", "--start", "2026-03-01T09:00:00Z"],
    )
    assert result.exit_code == 0
    assert "scheduled" in result.output.lower()


def test_schedule_workitem_no_options(monkeypatch: Any, runner: CliRunner) -> None:
    """Schedule without any date/duration options exits with invalid input."""
    patch_keyring(monkeypatch)

    cli = make_cli()
    result = runner.invoke(cli, ["workitem", "schedule", "1000"])
    assert result.exit_code == ExitCodes.INVALID_INPUT


# ---------------------------------------------------------------------------
# workitem template list
# ---------------------------------------------------------------------------


def test_list_templates_table(monkeypatch: Any, runner: CliRunner) -> None:
    """List templates returns a table."""
    patch_keyring(monkeypatch)

    templates = [_make_template()]

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"workItemTemplates": templates}

        return R()

    monkeypatch.setattr("requests.post", mock_post)
    monkeypatch.setattr("slcli.workitem_click.get_workspace_map", lambda: {"ws1": "Default"})

    cli = make_cli()
    result = runner.invoke(cli, ["workitem", "template", "list"])
    assert result.exit_code == 0
    assert "Battery Test Template" in result.output
    assert "Functional" in result.output


def test_list_templates_json(monkeypatch: Any, runner: CliRunner) -> None:
    """List templates with --format json returns JSON array."""
    patch_keyring(monkeypatch)

    templates = [_make_template()]

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"workItemTemplates": templates}

        return R()

    monkeypatch.setattr("requests.post", mock_post)
    monkeypatch.setattr("slcli.workitem_click.get_workspace_map", lambda: {"ws1": "Default"})

    cli = make_cli()
    result = runner.invoke(cli, ["workitem", "template", "list", "--format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["id"] == "2000"


def test_list_templates_empty(monkeypatch: Any, runner: CliRunner) -> None:
    """Empty template list shows informational message."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"workItemTemplates": []}

        return R()

    monkeypatch.setattr("requests.post", mock_post)
    monkeypatch.setattr("slcli.workitem_click.get_workspace_map", lambda: {})

    cli = make_cli()
    result = runner.invoke(cli, ["workitem", "template", "list"])
    assert result.exit_code == 0
    assert "No templates found" in result.output


# ---------------------------------------------------------------------------
# workitem template get
# ---------------------------------------------------------------------------


def test_get_template_table(monkeypatch: Any, runner: CliRunner) -> None:
    """Get a template by ID renders key fields."""
    patch_keyring(monkeypatch)

    tmpl = _make_template()

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"workItemTemplates": [tmpl]}

        return R()

    monkeypatch.setattr("requests.post", mock_post)
    monkeypatch.setattr("slcli.workitem_click.get_workspace_map", lambda: {"ws1": "Default"})

    cli = make_cli()
    result = runner.invoke(cli, ["workitem", "template", "get", "2000"])
    assert result.exit_code == 0
    assert "Battery Test Template" in result.output
    assert "Functional" in result.output


def test_get_template_not_found(monkeypatch: Any, runner: CliRunner) -> None:
    """Get a template that doesn't exist exits with NOT_FOUND."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"workItemTemplates": []}

        return R()

    monkeypatch.setattr("requests.post", mock_post)

    cli = make_cli()
    result = runner.invoke(cli, ["workitem", "template", "get", "9999"])
    assert result.exit_code == ExitCodes.NOT_FOUND


# ---------------------------------------------------------------------------
# workitem template create
# ---------------------------------------------------------------------------


def test_create_template_success(monkeypatch: Any, runner: CliRunner) -> None:
    """Create a template with required flags."""
    patch_keyring(monkeypatch)

    created = _make_template()

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 201
            text = json.dumps({"createdWorkItemTemplates": [created]})

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"createdWorkItemTemplates": [created]}

        return R()

    monkeypatch.setattr("requests.post", mock_post)

    cli = make_cli()
    result = runner.invoke(
        cli,
        [
            "workitem",
            "template",
            "create",
            "--name",
            "Battery Test Template",
            "--type",
            "testplan",
            "--template-group",
            "Functional",
        ],
    )
    assert result.exit_code == 0
    assert "created" in result.output.lower()


def test_create_template_missing_required(monkeypatch: Any, runner: CliRunner) -> None:
    """Create template without required options exits with INVALID_INPUT."""
    patch_keyring(monkeypatch)

    cli = make_cli()
    result = runner.invoke(cli, ["workitem", "template", "create", "--name", "Incomplete"])
    assert result.exit_code == ExitCodes.INVALID_INPUT


# ---------------------------------------------------------------------------
# workitem template delete
# ---------------------------------------------------------------------------


def test_delete_template_success(monkeypatch: Any, runner: CliRunner) -> None:
    """Delete a template with --yes bypasses confirmation."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200
            text = json.dumps(
                {"deletedWorkItemTemplateIds": ["2000"], "failedWorkItemTemplateIds": []}
            )

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {
                    "deletedWorkItemTemplateIds": ["2000"],
                    "failedWorkItemTemplateIds": [],
                }

        return R()

    monkeypatch.setattr("requests.post", mock_post)

    cli = make_cli()
    result = runner.invoke(cli, ["workitem", "template", "delete", "2000", "--yes"])
    assert result.exit_code == 0
    assert "2000" in result.output


# ---------------------------------------------------------------------------
# workitem workflow list (refactored)
# ---------------------------------------------------------------------------


def test_list_workflows_table(monkeypatch: Any, runner: CliRunner) -> None:
    """List workflows under workitem workflow subgroup."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {
                    "workflows": [
                        {
                            "id": "wf1",
                            "name": "Battery Cycle Workflow",
                            "workspace": "ws1",
                            "description": "Test",
                        }
                    ]
                }

        return R()

    monkeypatch.setattr("requests.post", mock_post)
    monkeypatch.setattr("slcli.workitem_click.get_workspace_map", lambda: {"ws1": "Default"})

    cli = make_cli()
    result = runner.invoke(cli, ["workitem", "workflow", "list"])
    assert result.exit_code == 0
    assert "Battery Cycle Workflow" in result.output


def test_list_workflows_json(monkeypatch: Any, runner: CliRunner) -> None:
    """List workflows with --format json returns a JSON array."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"workflows": [{"id": "wf1", "name": "Test WF", "workspace": "ws1"}]}

        return R()

    monkeypatch.setattr("requests.post", mock_post)
    monkeypatch.setattr("slcli.workitem_click.get_workspace_map", lambda: {"ws1": "Default"})

    cli = make_cli()
    result = runner.invoke(cli, ["workitem", "workflow", "list", "--format", "json"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["id"] == "wf1"


def test_list_workflows_empty(monkeypatch: Any, runner: CliRunner) -> None:
    """Empty workflow list shows informational message."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"workflows": []}

        return R()

    monkeypatch.setattr("requests.post", mock_post)
    monkeypatch.setattr("slcli.workitem_click.get_workspace_map", lambda: {})

    cli = make_cli()
    result = runner.invoke(cli, ["workitem", "workflow", "list"])
    assert result.exit_code == 0
    assert "No workflows found" in result.output


# ---------------------------------------------------------------------------
# workitem workflow get
# ---------------------------------------------------------------------------


def test_get_workflow_by_id(monkeypatch: Any, runner: CliRunner) -> None:
    """Get a workflow by ID renders details."""
    patch_keyring(monkeypatch)

    wf = {"id": "wf1", "name": "My Workflow", "workspace": "ws1", "description": "desc"}

    def mock_get(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return wf

        return R()

    monkeypatch.setattr("requests.get", mock_get)
    monkeypatch.setattr("slcli.workitem_click.get_workspace_map", lambda: {"ws1": "Default"})

    cli = make_cli()
    result = runner.invoke(cli, ["workitem", "workflow", "get", "--id", "wf1"])
    assert result.exit_code == 0
    assert "My Workflow" in result.output


def test_get_workflow_requires_id_or_name(monkeypatch: Any, runner: CliRunner) -> None:
    """Get workflow without --id or --name exits with INVALID_INPUT."""
    patch_keyring(monkeypatch)

    cli = make_cli()
    result = runner.invoke(cli, ["workitem", "workflow", "get"])
    assert result.exit_code == ExitCodes.INVALID_INPUT


def test_get_workflow_id_and_name_exclusive(monkeypatch: Any, runner: CliRunner) -> None:
    """Get workflow with both --id and --name exits with INVALID_INPUT."""
    patch_keyring(monkeypatch)

    cli = make_cli()
    result = runner.invoke(cli, ["workitem", "workflow", "get", "--id", "wf1", "--name", "My WF"])
    assert result.exit_code == ExitCodes.INVALID_INPUT


# ---------------------------------------------------------------------------
# workitem workflow export
# ---------------------------------------------------------------------------


def test_export_workflow_success(monkeypatch: Any, runner: CliRunner) -> None:
    """Export a workflow by ID writes a JSON file."""
    patch_keyring(monkeypatch)

    wf = {"id": "wf123", "name": "Test Workflow", "description": "desc", "workspace": "ws1"}

    def mock_get(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return wf

        return R()

    monkeypatch.setattr("requests.get", mock_get)

    cli = make_cli()
    with runner.isolated_filesystem():
        result = runner.invoke(
            cli, ["workitem", "workflow", "export", "--id", "wf123", "--output", "out.json"]
        )
        assert result.exit_code == 0
        assert "Workflow exported to out.json" in result.output
        import os

        assert os.path.exists("out.json")


def test_export_workflow_not_found(monkeypatch: Any, runner: CliRunner) -> None:
    """Export of a nonexistent workflow exits with NOT_FOUND."""
    patch_keyring(monkeypatch)

    def mock_get(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return None

        return R()

    monkeypatch.setattr("requests.get", mock_get)

    cli = make_cli()
    with runner.isolated_filesystem():
        result = runner.invoke(
            cli,
            ["workitem", "workflow", "export", "--id", "nonexistent", "--output", "out.json"],
        )
        assert result.exit_code == ExitCodes.NOT_FOUND


# ---------------------------------------------------------------------------
# workitem workflow import
# ---------------------------------------------------------------------------


def test_import_workflow_success(monkeypatch: Any, runner: CliRunner) -> None:
    """Import a workflow from a JSON file succeeds."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 201
            text = '{"id": "wf123"}'

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"id": "wf123"}

        return R()

    def mock_get(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"workspaces": [{"id": "ws456", "name": "Default"}]}

        return R()

    monkeypatch.setattr("requests.post", mock_post)
    monkeypatch.setattr("requests.get", mock_get)

    cli = make_cli()
    with runner.isolated_filesystem():
        workflow_data = {
            "name": "Test Workflow",
            "description": "Test description",
            "workspace": "ws456",
        }
        with open("test_workflow.json", "w") as f:
            json.dump(workflow_data, f)

        result = runner.invoke(
            cli, ["workitem", "workflow", "import", "--file", "test_workflow.json"]
        )
        assert result.exit_code == 0
        assert "Workflow imported successfully" in result.output


def test_import_workflow_failure(monkeypatch: Any, runner: CliRunner) -> None:
    """Import workflow with rejected data reports error and exits non-zero."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 400
            text = '{"error": {"name": "Skyline.WorkOrder.InputValidationError", "message": "Validation failed", "args": [], "innerErrors": []}}'

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {
                    "error": {
                        "name": "Skyline.WorkOrder.InputValidationError",
                        "message": "Validation failed",
                        "args": [],
                        "innerErrors": [],
                    }
                }

        return R()

    def mock_get(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"workspaces": [{"id": "ws456", "name": "Default"}]}

        return R()

    monkeypatch.setattr("requests.post", mock_post)
    monkeypatch.setattr("requests.get", mock_get)

    cli = make_cli()
    with runner.isolated_filesystem():
        with open("bad_workflow.json", "w") as f:
            json.dump({"name": "Bad Workflow", "workspace": "ws456"}, f)

        result = runner.invoke(
            cli, ["workitem", "workflow", "import", "--file", "bad_workflow.json"]
        )
        assert result.exit_code == 1
        assert "Workflow import failed" in result.output


# ---------------------------------------------------------------------------
# workitem workflow delete
# ---------------------------------------------------------------------------


def test_delete_workflow_success(monkeypatch: Any, runner: CliRunner) -> None:
    """Delete a workflow by ID succeeds."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 204
            text = ""

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:  # pragma: no cover
                return {}

        return R()

    monkeypatch.setattr("requests.post", mock_post)

    cli = make_cli()
    result = runner.invoke(cli, ["workitem", "workflow", "delete", "--id", "wf123"], input="y\n")
    assert result.exit_code == 0
    assert "deleted successfully" in result.output


def test_delete_workflow_failure(monkeypatch: Any, runner: CliRunner) -> None:
    """Delete workflow that does not exist exits non-zero."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200
            text = json.dumps(
                {
                    "deletedWorkflowIds": [],
                    "failedWorkflowIds": ["nonexistent"],
                    "error": {
                        "name": "Skyline.OneOrMoreErrorsOccurred",
                        "code": -251041,
                        "message": "One or more errors occurred.",
                        "args": [],
                        "innerErrors": [
                            {
                                "name": "Skyline.WorkOrder.WorkflowNotFoundOrNoAccess",
                                "code": None,
                                "message": "Workflow nonexistent does not exist.",
                                "resourceType": "workflow",
                                "resourceId": "nonexistent",
                                "args": ["nonexistent"],
                                "innerErrors": [],
                            }
                        ],
                    },
                }
            )

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {
                    "deletedWorkflowIds": [],
                    "failedWorkflowIds": ["nonexistent"],
                    "error": {
                        "name": "Skyline.OneOrMoreErrorsOccurred",
                        "code": -251041,
                        "message": "One or more errors occurred.",
                        "args": [],
                        "innerErrors": [
                            {
                                "name": "Skyline.WorkOrder.WorkflowNotFoundOrNoAccess",
                                "code": None,
                                "message": "Workflow nonexistent does not exist.",
                                "resourceType": "workflow",
                                "resourceId": "nonexistent",
                                "args": ["nonexistent"],
                                "innerErrors": [],
                            }
                        ],
                    },
                }

        return R()

    monkeypatch.setattr("requests.post", mock_post)

    cli = make_cli()
    result = runner.invoke(
        cli, ["workitem", "workflow", "delete", "--id", "nonexistent"], input="y\n"
    )
    assert result.exit_code != 0
    assert "Failed to delete workflow" in result.output


# ---------------------------------------------------------------------------
# workitem workflow update
# ---------------------------------------------------------------------------


def test_update_workflow_success(monkeypatch: Any, runner: CliRunner) -> None:
    """Update a workflow from a JSON file succeeds."""
    patch_keyring(monkeypatch)

    def mock_put(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200
            text = ""

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {}

        return R()

    monkeypatch.setattr("requests.put", mock_put)

    cli = make_cli()
    with runner.isolated_filesystem():
        with open("updated_workflow.json", "w") as f:
            json.dump({"name": "Updated Workflow", "description": "Updated"}, f)

        result = runner.invoke(
            cli,
            [
                "workitem",
                "workflow",
                "update",
                "--id",
                "wf123",
                "--file",
                "updated_workflow.json",
            ],
        )
        assert result.exit_code == 0
        assert "updated successfully" in result.output


# ---------------------------------------------------------------------------
# workitem workflow init
# ---------------------------------------------------------------------------


def test_init_workflow_writes_file(monkeypatch: Any, runner: CliRunner, tmp_path: Any) -> None:
    """Init command creates a workflow JSON file."""
    patch_keyring(monkeypatch)

    def mock_get(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"workspaces": [{"id": "ws1", "name": "Default"}]}

        return R()

    monkeypatch.setattr("requests.get", mock_get)

    cli = make_cli()
    output_file = str(tmp_path / "my-workflow.json")
    result = runner.invoke(
        cli,
        [
            "workitem",
            "workflow",
            "init",
            "--name",
            "My Workflow",
            "--description",
            "Test workflow",
            "--output",
            output_file,
        ],
    )
    assert result.exit_code == 0
    assert "Workflow initialized" in result.output

    import os

    assert os.path.exists(output_file)
    with open(output_file) as fh:
        data = json.load(fh)
    assert data["name"] == "My Workflow"
    assert "states" in data
    assert "actions" in data


# ---------------------------------------------------------------------------
# workitem workflow preview
# ---------------------------------------------------------------------------


def test_preview_workflow_mmd_output(monkeypatch: Any, runner: CliRunner, tmp_path: Any) -> None:
    """Preview --format mmd writes a Mermaid file from a local workflow JSON."""
    patch_keyring(monkeypatch)

    wf_data = {
        "name": "Sample",
        "actions": [
            {
                "name": "START",
                "displayText": "Start",
                "privilegeSpecificity": [],
                "executionAction": {"type": "MANUAL", "action": "START"},
            }
        ],
        "states": [
            {
                "name": "NEW",
                "dashboardAvailable": False,
                "defaultSubstate": "NEW",
                "substates": [
                    {
                        "name": "NEW",
                        "displayText": "New",
                        "availableActions": [
                            {
                                "action": "START",
                                "nextState": "DONE",
                                "nextSubstate": "DONE",
                                "showInUI": True,
                            }
                        ],
                    }
                ],
            },
            {
                "name": "DONE",
                "dashboardAvailable": False,
                "defaultSubstate": "DONE",
                "substates": [{"name": "DONE", "displayText": "Done", "availableActions": []}],
            },
        ],
    }

    cli = make_cli()
    input_file = str(tmp_path / "wf.json")
    output_file = str(tmp_path / "wf.mmd")
    with open(input_file, "w") as fh:
        json.dump(wf_data, fh)

    result = runner.invoke(
        cli,
        [
            "workitem",
            "workflow",
            "preview",
            "--file",
            input_file,
            "--format",
            "mmd",
            "--output",
            output_file,
        ],
    )
    assert result.exit_code == 0
    assert "Mermaid diagram saved" in result.output

    import os

    assert os.path.exists(output_file)


# ---------------------------------------------------------------------------
# Additional coverage: filter expression, workspace, take in JSON, create JSON
# ---------------------------------------------------------------------------


def test_list_workitems_json_respects_take(monkeypatch: Any, runner: CliRunner) -> None:
    """JSON mode passes --take as max_items, capping pagination at that limit."""
    patch_keyring(monkeypatch)

    call_count: List[int] = [0]

    def mock_post(*a: Any, **kw: Any) -> Any:
        call_count[0] += 1

        class R:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                # Always return 100 items with a stale token to trigger the cap
                return {
                    "workItems": [
                        _make_workitem(wi_id=str(call_count[0] * 100 + i)) for i in range(100)
                    ],
                    "continuationToken": "stale-token",
                }

        return R()

    monkeypatch.setattr("requests.post", mock_post)
    monkeypatch.setattr("slcli.workitem_click.get_workspace_map", lambda: {})

    cli = make_cli()
    result = runner.invoke(cli, ["workitem", "list", "--format", "json", "--take", "50"])
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert isinstance(data, list)
    assert len(data) == 50  # capped by max_items=take


def test_list_workitems_with_filter_expression(monkeypatch: Any, runner: CliRunner) -> None:
    """--filter expression is offset when combined with --state substitutions."""
    patch_keyring(monkeypatch)

    captured_payloads: List[Any] = []

    def mock_post(url: str, *a: Any, **kw: Any) -> Any:
        captured_payloads.append(kw.get("json") or (a[0] if a else {}))

        class R:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"workItems": []}

        return R()

    monkeypatch.setattr("requests.post", mock_post)
    monkeypatch.setattr("slcli.workitem_click.get_workspace_map", lambda: {})

    cli = make_cli()
    # Using both --state (adds @0) and --filter with @0 (should be offset to @1)
    result = runner.invoke(
        cli,
        ["workitem", "list", "--state", "NEW", "--filter", "name == @0", "--format", "json"],
    )
    assert result.exit_code == 0
    # The combined filter should have the state sub at @0 and the filter sub offset to @1
    payload = captured_payloads[0] if captured_payloads else {}
    assert "filter" in payload
    # @0 is for state, @1 should be the offset user filter
    assert "@1" in payload["filter"]


def test_list_workitems_with_workspace_filter_unit(monkeypatch: Any, runner: CliRunner) -> None:
    """--workspace flag resolves workspace and passes ID to API query."""
    patch_keyring(monkeypatch)

    captured_payloads: List[Any] = []

    def mock_post(url: str, *a: Any, **kw: Any) -> Any:
        captured_payloads.append(kw.get("json") or (a[0] if a else {}))

        class R:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"workItems": [_make_workitem()]}

        return R()

    def mock_get(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"workspaces": [{"id": "ws1", "name": "Default"}]}

        return R()

    monkeypatch.setattr("requests.post", mock_post)
    monkeypatch.setattr("requests.get", mock_get)
    monkeypatch.setattr("slcli.workitem_click.get_workspace_map", lambda: {"ws1": "Default"})

    cli = make_cli()
    result = runner.invoke(cli, ["workitem", "list", "--workspace", "Default", "--format", "json"])
    assert result.exit_code == 0
    payload = captured_payloads[0] if captured_payloads else {}
    assert "substitutions" in payload
    assert "ws1" in payload["substitutions"]


def test_create_workitem_json_format(monkeypatch: Any, runner: CliRunner) -> None:
    """Create with --format json outputs the created work item as JSON."""
    patch_keyring(monkeypatch)

    created = _make_workitem()

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 201
            text = json.dumps({"createdWorkItems": [created]})

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"createdWorkItems": [created]}

        return R()

    monkeypatch.setattr("requests.post", mock_post)

    cli = make_cli()
    result = runner.invoke(
        cli,
        ["workitem", "create", "--name", "Battery Test", "--type", "testplan", "--format", "json"],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["id"] == "1000"


def test_execute_workitem_readonly_mode(monkeypatch: Any, runner: CliRunner) -> None:
    """Execute is blocked in readonly mode."""
    patch_keyring(monkeypatch)

    monkeypatch.setattr(
        "slcli.utils.check_readonly_mode",
        lambda *a, **kw: (_ for _ in ()).throw(SystemExit(ExitCodes.PERMISSION_DENIED)),
    )

    cli = make_cli()
    result = runner.invoke(cli, ["workitem", "execute", "1000", "--action", "START"])
    assert result.exit_code != 0


def test_update_template_success(monkeypatch: Any, runner: CliRunner) -> None:
    """Update a template by ID succeeds."""
    patch_keyring(monkeypatch)

    updated = _make_template(name="Updated Template")

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200
            text = json.dumps({"updatedWorkItemTemplates": [updated]})

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"updatedWorkItemTemplates": [updated]}

        return R()

    monkeypatch.setattr("requests.post", mock_post)

    cli = make_cli()
    result = runner.invoke(
        cli,
        ["workitem", "template", "update", "2000", "--name", "Updated Template"],
    )
    assert result.exit_code == 0
    assert "updated" in result.output.lower()


def test_list_templates_json_respects_take(monkeypatch: Any, runner: CliRunner) -> None:
    """Template JSON mode caps results at --take via max_items."""
    patch_keyring(monkeypatch)

    call_count: List[int] = [0]

    def mock_post(*a: Any, **kw: Any) -> Any:
        call_count[0] += 1

        class R:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {
                    "workItemTemplates": [
                        _make_template(tmpl_id=str(call_count[0] * 100 + i)) for i in range(100)
                    ],
                    "continuationToken": "stale-token",
                }

        return R()

    monkeypatch.setattr("requests.post", mock_post)
    monkeypatch.setattr("slcli.workitem_click.get_workspace_map", lambda: {})

    cli = make_cli()
    result = runner.invoke(
        cli, ["workitem", "template", "list", "--format", "json", "--take", "30"]
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 30


def test_list_workflows_json_respects_take(monkeypatch: Any, runner: CliRunner) -> None:
    """Workflow JSON mode caps results at --take via max_items."""
    patch_keyring(monkeypatch)

    call_count: List[int] = [0]

    def mock_post(*a: Any, **kw: Any) -> Any:
        call_count[0] += 1

        class R:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {
                    "workflows": [
                        {"id": f"wf{call_count[0] * 100 + i}", "name": f"WF{i}", "workspace": "ws1"}
                        for i in range(100)
                    ],
                    "continuationToken": "stale-token",
                }

        return R()

    monkeypatch.setattr("requests.post", mock_post)
    monkeypatch.setattr("slcli.workitem_click.get_workspace_map", lambda: {})

    cli = make_cli()
    result = runner.invoke(
        cli, ["workitem", "workflow", "list", "--format", "json", "--take", "20"]
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert len(data) == 20


def test_get_workflow_by_name_lookup(monkeypatch: Any, runner: CliRunner) -> None:
    """Get workflow by --name queries the list and then fetches by ID."""
    patch_keyring(monkeypatch)

    wf = {"id": "wf-abc", "name": "Named Workflow", "workspace": "ws1", "description": ""}

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"workflows": [wf]}

        return R()

    def mock_get(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return wf

        return R()

    monkeypatch.setattr("requests.post", mock_post)
    monkeypatch.setattr("requests.get", mock_get)
    monkeypatch.setattr("slcli.workitem_click.get_workspace_map", lambda: {"ws1": "Default"})

    cli = make_cli()
    result = runner.invoke(
        cli, ["workitem", "workflow", "get", "--name", "Named Workflow", "--format", "json"]
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["id"] == "wf-abc"


def test_preview_workflow_html_to_file(monkeypatch: Any, runner: CliRunner, tmp_path: Any) -> None:
    """Preview --format html --output writes an HTML file."""
    patch_keyring(monkeypatch)

    wf_data = {
        "name": "HTML Preview WF",
        "actions": [
            {
                "name": "START",
                "displayText": "Start",
                "privilegeSpecificity": [],
                "executionAction": {"type": "MANUAL", "action": "START"},
            }
        ],
        "states": [
            {
                "name": "NEW",
                "dashboardAvailable": False,
                "defaultSubstate": "NEW",
                "substates": [
                    {
                        "name": "NEW",
                        "displayText": "New",
                        "availableActions": [
                            {
                                "action": "START",
                                "nextState": "DONE",
                                "nextSubstate": "DONE",
                                "showInUI": True,
                            }
                        ],
                    }
                ],
            },
            {
                "name": "DONE",
                "dashboardAvailable": False,
                "defaultSubstate": "DONE",
                "substates": [{"name": "DONE", "displayText": "Done", "availableActions": []}],
            },
        ],
    }

    input_file = str(tmp_path / "wf.json")
    output_file = str(tmp_path / "wf.html")
    with open(input_file, "w") as fh:
        json.dump(wf_data, fh)

    cli = make_cli()
    result = runner.invoke(
        cli,
        [
            "workitem",
            "workflow",
            "preview",
            "--file",
            input_file,
            "--format",
            "html",
            "--output",
            output_file,
        ],
    )
    assert result.exit_code == 0
    assert "HTML preview saved" in result.output

    import os

    assert os.path.exists(output_file)
    with open(output_file) as fh:
        content = fh.read()
    assert "mermaid" in content.lower()


def test_list_workitems_multi_page_table(monkeypatch: Any, runner: CliRunner) -> None:
    """Table mode fetches a second page when user confirms and token is valid."""
    patch_keyring(monkeypatch)

    call_count: List[int] = [0]

    def mock_post(*a: Any, **kw: Any) -> Any:
        call_count[0] += 1

        class R:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                if call_count[0] == 1:
                    return {
                        "workItems": [_make_workitem(wi_id=str(i)) for i in range(3)],
                        "continuationToken": "page2-token",
                    }
                return {"workItems": [_make_workitem(wi_id=str(i + 10)) for i in range(2)]}

        return R()

    monkeypatch.setattr("requests.post", mock_post)
    monkeypatch.setattr("slcli.workitem_click.get_workspace_map", lambda: {"ws1": "Default"})

    cli = make_cli()
    # Confirm to fetch the second page
    result = runner.invoke(cli, ["workitem", "list", "--take", "3"], input="y\n")
    assert result.exit_code == 0
    assert call_count[0] == 2  # both pages fetched


# ---------------------------------------------------------------------------
# More targeted coverage for error/edge paths
# ---------------------------------------------------------------------------


def test_create_workitem_failed_items(monkeypatch: Any, runner: CliRunner) -> None:
    """Create returns failedWorkItems → exits with error."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200
            text = '{"failedWorkItems": [{"code": "E1", "message": "bad input"}]}'

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"failedWorkItems": [{"code": "E1", "message": "bad input"}]}

        return R()

    monkeypatch.setattr("requests.post", mock_post)

    cli = make_cli()
    result = runner.invoke(cli, ["workitem", "create", "--name", "Bad", "--type", "testplan"])
    assert result.exit_code != 0


def test_delete_workitem_returns_200(monkeypatch: Any, runner: CliRunner) -> None:
    """Delete returning HTTP 200 with deletedWorkItemIds prints success."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200
            text = '{"deletedWorkItemIds": ["1000"]}'

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"deletedWorkItemIds": ["1000"]}

        return R()

    monkeypatch.setattr("requests.post", mock_post)

    cli = make_cli()
    result = runner.invoke(cli, ["workitem", "delete", "1000", "--yes"])
    assert result.exit_code == 0
    assert "1000" in result.output


def test_delete_workitem_returns_200_with_failures(monkeypatch: Any, runner: CliRunner) -> None:
    """Delete returning HTTP 200 with failedWorkItemIds exits with error."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200
            text = '{"failedWorkItemIds": ["1000"]}'

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"failedWorkItemIds": ["1000"]}

        return R()

    monkeypatch.setattr("requests.post", mock_post)

    cli = make_cli()
    result = runner.invoke(cli, ["workitem", "delete", "1000", "--yes"])
    assert result.exit_code != 0


def test_execute_workitem_failure(monkeypatch: Any, runner: CliRunner) -> None:
    """Execute returns 400 → exits with error."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 400
            text = '{"error": {"message": "Invalid action"}}'

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"error": {"message": "Invalid action"}}

        return R()

    monkeypatch.setattr("requests.post", mock_post)

    cli = make_cli()
    result = runner.invoke(cli, ["workitem", "execute", "1000", "--action", "BOGUS"])
    assert result.exit_code != 0


def test_schedule_workitem_failure(monkeypatch: Any, runner: CliRunner) -> None:
    """Schedule returning failedWorkItems exits with error."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200
            text = '{"failedWorkItems": [{"id": "1000", "message": "conflict"}]}'

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"failedWorkItems": [{"id": "1000", "message": "conflict"}]}

        return R()

    monkeypatch.setattr("requests.post", mock_post)

    cli = make_cli()
    result = runner.invoke(
        cli,
        ["workitem", "schedule", "1000", "--start-time", "2025-01-01T00:00:00Z"],
    )
    assert result.exit_code != 0


def test_list_templates_with_workspace(monkeypatch: Any, runner: CliRunner) -> None:
    """Template list with --workspace passes workspace ID to API."""
    patch_keyring(monkeypatch)

    captured: List[Any] = []

    def mock_post(url: str, *a: Any, **kw: Any) -> Any:
        captured.append(kw.get("json") or (a[0] if a else {}))

        class R:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"workItemTemplates": [_make_template()]}

        return R()

    def mock_get(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"workspaces": [{"id": "ws1", "name": "Default"}]}

        return R()

    monkeypatch.setattr("requests.post", mock_post)
    monkeypatch.setattr("requests.get", mock_get)
    monkeypatch.setattr("slcli.workitem_click.get_workspace_map", lambda: {"ws1": "Default"})

    cli = make_cli()
    result = runner.invoke(
        cli, ["workitem", "template", "list", "--workspace", "Default", "--format", "json"]
    )
    assert result.exit_code == 0
    payload = captured[0] if captured else {}
    assert "substitutions" in payload
    assert "ws1" in payload["substitutions"]


def test_delete_template_confirmed(monkeypatch: Any, runner: CliRunner) -> None:
    """Delete template when user confirms."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 204
            text = ""

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {}

        return R()

    monkeypatch.setattr("requests.post", mock_post)

    cli = make_cli()
    result = runner.invoke(cli, ["workitem", "template", "delete", "2000"], input="y\n")
    assert result.exit_code == 0
    assert "deleted" in result.output.lower()


def test_get_workflow_table_format(monkeypatch: Any, runner: CliRunner) -> None:
    """Get workflow in table format displays structured output."""
    patch_keyring(monkeypatch)

    wf = {"id": "wf1", "name": "My Workflow", "workspace": "ws1", "description": "A workflow"}

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"workflows": [wf]}

        return R()

    def mock_get(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return wf

        return R()

    monkeypatch.setattr("requests.post", mock_post)
    monkeypatch.setattr("requests.get", mock_get)
    monkeypatch.setattr("slcli.workitem_click.get_workspace_map", lambda: {"ws1": "Default"})

    cli = make_cli()
    result = runner.invoke(cli, ["workitem", "workflow", "get", "--id", "wf1"])
    assert result.exit_code == 0
    assert "My Workflow" in result.output


def test_list_workflows_with_workspace_table(monkeypatch: Any, runner: CliRunner) -> None:
    """Workflow list in table mode with --workspace passes workspace_id filter."""
    patch_keyring(monkeypatch)

    captured: List[Any] = []

    def mock_post(url: str, *a: Any, **kw: Any) -> Any:
        captured.append(kw.get("json") or (a[0] if a else {}))

        class R:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"workflows": [{"id": "wf1", "name": "WF1", "workspace": "ws1"}]}

        return R()

    def mock_get(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"workspaces": [{"id": "ws1", "name": "Default"}]}

        return R()

    monkeypatch.setattr("requests.post", mock_post)
    monkeypatch.setattr("requests.get", mock_get)
    monkeypatch.setattr("slcli.workitem_click.get_workspace_map", lambda: {"ws1": "Default"})

    cli = make_cli()
    result = runner.invoke(cli, ["workitem", "workflow", "list", "--workspace", "Default"])
    assert result.exit_code == 0


def test_workflow_create_from_file(monkeypatch: Any, runner: CliRunner, tmp_path: Any) -> None:
    """Import workflow from JSON file with --workspace creates the workflow."""
    patch_keyring(monkeypatch)

    wf_data = {
        "name": "Created WF",
        "states": [],
        "actions": [],
        "workspace": "//ni/workspaces/Default",
    }
    input_file = str(tmp_path / "wf.json")
    with open(input_file, "w") as fh:
        json.dump(wf_data, fh)

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 201
            text = '{"id": "wf-new"}'

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"id": "wf-new"}

        return R()

    monkeypatch.setattr("requests.post", mock_post)

    cli = make_cli()
    result = runner.invoke(
        cli,
        ["workitem", "workflow", "import", "--file", input_file],
    )
    assert result.exit_code == 0
    assert "successfully" in result.output.lower()


def test_workitem_get_table_format(monkeypatch: Any, runner: CliRunner) -> None:
    """Get workitem in table format displays all details."""
    patch_keyring(monkeypatch)

    wi = _make_workitem()
    wi["assignedTo"] = "user-1234-5678-abcd-ef01"
    wi["state"] = "RUNNING"
    wi["type"] = "testplan"
    wi["description"] = "Test description"
    wi["workspace"] = "ws1"

    def mock_get(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return wi

        return R()

    monkeypatch.setattr("requests.get", mock_get)
    monkeypatch.setattr("slcli.workitem_click.get_workspace_map", lambda: {"ws1": "Default"})

    cli = make_cli()
    result = runner.invoke(cli, ["workitem", "get", "1000"])
    assert result.exit_code == 0
    assert "1000" in result.output


def test_update_workitem_from_file(monkeypatch: Any, runner: CliRunner, tmp_path: Any) -> None:
    """Update workitem with --file option loads data from file."""
    patch_keyring(monkeypatch)

    wi_data = {"name": "From File", "state": "RUNNING"}
    input_file = str(tmp_path / "wi.json")
    with open(input_file, "w") as fh:
        json.dump(wi_data, fh)

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200
            text = '{"updatedWorkItems": [{"id": "1000", "name": "From File"}]}'

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"updatedWorkItems": [{"id": "1000", "name": "From File"}]}

        return R()

    monkeypatch.setattr("requests.post", mock_post)

    cli = make_cli()
    result = runner.invoke(cli, ["workitem", "update", "1000", "--file", input_file])
    assert result.exit_code == 0
    assert "updated" in result.output.lower()


def test_execute_workitem_with_result_type(monkeypatch: Any, runner: CliRunner) -> None:
    """Execute returns result with type field → prints execution type."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200
            text = '{"result": {"type": "MANUAL", "id": "r1"}}'

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"result": {"type": "MANUAL", "id": "r1"}}

        return R()

    monkeypatch.setattr("requests.post", mock_post)

    cli = make_cli()
    result = runner.invoke(cli, ["workitem", "execute", "1000", "--action", "START"])
    assert result.exit_code == 0
    assert "MANUAL" in result.output or "START" in result.output


# ---------------------------------------------------------------------------
# Deep option coverage: state/description/assigned-to, filter + workspace,
# workflow update/preview, template error paths
# ---------------------------------------------------------------------------


def test_create_workitem_with_all_options(monkeypatch: Any, runner: CliRunner) -> None:
    """Create with --state, --description, --assigned-to, --workflow-id covers optional branches."""
    patch_keyring(monkeypatch)

    created = _make_workitem()

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 201
            text = json.dumps({"createdWorkItems": [created]})

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"createdWorkItems": [created]}

        return R()

    monkeypatch.setattr("requests.post", mock_post)

    cli = make_cli()
    result = runner.invoke(
        cli,
        [
            "workitem",
            "create",
            "--name",
            "Full Test",
            "--type",
            "testplan",
            "--state",
            "NEW",
            "--description",
            "A description",
            "--assigned-to",
            "user-abc",
            "--workflow-id",
            "wf-xyz",
        ],
    )
    assert result.exit_code == 0
    assert "created" in result.output.lower()


def test_create_workitem_from_file_option(
    monkeypatch: Any, runner: CliRunner, tmp_path: Any
) -> None:
    """Create with --file loads work item data from JSON file (covers load_json_file path)."""
    patch_keyring(monkeypatch)

    created = _make_workitem()
    wi_data = {"name": "From JSON", "type": "testplan"}
    input_file = str(tmp_path / "wi.json")
    with open(input_file, "w") as fh:
        json.dump(wi_data, fh)

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 201
            text = json.dumps({"createdWorkItems": [created]})

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"createdWorkItems": [created]}

        return R()

    monkeypatch.setattr("requests.post", mock_post)

    cli = make_cli()
    result = runner.invoke(cli, ["workitem", "create", "--file", input_file])
    assert result.exit_code == 0


def test_list_workitems_combined_filter_and_workspace(monkeypatch: Any, runner: CliRunner) -> None:
    """List with --state, --filter, --workspace covers full _query_all_workitems paths."""
    patch_keyring(monkeypatch)

    call_count: List[int] = [0]

    def mock_post(url: str, *a: Any, **kw: Any) -> Any:
        call_count[0] += 1

        class R:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                # Return 15 items + continuation token on first call, 15 on second
                items = [_make_workitem(wi_id=str(call_count[0] * 100 + i)) for i in range(15)]
                tok = "page2-tok" if call_count[0] == 1 else None
                result: Dict[str, Any] = {"workItems": items}
                if tok:
                    result["continuationToken"] = tok
                return result

        return R()

    def mock_get(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"workspaces": [{"id": "ws1", "name": "Default"}]}

        return R()

    monkeypatch.setattr("requests.post", mock_post)
    monkeypatch.setattr("requests.get", mock_get)
    monkeypatch.setattr("slcli.workitem_click.get_workspace_map", lambda: {"ws1": "Default"})

    cli = make_cli()
    result = runner.invoke(
        cli,
        [
            "workitem",
            "list",
            "--state",
            "NEW",
            "--filter",
            "type == @0",
            "--workspace",
            "Default",
            "--format",
            "json",
            "--take",
            "20",
        ],
    )
    assert result.exit_code == 0
    data = json.loads(result.output)
    # max_items=20 caps at 20 (2 pages × 15 = 30 items, capped at 20)
    assert len(data) == 20


def test_workflow_update_from_file_with_workspace(
    monkeypatch: Any, runner: CliRunner, tmp_path: Any
) -> None:
    """Workflow update --file --workspace exercises workspace resolution in update."""
    patch_keyring(monkeypatch)

    wf_data = {
        "name": "Updated Name",
        "description": "Updated description",
        "workspace": "Default",  # non-// workspace string → needs resolution
        "actions": [],
        "states": [],
    }
    input_file = str(tmp_path / "wf.json")
    with open(input_file, "w") as fh:
        json.dump(wf_data, fh)

    def mock_put(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200
            text = ""

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {}

        return R()

    # Patch get_workspace_id_with_fallback to avoid real API call
    monkeypatch.setattr(
        "slcli.workitem_click.get_workspace_id_with_fallback", lambda ws: "ws-resolved"
    )
    monkeypatch.setattr("requests.put", mock_put)

    cli = make_cli()
    result = runner.invoke(
        cli,
        ["workitem", "workflow", "update", "--id", "wf-abc", "--file", input_file],
    )
    assert result.exit_code == 0
    assert "updated" in result.output.lower()


def test_workflow_preview_from_id(monkeypatch: Any, runner: CliRunner, tmp_path: Any) -> None:
    """Workflow preview --id fetches workflow from API and generates HTML output."""
    patch_keyring(monkeypatch)

    wf = {
        "name": "ID Preview",
        "actions": [
            {
                "name": "START",
                "displayText": "Start",
                "privilegeSpecificity": [],
                "executionAction": {"type": "MANUAL", "action": "START"},
            }
        ],
        "states": [
            {
                "name": "NEW",
                "dashboardAvailable": False,
                "defaultSubstate": "NEW",
                "substates": [
                    {
                        "name": "NEW",
                        "displayText": "New",
                        "availableActions": [
                            {
                                "action": "START",
                                "nextState": "DONE",
                                "nextSubstate": "DONE",
                                "showInUI": True,
                            }
                        ],
                    }
                ],
            },
            {
                "name": "DONE",
                "dashboardAvailable": False,
                "defaultSubstate": "DONE",
                "substates": [{"name": "DONE", "displayText": "Done", "availableActions": []}],
            },
        ],
    }

    def mock_get(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return wf

        return R()

    monkeypatch.setattr("requests.get", mock_get)

    output_file = str(tmp_path / "preview.html")
    cli = make_cli()
    result = runner.invoke(
        cli,
        [
            "workitem",
            "workflow",
            "preview",
            "--id",
            "wf-abc",
            "--output",
            output_file,
        ],
    )
    assert result.exit_code == 0
    assert "HTML preview saved" in result.output

    import os

    assert os.path.exists(output_file)


def test_workflow_preview_no_open_html(monkeypatch: Any, runner: CliRunner, tmp_path: Any) -> None:
    """Workflow preview --file --format html --no-open prints HTML to stdout."""
    patch_keyring(monkeypatch)

    wf_data = {
        "name": "No-open Preview",
        "actions": [
            {
                "name": "START",
                "displayText": "Start",
                "privilegeSpecificity": [],
                "executionAction": {"type": "MANUAL", "action": "START"},
            }
        ],
        "states": [
            {
                "name": "NEW",
                "dashboardAvailable": False,
                "defaultSubstate": "NEW",
                "substates": [
                    {
                        "name": "NEW",
                        "displayText": "New",
                        "availableActions": [
                            {
                                "action": "START",
                                "nextState": "DONE",
                                "nextSubstate": "DONE",
                                "showInUI": True,
                            }
                        ],
                    }
                ],
            },
            {
                "name": "DONE",
                "dashboardAvailable": False,
                "defaultSubstate": "DONE",
                "substates": [{"name": "DONE", "displayText": "Done", "availableActions": []}],
            },
        ],
    }
    input_file = str(tmp_path / "wf.json")
    with open(input_file, "w") as fh:
        json.dump(wf_data, fh)

    cli = make_cli()
    result = runner.invoke(
        cli,
        [
            "workitem",
            "workflow",
            "preview",
            "--file",
            input_file,
            "--format",
            "html",
            "--no-open",
        ],
    )
    assert result.exit_code == 0
    # HTML content written directly to stdout
    assert "mermaid" in result.output.lower() or "<!DOCTYPE" in result.output


def test_delete_template_200_with_deleted_ids(monkeypatch: Any, runner: CliRunner) -> None:
    """Template delete returning HTTP 200 with deletedWorkItemTemplateIds → success."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200
            text = '{"deletedWorkItemTemplateIds": ["2000"]}'

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"deletedWorkItemTemplateIds": ["2000"]}

        return R()

    monkeypatch.setattr("requests.post", mock_post)

    cli = make_cli()
    result = runner.invoke(cli, ["workitem", "template", "delete", "2000", "--yes"])
    assert result.exit_code == 0
    assert "2000" in result.output


def test_update_template_failure(monkeypatch: Any, runner: CliRunner) -> None:
    """Update template returning failedWorkItemTemplates exits with error."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200
            text = '{"failedWorkItemTemplates": [{"id": "2000", "message": "conflict"}]}'

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"failedWorkItemTemplates": [{"id": "2000", "message": "conflict"}]}

        return R()

    monkeypatch.setattr("requests.post", mock_post)

    cli = make_cli()
    result = runner.invoke(
        cli,
        ["workitem", "template", "update", "2000", "--name", "Bad Update"],
    )
    assert result.exit_code != 0


def test_update_workitem_failure(monkeypatch: Any, runner: CliRunner) -> None:
    """Update workitem returning failedWorkItems exits with error."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200
            text = '{"failedWorkItems": [{"id": "1000", "message": "conflict"}]}'

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"failedWorkItems": [{"id": "1000", "message": "conflict"}]}

        return R()

    monkeypatch.setattr("requests.post", mock_post)

    cli = make_cli()
    result = runner.invoke(cli, ["workitem", "update", "1000", "--name", "Conflicting"])
    assert result.exit_code != 0


def test_workflow_import_without_workspace_in_file(
    monkeypatch: Any, runner: CliRunner, tmp_path: Any
) -> None:
    """Import workflow from file that has no workspace → error (workspace required)."""
    patch_keyring(monkeypatch)

    wf_data = {
        "name": "No Workspace WF",
        "states": [],
        "actions": [],
        # no "workspace" key
    }
    input_file = str(tmp_path / "wf.json")
    with open(input_file, "w") as fh:
        json.dump(wf_data, fh)

    cli = make_cli()
    result = runner.invoke(cli, ["workitem", "workflow", "import", "--file", input_file])
    assert result.exit_code != 0
    assert "workspace" in result.output.lower() or "workspace" in result.stderr.lower()


def test_workflow_preview_mmd_from_id(monkeypatch: Any, runner: CliRunner, tmp_path: Any) -> None:
    """Preview --id --format mmd --output saves Mermaid diagram fetched via API."""
    patch_keyring(monkeypatch)

    wf = {
        "name": "ID MMD Preview",
        "actions": [
            {
                "name": "START",
                "displayText": "Start",
                "privilegeSpecificity": [],
                "executionAction": {"type": "MANUAL", "action": "START"},
            }
        ],
        "states": [
            {
                "name": "NEW",
                "dashboardAvailable": False,
                "defaultSubstate": "NEW",
                "substates": [
                    {
                        "name": "NEW",
                        "displayText": "New",
                        "availableActions": [
                            {
                                "action": "START",
                                "nextState": "DONE",
                                "nextSubstate": "DONE",
                                "showInUI": True,
                            }
                        ],
                    }
                ],
            },
            {
                "name": "DONE",
                "dashboardAvailable": False,
                "defaultSubstate": "DONE",
                "substates": [{"name": "DONE", "displayText": "Done", "availableActions": []}],
            },
        ],
    }

    def mock_get(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return wf

        return R()

    monkeypatch.setattr("requests.get", mock_get)

    output_file = str(tmp_path / "preview.mmd")
    cli = make_cli()
    result = runner.invoke(
        cli,
        [
            "workitem",
            "workflow",
            "preview",
            "--id",
            "wf-abc",
            "--format",
            "mmd",
            "--output",
            output_file,
        ],
    )
    assert result.exit_code == 0
    assert "Mermaid diagram saved" in result.output

    import os

    assert os.path.exists(output_file)


# ---------------------------------------------------------------------------
# Remaining targeted coverage: export auto-filename, by-name, guard paths,
# continuation in table mode, getitem edge cases
# ---------------------------------------------------------------------------


def test_export_workflow_auto_filename(monkeypatch: Any, runner: CliRunner, tmp_path: Any) -> None:
    """Export without --output auto-generates filename from workflow name."""
    patch_keyring(monkeypatch)

    wf = {"id": "wf1", "name": "My Export WF", "workspace": "ws1"}

    def mock_get(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return wf

        return R()

    monkeypatch.setattr("requests.get", mock_get)

    import os

    original_cwd = os.getcwd()
    try:
        os.chdir(str(tmp_path))
        cli = make_cli()
        result = runner.invoke(cli, ["workitem", "workflow", "export", "--id", "wf1"])
    finally:
        os.chdir(original_cwd)

    assert result.exit_code == 0
    assert "exported" in result.output.lower()


def test_export_workflow_by_name(monkeypatch: Any, runner: CliRunner, tmp_path: Any) -> None:
    """Export by --name queries workflows API and exports the matching one."""
    patch_keyring(monkeypatch)

    wf = {"id": "wf1", "name": "Named Export WF", "workspace": "ws1"}

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"workflows": [wf]}

        return R()

    def mock_get(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return wf

        return R()

    monkeypatch.setattr("requests.post", mock_post)
    monkeypatch.setattr("requests.get", mock_get)

    output_file = str(tmp_path / "export.json")
    cli = make_cli()
    result = runner.invoke(
        cli,
        [
            "workitem",
            "workflow",
            "export",
            "--name",
            "Named Export WF",
            "--output",
            output_file,
        ],
    )
    assert result.exit_code == 0
    assert "exported" in result.output.lower()


def test_create_workitem_with_workspace_option(monkeypatch: Any, runner: CliRunner) -> None:
    """Create with --workspace resolves workspace ID and sets it on the work item."""
    patch_keyring(monkeypatch)

    created = _make_workitem()

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 201
            text = json.dumps({"createdWorkItems": [created]})

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"createdWorkItems": [created]}

        return R()

    monkeypatch.setattr("requests.post", mock_post)
    monkeypatch.setattr("slcli.workitem_click.get_workspace_id_with_fallback", lambda ws: "ws1")

    cli = make_cli()
    result = runner.invoke(
        cli,
        [
            "workitem",
            "create",
            "--name",
            "Workspace Test",
            "--type",
            "testplan",
            "--workspace",
            "Default",
        ],
    )
    assert result.exit_code == 0
    assert "created" in result.output.lower()


def test_update_workitem_with_description_and_assigned_to(
    monkeypatch: Any, runner: CliRunner
) -> None:
    """Update with --description and --assigned-to covers those optional parameter bodies."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200
            text = '{"updatedWorkItems": [{"id": "1000"}]}'

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"updatedWorkItems": [{"id": "1000"}]}

        return R()

    monkeypatch.setattr("requests.post", mock_post)

    cli = make_cli()
    result = runner.invoke(
        cli,
        [
            "workitem",
            "update",
            "1000",
            "--description",
            "New description",
            "--assigned-to",
            "user-xyz-123",
        ],
    )
    assert result.exit_code == 0
    assert "updated" in result.output.lower()


def test_delete_template_200_with_failed_ids(monkeypatch: Any, runner: CliRunner) -> None:
    """Template delete returning HTTP 200 with failedWorkItemTemplateIds exits with error."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200
            text = '{"failedWorkItemTemplateIds": ["2000"]}'

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"failedWorkItemTemplateIds": ["2000"]}

        return R()

    monkeypatch.setattr("requests.post", mock_post)

    cli = make_cli()
    result = runner.invoke(cli, ["workitem", "template", "delete", "2000", "--yes"])
    assert result.exit_code != 0


def test_workflow_list_table_with_continuation(monkeypatch: Any, runner: CliRunner) -> None:
    """Workflow list in table mode shows continuation prompt when more pages available."""
    patch_keyring(monkeypatch)

    call_count: List[int] = [0]

    def mock_post(*a: Any, **kw: Any) -> Any:
        call_count[0] += 1

        class R:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                items = [
                    {"id": f"wf{call_count[0]}", "name": f"WF{call_count[0]}", "workspace": "ws1"}
                ]
                tok = "page2" if call_count[0] == 1 else None
                result_data: Dict[str, Any] = {"workflows": items}
                if tok:
                    result_data["continuationToken"] = tok
                return result_data

        return R()

    monkeypatch.setattr("requests.post", mock_post)
    monkeypatch.setattr("slcli.workitem_click.get_workspace_map", lambda: {"ws1": "Default"})

    cli = make_cli()
    # Confirm "y" to fetch next page
    result = runner.invoke(cli, ["workitem", "workflow", "list", "--take", "1"], input="y\n")
    assert result.exit_code == 0
    assert call_count[0] == 2


def test_get_workitem_not_found(monkeypatch: Any, runner: CliRunner) -> None:
    """Get workitem that returns empty dict exits with NOT_FOUND."""
    patch_keyring(monkeypatch)

    def mock_get(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {}

        return R()

    monkeypatch.setattr("requests.get", mock_get)

    cli = make_cli()
    result = runner.invoke(cli, ["workitem", "get", "9999"])
    assert result.exit_code != 0


def test_get_workitem_with_properties(monkeypatch: Any, runner: CliRunner) -> None:
    """Get workitem table view with properties dict renders properties section."""
    patch_keyring(monkeypatch)

    wi = _make_workitem()
    wi["properties"] = {"batch": "001", "priority": "high"}
    wi["workspace"] = "ws1"

    def mock_get(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return wi

        return R()

    monkeypatch.setattr("requests.get", mock_get)
    monkeypatch.setattr("slcli.workitem_click.get_workspace_map", lambda: {"ws1": "Default"})

    cli = make_cli()
    result = runner.invoke(cli, ["workitem", "get", "1000"])
    assert result.exit_code == 0
    assert "Properties" in result.output
    assert "batch" in result.output


def test_list_workitems_table_long_assigned_to(monkeypatch: Any, runner: CliRunner) -> None:
    """List workitems with assignedTo > 8 chars truncates UUID in table output."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                wi = _make_workitem()
                wi["assignedTo"] = "user-abc-def-1234-5678"  # > 8 chars
                return {"workItems": [wi]}

        return R()

    monkeypatch.setattr("requests.post", mock_post)
    monkeypatch.setattr("slcli.workitem_click.get_workspace_map", lambda: {"ws1": "Default"})

    cli = make_cli()
    result = runner.invoke(cli, ["workitem", "list"])
    assert result.exit_code == 0
    # UUID was truncated to first 8 chars + "…"
    assert "user-abc" in result.output


# ---------------------------------------------------------------------------
# Final coverage push: delete 204, schedule options, template create options,
# workflow list "no" to continuation
# ---------------------------------------------------------------------------


def test_delete_workitem_204_success(monkeypatch: Any, runner: CliRunner) -> None:
    """Delete returning HTTP 204 prints success and returns immediately."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 204
            text = ""

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {}

        return R()

    monkeypatch.setattr("requests.post", mock_post)

    cli = make_cli()
    result = runner.invoke(cli, ["workitem", "delete", "1000", "--yes"])
    assert result.exit_code == 0
    assert "deleted" in result.output.lower()


def test_schedule_workitem_with_end_and_duration(monkeypatch: Any, runner: CliRunner) -> None:
    """Schedule with --end-time, --duration, and --assigned-to covers those parameter bodies."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200
            text = '{"scheduledWorkItems": [{"id": "1000"}]}'

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"scheduledWorkItems": [{"id": "1000"}]}

        return R()

    monkeypatch.setattr("requests.post", mock_post)

    cli = make_cli()
    result = runner.invoke(
        cli,
        [
            "workitem",
            "schedule",
            "1000",
            "--end",
            "2025-12-31T23:59:00Z",
            "--duration",
            "3600",
            "--assigned-to",
            "user-xyz",
        ],
    )
    assert result.exit_code == 0
    assert "scheduled" in result.output.lower()


def test_create_template_with_description_summary_workspace(
    monkeypatch: Any, runner: CliRunner
) -> None:
    """Create template with --description, --summary, and --workspace covers optional fields."""
    patch_keyring(monkeypatch)

    created = _make_template()

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 201
            text = json.dumps({"createdWorkItemTemplates": [created]})

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"createdWorkItemTemplates": [created]}

        return R()

    monkeypatch.setattr("requests.post", mock_post)
    monkeypatch.setattr("slcli.workitem_click.get_workspace_id_with_fallback", lambda ws: "ws1")

    cli = make_cli()
    result = runner.invoke(
        cli,
        [
            "workitem",
            "template",
            "create",
            "--name",
            "Full Template",
            "--type",
            "testplan",
            "--template-group",
            "default",
            "--description",
            "A detailed description",
            "--summary",
            "Short summary",
            "--workspace",
            "Default",
        ],
    )
    assert result.exit_code == 0
    assert "created" in result.output.lower()


def test_workflow_list_table_decline_continuation(monkeypatch: Any, runner: CliRunner) -> None:
    """Workflow list table mode stops when user declines continuation prompt."""
    patch_keyring(monkeypatch)

    call_count: List[int] = [0]

    def mock_post(*a: Any, **kw: Any) -> Any:
        call_count[0] += 1

        class R:
            status_code = 200

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {
                    "workflows": [{"id": "wf1", "name": "WF1", "workspace": "ws1"}],
                    "continuationToken": "page2",
                }

        return R()

    monkeypatch.setattr("requests.post", mock_post)
    monkeypatch.setattr("slcli.workitem_click.get_workspace_map", lambda: {"ws1": "Default"})

    cli = make_cli()
    # Press "n" to decline fetching next page
    result = runner.invoke(cli, ["workitem", "workflow", "list", "--take", "1"], input="n\n")
    assert result.exit_code == 0
    assert call_count[0] == 1  # Only one page fetched


def test_workflow_update_success_from_file(
    monkeypatch: Any, runner: CliRunner, tmp_path: Any
) -> None:
    """Workflow update from file with already-resolved workspace (// prefix) succeeds."""
    patch_keyring(monkeypatch)

    wf_data = {
        "name": "Updated WF",
        "description": "Updated desc",
        "workspace": "//ni/workspaces/Default",  # starts with // — no resolution needed
        "actions": [],
        "states": [],
    }
    input_file = str(tmp_path / "wf.json")
    with open(input_file, "w") as fh:
        json.dump(wf_data, fh)

    def mock_put(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200
            text = ""

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {}

        return R()

    monkeypatch.setattr("requests.put", mock_put)

    cli = make_cli()
    result = runner.invoke(
        cli,
        ["workitem", "workflow", "update", "--id", "wf-abc", "--file", input_file],
    )
    assert result.exit_code == 0
    assert "updated" in result.output.lower()


def test_update_template_with_optional_fields(monkeypatch: Any, runner: CliRunner) -> None:
    """Template update with --description, --summary, --template-group covers those bodies."""
    patch_keyring(monkeypatch)

    updated = _make_template(name="T1")

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200
            text = json.dumps({"updatedWorkItemTemplates": [updated]})

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"updatedWorkItemTemplates": [updated]}

        return R()

    monkeypatch.setattr("requests.post", mock_post)

    cli = make_cli()
    result = runner.invoke(
        cli,
        [
            "workitem",
            "template",
            "update",
            "2001",
            "--description",
            "New description",
            "--summary",
            "New summary",
            "--template-group",
            "grp-b",
        ],
    )
    assert result.exit_code == 0
    assert "updated" in result.output.lower()


def test_update_template_from_file(monkeypatch: Any, runner: CliRunner, tmp_path: Any) -> None:
    """Template update with --file merges file data into request body."""
    patch_keyring(monkeypatch)

    updated = _make_template(name="File Template")
    input_file = str(tmp_path / "tmpl.json")
    with open(input_file, "w") as fh:
        json.dump({"name": "File Template", "type": "testplan"}, fh)

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            status_code = 200
            text = json.dumps({"updatedWorkItemTemplates": [updated]})

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"updatedWorkItemTemplates": [updated]}

        return R()

    monkeypatch.setattr("requests.post", mock_post)

    cli = make_cli()
    result = runner.invoke(
        cli,
        ["workitem", "template", "update", "2001", "--file", input_file],
    )
    assert result.exit_code == 0
    assert "updated" in result.output.lower()
