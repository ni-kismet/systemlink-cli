"""Tests for DFF (Dynamic Form Fields) CLI commands."""

import json
import tempfile
from pathlib import Path
from typing import Any

import click
import pytest
from click.testing import CliRunner

from slcli.dff_click import register_dff_commands
from .test_utils import patch_keyring


def make_cli() -> click.Group:
    """Create a dummy CLI for testing."""

    @click.group()
    def cli() -> None:
        pass

    register_dff_commands(cli)
    return cli


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


def mock_requests(
    monkeypatch: Any, method: str, response_json: Any, status_code: int = 200
) -> None:
    """Mock requests for testing."""

    class MockResponse:
        def __init__(self) -> None:
            self.status_code = status_code

        def json(self) -> Any:
            return response_json

        def raise_for_status(self) -> None:
            if self.status_code >= 400:
                raise Exception("HTTP error")

        @property
        def text(self) -> str:
            return json.dumps(response_json) if response_json else ""

    monkeypatch.setattr("requests." + method, lambda *a, **kw: MockResponse())


def test_dff_config_list_success(monkeypatch: Any, runner: CliRunner) -> None:
    """Test listing DFF configurations with a successful response."""
    patch_keyring(monkeypatch)

    def mock_get(*a: Any, **kw: Any) -> Any:
        class R:
            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {
                    "configurations": [
                        {
                            "id": "config1",
                            "name": "Test Configuration",
                            "workspace": "ws1",
                            "resourceType": "workorder:workorder",
                        }
                    ]
                }

        return R()

    def mock_workspace_get(*a: Any, **kw: Any) -> Any:
        class R:
            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"workspaces": [{"id": "ws1", "name": "TestWorkspace"}]}

        return R()

    monkeypatch.setattr("requests.get", mock_get)
    monkeypatch.setattr(
        "slcli.dff_click.make_api_request", lambda method, url, *args, **kwargs: mock_get()
    )
    monkeypatch.setattr(
        "slcli.utils.make_api_request", lambda method, url, *args, **kwargs: mock_workspace_get()
    )

    cli = make_cli()
    result = runner.invoke(cli, ["customfields", "list"])

    assert result.exit_code == 0
    assert "Test Configuration" in result.output
    assert "config1" in result.output


def test_dff_config_list_json_format(monkeypatch: Any, runner: CliRunner) -> None:
    """Test listing DFF configurations with JSON output."""
    patch_keyring(monkeypatch)

    configurations = [
        {
            "id": "config1",
            "name": "Test Configuration",
            "workspace": "ws1",
            "resourceType": "workorder:workorder",
        }
    ]

    def mock_get(*a: Any, **kw: Any) -> Any:
        class R:
            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"configurations": configurations}

        return R()

    monkeypatch.setattr(
        "slcli.dff_click.make_api_request", lambda method, url, *args, **kwargs: mock_get()
    )

    cli = make_cli()
    result = runner.invoke(cli, ["customfields", "list", "--format", "json"])

    assert result.exit_code == 0
    output_json = json.loads(result.output)
    assert len(output_json) == 1
    assert output_json[0]["name"] == "Test Configuration"


def test_dff_config_get_success(monkeypatch: Any, runner: CliRunner) -> None:
    """Test getting a specific DFF configuration."""
    patch_keyring(monkeypatch)

    config_data = {
        "configuration": {
            "id": "config1",
            "name": "Test Configuration",
            "workspace": "ws1",
            "resourceType": "workorder:workorder",
        },
        "groups": [],
        "fields": [],
    }

    def mock_get(*a: Any, **kw: Any) -> Any:
        class R:
            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return config_data

        return R()

    monkeypatch.setattr(
        "slcli.dff_click.make_api_request", lambda method, url, *args, **kwargs: mock_get()
    )

    cli = make_cli()
    result = runner.invoke(cli, ["customfields", "get", "--id", "config1"])

    assert result.exit_code == 0
    output_json = json.loads(result.output)
    assert output_json["configuration"]["name"] == "Test Configuration"


