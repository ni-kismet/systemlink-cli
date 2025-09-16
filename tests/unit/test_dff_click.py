"""Tests for DFF (Dynamic Form Fields) CLI commands."""

import json
import tempfile
from pathlib import Path

import click
import pytest
from click.testing import CliRunner
from typing import Any

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
    result = runner.invoke(cli, ["dff", "config", "list"])

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
    result = runner.invoke(cli, ["dff", "config", "list", "--format", "json"])

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
    result = runner.invoke(cli, ["dff", "config", "get", "--id", "config1"])

    assert result.exit_code == 0
    output_json = json.loads(result.output)
    assert output_json["configuration"]["name"] == "Test Configuration"


def test_dff_config_init_success(runner: CliRunner) -> None:
    """Test initializing a new DFF configuration template."""
    cli = make_cli()

    with tempfile.TemporaryDirectory() as temp_dir:
        output_file = Path(temp_dir) / "test-config.json"

        result = runner.invoke(
            cli,
            [
                "dff",
                "config",
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
        result = runner.invoke(cli, ["dff", "config", "create", "--file", input_file])
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
        result = runner.invoke(cli, ["dff", "config", "create", "--file", input_file])
        assert result.exit_code == 2  # ExitCodes.INVALID_INPUT
        assert "Validation errors occurred" in result.output
        assert "request: The request field is required" in result.output
        assert "$.fields[0].type: Unknown value INVALID_TYPE" in result.output
    finally:
        Path(input_file).unlink()


def test_dff_groups_list_success(monkeypatch: Any, runner: CliRunner) -> None:
    """Test listing DFF groups."""
    patch_keyring(monkeypatch)

    def mock_get(*a: Any, **kw: Any) -> Any:
        class R:
            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {"groups": [{"key": "group1", "name": "Test Group", "workspace": "ws1"}]}

        return R()

    monkeypatch.setattr(
        "slcli.dff_click.make_api_request", lambda method, url, *args, **kwargs: mock_get()
    )

    cli = make_cli()
    result = runner.invoke(cli, ["dff", "groups", "list"])

    assert result.exit_code == 0
    assert "Test Group" in result.output
    assert "group1" in result.output


def test_dff_fields_list_success(monkeypatch: Any, runner: CliRunner) -> None:
    """Test listing DFF fields."""
    patch_keyring(monkeypatch)

    def mock_get(*a: Any, **kw: Any) -> Any:
        class R:
            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {
                    "fields": [
                        {
                            "key": "field1",
                            "name": "Test Field",
                            "workspace": "ws1",
                            "fieldType": "STRING",
                        }
                    ]
                }

        return R()

    monkeypatch.setattr(
        "slcli.dff_click.make_api_request", lambda method, url, *args, **kwargs: mock_get()
    )

    cli = make_cli()
    result = runner.invoke(cli, ["dff", "fields", "list"])

    assert result.exit_code == 0
    assert "Test Field" in result.output
    assert "field1" in result.output


def test_dff_tables_query_success(monkeypatch: Any, runner: CliRunner) -> None:
    """Test querying table properties."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {
                    "tables": [
                        {
                            "id": "table1",
                            "workspace": "ws1",
                            "resourceType": "workorder:workorder",
                            "resourceId": "resource1",
                        }
                    ]
                }

        return R()

    monkeypatch.setattr(
        "slcli.dff_click.make_api_request", lambda method, url, data, *args, **kwargs: mock_post()
    )

    cli = make_cli()
    result = runner.invoke(
        cli,
        [
            "dff",
            "tables",
            "query",
            "--workspace",
            "ws1",
            "--resource-type",
            "workorder:workorder",
            "--resource-id",
            "resource1",
        ],
    )

    assert result.exit_code == 0
    assert "table1" in result.output
    assert "workorder:workorder" in result.output


def test_dff_tables_query_with_optional_params(monkeypatch: Any, runner: CliRunner) -> None:
    """Test querying table properties with optional parameters."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        class R:
            def raise_for_status(self) -> None:
                pass

            def json(self) -> Any:
                return {
                    "tables": [
                        {
                            "id": "table1",
                            "workspace": "ws1",
                            "resourceType": "workorder:workorder",
                            "resourceId": "resource1",
                        }
                    ],
                    "totalCount": 5,
                }

        return R()

    monkeypatch.setattr(
        "slcli.dff_click.make_api_request", lambda method, url, data, *args, **kwargs: mock_post()
    )

    cli = make_cli()
    result = runner.invoke(
        cli,
        [
            "dff",
            "tables",
            "query",
            "--workspace",
            "ws1",
            "--resource-type",
            "workorder:workorder",
            "--resource-id",
            "resource1",
            "--keys",
            "key1",
            "--keys",
            "key2",
            "--take",
            "50",
            "--return-count",
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0
    assert "table1" in result.output
    assert "workorder:workorder" in result.output


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
            cli, ["dff", "config", "export", "--id", "config1", "--output", str(output_file)]
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
    result = runner.invoke(cli, ["dff", "config", "delete", "--id", "config1"], input="n\n")

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
    result = runner.invoke(cli, ["dff", "config", "list", "--workspace", "Workspace1"])
    assert result.exit_code == 0
    assert "Config 1" in result.output
    assert "Config 2" not in result.output


def test_dff_help_commands(runner: CliRunner) -> None:
    """Test that help is available for all DFF commands."""
    cli = make_cli()

    # Test main dff help
    result = runner.invoke(cli, ["dff", "--help"])
    assert result.exit_code == 0
    assert "Manage dynamic form fields" in result.output

    # Test config help
    result = runner.invoke(cli, ["dff", "config", "--help"])
    assert result.exit_code == 0
    assert "Manage dynamic form field configurations" in result.output

    # Test groups help
    result = runner.invoke(cli, ["dff", "groups", "--help"])
    assert result.exit_code == 0
    assert "Manage dynamic form field groups" in result.output

    # Test fields help
    result = runner.invoke(cli, ["dff", "fields", "--help"])
    assert result.exit_code == 0
    assert "Manage dynamic form field definitions" in result.output

    # Test tables help
    result = runner.invoke(cli, ["dff", "tables", "--help"])
    assert result.exit_code == 0
    assert "Manage table properties" in result.output


def test_dff_edit_command_help(runner: CliRunner) -> None:
    """Test that the edit command shows proper help."""
    cli = make_cli()

    result = runner.invoke(cli, ["dff", "edit", "--help"])
    assert result.exit_code == 0
    assert "Launch a local web editor" in result.output
    assert "--port" in result.output
    assert "--output-dir" in result.output
