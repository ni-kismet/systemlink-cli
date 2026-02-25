"""E2E tests for comment commands against dev tier."""

import uuid
from typing import Any, Generator, Tuple

import pytest


def _extract_comment_id(stdout: str) -> str:
    """Parse the comment ID emitted by 'comment add' / 'comment update' success output.

    format_success produces lines like:
        ✓ Comment added
          ID: <comment_id>
    """
    for line in stdout.splitlines():
        stripped = line.strip()
        if stripped.startswith("ID:"):
            return stripped.split(":", 1)[1].strip()
    pytest.fail(f"Could not find comment ID in output:\n{stdout}")


@pytest.fixture
def temp_asset(
    cli_runner: Any, cli_helper: Any, configured_workspace: str
) -> Generator[Tuple[str, str], None, None]:
    """Create a temporary asset for comment tests, yield (asset_id, workspace), then delete it."""
    unique = uuid.uuid4().hex[:8]
    result = cli_runner(
        [
            "asset",
            "create",
            "--model-name",
            f"e2e-comment-test-{unique}",
            "--serial-number",
            f"e2e-sn-{unique}",
            "--vendor-name",
            "E2E Test Vendor",
            "--asset-type",
            "GENERIC",
            "--format",
            "json",
        ]
    )
    cli_helper.assert_success(result)
    response = cli_helper.get_json_output(result)
    # create returns {"assets": [...], "failed": [...]}
    asset_id: str = response["assets"][0]["id"]

    yield asset_id, configured_workspace

    try:
        cli_runner(["asset", "delete", asset_id, "--force"], check=False)
    except Exception:
        pass  # Best-effort cleanup


@pytest.mark.e2e
@pytest.mark.comment
class TestCommentListE2E:
    """End-to-end tests for 'comment list' command."""

    def test_list_json(self, cli_runner: Any, cli_helper: Any, temp_asset: Tuple[str, str]) -> None:
        """Test listing comments in JSON format against a known asset resource."""
        asset_id, workspace = temp_asset

        # Add a comment so the list is non-trivially exercised
        cli_runner(
            [
                "comment",
                "add",
                "--resource-type",
                "niapm:Asset",
                "--resource-id",
                asset_id,
                "--workspace",
                workspace,
                "--message",
                "E2E list test comment",
            ]
        )

        result = cli_runner(
            [
                "comment",
                "list",
                "--resource-type",
                "niapm:Asset",
                "--resource-id",
                asset_id,
                "--format",
                "json",
            ]
        )
        cli_helper.assert_success(result)

        comments = cli_helper.get_json_output(result)
        assert isinstance(comments, list)
        assert len(comments) >= 1

    def test_list_table(
        self, cli_runner: Any, cli_helper: Any, temp_asset: Tuple[str, str]
    ) -> None:
        """Test listing comments in table format against a known asset resource."""
        asset_id, workspace = temp_asset

        # Add a comment so there is at least one row to render
        cli_runner(
            [
                "comment",
                "add",
                "--resource-type",
                "niapm:Asset",
                "--resource-id",
                asset_id,
                "--workspace",
                workspace,
                "--message",
                "E2E table list test comment",
            ]
        )

        result = cli_runner(
            [
                "comment",
                "list",
                "--resource-type",
                "niapm:Asset",
                "--resource-id",
                asset_id,
                "--format",
                "table",
            ],
            input_data="n\n",
        )
        cli_helper.assert_success(result)

        assert "Message" in result.stdout or "No comments found" in result.stdout


@pytest.mark.e2e
@pytest.mark.comment
class TestCommentAddUpdateDeleteE2E:
    """End-to-end tests for comment add/update/delete lifecycle."""

    def test_add_comment(
        self, cli_runner: Any, cli_helper: Any, temp_asset: Tuple[str, str]
    ) -> None:
        """Test adding a comment to a dynamically created asset resource."""
        asset_id, workspace = temp_asset

        result = cli_runner(
            [
                "comment",
                "add",
                "--resource-type",
                "niapm:Asset",
                "--resource-id",
                asset_id,
                "--workspace",
                workspace,
                "--message",
                "E2E test comment - add",
            ]
        )
        cli_helper.assert_success(result)
        assert "✓" in result.stdout
        assert _extract_comment_id(result.stdout)

    def test_update_comment(
        self, cli_runner: Any, cli_helper: Any, temp_asset: Tuple[str, str]
    ) -> None:
        """Test updating a comment: add one first, then update its message."""
        asset_id, workspace = temp_asset

        add_result = cli_runner(
            [
                "comment",
                "add",
                "--resource-type",
                "niapm:Asset",
                "--resource-id",
                asset_id,
                "--workspace",
                workspace,
                "--message",
                "E2E test comment - before update",
            ]
        )
        cli_helper.assert_success(add_result)
        comment_id = _extract_comment_id(add_result.stdout)

        result = cli_runner(
            [
                "comment",
                "update",
                comment_id,
                "--message",
                "E2E test comment - after update",
            ]
        )
        cli_helper.assert_success(result)
        assert "✓" in result.stdout

    def test_delete_comment(
        self, cli_runner: Any, cli_helper: Any, temp_asset: Tuple[str, str]
    ) -> None:
        """Test deleting a comment: add one first, then delete it by ID."""
        asset_id, workspace = temp_asset

        add_result = cli_runner(
            [
                "comment",
                "add",
                "--resource-type",
                "niapm:Asset",
                "--resource-id",
                asset_id,
                "--workspace",
                workspace,
                "--message",
                "E2E test comment - to be deleted",
            ]
        )
        cli_helper.assert_success(add_result)
        comment_id = _extract_comment_id(add_result.stdout)

        result = cli_runner(["comment", "delete", comment_id])
        cli_helper.assert_success(result)
        assert "✓" in result.stdout
