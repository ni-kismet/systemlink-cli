"""E2E tests for workspace commands against dev tier."""

from typing import Any

import pytest


@pytest.mark.e2e
@pytest.mark.workspace
class TestWorkspaceE2E:
    """End-to-end tests for workspace commands."""

    def test_workspace_list_basic(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test basic workspace list functionality."""
        result = cli_runner(["workspace", "list", "--format", "json"])
        cli_helper.assert_success(result)

        workspaces = cli_helper.get_json_output(result)
        assert isinstance(workspaces, list)
        assert len(workspaces) > 0  # Should have at least Default workspace

    def test_workspace_list_table_format(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test workspace list with table format."""
        result = cli_runner(["workspace", "list", "--format", "table"])
        cli_helper.assert_success(result)

        # Should show table headers
        assert "Workspace" in result.stdout or "Name" in result.stdout

    def test_workspace_get_by_name(
        self, cli_runner: Any, cli_helper: Any, configured_workspace: str
    ) -> None:
        """Test getting workspace details by name."""
        workspace_name = configured_workspace

        result = cli_runner(["workspace", "get", "--workspace", workspace_name, "--format", "json"])
        cli_helper.assert_success(result)

        workspace_info = cli_helper.get_json_output(result)
        assert isinstance(workspace_info, dict)
        assert "workspace" in workspace_info
        assert workspace_info["workspace"]["name"] == workspace_name

    def test_workspace_get_by_id(
        self, cli_runner: Any, cli_helper: Any, configured_workspace: str
    ) -> None:
        """Test getting workspace details by ID."""
        workspace_name = configured_workspace

        # First get workspace ID
        result = cli_runner(["workspace", "list", "--format", "json"])
        cli_helper.assert_success(result)
        workspaces = cli_helper.get_json_output(result)

        target_workspace = cli_helper.find_resource_by_name(workspaces, workspace_name)
        assert target_workspace, f"Workspace '{workspace_name}' not found"

        workspace_id = target_workspace["id"]

        # Get workspace by ID
        result = cli_runner(["workspace", "get", "--workspace", workspace_id, "--format", "json"])
        cli_helper.assert_success(result)

        workspace_info = cli_helper.get_json_output(result)
        assert isinstance(workspace_info, dict)
        assert "workspace" in workspace_info
        assert workspace_info["workspace"]["id"] == workspace_id
        assert workspace_info["workspace"]["name"] == workspace_name

    def test_workspace_pagination(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test workspace list pagination."""
        result = cli_runner(["workspace", "list", "--take", "5", "--format", "json"])
        cli_helper.assert_success(result)

        workspaces = cli_helper.get_json_output(result)
        assert isinstance(workspaces, list)
        assert len(workspaces) <= 5

    def test_workspace_error_handling(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test error handling for invalid workspace operations."""
        # Test get with invalid workspace name
        result = cli_runner(
            ["workspace", "get", "--workspace", "NonExistentWorkspace12345", "--format", "json"],
            check=False,
        )
        cli_helper.assert_failure(result)

        # Test get with invalid workspace ID
        result = cli_runner(
            ["workspace", "get", "--workspace", "invalid-workspace-id-12345", "--format", "json"],
            check=False,
        )
        cli_helper.assert_failure(result)

        # Test delete with invalid workspace name
        result = cli_runner(
            ["workspace", "delete", "--name", "NonExistentWorkspace12345"], check=False
        )
        cli_helper.assert_failure(result)
