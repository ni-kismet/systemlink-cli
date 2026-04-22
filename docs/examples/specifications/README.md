# Specification Import and Export Examples

This folder contains sample payloads for the `slcli spec import` and `slcli spec export` workflows.

## Import Example

Use [import-specs.json](import-specs.json) as a starting point for a bulk import payload:

```bash
slcli spec import --file docs/examples/specifications/import-specs.json
```

Replace `"<PRODUCT_ID>"` and `"<WORKSPACE_ID>"` in the sample payload with values from your environment before importing.

The file contains only create-compatible fields such as `productId`, `specId`, `type`, `limit`, `conditions`, `keywords`, and `properties`.

If a spec payload omits `workspace`, `slcli spec import` now inherits the workspace from the referenced product unless you explicitly provide a workspace in the payload.

For agent-driven ingestion, CSV and PDF parsing should normalize into this same create-compatible JSON shape before upload.

## Export Example

Use the export command to generate a reusable payload with only the fields you want to carry forward:

```bash
slcli spec export \
  --product <PRODUCT_ID> \
  --projection PRODUCT_ID \
  --projection SPEC_ID \
  --projection NAME \
  --projection CATEGORY \
  --projection TYPE \
  --projection SYMBOL \
  --projection BLOCK \
  --projection UNIT \
  --projection WORKSPACE \
  --include-limits \
  --include-conditions \
  --output docs/examples/specifications/exported-specs.json
```

[exported-specs.json](exported-specs.json) shows the shape produced by that export workflow.

Replace `"<PRODUCT_ID>"` and `"<WORKSPACE_ID>"` in the checked-in example payload before reusing it in your environment.

If you plan to re-import an exported file, keep the export limited to create-compatible fields like the example above and avoid server-managed fields such as `id`, `createdAt`, `updatedAt`, and `version`.
