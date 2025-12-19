"""Unit tests for example loader module."""

import json
import tempfile
from pathlib import Path
from typing import Generator

import pytest

from slcli.example_loader import ExampleLoader


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


def test_loader_initialization(temp_examples_dir: Path) -> None:
    """Test loader initializes with custom directory."""
    loader = ExampleLoader(temp_examples_dir)
    assert loader.examples_dir == temp_examples_dir


def test_load_valid_config(temp_examples_dir: Path) -> None:
    """Test loading a valid example config."""
    config = {
        "format_version": "1.0",
        "name": "test-example",
        "title": "Test Example",
        "description": "Test example description",
        "author": "Test Author",
        "tags": ["test"],
        "estimated_setup_time_minutes": 5,
        "resources": [
            {
                "type": "location",
                "name": "Test Location",
                "properties": {"city": "Austin"},
                "id_reference": "loc_test",
                "tags": ["test"],
            }
        ],
    }
    create_example_config(temp_examples_dir, "test-example", config)

    loader = ExampleLoader(temp_examples_dir)
    loaded = loader.load_config("test-example")

    assert loaded["name"] == "test-example"
    assert loaded["title"] == "Test Example"
    assert len(loaded["resources"]) == 1


def test_load_missing_config(temp_examples_dir: Path) -> None:
    """Test loading a non-existent example raises FileNotFoundError."""
    loader = ExampleLoader(temp_examples_dir)
    with pytest.raises(FileNotFoundError):
        loader.load_config("nonexistent")


def test_validate_config_required_fields(temp_examples_dir: Path) -> None:
    """Test schema validation catches missing required fields."""
    config = {
        "format_version": "1.0",
        # Missing: name, title, resources
    }
    loader = ExampleLoader(temp_examples_dir)
    errors = loader.validate_config(config)
    assert len(errors) > 0


def test_validate_config_invalid_format_version(temp_examples_dir: Path) -> None:
    """Test schema validation catches unsupported format version."""
    config = {
        "format_version": "2.0",  # Not supported
        "name": "test",
        "title": "Test",
        "resources": [],
    }
    loader = ExampleLoader(temp_examples_dir)
    errors = loader.validate_config(config)
    assert any("Unsupported format_version" in e for e in errors)


def test_validate_references_all_defined(temp_examples_dir: Path) -> None:
    """Test that all references are resolved correctly."""
    config = {
        "format_version": "1.0",
        "name": "test",
        "title": "Test",
        "resources": [
            {
                "type": "location",
                "name": "Location",
                "properties": {"city": "Austin"},
                "id_reference": "loc_test",
            },
            {
                "type": "system",
                "name": "System",
                "properties": {"location_id": "${loc_test}"},
                "id_reference": "sys_test",
            },
        ],
    }
    loader = ExampleLoader(temp_examples_dir)
    errors = loader._validate_references(config)
    assert len(errors) == 0


def test_validate_references_undefined(temp_examples_dir: Path) -> None:
    """Test that undefined references are caught."""
    config = {
        "format_version": "1.0",
        "name": "test",
        "title": "Test",
        "resources": [
            {
                "type": "system",
                "name": "System",
                "properties": {"location_id": "${loc_undefined}"},
                "id_reference": "sys_test",
            }
        ],
    }
    loader = ExampleLoader(temp_examples_dir)
    errors = loader._validate_references(config)
    assert len(errors) > 0
    assert any("Undefined reference" in e for e in errors)


def test_list_examples_empty(temp_examples_dir: Path) -> None:
    """Test listing examples when directory is empty."""
    loader = ExampleLoader(temp_examples_dir)
    examples = loader.list_examples()
    assert len(examples) == 0


def test_list_examples_multiple(temp_examples_dir: Path) -> None:
    """Test listing multiple examples."""
    # Create first example
    config1 = {
        "format_version": "1.0",
        "name": "example-1",
        "title": "Example 1",
        "author": "Author A",
        "tags": ["training"],
        "estimated_setup_time_minutes": 5,
        "resources": [],
    }
    create_example_config(temp_examples_dir, "example-1", config1)

    # Create second example
    config2 = {
        "format_version": "1.0",
        "name": "example-2",
        "title": "Example 2",
        "author": "Author B",
        "tags": ["demo"],
        "estimated_setup_time_minutes": 10,
        "resources": [],
    }
    create_example_config(temp_examples_dir, "example-2", config2)

    loader = ExampleLoader(temp_examples_dir)
    examples = loader.list_examples()

    assert len(examples) == 2
    assert examples[0]["name"] == "example-1"
    assert examples[1]["name"] == "example-2"


def test_list_examples_skips_invalid(temp_examples_dir: Path) -> None:
    """Test that list_examples skips invalid configs."""
    # Create valid example
    valid_config = {
        "format_version": "1.0",
        "name": "valid",
        "title": "Valid",
        "resources": [],
    }
    create_example_config(temp_examples_dir, "valid", valid_config)

    # Create invalid example (missing required fields)
    invalid_config = {
        "format_version": "1.0",
        # Missing required fields
    }
    create_example_config(temp_examples_dir, "invalid", invalid_config)

    loader = ExampleLoader(temp_examples_dir)
    examples = loader.list_examples()

    # Should only include the valid example
    assert len(examples) == 1
    assert examples[0]["name"] == "valid"


def test_get_resource_order(temp_examples_dir: Path) -> None:
    """Test that resources are returned in order."""
    config = {
        "format_version": "1.0",
        "name": "test",
        "title": "Test",
        "resources": [
            {
                "type": "location",
                "name": "Loc",
                "properties": {},
                "id_reference": "loc",
            },
            {
                "type": "system",
                "name": "Sys",
                "properties": {},
                "id_reference": "sys",
            },
        ],
    }
    loader = ExampleLoader(temp_examples_dir)
    resources = loader.get_resource_order(config)

    assert len(resources) == 2
    assert resources[0]["type"] == "location"
    assert resources[1]["type"] == "system"


def test_invalid_yaml_syntax(temp_examples_dir: Path) -> None:
    """Test that invalid YAML is caught."""
    example_dir = temp_examples_dir / "bad-yaml"
    example_dir.mkdir()
    config_path = example_dir / "config.yaml"

    # Write invalid YAML
    with open(config_path, "w") as f:
        f.write("invalid: yaml: syntax: here:\n  bad indentation")

    loader = ExampleLoader(temp_examples_dir)
    with pytest.raises(ValueError):
        loader.load_config("bad-yaml")
