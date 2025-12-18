# Example Configuration System - Implementation Plan

**Date:** December 17, 2025  
**Scope:** Local example configs in slcli repository  
**Platform:** SystemLink Enterprise (SLE) only  
**Status:** Planning phase

---

## 1. Executive Summary

Implement a local example configuration system that allows users to provision predefined example resources (systems, assets, DUTs, locations, products, templates) into their SLE instance via CLI commands. Configs are stored in the repo (not fetched remotely), versioned independently from CLI, and support dry-run and cleanup.

**Key goals:**

- Simple to use: `slcli example install demo-test-plans`
- Easy to extend: Add new examples by dropping a YAML file
- Safe: Validate before provisioning; support cleanup
- Maintainable: Schema versioning; minimal CLI logic

---

## 2. Directory Structure

```
slcli/
├── example_click.py              # CLI command registration
├── example_loader.py              # Load & validate configs
├── example_provisioner.py         # Provision SLE resources
└── examples/                       # Local configs
    ├── _schema/
    │   ├── schema-v1.0.json       # JSON schema for validation
    │   └── README.md
    ├── _shared/
    │   └── common-systems.yaml    # Reusable component snippets
    ├── demo-test-plans/
    │   ├── config.yaml            # Main config
    │   ├── README.md              # Example-specific docs
    │   └── screenshots/           # Optional visual guides
    ├── supply-chain/
    │   ├── config.yaml
    │   └── README.md
    └── index.yaml                 # Catalog of all examples

tests/
├── unit/
│   ├── test_example_loader.py
│   ├── test_example_provisioner.py
│   └── test_example_click.py
└── e2e/
    └── test_example_e2e.py

docs/
└── EXAMPLES_CONTRIBUTING.md       # How to add new examples
```

---

## 3. Schema Design (Version 1.0)

### 3.1 Top-Level Structure

