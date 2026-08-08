# SystemLink Examples Directory

This directory contains example configurations for quickly setting up demo resources in SystemLink Enterprise (SLE).

## Examples

### demo-data-2

A complete example demonstrating the end-to-end test planning workflow. Includes:

- 1 location (Demo HQ)
- 1 product (Demo Widget Pro)
- 2 systems (Test Stand 1 & 2)
- 2 assets (Asset 1 & 2)
- 2 DUTs (DUT 1 & 2)
- 1 test template

**Setup time:** ~5 minutes

### spec-compliance-notebooks

A complete example providing Jupyter notebooks for performing specification compliance analysis on test data. Publishes three notebooks with the File Analysis interface:

- Spec Compliance Calculation
- Spec Analysis & Compliance Calculation
- Specfile Extraction and Ingestion

**Setup time:** ~3 minutes

### exercise-5-1-parametric-insights

Training data for **Exercise 5-1: Query and Visualize Parametric Test Data**.
Provisions a six-week dataset of thermal cycle test results for the **Model ABC** battery
pack product across three test stands, plus distractor products (Model XYZ, Model ABC Rev B)
to populate the Products table realistically. Includes deliberate anomalies students will
discover through visualization:

- 18 test results (Model ABC) with 11 parametric measurements per result
- TC-03 runs ~3–4 °C warmer than TC-01/TC-02 (calibration offset)
- TC-01 Cycle 5: internal resistance spike → FAIL
- TC-03 Cycle 4: cell temperature spike → FAIL

**Setup time:** ~5 minutes

### demo-data-3

Phase-one fixture data for validating Systems and Products queries. It
provisions the resource families supported by the generic example provisioner:
1 deployment state, 1 feed, 1 tag with 12 history samples, 3 active alarms,
and 1 specification (metadata only). It reports unsupported package inventory,
jobs, feed packages, deployment state package inventory, specification
evidence, and workspace lifecycle.
Because those capabilities are required by the full Nigel acceptance matrix,
the install intentionally exits nonzero after emitting its JSON manifest.

**Setup time:** ~5 minutes

## Usage

```bash
# List available examples
slcli example list

# Show details about an example
slcli example info demo-data-2

# Preview what would be created (dry-run)
slcli example install demo-data-2 -w <workspace-id> --dry-run

# Create resources in a specific workspace (name or ID)
slcli example install demo-data-2 -w <workspace>
# Write an audit log of provisioning results
slcli example install demo-data-2 -w <workspace> --audit-log install-log.json --format json

# Install the Nigel fixture and inspect its completeness manifest
slcli example install demo-data-3 \
  -w <workspace> --format json --audit-log nigel-fixture-manifest.json

# Delete example resources from a workspace
slcli example delete demo-data-2 -w <workspace-id> --dry-run
slcli example delete demo-data-2 -w <workspace>
# Write an audit log of deletion results
slcli example delete demo-data-2 -w <workspace> --audit-log delete-log.json --format json
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
- `workflow` - Workflow definition
- `work_item` - Work item
- `work_order` - Work order
- `test_result` - Test Monitor result, with optional steps
- `data_table` - DataFrame table schema
- `file` - Uploaded supporting file
- `notebook` - Uploaded Jupyter notebook
- `feed` - Package feed metadata (package uploads are separate)
- `state` - Systems deployment state
- `tag` - Workspace-scoped tag metadata
- `specification` - Product specification metadata
- `alarm` - Active alarm instance and transition

## Notes

- Examples are versioned with the `format_version` field (currently 1.0)
- Resource cleanup is tag-based and order-aware
- References use `${id_reference}` syntax for interpolation
- All resources created by an example are tagged with the example name for safe deletion
- Examples with `install_manifest: true` emit grouped resource actions and a
  `validation.complete` flag when JSON output is requested. Unsupported
  capabilities or failed relationships make the command return a nonzero exit
  code; do not treat the resource list alone as proof of completeness.
