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
        self, cli_runner: Any, cli_helper: Any, configured_workspace: str
    ) -> None:
        """Test notebook list with workspace filtering."""
        workspace = configured_workspace
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

            # Delete notebook (need to confirm with 'y')
            result = cli_runner(
                ["notebook", "manage", "delete", "--id", notebook_id], input_data="y\n"
            )
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
            cli_runner(
                ["notebook", "manage", "delete", "--id", notebook_id],
                input_data="y\n",
                check=False,
            )

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
                cli_runner(
                    ["notebook", "manage", "delete", "--id", notebook["id"]],
                    input_data="y\n",
                    check=False,
                )

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
            cli_runner(
                ["notebook", "manage", "delete", "--id", notebook_id],
                input_data="y\n",
                check=False,
            )


@pytest.mark.e2e
@pytest.mark.notebook
@pytest.mark.sls
class TestNotebookExecutionSLSE2E:
    """End-to-end tests for notebook execution commands on SystemLink Server (SLS).

    These tests use the SLS-specific ninbexec/v2 API which uses notebookPath
    instead of notebookId.
    """

    def test_notebook_execute_list_basic(
        self, sls_cli_runner: Any, sls_cli_helper: Any, require_sls: Any
    ) -> None:
        """Test listing notebook executions on SLS."""
        result = sls_cli_runner(["notebook", "execute", "list", "--format", "json"])
        sls_cli_helper.assert_success(result)
        executions = sls_cli_helper.get_json_output(result)
        assert isinstance(executions, list)

    def test_notebook_execute_list_with_status_filter(
        self, sls_cli_runner: Any, sls_cli_helper: Any, require_sls: Any
    ) -> None:
        """Test listing executions with status filter on SLS."""
        # Test various status filters
        for status in ["succeeded", "failed", "queued"]:
            result = sls_cli_runner(
                ["notebook", "execute", "list", "--status", status, "--format", "json"]
            )
            sls_cli_helper.assert_success(result)
            executions = sls_cli_helper.get_json_output(result)
            assert isinstance(executions, list)

    def test_notebook_execute_list_table_format(
        self, sls_cli_runner: Any, sls_cli_helper: Any, require_sls: Any
    ) -> None:
        """Test listing executions in table format on SLS."""
        result = sls_cli_runner(["notebook", "execute", "list", "--format", "table", "--take", "5"])
        sls_cli_helper.assert_success(result)
        # SLS table should show "Notebook Path" column, not "Notebook ID"
        # Either shows executions or "No notebook executions found"
        assert "Notebook Path" in result.stdout or "No notebook executions found" in result.stdout

    def test_notebook_execute_start_with_path(
        self, sls_cli_runner: Any, sls_cli_helper: Any, require_sls: Any, sls_config: Any
    ) -> None:
        """Test starting a notebook execution using notebookPath on SLS.

        Note: Requires a valid notebook path in the SLS environment.
        """
        # Check if a test notebook path is configured
        test_notebook_path = sls_config.get("test_notebook_path")
        if not test_notebook_path:
            pytest.skip("No test notebook path configured (test_notebook_path)")

        result = sls_cli_runner(
            [
                "notebook",
                "execute",
                "start",
                "--notebook-id",  # On SLS this is treated as notebook path
                test_notebook_path,
                "--format",
                "json",
            ]
        )
        sls_cli_helper.assert_success(result)
        execution = sls_cli_helper.get_json_output(result)
        assert "id" in execution
        assert "status" in execution

        # Cancel the execution to clean up
        execution_id = execution.get("id")
        if execution_id:
            sls_cli_runner(
                ["notebook", "execute", "cancel", "--id", execution_id],
                check=False,
            )

    def test_notebook_execute_get_details(
        self, sls_cli_runner: Any, sls_cli_helper: Any, require_sls: Any
    ) -> None:
        """Test getting execution details on SLS."""
        # First, list executions to get an ID
        result = sls_cli_runner(["notebook", "execute", "list", "--format", "json", "--take", "1"])
        sls_cli_helper.assert_success(result)
        executions = sls_cli_helper.get_json_output(result)

        if not executions:
            pytest.skip("No executions available to test get details")

        execution_id = executions[0].get("id")
        assert execution_id, "No execution ID found"

        # Get execution details
        result = sls_cli_runner(
            ["notebook", "execute", "get", "--id", execution_id, "--format", "json"]
        )
        sls_cli_helper.assert_success(result)
        details = sls_cli_helper.get_json_output(result)

        # SLS should return notebookPath, not notebookId
        assert "id" in details
        assert "status" in details
        assert "notebookPath" in details, "SLS execution should have notebookPath"

    def test_notebook_execute_get_table_format(
        self, sls_cli_runner: Any, sls_cli_helper: Any, require_sls: Any
    ) -> None:
        """Test getting execution details in table format on SLS."""
        # First, list executions to get an ID
        result = sls_cli_runner(["notebook", "execute", "list", "--format", "json", "--take", "1"])
        sls_cli_helper.assert_success(result)
        executions = sls_cli_helper.get_json_output(result)

        if not executions:
            pytest.skip("No executions available to test get details")

        execution_id = executions[0].get("id")

        # Get execution details in table format
        result = sls_cli_runner(
            ["notebook", "execute", "get", "--id", execution_id, "--format", "table"]
        )
        sls_cli_helper.assert_success(result)
        # SLS table should show "Notebook Path" not "Notebook ID"
        assert "Notebook Path:" in result.stdout

    def test_notebook_execute_cancel(
        self, sls_cli_runner: Any, sls_cli_helper: Any, require_sls: Any, sls_config: Any
    ) -> None:
        """Test canceling a notebook execution on SLS.

        SLS uses the bulk cancel endpoint POST /cancel-executions.
        """
        # Check if a test notebook path is configured
        test_notebook_path = sls_config.get("test_notebook_path")
        if not test_notebook_path:
            pytest.skip("No test notebook path configured (test_notebook_path)")

        # Start an execution
        result = sls_cli_runner(
            [
                "notebook",
                "execute",
                "start",
                "--notebook-id",
                test_notebook_path,
                "--format",
                "json",
            ]
        )
        sls_cli_helper.assert_success(result)
        execution = sls_cli_helper.get_json_output(result)
        execution_id = execution.get("id")
        assert execution_id, "No execution ID returned"

        # Cancel the execution
        result = sls_cli_runner(["notebook", "execute", "cancel", "--id", execution_id])
        sls_cli_helper.assert_success(result, "cancellation requested")

    def test_notebook_execute_retry_not_available_on_sls(
        self, sls_cli_runner: Any, sls_cli_helper: Any, require_sls: Any
    ) -> None:
        """Test that retry command fails gracefully on SLS.

        SLS does not support the retry endpoint - the CLI should show a clear error.
        Verifies both the error message content and the exit code.
        """
        # Use a fake execution ID - we just want to verify the error message
        result = sls_cli_runner(
            ["notebook", "execute", "retry", "--id", "fake-execution-id"],
            check=False,
        )
        # Verify the error message explains SLS doesn't support retry
        sls_cli_helper.assert_failure(result, "not available on SystemLink Server")
        # Verify correct exit code (INVALID_INPUT = 2)
        assert result.returncode == 2, f"Expected exit code 2, got {result.returncode}"

    def test_notebook_execute_invalid_status_filter(
        self, sls_cli_runner: Any, sls_cli_helper: Any, require_sls: Any
    ) -> None:
        """Test that invalid status filter shows proper error."""
        result = sls_cli_runner(
            ["notebook", "execute", "list", "--status", "invalid_status"],
            check=False,
        )
        sls_cli_helper.assert_failure(result, "Invalid status")


