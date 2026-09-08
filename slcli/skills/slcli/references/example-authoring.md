# Example Fixture Authoring

Use this guide when creating a SystemLink example for `slcli example install`.
The machine-readable contract is [schema-v1.0.json](../../../examples/_schema/schema-v1.0.json).
The schema defines the common YAML envelope; the bundled examples show the
SystemLink API properties for each resource type.

## Quick Start

An example is a directory containing `config.yaml` and any files referenced by
that configuration:

```text
fixtures/example-resources/
├── config.yaml
├── README.md
├── product-xyz-specification.csv
└── notebooks/
    └── analysis.ipynb
```

Install a bundled example by name:

```bash
slcli example install demo-data-1 \
  --workspace <workspace> --dry-run
```

Install an example from any local directory with `--file`:

```bash
slcli example install \
  --file fixtures/example-resources/config.yaml \
  --workspace <workspace> \
  --dry-run
```

For `--file` installs, all relative file references are resolved from the
directory containing `config.yaml`. A README or an unreferenced file is not
uploaded automatically; add a `file` or `notebook` resource when it should be
published to SystemLink.

## Configuration Contract

The required top-level fields are:

| Field | Meaning |
| --- | --- |
| `format_version` | Schema version. Use the string `"1.0"`. |
| `name` | Lowercase example slug using letters, numbers, and hyphens. It is also used for ownership tagging. |
| `title` | Human-readable title. |
| `resources` | Ordered list of resources to create. |

Common optional fields include `description`, `author`, `created_date`,
`updated_date`, `example_version`, `tags`, `estimated_setup_time_minutes`,
`required_systemlink_version`, `target_workspace`, `workspace_name`,
`install_manifest`, `cleanup`, `validation`, and `post_install`.

Each resource has this envelope:

```yaml
- type: "location"
  name: "Production Test Lab"
  properties:
    city: "Austin"
  id_reference: "loc_lab"
  tags: ["example-resources"]
```

- `type` selects one of the supported resource handlers.
- `name` is the resource name sent to SystemLink.
- `properties` contains fields specific to that resource type.
- `id_reference` is a local identifier using lowercase letters, numbers, and
  underscores. Use it in later properties as `${id_reference}`.
- `tags` is used for organization and cleanup filtering.

Resources are processed in list order. Put a resource before any resource that
references its ID. References are resolved recursively inside `properties`, but
only a complete string such as `${loc_lab}` is substituted; embedded text such
as `location-${loc_lab}` is not substituted.

## Resource Types

The supported `type` values are:

| Type | Typical use | Example |
| --- | --- | --- |
| `location` | Physical location hierarchy | [demo-data-1](../../../examples/demo-data-1/config.yaml) |
| `product` | Product definition and part number | [demo-data-3](../../../examples/demo-data-3/config.yaml) |
| `system` | Test system or virtual system | [demo-data-3](../../../examples/demo-data-3/config.yaml) |
| `asset` | Instrument or equipment asset | [demo-data-3](../../../examples/demo-data-3/config.yaml) |
| `dut` | Device under test | [demo-data-1](../../../examples/demo-data-1/config.yaml) |
| `testtemplate` | Test plan template | [demo-data-2](../../../examples/demo-data-2/config.yaml) |
| `workflow` | Work item state machine | [demo-data-1](../../../examples/demo-data-1/config.yaml) |
| `work_item` | Work item instance | [demo-data-1](../../../examples/demo-data-1/config.yaml) |
| `work_order` | Work order | [demo-data-1](../../../examples/demo-data-1/config.yaml) |
| `test_result` | Test Monitor result and optional steps | [demo-data-3](../../../examples/demo-data-3/config.yaml) |
| `data_table` | DataFrame table and optional rows | [demo-data-3](../../../examples/demo-data-3/config.yaml) |
| `file` | Supporting file upload | [spec-compliance-notebooks](../../../examples/spec-compliance-notebooks/config.yaml) |
| `notebook` | Jupyter notebook upload | [spec-compliance-notebooks](../../../examples/spec-compliance-notebooks/config.yaml) |
| `feed` | Package feed metadata | [demo-data-3](../../../examples/demo-data-3/config.yaml) |
| `package` | Package uploaded to a feed | This guide's package example |
| `state` | Deployment state metadata | [demo-data-3](../../../examples/demo-data-3/config.yaml) |
| `tag` | Workspace tag and optional history | [demo-data-3](../../../examples/demo-data-3/config.yaml) |
| `specification` | Product specification and conditions | [demo-data-3](../../../examples/demo-data-3/config.yaml) |
| `alarm` | Alarm instance or transition | [demo-data-3](../../../examples/demo-data-3/config.yaml) |

