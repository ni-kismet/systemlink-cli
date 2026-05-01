# CLI Command Reference

Complete option reference for all `slcli` command groups.

## testmonitor — Test data analysis

The primary command group for test result queries and product analysis.

```bash
# List results with filters
slcli testmonitor result list [OPTIONS]

# Convenience filters (combine freely)
  --status TEXT              # PASSED, FAILED, RUNNING, ERRORED, TERMINATED, TIMEDOUT, etc.
  --program-name TEXT        # Filter by test program name (contains)
  --serial-number TEXT       # Filter by DUT serial number (contains)
  --part-number TEXT         # Filter by part number (contains)
  --operator TEXT            # Filter by operator name (contains)
  --host-name TEXT           # Filter by test host (contains)
  --system-id TEXT           # Filter by system ID (exact)
  --workspace, -w TEXT       # Filter by workspace name or ID

# Advanced filtering
  --filter TEXT              # Dynamic LINQ expression
  --substitution TEXT        # Parameterized value for --filter (repeatable)
  --product-filter TEXT      # LINQ filter on associated products
  --product-substitution TEXT # Parameterized value for --product-filter (repeatable)

# Sorting
  --order-by CHOICE          # ID, STARTED_AT, UPDATED_AT, PROGRAM_NAME, SYSTEM_ID,
                             # HOST_NAME, OPERATOR, SERIAL_NUMBER, PART_NUMBER,
                             # TOTAL_TIME_IN_SECONDS, PROPERTIES
  --descending / --ascending # Default: descending

# Aggregation
  --summary                  # Show summary statistics instead of individual results
  --group-by CHOICE          # status, programName, serialNumber, operator, hostName, systemId

# Pagination & output
  --take, -t INTEGER         # Items per page (default 25)
  --format, -f [table|json]  # Output format (default: table)

# Get a single result
slcli testmonitor result get <RESULT_ID> [--include-steps] [-f json]

# List products
slcli testmonitor product list [OPTIONS]
  --name TEXT                # Filter by product name (contains)
  --part-number TEXT         # Filter by part number (contains)
  --family TEXT              # Filter by product family (contains)
  --workspace, -w TEXT       # Filter by workspace name or ID
  --summary                  # Show summary statistics
  --take, -t INTEGER         # Items per page (default 25)
  -f [table|json]

# Get a single product
slcli testmonitor product get <PRODUCT_ID> [-f json]

# Create a product
slcli testmonitor product create --part-number TEXT [OPTIONS]
  --part-number TEXT         # Part number (required)
  --name TEXT                # Product name
  --family TEXT              # Product family
  --workspace, -w TEXT       # Workspace name or ID
  --keyword TEXT             # Keyword (repeatable)
  --property KEY=VALUE       # Key-value property (repeatable)
  -f [table|json]

# Update a product
slcli testmonitor product update <PRODUCT_ID> [OPTIONS]
  --name TEXT                # New product name
  --family TEXT              # New product family
  --workspace, -w TEXT       # New workspace name or ID
  --keyword TEXT             # Keyword (repeatable; replaces all if --replace)
  --property KEY=VALUE       # Key-value property (repeatable; replaces all if --replace)
  --replace                  # Replace fields instead of merging
  -f [table|json]

# Delete products
slcli testmonitor product delete [--yes] <PRODUCT_ID>...
  --yes, -y                  # Skip confirmation prompt
```

## spec — Specification management

```bash
# List specs for a product (accepts name, part number, or ID)
slcli spec list --product <PRODUCT> -f json

# Create a spec; when --workspace is omitted, the CLI inherits the product workspace
slcli spec create --product <PRODUCT> --spec-id VSAT01 --type PARAMETRIC \
  --name "Saturation voltage" --limit-min 1.2 --limit-max 1.8

# Bulk import create-compatible specs from JSON
slcli spec import --file docs/examples/specifications/import-specs.json

# Export reusable create-compatible fields
slcli spec export --product <PRODUCT> --include-limits --include-conditions \
  --projection PRODUCT_ID --projection SPEC_ID --projection NAME --projection CATEGORY \
  --projection TYPE --projection SYMBOL --projection BLOCK --projection UNIT --output specs.json
```

## asset — Asset and calibration management

