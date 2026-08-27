"""Unit tests for example CLI commands."""

import json
import tempfile
from pathlib import Path
from typing import Any, Dict, Generator, List, Optional, Tuple

import click
import pytest
from click.testing import CliRunner

from slcli.example_click import register_example_commands
from slcli.example_loader import ExampleLoader
from slcli.example_provisioner import ProvisioningAction, ProvisioningResult
from slcli.utils import ExitCodes


def make_cli() -> click.Group:
    """Create a dummy CLI for testing."""

    @click.group()
    def cli() -> None:
        pass

    register_example_commands(cli)
    return cli


@pytest.fixture
def runner() -> CliRunner:
    """Return a CLI runner."""
    return CliRunner()


@pytest.fixture
def temp_examples_dir() -> Generator[Path, None, None]:
    """Create a temporary examples directory for testing."""
    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        # Create the schema directory and a minimal schema
        schema_dir = tmppath / "_schema"
        schema_dir.mkdir()
        schema_path = schema_dir / "schema-v1.0.json"
        with open(schema_path, "w") as f:
            json.dump(
                {
                    "$schema": "http://json-schema.org/draft-07/schema#",
                    "type": "object",
                    "required": ["format_version", "name", "title", "resources"],
                    "properties": {
                        "format_version": {"type": "string"},
                        "name": {"type": "string"},
                        "title": {"type": "string"},
                        "resources": {"type": "array"},
                    },
                },
                f,
            )
        yield tmppath


def create_example_config(
    dir_path: Path,
    name: str,
    config: dict,
) -> None:
    """Create an example config file in a directory."""
    example_dir = dir_path / name
    example_dir.mkdir(exist_ok=True)
    config_path = example_dir / "config.yaml"

    import yaml  # type: ignore

    with open(config_path, "w") as f:
        yaml.dump(config, f)


def test_list_examples_empty(runner: CliRunner, monkeypatch: Any) -> None:
    """Test listing examples when none exist."""
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setattr(
            "slcli.example_click.ExampleLoader",
            lambda: ExampleLoader(Path(tmpdir)),
        )
        cli = make_cli()
        result = runner.invoke(cli, ["example", "list"])

        assert result.exit_code == 0


def test_list_examples_table_format(
    runner: CliRunner, temp_examples_dir: Path, monkeypatch: Any
) -> None:
    """Test listing examples in table format."""
    # Create a test example
    config = {
        "format_version": "1.0",
        "name": "demo-test",
        "title": "Demo Test Example",
        "author": "Test Author",
        "tags": ["training", "demo"],
        "estimated_setup_time_minutes": 5,
        "resources": [],
    }
    create_example_config(temp_examples_dir, "demo-test", config)

    # Mock the loader
    monkeypatch.setattr(
        "slcli.example_click.ExampleLoader",
        lambda: ExampleLoader(temp_examples_dir),
    )

    monkeypatch.setattr("slcli.example_click.get_workspace_map", lambda: {"ws-1": "Test Workspace"})

    cli = make_cli()
    result = runner.invoke(cli, ["example", "list", "--format", "table"])

    assert result.exit_code == 0
    assert "demo-test" in result.output