```yaml
# examples/demo-test-plans/config.yaml
---
# SLE Example Configuration
format_version: "1.0"
name: "demo-test-plans"
title: "Demo Test Plans"
description: |
  A complete example demonstrating the end-to-end test planning workflow.
  Includes systems, assets, DUTs, locations, products, and test templates.

# Metadata
author: "NI"
created_date: "2025-12-17"
updated_date: "2025-12-17"
tags:
  - "training"
  - "beginner"
  - "test-plans"

# Setup guidance
estimated_setup_time_minutes: 5
required_systemlink_version: "2024.1" # Minimum SLE version

# Optional: workspace targeting (if different from CLI default)
target_workspace: null # null = use CLI default

# Resource definitions in dependency order
resources:
  # Phase 1: Locations (no dependencies)
  - type: "location"
    name: "Demo HQ"
    properties:
      address: "123 Main St"
      city: "Austin"
      state: "TX"
      country: "USA"
    id_reference: "loc_hq"
    tags: ["demo"]

  # Phase 2: Products (no dependencies)
  - type: "product"
    name: "Demo Widget Pro"
    properties:
      description: "Professional widget for demonstration"
      category: "Industrial Equipment"
      manufacturer: "Demo Inc."
    id_reference: "prod_widget"
    tags: ["demo"]

  # Phase 3: Systems (depends on location, product)
  - type: "system"
    name: "Test Stand 1"
    properties:
      description: "First test system for demo workflow"
      location_id: "${loc_hq}"
      product_id: "${prod_widget}"
      serial_number: "TS-001"
      status: "operational"
    id_reference: "sys_ts1"
    tags: ["demo"]

  - type: "system"
    name: "Test Stand 2"
    properties:
      description: "Second test system for demo workflow"
      location_id: "${loc_hq}"
      product_id: "${prod_widget}"
      serial_number: "TS-002"
      status: "operational"
    id_reference: "sys_ts2"
    tags: ["demo"]

  # Phase 4: Assets (depends on system)
  - type: "asset"
    name: "Asset 1 - Stand 1"
    properties:
      system_id: "${sys_ts1}"
      serial_number: "ASSET-001"
      status: "active"
      properties:
        asset_type: "measurement_unit"
    id_reference: "asset_1"
    tags: ["demo"]

  - type: "asset"
    name: "Asset 2 - Stand 2"
    properties:
      system_id: "${sys_ts2}"
      serial_number: "ASSET-002"
      status: "active"
      properties:
        asset_type: "measurement_unit"
    id_reference: "asset_2"
    tags: ["demo"]

  # Phase 5: DUTs (depends on asset)
  - type: "dut"
    name: "DUT 1 - Stand 1"
    properties:
      asset_id: "${asset_1}"
      model: "Demo Model X1"
      serial_number: "DUT-001"
      status: "ready"
    id_reference: "dut_1"
    tags: ["demo"]

  - type: "dut"
    name: "DUT 2 - Stand 2"
    properties:
      asset_id: "${asset_2}"
      model: "Demo Model X2"
      serial_number: "DUT-002"
      status: "ready"
    id_reference: "dut_2"
    tags: ["demo"]

  # Phase 6: Templates (no direct dependencies; can reference systems/products)
  - type: "testtemplate"
    name: "Demo Test Template"
    properties:
      description: "Basic test template for demo workflow"
      version: "1.0"
      systems: ["${sys_ts1}", "${sys_ts2}"]
      products: ["${prod_widget}"]
      test_stages:
        - name: "Setup"
          description: "Prepare DUTs"
        - name: "Test"
          description: "Run tests"
        - name: "Cleanup"
          description: "Cleanup"
    id_reference: "template_demo"
    tags: ["demo"]

# Cleanup strategy
cleanup:
  # Order in which to delete resources (reverse dependency order)
  order:
    - "testtemplate"
    - "dut"
    - "asset"
    - "system"
    - "product"
    - "location"

  # Only delete resources with these tags (for safety)
  filter_tags: ["demo"]

  # If true, require --force to cleanup
  require_confirmation: true

# Validation rules
validation:
  # Warn if any of these systems don't exist (advisory only)
  require_existing_systems: []

  # Workspace must exist
  require_workspace: true

# Optional post-install instructions
post_install:
  instructions: |
    ✓ Example installed successfully!

    Next steps:
    1. Open SystemLink web interface
    2. Navigate to Assets & Test Planning
    3. Create a test by selecting:
       - System: "Test Stand 1" or "Test Stand 2"
       - Product: "Demo Widget Pro"
       - Template: "Demo Test Template"
    4. Run a test to verify setup

    Learn more: https://docs.systemlink.local/examples
```

### 3.2 SLE Resource Types Supported (Phase 1)

| Type           | SLE API Endpoint                 | Create Method | Delete Method | Notes                |
| -------------- | -------------------------------- | ------------- | ------------- | -------------------- |
| `location`     | `/niuser/v1/locations`           | POST          | DELETE        | Create location      |
| `product`      | `/niworkorder/v1/products`       | POST          | DELETE        | Create product       |
| `system`       | `/niworkorder/v1/systems`        | POST          | DELETE        | Create system        |
| `asset`        | `/niworkorder/v1/assets`         | POST          | DELETE        | Create asset         |
| `dut`          | `/niworkorder/v1/duts`           | POST          | DELETE        | Create DUT           |
| `testtemplate` | `/niworkorder/v1/test-templates` | POST          | DELETE        | Create test template |

---

## 4. Implementation Phases

### Phase 1: Core Infrastructure (Week 1)

**Goal:** Load, validate, and display example configs

**Deliverables:**

1. `example_loader.py` - Load YAML, validate schema
2. `example_click.py` - CLI commands: `list`, `info`
3. `examples/demo-test-plans/config.yaml` - First example
4. Unit tests for loader & validator
5. Update `slcli/main.py` to register commands

**Acceptance Criteria:**

- `slcli example list` displays available examples
- `slcli example info demo-test-plans` shows details
- Schema validation catches errors
- All unit tests pass

