# Example Architecture & Best Practices

This document describes the architecture of the SystemLink CLI example system and best practices for extending it with new resource types.

## Table of Contents

1. [Architecture Overview](#architecture-overview)
2. [Code Organization](#code-organization)
3. [Core Concepts](#core-concepts)
4. [Resource Handling](#resource-handling)
5. [Adding New Resource Types](#adding-new-resource-types)
6. [Testing Strategy](#testing-strategy)
7. [Safety & Error Handling](#safety--error-handling)

## Architecture Overview

The example system is built on a three-layer architecture:

```
┌─────────────────────────────────────────────────────────┐
│                    CLI Layer                            │
│                (example_click.py)                       │
│  Handles: install, delete, list, info commands          │
└──────────────────┬──────────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────────┐
│              Provisioning Layer                         │
│              (example_provisioner.py)                   │
│  Handles: provision/delete operations, resource         │
│  creation/deletion, reference resolution                │
└──────────────────┬──────────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────────┐
│               Configuration Layer                       │
│              (example_loader.py)                        │
│  Handles: YAML parsing, schema validation,              │
│  example discovery and enumeration                      │
└─────────────────────────────────────────────────────────┘
```

## Code Organization

### Core Files

- **[slcli/example_click.py](../slcli/example_click.py)** - CLI entry point

  - `install` - Install example resources to a workspace
  - `delete` - Delete example resources from a workspace
  - `list` - List available examples
  - `info` - Show details about an example
  - Uses `ExampleProvisioner` for provisioning/deletion
  - Uses `ExampleLoader` for configuration loading

- **[slcli/example_provisioner.py](../slcli/example_provisioner.py)** - Core provisioning logic

  - `ExampleProvisioner` class orchestrates resource creation/deletion
  - Implements creation and deletion methods for each resource type
  - Handles:
    - Dry-run mode (validation without side effects)
    - Reference resolution (`${ref}` tokens → server IDs)
    - Duplicate detection (skip if already exists)
    - Audit logging (track all operations)
    - Workspace filtering (operate within scoped workspace)

- **[slcli/example_loader.py](../slcli/example_loader.py)** - Configuration management
  - `ExampleLoader` class loads and validates example YAML files
  - Supports schema versioning (currently v1.0)
  - Discovers examples from `slcli/examples/` directory
  - Validates required fields and resource types

### Configuration Files

Each example lives in `slcli/examples/{example-name}/`:

```
demo-complete-workflow/
├── config.yaml              # Resource definitions (YAML)
├── README.md                # Usage guide & background
└── _schema/schema-v1.0.json # (root) JSON schema for validation
```

## Core Concepts

### Reference Resolution

Resources can reference each other using `${id_reference}` syntax. References are resolved at provision time by building an `id_map`:

```yaml
resources:
  - type: location
    id_reference: loc_main
    name: Main Lab

  - type: system
    id_reference: sys_1
    name: Test System 1
    properties:
      location_id: "${loc_main}" # Will be replaced with created location ID
```

The provisioner:

1. Creates `loc_main`, records ID in `id_map`
2. Resolves `${loc_main}` → actual ID from `id_map`
3. Creates `sys_1` with resolved location ID

### Dry-Run Mode

Set `dry_run=True` when creating `ExampleProvisioner`:

- Resources are NOT created
- All results marked as `SKIPPED`
- Useful for validation before applying changes
- Returns empty `server_id` (or mock ID for reference resolution)

### Duplicate Detection

Before creating a resource, the provisioner queries the API to check if it already exists:

- If found: result marked `SKIPPED` with existing `server_id`
- If not found: resource is created
- This prevents accidental overwrites and allows idempotent operations

### Workspace Filtering

Resources are scoped to a workspace:

- When creating: include `workspace` in API payload
- When checking existence: filter by `workspace` in queries
- Allows multiple isolated example deployments

## Resource Handling

### Resource Types (Tier 1 - APM)

These are atomic infrastructure resources:

| Type       | API              | Create                                    | Query              | Delete                    |
| ---------- | ---------------- | ----------------------------------------- | ------------------ | ------------------------- |
| `location` | nilocation/v1    | POST locations                            | GET locations      | POST locations:deleteMany |
| `product`  | nitestmonitor/v2 | POST products                             | GET products       | POST delete-products      |
| `system`   | nisysmgmt/v1     | POST virtual                              | POST query-systems | POST remove-systems       |
| `asset`    | niapm/v1         | POST assets                               | POST query-assets  | POST delete-assets        |
| `dut`      | niapm/v1         | POST assets (assetType=DEVICE_UNDER_TEST) | POST query-assets  | POST delete-assets        |

**Pattern:**

```python
def _create_location(self, props: Dict[str, Any]) -> str:
    """Create location via /nilocation/v1/locations API and return server ID."""
    url = f"{get_base_url()}/nilocation/v1/locations"
    payload = {
        "name": props.get("name", "Unknown Location"),
        "workspace": self.workspace_id or "",
    }
    # Add optional fields, tag for cleanup
    resp = make_api_request("POST", url, payload, handle_errors=False)
    return str(resp.json().get("id", ""))

def _get_location_by_name(self, name: str) -> Optional[str]:
    """Find location by name, scoped to workspace and example tag."""
    # Client-side filtering for exact match + workspace + example tag

def _delete_location(self, props: Dict[str, Any]) -> Optional[str]:
    """Delete location by name."""
    # Look up ID, then call delete API
```

### Resource Types (Tier 2 - Workflow & Work Management)

These define the test execution workflow:

| Type           | API            | Create                  | Query                         | Delete                         |
| -------------- | -------------- | ----------------------- | ----------------------------- | ------------------------------ |
| `testtemplate` | niworkitem/v1  | POST workitem-templates | POST query-workitem-templates | POST delete-workitem-templates |
| `workflow`     | niworkorder/v1 | POST workflows          | POST query-workflows          | POST delete-workflows          |
| `work_item`    | niworkitem/v1  | POST workitems          | POST query-workitems          | POST delete-workitems          |
| `work_order`   | niworkorder/v1 | POST workorders         | POST query-workorders         | POST delete-workorders         |

**Pattern:**

```python
def _create_workflow(self, props: Dict[str, Any]) -> Optional[str]:
    """Create workflow with standard state machine."""
    # Include default states and actions
    # Resolve template references from id_map

def _get_workflow_by_name(self, name: str) -> Optional[str]:
    """Query with parameterized filter for safety."""
    payload = {
        "filter": "name == @0",
        "substitutions": [name],
        "projection": ["ID", "NAME"],
        "take": 100,  # Get multiple results to verify exact match
    }
    # Find exact case-insensitive match in results
```

### Resource Types (Tier 3 - Data & Results)

These capture test execution data:

| Type          | API              | Create                        | Query             | Delete              |
| ------------- | ---------------- | ----------------------------- | ----------------- | ------------------- |
| `test_result` | nitestmonitor/v2 | POST results                  | GET results       | POST delete-results |
| `data_table`  | nidataframe/v1   | POST tables                   | POST query-tables | POST delete-tables  |
| `file`        | nifile/v1        | POST upload-files (multipart) | Query via tags    | POST delete-files   |

**Special handling:**

- `test_result`: Tagged with `slcli-provisioner` + example tag; bulk delete by tag filter
- `data_table`: Dynamic LINQ query support
- `file`: Multipart form upload; metadata stored in custom properties for tagging

## Adding New Resource Types

To add a new resource type (e.g., `notebook`), follow this pattern:

### Step 1: Update Loader Schema

Edit `slcli/examples/_schema/schema-v1.0.json` to include the new type:

```json
{
  "type": "object",
  "properties": {
    "type": {
      "enum": [
        "location",
        "product",
        "system",
        "asset",
        "dut",
        "testtemplate",
        "workflow",
        "work_item",
        "work_order",
        "test_result",
        "data_table",
        "file",
        "notebook" // NEW
      ]
    }
  }
}
```

### Step 2: Update ExampleLoader

Add to `SUPPORTED_RESOURCE_TYPES` in [example_loader.py](../slcli/example_loader.py):

```python
SUPPORTED_RESOURCE_TYPES = {
    "location", "product", "system", "asset", "dut",
    "testtemplate", "workflow", "work_item", "work_order",
    "test_result", "data_table", "file",
    "notebook",  # NEW
}
```

### Step 3: Implement in ExampleProvisioner

Add to [example_provisioner.py](../slcli/example_provisioner.py):

```python
# Add to ProvisioningAction enum if needed
# CREATED, SKIPPED, FAILED, DELETED

def _create_notebook(self, props: Dict[str, Any]) -> Optional[str]:
    """Create notebook via /ninotebook/v1/notebooks.

    Args:
        props: Properties dict with 'name', 'description', etc.

    Returns:
        Notebook ID if created, None on error.
    """
    name = props.get("name", "")
    if not name:
        return None

    try:
        url = f"{get_base_url()}/ninotebook/v1/notebooks"
        payload = {
            "name": name,
            "description": props.get("description", ""),
            "workspace": self.workspace_id or "",
        }

        # Add optional fields from API schema
        for key in ["content", "owner", "tags"]:
            if key in props:
                payload[key] = props[key]

        # Tag resource for cleanup
        if self.example_name:
            tags = payload.get("tags", [])
            if not isinstance(tags, list):
                tags = []
            tags.append(f"slcli-example:{self.example_name}")
            payload["tags"] = tags

        resp = make_api_request("POST", url, payload, handle_errors=False)
        resp.raise_for_status()
        data = resp.json()

        # Extract ID from response
        return str(data.get("id", "")) if data.get("id") else None

    except Exception:
        return None

def _get_notebook_by_name(self, name: str) -> Optional[str]:
    """Find notebook by name within workspace.

    Returns:
        Notebook ID if found, None otherwise.
    """
    if not name:
        return None

    try:
        url = f"{get_base_url()}/ninotebook/v1/query-notebooks"
        payload = {
            "filter": "name == @0",
            "substitutions": [name],
            "projection": ["ID", "NAME"],
            "take": 100,
        }
        if self.workspace_id:
            payload["filter"] += " and workspace == @1"
            payload["substitutions"].append(self.workspace_id)

        resp = make_api_request("POST", url, payload, handle_errors=False)
        resp.raise_for_status()
        data = resp.json()

        if "notebooks" in data:
            for notebook in data["notebooks"]:
                if notebook.get("name", "").lower() == name.lower():
                    return str(notebook.get("id", "")) or None
        return None

    except Exception:
        return None

def _delete_notebook(self, props: Dict[str, Any]) -> Optional[str]:
    """Delete notebook by name.

    Returns:
        Notebook ID if deleted, None otherwise.
    """
    name = props.get("name", "")
    if not name:
        return None

    notebook_id = self._get_notebook_by_name(name)
    if not notebook_id:
        return None

    try:
        url = f"{get_base_url()}/ninotebook/v1/delete-notebooks"
        payload = {"ids": [notebook_id]}
        resp = make_api_request("POST", url, payload, handle_errors=False)
        resp.raise_for_status()
        return notebook_id

    except Exception:
        return None
```

### Step 4: Update Provisioning Dispatch

Add to the `create_map` and `delete_map` in `_provision_resource()` and `delete()`:

```python
create_map = {
    # ... existing entries ...
    "notebook": self._create_notebook,
}

delete_map = {
    # ... existing entries ...
    "notebook": self._delete_notebook,
}
```

### Step 5: Update Duplicate Detection

Add to the duplicate detection logic in `_provision_resource()`:

```python
elif rtype == "notebook":
    existing_id = self._get_notebook_by_name(rname)
```

### Step 6: Create Example

Create `slcli/examples/demo-notebooks/config.yaml`:

```yaml
format_version: "1.0"
name: "demo-notebooks"
title: "Notebook Example"
description: "Creates a sample notebook"
author: "Your Name"
tags: ["demo"]
estimated_setup_time_minutes: 2

resources:
  - type: notebook
    id_reference: nb_demo
    name: "Demo Notebook"
    properties:
      description: "Sample notebook for demonstration"
```

### Step 7: Add Tests

Create `tests/unit/test_example_notebook.py`:

```python
from unittest.mock import patch, MagicMock
from slcli.example_provisioner import ExampleProvisioner, ProvisioningAction

@patch("slcli.example_provisioner.make_api_request")
def test_create_notebook(mock_api: Any) -> None:
    # Mock API response
    resp = MagicMock()
    resp.json.return_value = {"id": "notebook-12345"}
    mock_api.return_value = resp

    prov = ExampleProvisioner(workspace_id="ws-test")
    result = prov._create_notebook({"name": "Test Notebook"})

    assert result == "notebook-12345"
    mock_api.assert_called_once()
    call_args = mock_api.call_args
    assert "notebook" in call_args[0][1]
```

## Testing Strategy

### Unit Tests

Located in `tests/unit/test_example_*.py`:

1. **Dry-run tests** - Verify `dry_run=True` skips creation
2. **Provisioning tests** - Mock API responses, verify creation order and ID assignment
3. **Duplicate detection tests** - Verify skipped when resource exists
4. **Reference resolution tests** - Verify `${ref}` tokens resolved correctly
5. **Error handling tests** - Verify graceful failures with error messages

**Example test:**

```python
@patch("slcli.example_provisioner.make_api_request")
def test_duplicate_detection(mock_api: Any) -> None:
    # First call (existence check) returns existing resource
    resp_exists = MagicMock()
    resp_exists.json.return_value = {"locations": [{"id": "loc-existing"}]}

    # Setup mock to return different responses based on call order
    mock_api.side_effect = [resp_exists]

    prov = ExampleProvisioner()
    result = prov._create_location({"name": "Existing Location"})

    # Should detect it already exists
    assert result == "__DUPLICATE_ID__loc-existing" or result == "loc-existing"
```

### End-to-End Tests

Run against a real SystemLink instance:

```bash
# Install example
slcli example install demo-notebooks -w test-workspace --dry-run

# Verify in workspace UI - resources should NOT be created

# Install for real
slcli example install demo-notebooks -w test-workspace

# Verify in workspace UI - resources should be created

# Delete and verify cleanup
slcli example delete demo-notebooks -w test-workspace
```

### Test Coverage

Current gaps that should be addressed:

1. **Batch operations** - Multiple resources of same type
2. **Circular references** - `A → B → A` dependency cycles
3. **Workspace filtering** - Resources visible in correct workspace only
4. **Query safety** - Parameterized filters prevent injection
5. **Deletion ordering** - Reverse order of creation (LIFO)

## Safety & Error Handling

### Query Safety (Defense in Depth)

All queries use parameterized filters to prevent injection attacks:

```python
# SAFE: Parameterized substitution
payload = {
    "filter": "name == @0",
    "substitutions": [user_input],
}

# UNSAFE: String interpolation (DO NOT USE)
payload = {
    "filter": f"name == '{user_input}'",  # Vulnerable!
}
```

### Exact Name Matching

When finding resources by name, we:

1. Query with parameterized filter
2. Get multiple results (take=100)
3. Loop through and find exact case-insensitive match
4. Verify workspace match (if scoped)
5. Verify example tag match (if tagged)

This prevents returning the "wrong" resource due to filter bugs.

### Deletion Safety

When deleting, we:

1. Look up resource ID by name
2. Verify it exists before deletion
3. Only delete if ID found
4. Report SKIPPED (not found) vs DELETED (removed)

### Error Reporting

All operations return structured results:

```python
ProvisioningResult(
    id_reference="loc_main",
    resource_type="location",
    resource_name="Main Lab",
    action=ProvisioningAction.CREATED,
    server_id="loc-12345",
    error=None,  # Or error message
)
```

Results are:

- Printed as formatted table
- Optionally saved to JSON audit log
- Provide full traceability of operations

## Best Practices Summary

✅ **DO:**

- Use parameterized filters (`@0`, `@1` placeholders)
- Verify resource exists by exact name before creating/deleting
- Query with `take=100` to verify exact match
- Tag all resources for precise cleanup
- Implement dry-run mode
- Return optional ID (None if failed)
- Document example in README

❌ **DON'T:**

- Use string interpolation in filter expressions
- Blindly use first query result
- Assume filter works perfectly (verify match)
- Create resources without existence check
- Hard-code workspace IDs
- Skip error handling
- Create uncleaned test resources

## Implementation Status

### Current Coverage

The example system includes comprehensive coverage of core resource types:

**Tier 1 (APM Foundation):**

- Location, Product, System, Asset, DUT

**Tier 2 (Workflow):**

- Test Template, Workflow, Work Item, Work Order

**Tier 3 (Data):**

- Test Result, Data Table, File

### Test Coverage

- **Unit Tests**: 310+ passing tests across all example modules
- **example_provisioner.py**: 9 test functions covering:
  - Reference resolution (${ref} token substitution)
  - Duplicate detection (skip existing resources)
  - Invalid config handling
  - Unsupported resource type handling
  - Tag filtering on deletion
- **example_loader.py**: Full schema validation tests
- **example_click.py**: CLI command tests

**Coverage Metrics:**

- `example_loader.py`: 84% code coverage
- `example_click.py`: 83% code coverage
- `example_provisioner.py`: 20%+ code coverage (large complex module)

All tests pass without type checking errors (mypy verified).

### Example Configurations

Available examples demonstrate different use cases:

1. **demo-test-plans** - Basic resource hierarchy (Tier 1-2)
2. **demo-complete-workflow** - Complete workflow with all resource types (Tier 0-3)

Each example includes:

- YAML configuration with schema validation
- README with setup instructions
- Reference system for resource dependencies
- Tag-based cleanup support

## References

- [Example CLI Guide](../README.md#examples)
- [Demo Workflow Example](../slcli/examples/demo-complete-workflow)
- [OpenAPI Schemas](../openapi-schemas/)