```bash
# List assets with filters
slcli asset list [OPTIONS]

# Convenience filters
  --model TEXT               # Filter by model name (contains)
  --serial-number TEXT       # Filter by serial number (exact)
  --bus-type CHOICE          # BUILT_IN_SYSTEM, PCI_PXI, USB, GPIB, VXI, SERIAL, TCP_IP, CRIO
  --asset-type CHOICE        # GENERIC, DEVICE_UNDER_TEST, FIXTURE, SYSTEM
                             # FIXTURE assets are also called "slots" in scheduling context:
                             #   a slot/fixture is a physical test station, chamber, rack, etc.
                             #   that a work item is scheduled to run on.
                             # DEVICE_UNDER_TEST (DUT) assets are the units being tested.
                             # SYSTEM assets are registered SystemLink-managed systems.
  --calibration-status CHOICE # OK, APPROACHING_RECOMMENDED_DUE_DATE,
                              # PAST_RECOMMENDED_DUE_DATE, OUT_FOR_CALIBRATION
  --connected                # Only assets in connected systems
  --calibratable             # Only calibratable assets
  --workspace, -w TEXT       # Filter by workspace name or ID

# Advanced filtering
  --filter TEXT              # Asset API expression (e.g., 'ModelName.Contains("PXI")')

# Sorting & output
  --order-by CHOICE          # Sort field
  --descending / --ascending
  --take, -t INTEGER         # Default 25
  -f [table|json]

# Other asset commands
slcli asset get <ASSET_ID> [-f json]
slcli asset summary [-f json]                       # Fleet-wide statistics
slcli asset calibration <ASSET_ID> [-f json]        # Calibration history
slcli asset location-history <ASSET_ID> [-f json]   # Location/connection history
slcli asset create --model-name TEXT [OPTIONS]       # Create an asset
slcli asset update <ASSET_ID> [OPTIONS]              # Update an asset
slcli asset delete <ASSET_ID>                        # Delete an asset
```

## system — System fleet management

```bash
# List systems with filters
slcli system list [OPTIONS]

# Convenience filters
  --alias, -a TEXT           # Filter by alias (contains)
  --state CHOICE             # CONNECTED, DISCONNECTED, VIRTUAL, APPROVED, etc.
  --os TEXT                  # Filter by OS/kernel (contains)
  --host TEXT                # Filter by hostname (contains)
  --has-package TEXT         # Systems with installed package (contains, client-side)
  --has-keyword TEXT         # Systems with keyword (repeatable)
  --property TEXT            # Property key=value filter (repeatable)
  --workspace, -w TEXT       # Filter by workspace name or ID

# Advanced filtering
  --filter TEXT              # Systems Management filter expression

# JSON schema selection
  --field CHOICE             # JSON-only; add extended JSON fields (repeatable, use with -f json, forces legacy query path)
  --all-fields               # JSON-only; restore the full legacy JSON schema (use with -f json)

# Performance note
  # `slcli system list -f json` returns a slim schema by default:
  # id, alias, workspace, connected, host, kernel
  # `--field` and `--all-fields` are JSON-only and should be used with `-f json`.
  # Use `--field packages` or `--all-fields` when you need the extended legacy schema.
                             # e.g., 'connected.data.state = "CONNECTED"'

# Output
  --take, -t INTEGER         # Default 100
  -f [table|json]

# Get detailed information about a single system
slcli system get <SYSTEM_ID> [-f json]

# Include related resources from other services (fetched in parallel):
slcli system get <SYSTEM_ID> --include-assets       # Assets (niapm/v1)
slcli system get <SYSTEM_ID> --include-alarms       # Active alarm instances
slcli system get <SYSTEM_ID> --include-jobs         # Recent jobs
slcli system get <SYSTEM_ID> --include-results      # Test results (nitestmonitor/v2)
slcli system get <SYSTEM_ID> --include-workitems    # Scheduled test plan work items

# Convenience shorthand: enables all sections including packages and feeds
slcli system get <SYSTEM_ID> --include-all

# Options that apply to --include-* sections:
#   --take/-t INTEGER      Max rows per section (default: 10)
#   --workitem-days INT    Time window ±days for work items query (default: 30)

# JSON output embeds related resources under _assets, _alarms, _jobs, etc.
slcli system get <SYSTEM_ID> --include-all -f json  | jq '._results.items'

slcli system summary [-f json]                      # Fleet-wide statistics
slcli system report --type [SOFTWARE|HARDWARE] -o FILE  # Generate CSV report
slcli system update <SYSTEM_ID> [OPTIONS]            # Update system metadata
slcli system remove <SYSTEM_ID>                      # Remove a system

# Compare two systems (by ID or alias)
slcli system compare <SYSTEM_A> <SYSTEM_B> [-f json]
# Compares installed software (packages, versions) and connected assets
# (model, vendor, slot number). Accepts system IDs or alias names.
# Output sections:
#   Software: packages unique to each system, version differences
#   Assets:   assets unique to each system, count mismatches, slot differences
# Assets are matched by (modelName, vendorName) identity.

# System jobs
slcli system job list [OPTIONS]
slcli system job get <JOB_ID>
slcli system job summary [-f json]
slcli system job cancel <JOB_ID>
```