---

### Phase 2: Provisioning (Week 2)

**Goal:** Implement safe resource creation with dry-run support

**Deliverables:**

1. `example_provisioner.py` - Provision resources to SLE
2. `slcli example install` command with `--dry-run` and `--force`
3. Provisioning for all Phase 1 resource types
4. Error handling with rollback
5. ID reference tracking
6. Integration tests for provisioning flow

**Acceptance Criteria:**

- `slcli example install demo-test-plans --dry-run` validates without creating
- `slcli example install demo-test-plans` provisions all resources
- Resources created match config; IDs tracked correctly
- Error in resource N doesn't crash; partial rollback support
- E2E test confirms resources exist in SLE after install

---

### Phase 3: Cleanup & Safety (Week 3)

**Goal:** Implement safe deletion and add safeguards

**Deliverables:**

1. `slcli example delete` command
2. Cleanup in reverse dependency order
3. Tag-based filtering (only delete demo-tagged resources)
4. Audit logging (what was created/deleted)
5. Unit & E2E tests for cleanup
6. Documentation: contributing new examples

**Acceptance Criteria:**

- `slcli example delete demo-test-plans --dry-run` shows what would be deleted
- `slcli example delete demo-test-plans --force` deletes all demo resources
- Deletion respects tag filter
- Audit log records all actions
- No orphaned resources left behind

---

### Phase 4: Polish & Docs (Week 4)

**Goal:** Production-ready with examples and docs

**Deliverables:**

1. Second example config (`supply-chain-tracking`)
2. Example-specific README files
3. Contributing guide: `EXAMPLES_CONTRIBUTING.md`
4. JSON schema file for IDE validation
5. CLI help text improvements
6. Integration tests for multi-example scenarios
7. Release notes update

**Acceptance Criteria:**

- 2 working examples in repo
- Developer can add new example by following guide
- JSON schema validates all configs
- All tests pass; lint clean
- Documentation complete & clear

---

## 5. Detailed Module Specifications

### 5.1 `example_loader.py`

```python
"""Load and validate example configurations."""

from pathlib import Path
from typing import Any, Dict, List, Optional
import yaml
import json

class ExampleLoader:
    """Load example configs from local examples/ directory."""

    def __init__(self, examples_dir: Optional[Path] = None):
        """Initialize loader with path to examples directory."""
        self.examples_dir = examples_dir or Path(__file__).parent / "examples"
        self.schema = self._load_schema()

    def list_examples(self) -> List[Dict[str, Any]]:
        """
        Return list of available examples with metadata.

        Returns:
            List of dicts with keys: name, title, description, tags,
            estimated_setup_time_minutes
        """

    def load_config(self, example_name: str) -> Dict[str, Any]:
        """
        Load and validate example config.

        Raises:
            FileNotFoundError: If example config not found
            ValueError: If config fails schema validation
        """

    def validate_config(self, config: Dict[str, Any]) -> List[str]:
        """
        Validate config against schema.

        Returns:
            List of validation errors (empty if valid)
        """

    def resolve_references(self, config: Dict[str, Any]) -> Dict[str, Any]:
        """
        Pre-validate all ${ref} references exist.

        Raises:
            ValueError: If any reference is undefined
        """

    def get_resource_order(self, config: Dict[str, Any]) -> List[Dict]:
        """
        Return resources in correct provisioning order.

        Order determined by:
        1. Explicit dependency graph in schema (future)
        2. For now: resources listed in config order
        """

class ExampleIndexer:
    """Build and cache example index."""

    def __init__(self, examples_dir: Path):
        """Initialize indexer."""

    def build_index(self) -> Dict[str, Any]:
        """
        Scan examples/ directory and build index.yaml.

        Returns:
            Index dict with all examples metadata
        """

    def validate_index(self) -> List[str]:
        """
        Validate all examples in index.

        Returns:
            List of validation errors
        """
```

**Test locations:**

