# DataFrame Command Proposal: Analysis & Recommendations

**Date:** April 27, 2026  
**Context:** Planning a new `slcli dataframe` command group against the `nidataframe` v1 OpenAPI

---

## Executive Summary

The `nidataframe` API is a good fit for a new `slcli dataframe` command group, but the CLI should be designed around the actual service model:

1. The resource is a **table**, not a generic mutable dataframe object.
2. The primary value for CLI users is **schema discovery** and **scriptable row access**.
3. Row writes are **append-only**. The API supports appending rows, but it does **not** expose arbitrary row update or delete operations.
4. Table metadata is fully manageable: create, list, get, update metadata, and delete are all supported.

**Recommendation:** Add a focused `slcli dataframe` group with standard metadata commands plus dedicated data access commands:

```bash
slcli dataframe list
slcli dataframe get <table-id>
slcli dataframe schema <table-id>
slcli dataframe query <table-id>
slcli dataframe export <table-id>
slcli dataframe append <table-id>
slcli dataframe create
slcli dataframe update <table-id>
slcli dataframe delete <table-id>
```

This gives users the three things they actually need:

- discover table shape quickly
- read/query/export rows in script-friendly formats
- create tables and append new data without promising unsupported row-mutation behavior

---

## API Assessment

### Available Endpoints

#### Table metadata

- `GET /nidataframe/v1/tables` — list tables
- `POST /nidataframe/v1/query-tables` — query tables with filter, projection, ordering, pagination
- `POST /nidataframe/v1/tables` — create table
- `GET /nidataframe/v1/tables/{id}` — get table metadata and columns
- `PATCH /nidataframe/v1/tables/{id}` — modify table metadata and column properties
- `DELETE /nidataframe/v1/tables/{id}` — delete single table
- `POST /nidataframe/v1/delete-tables` — delete multiple tables
- `POST /nidataframe/v1/modify-tables` — modify multiple tables

#### Row data

- `GET /nidataframe/v1/tables/{id}/data` — read rows with basic column selection and ordering
- `POST /nidataframe/v1/tables/{id}/query-data` — query rows with structured filters, ordering, pagination
- `POST /nidataframe/v1/tables/{id}/export-data` — export rows, currently as CSV
- `POST /nidataframe/v1/tables/{id}/data` — append rows using JSON or Arrow stream
- `POST /nidataframe/v1/tables/{id}/query-decimated-data` — decimated reads for large numeric/timeseries tables

### Data Model Shape

The service already provides the information that matters most for scripting:

- table-level metadata: `id`, `name`, `workspace`, `rowCount`, `supportsAppend`, `properties`, timestamps
- column-level schema: `name`, `dataType`, `columnType`, `properties`
- row data in split-oriented dataframe form:

```json
{
  "frame": {
    "columns": ["Time", "Voltage", "State"],
    "data": [
      ["2026-04-27T10:00:00.000Z", "5.01", "PASS"],
      ["2026-04-27T10:00:01.000Z", "5.02", "PASS"]
    ]
  },
  "totalRowCount": 2,
  "continuationToken": null
}
```

This is already script-friendly and should be preserved in `--format json` output instead of flattening it into a lossy custom shape.

### Important Constraints

#### 1. Row writes are append-only

There is no API for updating or deleting existing rows. The CLI should expose this honestly as `append`, not `write` or `update-row`.

#### 2. Exactly one index column is required at create time

Each table must have exactly one `INDEX` column, and its type must be `INT32`, `INT64`, or `TIMESTAMP`.

#### 3. Query filtering is structured, not Dynamic LINQ

Unlike several existing services in `slcli`, row queries use structured filters like:

```json
{
  "filters": [
    {
      "column": "Time",
      "operation": "GREATER_THAN_EQUALS",
      "value": "2026-04-01T00:00:00.000Z"
    },
    { "column": "State", "operation": "EQUALS", "value": "FAIL" }
  ]
}
```

That means the CLI should offer both:

- convenience flags for common shell usage
- a raw request-file option for complex queries

#### 4. Export is CSV-only today

The export endpoint supports `CSV`, either inline or via download link. The first CLI version should not invent unsupported export formats.

---

## Recommended CLI Structure

### Core Metadata Commands

#### `slcli dataframe list`

Purpose: discover available tables.

Recommended options:

- `--name TEXT` — contains match on table name
- `--workspace, -w TEXT` — workspace name or ID
- `--test-result-id TEXT` — filter associated test result
- `--supports-append / --no-supports-append`
- `--filter TEXT` — raw `query-tables` filter expression
- `--substitution TEXT` — repeatable substitutions for `--filter`
- `--order-by [CREATED_AT|METADATA_MODIFIED_AT|NAME|NUMBER_OF_ROWS|ROWS_MODIFIED_AT]`
- `--descending / --ascending`
- `--take, -t INTEGER` — default 25 for table output
- `--format, -f [table|json]`