## state — Software state management

```bash
# List saved states
slcli state list [OPTIONS]

  --workspace, -w TEXT       # Filter by workspace name or ID
  --architecture CHOICE      # ARM, X64, X86, ANY
  --distribution CHOICE      # NI_LINUXRT, NI_LINUXRT_NXG, WINDOWS, ANY
  --take, -t INTEGER         # Default 25
  -f [table|json]

# Get state details
slcli state get <STATE_ID> [-f json]

# Create or update a package/feed-defined state
slcli state create --name TEXT --distribution CHOICE --architecture CHOICE [OPTIONS]
  --workspace, -w TEXT
  --property KEY=VALUE       # Repeatable custom property
  --feed JSON_OR_@FILE       # Repeatable feed object
  --package JSON_OR_@FILE    # Repeatable package object
  --system-image JSON_OR_@FILE
  --request FILE             # Raw JSON request override
  -f [table|json]

slcli state update <STATE_ID> [OPTIONS]
  --name TEXT
  --description TEXT
  --distribution CHOICE
  --architecture CHOICE
  --workspace, -w TEXT
  --property KEY=VALUE       # Replaces properties when provided
  --request FILE             # Raw JSON patch override
  -f [table|json]

# Destructive operations
slcli state delete <STATE_ID> [--yes]
slcli state revert <STATE_ID> <VERSION> [--yes]

# SLS file workflows
slcli state import --name TEXT --distribution CHOICE --architecture CHOICE --file PATH [OPTIONS]
slcli state replace-content <STATE_ID> --file PATH [--change-description TEXT] [-f json]
slcli state export <STATE_ID> [--version VERSION] [--inline | --output FILE]
slcli state capture <SYSTEM_ID> [--inline | --output FILE]

# Version history
slcli state history <STATE_ID> [-t INT] [-f json]
slcli state version <STATE_ID> <VERSION> [-f json]
```

## dataframe — DataFrame tables and row access

> **Requires:** DataFrame service (SLE only). Check `slcli info` for availability.

```bash
# List tables with metadata filters
slcli dataframe list [OPTIONS]

  --name TEXT                # Filter by table name (contains)
  --workspace, -w TEXT       # Filter by workspace name or ID
  --test-result-id TEXT      # Filter by associated test result ID
  --supports-append / --no-supports-append
  --filter TEXT              # Dynamic LINQ table filter
  --substitution TEXT        # Parameterized value for --filter (repeatable)
  --order-by CHOICE          # CREATED_AT, METADATA_MODIFIED_AT, NAME,
                             # NUMBER_OF_ROWS, ROWS_MODIFIED_AT
  --descending / --ascending
  --take, -t INTEGER         # Default 25
  -f [table|json]

# Inspect a single table and its schema
slcli dataframe get <TABLE_ID> [-f json]
slcli dataframe schema <TABLE_ID> [--properties] [-f json]

# Query row data
slcli dataframe query <TABLE_ID> [OPTIONS]
  --columns TEXT             # Comma-separated column list
  --where TEXT               # column,operation,value (repeatable)
  --order-by TEXT            # column[:asc|desc] (repeatable)
  --take, -t INTEGER         # Default 100
  --continuation-token TEXT  # Resume a paged read
  --request FILE             # Raw query-data request JSON
  -f [table|json]

# Query decimated rows for plotting or large series
slcli dataframe decimate <TABLE_ID> [OPTIONS]
  --columns TEXT
  --where TEXT
  --x-column TEXT
  --y-column TEXT            # Repeatable
  --intervals INTEGER        # Default 1000
  --method [LOSSY|MAX_MIN|ENTRY_EXIT]
  --distribution [EQUAL_FREQUENCY|EQUAL_WIDTH]
  --request FILE
  -f [table|json]

# Export or append rows
slcli dataframe export <TABLE_ID> [OPTIONS]
  --columns TEXT
  --where TEXT
  --order-by TEXT
  --take INTEGER
  --request FILE
  --output, -o FILE          # Write CSV to a file

slcli dataframe append <TABLE_ID> --input FILE [--input-format json|arrow] [--end-of-data]

# Manage table metadata
slcli dataframe create --definition FILE [--name TEXT] [--workspace TEXT] [-f json]
slcli dataframe update <TABLE_ID> [OPTIONS]
  --name TEXT
  --workspace, -w TEXT
  --test-result-id TEXT
  --property KEY=VALUE                # Repeatable
  --remove-property KEY               # Repeatable
  --column-property COLUMN:KEY=VALUE  # Repeatable
  --remove-column-property COLUMN:KEY # Repeatable
  --metadata-revision INTEGER

slcli dataframe update-many --definition FILE
slcli dataframe delete <TABLE_ID>... [--yes]
```