- `tests/unit/test_example_loader.py` - Schema validation, reference resolution
- `tests/unit/test_example_indexer.py` - Index building

---

### 5.2 `example_provisioner.py`

```python
"""Provision SLE resources from example configs."""

from typing import Any, Dict, List, Optional, Tuple
from enum import Enum
from dataclasses import dataclass

class ProvisioningAction(Enum):
    """Type of action taken."""
    CREATED = "created"
    SKIPPED = "skipped"
    FAILED = "failed"

@dataclass
class ProvisioningResult:
    """Result of provisioning a single resource."""
    id_reference: str
    resource_type: str
    resource_name: str
    action: ProvisioningAction
    server_id: Optional[str] = None
    error: Optional[str] = None

class ExampleProvisioner:
    """Provision resources to SLE."""

    def __init__(self, workspace_id: str, dry_run: bool = False):
        """
        Initialize provisioner.

        Args:
            workspace_id: Target workspace ID
            dry_run: If True, validate without creating
        """

    def provision(
        self, config: Dict[str, Any]
    ) -> Tuple[List[ProvisioningResult], Optional[Exception]]:
        """
        Provision all resources from config.

        Returns:
            (results list, error if provisioning failed at any point)

            If error is not None, some resources may have been created
            before the error occurred.
        """

    def _provision_resource(
        self, resource_def: Dict[str, Any], id_map: Dict[str, str]
    ) -> ProvisioningResult:
        """
        Provision a single resource and track the ID.

        Args:
            resource_def: Resource definition from config
            id_map: Current mapping of id_references to server IDs

        Returns:
            ProvisioningResult with outcome
        """

    def _create_location(self, props: Dict[str, Any]) -> str:
        """Create location via /niuser/v1/locations POST."""

    def _create_product(self, props: Dict[str, Any]) -> str:
        """Create product via /niworkorder/v1/products POST."""

    def _create_system(self, props: Dict[str, Any]) -> str:
        """Create system via /niworkorder/v1/systems POST."""

    def _create_asset(self, props: Dict[str, Any]) -> str:
        """Create asset via /niworkorder/v1/assets POST."""

    def _create_dut(self, props: Dict[str, Any]) -> str:
        """Create DUT via /niworkorder/v1/duts POST."""

    def _create_testtemplate(self, props: Dict[str, Any]) -> str:
        """Create test template via /niworkorder/v1/test-templates POST."""

    def cleanup(
        self, config: Dict[str, Any], created_ids: Dict[str, str]
    ) -> List[ProvisioningResult]:
        """
        Delete resources in reverse order.

        Only deletes resources with tags matching cleanup.filter_tags.

        Args:
            config: Example config
            created_ids: Mapping of id_references to server IDs

        Returns:
            List of deletion results
        """

class AuditLogger:
    """Log provisioning actions for audit trail."""

    def __init__(self, example_name: str, workspace_id: str):
        """Initialize audit logger."""

    def log_install(self, results: List[ProvisioningResult]) -> None:
        """Log install action."""

    def log_delete(self, results: List[ProvisioningResult]) -> None:
        """Log delete action."""

    def get_log_path(self) -> Path:
        """Return path to audit log file."""
```

**Error handling strategy:**

```python
class ProvisioningError(Exception):
    """Provisioning failed."""
    def __init__(self, message: str, results: List[ProvisioningResult]):
        self.results = results  # What was created before error
        super().__init__(message)

# On error during install:
# 1. Log what was created
# 2. Offer rollback: "Do you want to delete the 5 resources created before error?"
# 3. If yes, call cleanup() with the created IDs
```

**Test locations:**

- `tests/unit/test_example_provisioner.py` - Mock API calls
- `tests/e2e/test_example_e2e.py` - Real SLE instance

---

### 5.3 `example_click.py`

