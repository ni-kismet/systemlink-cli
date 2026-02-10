"""Tests for readonly mode protection across CLI commands.

This test suite verifies that readonly mode properly blocks mutation operations
(create, update, delete, edit) across all command modules.
"""

import re
from pathlib import Path
from typing import Any
from unittest.mock import patch

import click
import pytest
from click.testing import CliRunner

from slcli.utils import ExitCodes


def test_check_readonly_mode_blocks_when_active() -> None:
    """Test that check_readonly_mode exits with PERMISSION_DENIED when readonly is active."""
    from slcli.utils import check_readonly_mode

    with patch("slcli.profiles.is_active_profile_readonly", return_value=True):
        with pytest.raises(SystemExit) as exc_info:
            check_readonly_mode("test operation")

        assert exc_info.value.code == ExitCodes.PERMISSION_DENIED


def test_check_readonly_mode_allows_when_inactive() -> None:
    """Test that check_readonly_mode allows operation when readonly is inactive."""
    from slcli.utils import check_readonly_mode

    with patch("slcli.profiles.is_active_profile_readonly", return_value=False):
        # Should not raise or exit
        check_readonly_mode("test operation")


def test_readonly_mode_error_message_content() -> None:
    """Test that readonly mode provides clear error message mentioning mutation operations."""
    from slcli.utils import check_readonly_mode
    from click.testing import CliRunner

    # Create a simple CLI command to capture output
    @click.command()
    def test_cmd() -> None:
        check_readonly_mode("delete resource")

    runner = CliRunner()
    with patch("slcli.profiles.is_active_profile_readonly", return_value=True):
        result = runner.invoke(test_cmd)

        # Check exit code
        assert result.exit_code == ExitCodes.PERMISSION_DENIED

        # Check error message content
        assert "Cannot delete resource: profile is in readonly mode" in result.output
        assert "Readonly mode disables all mutation operations" in result.output
        assert "create" in result.output
        assert "update" in result.output
        assert "delete" in result.output
        assert "import" in result.output
        assert "upload" in result.output
        assert "publish" in result.output
        assert "disable" in result.output


# Helper function for creating test CLI
def make_cli() -> click.Group:
    """Create CLI instance for testing."""

    @click.group()
    def test_cli() -> None:
        pass

    return test_cli


# Test that read operations are NOT blocked in readonly mode


def test_user_list_allowed_in_readonly_mode() -> None:
    """Test that user list command is allowed in readonly mode."""
    from slcli import user_click

    cli = make_cli()
    user_click.register_user_commands(cli)
    runner = CliRunner()

    def mock_get(*args: Any, **kwargs: Any) -> Any:
        class MockResponse:
            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"users": []}

        return MockResponse()

    with patch("slcli.profiles.is_active_profile_readonly", return_value=True):
        with patch("slcli.user_click.make_api_request", side_effect=mock_get):
            result = runner.invoke(cli, ["user", "list"])

            # Should succeed (exit code 0) even in readonly mode
            assert result.exit_code == 0


def test_workflow_list_allowed_in_readonly_mode() -> None:
    """Test that workflow list command is allowed in readonly mode."""
    from slcli import workflows_click

    cli = make_cli()
    workflows_click.register_workflows_commands(cli)
    runner = CliRunner()

    def mock_get(*args: Any, **kwargs: Any) -> Any:
        class MockResponse:
            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"workflows": []}

        return MockResponse()

    with patch("slcli.profiles.is_active_profile_readonly", return_value=True):
        with patch("slcli.workflows_click.make_api_request", side_effect=mock_get):
            result = runner.invoke(cli, ["workflow", "list"])

            # Should succeed (exit code 0) even in readonly mode
            assert result.exit_code == 0


def test_tag_list_allowed_in_readonly_mode() -> None:
    """Test that tag list command is allowed in readonly mode."""
    from slcli import tag_click

    cli = make_cli()
    tag_click.register_tag_commands(cli)
    runner = CliRunner()

    def mock_get(*args: Any, **kwargs: Any) -> Any:
        class MockResponse:
            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"tags": []}

        return MockResponse()

    with patch("slcli.profiles.is_active_profile_readonly", return_value=True):
        with patch("slcli.tag_click.make_api_request", side_effect=mock_get):
            result = runner.invoke(cli, ["tag", "list"])

            # Should succeed (exit code 0) even in readonly mode
            assert result.exit_code == 0