## tag — Tag operations

```bash
slcli tag list [OPTIONS]                            # List tags (filter by path glob, workspace)
slcli tag get <TAG_PATH> [-f json]                  # Get tag metadata
slcli tag get-value <TAG_PATH>                      # Read current tag value
slcli tag set-value <TAG_PATH> <VALUE>              # Write a tag value
slcli tag create --path <PATH> --data-type <TYPE>   # Create a new tag
slcli tag update <TAG_PATH> [OPTIONS]               # Update tag metadata
slcli tag delete <TAG_PATH>                         # Delete a tag
```

## routine — Event-action and notebook routine management

Two API versions are supported:

- **v2** (default): General event-action routines — monitor tags, work-item changes, and more; trigger alarms, emails, or notebook executions.
- **v1**: Notebook-execution routines with SCHEDULED or TRIGGERED types.

```bash
# List routines
slcli routine list [OPTIONS]

  --api-version [v1|v2]          API version (default: v2)
  --enabled                      Show only enabled routines
  --disabled                     Show only disabled routines
  --workspace, -w TEXT           Filter by workspace name or ID
  --filter TEXT                  Filter by routine name (case-insensitive substring)
  --event-type TEXT              Filter by event type (v2 only, e.g. TAG, WORKITEMCHANGED)
  --type [TRIGGERED|SCHEDULED]   Filter by routine type (v1 only)
  --take, -t INTEGER             Items per page / max results (default: 25)
  -f [table|json]                Output format (default: table)

# Get a single routine by ID
slcli routine get <ROUTINE_ID> [--api-version v1|v2] [-f json]

# Create a v2 event-action routine
# --event: JSON object with `type` and `triggers` array
# --actions: JSON array of action objects
slcli routine create \
  --name "My Routine" \
  --description "Description" \
  --workspace <WORKSPACE_ID> \
  --enabled \
  --event   '<event-json>' \
  --actions '<actions-json>'

# Create a v1 notebook routine (SCHEDULED)
# IMPORTANT: startTime must be in the future (UTC). The API rejects past start times.
# Use ISO-8601 UTC format (e.g. 2026-03-03T09:00:00Z). Since the server operates in UTC,
# verify the current UTC time first if in doubt: date -u
slcli routine create --api-version v1 \
  --name "Daily Notebook" \
  --type SCHEDULED \
  --notebook-id <NOTEBOOK_ID> \
  --schedule '{"startTime":"2026-01-01T00:00:00Z","repeat":"DAY"}'

# Create a v1 notebook routine (TRIGGERED by file)
slcli routine create --api-version v1 \
  --name "On Upload" \
  --type TRIGGERED \
  --notebook-id <NOTEBOOK_ID> \
  --trigger '{"source":"FILES","events":["CREATED"],"filter":"extension=\".csv\""}'

# Update a routine (only supplied fields are changed)
slcli routine update <ROUTINE_ID> [--api-version v1|v2] \
  [--name TEXT] [--description TEXT] [--workspace TEXT] \
  [--enable|--disable] \
  [--event '<event-json>'] [--actions '<actions-json>']   # v2
  [--notebook-id TEXT] [--trigger JSON] [--schedule JSON]  # v1

# Enable / disable a routine
slcli routine enable  <ROUTINE_ID> [--api-version v1|v2]
slcli routine disable <ROUTINE_ID> [--api-version v1|v2]

# Delete a routine (prompts for confirmation unless -y)
slcli routine delete <ROUTINE_ID> [--api-version v1|v2] [-y]
```

