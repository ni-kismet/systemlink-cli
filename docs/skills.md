# slcli skills

## Summary

`slcli` is the SystemLink command-line interface for managing SystemLink
resources. It provides authentication, configuration, workspace selection, CRUD
operations across multiple services, and local-to-remote workflows (init, pack,
publish, import/export).

## Global usage

- **Command shape:** `slcli [OPTIONS] COMMAND [ARGS]...`
- **Global options:**
  - `-v, --version` — Show version and exit
  - `-p, --profile TEXT` — Use a specific profile for this command
  - `-h, --help` — Show help
- **Profiles:** Set up multiple environments and switch between them using
  `slcli config` and `slcli login`.

## Capabilities by command group

### asset

Manage SystemLink assets (hardware tracked by Asset Management service).

- **Filtering**: Supports Asset API expression language (e.g.,
  `ModelName.Contains("PXI")`, `BusType = "PCI_PXI"`)
- **Operations**: create, delete, get, list, update
- **calibration**: Get calibration history for a specific asset
- **location-history**: Get location/connection history for a specific asset
- **summary**: Show fleet-wide asset summary statistics

### auth

Manage authorization policies and policy templates.

- **policy**: create, delete, diff, get, list, update
- **template**: delete, get, list

### completion

Generate or install shell completion scripts.

- Supports: bash, zsh, fish, powershell
- Can install directly into shell config or output to a file

### config

Manage slcli configuration and profiles.

- current-profile, list-profiles, use-profile
- view configuration
- delete-profile
- migrate credentials from keyring

### customfield

Manage DFF (custom field) configurations.

- init, create, update, delete
- list, get, export
- edit with a local web editor

### example

Provision or remove example resource configurations.

- list, info
- install (provision example resources)
- delete (cleanup in reverse order)

### feed

Manage NI Package Manager feeds and their packages.

- Supports Windows (.nipkg) and NI Linux RT (.ipk/.deb) platforms
- **feed**: create, delete, get, list, replicate
- **package**: upload, list, delete

### file

Manage files in SystemLink File Service.

- upload, download, get, list, delete
- update-metadata
- query for files
- watch a folder for auto-upload

### info

Show current configuration and detected platform.

- output format: `table` or `json`

### login / logout

Manage credentials and profiles.

- login: set profile, url, api key, web url, default workspace
- logout: remove current or specific profile, or all profiles

### notebook

Manage notebooks locally and remotely, and run executions.

- init: create a local notebook skeleton
- manage: create, update, delete, list, get, download, set-interface
- execute: start, sync, list, get, cancel, retry (SLE only)

### system

Manage SystemLink systems (registered with Systems Management service).

- **Filtering**: Supports Systems Management filter language (e.g.,
  `alias.Contains("PXI")`, `connected.data.state = "CONNECTED"`)
- **Operations**: get, list, remove, update
- **job**: Manage system jobs (cancel, get, list, summary)
- **report**: Generate software or hardware reports for systems
- **summary**: Show fleet-wide system summary

### tag

Manage SystemLink tags.

- **Operations**: create, delete, get, list, update
- **Value operations**: get-value, set-value
- Supports filtering when listing tags

### template

Manage test plan templates.

- init scaffold
- import/export
- list, get, delete

### testmonitor

Manage test monitor products and results.

- **product**: get, list
- **result**: get, list

### user

Manage SystemLink users and service accounts.

- create, update, delete
- get, list

### webapp

Manage web applications locally and remotely.

- init scaffold
- pack a folder into a .nipkg
- publish a .nipkg or folder
- list, get, open, delete

### workflow

Manage workflows.

- init scaffold
- import/export
- update
- list, get, delete
- preview workflow file

### workspace

Manage workspaces.

- list, get, disable

## Common patterns

### Profile-based targeting

- Use `--profile` to run commands against a specific SystemLink environment.
- Use `slcli config use-profile` to switch the active profile.

### CRUD consistency

Most resource groups expose a consistent shape:

- **Create:** `create`
- **Read:** `get`, `list`
- **Update:** `update`
- **Delete:** `delete`

