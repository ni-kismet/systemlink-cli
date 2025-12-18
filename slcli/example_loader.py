"""Load and validate example configurations."""

import json
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml  # type: ignore


class ExampleLoader:
    """Load and validate example configurations from local examples/ directory."""

    # Supported schema versions
    SUPPORTED_SCHEMA_VERSIONS = {"1.0"}

    # Required fields in config
    REQUIRED_FIELDS = {"format_version", "name", "title", "resources"}

    # Required resource fields
    REQUIRED_RESOURCE_FIELDS = {"type", "name", "properties", "id_reference"}

    # Supported resource types
    SUPPORTED_RESOURCE_TYPES = {
        "location",
        "product",
        "system",
        "asset",
        "dut",
        "testtemplate",
    }

    def __init__(self, examples_dir: Optional[Path] = None) -> None:
        """Initialize loader with path to examples directory.

        Args:
            examples_dir: Path to examples directory. Defaults to slcli/examples/.
        """
        self.examples_dir = examples_dir or Path(__file__).parent / "examples"
        self._schema: Optional[Dict[str, Any]] = None

    def list_examples(self) -> List[Dict[str, Any]]:
        """List all available examples with metadata.

        Returns:
            List of dicts with keys: name, title, description, tags,
            estimated_setup_time_minutes, author.
        """
        examples = []
        for example_dir in sorted(self.examples_dir.iterdir()):
            # Skip special directories and non-directories
            if not example_dir.is_dir() or example_dir.name.startswith("_"):
                continue

            config_path = example_dir / "config.yaml"
            if not config_path.exists():
                continue

            try:
                config = self.load_config(example_dir.name)
                examples.append(
                    {
                        "name": config["name"],
                        "title": config["title"],
                        "description": config.get("description", ""),
                        "tags": config.get("tags", []),
                        "estimated_setup_time_minutes": config.get(
                            "estimated_setup_time_minutes", 0
                        ),
                        "author": config.get("author", "Unknown"),
                    }
                )
            except (FileNotFoundError, ValueError):
                # Skip invalid examples
                continue

        return examples

    def load_config(self, example_name: str) -> Dict[str, Any]:
        """Load and validate example configuration.

        Args:
            example_name: Name of example (directory name).

        Returns:
            Validated config dictionary.

        Raises:
            FileNotFoundError: If example config not found.
            ValueError: If config fails validation.
        """
        config_path = self.examples_dir / example_name / "config.yaml"
        if not config_path.exists():
            raise FileNotFoundError(
                f"Example '{example_name}' not found. " f"Config path: {config_path}"
            )

        # Load YAML
        try:
            with open(config_path, "r") as f:
                config = yaml.safe_load(f)
        except yaml.YAMLError as e:
            raise ValueError(f"Invalid YAML in {config_path}: {e}")

        if not isinstance(config, dict):
            raise ValueError(f"Config must be a dictionary, got {type(config)}")

        # Validate schema
        errors = self.validate_config(config)
        if errors:
            msg = f"Config validation failed for '{example_name}':\n"
            msg += "\n".join(f"  - {e}" for e in errors)
            raise ValueError(msg)

        # Validate references
        ref_errors = self._validate_references(config)
        if ref_errors:
            msg = f"Reference validation failed for '{example_name}':\n"
            msg += "\n".join(f"  - {e}" for e in ref_errors)
            raise ValueError(msg)

        return config

    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        """Validate config against basic schema requirements.

        Args:
            config: Config dictionary to validate.

        Returns:
            List of validation error messages (empty if valid).
        """
        errors = []

        # Check all required top-level fields are present
        if not isinstance(config, dict):
            return ["Config must be a dictionary"]

        missing_fields = self.REQUIRED_FIELDS - set(config.keys())
        if missing_fields:
            errors.append(f"Missing required fields: {', '.join(sorted(missing_fields))}")

        # Check format_version is supported
        version = config.get("format_version")
        if version and version not in self.SUPPORTED_SCHEMA_VERSIONS:
            errors.append(
                f"Unsupported format_version '{version}'. "
                f"Supported: {self.SUPPORTED_SCHEMA_VERSIONS}"
            )

        # Validate resources
        resources = config.get("resources", [])
        if not isinstance(resources, list):
            errors.append("resources must be a list")
            return errors

        for idx, resource in enumerate(resources):
            if not isinstance(resource, dict):
                errors.append(f"Resource {idx}: must be a dictionary")
                continue

            # Check required resource fields
            missing = self.REQUIRED_RESOURCE_FIELDS - set(resource.keys())
            if missing:
                errors.append(
                    f"Resource {idx}: missing fields: {', '.join(sorted(missing))}"
                )

            # Check resource type is supported
            res_type = resource.get("type")
            if res_type and res_type not in self.SUPPORTED_RESOURCE_TYPES:
                errors.append(
                    f"Resource {idx}: unsupported type '{res_type}'. "
                    f"Supported: {', '.join(sorted(self.SUPPORTED_RESOURCE_TYPES))}"
                )

            # Validate id_reference format (should be valid identifier)
            id_ref = resource.get("id_reference", "")
            if id_ref and not self._is_valid_identifier(id_ref):
                errors.append(
                    f"Resource {idx}: invalid id_reference '{id_ref}'. "
                    f"Must start with letter or underscore, contain only "
                    f"alphanumeric and underscores."
                )

        return errors

    def _is_valid_identifier(self, name: str) -> bool:
        """Check if name is a valid Python identifier."""
        if not name:
            return False
        if not (name[0].isalpha() or name[0] == "_"):
            return False
        return all(c.isalnum() or c == "_" for c in name)

    def _validate_references(self, config: Dict[str, Any]) -> List[str]:
        """Validate that all ${ref} references are defined.

        Args:
            config: Config dictionary.

        Returns:
            List of reference error messages.
        """
        errors = []

        # Collect all defined id_references
        defined_refs = set()
        resources = config.get("resources", [])
        if not isinstance(resources, list):
            return ["resources must be a list"]

        for resource in resources:
            if isinstance(resource, dict):
                ref = resource.get("id_reference")
                if ref:
                    defined_refs.add(ref)

        # Check all ${ref} references are defined
        for resource in resources:
            if not isinstance(resource, dict):
                continue

            # Check in resource properties
            props = resource.get("properties", {})
            if isinstance(props, dict):
                ref_errors = self._collect_undefined_refs(props, defined_refs)
                errors.extend(ref_errors)

        return errors

    def _collect_undefined_refs(self, obj: Any, defined_refs: set) -> List[str]:
        """Recursively collect undefined references from an object.

        Args:
            obj: Object to scan (dict, list, string, etc).
            defined_refs: Set of defined id_references.

        Returns:
            List of error messages for undefined references.
        """
        errors = []

        if isinstance(obj, dict):
            for value in obj.values():
                errors.extend(self._collect_undefined_refs(value, defined_refs))
        elif isinstance(obj, list):
            for item in obj:
                errors.extend(self._collect_undefined_refs(item, defined_refs))
        elif isinstance(obj, str):
            # Check for ${ref} pattern
            if obj.startswith("${") and obj.endswith("}"):
                ref = obj[2:-1]
                if ref not in defined_refs:
                    errors.append(
                        f"Undefined reference: {obj}. "
                        f"Defined references: {sorted(defined_refs)}"
                    )

        return errors

    def get_resource_order(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Get resources in provisioning order (as listed in config).

        Args:
            config: Config dictionary.

        Returns:
            List of resource definitions.
        """
        resources = config.get("resources", [])
        if not isinstance(resources, list):
            return []
        return [r for r in resources if isinstance(r, dict)]