def test_list_examples_json_format(
    runner: CliRunner, temp_examples_dir: Path, monkeypatch: Any
) -> None:
    """Test listing examples in JSON format."""
    # Create a test example
    config = {
        "format_version": "1.0",
        "name": "demo-test",
        "title": "Demo Test Example",
        "author": "Test Author",
        "tags": ["training"],
        "estimated_setup_time_minutes": 5,
        "resources": [],
    }
    create_example_config(temp_examples_dir, "demo-test", config)

    # Mock the loader
    monkeypatch.setattr(
        "slcli.example_click.ExampleLoader",
        lambda: ExampleLoader(temp_examples_dir),
    )

    monkeypatch.setattr("slcli.example_click.get_workspace_map", lambda: {"ws-1": "Test Workspace"})

    cli = make_cli()
    result = runner.invoke(cli, ["example", "list", "--format", "json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert isinstance(data, list)
    assert len(data) == 1
    assert data[0]["name"] == "demo-test"


def test_list_examples_default_format(
    runner: CliRunner, temp_examples_dir: Path, monkeypatch: Any
) -> None:
    """Test that default format is table."""
    # Create a test example
    config = {
        "format_version": "1.0",
        "name": "test",
        "title": "Test",
        "resources": [],
    }
    create_example_config(temp_examples_dir, "test", config)

    # Mock the loader
    monkeypatch.setattr(
        "slcli.example_click.ExampleLoader",
        lambda: ExampleLoader(temp_examples_dir),
    )

    monkeypatch.setattr("slcli.example_click.get_workspace_map", lambda: {"ws-1": "Test Workspace"})

    cli = make_cli()
    result = runner.invoke(cli, ["example", "list"])

    assert result.exit_code == 0
    # Table format should not be JSON
    assert "{" not in result.output or "[" not in result.output


def test_info_example_table_format(
    runner: CliRunner, temp_examples_dir: Path, monkeypatch: Any
) -> None:
    """Test info command in table format."""
    config = {
        "format_version": "1.0",
        "name": "demo-test",
        "title": "Demo Test Example",
        "description": "Test description",
        "author": "Test Author",
        "tags": ["training"],
        "estimated_setup_time_minutes": 5,
        "resources": [
            {
                "type": "location",
                "name": "Location 1",
                "properties": {},
                "id_reference": "loc1",
            },
            {
                "type": "system",
                "name": "System 1",
                "properties": {},
                "id_reference": "sys1",
            },
        ],
    }
    create_example_config(temp_examples_dir, "demo-test", config)

    # Mock the loader
    monkeypatch.setattr(
        "slcli.example_click.ExampleLoader",
        lambda: ExampleLoader(temp_examples_dir),
    )

    monkeypatch.setattr("slcli.example_click.get_workspace_map", lambda: {"ws-1": "Test Workspace"})

    cli = make_cli()
    result = runner.invoke(cli, ["example", "info", "demo-test"])

    assert result.exit_code == 0
    assert "Demo Test Example" in result.output
    assert "Test Author" in result.output
    assert "Location 1" in result.output
    assert "System 1" in result.output


def test_info_example_json_format(
    runner: CliRunner, temp_examples_dir: Path, monkeypatch: Any
) -> None:
    """Test info command in JSON format."""
    config = {
        "format_version": "1.0",
        "name": "demo-test",
        "title": "Demo Test Example",
        "author": "Test Author",
        "resources": [],
    }
    create_example_config(temp_examples_dir, "demo-test", config)

    # Mock the loader
    monkeypatch.setattr(
        "slcli.example_click.ExampleLoader",
        lambda: ExampleLoader(temp_examples_dir),
    )

    monkeypatch.setattr("slcli.example_click.get_workspace_map", lambda: {"ws-1": "Test Workspace"})

    cli = make_cli()
    result = runner.invoke(cli, ["example", "info", "demo-test", "--format", "json"])

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data["name"] == "demo-test"
    assert data["title"] == "Demo Test Example"


def test_info_example_not_found(runner: CliRunner, monkeypatch: Any) -> None:
    """Test info command with non-existent example."""
    with tempfile.TemporaryDirectory() as tmpdir:
        monkeypatch.setattr(
            "slcli.example_click.ExampleLoader",
            lambda: ExampleLoader(Path(tmpdir)),
        )

        cli = make_cli()
        result = runner.invoke(cli, ["example", "info", "nonexistent"])

        assert result.exit_code == ExitCodes.NOT_FOUND


def test_info_example_invalid_config(
    runner: CliRunner, temp_examples_dir: Path, monkeypatch: Any
) -> None:
    """Test info command with invalid config."""
    # Create invalid config
    example_dir = temp_examples_dir / "invalid"
    example_dir.mkdir()
    config_path = example_dir / "config.yaml"
    with open(config_path, "w") as f:
        # Missing required fields
        import yaml  # type: ignore

        yaml.dump({"format_version": "1.0"}, f)

    # Mock the loader
    monkeypatch.setattr(
        "slcli.example_click.ExampleLoader",
        lambda: ExampleLoader(temp_examples_dir),
    )

    monkeypatch.setattr("slcli.example_click.get_workspace_map", lambda: {"ws-1": "Test Workspace"})

    cli = make_cli()
    result = runner.invoke(cli, ["example", "info", "invalid"])

    assert result.exit_code == ExitCodes.INVALID_INPUT


def test_list_help_text(runner: CliRunner) -> None:
    """Test list command help text."""
    cli = make_cli()
    result = runner.invoke(cli, ["example", "list", "--help"])

    assert result.exit_code == 0
    assert "list available example configurations" in result.output.lower()


def test_info_help_text(runner: CliRunner) -> None:
    """Test info command help text."""
    cli = make_cli()
    result = runner.invoke(cli, ["example", "info", "--help"])

    assert result.exit_code == 0
    assert "show detailed information" in result.output.lower()


def test_example_group_help(runner: CliRunner) -> None:
    """Test example group help text."""
    cli = make_cli()
    result = runner.invoke(cli, ["example", "--help"])

    assert result.exit_code == 0
    assert "example systemlink resource configurations" in result.output.lower()


def test_install_example_resolves_workspace_and_outputs_table(
    runner: CliRunner, temp_examples_dir: Path, monkeypatch: Any
) -> None:
    """Install command should resolve workspace names and render table output."""
    config = {
        "format_version": "1.0",
        "name": "demo-test",
        "title": "Demo Test Example",
        "resources": [
            {
                "type": "system",
                "name": "System 1",
                "id_reference": "sys1",
                "properties": {"name": "System 1"},
            }
        ],
    }
    create_example_config(temp_examples_dir, "demo-test", config)

    captured: Dict[str, Any] = {}

    class DummyProvisioner:
        def __init__(
            self, workspace_id: Optional[str], example_name: Optional[str], dry_run: bool
        ) -> None:
            captured["workspace_id"] = workspace_id
            captured["example_name"] = example_name
            captured["dry_run"] = dry_run

        def provision(self, _: Dict[str, Any]) -> Tuple[List[ProvisioningResult], None]:
            res = ProvisioningResult(
                id_reference="sys1",
                resource_type="system",
                resource_name="System 1",
                action=ProvisioningAction.CREATED,
                server_id="sys-123",
            )
            return [res], None

    monkeypatch.setattr(
        "slcli.example_click.ExampleLoader",
        lambda: ExampleLoader(temp_examples_dir),
    )
    monkeypatch.setattr("slcli.example_click.ExampleProvisioner", DummyProvisioner)
    monkeypatch.setattr("slcli.example_click.get_workspace_map", lambda: {"ws-1": "Training"})

    cli = make_cli()
    result = runner.invoke(cli, ["example", "install", "demo-test", "--workspace", "Training"])

    assert result.exit_code == 0
    assert "System 1" in result.output
    assert captured["workspace_id"] == "ws-1"
    assert captured["dry_run"] is False


def test_install_example_from_file_uses_config_directory_for_references(
    runner: CliRunner, temp_examples_dir: Path, monkeypatch: Any
) -> None:
    """Install accepts an external config and passes its directory to the provisioner."""
    import yaml  # type: ignore

    example_dir = temp_examples_dir / "example-resources"
    example_dir.mkdir()
    config_path = example_dir / "config.yaml"
    reference_path = example_dir / "product-xyz-specification.csv"
    config = {
        "format_version": "1.0",
        "name": "example-resources",
        "title": "Nigel Evaluation Fixture",
        "resources": [],
    }
    with open(config_path, "w") as f:
        yaml.dump(config, f)
    reference_path.write_text("name,value\nOutput Voltage,5\n")

    captured: Dict[str, Any] = {}

    class DummyProvisioner:
        def __init__(
            self,
            workspace_id: Optional[str],
            example_name: Optional[str],
            dry_run: bool,
            example_dir: Optional[Path] = None,
        ) -> None:
            captured["workspace_id"] = workspace_id
            captured["example_name"] = example_name
            captured["dry_run"] = dry_run
            captured["example_dir"] = example_dir

        def provision(self, _: Dict[str, Any]) -> Tuple[List[ProvisioningResult], None]:
            return [], None

    monkeypatch.setattr(
        "slcli.example_click.ExampleLoader", lambda: ExampleLoader(temp_examples_dir)
    )
    monkeypatch.setattr("slcli.example_click.ExampleProvisioner", DummyProvisioner)
    monkeypatch.setattr("slcli.example_click.get_workspace_map", lambda: {"ws-1": "Training"})

    cli = make_cli()
    result = runner.invoke(
        cli,
        ["example", "install", "--file", str(config_path), "--workspace", "Training"],
    )

    assert result.exit_code == 0
    assert captured["workspace_id"] == "ws-1"
    assert captured["example_name"] == "example-resources"
    assert captured["example_dir"] == example_dir.resolve()


def test_install_example_json_and_audit_log(
    runner: CliRunner, temp_examples_dir: Path, monkeypatch: Any
) -> None:
    """Install command should support JSON output and audit logging."""
    config = {
        "format_version": "1.0",
        "name": "demo-test",
        "title": "Demo Test Example",
        "resources": [
            {
                "type": "system",
                "name": "System 1",
                "id_reference": "sys1",
                "properties": {"name": "System 1"},
            }
        ],
    }
    create_example_config(temp_examples_dir, "demo-test", config)

    class DummyProvisioner:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def provision(self, _: Dict[str, Any]) -> Tuple[List[ProvisioningResult], None]:
            res = ProvisioningResult(
                id_reference="sys1",
                resource_type="system",
                resource_name="System 1",
                action=ProvisioningAction.SKIPPED,
                server_id=None,
                details={"rows_expected": 2, "rows_added": 1},
            )
            return [res], None

    audit_path = temp_examples_dir / "audit.json"

    monkeypatch.setattr(
        "slcli.example_click.ExampleLoader", lambda: ExampleLoader(temp_examples_dir)
    )
    monkeypatch.setattr("slcli.example_click.ExampleProvisioner", DummyProvisioner)
    monkeypatch.setattr("slcli.example_click.get_workspace_map", lambda: {"ws-1": "Training"})

    cli = make_cli()
    result = runner.invoke(
        cli,
        [
            "example",
            "install",
            "demo-test",
            "--workspace",
            "Training",
            "--format",
            "json",
            "--audit-log",
            str(audit_path),
            "--dry-run",
        ],
    )

    assert result.exit_code == 0
    data = json.loads(result.output)
    assert data[0]["action"] == "skipped"
    assert data[0]["details"] == {"rows_expected": 2, "rows_added": 1}
    assert audit_path.exists()
    with open(audit_path, "r") as f:
        saved = json.load(f)
    assert saved[0]["action"] == "skipped"


def test_install_fixture_manifest_reports_unsupported_capabilities(
    runner: CliRunner, temp_examples_dir: Path, monkeypatch: Any
) -> None:
    """Fixture installs must expose incomplete capabilities and fail explicitly."""
    config = {
        "format_version": "1.0",
        "name": "demo-data-3",
        "example_version": "1.0.0",
        "title": "Nigel Query Fixture",
        "install_manifest": True,
        "validation": {
            "required_relationships": ["result-to-instrument"],
            "unsupported": ["system.packageInventory"],
        },
        "resources": [
            {
                "type": "system",
                "name": "PXI-Rack-07",
                "id_reference": "system_pxi_rack_07",
                "properties": {"name": "PXI-Rack-07"},
            }
        ],
    }
    create_example_config(temp_examples_dir, "demo-data-3", config)
    audit_path = temp_examples_dir / "manifest.json"

    class DummyProvisioner:
        id_map = {"system_pxi_rack_07": "system-007"}

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def provision(self, _: Dict[str, Any]) -> Tuple[List[ProvisioningResult], None]:
            return [
                ProvisioningResult(
                    id_reference="system_pxi_rack_07",
                    resource_type="system",
                    resource_name="PXI-Rack-07",
                    action=ProvisioningAction.CREATED,
                    server_id="system-007",
                )
            ], None

    monkeypatch.setattr(
        "slcli.example_click.ExampleLoader", lambda: ExampleLoader(temp_examples_dir)
    )
    monkeypatch.setattr("slcli.example_click.ExampleProvisioner", DummyProvisioner)
    monkeypatch.setattr("slcli.example_click.get_workspace_map", lambda: {"ws-1": "Training"})

    cli = make_cli()
    result = runner.invoke(
        cli,
        [
            "example",
            "install",
            "demo-data-3",
            "--workspace",
            "Training",
            "--format",
            "json",
            "--audit-log",
            str(audit_path),
        ],
    )

    assert result.exit_code == ExitCodes.GENERAL_ERROR
    manifest = json.loads(result.stdout)
    assert manifest["example"] == "demo-data-3"
    assert manifest["logical_ids"]["system_pxi_rack_07"] == "system-007"
    assert manifest["resources"]["created"][0]["resource_name"] == "PXI-Rack-07"
    assert manifest["validation"]["complete"] is False
    assert manifest["validation"]["unsupported"] == ["system.packageInventory"]
    with open(audit_path, "r") as f:
        saved_manifest = json.load(f)
    assert saved_manifest["example"] == "demo-data-3"


def test_delete_example_outputs_deleted_results(
    runner: CliRunner, temp_examples_dir: Path, monkeypatch: Any
) -> None:
    """Delete command should surface deletion actions."""
    config = {
        "format_version": "1.0",
        "name": "demo-test",
        "title": "Demo Test Example",
        "resources": [
            {
                "type": "system",
                "name": "System 1",
                "id_reference": "sys1",
                "properties": {"name": "System 1"},
            }
        ],
    }
    create_example_config(temp_examples_dir, "demo-test", config)

    class DummyProvisioner:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            pass

        def delete(self, _: Dict[str, Any]) -> Tuple[List[ProvisioningResult], None]:
            res = ProvisioningResult(
                id_reference="sys1",
                resource_type="system",
                resource_name="System 1",
                action=ProvisioningAction.DELETED,
                server_id="sys-123",
            )
            return [res], None

    monkeypatch.setattr(
        "slcli.example_click.ExampleLoader", lambda: ExampleLoader(temp_examples_dir)
    )
    monkeypatch.setattr("slcli.example_click.ExampleProvisioner", DummyProvisioner)
    monkeypatch.setattr("slcli.example_click.get_workspace_map", lambda: {"ws-1": "Training"})

    cli = make_cli()
    result = runner.invoke(cli, ["example", "delete", "demo-test", "--workspace", "Training"])

    assert result.exit_code == 0
    assert "deleted" in result.output.lower()


def test_delete_example_from_file_uses_config_directory_for_references(
    runner: CliRunner, temp_examples_dir: Path, monkeypatch: Any
) -> None:
    """Delete accepts an external config and passes its directory to the provisioner."""
    import yaml  # type: ignore

    example_dir = temp_examples_dir / "example-resources"
    example_dir.mkdir()
    config_path = example_dir / "config.yaml"
    config = {
        "format_version": "1.0",
        "name": "example-resources",
        "title": "External Delete Fixture",
        "resources": [],
    }
    with open(config_path, "w") as f:
        yaml.dump(config, f)

    captured: Dict[str, Any] = {}

    class DummyProvisioner:
        def __init__(
            self,
            workspace_id: Optional[str],
            example_name: Optional[str],
            dry_run: bool,
            example_dir: Optional[Path] = None,
        ) -> None:
            captured["workspace_id"] = workspace_id
            captured["example_name"] = example_name
            captured["dry_run"] = dry_run
            captured["example_dir"] = example_dir

        def delete(self, _: Dict[str, Any]) -> Tuple[List[ProvisioningResult], None]:
            return [], None

    monkeypatch.setattr(
        "slcli.example_click.ExampleLoader", lambda: ExampleLoader(temp_examples_dir)
    )
    monkeypatch.setattr("slcli.example_click.ExampleProvisioner", DummyProvisioner)
    monkeypatch.setattr("slcli.example_click.get_workspace_map", lambda: {"ws-1": "Training"})

    cli = make_cli()
    result = runner.invoke(
        cli,
        ["example", "delete", "--file", str(config_path), "--workspace", "Training"],
    )

    assert result.exit_code == 0
    assert captured["workspace_id"] == "ws-1"
    assert captured["example_name"] == "example-resources"
    assert captured["example_dir"] == example_dir.resolve()


def test_delete_example_from_file_exits_nonzero_for_failed_resource(
    runner: CliRunner, temp_examples_dir: Path, monkeypatch: Any
) -> None:
    """External config deletion propagates resource failures to the exit code."""
    import yaml  # type: ignore

    config_path = temp_examples_dir / "external-config.yaml"
    config = {
        "format_version": "1.0",
        "name": "external-config",
        "title": "External Config",
        "resources": [
            {
                "type": "fixture",
                "name": "Fixture Slot",
                "id_reference": "fixture_slot",
                "properties": {},
            }
        ],
    }
    with open(config_path, "w") as config_stream:
        yaml.dump(config, config_stream)

    class FailingProvisioner:
        def __init__(self, **_: Any) -> None:
            pass

        def delete(self, _: Dict[str, Any]) -> Tuple[List[ProvisioningResult], Optional[Exception]]:
            return [
                ProvisioningResult(
                    id_reference="fixture_slot",
                    resource_type="fixture",
                    resource_name="Fixture Slot",
                    action=ProvisioningAction.FAILED,
                    error="partial API failure",
                )
            ], None

    monkeypatch.setattr(
        "slcli.example_click.ExampleLoader", lambda: ExampleLoader(temp_examples_dir)
    )
    monkeypatch.setattr("slcli.example_click.ExampleProvisioner", FailingProvisioner)
    monkeypatch.setattr("slcli.example_click.get_workspace_map", lambda: {"ws-1": "Training"})

    result = runner.invoke(
        make_cli(),
        ["example", "delete", "--file", str(config_path), "--workspace", "Training"],
    )

    assert result.exit_code == ExitCodes.GENERAL_ERROR
    assert "One or more resources failed to delete" in result.output


def test_install_example_workspace_not_found(
    runner: CliRunner, temp_examples_dir: Path, monkeypatch: Any
) -> None:
    """Install should exit with invalid input when workspace cannot be resolved."""
    config = {
        "format_version": "1.0",
        "name": "demo-test",
        "title": "Demo Test Example",
        "resources": [
            {
                "type": "system",
                "name": "System 1",
                "id_reference": "sys1",
                "properties": {"name": "System 1"},
            }
        ],
    }
    create_example_config(temp_examples_dir, "demo-test", config)

    # Provisioner should never be invoked when workspace resolution fails
    class DummyProvisioner:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            raise AssertionError("Provisioner should not be constructed")

    monkeypatch.setattr(
        "slcli.example_click.ExampleLoader", lambda: ExampleLoader(temp_examples_dir)
    )
    monkeypatch.setattr("slcli.example_click.ExampleProvisioner", DummyProvisioner)
    monkeypatch.setattr("slcli.example_click.get_workspace_map", lambda: {"ws-1": "Training"})

    cli = make_cli()
    result = runner.invoke(cli, ["example", "install", "demo-test", "--workspace", "Missing"])

    assert result.exit_code == ExitCodes.INVALID_INPUT