### Scaffold → import/publish

Several groups support a local-first workflow:

- **init** creates a local scaffold (workflow, template, webapp, notebook).
- **import/publish/update** pushes local artifacts to SystemLink.
- **export** pulls remote artifacts to local JSON files.

### Execution vs. management

For notebooks, resource management is separated from execution:

- **manage**: CRUD and metadata/interface operations
- **execute**: run, list, cancel, retry

### Output formatting

Where supported (e.g., `info`), use `--format json` for script-friendly output.

### Filtering and querying

Many list commands support both convenience filters and advanced filter
expressions.

#### Asset filtering (`slcli asset list`)

**Convenience filters** (combine with `and`):

- `--model TEXT` — Filter by model name (contains match)
- `--serial-number TEXT` — Filter by serial number (exact match)
- `--bus-type [BUILT_IN_SYSTEM|PCI_PXI|USB|GPIB|VXI|SERIAL|TCP_IP|CRIO]` —
  Filter by bus type
- `--asset-type [GENERIC|DEVICE_UNDER_TEST|FIXTURE|SYSTEM]` — Filter by asset
  type
- `--calibration-status [OK|APPROACHING_RECOMMENDED_DUE_DATE|PAST_RECOMMENDED_DUE_DATE|OUT_FOR_CALIBRATION]`
- `--connected` — Show only assets in connected systems (CONNECTED + PRESENT)
- `--calibratable` — Show only calibratable assets
- `--workspace TEXT` — Filter by workspace name or ID

**Advanced filter syntax** (use with `--filter`):

- Property access: `ModelName`, `SerialNumber`, `BusType`
- String operations: `.Contains("text")`, `= "exact"`
- Logical operators: `and`, `or`
- Examples:
  - `ModelName.Contains("PXI") and BusType = "PCI_PXI"`
  - `SerialNumber = "01BB877A"`
  - `CalibrationStatus = "OK" and ModelName.Contains("407")`

#### System filtering (`slcli system list`)

**Convenience filters** (combine with `and`):

- `--alias TEXT` — Filter by system alias (contains match)
- `--state [CONNECTED|DISCONNECTED|VIRTUAL|APPROVED|...]` — Filter by connection
  state
- `--os TEXT` — Filter by OS (kernel contains match)
- `--host TEXT` — Filter by hostname (contains match)
- `--has-package TEXT` — Filter for systems with specified package installed
  (contains match, client-side)
- `--has-keyword TEXT` — Filter systems that have this keyword (repeatable)
- `--property TEXT` — Filter by property key=value (repeatable)
- `--workspace TEXT` — Filter by workspace name or ID

**Advanced filter syntax** (use with `--filter`):

- Nested property access: `connected.data.state`, `grains.data.kernel`
- String operations: `.Contains("text")`, `= "exact"`
- Logical operators: `and`, `or`
- Examples:
  - `connected.data.state = "CONNECTED" and grains.data.kernel = "Windows"`
  - `alias.Contains("PXI")`
  - `connected.data.state = "CONNECTED" and grains.data.os = "Windows 10"`

#### Test Monitor filtering (`slcli testmonitor result list`, `slcli testmonitor product list`)

**Result convenience filters**:

- `--status TEXT` — Filter by status type (e.g., PASSED, FAILED)
- `--program-name TEXT` — Filter by program name (contains)
- `--serial-number TEXT` — Filter by serial number (contains)
- `--part-number TEXT` — Filter by part number (contains)
- `--operator TEXT` — Filter by operator name (contains)
- `--host-name TEXT` — Filter by host name (contains)
- `--system-id TEXT` — Filter by system ID
- `--workspace TEXT` — Filter by workspace name or ID

**Product convenience filters**:

- `--name TEXT` — Filter by product name (contains)
- `--part-number TEXT` — Filter by product part number (contains)
- `--family TEXT` — Filter by product family (contains)
- `--workspace TEXT` — Filter by workspace name or ID

**Advanced filter syntax** (use with `--filter`):

- Uses Dynamic LINQ filter expressions
- Supports `--substitution TEXT` for parameterized queries (repeatable)
- For results: `--product-filter TEXT` with `--product-substitution TEXT` to
  filter by associated product properties