```python
"""CLI commands for example configurations."""

import click
from typing import Any, Optional
from .example_loader import ExampleLoader
from .example_provisioner import ExampleProvisioner

def register_example_commands(cli: Any) -> None:
    """Register example command group."""

    @cli.group()
    def example() -> None:
        """Manage example resource configurations.

        Examples help you quickly set up demo systems for training,
        testing, or evaluation. Each example includes systems, assets,
        DUTs, templates, and other resources needed for a complete workflow.

        Workspace: Uses default workspace unless --workspace specified.
        """
        pass

    @example.command(name="list")
    @click.option("--format", "-f", type=click.Choice(["table", "json"]),
                  default="table", help="Output format")
    def list_examples(format: str) -> None:
        """List available example configurations.

        Shows all examples with descriptions, tags, and estimated setup time.
        """

    @example.command(name="info")
    @click.argument("example_name")
    @click.option("--format", "-f", type=click.Choice(["table", "json"]),
                  default="table", help="Output format")
    def info_example(example_name: str, format: str) -> None:
        """Show detailed information about an example.

        Displays full config including resources, dependencies, and
        estimated setup time.

        Example:
            slcli example info demo-test-plans
        """

    @example.command(name="install")
    @click.argument("example_name")
    @click.option("--workspace", "-w", default=None,
                  help="Target workspace (default: Default workspace)")
    @click.option("--dry-run", is_flag=True,
                  help="Validate config without provisioning")
    @click.option("--force", is_flag=True,
                  help="Skip confirmation prompt")
    def install_example(
        example_name: str,
        workspace: Optional[str],
        dry_run: bool,
        force: bool
    ) -> None:
        """Install an example configuration.

        Creates all resources defined in the example (systems, assets, DUTs,
        test templates, etc.) in the specified workspace.

        Use --dry-run to validate without creating resources.
        Use --force to skip the confirmation prompt.

        Example:
            slcli example install demo-test-plans
            slcli example install demo-test-plans --dry-run
            slcli example install demo-test-plans --workspace Production --force
        """

    @example.command(name="delete")
    @click.argument("example_name")
    @click.option("--workspace", "-w", default=None,
                  help="Target workspace (default: Default workspace)")
    @click.option("--dry-run", is_flag=True,
                  help="Show what would be deleted without deleting")
    @click.option("--force", is_flag=True,
                  help="Skip confirmation prompt")
    def delete_example(
        example_name: str,
        workspace: Optional[str],
        dry_run: bool,
        force: bool
    ) -> None:
        """Delete resources created by an example.

        Deletes all resources tagged with the example name in reverse
        dependency order.

        Only deletes resources with tags matching the example.

        Use --dry-run to preview what would be deleted.
        Use --force to skip the confirmation prompt.

        Example:
            slcli example delete demo-test-plans
            slcli example delete demo-test-plans --dry-run
            slcli example delete demo-test-plans --force
        """
```

---

## 6. Example Configs (Starter Set)

### 6.1 `examples/demo-test-plans/config.yaml`

See Section 3.1 above for full detailed example.

### 6.2 `examples/supply-chain/config.yaml`

```yaml
format_version: "1.0"
name: "supply-chain-tracking"
title: "Supply Chain Tracking"
description: |
  Demonstrates asset tracking across a supply chain with
  multiple locations, suppliers, and test points.

author: "NI"
tags: ["training", "supply-chain", "assets"]
estimated_setup_time_minutes: 8

resources:
  - type: "location"
    name: "Supplier A - Chicago"
    properties:
      city: "Chicago"
      state: "IL"
      country: "USA"
    id_reference: "loc_supplier_a"
    tags: ["supply-chain"]

  - type: "location"
    name: "Distribution Center - Memphis"
    properties:
      city: "Memphis"
      state: "TN"
      country: "USA"
    id_reference: "loc_dc"
    tags: ["supply-chain"]

  # ... systems, assets, etc.

cleanup:
  order: ["dut", "asset", "system", "product", "location"]
  filter_tags: ["supply-chain"]
  require_confirmation: true
```

---

## 7. Testing Strategy

### 7.1 Unit Tests

**`tests/unit/test_example_loader.py`:**

