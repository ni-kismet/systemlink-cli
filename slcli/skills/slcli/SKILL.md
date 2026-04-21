---
name: slcli
description: >-
  Query and manage NI SystemLink resources using the slcli command-line interface.
  Covers test results, assets, systems, tags, feeds, files, notebooks,
  routines, work items, work item templates, workflows, test plan templates,
  specifications, products, datasheet-to-specification ingestion (PDF and CSV),
  custom fields, web applications, authorization policies, users, workspaces, and more.
  Use when the user asks about test data analysis, asset management, calibration status,
  system fleet health, operator performance, failure analysis, production metrics,
  equipment utilization, work order tracking, specification management,
  importing datasheets, creating products from spec sheets,
  or any SystemLink resource operations.
  Supports filtering, aggregation, summary statistics, and JSON output for programmatic processing.
argument-hint: >-
  Describe what you want to do: query test results, import a datasheet,
  list assets, manage work items, etc.
compatibility: >-
  Requires slcli installed and authenticated (slcli login). Python 3.10+.
  Requires network access to a SystemLink server instance.
metadata:
  author: ni-kismet
  version: "2.0"
---

# SystemLink CLI (slcli)

## Quick start

```bash
# check current connection
slcli info

# list test results (table output, paginated)
slcli testmonitor result list --take 25

# list test results (JSON output, all results)
slcli testmonitor result list --take 100 -f json

# summarize test results by status
slcli testmonitor result list --summary --group-by status -f json

# list assets needing calibration
slcli asset list --calibration-status PAST_RECOMMENDED_DUE_DATE

# list connected systems
slcli system list --state CONNECTED

# list work items
slcli workitem list -f json -t 25

# create a work item
slcli workitem create --name "Battery Cycle Test" --type testplan --state NEW --part-number "P-001" -w Default

# register the MCP server for VS Code Copilot Agent mode
slcli mcp install

# run the MCP server over streamable HTTP for local inspector testing
slcli mcp serve --transport streamable-http
```

## Output formats

All list and get commands support `-f, --format` with `table` (default) or `json`.

- **Table**: Paginated (default 25 rows), human-readable with box-drawing.
- **JSON**: Returns all matching results as a JSON array — ideal for piping to `jq`.

Always use `-f json` when you need to process, filter, or aggregate output programmatically.

## Reference docs

Consult these for detailed guidance. Load only what you need for the current task.

| Topic                       | File                                                        | When to load                                                  |
| --------------------------- | ----------------------------------------------------------- | ------------------------------------------------------------- |
| CLI command reference       | [commands.md](./references/commands.md)                     | Looking up command syntax, options, or examples               |
| Datasheet-to-specs workflow | [datasheet-workflow.md](./references/datasheet-workflow.md) | Importing specs from PDF, CSV, or structured text             |
| Filtering guide             | [filtering.md](./references/filtering.md)                   | Advanced LINQ expressions, parameterized queries              |
| Analysis recipes            | [analysis-recipes.md](./references/analysis-recipes.md)     | Multi-step analysis: yield, calibration, operator performance |
| Troubleshooting             | [troubleshooting.md](./references/troubleshooting.md)       | Workspace ID issues, SSL errors, encoding, PowerShell quoting |

## Command groups at a glance

| Group         | Purpose                 | Key subcommands                                      |
| ------------- | ----------------------- | ---------------------------------------------------- |
| `testmonitor` | Test results & products | `result list/get`, `product list/create/update`      |
| `spec`        | Specifications          | `list`, `query`, `get`, `create`, `import`, `export` |
| `asset`       | Assets & calibration    | `list`, `get`, `summary`, `calibration`              |
| `system`      | System fleet            | `list`, `get`, `compare`, `summary`, `job`           |
| `tag`         | Tag read/write          | `list`, `get-value`, `set-value`, `create`           |
| `routine`     | Event-action routines   | `list`, `create`, `enable/disable` (v1 + v2)         |
| `comment`     | Resource comments       | `list`, `add`, `update`, `delete`                    |
| `workitem`    | Work items & workflows  | `list`, `create`, `schedule`, `template`, `workflow` |
| `file`        | File management         | `list`, `upload`, `download`, `query`, `watch`       |
| `notebook`    | Jupyter notebooks       | `manage list/create`, `execute start/sync`           |
| `feed`        | Package feeds           | `list`, `create`, `package upload`                   |
| `customfield` | Dynamic form fields     | `list`, `create`, `export`, `edit`                   |
| `template`    | Test plan templates     | `list`, `import`, `export`                           |
| `webapp`      | Web applications        | `init`, `pack`, `publish`, `list`                    |
| `config`      | Connection profiles     | `list`, `use`, `add`, `delete`                       |
| `user`        | User management         | `list`, `get`, `create`, `update`                    |
| `auth`        | Authorization policies  | `policy list/create`, `template list`                |
| `workspace`   | Workspaces              | `list`, `get`                                        |
| `skill`       | AI skill installation   | `install`                                            |
| `example`     | Demo provisioning       | `list`, `install`, `delete`                          |
## Key rules

1. **Always use `-f json`** when piping output to `jq` or doing programmatic analysis.
2. **Use `--summary --group-by`** for aggregation instead of fetching all records and counting.
3. **Use convenience filters first** (e.g., `--status FAILED`), fall back to `--filter` for complex queries.
4. **Parameterize `--filter` queries** — use `--substitution` instead of string interpolation.
5. **Combine filters** — convenience filters are ANDed together automatically.
6. **Use `--take`** to control result volume; JSON returns all matching up to `--take`.
7. **Status enum values**: `PASSED`, `FAILED`, `RUNNING`, `ERRORED`, `TERMINATED`, `TIMEDOUT`, `WAITING`, `SKIPPED`, `CUSTOM`.
8. **Exit codes**: 0 = success, 1 = general error, 2 = invalid input, 3 = not found, 4 = permission denied, 5 = network error.
9. **Prefer workspace IDs** (UUIDs) over names in scripted workflows — some endpoints reject names.
10. **Use `make_api_request`** from `slcli.utils` for helper scripts — handles auth, SSL, and errors.