The `properties` object is intentionally resource-specific and open-ended in
the common schema. Start with the closest bundled example and verify the
property names against the corresponding `slcli` command or API model.

### Package Resources

Place a package after its feed and reference the feed with `${feed_reference}`:

```yaml
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
        README.txt: "Fixture payload\n"
  id_reference: "package_fixture"
```

The `source.type` values are:

- `dummy`: builds a minimal `.nipkg` from inline text or byte `files`. The
  generated folder uses `<package_name>_<version>_<architecture>` naming.
- `file`: uploads a `.nipkg` at a path relative to the fixture directory, for
  example `source: {type: file, path: packages/fixture_1.0.0_all.nipkg}`.
- `repository`: downloads an explicitly declared HTTP(S) `.nipkg` URL before
  upload. Use a direct package URL discovered from NI repository/feed metadata;
  the repository catalog itself does not provide package bytes through this
  resource. The URL must end in `.nipkg`.

All package sources are uploaded through the existing feed package helpers.
Package identity is the target feed plus package name and version, and package
cleanup runs before the feed cleanup because resources are deleted in reverse
configuration order.

To include a provisioned feed and packages in a deployment state, place the
state after those resources and use their references as list entries:

```yaml
- type: "state"
  name: "Fixture state"
  properties:
    distribution: "WINDOWS"
    architecture: "X64"
    feeds:
      - "${feed_fixture}"
    packages:
      - "${package_fixture}"
  id_reference: "state_fixture"
```

The provisioner resolves feed references to `{name, url, enabled, compressed}`
objects and package references to `{name, version, installRecommends}` objects.
This keeps server IDs out of the state content and makes reinstalling an
existing fixture refresh its state inventory.

## File-Backed Resources

These are the file-reference keys consumed by the generic provisioner:

| Resource | Property | Value |
| --- | --- | --- |
| `file` | `file_path` | Relative path to bytes to upload. `description`, `content_type`, `keywords`, and `tags` are also supported metadata. |
| `notebook` | `file_path` | Relative path to an `.ipynb` file. `notebook_interface` selects the notebook interface, for example `File Analysis`. |
| `data_table` | `rows_file` or `data_file` | Relative path to JSON rows. The JSON may be a list of rows or an object containing `frame.columns` and `frame.data`. |

A data table may use inline `rows` instead of a rows file, but it must not
define both. Row values are normalized to strings when appended. The configured
`columns` must match the columns in the rows payload when both are provided.

Example:

```yaml
- type: "file"
  name: "product-xyz-specification.csv"
  properties:
    file_path: "product-xyz-specification.csv"
    content_type: "text/csv"
  id_reference: "file_specification"

- type: "data_table"
  name: "Overvoltage Results"
  properties:
    columns:
      - name: "timestamp"
      - name: "value"
    rows_file: "data/overvoltage-results.json"
  id_reference: "table_overvoltage"
```

## Validation And Dry Runs

The JSON Schema is the authoring reference, but the current loader performs a
smaller runtime validation set. It checks required fields, the supported format
version, supported resource types, basic resource reference identifiers, and
undefined `${reference}` values. It does not enforce every JSON Schema type or
pattern, and `properties` remains API-specific.

Use a dry run before making API calls:

```bash
slcli example install \
  --file fixtures/example-resources/config.yaml \
  --workspace <workspace> \
  --dry-run \
  --format json
```

For a real install, inspect the JSON result when checking automation:

```bash
slcli example install \
  --file fixtures/example-resources/config.yaml \
  --workspace <workspace> \
  --format json \
  --audit-log install.json
```

A successful resource list does not prove that every intended relationship or
capability was created. If the configuration uses `install_manifest: true`,
check `validation.complete` and the `unsupported` and `failed_relationships`
entries in the JSON manifest.

The `cleanup` block is currently descriptive metadata. `slcli example delete`
uses the example ownership marker and reverses the resource list; it does not
currently apply a custom cleanup order or confirmation setting from the YAML.

## Authoring Checklist

Before sharing an example:

1. Put `config.yaml` and every referenced file in the fixture directory.
2. Set a unique lowercase `name` and `format_version: "1.0"`.
3. Give every resource a unique `id_reference` and place resources in dependency order.
4. Use the closest bundled fixture as the reference for resource-specific properties.
5. Add explicit `file` or `notebook` resources for files that should be uploaded.
6. Run the external-file dry run and inspect JSON output for failed resources.
7. Add a README with the workspace prerequisites, expected resources, and post-install steps.
8. Add an `install_manifest` and `validation` section when the fixture has known limitations.