Implementation notes:

- Use `POST /query-tables` instead of `GET /tables` for consistency and better filtering.
- Default table output should show: `Name`, `ID`, `Workspace`, `Rows`, `Append`, `Modified`.
- Default JSON output should return the service response shape or a minimal wrapper that still includes `continuationToken`.

#### `slcli dataframe get <table-id>`

Purpose: show one table's metadata summary.

Recommended output:

- summary fields: `id`, `name`, `workspace`, `rowCount`, `supportsAppend`, `testResultId`, timestamps
- column count
- properties count or selected properties

Recommended options:

- `--format, -f [table|json]`

Implementation notes:

- Use `GET /tables/{id}`.
- Table output should be concise and lead with schema facts, not just dump properties.

#### `slcli dataframe schema <table-id>`

Purpose: make table shape inspection first-class for shell scripting and humans.

Recommended output:

- one row per column
- columns: `Name`, `Data Type`, `Column Type`, `Properties`

Recommended options:

- `--format, -f [table|json]`
- `--properties/--no-properties` — include column property maps in table output

Rationale:

- `get` is useful for resource metadata.
- `schema` is the command users will actually reach for when they need to know how to query or append data.

### Data Access Commands

#### `slcli dataframe query <table-id>`

Purpose: read rows with column selection, filtering, ordering, and pagination.

Recommended options:

- `--columns TEXT` — comma-separated column list in response order
- `--where TEXT` — repeatable shorthand in the form `column,operation,value`
- `--order-by TEXT` — repeatable shorthand in the form `column[:asc|desc]`
- `--take, -t INTEGER` — default 100 for interactive use, max 10000
- `--continuation-token TEXT`
- `--request FILE` — raw JSON request body for advanced use
- `--format, -f [table|json]`

Recommended JSON behavior:

- return `frame`, `totalRowCount`, and `continuationToken`
- do not silently reshape split-format data into record arrays

Recommended table behavior:

- render the returned frame as a normal table using `frame.columns`
- if `continuationToken` exists, display a pager prompt similar to other list commands

Implementation notes:

- Use `POST /tables/{id}/query-data` for almost everything.
- Keep `GET /tables/{id}/data` as an internal fast-path only if the request is a simple projection/order case.
- Add a `--request` file path because structured filter syntax is too awkward to force entirely through flags.

#### `slcli dataframe export <table-id>`

Purpose: export query results to CSV for downstream tools.

Recommended options:

- same filter, column, and ordering options as `query`
- `--take INTEGER`
- `--output, -o FILE` — required for file export workflow
- `--inline` — print CSV to stdout when no output file is given

Implementation notes:

- Use `POST /tables/{id}/export-data` with `responseFormat=CSV`.
- Default to inline response handling for simple piping.
- Support writing the CSV body directly to `--output`.
- Do not add XLSX or Parquet until the service supports it or the CLI intentionally performs a client-side conversion.

### Write Commands

#### `slcli dataframe append <table-id>`

Purpose: append new rows to an existing table.

Recommended options:

- `--input, -i FILE` — JSON file in DataFrame split format
- `--columns TEXT` — optional override when reading row-only input formats later
- `--end-of-data` — mark the table complete after append
- `--format, -f [json]` only if we want a machine-readable confirmation block

Initial scope recommendation:

- support JSON input first
- defer Arrow stream input unless a clear performance use case appears

Example input:

```json
{
  "frame": {
    "columns": ["Time", "Voltage", "State"],
    "data": [
      ["2026-04-27T10:00:00.000Z", "5.01", "PASS"],
      ["2026-04-27T10:00:01.000Z", "4.72", "FAIL"]
    ]
  },
  "endOfData": false
}
```

Implementation notes:

- Use `POST /tables/{id}/data`.
- Validate input early against obvious table constraints when practical:
  - referenced columns exist
  - non-nullable columns are present unless omitted by design with full-column ordering
  - `endOfData` semantics are explicit

#### `slcli dataframe create`

Purpose: create a new table with explicit schema.

Recommended options:

- `--definition FILE` — JSON request body file
- `--name TEXT` — convenience override
- `--workspace, -w TEXT`
- `--format, -f [table|json]`

Initial scope recommendation:

- require a JSON definition file in the service schema
- optionally add repeated `--column` convenience flags later if users ask for it

Rationale:

- table definitions are structured enough that file-based input is clearer and safer than a long list of flags
- this matches the service contract closely and keeps the first implementation small

#### `slcli dataframe update <table-id>`

Purpose: update table metadata and column properties.

Recommended options:

- `--name TEXT`
- `--workspace, -w TEXT`
- `--test-result-id TEXT`
- `--property KEY=VALUE` — repeatable
- `--remove-property KEY` — repeatable
- `--column-property COLUMN:KEY=VALUE` — repeatable
- `--remove-column-property COLUMN:KEY` — repeatable
- `--metadata-revision INTEGER` — optional optimistic concurrency support