### v2 event JSON structure

```json
{
  "type": "TAG",
  "triggers": [
    {
      "name": "<uuid>",
      "configuration": {
        "comparator": "GREATER_THAN",
        "path": "my.tag.path.*",
        "thresholds": ["10.2"],
        "type": "DOUBLE"
      }
    }
  ]
}
```

Supported TAG comparators: `GREATER_THAN`, `LESS_THAN`, `EQUAL`, `NOT_EQUAL`.
Tag data types: `DOUBLE`, `INT32`, `U_INT64`, `STRING`, `BOOLEAN`.

### v2 actions JSON structure

```json
[
  {
    "type": "ALARM",
    "triggers": ["<same-uuid-as-event-trigger>"],
    "configuration": {
      "displayName": "Alarm display name",
      "description": "Alarm description",
      "severity": 4,
      "condition": "Greater than: 10.2",
      "dynamicRecipientList": ["user@example.com"]
    }
  },
  {
    "type": "ALARM",
    "triggers": ["nisystemlink_no_triggers_breached"],
    "configuration": null
  }
]
```

The second ALARM entry with trigger `nisystemlink_no_triggers_breached` is required by the API — it handles the alarm clear/reset state. Email notifications are delivered via `dynamicRecipientList` inside the ALARM action configuration. Severity levels: 1 (low) – 4 (critical).

### Full example: tag threshold monitor with alarm + email

```bash
slcli routine create \
  --name "Fred Tag Monitor" \
  --description "Alert when fred.test.* exceeds 10.2" \
  --enabled \
  --event '{
    "type": "TAG",
    "triggers": [{
      "name": "a1b2c3d4-e5f6-7890-abcd-ef1234567890",
      "configuration": {
        "comparator": "GREATER_THAN",
        "path": "fred.test.*",
        "thresholds": ["10.2"],
        "type": "DOUBLE"
      }
    }]
  }' \
  --actions '[
    {
      "type": "ALARM",
      "triggers": ["a1b2c3d4-e5f6-7890-abcd-ef1234567890"],
      "configuration": {
        "displayName": "Fred Test Tag Alarm",
        "description": "Tag fred.test.* exceeded 10.2",
        "severity": 4,
        "condition": "Greater than: 10.2",
        "dynamicRecipientList": ["fred.visser@emerson.com"]
      }
    },
    {
      "type": "ALARM",
      "triggers": ["nisystemlink_no_triggers_breached"],
      "configuration": null
    }
  ]'
```

## comment — Resource comments

> **Requires:** Comments service (SLE only). Check `slcli info` for availability.

Attach, edit, and remove comments on any SystemLink resource. User IDs in responses
are automatically resolved to display names.

```bash
# List comments for a resource (most recent 1000, ordered by creation time)
slcli comment list --resource-type <TYPE> --resource-id <ID> [-f json]

# Supported resource types
#   testmonitor:Result   Test Monitor results
#   niapm:Asset          Assets
#   nisysmgmt:System     Systems
#   workorder:workorder  Work Orders
#   workitem:workitem    Work Items
#   DataSpace            Data Spaces

# Short aliases: -r for --resource-type, -i for --resource-id
slcli comment list -r testmonitor:Result -i <RESULT_ID>
slcli comment list -r niapm:Asset -i <ASSET_ID> -f json

# Add a comment to a resource
slcli comment add \
  --resource-type <TYPE> \
  --resource-id <ID> \
  --workspace <WORKSPACE_NAME_OR_ID> \
  --message "Comment text (supports Markdown)"

# Optionally mention users in a comment.
# Mentions require ALL of the following:
#   1. A <user:USER_ID> tag embedded in the --message body for each mentioned user
#   2. The same user ID(s) passed to --mention (one flag per user)
#   3. --resource-name / -n   human-readable resource name (for the email)
#   4. --resource-type / -r   resource type (auto-mapped to display name for email)
#   5. --comment-url / -u     URL to the comment in the UI (for the email)
slcli comment add -r testmonitor:Result -i <ID> -w default \
  -n "Result #1234" \
  -u "https://<server>/nitestmonitor/results/<ID>" \
  -m "See findings: <user:f9d5c5c9-e098-4a82-8e55-fede326a4ec3>" \
  --mention f9d5c5c9-e098-4a82-8e55-fede326a4ec3

# Update an existing comment (replaces message and mention list entirely)
# Same mention requirements apply
slcli comment update <COMMENT_ID> --message "Revised text"
slcli comment update <COMMENT_ID> \
  -m "FYI: <user:f9d5c5c9-e098-4a82-8e55-fede326a4ec3>" \
  -n "My Result" -r testmonitor:Result \
  -u "https://<server>/nitestmonitor/results/<ID>" \
  --mention f9d5c5c9-e098-4a82-8e55-fede326a4ec3

# Delete one or more comments by ID (up to 1000 per call)
slcli comment delete <COMMENT_ID>
slcli comment delete <ID1> <ID2> <ID3>
```

