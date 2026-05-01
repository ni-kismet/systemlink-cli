---
name: slcli
description: >-
  Query and manage NI SystemLink resources using the slcli command-line interface.
  Covers test results, assets, systems, software states, tags, feeds, files, notebooks,
  dataframe tables,
  routines, work items, work item templates, workflows, test plan templates,
  specifications, products, datasheet-to-specification ingestion (PDF and CSV),
  custom fields, web applications, authorization policies, users, workspaces, and more.
  Use when the user asks about test data analysis, asset management, calibration status,
  system fleet health, operator performance, failure analysis, production metrics,
  equipment utilization, dataframe schema inspection, row export or append workflows,
  software state lifecycle management,
  work order tracking, specification management,
  importing datasheets, creating products from spec sheets,
  or any SystemLink resource operations.
  Supports filtering, aggregation, summary statistics, and JSON output for programmatic processing.
argument-hint: >-
  Describe what you want to do: query test results, inspect a dataframe schema,
  export table rows, import a datasheet, manage saved software states, list assets, manage work items, etc.
compatibility: >-
  Requires slcli installed and authenticated (slcli login). Python 3.10+.
  Requires network access to a SystemLink server instance.
metadata:
  author: ni-kismet
  version: "2.0"
#   --system SYSTEM_ID    Assign a system (by minion/system ID). Repeatable.
#   --fixture ASSET_ID    Assign a fixture/slot (by asset ID, asset type FIXTURE). Repeatable.
#   --dut ASSET_ID        Assign a DUT (by asset ID, asset type DEVICE_UNDER_TEST). Repeatable.
# Use `slcli asset list --asset-type FIXTURE` to find fixture IDs.
# Use `slcli system list` to find system IDs.
# At least one option must be provided; time and resource options can be combined freely.
slcli workitem schedule <WORK_ITEM_ID> \
  [--start ISO8601] [--end ISO8601] [--duration SECONDS] \
  [--assigned-to USER_ID] \
  [--system SYSTEM_ID]... [--fixture ASSET_ID]... [--dut ASSET_ID]...

# Work item template subgroup
slcli workitem template list [-w WORKSPACE] [--filter TEXT] [-t INT] [-f json]
slcli workitem template get <TEMPLATE_ID> [-f json]
slcli workitem template create --name TEXT --type TEXT --template-group TEXT [-w WORKSPACE] [OPTIONS]
slcli workitem template update <TEMPLATE_ID> [--name TEXT] [--description TEXT] [--summary TEXT]
slcli workitem template delete <TEMPLATE_ID>... [--yes]

# Workflow subgroup
slcli workitem workflow list [-w WORKSPACE] [-t INT] [-f json]
slcli workitem workflow get [--id WORKFLOW_ID] [--name NAME] [-f json]
slcli workitem workflow init [--name TEXT] [--directory DIR]   # Scaffold a local workflow file
slcli workitem workflow create --file PATH [-w WORKSPACE]      # Create from JSON file
slcli workitem workflow import --file PATH [-w WORKSPACE]      # Import workflow from JSON
slcli workitem workflow export [--id WORKFLOW_ID] [--name NAME] [-o FILE]  # Export to JSON
slcli workitem workflow update --id WORKFLOW_ID --file PATH    # Update from JSON file
slcli workitem workflow delete --id WORKFLOW_ID [--yes]
slcli workitem workflow preview [--file PATH] [--id WORKFLOW_ID] [--html] [--no-open] [-o FILE]
```

**Create work item options:**

```bash
slcli workitem create \
  --name "Battery Cycle Test" \
  --type testplan \
  --state NEW \
  --part-number "P-BAT-001" \
  --description "Battery capacity test" \
  --assigned-to <user-id> \
  --workflow-id <workflow-id> \
  --workspace Default \
  --format json
```

### workflow — Workflow management

> **Note:** The standalone `slcli workflow` command group has been replaced by
> `slcli workitem workflow`. Use `slcli workitem workflow` for all workflow operations.
> See the **workitem** section above.

### webapp — Web application management

Scaffold, package, and publish custom web applications to SystemLink.

```bash
slcli webapp init <DIRECTORY>                      # Scaffold the Angular starter
slcli webapp manifest init <DIRECTORY> [OPTIONS]  # Create nipkg.config.json for packaging
slcli webapp pack [FOLDER] [--config FILE] [-o OUTPUT_FILE]  # Package a webapp into a .nipkg
slcli webapp list [-w WORKSPACE] [-t INT] [-f json]
slcli webapp get <WEBAPP_ID> [-f json]
slcli webapp publish PATH [--workspace NAME]             # Upload and publish a webapp
slcli webapp delete <WEBAPP_ID>
slcli webapp open <WEBAPP_ID>                            # Open webapp URL in browser
```

### state — Software state management

Create, inspect, import, export, and revert saved software states managed by the SystemLink Systems State service.

```bash
slcli state list [-w WORKSPACE] [--architecture CHOICE] [--distribution CHOICE] [-t INT] [-f json]
slcli state get <STATE_ID> [-f json]
slcli state create --name TEXT --distribution CHOICE --architecture CHOICE [OPTIONS]
slcli state update <STATE_ID> [OPTIONS]
slcli state delete <STATE_ID> [--yes]

slcli state import --name TEXT --distribution CHOICE --architecture CHOICE --file PATH [OPTIONS]
slcli state replace-content <STATE_ID> --file PATH [--change-description TEXT] [-f json]
slcli state export <STATE_ID> [--version VERSION] [--inline | --output FILE]
slcli state capture <SYSTEM_ID> [--inline | --output FILE]