def test_dff_config_init_success(runner: CliRunner, monkeypatch: Any) -> None:
    """Test initializing a new DFF configuration template.

    DFF is an SLE-only feature, so we explicitly set platform='SLE'.
    """
    patch_keyring(monkeypatch, platform="SLE")
    cli = make_cli()

    with tempfile.TemporaryDirectory() as temp_dir:
        output_file = Path(temp_dir) / "test-config.json"

        result = runner.invoke(
            cli,
            [
                "customfields",
                "init",
                "--name",
                "Test Config",
                "--workspace",
                "test-workspace",
                "--resource-type",
                "workorder:workorder",
                "--output",
                str(output_file),
            ],
        )

        assert result.exit_code == 0
        assert output_file.exists()

        # Verify the content
        with open(output_file) as f:
            config_data = json.load(f)

        assert len(config_data["configurations"]) == 1
        config = config_data["configurations"][0]
        assert config["name"] == "Test Config"
        assert config["key"].startswith("test-config-config-")  # Now includes unique suffix
        assert config["resourceType"] == "workorder:workorder"
        assert config["workspace"] == "test-workspace"
        assert "views" in config
        assert len(config["views"]) == 1
        assert config["views"][0]["key"].startswith("default-view-")  # Now includes unique suffix
        assert config["views"][0]["displayText"] == "Default View"
        assert len(config["views"][0]["groups"]) == 1
        assert config["views"][0]["groups"][0].startswith("group1-")  # Now includes unique suffix

        assert len(config_data["groups"]) == 1
        group = config_data["groups"][0]
        assert group["key"].startswith("group1-")  # Now includes unique suffix
        assert group["displayText"] == "Example Group"
        assert len(group["fields"]) == 2
        assert group["fields"][0].startswith("field1-")  # Now includes unique suffix
        assert group["fields"][1].startswith("field2-")  # Now includes unique suffix

        assert len(config_data["fields"]) == 2
        field1 = config_data["fields"][0]
        assert field1["key"].startswith("field1-")  # Now includes unique suffix
        assert field1["type"] == "Text"
        assert field1["mandatory"] is False


def test_dff_config_create_success(monkeypatch: Any, runner: CliRunner) -> None:
    """Test creating DFF configurations from file."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            def __init__(self) -> None:
                self.status_code = 201

            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"configurations": [{"id": "new-config-id", "name": "Test Configuration"}]}

            @property
            def text(self) -> str:
                return json.dumps(self.json())

        return R()

    monkeypatch.setattr(
        "slcli.dff_click.make_api_request", lambda method, url, data, *args, **kwargs: mock_post()
    )

    cli = make_cli()

    # Create test input file
    with tempfile.NamedTemporaryFile(mode="w", suffix=".json", delete=False) as f:
        test_config = {
            "configurations": [
                {
                    "name": "Test Configuration",
                    "workspace": "ws1",
                    "resourceType": "workorder:workorder",
                    "groupKeys": [],
                }
            ]
        }
        json.dump(test_config, f)
        input_file = f.name

    try:
        result = runner.invoke(cli, ["customfields", "create", "--file", input_file])
        assert result.exit_code == 0
        assert "configurations created successfully" in result.output
    finally:
        Path(input_file).unlink()


def test_dff_config_create_validation_error(monkeypatch: Any, runner: CliRunner) -> None:
    """Test creating DFF configurations with validation errors."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            def __init__(self) -> None:
                self.status_code = 400

            def raise_for_status(self) -> None:
                import requests

                response = requests.Response()
                response.status_code = 400
                response._content = json.dumps(
                    {
                        "type": "https://tools.ietf.org/html/rfc9110#section-15.5.1",
                        "title": "One or more validation errors occurred.",
                        "status": 400,
                        "errors": {
                            "request": ["The request field is required."],
                            "$.fields[0].type": ["Unknown value INVALID_TYPE."],
                        },
                        "traceId": "00-test-trace-id",
                    }
                ).encode()
                raise requests.RequestException(response=response)

            def json(self) -> Any:
                return {
                    "type": "https://tools.ietf.org/html/rfc9110#section-15.5.1",
                    "title": "One or more validation errors occurred.",
                    "status": 400,
                    "errors": {
                        "request": ["The request field is required."],
                        "$.fields[0].type": ["Unknown value INVALID_TYPE."],
                    },
                    "traceId": "00-test-trace-id",
                }

        return R()

    monkeypatch.setattr("slcli.utils.requests.post", mock_post)

    cli = make_cli()

    # Create a config file with validation errors
    invalid_config = {
        "configurations": [
            {
                "name": "test",
                "key": "test-key",
                "workspace": "test-workspace",
                "resourceType": "workorder:workorder",
            }
        ]
    }

    input_file = "test_invalid_config.json"
    with open(input_file, "w") as f:
        json.dump(invalid_config, f)

    try:
        result = runner.invoke(cli, ["customfields", "create", "--file", input_file])
        assert result.exit_code == 2  # ExitCodes.INVALID_INPUT
        assert "Validation errors occurred" in result.output
        assert "request: The request field is required" in result.output
        assert "$.fields[0].type: Unknown value INVALID_TYPE" in result.output
    finally:
        Path(input_file).unlink()


