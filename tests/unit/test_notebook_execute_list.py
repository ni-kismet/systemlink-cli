"""Unit tests for slcli notebook execute list command."""

from __future__ import annotations

from typing import Any, Dict, List

from click.testing import CliRunner

from slcli.main import cli
from .test_utils import patch_keyring


def _invoke(args: List[str]) -> Any:
    runner = CliRunner()
    return runner.invoke(cli, args)


def test_notebook_execute_list_basic(monkeypatch):
    """List executions with no filters."""
    patch_keyring(monkeypatch)
    import slcli.notebook_click

    executions = [
        {
            "id": "exe1",
            "notebookId": "nb1",
            "workspaceId": "w1",
            "status": "SUCCEEDED",
            "queuedAt": "2025-09-01T10:00:00Z",
        },
        {
            "id": "exe2",
            "notebookId": "nb2",
            "workspaceId": "w2",
            "status": "FAILED",
            "queuedAt": "2025-09-01T11:00:00Z",
        },
    ]

    def mock_query_execs(workspace_id=None, status=None, notebook_id=None):  # noqa: D401
        assert workspace_id is None
        assert status is None
        assert notebook_id is None
        return executions

    monkeypatch.setattr(slcli.notebook_click, "_query_notebook_executions", mock_query_execs)
    import slcli.utils

    monkeypatch.setattr(
        slcli.utils, "get_workspace_map", lambda: {"w1": "Workspace1", "w2": "Workspace2"}
    )
    result = _invoke(
        ["notebook", "execute", "list", "--format", "json"]
    )  # JSON to avoid pagination
    if result.exit_code != 0:
        print(result.output)
    assert result.exit_code == 0
    # Should output array of executions
    assert "exe1" in result.output and "exe2" in result.output


def test_notebook_execute_list_status_mapping(monkeypatch):
    """Status mapping: user passes timed_out -> service TIMEDOUT."""
    patch_keyring(monkeypatch)
    import slcli.notebook_click

    captured_params: Dict[str, Any] = {}

    def mock_query_execs(workspace_id=None, status=None, notebook_id=None):  # noqa: D401
        captured_params.update(
            {"workspace_id": workspace_id, "status": status, "notebook_id": notebook_id}
        )
        return []

    monkeypatch.setattr(slcli.notebook_click, "_query_notebook_executions", mock_query_execs)
    import slcli.utils

    monkeypatch.setattr(slcli.utils, "get_workspace_map", lambda: {})
    result = _invoke(
        ["notebook", "execute", "list", "--status", "timed_out", "--format", "json"]
    )  # no output data; ensure mapping
    assert result.exit_code == 0
    assert captured_params["status"] == "TIMEDOUT"  # mapped form


def test_notebook_execute_list_invalid_status(monkeypatch):
    """Invalid status results in exit code 2 (INVALID_INPUT)."""
    patch_keyring(monkeypatch)
    import slcli.notebook_click

    def mock_query_execs(workspace_id=None, status=None, notebook_id=None):  # pragma: no cover
        return []

    monkeypatch.setattr(slcli.notebook_click, "_query_notebook_executions", mock_query_execs)
    import slcli.utils

    monkeypatch.setattr(slcli.utils, "get_workspace_map", lambda: {})
    result = _invoke(
        ["notebook", "execute", "list", "--status", "bogus", "--format", "json"]
    )  # invalid
    assert result.exit_code == 2
    assert "Invalid status" in result.output


def test_notebook_execute_list_with_filters(monkeypatch):
    """Workspace + notebook ID + status filters propagate to query helper."""
    patch_keyring(monkeypatch)
    import slcli.notebook_click

    received: Dict[str, Any] = {}

    def mock_get_workspace_id_with_fallback(val: str) -> str:  # noqa: D401
        return "workspace-guid-123" if val == "MyWS" else val

    def mock_query_execs(workspace_id=None, status=None, notebook_id=None):  # noqa: D401
        received.update(
            {"workspace_id": workspace_id, "status": status, "notebook_id": notebook_id}
        )
        return []

    monkeypatch.setattr(slcli.notebook_click, "_query_notebook_executions", mock_query_execs)
    monkeypatch.setattr(
        slcli.notebook_click, "get_workspace_id_with_fallback", mock_get_workspace_id_with_fallback
    )
    import slcli.utils

    monkeypatch.setattr(slcli.utils, "get_workspace_map", lambda: {"workspace-guid-123": "MyWS"})
    result = _invoke(
        [
            "notebook",
            "execute",
            "list",
            "--workspace",
            "MyWS",
            "--notebook-id",
            "nb-xyz",
            "--status",
            "in_progress",
            "--format",
            "json",
        ]
    )
    assert result.exit_code == 0
    assert received == {
        "workspace_id": "workspace-guid-123",
        "status": "INPROGRESS",
        "notebook_id": "nb-xyz",
    }