slcli state history <STATE_ID> [-t INT] [-f json]
slcli state version <STATE_ID> <VERSION> [-f json]
slcli state revert <STATE_ID> <VERSION> [--yes]
```

`webapp init` creates the SystemLink Angular starter, not a generic HTML app. The starter installs
project-scoped skills into `.agents/skills/` and creates `PROMPTS.md` plus `START_HERE.md` so an
AI assistant can bootstrap the Angular workspace in place with the same Nimble/SystemLink
conventions described by the `systemlink-webapp` skill.

`webapp manifest init` writes `nipkg.config.json` using the Plugin Manager field names
(`section`, `maintainer`, `homepage`, `xbPlugin`, `slPluginManagerTags`,
`slPluginManagerMinServerVersion`, `iconFile`). `webapp pack --config ...` consumes that
metadata, carries the icon into the package, writes the matching control-file fields into the
generated `.nipkg`, and emits a thin `manifest.json` with `schemaVersion`, `nipkgFile`,
`sha256`, and any configured provenance fields.

### skill — AI skill installation

Install bundled skills for supported AI clients.

```bash
slcli skill install --skill [slcli|systemlink-webapp|systemlink-notebook|all] --client [agents|claude|all] --scope [personal|project|both]
```

Client paths:

- `agents` — personal: `~/.agents/skills/`, project: `.agents/skills/` (most agents)
- `claude` — personal: `~/.claude/skills/`, project: `.claude/skills/`
- `all` — install to both the `agents` and `claude` locations for the selected scope

Notes:

- `agents` is the default client in interactive mode.
- `webapp init` installs project-scoped skills into `.agents/skills/` by default.

### example — Built-in example resource provisioning

Install pre-built demo configurations (systems, assets, DUTs, templates, etc.)
for training, testing, or evaluation.

```bash
slcli example list [-f json]                             # List available examples
slcli example info <EXAMPLE_ID>                          # Show example details
slcli example install <EXAMPLE_ID> [--workspace NAME]    # Provision example resources
slcli example delete <EXAMPLE_ID> [--workspace NAME]     # Remove provisioned resources
```

## Reference docs

Consult these for detailed guidance. Load only what you need for the current task.

| Topic                       | File                                                        | When to load                                                  |
| --------------------------- | ----------------------------------------------------------- | ------------------------------------------------------------- |
| CLI command reference       | [commands.md](./references/commands.md)                     | Looking up command syntax, options, or examples               |
| Datasheet-to-specs workflow | [datasheet-workflow.md](./references/datasheet-workflow.md) | Importing specs from PDF, CSV, or structured text             |
| Filtering guide             | [filtering.md](./references/filtering.md)                   | Advanced LINQ expressions, parameterized queries              |
| Analysis recipes            | [analysis-recipes.md](./references/analysis-recipes.md)     | Multi-step analysis: yield, calibration, operator performance |
| Troubleshooting             | [troubleshooting.md](./references/troubleshooting.md)       | Workspace ID issues, SSL errors, encoding, PowerShell quoting |

## Platform availability

Not all command groups are available on every SystemLink server. Some services exist only on
SystemLink Enterprise (SLE) or require a specific microservice to be deployed.

**Check what's available on your server:**

```bash
slcli info                # Shows platform type and service health
slcli info -f json        # Machine-readable; check .services for per-service status
```

| Command group                | Required service     | SLE | SLS | Notes                                   |
| ---------------------------- | -------------------- | --- | --- | --------------------------------------- |
| `dataframe`                  | DataFrame            | ✓   | ✗   | Table row storage                       |
| `comment`                    | Comments             | ✓   | ✗   | Resource annotations                    |
| `template`                   | Work Order           | ✓   | ✗   | Test plan configuration templates       |
| `workitem template`          | Work Order           | ✓   | ✗   | Work item template CRUD                 |
| `workitem workflow`          | Work Order           | ✓   | ✗   | Workflow lifecycle                       |
| `customfield`                | Dynamic Form Fields  | ✓   | ✗   | Custom metadata fields                  |
| `notebook`                   | Notebook             | ✓   | ✗   | Jupyter execution                       |
| `routine` (v2)               | Routine v2           | ✓   | ✗   | Event-action routines                   |
| `testmonitor`, `asset`, etc. | Core services        | ✓   | ✓   | Available on both platforms             |

When a gated command is run on a server that lacks the required service, the CLI exits with
code 2 and a message like:

```
✗ Error: DataFrames is not available on SystemLink Server.
  This feature requires the DataFrame service.
```

Service probe results are cached for 5 minutes across CLI invocations. Running `slcli info`
force-refreshes and persists the latest snapshot. Set `SLCLI_SERVICE_PROBE_CACHE_TTL_SECONDS=0`
to disable caching for debugging.

## Command groups at a glance

| Group         | Purpose                 | Key subcommands                                      |
| ------------- | ----------------------- | ---------------------------------------------------- |
| `testmonitor` | Test results & products | `result list/get`, `product list/create/update`      |
| `spec`        | Specifications          | `list`, `query`, `get`, `create`, `import`, `export` |
| `asset`       | Assets & calibration    | `list`, `get`, `summary`, `calibration`              |
| `system`      | System fleet            | `list`, `get`, `compare`, `summary`, `job`           |
| `state`       | Software states         | `list`, `get`, `create`, `update`, `delete`, `import`, `replace-content`, `export`, `capture`, `history`, `version`, `revert` |
| `dataframe`   | DataFrame tables        | `list`, `schema`, `query`, `export`, `append`        |
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