Implementation notes:

- Use `PATCH /tables/{id}` for single-table edits.
- Keep batch metadata modification out of the first release.

#### `slcli dataframe delete <table-id>`

Purpose: remove a table and all of its data.

Recommended options:

- `-y, --yes` — skip confirmation

Implementation notes:

- Use `DELETE /tables/{id}` for the initial version.
- Add multi-delete only if we see a real need.

---

## Recommended UX Priorities

### Priority 1: Schema-first discoverability

The first user story to optimize is:

```bash
slcli dataframe schema <table-id>
slcli dataframe get <table-id> -f json
slcli dataframe query <table-id> --take 5 -f json
```

This covers the fastest path to understanding:

- what columns exist
- which one is the index
- what types values must use
- how row data is returned

### Priority 2: Shell-safe advanced querying

Structured filters are powerful but awkward to express inline. The CLI should support both:

```bash
slcli dataframe query <id> \
  --where 'State,EQUALS,FAIL' \
  --where 'Voltage,LESS_THAN,4.8' \
  --columns Time,Voltage,State
```

and:

```bash
slcli dataframe query <id> --request query.json -f json
```

The file-based path is important for maintainability in scripts.

### Priority 3: Honest write semantics

Use `append`, not `write`, and document clearly that existing rows cannot be mutated through this API.

---

## Implementation Plan

### Phase 1: MVP

Deliver the commands that provide immediate schema and scripting value:

1. `slcli dataframe list`
2. `slcli dataframe get`
3. `slcli dataframe schema`
4. `slcli dataframe query`
5. `slcli dataframe export`
6. `slcli dataframe append`

Why this set first:

- it covers discovery, inspection, read access, CSV export, and append workflows
- it avoids spending time on metadata mutation before the data read path is proven useful
- it matches the user's stated priority around understanding table shape

### Phase 2: Full management

Add metadata lifecycle operations:

1. `slcli dataframe create`
2. `slcli dataframe update`
3. `slcli dataframe delete`

### Phase 3: Advanced and optional

Only add after validating demand:

1. `slcli dataframe decimate` backed by `query-decimated-data`
2. Arrow stream import for high-volume append workflows
3. batch metadata operations
4. batch delete

---

## Implementation Notes For This Repository

### File layout

Expected files:

- `slcli/dataframe_click.py`
- `tests/unit/test_dataframe_click.py`

Possible helpers if the command grows beyond one file:

- `slcli/dataframe_utils.py`
- `slcli/cli_formatters.py` additions for schema and row formatting

### Registration

Add `register_dataframe_commands(cli)` in `slcli/main.py`.

### Shared patterns to follow

- Use `handle_api_error()` for all API failures.
- Use `format_success()` for create, update, append, and delete confirmations.
- Use `UniversalResponseHandler` where it fits list responses.
- Reuse workspace resolution helpers so `--workspace` accepts both workspace name and ID.
- Keep `--format table|json` behavior consistent with other command groups.

### Existing useful reference

`slcli/example_provisioner.py` already contains lightweight helper logic for:

- create table
- query table by name
- delete table by name

That code should be treated as a reference for endpoint usage, not copied directly into the CLI implementation.

---

## Testing Plan

### Unit tests

Add focused tests for:

1. `list` building the expected `query-tables` request payload
2. `schema` rendering column definitions correctly
3. `query` translating `--where` and `--order-by` into the expected API request
4. `query --request FILE` passing through raw JSON safely
5. `export` writing CSV output correctly
6. `append` validating input and posting the expected payload
7. `update` building property and column-property patch payloads correctly
8. error handling for not found, invalid filters, and append conflicts

### Validation commands for implementation work

After code changes:

```bash
poetry run ni-python-styleguide lint
poetry run mypy slcli tests
poetry run pytest tests/unit/test_dataframe_click.py -q
poetry run pytest tests/unit -q
poetry run pytest
```

---

## Open Questions

1. Should `query --format table` auto-page through continuation tokens interactively, or only show a single page unless the user passes a follow-up token?
2. Should `append` support CSV input in addition to JSON, or is JSON enough for the first version?
3. Should `list --format json` return the raw API response with `tables` and `continuationToken`, or a flattened array plus token metadata wrapper?
4. Do we want `schema` to accept table name lookup when unique within workspace, or should it stay ID-only initially?

---

## Bottom Line

The right `slcli dataframe` plan is not a generic CRUD surface. It is a **schema-first, table-centric** command group that makes dataframe shape easy to inspect and row data easy to query and export, while exposing row writes accurately as **append-only**.

If we scope the first implementation to `list`, `get`, `schema`, `query`, `export`, and `append`, we will cover the most valuable scripting workflows without over-designing unsupported capabilities.