def test_dff_config_export_success(monkeypatch: Any, runner: CliRunner) -> None:
    """Test exporting a DFF configuration."""
    patch_keyring(monkeypatch)

    config_data = {
        "configuration": {"id": "config1", "name": "Test Configuration", "workspace": "ws1"},
        "groups": [],
        "fields": [],
    }

    def mock_get(*a: Any, **kw: Any) -> Any:
        class R:
            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return config_data

        return R()

    monkeypatch.setattr(
        "slcli.dff_click.make_api_request", lambda method, url, *args, **kwargs: mock_get()
    )

    cli = make_cli()

    with tempfile.TemporaryDirectory() as temp_dir:
        output_file = Path(temp_dir) / "exported-config.json"

        result = runner.invoke(
            cli, ["customfields", "export", "--id", "config1", "--output", str(output_file)]
        )

        assert result.exit_code == 0
        assert output_file.exists()
        assert "Configuration exported" in result.output

        # Verify exported content
        with open(output_file) as f:
            exported_data = json.load(f)

        assert exported_data["configuration"]["name"] == "Test Configuration"


def test_dff_config_delete_confirmation_abort(monkeypatch: Any, runner: CliRunner) -> None:
    """Test that config deletion can be aborted via confirmation prompt."""
    patch_keyring(monkeypatch)

    cli = make_cli()

    # Simulate user saying 'no' to confirmation
    result = runner.invoke(cli, ["customfields", "delete", "--id", "config1"], input="n\n")

    assert result.exit_code == 1  # Aborted
    assert "Aborted" in result.output


def test_dff_config_workspace_filtering(monkeypatch: Any, runner: CliRunner) -> None:
    """Test workspace filtering in config list."""
    patch_keyring(monkeypatch)

    def mock_get(*a: Any, **kw: Any) -> Any:
        class R:
            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {
                    "configurations": [
                        {"id": "config1", "name": "Config 1", "workspace": "ws1"},
                        {"id": "config2", "name": "Config 2", "workspace": "ws2"},
                    ]
                }

        return R()

    def mock_workspace_get(*a: Any, **kw: Any) -> Any:
        class R:
            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {
                    "workspaces": [
                        {"id": "ws1", "name": "Workspace1"},
                        {"id": "ws2", "name": "Workspace2"},
                    ]
                }

        return R()

    monkeypatch.setattr(
        "slcli.dff_click.make_api_request", lambda method, url, *args, **kwargs: mock_get()
    )
    monkeypatch.setattr(
        "slcli.utils.make_api_request", lambda method, url, *args, **kwargs: mock_workspace_get()
    )

    cli = make_cli()

    # Test filtering by workspace name
    result = runner.invoke(cli, ["customfields", "list", "--workspace", "Workspace1"])
    assert result.exit_code == 0
    assert "Config 1" in result.output
    assert "Config 2" not in result.output


def test_dff_help_commands(runner: CliRunner, monkeypatch: Any) -> None:
    """Test that help is available for all DFF commands."""
    patch_keyring(monkeypatch)
    cli = make_cli()

    # Test main customfields help
    result = runner.invoke(cli, ["customfields", "--help"])
    assert result.exit_code == 0
    assert "Manage custom field" in result.output


def test_dff_edit_command_help(runner: CliRunner, monkeypatch: Any) -> None:
    """Test that the edit command shows proper help."""
    patch_keyring(monkeypatch)
    cli = make_cli()

    result = runner.invoke(cli, ["customfields", "edit", "--help"])
    assert result.exit_code == 0
    assert "Launch a local web editor" in result.output
    assert "--port" in result.output
    assert "--no-browser" in result.output


def test_dff_edit_with_config_id_loads_config(monkeypatch: Any, runner: CliRunner) -> None:
    """Test that dff edit --id loads configuration from server."""
    patch_keyring(monkeypatch)

    # Track calls to save_json_file
    saved_files: dict[str, Any] = {}

    def mock_save_json_file(data: Any, path: str) -> None:
        saved_files[path] = data

    def mock_get(*a: Any, **kw: Any) -> Any:
        class R:
            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {
                    "configuration": {
                        "id": "test-config-123",
                        "name": "Test Config",
                        "workspace": "ws1",
                    },
                    "groups": [],
                    "fields": [],
                }

        return R()

    # Mock launch_dff_editor to prevent actual server launch
    def mock_launch_editor(*args: Any, **kwargs: Any) -> None:
        pass

    monkeypatch.setattr("slcli.dff_click.make_api_request", lambda *a, **kw: mock_get())
    monkeypatch.setattr("slcli.dff_click.save_json_file", mock_save_json_file)
    monkeypatch.setattr("slcli.dff_click.launch_dff_editor", mock_launch_editor)

    cli = make_cli()
    result = runner.invoke(cli, ["customfields", "edit", "--id", "test-config-123", "--no-browser"])

    assert result.exit_code == 0

    # Check that configuration file was saved (not metadata file)
    config_files = [path for path in saved_files.keys() if ".json" in path]
    assert len(config_files) >= 1


