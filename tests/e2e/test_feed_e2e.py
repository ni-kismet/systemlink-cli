"""E2E tests for feed commands against dev tier."""

import uuid
from typing import Any, Optional

import pytest


@pytest.mark.e2e
@pytest.mark.sle
class TestFeedE2E:
    """End-to-end tests for feed commands (SLE)."""

    def test_feed_list_basic(self, sle_cli_runner: Any, sle_cli_helper: Any) -> None:
        """Ensure feed list returns results on SLE."""
        result = sle_cli_runner(["feed", "list", "--format", "json"])
        sle_cli_helper.assert_success(result)

        feeds = sle_cli_helper.get_json_output(result)
        assert isinstance(feeds, list)

    def test_feed_create_get_delete(
        self, sle_cli_runner: Any, sle_cli_helper: Any, sle_workspace: str
    ) -> None:
        """Create a feed, fetch it, list packages, and delete it."""
        feed_name = f"e2e-feed-{uuid.uuid4().hex[:8]}"
        feed_id: Optional[str] = None

        try:
            # Create feed and wait for completion
            create_result = sle_cli_runner(
                [
                    "feed",
                    "create",
                    "--name",
                    feed_name,
                    "--platform",
                    "windows",
                    "--workspace",
                    sle_workspace,
                ]
            )
            sle_cli_helper.assert_success(create_result)

            # List feeds and locate the created feed
            list_result = sle_cli_runner(["feed", "list", "--format", "json"])
            sle_cli_helper.assert_success(list_result)
            feeds = sle_cli_helper.get_json_output(list_result)
            feed = sle_cli_helper.find_resource_by_name(feeds, feed_name)
            assert feed, f"Feed '{feed_name}' not found after creation"
            feed_id = feed.get("id")
            assert feed_id, "Created feed missing ID"

            # Get feed by ID
            get_result = sle_cli_runner(["feed", "get", "--id", feed_id, "--format", "json"])
            sle_cli_helper.assert_success(get_result)
            feed_details = sle_cli_helper.get_json_output(get_result)
            assert feed_details.get("id") == feed_id

            # List packages for the new feed (should be empty)
            pkg_result = sle_cli_runner(
                ["feed", "package", "list", "--feed-id", feed_id, "--format", "json"]
            )
            sle_cli_helper.assert_success(pkg_result)
            packages = sle_cli_helper.get_json_output(pkg_result)
            assert isinstance(packages, list)

        finally:
            if feed_id:
                sle_cli_runner(
                    ["feed", "delete", "--id", feed_id, "--yes"],
                    check=False,
                )