- Examples:
  - `status.statusType = "FAILED"`
  - `partNumber.Contains("ABC") and programName = "TestProgram"`
  - `startedAt > DateTime(2026, 1, 1)`

#### Common filtering features

- **Order by**: Most list commands support `--order-by` with field-specific
  options
- **Sort direction**: Use `--descending` or `--ascending` (default varies by
  command)
- **Pagination**: `--take INTEGER` controls items per page (table output only)
- **Output format**: `-f, --format [table|json]` for structured output
- **Summary mode**: Many commands support `--summary` for aggregate statistics
- **Group by**: Test monitor results support `--group-by` for grouping summary
  statistics

## Example workflows

### Multi-environment setup

1. `slcli login --profile dev --url <dev-url> --api-key <key>`
2. `slcli login --profile prod --url <prod-url> --api-key <key>`
3. `slcli config use-profile dev`

### Asset management

- `slcli asset list --filter 'ModelName.Contains("PXI")'` — Find all PXI assets
- `slcli asset list --model "4071" --connected` — Find connected DMM assets
- `slcli asset list --calibration-status PAST_RECOMMENDED_DUE_DATE` — Assets
  needing calibration
- `slcli asset list --filter 'BusType = "PCI_PXI" and CalibrationStatus = "OK"'`
  — PXI assets with valid calibration
- `slcli asset calibration <asset-id>` — View calibration history
- `slcli asset location-history <asset-id>` — Track where an asset has been
- `slcli asset summary` — Get fleet-wide statistics

### System management

- `slcli system list --state CONNECTED` — List connected systems
- `slcli system list --filter 'connected.data.state = "CONNECTED" and grains.data.kernel = "Windows"'`
  — Connected Windows systems
- `slcli system list --has-package "DAQmx"` — Systems with DAQmx installed
- `slcli system list --alias "PXI" --os "Windows 10"` — Windows 10 PXI systems
- `slcli system get <system-id>` — View detailed system information
- `slcli system job list` — View all system jobs
- `slcli system report --type SOFTWARE --output report.csv` — Generate software
  inventory report
- `slcli system summary` — Show fleet-wide system statistics

### Test result analysis

- `slcli testmonitor result list --status FAILED --part-number "ABC123"` —
  Failed tests for specific part
- `slcli testmonitor result list --filter 'status.statusType = "FAILED" and startedAt > DateTime(2026, 1, 1)'`
  — Recent failures
- `slcli testmonitor result list --program-name "Overvoltage" --serial-number "1234567"`
  — Specific test on specific DUT
- `slcli testmonitor result list --summary --group-by status` — Summary
  statistics by status
- `slcli testmonitor result get <result-id>` — Get detailed result information
- `slcli testmonitor product list --family "Sensors"` — List products in a
  family
- `slcli testmonitor product list --part-number "ABC" --summary` — Product
  summary statistics
- `slcli testmonitor product get <product-id>` — Get product details

### Tag operations

- `slcli tag list` — List all tags
- `slcli tag get-value <tag-path>` — Read current tag value
- `slcli tag set-value <tag-path> <value>` — Write a value to a tag
- `slcli tag create --path <path> --data-type <type>` — Create a new tag

### Template and workflow lifecycle

- `slcli template init` → edit JSON → `slcli template import`
- `slcli workflow init` → edit JSON → `slcli workflow import`
- `slcli workflow preview` for validation before update

### Notebook execution

- `slcli notebook manage create ...`
- `slcli notebook execute start ...` or `slcli notebook execute sync ...`
- `slcli notebook execute list/get/cancel` to manage runs

### Web app deployment

- `slcli webapp init` → edit `index.html`
- `slcli webapp pack` → `slcli webapp publish`

### Feed and package management

- `slcli feed list` — List all feeds
- `slcli feed create --name <name>` — Create a new feed
- `slcli feed package upload --feed-id <id> --file <package.nipkg>` — Upload
  package to feed
- `slcli feed replicate --url <external-url>` — Replicate from external source