def test_dff_edit_with_config_id_fetches_resolved_configuration(
    monkeypatch: Any, runner: CliRunner
) -> None:
    """Test that dff edit --id uses resolved-configuration endpoint."""
    patch_keyring(monkeypatch)

    requested_url = None

    def mock_make_api_request(method: str, url: str, *args: Any, **kwargs: Any) -> Any:
        nonlocal requested_url
        requested_url = url

        class R:
            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {
                    "configuration": {"id": "cfg-123", "name": "Config"},
                    "groups": [],
                    "fields": [],
                }

        return R()

    def mock_launch_editor(*args: Any, **kwargs: Any) -> None:
        pass

    def mock_save_json_file(data: Any, path: str) -> None:
        pass

    monkeypatch.setattr("slcli.dff_click.make_api_request", mock_make_api_request)
    monkeypatch.setattr("slcli.dff_click.launch_dff_editor", mock_launch_editor)
    monkeypatch.setattr("slcli.dff_click.save_json_file", mock_save_json_file)

    cli = make_cli()
    result = runner.invoke(cli, ["customfields", "edit", "--id", "cfg-123", "--no-browser"])

    assert result.exit_code == 0
    assert requested_url is not None
    assert "resolved-configuration" in requested_url
    assert "configurationId=cfg-123" in requested_url


def test_dff_edit_without_id_no_metadata_saved(monkeypatch: Any, runner: CliRunner) -> None:
    """Test that dff edit without --id does not save metadata."""
    patch_keyring(monkeypatch)

    saved_files: dict[str, Any] = {}

    def mock_save_json_file(data: Any, path: str) -> None:
        saved_files[path] = data

    def mock_launch_editor(*args: Any, **kwargs: Any) -> None:
        pass

    monkeypatch.setattr("slcli.dff_click.save_json_file", mock_save_json_file)
    monkeypatch.setattr("slcli.dff_click.launch_dff_editor", mock_launch_editor)

    cli = make_cli()
    result = runner.invoke(cli, ["customfields", "edit", "--no-browser"])

    assert result.exit_code == 0

    # Check that no metadata file was saved
    metadata_files = [path for path in saved_files.keys() if ".editor-metadata.json" in path]
    assert len(metadata_files) == 0


def test_dff_edit_with_id_generates_filename_from_config_name(
    monkeypatch: Any, runner: CliRunner
) -> None:
    """Test that dff edit --id generates safe filename from config name."""
    patch_keyring(monkeypatch)

    saved_files: dict[str, Any] = {}

    def mock_save_json_file(data: Any, path: str) -> None:
        saved_files[path] = data

    def mock_get(*a: Any, **kw: Any) -> Any:
        class R:
            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {
                    "configuration": {
                        "id": "cfg-xyz",
                        "name": "My Test / Configuration",
                        "workspace": "ws1",
                    },
                    "groups": [],
                    "fields": [],
                }

        return R()

    def mock_launch_editor(*args: Any, **kwargs: Any) -> None:
        pass

    monkeypatch.setattr("slcli.dff_click.make_api_request", lambda *a, **kw: mock_get())
    monkeypatch.setattr("slcli.dff_click.save_json_file", mock_save_json_file)
    monkeypatch.setattr("slcli.dff_click.launch_dff_editor", mock_launch_editor)

    cli = make_cli()
    result = runner.invoke(cli, ["customfields", "edit", "--id", "cfg-xyz", "--no-browser"])

    assert result.exit_code == 0

    # Check that config file was saved with sanitized filename
    config_files = [
        path for path in saved_files.keys() if ".json" in path and "metadata" not in path
    ]
    assert len(config_files) >= 1

    # Filename should not contain unsafe characters
    config_file = config_files[0]
    assert "/" not in Path(config_file).name
    assert "\\" not in Path(config_file).name


def test_dff_delete_with_recursive_flag(monkeypatch: Any, runner: CliRunner) -> None:
    """Test delete command with --no-recursive flag."""
    patch_keyring(monkeypatch)

    payload_data = {}

    def mock_make_api_request(
        method: str, url: str, data: Any = None, handle_errors: bool = True
    ) -> Any:
        nonlocal payload_data
        payload_data = data

        class MockResponse:
            status_code = 200

            def json(self) -> dict[str, Any]:
                return {"configurations": [{"id": "config1"}], "groups": [], "fields": []}

            def raise_for_status(self) -> None:
                pass

        return MockResponse()

    monkeypatch.setattr("slcli.dff_click.make_api_request", mock_make_api_request)

    cli = make_cli()
    result = runner.invoke(cli, ["customfields", "delete", "--id", "config1", "--no-recursive"], input="y\n")

    assert result.exit_code == 0
    assert payload_data["recursive"] is False