- Load valid config ✓
- Load missing config (FileNotFoundError) ✓
- Invalid YAML syntax ✓
- Schema validation errors ✓
- Reference resolution: existing refs ✓
- Reference resolution: missing refs (error) ✓
- List examples ✓

**`tests/unit/test_example_provisioner.py`:**

- Dry-run mode doesn't call API ✓
- Resolve references correctly ✓
- Create location (mocked API) ✓
- Create product, system, asset, DUT, template (mocked) ✓
- Handle API errors with partial rollback ✓
- Cleanup in reverse order ✓
- Cleanup respects tag filter ✓
- Audit log generation ✓

**`tests/unit/test_example_click.py`:**

- `list` command outputs table ✓
- `list` command outputs JSON ✓
- `info` command shows details ✓
- `install --dry-run` validates without creating ✓
- `install` prompts for confirmation ✓
- `install --force` skips confirmation ✓
- `delete --dry-run` shows deletion plan ✓
- Help text accessible ✓

### 7.2 E2E Tests

**`tests/e2e/test_example_e2e.py`:**

- Install demo-test-plans to SLE ✓
- Verify all resources created (query SLE) ✓
- Delete demo-test-plans cleanup ✓
- Verify cleanup (no demo-tagged resources remain) ✓
- Install, then install again (idempotent or error?) ✓
- Missing workspace error ✓

---

## 8. Schema Validation (JSON Schema)

**`examples/_schema/schema-v1.0.json`:**

```json
{
  "$schema": "http://json-schema.org/draft-07/schema#",
  "title": "SLE Example Configuration Schema v1.0",
  "type": "object",
  "required": ["format_version", "name", "title", "resources"],
  "properties": {
    "format_version": {
      "type": "string",
      "enum": ["1.0"]
    },
    "name": {
      "type": "string",
      "pattern": "^[a-z0-9-]+$",
      "description": "Unique slug identifier"
    },
    "title": {
      "type": "string"
    },
    "description": {
      "type": "string"
    },
    "resources": {
      "type": "array",
      "items": {
        "type": "object",
        "required": ["type", "name", "properties", "id_reference"],
        "properties": {
          "type": {
            "enum": [
              "location",
              "product",
              "system",
              "asset",
              "dut",
              "testtemplate"
            ]
          },
          "name": {
            "type": "string"
          },
          "properties": {
            "type": "object"
          },
          "id_reference": {
            "type": "string",
            "pattern": "^[a-z_][a-z0-9_]*$"
          },
          "tags": {
            "type": "array",
            "items": { "type": "string" }
          }
        }
      }
    },
    "cleanup": {
      "type": "object",
      "properties": {
        "order": {
          "type": "array",
          "items": { "type": "string" }
        },
        "filter_tags": {
          "type": "array",
          "items": { "type": "string" }
        }
      }
    }
  }
}
```

---

## 9. Integration Points with Existing Code

| Module                        | Integration                                  | Notes                                       |
| ----------------------------- | -------------------------------------------- | ------------------------------------------- |
| `slcli/main.py`               | Register `example` command group             | One-liner: `register_example_commands(cli)` |
| `slcli/utils.py`              | Use `handle_api_error()`, `format_success()` | Existing error handling                     |
| `slcli/workspace_utils.py`    | Resolve workspace ID from name               | `resolve_workspace_filter()`                |
| `slcli/universal_handlers.py` | Format list/info output                      | Use for table/JSON rendering                |
| `slcli/cli_utils.py`          | Validation helpers                           | Workspace validation                        |

---

## 10. Execution Roadmap

### Week 1: Core Infrastructure

- [ ] Create directory structure: `examples/`, `examples/_schema/`
- [ ] Implement `example_loader.py` with schema validation
- [ ] Implement first example config: `demo-test-plans/config.yaml`
- [ ] Add `example list` and `example info` CLI commands
- [ ] Unit tests for loader & CLI commands
- [ ] Lint, type-check, docs
- [ ] **Milestone:** `slcli example list` and `slcli example info` working

