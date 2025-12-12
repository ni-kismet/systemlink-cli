"""E2E tests for file commands against dev tier."""

import json
import tempfile
import time
import uuid
from pathlib import Path
from typing import Any, Generator

import pytest


@pytest.fixture
def temp_test_file() -> Generator[Path, None, None]:
    """Create a temporary test file for upload."""
    with tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False, prefix="e2e-test-"
    ) as f:
        f.write(f"E2E test file content - {uuid.uuid4().hex}\n")
        f.write("This is a test file for file service E2E testing.\n")
        temp_path = Path(f.name)

    yield temp_path

    # Cleanup
    try:
        temp_path.unlink()
    except FileNotFoundError:
        # File may have already been deleted; ignore error during cleanup.
        pass


@pytest.fixture
def temp_download_dir() -> Generator[Path, None, None]:
    """Create a temporary directory for downloads."""
    with tempfile.TemporaryDirectory(prefix="e2e-download-") as tmpdir:
        yield Path(tmpdir)


@pytest.mark.e2e
@pytest.mark.file
class TestFileE2E:
    """End-to-end tests for file commands."""

    def test_file_list_basic(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test basic file list functionality."""
        result = cli_runner(["file", "list", "--format", "json"])
        cli_helper.assert_success(result)
        files = cli_helper.get_json_output(result)
        assert isinstance(files, list)

    def test_file_list_table_format(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test file list with table format."""
        result = cli_runner(["file", "list", "--format", "table", "--take", "5"])
        cli_helper.assert_success(result)
        # Should show table headers or empty message
        assert "Name" in result.stdout or "No files found" in result.stdout

    def test_file_list_with_take(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test file list with take limit."""
        result = cli_runner(["file", "list", "--take", "3", "--format", "json"])
        cli_helper.assert_success(result)
        files = cli_helper.get_json_output(result)
        assert isinstance(files, list)
        assert len(files) <= 3

    def test_file_list_with_workspace(
        self, cli_runner: Any, cli_helper: Any, configured_workspace: str
    ) -> None:
        """Test file list with workspace filter."""
        workspace = configured_workspace

        # First get workspace ID
        result = cli_runner(["workspace", "list", "--format", "json"])
        cli_helper.assert_success(result)
        workspaces = cli_helper.get_json_output(result)
        target_ws = cli_helper.find_resource_by_name(workspaces, workspace)

        if target_ws:
            workspace_id = target_ws["id"]
            result = cli_runner(["file", "list", "--workspace", workspace_id, "--format", "json"])
            cli_helper.assert_success(result)
            files = cli_helper.get_json_output(result)
            assert isinstance(files, list)

    def test_file_list_with_filter(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test file list with name filter."""
        result = cli_runner(["file", "list", "--filter", "test", "--format", "json"])
        cli_helper.assert_success(result)
        files = cli_helper.get_json_output(result)
        assert isinstance(files, list)

    def test_file_upload_download_delete_cycle(
        self,
        cli_runner: Any,
        cli_helper: Any,
        temp_test_file: Path,
        temp_download_dir: Path,
        configured_workspace: str,
    ) -> None:
        """Test full file lifecycle: upload, get, download, delete."""
        workspace = configured_workspace
        unique_name = f"e2e-test-{uuid.uuid4().hex[:8]}.txt"

        # Get workspace ID
        result = cli_runner(["workspace", "list", "--format", "json"])
        cli_helper.assert_success(result)
        workspaces = cli_helper.get_json_output(result)
        target_ws = cli_helper.find_resource_by_name(workspaces, workspace)
        workspace_id = target_ws["id"] if target_ws else None

        file_id = None
        try:
            # Upload file
            upload_args = [
                "file",
                "upload",
                str(temp_test_file),
                "--name",
                unique_name,
            ]
            if workspace_id:
                upload_args.extend(["--workspace", workspace_id])

            result = cli_runner(upload_args)
            cli_helper.assert_success(result)
            assert "Uploaded" in result.stdout or "✓" in result.stdout

            # Extract file ID from output
            for line in result.stdout.split("\n"):
                if "ID:" in line:
                    file_id = line.split("ID:")[-1].strip()
                    break

            assert file_id, "Could not extract file ID from upload output"

            # Get file metadata
            result = cli_runner(["file", "get", file_id, "--format", "json"])
            cli_helper.assert_success(result)
            file_info = cli_helper.get_json_output(result)
            assert isinstance(file_info, dict)
            assert file_info.get("id") == file_id

            # Get file metadata in table format
            result = cli_runner(["file", "get", file_id, "--format", "table"])
            cli_helper.assert_success(result)
            assert unique_name in result.stdout

            # Download file
            download_path = temp_download_dir / "downloaded.txt"
            result = cli_runner(["file", "download", file_id, "--output", str(download_path)])
            cli_helper.assert_success(result)
            assert download_path.exists()
            assert download_path.stat().st_size > 0

            # Verify downloaded content
            downloaded_content = download_path.read_text()
            original_content = temp_test_file.read_text()
            assert downloaded_content == original_content

            # Delete file
            result = cli_runner(["file", "delete", file_id, "--force"])
            cli_helper.assert_success(result)
            assert "Deleted" in result.stdout or "✓" in result.stdout

            file_id = None  # Mark as deleted

        finally:
            # Cleanup if file was uploaded but not deleted
            if file_id:
                try:
                    cli_runner(["file", "delete", file_id, "--force"], check=False)
                except Exception:
                    # Ignore errors during test cleanup; file may already be deleted.
                    pass

    def test_file_upload_with_properties(
        self,
        cli_runner: Any,
        cli_helper: Any,
        temp_test_file: Path,
        e2e_config: Any,
    ) -> None:
        """Test file upload with custom properties."""
        unique_name = f"e2e-props-{uuid.uuid4().hex[:8]}.txt"
        properties = json.dumps({"TestKey": "TestValue", "Category": "E2E"})

        file_id = None
        try:
            # Upload file with properties
            result = cli_runner(
                [
                    "file",
                    "upload",
                    str(temp_test_file),
                    "--name",
                    unique_name,
                    "--properties",
                    properties,
                ]
            )
            cli_helper.assert_success(result)

            # Extract file ID
            for line in result.stdout.split("\n"):
                if "ID:" in line:
                    file_id = line.split("ID:")[-1].strip()
                    break

            assert file_id, "Could not extract file ID"

            # Verify properties
            result = cli_runner(["file", "get", file_id, "--format", "json"])
            cli_helper.assert_success(result)
            file_info = cli_helper.get_json_output(result)

            props = file_info.get("properties", {})
            assert props.get("TestKey") == "TestValue"
            assert props.get("Category") == "E2E"

        finally:
            if file_id:
                try:
                    cli_runner(["file", "delete", file_id, "--force"], check=False)
                except Exception:
                    # Ignore errors during test cleanup; file may already be deleted.
                    pass

    def test_file_query(self, cli_runner: Any, cli_helper: Any, temp_test_file: Path) -> None:
        """Test file query with search filter."""
        unique_prefix = f"e2e-query-{uuid.uuid4().hex[:8]}"
        unique_name = f"{unique_prefix}.txt"

        file_id = None
        try:
            # Upload file
            result = cli_runner(
                [
                    "file",
                    "upload",
                    str(temp_test_file),
                    "--name",
                    unique_name,
                ]
            )
            cli_helper.assert_success(result)

            # Extract file ID
            for line in result.stdout.split("\n"):
                if "ID:" in line:
                    file_id = line.split("ID:")[-1].strip()
                    break

            assert file_id, "Failed to extract file ID from upload output"

            # Query for the file by ID (using id filter which is fast)
            # search-files uses id:("value") syntax
            # Retry a few times since search indexing may have slight delay
            filter_expr = f'id:("{file_id}")'
            files: list = []
            for attempt in range(3):
                result = cli_runner(["file", "query", "--filter", filter_expr, "--format", "json"])
                cli_helper.assert_success(result)
                files = cli_helper.get_json_output(result)
                if files:
                    break
                time.sleep(1)  # Wait for search index

            assert isinstance(files, list)
            assert len(files) == 1
            # Verify we got the right file
            assert files[0].get("id") == file_id
            assert files[0].get("properties", {}).get("Name") == unique_name

        finally:
            if file_id:
                try:
                    cli_runner(["file", "delete", file_id, "--force"], check=False)
                except Exception:
                    # Ignore errors during test cleanup; file may already be deleted.
                    pass

    def test_file_update_metadata(
        self, cli_runner: Any, cli_helper: Any, temp_test_file: Path
    ) -> None:
        """Test updating file metadata."""
        original_name = f"e2e-meta-{uuid.uuid4().hex[:8]}.txt"
        new_name = f"e2e-renamed-{uuid.uuid4().hex[:8]}.txt"

        file_id = None
        try:
            # Upload file
            result = cli_runner(
                [
                    "file",
                    "upload",
                    str(temp_test_file),
                    "--name",
                    original_name,
                ]
            )
            cli_helper.assert_success(result)

            # Extract file ID
            for line in result.stdout.split("\n"):
                if "ID:" in line:
                    file_id = line.split("ID:")[-1].strip()
                    break

            assert file_id, "Could not extract file ID"

            # Update file name
            result = cli_runner(["file", "update-metadata", file_id, "--name", new_name])
            cli_helper.assert_success(result)
            assert "updated" in result.stdout.lower()

            # Verify name changed
            result = cli_runner(["file", "get", file_id, "--format", "json"])
            cli_helper.assert_success(result)
            file_info = cli_helper.get_json_output(result)
            assert file_info.get("properties", {}).get("Name") == new_name

            # Add a property
            result = cli_runner(
                ["file", "update-metadata", file_id, "--add-property", "NewProp=NewValue"]
            )
            cli_helper.assert_success(result)

            # Verify property added
            result = cli_runner(["file", "get", file_id, "--format", "json"])
            cli_helper.assert_success(result)
            file_info = cli_helper.get_json_output(result)
            assert file_info.get("properties", {}).get("NewProp") == "NewValue"

        finally:
            if file_id:
                try:
                    cli_runner(["file", "delete", file_id, "--force"], check=False)
                except Exception:
                    # Ignore errors during test cleanup; file may already be deleted.
                    pass

    def test_file_error_handling(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test error handling for invalid file operations."""
        # Test get with invalid file ID
        result = cli_runner(
            ["file", "get", "invalid-file-id-12345", "--format", "json"],
            check=False,
        )
        cli_helper.assert_failure(result)

        # Test download with invalid file ID
        result = cli_runner(
            ["file", "download", "invalid-file-id-12345"],
            check=False,
        )
        cli_helper.assert_failure(result)

        # Test delete with invalid file ID
        result = cli_runner(
            ["file", "delete", "invalid-file-id-12345", "--force"],
            check=False,
        )
        cli_helper.assert_failure(result)

    def test_file_update_metadata_no_updates_error(
        self, cli_runner: Any, cli_helper: Any, temp_test_file: Path
    ) -> None:
        """Test update-metadata fails when no updates specified."""
        unique_name = f"e2e-noupdate-{uuid.uuid4().hex[:8]}.txt"

        file_id = None
        try:
            # Upload file
            result = cli_runner(["file", "upload", str(temp_test_file), "--name", unique_name])
            cli_helper.assert_success(result)

            # Extract file ID
            for line in result.stdout.split("\n"):
                if "ID:" in line:
                    file_id = line.split("ID:")[-1].strip()
                    break

            # Try to update without specifying any changes
            result = cli_runner(
                ["file", "update-metadata", file_id],
                check=False,
            )
            cli_helper.assert_failure(result)
            assert "No updates specified" in result.stdout or "No updates" in result.stderr

        finally:
            if file_id:
                try:
                    cli_runner(["file", "delete", file_id, "--force"], check=False)
                except Exception:
                    # Ignore errors during test cleanup; file may already be deleted.
                    pass

    def test_file_download_force_overwrite(
        self,
        cli_runner: Any,
        cli_helper: Any,
        temp_test_file: Path,
        temp_download_dir: Path,
    ) -> None:
        """Test downloading file with force overwrite."""
        unique_name = f"e2e-overwrite-{uuid.uuid4().hex[:8]}.txt"

        file_id = None
        try:
            # Upload file
            result = cli_runner(["file", "upload", str(temp_test_file), "--name", unique_name])
            cli_helper.assert_success(result)

            # Extract file ID
            for line in result.stdout.split("\n"):
                if "ID:" in line:
                    file_id = line.split("ID:")[-1].strip()
                    break

            # Create existing file
            download_path = temp_download_dir / "existing.txt"
            download_path.write_text("existing content")

            # Download with --force to overwrite
            result = cli_runner(
                ["file", "download", file_id, "--output", str(download_path), "--force"]
            )
            cli_helper.assert_success(result)

            # Verify content was overwritten
            downloaded_content = download_path.read_text()
            assert downloaded_content != "existing content"

        finally:
            if file_id:
                try:
                    cli_runner(["file", "delete", file_id, "--force"], check=False)
                except Exception:
                    # Ignore errors during test cleanup; file may already be deleted.
                    pass
