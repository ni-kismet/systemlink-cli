"""E2E tests for notebook commands against dev tier."""

import json
import tempfile
import uuid
from pathlib import Path
from typing import Any

import pytest


@pytest.mark.e2e
@pytest.mark.notebook
class TestNotebookE2E:
    """End-to-end tests for notebook commands."""

    def test_notebook_list_basic(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test basic notebook list functionality."""
        result = cli_runner(["notebook", "manage", "list", "--format", "json"])
        cli_helper.assert_success(result)
        notebooks = cli_helper.get_json_output(result)
        assert isinstance(notebooks, list)

    def test_notebook_list_with_workspace_filter(
        self, cli_runner: Any, cli_helper: Any, e2e_config: Any
    ) -> None:
        """Test notebook list with workspace filtering."""
        workspace = e2e_config["workspace"]
        result = cli_runner(
            [
                "notebook",
                "manage",
                "list",
                "--workspace",
                workspace,
                "--format",
                "json",
            ]
        )
        cli_helper.assert_success(result)

        notebooks = cli_helper.get_json_output(result)
        assert isinstance(notebooks, list)

    def test_notebook_create_and_delete_cycle(
        self,
        cli_runner: Any,
        cli_helper: Any,
        sample_notebook_content: Any,
        configured_workspace: Any,
    ) -> None:
        """Test creating and deleting a notebook."""
        notebook_name = f"e2e-test-notebook-{uuid.uuid4().hex[:8]}.ipynb"

        # Create temporary file with notebook content
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ipynb", delete=False) as f:
            f.write(sample_notebook_content)
            temp_file = f.name

        try:
            # Create notebook
            result = cli_runner(
                [
                    "notebook",
                    "manage",
                    "create",
                    "--file",
                    temp_file,
                    "--name",
                    notebook_name,
                    "--workspace",
                    configured_workspace,
                ]
            )
            cli_helper.assert_success(result, "Notebook created")

            # Extract notebook ID from output
            output_lines = result.stdout.strip().split("\n")
            notebook_id = None
            for line in output_lines:
                if "ID:" in line:
                    notebook_id = line.split("ID:")[-1].strip()
                    break

            assert notebook_id, "Could not extract notebook ID from output"

            # Verify notebook exists by listing
            result = cli_runner(
                [
                    "notebook",
                    "manage",
                    "list",
                    "--workspace",
                    configured_workspace,
                    "--format",
                    "json",
                ]
            )
            cli_helper.assert_success(result)
            notebooks = cli_helper.get_json_output(result)

            created_notebook = cli_helper.find_resource_by_name(notebooks, notebook_name)
            assert created_notebook, f"Created notebook '{notebook_name}' not found in list"
            assert created_notebook["id"] == notebook_id

            # Delete notebook
            result = cli_runner(["notebook", "manage", "delete", "--id", notebook_id])
            cli_helper.assert_success(result, "Notebook deleted")

            # Verify notebook is deleted
            result = cli_runner(
                [
                    "notebook",
                    "manage",
                    "list",
                    "--workspace",
                    configured_workspace,
                    "--format",
                    "json",
                ]
            )
            cli_helper.assert_success(result)
            notebooks = cli_helper.get_json_output(result)

            deleted_notebook = cli_helper.find_resource_by_name(notebooks, notebook_name)
            assert (
                deleted_notebook is None
            ), f"Notebook '{notebook_name}' still exists after deletion"

        finally:
            # Cleanup temp file
            Path(temp_file).unlink(missing_ok=True)

    def test_notebook_download_by_id(
        self,
        cli_runner: Any,
        cli_helper: Any,
        sample_notebook_content: Any,
        configured_workspace: Any,
    ) -> None:
        """Test downloading notebook by ID."""
        notebook_name = f"e2e-download-test-{uuid.uuid4().hex[:8]}.ipynb"

        # Create temporary file with notebook content
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ipynb", delete=False) as f:
            f.write(sample_notebook_content)
            temp_file = f.name

        try:
            # Create notebook
            result = cli_runner(
                [
                    "notebook",
                    "manage",
                    "create",
                    "--file",
                    temp_file,
                    "--name",
                    notebook_name,
                    "--workspace",
                    configured_workspace,
                ]
            )
            cli_helper.assert_success(result)

            # Extract notebook ID
            output_lines = result.stdout.strip().split("\n")
            notebook_id = None
            for line in output_lines:
                if "ID:" in line:
                    notebook_id = line.split("ID:")[-1].strip()
                    break

            assert notebook_id, "Could not extract notebook ID"

            # Download notebook
            with tempfile.NamedTemporaryFile(suffix=".ipynb", delete=False) as download_file:
                download_path = download_file.name

            result = cli_runner(
                [
                    "notebook",
                    "manage",
                    "download",
                    "--id",
                    notebook_id,
                    "--output",
                    download_path,
                    "--type",
                    "content",
                ]
            )
            cli_helper.assert_success(result, "Notebook content downloaded")

            # Verify downloaded content
            assert Path(download_path).exists(), "Downloaded file does not exist"

            with open(download_path, "r") as f:
                downloaded_content = f.read()

            # Parse both as JSON to compare structure
            original_nb = json.loads(sample_notebook_content)
            downloaded_nb = json.loads(downloaded_content)

            # Verify key notebook structure
            assert downloaded_nb["nbformat"] == original_nb["nbformat"]
            assert len(downloaded_nb["cells"]) == len(original_nb["cells"])

            # Cleanup
            Path(download_path).unlink(missing_ok=True)
            cli_runner(["notebook", "manage", "delete", "--id", notebook_id], check=False)

        finally:
            Path(temp_file).unlink(missing_ok=True)

    def test_notebook_download_by_name(
        self,
        cli_runner: Any,
        cli_helper: Any,
        sample_notebook_content: Any,
        configured_workspace: Any,
    ) -> None:
        """Test downloading notebook by name."""
        notebook_name = f"e2e-download-name-test-{uuid.uuid4().hex[:8]}.ipynb"

        # Create temporary file with notebook content
        with tempfile.NamedTemporaryFile(mode="w", suffix=".ipynb", delete=False) as f:
            f.write(sample_notebook_content)
            temp_file = f.name

        try:
            # Create notebook
            result = cli_runner(
                [
                    "notebook",
                    "manage",
                    "create",
                    "--file",
                    temp_file,
                    "--name",
                    notebook_name,
                    "--workspace",
                    configured_workspace,
                ]
            )
            cli_helper.assert_success(result)

            # Download notebook by name
            with tempfile.NamedTemporaryFile(suffix=".ipynb", delete=False) as download_file:
                download_path = download_file.name

            result = cli_runner(
                [
                    "notebook",
                    "manage",
                    "download",
                    "--name",
                    notebook_name,
                    "--workspace",
                    configured_workspace,
                    "--output",
                    download_path,
                    "--type",
                    "content",
                ]
            )
            cli_helper.assert_success(result, "Notebook content downloaded")

            # Verify downloaded content exists
            assert Path(download_path).exists(), "Downloaded file does not exist"

            # Cleanup
            Path(download_path).unlink(missing_ok=True)

            # Get notebook ID for cleanup
            result = cli_runner(
                [
                    "notebook",
                    "manage",
                    "list",
                    "--workspace",
                    configured_workspace,
                    "--format",
                    "json",
                ]
            )
            notebooks = cli_helper.get_json_output(result)
            notebook = cli_helper.find_resource_by_name(notebooks, notebook_name)
            if notebook:
                cli_runner(["notebook", "manage", "delete", "--id", notebook["id"]], check=False)

        finally:
            Path(temp_file).unlink(missing_ok=True)

    @pytest.mark.slow
    def test_notebook_pagination(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test notebook list pagination."""
        # Test with small take value to trigger pagination

        result = cli_runner(["notebook", "manage", "list", "--take", "5", "--format", "table"])
        cli_helper.assert_success(result)

        # Should either show notebooks or "No notebooks found"
        assert "Notebook" in result.stdout or "No notebooks found" in result.stdout

    def test_notebook_error_handling(self, cli_runner: Any, cli_helper: Any) -> None:
        """Test error handling for invalid operations."""
        # Test download with invalid ID
        result = cli_runner(
            [
                "notebook",
                "manage",
                "download",
                "--id",
                "invalid-notebook-id-12345",
                "--type",
                "content",
            ],
            check=False,
        )
        cli_helper.assert_failure(result)

        # Test delete with invalid ID
        result = cli_runner(
            ["notebook", "manage", "delete", "--id", "invalid-notebook-id-12345"], check=False
        )
        cli_helper.assert_failure(result)

    def test_notebook_create_without_file(
        self, cli_runner: Any, cli_helper: Any, configured_workspace: Any
    ) -> None:
        """Test creating empty notebook without file."""
        notebook_name = f"e2e-empty-notebook-{uuid.uuid4().hex[:8]}.ipynb"

        # Create empty notebook
        result = cli_runner(
            [
                "notebook",
                "manage",
                "create",
                "--name",
                notebook_name,
                "--workspace",
                configured_workspace,
            ]
        )
        cli_helper.assert_success(result, "Notebook created")

        # Extract notebook ID for cleanup
        output_lines = result.stdout.strip().split("\n")
        notebook_id = None
        for line in output_lines:
            if "ID:" in line:
                notebook_id = line.split("ID:")[-1].strip()
                break

        if notebook_id:
            # Cleanup
            cli_runner(["notebook", "manage", "delete", "--id", notebook_id], check=False)
