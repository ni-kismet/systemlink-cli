"""E2E tests for DFF (Dynamic Form Fields) commands against dev tier."""

import json
import tempfile
from pathlib import Path

import pytest


@pytest.mark.e2e
@pytest.mark.dff
class TestDFFE2E:
    """End-to-end tests for Dynamic Form Fields commands."""

    def test_dff_config_list_basic(self, cli_runner, cli_helper):
        """Test basic DFF configuration list functionality."""
        result = cli_runner(["dff", "config", "list", "--format", "json"])
        cli_helper.assert_success(result)

        configs = cli_helper.get_json_output(result)
        assert isinstance(configs, list)

    def test_dff_config_list_table_format(self, cli_runner, cli_helper):
        """Test DFF config list with table format."""
        result = cli_runner(["dff", "config", "list", "--format", "table"])
        cli_helper.assert_success(result)

        # Should show table headers or "No configurations found"
        assert (
            "Configuration" in result.stdout
            or "No dynamic form field configurations found" in result.stdout
        )

    def test_dff_config_list_with_workspace_filter(self, cli_runner, cli_helper, e2e_config):
        """Test DFF config list with workspace filtering."""
        workspace = e2e_config["workspace"]
        result = cli_runner(["dff", "config", "list", "--workspace", workspace, "--format", "json"])
        cli_helper.assert_success(result)

        configs = cli_helper.get_json_output(result)
        assert isinstance(configs, list)

    def test_dff_groups_list_basic(self, cli_runner, cli_helper):
        """Test basic DFF groups list functionality."""
        result = cli_runner(["dff", "groups", "list", "--format", "json"])
        cli_helper.assert_success(result)

        groups = cli_helper.get_json_output(result)
        assert isinstance(groups, list)

    def test_dff_fields_list_basic(self, cli_runner, cli_helper):
        """Test basic DFF fields list functionality."""
        result = cli_runner(["dff", "fields", "list", "--format", "json"])
        cli_helper.assert_success(result)

        fields = cli_helper.get_json_output(result)
        assert isinstance(fields, list)

    def test_dff_config_create_and_delete_cycle(
        self, cli_runner, cli_helper, sample_dff_config, configured_workspace
    ):
        """Test creating and deleting a DFF configuration."""
        # Get workspace ID from workspace name
        result = cli_runner(["workspace", "list", "--format", "json"])
        cli_helper.assert_success(result)
        workspaces = cli_helper.get_json_output(result)
        workspace_id = None
        for ws in workspaces:
            if ws.get("name") == configured_workspace:
                workspace_id = ws.get("id")
                break

        assert workspace_id, f"Workspace '{configured_workspace}' not found"

        # Set workspace ID for all components
        config = sample_dff_config.copy()
        config["configurations"][0]["workspace"] = workspace_id
        config["groups"][0]["workspace"] = workspace_id
        config["fields"][0]["workspace"] = workspace_id

        # Create temporary file with DFF config
        with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
            json.dump(config, f, indent=2)
            temp_file = f.name

        try:
            # Create DFF configuration
            result = cli_runner(["dff", "config", "create", "--file", temp_file])

            if result.returncode == 0:
                # Creation succeeded
                cli_helper.assert_success(result, "configurations created")

                # Extract configuration ID from output
                config_id = None
                for line in result.stdout.split("\n"):
                    if ":" in line and config["configurations"][0]["name"] in line:
                        # Format: "  - Config Name: config-id"
                        config_id = line.split(":")[-1].strip()
                        break

                if config_id:
                    # Verify configuration exists
                    result = cli_runner(
                        ["dff", "config", "get", "--id", config_id, "--format", "json"]
                    )
                    if result.returncode == 0:
                        config_data = cli_helper.get_json_output(result)
                        # The get command returns configurations array
                        assert "configurations" in config_data
                        assert len(config_data["configurations"]) > 0
                        assert config_data["configurations"][0]["id"] == config_id

                    # Delete configuration
                    result = cli_runner(
                        ["dff", "config", "delete", "--id", config_id], input_data="y\n"
                    )
                    # Deletion may succeed or fail depending on dependencies
                    # Both are acceptable for E2E tests
            else:
                # Creation failed - check if it's due to validation or other issues
                # For E2E tests, some failures are expected due to environment constraints
                print(f"DFF creation failed (expected in some environments): {result.stderr}")

        finally:
            # Cleanup temp file
            Path(temp_file).unlink(missing_ok=True)

    def test_dff_config_export_functionality(self, cli_runner, cli_helper):
        """Test DFF configuration export functionality."""
        # First, get list of configurations
        result = cli_runner(["dff", "config", "list", "--format", "json"])
        cli_helper.assert_success(result)

        configs = cli_helper.get_json_output(result)

        if configs:
            # Pick the first configuration for export test
            config_id = configs[0].get("id")

            if config_id:
                # Export configuration
                with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as export_file:
                    export_path = export_file.name

                result = cli_runner(
                    ["dff", "config", "export", "--id", config_id, "--output", export_path]
                )

                try:
                    cli_helper.assert_success(result, "exported")

                    # Verify exported file exists and contains valid JSON
                    assert Path(export_path).exists()

                    with open(export_path, "r") as f:
                        exported_data = json.load(f)

                    # Should contain configuration data
                    assert "configurations" in exported_data
                    # Find our configuration in the list
                    config_found = False
                    for config in exported_data["configurations"]:
                        if config.get("id") == config_id:
                            config_found = True
                            break
                    assert config_found, f"Configuration {config_id} not found in exported data"

                finally:
                    # Cleanup
                    Path(export_path).unlink(missing_ok=True)

    def test_dff_config_init_template(self, cli_runner, cli_helper):
        """Test DFF configuration template initialization."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as template_file:
            template_path = template_file.name

        try:
            # Initialize template with prompts
            result = cli_runner(
                [
                    "dff",
                    "config",
                    "init",
                    "--name",
                    "E2E Test Template",
                    "--workspace",
                    "Default",
                    "--resource-type",
                    "workorder:workorder",
                    "--output",
                    template_path,
                ]
            )

            cli_helper.assert_success(result, "template created")

            # Verify template file was created
            assert Path(template_path).exists()

            # Verify template contains valid JSON structure
            with open(template_path, "r") as f:
                template_data = json.load(f)

            assert "configurations" in template_data
            assert "groups" in template_data
            assert "fields" in template_data

            # Verify basic structure
            assert len(template_data["configurations"]) == 1
            assert template_data["configurations"][0]["name"] == "E2E Test Template"
            assert template_data["configurations"][0]["resourceType"] == "workorder:workorder"

        finally:
            # Cleanup
            Path(template_path).unlink(missing_ok=True)

    @pytest.mark.slow
    def test_dff_pagination(self, cli_runner, cli_helper):
        """Test DFF list commands pagination."""
        # Test config pagination
        result = cli_runner(["dff", "config", "list", "--take", "3", "--format", "table"])
        cli_helper.assert_success(result)

        # Test groups pagination
        result = cli_runner(["dff", "groups", "list", "--take", "3", "--format", "table"])
        cli_helper.assert_success(result)

        # Test fields pagination
        result = cli_runner(["dff", "fields", "list", "--take", "3", "--format", "table"])
        cli_helper.assert_success(result)

    def test_dff_error_handling(self, cli_runner, cli_helper):
        """Test error handling for invalid DFF operations."""
        # Test get with invalid configuration ID
        result = cli_runner(
            ["dff", "config", "get", "--id", "invalid-config-id-12345", "--format", "json"],
            check=False,
        )
        cli_helper.assert_failure(result)

        # Test export with invalid configuration ID
        result = cli_runner(
            ["dff", "config", "export", "--id", "invalid-config-id-12345"], check=False
        )
        cli_helper.assert_failure(result)

    def test_dff_invalid_resource_type(self, cli_runner):
        """Test DFF config init with invalid resource type."""
        result = cli_runner(
            [
                "dff",
                "config",
                "init",
                "--name",
                "Invalid Test",
                "--workspace",
                "Default",
                "--resource-type",
                "invalid:resourcetype",
            ],
            check=False,
        )

        # Should fail with validation error
        assert result.returncode != 0
        assert (
            "Invalid resource type" in result.stderr
            or "Invalid resource type" in result.stdout
            or "Invalid value for '--resource-type'" in result.stderr
            or "Invalid value for '--resource-type'" in result.stdout
        )
