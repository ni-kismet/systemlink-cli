"""E2E tests for feed package commands."""

import uuid
from pathlib import Path
from typing import Any, Optional

import pytest

from slcli.webapp_click import _pack_folder_to_nipkg


@pytest.mark.e2e
@pytest.mark.sle
@pytest.mark.usefixtures("require_sle")
class TestFeedPackageE2E:
    """End-to-end tests for feed package commands (SLE)."""

    @pytest.fixture
    def test_package(self, tmp_path: Path) -> Path:
        """Create a dummy .nipkg file for testing."""
        pkg_dir = tmp_path / "test-package_1.0.0_all"
        pkg_dir.mkdir()
        (pkg_dir / "test.txt").write_text("Hello World")

        return _pack_folder_to_nipkg(pkg_dir)

    def test_feed_package_lifecycle(
        self, sle_cli_runner: Any, sle_cli_helper: Any, sle_workspace: str, test_package: Path
    ) -> None:
        """Create feed, upload package, list it, delete package, delete feed."""
        feed_name = f"e2e-pkg-feed-{uuid.uuid4().hex[:8]}"
        feed_id: Optional[str] = None
        package_id: Optional[str] = None

        try:
            # 1. Create feed
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
                    "--wait",
                ]
            )
            sle_cli_helper.assert_success(create_result)

            # Get feed ID from creation output or list
            list_result = sle_cli_runner(["feed", "list", "--format", "json"])
            feeds = sle_cli_helper.get_json_output(list_result)
            feed = sle_cli_helper.find_resource_by_name(feeds, feed_name)
            assert feed, "Feed not found after creation"
            feed_id = feed["id"]

            # 2. Upload package
            upload_result = sle_cli_runner(
                [
                    "feed",
                    "package",
                    "upload",
                    "--feed-id",
                    feed_id,
                    "--file",
                    str(test_package),
                    "--wait",
                ]
            )
            sle_cli_helper.assert_success(upload_result)

            # 3. List packages
            pkg_list_result = sle_cli_runner(
                ["feed", "package", "list", "--feed-id", feed_id, "--format", "json"]
            )
            sle_cli_helper.assert_success(pkg_list_result)
            packages = sle_cli_helper.get_json_output(pkg_list_result)
            assert len(packages) > 0, "No packages found after upload"

            # Find our package
            package = next(
                (
                    p
                    for p in packages
                    if "test-package" in p.get("metadata", {}).get("packageName", "")
                ),
                None,
            )
            assert package, "Uploaded package not found in list"
            package_id = package["id"]

            # 4. Delete package
            delete_pkg_result = sle_cli_runner(
                ["feed", "package", "delete", "--id", package_id, "--yes", "--wait"]
            )
            sle_cli_helper.assert_success(delete_pkg_result)

            # Verify deletion
            pkg_list_after = sle_cli_runner(
                ["feed", "package", "list", "--feed-id", feed_id, "--format", "json"]
            )
            packages_after = sle_cli_helper.get_json_output(pkg_list_after)
            assert not any(
                p["id"] == package_id for p in packages_after
            ), "Package still exists after deletion"

        finally:
            # Cleanup feed
            if feed_id:
                sle_cli_runner(
                    ["feed", "delete", "--id", feed_id, "--yes", "--wait"],
                    check=False,
                )
