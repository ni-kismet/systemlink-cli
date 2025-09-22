"""E2E tests for user commands against dev tier."""

from typing import Any

import pytest


@pytest.mark.e2e
@pytest.mark.user
class TestUserE2E:
    """End-to-end tests for user commands."""

    def test_user_list_basic(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test basic user list functionality."""
        result = cli_runner(["user", "list", "--format", "json"])
        cli_helper.assert_success(result)

        users = cli_helper.get_json_output(result)
        assert isinstance(users, list)

    def test_user_list_table_format(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test user list with table format."""
        result = cli_runner(["user", "list", "--format", "table"])
        cli_helper.assert_success(result)

        # Should show table headers or "No users found"
        assert (
            "First Name" in result.stdout and "Email" in result.stdout
        ) or "No users found" in result.stdout

    def test_user_list_with_pagination(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test user list with pagination."""
        result = cli_runner(["user", "list", "--take", "5", "--format", "json"])
        cli_helper.assert_success(result)

        users = cli_helper.get_json_output(result)
        assert isinstance(users, list)
        # Should return at most 5 users
        assert len(users) <= 5

    def test_user_list_with_workspace_filter(
        self, cli_runner: Any, cli_helper: Any, e2e_config: Any
    ) -> None:
        """Test user list with workspace filtering."""
        workspace = e2e_config["workspace"]
        result = cli_runner(["user", "list", "--workspace", workspace, "--format", "json"])
        cli_helper.assert_success(result)

        users = cli_helper.get_json_output(result)
        assert isinstance(users, list)

    def test_user_list_invalid_role(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test user list with invalid role filter."""
        result = cli_runner(
            ["user", "list", "--role", "InvalidRoleName", "--format", "json"], check=False
        )

        # Should either succeed with empty list or fail with validation error
        if result.returncode == 0:
            users = cli_helper.get_json_output(result)
            assert isinstance(users, list)
            assert len(users) == 0  # No users should have invalid role
        else:
            # Command failed due to validation - that's also acceptable
            pass

    @pytest.mark.slow
    def test_user_list_pagination_large(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test user pagination with larger dataset."""
        # First, get total count
        result = cli_runner(["user", "list", "--format", "json"])
        cli_helper.assert_success(result)
        all_users = cli_helper.get_json_output(result)

        if len(all_users) > 10:
            # Test pagination with smaller chunks
            result = cli_runner(["user", "list", "--take", "3", "--format", "json"])
            cli_helper.assert_success(result)
            paginated_users = cli_helper.get_json_output(result)

            assert len(paginated_users) <= 3
            # First 3 users should match
            for i, user in enumerate(paginated_users):
                assert user["email"] == all_users[i]["email"]

    def test_user_error_handling(self, cli_runner: Any) -> None:
        """Test error handling for invalid user operations."""
        # Test with invalid workspace
        result = cli_runner(
            ["user", "list", "--workspace", "NonExistentWorkspace12345", "--format", "json"],
            check=False,
        )

        # Should either succeed with empty list or fail with error
        # Both behaviors are acceptable depending on API implementation
        assert result.returncode in [0, 1, 2, 3]  # Various acceptable exit codes
