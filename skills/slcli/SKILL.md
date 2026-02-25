---
name: slcli
description: >-
  Query and manage NI SystemLink resources including test results, assets, systems,
  products, tags, feeds, and workspaces using the slcli command-line interface.
  Use when the user asks about test data analysis, asset management, calibration status,
  system fleet health, operator performance, failure analysis, production metrics,
  equipment utilization, or any SystemLink resource operations. Supports filtering,
  aggregation, summary statistics, and JSON output for programmatic processing.
compatibility: >-
  Requires slcli installed and authenticated (slcli login). Python 3.10+.
  Requires network access to a SystemLink server instance.
metadata:
  author: ni-kismet
  version: "1.0"
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
```

## Output formats

All list and get commands support `-f, --format` with `table` (default) or `json`.

- **Table**: Paginated (default 25 rows), human-readable with box-drawing.
- **JSON**: Returns all matching results as a JSON array — ideal for piping to `jq`.

Always use `-f json` when you need to process, filter, or aggregate output programmatically.

## Commands

### testmonitor — Test data analysis

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
```

### asset — Asset and calibration management

```bash
# List assets with filters
slcli asset list [OPTIONS]

# Convenience filters
  --model TEXT               # Filter by model name (contains)
  --serial-number TEXT       # Filter by serial number (exact)
  --bus-type CHOICE          # BUILT_IN_SYSTEM, PCI_PXI, USB, GPIB, VXI, SERIAL, TCP_IP, CRIO
  --asset-type CHOICE        # GENERIC, DEVICE_UNDER_TEST, FIXTURE, SYSTEM
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

### system — System fleet management

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
                             # e.g., 'connected.data.state = "CONNECTED"'

# Output
  --take, -t INTEGER         # Default 100
  -f [table|json]

# Other system commands
slcli system get <SYSTEM_ID> [-f json]
slcli system summary [-f json]                      # Fleet-wide statistics
slcli system report --type [SOFTWARE|HARDWARE] -o FILE  # Generate CSV report
slcli system update <SYSTEM_ID> [OPTIONS]            # Update system metadata
slcli system remove <SYSTEM_ID>                      # Remove a system

# System jobs
slcli system job list [OPTIONS]
slcli system job get <JOB_ID>
slcli system job summary [-f json]
slcli system job cancel <JOB_ID>
```

### tag — Tag operations

```bash
slcli tag list [OPTIONS]
slcli tag get-value <TAG_PATH>
slcli tag set-value <TAG_PATH> <VALUE>
slcli tag create --path <PATH> --data-type <TYPE>
slcli tag delete <TAG_PATH>
```

### comment — Resource comments

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

### workspace — Workspace management

```bash
slcli workspace list [-f json]
slcli workspace get <WORKSPACE_ID> [-f json]
```

## Recipes: answering analysis questions

See [references/analysis-recipes.md](references/analysis-recipes.md) for detailed
multi-step recipes covering operator performance, calibration tracking, capacity
planning, yield analysis, and failure pattern investigation.

## Filtering guide

See [references/filtering.md](references/filtering.md) for detailed filtering
syntax, advanced LINQ expressions, and parameterized query examples.

## Key rules

1. **Always use `-f json`** when piping output to `jq` or doing programmatic analysis.
2. **Use `--summary --group-by`** for aggregation instead of fetching all records and counting.
3. **Use convenience filters first** (e.g., `--status FAILED`), fall back to `--filter` for complex queries.
4. **Parameterize `--filter` queries** — use `--substitution` instead of string interpolation.
5. **Combine filters** — convenience filters are ANDed together automatically.
6. **Use `--take`** to control result volume; JSON returns all matching up to `--take`.
7. **Status enum values**: `PASSED`, `FAILED`, `RUNNING`, `ERRORED`, `TERMINATED`, `TIMEDOUT`, `WAITING`, `SKIPPED`, `CUSTOM`.
8. **Exit codes**: 0 = success, 1 = general error, 2 = invalid input, 3 = not found, 4 = permission denied, 5 = network error.