@pytest.mark.e2e
@pytest.mark.notebook
@pytest.mark.sle
class TestNotebookExecutionSLEE2E:
    """End-to-end tests for notebook execution commands on SystemLink Enterprise (SLE).

    These tests use the SLE-specific ninbexecution/v1 API which uses notebookId
    and workspaceId.
    """

    def test_notebook_execute_list_basic(
        self, sle_cli_runner: Any, sle_cli_helper: Any, require_sle: Any
    ) -> None:
        """Test listing notebook executions on SLE."""
        result = sle_cli_runner(["notebook", "execute", "list", "--format", "json"])
        sle_cli_helper.assert_success(result)
        executions = sle_cli_helper.get_json_output(result)
        assert isinstance(executions, list)

    def test_notebook_execute_list_with_workspace_filter(
        self, sle_cli_runner: Any, sle_cli_helper: Any, require_sle: Any, sle_workspace: Any
    ) -> None:
        """Test listing executions with workspace filter on SLE."""
        result = sle_cli_runner(
            [
                "notebook",
                "execute",
                "list",
                "--workspace",
                sle_workspace,
                "--format",
                "json",
            ]
        )
        sle_cli_helper.assert_success(result)
        executions = sle_cli_helper.get_json_output(result)
        assert isinstance(executions, list)

    def test_notebook_execute_list_table_format(
        self, sle_cli_runner: Any, sle_cli_helper: Any, require_sle: Any
    ) -> None:
        """Test listing executions in table format on SLE."""
        result = sle_cli_runner(["notebook", "execute", "list", "--format", "table", "--take", "5"])
        sle_cli_helper.assert_success(result)
        # SLE table should show "Notebook ID" and "Workspace" columns
        # Either shows executions or "No notebook executions found"
        assert "Notebook ID" in result.stdout or "No notebook executions found" in result.stdout

    def test_notebook_execute_get_details(
        self, sle_cli_runner: Any, sle_cli_helper: Any, require_sle: Any
    ) -> None:
        """Test getting execution details on SLE."""
        # First, list executions to get an ID
        result = sle_cli_runner(["notebook", "execute", "list", "--format", "json", "--take", "1"])
        sle_cli_helper.assert_success(result)
        executions = sle_cli_helper.get_json_output(result)

        if not executions:
            pytest.skip("No executions available to test get details")

        execution_id = executions[0].get("id")
        assert execution_id, "No execution ID found"

        # Get execution details
        result = sle_cli_runner(
            ["notebook", "execute", "get", "--id", execution_id, "--format", "json"]
        )
        sle_cli_helper.assert_success(result)
        details = sle_cli_helper.get_json_output(result)

        # SLE should return notebookId and workspaceId
        assert "id" in details
        assert "status" in details
        assert "notebookId" in details, "SLE execution should have notebookId"

    def test_notebook_execute_get_table_format(
        self, sle_cli_runner: Any, sle_cli_helper: Any, require_sle: Any
    ) -> None:
        """Test getting execution details in table format on SLE."""
        # First, list executions to get an ID
        result = sle_cli_runner(["notebook", "execute", "list", "--format", "json", "--take", "1"])
        sle_cli_helper.assert_success(result)
        executions = sle_cli_helper.get_json_output(result)

        if not executions:
            pytest.skip("No executions available to test get details")

        execution_id = executions[0].get("id")

        # Get execution details in table format
        result = sle_cli_runner(
            ["notebook", "execute", "get", "--id", execution_id, "--format", "table"]
        )
        sle_cli_helper.assert_success(result)
        # SLE table should show "Notebook ID" and "Workspace"
        assert "Notebook ID:" in result.stdout
        assert "Workspace:" in result.stdout

    def test_notebook_execute_retry_available_on_sle(
        self, sle_cli_runner: Any, sle_cli_helper: Any, require_sle: Any
    ) -> None:
        """Test that retry command is available on SLE (may fail if no failed execution).

        This just verifies the command doesn't immediately fail with "not available".
        """
        # Use a fake execution ID - we expect a different error than "not available"
        result = sle_cli_runner(
            ["notebook", "execute", "retry", "--id", "fake-execution-id"],
            check=False,
        )
        # On SLE, should NOT see "not available on SystemLink Server"
        assert "not available on SystemLink Server" not in result.stderr
        assert "not available on SystemLink Server" not in result.stdout