## workspace — Workspace management

```bash
slcli workspace list [-f json]
slcli workspace get <WORKSPACE_ID> [-f json]
```

## config — Profile and credential management

Manage named connection profiles (dev, test, prod). Credentials are stored in
`~/.config/slcli/config.json`.

```bash
slcli login [--profile NAME] [--url URL] [--api-key KEY] [--web-url URL] [--workspace NAME]
slcli logout [--profile NAME] [--all] [--force]
slcli info [-f json] [--skip-health]            # Show active profile and service health
slcli completion [--shell SHELL] [--install]    # Generate or install shell tab completion

slcli config list [-f json]                     # List all profiles
slcli config current                            # Show the active profile name
slcli config use <PROFILE>                      # Switch the active profile
slcli config view [--profile NAME] [-f json]    # Show full profile details
slcli config add [--profile NAME] [OPTIONS]     # Add or update a profile
slcli config delete <PROFILE> [--force]         # Delete a profile
slcli config migrate                            # Migrate legacy keyring credentials
```

## user — User management

```bash
slcli user list [--workspace NAME] [-t INT] [-f json]
slcli user get <USER_ID> [-f json]
slcli user create [OPTIONS]         # Create a new user
slcli user update <USER_ID> [OPTIONS]
slcli user delete <USER_ID>
```

## auth — Authorization policies and templates

```bash
# Policies
slcli auth policy list [--type CHOICE] [--builtin] [-t INT] [-f json]
slcli auth policy get <POLICY_ID> [-f json]
slcli auth policy create --name TEXT [OPTIONS]
slcli auth policy update <POLICY_ID> [OPTIONS]
slcli auth policy delete <POLICY_ID>
slcli auth policy diff <POLICY_ID>              # Show diff of a pending policy change

# Policy templates
slcli auth template list [-t INT] [-f json]
slcli auth template get <TEMPLATE_ID> [-f json]
slcli auth template delete <TEMPLATE_ID>
```

## feed — NI Package Manager feed management

Manage package repository feeds used to install software on test systems.
Supports Windows (.nipkg) and NI Linux RT (.ipk/.deb).

```bash
slcli feed list [-w WORKSPACE] [-t INT] [-f json]
slcli feed get <FEED_ID> [-f json]
slcli feed create --name TEXT [--workspace NAME] [OPTIONS]
slcli feed delete <FEED_ID>
slcli feed replicate --source-id FEED_ID --target-workspace WORKSPACE [OPTIONS]

# Packages within a feed
slcli feed package list --feed-id FEED_ID [-f json]
slcli feed package upload --feed-id FEED_ID --file PATH
slcli feed package delete --feed-id FEED_ID --package-name NAME
```

## file — File Service management

```bash
slcli file list [--workspace NAME] [--name TEXT] [-t INT] [-f json]
slcli file get <FILE_ID> [-f json]
slcli file upload --file PATH [--workspace NAME] [OPTIONS]
slcli file download <FILE_ID> -o OUTPUT_PATH
slcli file delete <FILE_ID>
slcli file query [--filter TEXT] [-t INT] [-f json]      # Advanced filter query
slcli file update-metadata <FILE_ID> [OPTIONS]
slcli file watch [--workspace NAME] [--filter TEXT]      # Stream new file events
```

## notebook — Jupyter Notebook management and execution