### Week 2: Provisioning

- [ ] Implement `example_provisioner.py` with all resource type handlers
- [ ] Implement `slcli example install` with dry-run support
- [ ] Add API integration for location, product, system, asset, DUT, template
- [ ] Error handling & partial rollback
- [ ] Audit logging
- [ ] Unit tests for provisioning
- [ ] E2E test with real SLE instance
- [ ] **Milestone:** `slcli example install demo-test-plans` creates resources

### Week 3: Cleanup & Second Example

- [ ] Implement `slcli example delete` with cleanup order
- [ ] Tag-based resource filtering
- [ ] Unit & E2E tests for deletion
- [ ] Create second example: `supply-chain-tracking`
- [ ] **Milestone:** Multi-example support, safe cleanup

### Week 4: Polish

- [ ] Contributing guide: `EXAMPLES_CONTRIBUTING.md`
- [ ] README files for each example
- [ ] JSON schema for IDE validation
- [ ] Final integration tests
- [ ] Lint, type-check, docs complete
- [ ] Release notes update
- [ ] **Milestone:** Production-ready with docs

---

## 11. Success Criteria (Definition of Done)

### Code Quality

- [ ] All new code passes lint: `ni-python-styleguide lint`
- [ ] All new code type-checks: `mypy slcli tests`
- [ ] Unit test coverage > 80% for new modules
- [ ] E2E test coverage: all main workflows

### Functionality

- [ ] `slcli example list` works
- [ ] `slcli example info <name>` works
- [ ] `slcli example install <name>` creates resources
- [ ] `slcli example install <name> --dry-run` validates
- [ ] `slcli example delete <name>` removes resources
- [ ] `slcli example delete <name> --dry-run` shows plan
- [ ] Cleanup respects tags (only deletes demo resources)
- [ ] Audit logs recorded

### User Experience

- [ ] Help text clear and examples provided
- [ ] Confirmation prompts before destructive operations
- [ ] Error messages actionable
- [ ] Progress feedback during long operations

### Documentation

- [ ] README updated with example commands
- [ ] `EXAMPLES_CONTRIBUTING.md` complete
- [ ] Example-specific README files (setup steps, expected resources, next steps)
- [ ] JSON schema validates all configs

### Maintainability

- [ ] New examples can be added by dropping a YAML file
- [ ] Schema version independent of CLI version
- [ ] No hardcoded resource lists or APIs
- [ ] Code is well-commented and modular

---

## 12. Known Unknowns & Future Enhancements

### Phase 2+ (Future)

- [ ] Example versioning (multiple versions of same example)
- [ ] Example dependencies (install example A as prerequisite for example B)
- [ ] Data import (import CSV data for assets, etc.)
- [ ] IDE integration (JSON schema for VSCode, PyCharm)
- [ ] Remote examples (fetch from GitHub repo later)
- [ ] Example marketplace (community-contributed examples)

### Potential Gotchas

- **API rate limits:** SLE may throttle multiple rapid API calls → Add backoff retry
- **Transaction semantics:** No atomic multi-resource create → Plan rollback on error
- **Workspace isolation:** Ensure examples tagged & cleaned up per workspace
- **ID mapping:** Track created IDs carefully; test reference resolution
- **API changes:** SLE API may change → Version config schema carefully

---

## 13. Questions for Stakeholder Review

1. **Resource types:** Are location, product, system, asset, DUT, template the right starting set? Any missing?
2. **API endpoints:** Do the endpoints in Section 3.2 match the actual SLE APIs?
3. **Example content:** Should I create real-world examples (e.g., supply-chain tracking) or simple demos?
4. **Rollback strategy:** On error, should we auto-rollback or prompt user?
5. **Audit trail:** What should we log? Where should logs be stored?
6. **Workspace support:** Examples always in default workspace, or support --workspace option?
7. **Idempotency:** If example already exists, error or skip? Update?

---

**End of Plan Document**
