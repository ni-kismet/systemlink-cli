# Specification Import and Export Examples

This folder contains sample payloads for the `slcli spec import` and `slcli spec export` workflows.

## Import Example

Use [import-specs.json](import-specs.json) as a starting point for a bulk import payload:

```bash
slcli spec import --file docs/examples/specifications/import-specs.json
```

The file contains only create-compatible fields such as `productId`, `specId`, `type`, `limit`, `conditions`, `keywords`, and `properties`.

If a spec payload omits `workspace`, `slcli spec import` now inherits the workspace from the referenced product unless you explicitly provide a workspace in the payload.

For agent-driven ingestion, CSV and PDF parsing should normalize into this same create-compatible JSON shape before upload.

## Export Example

Use the export command to generate a reusable payload with only the fields you want to carry forward:

```bash
slcli spec export \
  --product demo-product-usb-hub \
  --projection PRODUCT_ID \
  --projection SPEC_ID \
  --projection NAME \
  --projection CATEGORY \
  --projection TYPE \
  --projection SYMBOL \
  --projection BLOCK \
  --projection UNIT \
  --include-limits \
  --include-conditions \
  --output docs/examples/specifications/exported-specs.json
```

[exported-specs.json](exported-specs.json) shows the shape produced by that export workflow.

If you plan to re-import an exported file, keep the export limited to create-compatible fields like the example above and avoid server-managed fields such as `id`, `createdAt`, `updatedAt`, and `version`.