```bash
# Local scaffolding
slcli notebook init [--name NAME] [--directory DIR]      # Create a local .ipynb template

# Remote notebook management
slcli notebook manage list [-w WORKSPACE] [-t INT] [-f json]
slcli notebook manage get <NOTEBOOK_ID> [-f json]
slcli notebook manage create --file PATH [--workspace NAME]
slcli notebook manage update <NOTEBOOK_ID> --file PATH
slcli notebook manage set-interface <NOTEBOOK_ID> [OPTIONS]  # Define parameter interface
slcli notebook manage download <NOTEBOOK_ID> -o PATH
slcli notebook manage delete <NOTEBOOK_ID>

# Notebook executions
slcli notebook execute list [-w WORKSPACE] [-t INT] [-f json]
slcli notebook execute get <EXECUTION_ID> [-f json]
slcli notebook execute start <NOTEBOOK_ID> [--params JSON] [--workspace NAME]
slcli notebook execute sync <EXECUTION_ID>               # Wait for completion
slcli notebook execute cancel <EXECUTION_ID>
slcli notebook execute retry <EXECUTION_ID>
```

## customfield — Custom field (DFF) configuration

Manage Dynamic Form Field definitions used to attach custom metadata to resources.

```bash
slcli customfield list [-w WORKSPACE] [-t INT] [-f json]
slcli customfield get <FIELD_ID> [-f json]
slcli customfield create --name TEXT --entity-type TYPE [OPTIONS]
slcli customfield update <FIELD_ID> [OPTIONS]
slcli customfield delete <FIELD_ID>
slcli customfield export [-o FILE]                       # Export all custom fields to JSON
slcli customfield init [--directory DIR]                 # Scaffold a local config template
slcli customfield edit [--directory DIR]                 # Interactively edit + push config
```

## template — Test plan template management

> **Requires:** Work Order service (SLE only). Check `slcli info` for availability.

> **Note:** Work item templates are managed separately via `slcli workitem template`.
> The `slcli template` command manages test plan _configuration_ templates used
> when provisioning new test plan instances.

```bash
slcli template init [--name TEXT] [--directory DIR]      # Scaffold a local template file
slcli template list [-w WORKSPACE] [-t INT] [-f json]
slcli template get <TEMPLATE_ID> [-f json]
slcli template export [-o FILE] [-w WORKSPACE]           # Export all templates to JSON
slcli template import --file PATH [--workspace NAME]     # Import templates from JSON
slcli template delete <TEMPLATE_ID>
```

## workitem — Work item, template, and workflow management

> **Partially gated:** The `workitem template` and `workitem workflow` subgroups require the
> Work Order service (SLE only). Core work item commands (`list`, `create`, `get`) are available
> on both platforms. Check `slcli info` for service availability.

Unified command group for managing work items, work item templates, and workflows.

```bash
# Work item commands
slcli workitem list [-w WORKSPACE] [--filter TEXT] [--state TEXT] [-t INT] [-f json]
slcli workitem get <WORK_ITEM_ID> [-f json]
slcli workitem create --name TEXT --type TEXT --state TEXT --part-number TEXT [-w WORKSPACE]
slcli workitem create-from-template <TEMPLATE_ID> [--name TEXT] [--state TEXT] [--description TEXT]
                                    [--assigned-to TEXT] [--workflow-id TEXT] [-w WORKSPACE]
                                    [--part-number TEXT] [-f json]
slcli workitem update <WORK_ITEM_ID> [--name TEXT] [--state TEXT] [--description TEXT] [--assigned-to TEXT]
slcli workitem delete <WORK_ITEM_ID> [--yes]             # Prompts for confirmation without --yes
slcli workitem execute <WORK_ITEM_ID> --action TEXT      # Execute an action on a work item

# Schedule a work item: set planned time and/or assign resources.
# Resources map to the work item's resource requirement slots defined in the template:
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

## workflow — Workflow management

> **Note:** The standalone `slcli workflow` command group has been replaced by
> `slcli workitem workflow`. Use `slcli workitem workflow` for all workflow operations.
> See the **workitem** section above.

## webapp — Web application management

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

## skill — AI skill installation

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

## example — Built-in example resource provisioning

Install pre-built demo configurations (systems, assets, DUTs, templates, etc.)
for training, testing, or evaluation.

```bash
slcli example list [-f json]                             # List available examples
slcli example info <EXAMPLE_ID>                          # Show example details
slcli example install <EXAMPLE_ID> [--workspace NAME]    # Provision example resources
slcli example delete <EXAMPLE_ID> [--workspace NAME]     # Remove provisioned resources
```