def test_all_mutation_commands_have_readonly_guards() -> None:
    """Regression test: verify all mutation commands contain check_readonly_mode calls.

    This test scans all *_click.py modules for mutation command definitions
    (create, update, delete, edit, import, publish, upload, disable) and ensures
    each has a corresponding check_readonly_mode() call in its function body.
    """
    slcli_dir = Path(__file__).parent.parent.parent / "slcli"
    click_modules = list(slcli_dir.glob("*_click.py"))

    # Mutation command patterns to look for
    mutation_verbs = [
        "create",
        "update",
        "delete",
        "import",
        "publish",
        "upload",
        "disable",
        "edit",
    ]

    # Expected modules with mutation commands (exclude main.py, completion_click.py, etc.)
    expected_modules = {
        "config_click.py",  # delete-profile
        "tag_click.py",  # create, update, delete
        "user_click.py",  # create, update, delete
        "workflows_click.py",  # import, delete, update
        "templates_click.py",  # import, delete
        "workspace_click.py",  # disable
        "notebook_click.py",  # create, update, delete
        "policy_click.py",  # create, update, delete, delete (template)
        "feed_click.py",  # create, delete, upload, delete (package)
        "function_click.py",  # create, update, delete
        "dff_click.py",  # create, update, delete, edit
        "webapp_click.py",  # delete, publish
        "file_click.py",  # delete
        "example_click.py",  # delete
    }

    # Track findings
    unguarded_commands: list[str] = []
    modules_checked = 0

    for module_path in click_modules:
        if module_path.name not in expected_modules:
            continue

        modules_checked += 1
        content = module_path.read_text()

        # Find all mutation command definitions
        # Pattern: @<something>.command(name="verb") or def verb_<noun>
        for verb in mutation_verbs:
            # Look for command decorators with mutation verbs
            command_pattern = (
                rf'@\w+\.command\(name=["\']({verb}[^"\']*|[^"\']*{verb}[^"\']*)["\']\)'
            )
            matches = re.finditer(command_pattern, content)

            for match in matches:
                # Get the function definition that follows
                match_pos = match.end()
                remaining = content[match_pos:]
                func_match = re.search(r"def\s+(\w+)\s*\(", remaining)

                if func_match:
                    func_name = func_match.group(1)
                    # Extract function body (up to next 'def ' or end of file)
                    func_body_match = re.search(
                        r"def\s+\w+.*?(?=\n    def\s+|\n\n    @|\Z)", remaining, re.DOTALL
                    )

                    if func_body_match:
                        func_body = func_body_match.group(0)

                        # Check if check_readonly_mode is called
                        if "check_readonly_mode" not in func_body:
                            unguarded_commands.append(
                                f"{module_path.name}::{func_name} (command: {match.group(1)})"
                            )

            # Also look for direct function definitions like "def delete_<noun>"
            func_pattern = rf"def\s+({verb}_\w+)\s*\("
            func_matches = re.finditer(func_pattern, content)

            for func_match in func_matches:
                func_name = func_match.group(1)
                # Check if this is a Click command (has @command decorator before it)
                before_func = content[: func_match.start()]
                if "@" in before_func.split("\n")[-3:][0]:  # Decorator likely present
                    # Extract function body
                    func_body_match = re.search(
                        rf"def\s+{re.escape(func_name)}.*?(?=\n    def\s+|\n\n    @|\Z)",
                        content[func_match.start() :],
                        re.DOTALL,
                    )

                    if func_body_match:
                        func_body = func_body_match.group(0)

                        # Check if check_readonly_mode is called
                        if "check_readonly_mode" not in func_body:
                            # Avoid duplicates if already caught by command pattern
                            entry = f"{module_path.name}::{func_name}"
                            if not any(entry in cmd for cmd in unguarded_commands):
                                unguarded_commands.append(entry)

    # Assert all expected modules were checked
    assert modules_checked == len(
        expected_modules
    ), f"Expected to check {len(expected_modules)} modules, but only checked {modules_checked}"

    # Assert no unguarded commands found
    if unguarded_commands:
        pytest.fail(
            f"Found {len(unguarded_commands)} mutation command(s) without check_readonly_mode:\n"
            + "\n".join(f"  - {cmd}" for cmd in sorted(unguarded_commands))
        )
