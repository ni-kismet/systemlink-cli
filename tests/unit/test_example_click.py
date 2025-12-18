"""Unit tests for example CLI commands."""

import json
import tempfile
from pathlib import Path
from typing import Any, Generator

import click
import pytest
from click.testing import CliRunner

from slcli.example_click import register_example_commands
from slcli.example_loader import ExampleLoader
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
    assert "example resource configurations" in result.output.lower()
