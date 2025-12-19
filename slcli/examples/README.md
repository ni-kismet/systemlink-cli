# SystemLink Examples Directory

This directory contains example configurations for quickly setting up demo resources in SystemLink Enterprise (SLE).

## Examples

### demo-test-plans

A complete example demonstrating the end-to-end test planning workflow. Includes:

- 1 location (Demo HQ)
- 1 product (Demo Widget Pro)
- 2 systems (Test Stand 1 & 2)
- 2 assets (Asset 1 & 2)
- 2 DUTs (DUT 1 & 2)
- 1 test template

**Setup time:** ~5 minutes

## Usage

```bash
# List available examples
slcli example list

# Show details about an example
slcli example info demo-test-plans

# Preview what would be created (dry-run)
slcli example install demo-test-plans -w <workspace-id> --dry-run

# Create resources in a specific workspace (name or ID)
slcli example install demo-test-plans -w <workspace>
# Write an audit log of provisioning results
slcli example install demo-test-plans -w <workspace> --audit-log install-log.json --format json

# Delete example resources from a workspace
slcli example delete demo-test-plans -w <workspace-id> --dry-run
slcli example delete demo-test-plans -w <workspace>
# Write an audit log of deletion results
slcli example delete demo-test-plans -w <workspace> --audit-log delete-log.json --format json
```

## Creating New Examples

1. Create a new directory in `examples/`:

   ```
   examples/my-example/
   ├── config.yaml          # Example configuration
   └── README.md            # Optional: Setup guide
   ```

2. Create `config.yaml` following the schema in `_schema/schema-v1.0.json`

3. Test locally:
   ```bash
   slcli example info my-example
   ```

## Configuration Format

All examples use YAML format with the following structure:

```yaml
format_version: "1.0"
name: "example-slug"
title: "Example Title"
description: "Detailed description..."
author: "Author Name"
tags: ["training", "demo"]
estimated_setup_time_minutes: 5

resources:
  - type: "location"
    name: "Location Name"
    properties:
      # API-specific fields
    id_reference: "loc_ref"
    tags: ["example"]

  - type: "system"
    name: "System Name"
    properties:
      location_id: "${loc_ref}" # Reference resolution
    id_reference: "sys_ref"
    tags: ["example"]

cleanup:
  order: ["system", "location"]
  filter_tags: ["example"]
  require_confirmation: true
```

## Resource Types Supported

- `location` - Physical location
- `product` - Product definition
- `system` - Test system
- `asset` - Asset on a system
- `dut` - Device under test
- `testtemplate` - Test plan template

## Notes

- Examples are versioned with the `format_version` field (currently 1.0)
- Resource cleanup is tag-based and order-aware
- References use `${id_reference}` syntax for interpolation
- All resources created by an example are tagged with the example name for safe deletion
