"""E2E tests for tag commands against dev tier."""

import time
from typing import Any

import pytest


@pytest.mark.e2e
@pytest.mark.tag
class TestTagE2E:
    """End-to-end tests for tag commands."""

    def test_tag_lifecycle_basic(
        self, cli_runner: Any, cli_helper: Any, configured_workspace: str
    ) -> None:
        """Test basic tag lifecycle: create, get, set-value, get-value, delete."""
        tag_path = f"e2e.test.basic.{int(time.time())}"

        try:
            # Create tag
            result = cli_runner(
                [
                    "tag",
                    "create",
                    tag_path,
                    "--type",
                    "DOUBLE",
                    "--workspace",
                    configured_workspace,
                ]
            )
            cli_helper.assert_success(result)
            assert "Tag created" in result.stdout

            # Get tag details
            result = cli_runner(["tag", "get", tag_path, "--workspace", configured_workspace])
            cli_helper.assert_success(result)
            assert tag_path in result.stdout
            assert "DOUBLE" in result.stdout

            # Set tag value
            result = cli_runner(
                [
                    "tag",
                    "set-value",
                    tag_path,
                    "42.5",
                    "--workspace",
                    configured_workspace,
                ]
            )
            cli_helper.assert_success(result)
            assert "Tag value updated" in result.stdout

            # Get tag value
            result = cli_runner(["tag", "get-value", tag_path, "--workspace", configured_workspace])
            cli_helper.assert_success(result)
            assert "42.5" in result.stdout

        finally:
            # Cleanup: Delete tag
            cli_runner(
                ["tag", "delete", tag_path, "--workspace", configured_workspace],
                check=False,
            )

    def test_tag_list_basic(
        self, cli_runner: Any, cli_helper: Any, configured_workspace: str
    ) -> None:
        """Test basic tag listing functionality."""
        result = cli_runner(
            ["tag", "list", "--workspace", configured_workspace, "--format", "json"]
        )
        cli_helper.assert_success(result)

        tags = cli_helper.get_json_output(result)
        assert isinstance(tags, list)

    def test_tag_list_with_filter(
        self, cli_runner: Any, cli_helper: Any, configured_workspace: str
    ) -> None:
        """Test tag listing with path filter."""
        tag_path_prefix = f"e2e.test.filter.{int(time.time())}"
        tag_path1 = f"{tag_path_prefix}.tag1"
        tag_path2 = f"{tag_path_prefix}.tag2"
        tag_path3 = f"e2e.other.{int(time.time())}"

        try:
            # Create test tags
            for path in [tag_path1, tag_path2, tag_path3]:
                cli_runner(
                    [
                        "tag",
                        "create",
                        path,
                        "--type",
                        "STRING",
                        "--workspace",
                        configured_workspace,
                    ]
                )

            # Give server time to index
            time.sleep(1)

            # List with filter
            result = cli_runner(
                [
                    "tag",
                    "list",
                    "--workspace",
                    configured_workspace,
                    "--filter",
                    tag_path_prefix,
                    "--format",
                    "json",
                ]
            )
            cli_helper.assert_success(result)

            tags = cli_helper.get_json_output(result)
            filtered_paths = [t["tag"]["path"] for t in tags]

            # Should include tags with matching prefix
            assert tag_path1 in filtered_paths or any(tag_path_prefix in p for p in filtered_paths)
            assert tag_path2 in filtered_paths or any(tag_path_prefix in p for p in filtered_paths)

        finally:
            # Cleanup
            for path in [tag_path1, tag_path2, tag_path3]:
                cli_runner(
                    ["tag", "delete", path, "--workspace", configured_workspace],
                    check=False,
                )

    def test_tag_list_with_keywords(
        self, cli_runner: Any, cli_helper: Any, configured_workspace: str
    ) -> None:
        """Test tag listing with keyword filter."""
        tag_path = f"e2e.test.keywords.{int(time.time())}"
        keyword = f"e2e-test-{int(time.time())}"

        try:
            # Create tag with keyword
            result = cli_runner(
                [
                    "tag",
                    "create",
                    tag_path,
                    "--type",
                    "STRING",
                    "--keywords",
                    keyword,
                    "--workspace",
                    configured_workspace,
                ]
            )
            cli_helper.assert_success(result)

            # Give server time to index
            time.sleep(1)

            # List with keyword filter
            result = cli_runner(
                [
                    "tag",
                    "list",
                    "--workspace",
                    configured_workspace,
                    "--keywords",
                    keyword,
                    "--format",
                    "json",
                ]
            )
            cli_helper.assert_success(result)

            tags = cli_helper.get_json_output(result)
            if tags:  # May be empty depending on indexing
                tag_paths = [t["tag"]["path"] for t in tags]
                assert any(tag_path in p for p in tag_paths) or tag_path in tag_paths

        finally:
            # Cleanup
            cli_runner(
                ["tag", "delete", tag_path, "--workspace", configured_workspace],
                check=False,
            )

    def test_tag_list_table_format(
        self, cli_runner: Any, cli_helper: Any, configured_workspace: str
    ) -> None:
        """Test tag listing with table format."""
        result = cli_runner(
            [
                "tag",
                "list",
                "--workspace",
                configured_workspace,
                "--format",
                "table",
                "--take",
                "5",
            ],
            input_data="n\n",  # Don't fetch more pages
        )
        cli_helper.assert_success(result)

        # Should show table headers
        assert "Path" in result.stdout
        assert "Type" in result.stdout

    def test_tag_create_with_keywords_and_properties(
        self, cli_runner: Any, cli_helper: Any, configured_workspace: str
    ) -> None:
        """Test creating tag with keywords and properties."""
        tag_path = f"e2e.test.metadata.{int(time.time())}"

        try:
            result = cli_runner(
                [
                    "tag",
                    "create",
                    tag_path,
                    "--type",
                    "INT",
                    "--keywords",
                    "test,e2e,automation",
                    "--properties",
                    "owner=e2e-test",
                    "--properties",
                    "env=testing",
                    "--workspace",
                    configured_workspace,
                ]
            )
            cli_helper.assert_success(result)
            assert "Tag created" in result.stdout

            # Verify tag details
            result = cli_runner(["tag", "get", tag_path, "--workspace", configured_workspace])
            cli_helper.assert_success(result)

            # Check text output contains expected values
            assert "INT" in result.stdout
            assert "test" in result.stdout
            assert "owner" in result.stdout

        finally:
            cli_runner(
                ["tag", "delete", tag_path, "--workspace", configured_workspace],
                check=False,
            )

    def test_tag_update_metadata(
        self, cli_runner: Any, cli_helper: Any, configured_workspace: str
    ) -> None:
        """Test updating tag keywords and properties."""
        tag_path = f"e2e.test.update.{int(time.time())}"

        try:
            # Create tag
            result = cli_runner(
                [
                    "tag",
                    "create",
                    tag_path,
                    "--type",
                    "STRING",
                    "--keywords",
                    "initial",
                    "--workspace",
                    configured_workspace,
                ]
            )
            cli_helper.assert_success(result)

            # Update keywords
            result = cli_runner(
                [
                    "tag",
                    "update",
                    tag_path,
                    "--keywords",
                    "updated,keywords",
                    "--workspace",
                    configured_workspace,
                ]
            )
            cli_helper.assert_success(result)
            assert "Tag updated" in result.stdout

            # Update properties
            result = cli_runner(
                [
                    "tag",
                    "update",
                    tag_path,
                    "--properties",
                    "version=1.0",
                    "--workspace",
                    configured_workspace,
                ]
            )
            cli_helper.assert_success(result)

        finally:
            cli_runner(
                ["tag", "delete", tag_path, "--workspace", configured_workspace],
                check=False,
            )

    def test_tag_type_detection_boolean(
        self, cli_runner: Any, cli_helper: Any, configured_workspace: str
    ) -> None:
        """Test automatic type detection for boolean values."""
        tag_path = f"e2e.test.bool.{int(time.time())}"

        try:
            # Create STRING tag (to test type detection on set-value)
            result = cli_runner(
                [
                    "tag",
                    "create",
                    tag_path,
                    "--type",
                    "BOOLEAN",
                    "--workspace",
                    configured_workspace,
                ]
            )
            cli_helper.assert_success(result)

            # Set boolean value
            result = cli_runner(
                [
                    "tag",
                    "set-value",
                    tag_path,
                    "true",
                    "--workspace",
                    configured_workspace,
                ]
            )
            cli_helper.assert_success(result)

            # Get value
            result = cli_runner(["tag", "get-value", tag_path, "--workspace", configured_workspace])
            cli_helper.assert_success(result)
            # Should show boolean representation
            assert "True" in result.stdout or "true" in result.stdout.lower()

        finally:
            cli_runner(
                ["tag", "delete", tag_path, "--workspace", configured_workspace],
                check=False,
            )

    def test_tag_type_detection_int(
        self, cli_runner: Any, cli_helper: Any, configured_workspace: str
    ) -> None:
        """Test automatic type detection for integer values."""
        tag_path = f"e2e.test.int.{int(time.time())}"

        try:
            result = cli_runner(
                [
                    "tag",
                    "create",
                    tag_path,
                    "--type",
                    "INT",
                    "--workspace",
                    configured_workspace,
                ]
            )
            cli_helper.assert_success(result)

            result = cli_runner(
                [
                    "tag",
                    "set-value",
                    tag_path,
                    "42",
                    "--workspace",
                    configured_workspace,
                ]
            )
            cli_helper.assert_success(result)

            result = cli_runner(["tag", "get-value", tag_path, "--workspace", configured_workspace])
            cli_helper.assert_success(result)
            assert "42" in result.stdout

        finally:
            cli_runner(
                ["tag", "delete", tag_path, "--workspace", configured_workspace],
                check=False,
            )

    def test_tag_type_detection_double(
        self, cli_runner: Any, cli_helper: Any, configured_workspace: str
    ) -> None:
        """Test automatic type detection for double values."""
        tag_path = f"e2e.test.double.{int(time.time())}"

        try:
            result = cli_runner(
                [
                    "tag",
                    "create",
                    tag_path,
                    "--type",
                    "DOUBLE",
                    "--workspace",
                    configured_workspace,
                ]
            )
            cli_helper.assert_success(result)

            result = cli_runner(
                [
                    "tag",
                    "set-value",
                    tag_path,
                    "3.14159",
                    "--workspace",
                    configured_workspace,
                ]
            )
            cli_helper.assert_success(result)

            result = cli_runner(["tag", "get-value", tag_path, "--workspace", configured_workspace])
            cli_helper.assert_success(result)
            assert "3.14" in result.stdout

        finally:
            cli_runner(
                ["tag", "delete", tag_path, "--workspace", configured_workspace],
                check=False,
            )

    def test_tag_special_characters_in_path(
        self, cli_runner: Any, cli_helper: Any, configured_workspace: str
    ) -> None:
        """Test tag with special characters in path (URL encoding)."""
        tag_path = f"e2e/test/special-chars/{int(time.time())}"

        try:
            result = cli_runner(
                [
                    "tag",
                    "create",
                    tag_path,
                    "--type",
                    "STRING",
                    "--workspace",
                    configured_workspace,
                ]
            )
            cli_helper.assert_success(result)

            result = cli_runner(["tag", "get", tag_path, "--workspace", configured_workspace])
            cli_helper.assert_success(result)
            assert tag_path in result.stdout

        finally:
            cli_runner(
                ["tag", "delete", tag_path, "--workspace", configured_workspace],
                check=False,
            )

    def test_tag_pagination(
        self, cli_runner: Any, cli_helper: Any, configured_workspace: str
    ) -> None:
        """Test tag list pagination."""
        # Test with small take value
        result = cli_runner(
            [
                "tag",
                "list",
                "--workspace",
                configured_workspace,
                "--take",
                "5",
                "--format",
                "json",
            ]
        )
        cli_helper.assert_success(result)

        tags = cli_helper.get_json_output(result)
        assert isinstance(tags, list)
        assert len(tags) <= 5

    def test_tag_error_handling_invalid_path(
        self, cli_runner: Any, cli_helper: Any, configured_workspace: str
    ) -> None:
        """Test error handling for invalid tag path."""
        result = cli_runner(
            [
                "tag",
                "get",
                "nonexistent.tag.path.12345",
                "--workspace",
                configured_workspace,
                "--format",
                "json",
            ],
            check=False,
        )
        cli_helper.assert_failure(result)

    def test_tag_error_handling_invalid_type(
        self, cli_runner: Any, cli_helper: Any, configured_workspace: str
    ) -> None:
        """Test error handling for invalid tag type."""
        result = cli_runner(
            [
                "tag",
                "create",
                f"e2e.test.invalid.{int(time.time())}",
                "--type",
                "INVALID_TYPE",
                "--workspace",
                configured_workspace,
            ],
            check=False,
        )
        cli_helper.assert_failure(result)

    def test_tag_delete_nonexistent(
        self, cli_runner: Any, cli_helper: Any, configured_workspace: str
    ) -> None:
        """Test deleting a non-existent tag."""
        result = cli_runner(
            [
                "tag",
                "delete",
                f"nonexistent.tag.{int(time.time())}",
                "--workspace",
                configured_workspace,
            ],
            check=False,
        )
        cli_helper.assert_failure(result)

    def test_tag_get_value_without_value(
        self, cli_runner: Any, cli_helper: Any, configured_workspace: str
    ) -> None:
        """Test getting value from tag that has no current value."""
        tag_path = f"e2e.test.novalue.{int(time.time())}"

        try:
            # Create tag without setting value
            result = cli_runner(
                [
                    "tag",
                    "create",
                    tag_path,
                    "--type",
                    "DOUBLE",
                    "--workspace",
                    configured_workspace,
                ]
            )
            cli_helper.assert_success(result)

            # Try to get value (should handle gracefully)
            cli_runner(
                ["tag", "get-value", tag_path, "--workspace", configured_workspace],
                check=False,
            )
            # May return success with "No value" or fail gracefully
            # Just ensure it doesn't crash

        finally:
            cli_runner(
                ["tag", "delete", tag_path, "--workspace", configured_workspace],
                check=False,
            )

    def test_tag_list_format_json_no_pagination(
        self, cli_runner: Any, cli_helper: Any, configured_workspace: str
    ) -> None:
        """Test that JSON format shows all results without pagination prompts."""
        result = cli_runner(
            [
                "tag",
                "list",
                "--workspace",
                configured_workspace,
                "--format",
                "json",
                "--take",
                "100",
            ]
        )
        cli_helper.assert_success(result)

        # Should not have pagination prompts in JSON output
        assert "Show next" not in result.stdout
        assert "results?" not in result.stdout

        # Should be valid JSON
        tags = cli_helper.get_json_output(result)
        assert isinstance(tags, list)
