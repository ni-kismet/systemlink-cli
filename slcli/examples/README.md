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
1 deployment state populated with that feed and both package versions, 1 tag
with 12 history samples, 3 active alarms, and 1 specification (metadata only).
It reports unsupported jobs, specification evidence, and workspace lifecycle.
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

# Install an example from any local directory. Paths in config.yaml are
# resolved relative to the directory containing config.yaml.
slcli example install \
  --file ./fixtures/example-resources/config.yaml \
  --workspace <workspace>

# Delete example resources from a workspace
slcli example delete demo-data-2 -w <workspace-id> --dry-run
slcli example delete demo-data-2 -w <workspace>
# Write an audit log of deletion results
slcli example delete demo-data-2 -w <workspace> --audit-log delete-log.json --format json
```

## Creating New Examples

For the complete authoring contract, including external fixture directories,
resource references, file-backed resources, and validation caveats, see the
[Example Fixture Authoring Guide](../skills/slcli/references/example-authoring.md).

1. Create a new directory in `examples/`:

   ```
   examples/my-example/
   ├── config.yaml          # Example configuration
   └── README.md            # Optional: Setup guide
   ```

2. Create `config.yaml` following the schema in
  [`_schema/schema-v1.0.json`](_schema/schema-v1.0.json). Use the closest
  bundled example as the reference for resource-specific `properties`.

3. Test locally:
  ```bash
  slcli example install my-example --workspace <workspace> --dry-run
   ```

External fixtures use the same format and do not need to be copied into the
package:

```text
fixtures/example-resources/
├── config.yaml
├── README.md
└── product-xyz-specification.csv
```

```bash
slcli example install \
  --file fixtures/example-resources/config.yaml \
  --workspace <workspace> \
  --dry-run
```

Paths in `file_path`, `rows_file`, and `data_file` properties are resolved
relative to the directory containing `config.yaml`. Only files named by a
resource are uploaded; a sibling README or data file is not uploaded merely
because it is present.

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
- `feed` - Package feed metadata
- `package` - Package uploaded to a previously created feed
- `state` - Systems deployment state
- `tag` - Workspace-scoped tag metadata
- `specification` - Product specification metadata
- `alarm` - Active alarm instance and transition

### Package Resources

Package resources must follow their feed in the resource list so that the feed
reference can be resolved:

```yaml
- type: "feed"
  name: "Fixture Windows Feed"
  properties:
    platform: "windows"
  id_reference: "feed_fixture"

- type: "package"
  name: "Fixture package"
  properties:
    feed_id: "${feed_fixture}"
    source:
      type: "dummy"
      package_name: "fixture-package"
      version: "1.0.0"
      architecture: "all"
      files:
        README.txt: "Package payload created for fixture validation.\n"
  id_reference: "package_fixture"
```

Supported package sources are:

- `dummy` (default): creates a deterministic minimal `.nipkg` from inline
  `files` and uploads it to the feed.
- `file`: uploads a fixture-relative `.nipkg` from `source.path`. The path is
  contained within the directory containing `config.yaml`.
- `repository`: downloads a direct HTTP(S) URL ending in `.nipkg`, then uploads
  it. Use a URL obtained from the repository/feed service; the repository
  catalog is not treated as a package-byte endpoint. Downloads are streamed and
  TLS verification remains enabled.

`source.package_name` and `source.version` identify a package for duplicate
detection across all source modes. Dummy packages default to the resource name
and version `1.0.0`; declare both values for local or repository packages when
they cannot be inferred from the resource name.

## Notes

- Examples are versioned with the `format_version` field (currently 1.0)
- Resource cleanup uses example ownership tags and reverse resource order. The
  `cleanup` block is descriptive metadata; `example delete` does not currently
  consume its custom order or confirmation settings.
- References use `${id_reference}` syntax for interpolation
- Resources are provisioned in list order, so referenced resources must appear first
- Package resources are provisioned after their feed and are deleted before it
- All resources created by an example are tagged with the example name for safe deletion
- The JSON Schema is the authoring reference; runtime validation currently checks only a subset of its types and patterns
- Examples with `install_manifest: true` emit grouped resource actions and a
  `validation.complete` flag when JSON output is requested. Unsupported
  capabilities or failed relationships make the command return a nonzero exit
  code; do not treat the resource list alone as proof of completeness.
