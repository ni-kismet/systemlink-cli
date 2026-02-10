# Asset Command Proposal: Analysis & Recommendations

**Date:** February 10, 2026  
**Context:** Review of slcli-workflow-analysis.md against the Asset Management API (niapm v1)

---

## Executive Summary

The workflow analysis identifies two high-priority workflows requiring asset data (Workflows 2 and 4), plus general asset management needs. The Asset Management API (`/niapm/v1/`) provides comprehensive endpoints for querying, filtering, and managing assets — including location history, calibration tracking, and utilization.

**Recommendation:** Create a single `slcli asset` command group with `list`, `get`, `summary`, and `calibration` subcommands. Keep the command structure flat (no nested groups), consistent with `slcli file`, `slcli tag`, etc. The `testmonitor` nested-group pattern is not needed here because assets are a single entity type, unlike testmonitor's product/result split.

---

## Current Implementation Assessment

### What We Have

No asset commands exist in slcli today. The workflow analysis proposes several asset-related commands across Workflows 2 and 4:

- **Workflow 2:** "What was the SN of the PXI-4071 used to measure DUT SN 1234567?" — requires cross-service correlation (Test Monitor → Systems → Assets)
- **Workflow 4:** "Find me a system that has a DMM and a scope" — requires querying assets by model and correlating by system location

---

## Workflow Analysis Proposals vs. Recommended Implementation

### Workflow 2: "What was the SN of the PXI-4071 used to measure DUT SN 1234567?"

**Workflow Analysis Proposes:**

```bash
# Multiple specialized commands
slcli asset query \
  --filter 'location.minionId = "<minion-id>" and model contains "PXI-4071"'
slcli asset location-history <asset-id> \
  --from "<date>" --to "<date>"
slcli testresult get-assets <result-id> \
  --filter 'model contains "PXI-4071"'
slcli testresult correlate \
  --serial-number "1234567" \
  --show assets,system,conditions
```

**Recommended Implementation:**

```bash
# Step 1: Get result to find systemId (existing testmonitor command)
slcli testmonitor result list \
  --serial-number "1234567" \
  --format json

# Step 2: Find assets on that system matching the model
slcli asset list \
  --filter 'Location.MinionId = "<minion-id>" and ModelName.Contains("PXI-4071")' \
  --format json

# Step 3: Check location history if temporal correlation needed
slcli asset location-history <asset-id> \
  --from "2025-12-01T00:00:00Z" \
  --to "2025-12-02T00:00:00Z"
```

**Assessment:** ✅ Recommended approach is BETTER

- Uses existing `testmonitor result list` for step 1
- Standard `asset list` with filter handles step 2
- `location-history` is a focused, composable subcommand
- No need for specialized cross-service correlation commands — AI agents (Copilot) can chain these steps naturally

---

### Workflow 4: "Find me a system that has a DMM and a scope"

**Workflow Analysis Proposes:**

```bash
slcli system find \
  --has-asset "DMM" \
  --has-asset "scope" \
  --state connected
slcli system query-by-assets \
  --requires "DMM,scope"
slcli asset find-systems \
  --with-capabilities "voltage-measurement,waveform-acquisition"
```

**Recommended Implementation:**

```bash
# Step 1: Find DMMs and note their minionIds
slcli asset list \
  --model "DMM" \
  --connected \
  --format json

# Step 2: Find scopes and note their minionIds
slcli asset list \
  --model "scope" \
  --connected \
  --format json

# Copilot computes intersection of minionIds client-side
```

**Assessment:** ✅ Recommended approach is BETTER

- Uses a single, general-purpose `asset list` command with convenience filters
- AI agents can easily correlate minionIds across two queries
- No need for `system find --has-asset` or `asset find-systems` — these would be single-use commands
- The API doesn't support cross-entity joins, so these would just be client-side wrappers anyway

---

## Concrete Command Proposal

### Command Structure

```
slcli asset
├── list              # Query/list assets with filters
├── get <id>          # Get detailed asset information
├── summary           # Get fleet summary statistics
├── calibration       # Get calibration history for an asset
└── location-history  # Get location/connection history for an asset
```

**NOT creating (Phase 1 scope):**

- ❌ `asset query` separate from `list` (consolidated into `list --filter`)
- ❌ `asset find-systems` (AI agent can correlate `asset list` results)
- ❌ `asset utilization` (Phase 2, lower priority)
- ❌ `asset move-location` / `asset send-for-calibration` (Phase 2, mutation operations)

> Note: In the current implementation, `asset create`, `asset update`, and `asset delete` are implemented
> and documented in the README. They were originally proposed as Phase 2 work and are no longer excluded.

---

### 1. `slcli asset list`

**Purpose:** Query and list assets with comprehensive filtering

**API Endpoint:** POST `/niapm/v1/query-assets`  
**Pagination:** Skip/Take (server-side offset pagination, max Take=1000)

```bash
# List all assets (paginated, 25 per page)
slcli asset list

# Filter by model name (convenience option)
slcli asset list --model "PXI-4071"

# Filter by serial number
slcli asset list --serial-number "01BB877A"

# Filter by bus type
slcli asset list --bus-type PCI_PXI

# Filter by asset type
slcli asset list --asset-type DEVICE_UNDER_TEST

# Filter by calibration status
slcli asset list --calibration-status PAST_RECOMMENDED_DUE_DATE

# Show only connected/present assets
slcli asset list --connected

# Show only calibratable assets
slcli asset list --calibratable

# Advanced filter with API filter syntax
slcli asset list \
  --filter 'ModelName.Contains("PXI") and BusType = "PCI_PXI"'

# Filter by workspace
slcli asset list --workspace "Production"

# JSON output (all results, no pagination)
slcli asset list --model "DMM" --format json

# Order by last updated
slcli asset list --order-by LAST_UPDATED_TIMESTAMP --descending
```

**Options:**

| Option                     | Type                | Default | Description                           |
| -------------------------- | ------------------- | ------- | ------------------------------------- |
| `--format/-f`              | Choice[table, json] | table   | Output format                         |
| `--take/-t`                | int                 | 25      | Items per page (table)                |
| `--model`                  | str                 | None    | Filter by model name (contains match) |
| `--serial-number`          | str                 | None    | Filter by serial number (exact match) |
| `--bus-type`               | Choice              | None    | Filter by bus type                    |
| `--asset-type`             | Choice              | None    | Filter by asset type                  |
| `--calibration-status`     | Choice              | None    | Filter by calibration status          |
| `--connected`              | flag                | False   | Show only assets in connected systems |
| `--calibratable`           | flag                | False   | Show only calibratable assets         |
| `--workspace/-w`           | str                 | None    | Filter by workspace (name or ID)      |
| `--filter`                 | str                 | None    | Advanced API filter expression        |
| `--order-by`               | Choice              | None    | Sort field                            |
| `--descending/--ascending` | flag                | True    | Sort direction                        |
| `--summary`                | flag                | False   | Show summary statistics               |

**Table Output Columns:**

| Column        | Width | Source Field                                                   |
| ------------- | ----- | -------------------------------------------------------------- |
| Name          | 24    | `name`                                                         |
| Model         | 20    | `modelName`                                                    |
| Serial Number | 16    | `serialNumber`                                                 |
| Bus Type      | 12    | `busType`                                                      |
| Calibration   | 16    | `calibrationStatus`                                            |
| Location      | 16    | `location.minionId` (truncated) or `location.physicalLocation` |
| Workspace     | 16    | workspace name via `get_workspace_map()`                       |
| ID            | 36    | `id`                                                           |

**Implementation Notes:**

- The Asset API uses **skip/take pagination** (not continuation tokens). Table output paginates interactively (25 per page, Y/n). JSON fetches all pages.
- Convenience options (`--model`, `--serial-number`, etc.) are translated into the API's filter expression syntax: `ModelName.Contains("value")`, `SerialNumber = "value"`, etc.
- The filter syntax uses `=`, `!=`, `.Contains()`, `!.Contains()`, `and`, `or` — different from Test Monitor's Dynamic LINQ `@0` substitutions. Document this clearly in `--help`.
- `--connected` maps to filter: `Location.AssetState.SystemConnection = "CONNECTED" and Location.AssetState.AssetPresence = "PRESENT"`

---

### 2. `slcli asset get <id>`

**Purpose:** Get detailed information about a specific asset

**API Endpoint:** GET `/niapm/v1/assets/{assetId}`

```bash
# Get asset details in table format
slcli asset get 69e95bf9-8b52-4e46-924b-abbd5ee19bbf

# Get asset details in JSON format
slcli asset get 69e95bf9-8b52-4e46-924b-abbd5ee19bbf --format json

# Include calibration details
slcli asset get 69e95bf9-8b52-4e46-924b-abbd5ee19bbf --include-calibration
```

**Options:**

| Option                  | Type                | Default | Description                 |
| ----------------------- | ------------------- | ------- | --------------------------- |
| `--format/-f`           | Choice[table, json] | table   | Output format               |
| `--include-calibration` | flag                | False   | Include calibration details |

**Table Output (detailed view):**

```
Asset: NI PXIe-6368 (69e95bf9-8b52-4e46-924b-abbd5ee19bbf)
Model: NI PXIe-6368
Serial Number: 01BB877A
Part Number: A1234 B5
Vendor: NI
Bus Type: PCI_PXI
Asset Type: GENERIC
Firmware: A1
Hardware: 12A
Workspace: Production (846e294a-a007-47ac-9fc2-fac07eab240e)
Location: NI_PXIe-8135_Embedded_Controller (Slot 2)
Presence: PRESENT
System Connection: CONNECTED
Calibration Status: OK
Last Calibrated: 2025-06-15
Next Due: 2026-06-15
Keywords: Keyword1, Keyword2
Properties:
  Key1: Value1
```

**Implementation Notes:**

- `--include-calibration`: Fetches GET `/niapm/v1/assets/{assetId}/history/calibration` and appends history entries
- Location display: Show `minionId` or `physicalLocation`, whichever is populated, plus `slotNumber` if present
- Calibration display: Show `calibrationStatus`, last calibration date, next due date
- Use `isinstance()` checks for nested objects (location, calibration) — they may be null

---

### 3. `slcli asset summary`

**Purpose:** Get fleet-wide asset summary statistics

**API Endpoint:** GET `/niapm/v1/asset-summary`

```bash
# Show asset summary in table format
slcli asset summary

# Show summary in JSON format
slcli asset summary --format json
```

**Options:**

| Option        | Type                | Default | Description   |
| ------------- | ------------------- | ------- | ------------- |
| `--format/-f` | Choice[table, json] | table   | Output format |

**Table Output:**

```
Asset Fleet Summary:
  Total Assets: 17
  Active (in connected system): 12
  Not Active: 5
  In Use: 10
  Not In Use: 7
  With Alarms: 3

Calibration Status:
  Approaching Due Date: 3
  Past Due Date: 4
  Out for Calibration: 2
  Total Calibratable: 7
```

**Implementation Notes:**

- This is a simple single-endpoint command — no pagination needed
- The `AssetSummaryResponse` returns all fields in one call
- Useful for AI agents to quickly assess fleet health

---

### 4. `slcli asset calibration <asset-id>`

**Purpose:** Get calibration history for a specific asset

**API Endpoint:** GET `/niapm/v1/assets/{assetId}/history/calibration`

```bash
# Show calibration history
slcli asset calibration 69e95bf9-8b52-4e46-924b-abbd5ee19bbf

# JSON output
slcli asset calibration 69e95bf9-8b52-4e46-924b-abbd5ee19bbf --format json

# Limit results
slcli asset calibration 69e95bf9-8b52-4e46-924b-abbd5ee19bbf --take 10
```

**Options:**

| Option        | Type                | Default | Description               |
| ------------- | ------------------- | ------- | ------------------------- |
| `--format/-f` | Choice[table, json] | table   | Output format             |
| `--take/-t`   | int                 | 25      | Number of history entries |

**Table Output Columns:**

| Column        | Width | Source Field                   |
| ------------- | ----- | ------------------------------ |
| Date          | 20    | `date`                         |
| Type          | 12    | `entryType` (AUTOMATIC/MANUAL) |
| Limited       | 8     | `isLimited`                    |
| Next Due      | 20    | `resolvedDueDate`              |
| Interval (mo) | 14    | `recommendedInterval`          |
| Comments      | 30    | `comments`                     |

**Implementation Notes:**

- Uses skip/take pagination on the calibration history endpoint
- `CalibrationHistoryResponse` returns an array of `CalibrationHistoryModel` entries
- Temperature sensor data available but not shown in table by default (included in JSON)

---

### 5. `slcli asset location-history <asset-id>`

**Purpose:** Get location/connection history for a specific asset (supports temporal correlation for Workflow 2)

**API Endpoint:** POST `/niapm/v1/assets/{assetId}/history/query-location`

```bash
# Show location history
slcli asset location-history 69e95bf9-8b52-4e46-924b-abbd5ee19bbf

# Filter by date range (for temporal correlation)
slcli asset location-history 69e95bf9-8b52-4e46-924b-abbd5ee19bbf \
  --from "2025-12-01T00:00:00Z" \
  --to "2025-12-02T00:00:00Z"

# JSON output
slcli asset location-history 69e95bf9-8b52-4e46-924b-abbd5ee19bbf --format json
```

**Options:**

| Option        | Type                | Default | Description               |
| ------------- | ------------------- | ------- | ------------------------- |
| `--format/-f` | Choice[table, json] | table   | Output format             |
| `--take/-t`   | int                 | 25      | Number of history entries |
| `--from`      | str (ISO-8601)      | None    | Start of date range       |
| `--to`        | str (ISO-8601)      | None    | End of date range         |

**Table Output Columns:**

| Column     | Width | Source Field                 |
| ---------- | ----- | ---------------------------- |
| Timestamp  | 24    | timestamp from history entry |
| Minion ID  | 30    | `minionId`                   |
| Slot       | 6     | `slotNumber`                 |
| Connection | 14    | `systemConnection`           |
| Presence   | 12    | `assetPresence`              |

**Implementation Notes:**

- This is a POST endpoint with `QueryLocationHistoryRequest` body
- Returns `ConnectionHistoryResponse` with a list of `ConnectionHistoryModel` entries
- Critical for Workflow 2: confirming an asset was present in a system at the time of a test
- Date filtering is handled server-side in the request body

---

## Rationale for Simplified Structure

### 1. Aligns with API Structure

The Asset Management API v1 is organized around a **single primary entity** (assets) with related sub-resources:

- **Assets** — core entity with rich properties (model, serial, location, calibration)
- **Calibration History** — sub-resource of an asset
- **Location History** — sub-resource of an asset
- **Utilization History** — sub-resource of an asset (Phase 2)

This supports a flat command group (like `file`, `tag`) rather than nested groups (like `testmonitor`).

### 2. Matches User Mental Model

Users think in terms of:

- "What assets do I have?" → `asset list`
- "Show me details of this asset" → `asset get`
- "What's the calibration status?" → `asset summary` or `asset calibration <id>`
- "Was this DMM in that system during testing?" → `asset location-history <id> --from --to`

They don't think:

- "Query asset location moves" (too API-specific)
- "Search materialized assets" (implementation detail)
- "Start/end utilization" (API operation, not user workflow)

### 3. Reduces Command Explosion

Workflow analysis proposes:

- `asset query` (generic query)
- `asset find-systems` (cross-service)
- `asset query-for-test` (cross-service)
- `asset location-history` (history)
- `system find --has-asset` (cross-service)
- `system query-by-assets` (cross-service)
  = **6+ new commands across groups**

Our proposal:

- `asset list` (with rich filtering)
- `asset get` (detailed view)
- `asset summary` (fleet overview)
- `asset calibration` (calibration history)
- `asset location-history` (location tracking)
  = **5 focused commands in one group**

### 4. Follows Established slcli Patterns

Similar commands in slcli:

```bash
# File service — single group, simple verbs
slcli file list
slcli file get <id>
slcli file upload

# Tag service — single group
slcli tag list
slcli tag get <path>
slcli tag create

# Workspace service — single group
slcli workspace list
slcli workspace get --workspace <name-or-id>
```

We follow this pattern:

```bash
slcli asset list
slcli asset get <id>
slcli asset summary
slcli asset calibration <id>
slcli asset location-history <id>
```

---

## Addressing Specific Workflow Requirements

### Workflow 2: "What was the SN of the PXI-4071 used to measure DUT SN 1234567?"

**Using proposed commands (AI agent orchestration):**

```bash
# Step 1: Find the test result to get systemId
slcli testmonitor result list \
  --serial-number "1234567" \
  --format json
# → Extract systemId from result

# Step 2: Find PXI-4071 assets on that system
slcli asset list \
  --filter 'Location.MinionId = "<minion-id>" and ModelName.Contains("PXI-4071")' \
  --format json
# → Get asset serial number

# Step 3 (optional): Verify asset was present during test
slcli asset location-history <asset-id> \
  --from "2025-12-01T10:00:00Z" \
  --to "2025-12-01T11:00:00Z" \
  --format json
# → Confirm PRESENT + CONNECTED at test time
```

**Why this works:** Copilot can chain these three commands and correlate the results. No specialized cross-service command needed.

---

### Workflow 4: "Find me a system that has a DMM and a scope"

**Using proposed commands (AI agent orchestration):**

```bash
# Step 1: Find DMMs in connected systems
slcli asset list \
  --model "DMM" \
  --connected \
  --format json
# → Collect minionIds: ["minion-A", "minion-B", "minion-C"]

# Step 2: Find scopes in connected systems
slcli asset list \
  --model "scope" \
  --connected \
  --format json
# → Collect minionIds: ["minion-B", "minion-D"]

# Step 3: Intersection → minion-B has both
# Copilot computes this client-side and presents the result
```

**Why this works:** The `--model` convenience filter with `--connected` flag makes each query simple. Copilot excels at set intersection logic.

---

## API Requirements

### Existing APIs (Available Now)

**Asset CRUD:**

- ✅ GET `/niapm/v1/assets` — Get assets (query params: Skip, Take, CalibratableOnly, ReturnCount)
- ✅ POST `/niapm/v1/query-assets` — Query assets with filter expression
- ✅ GET `/niapm/v1/assets/{assetId}` — Get single asset by ID
- ✅ POST `/niapm/v1/assets` — Create assets (Phase 2)
- ✅ POST `/niapm/v1/update-assets` — Update assets (Phase 2)
- ✅ POST `/niapm/v1/delete-assets` — Delete assets (Phase 2)

**Summary:**

- ✅ GET `/niapm/v1/asset-summary` — Get fleet summary statistics

**Calibration:**

- ✅ GET `/niapm/v1/assets/{assetId}/history/calibration` — Get calibration history
- ✅ POST `/niapm/v1/assets/{assetId}/history/delete-calibrations` — Delete calibration entries (Phase 2)
- ✅ POST `/niapm/v1/assets/send-for-calibration` — Send for calibration (Phase 2)
- ✅ POST `/niapm/v1/assets/receive-from-calibration` — Receive from calibration (Phase 2)

**Location:**

- ✅ POST `/niapm/v1/assets/{assetId}/history/query-location` — Query location history
- ✅ POST `/niapm/v1/assets/move-location` — Move asset location (Phase 2)
- ✅ POST `/niapm/v1/assets/query-location-moves` — Query pending moves (Phase 2)

**Search (Materialized):**

- ✅ POST `/niapm/v1/materialized/search-assets` — Advanced search with projection support

**Utilization:**

- ✅ POST `/niapm/v1/query-asset-utilization-history` — Query utilization history
- ✅ POST `/niapm/v1/assets/start-utilization` — Start utilization (Phase 2)
- ✅ POST `/niapm/v1/assets/end-utilization` — End utilization (Phase 2)

### Implementation Notes

**For `asset list` (query-assets):**

- POST `/niapm/v1/query-assets` with `QueryAssetsRequest` body
- Supports rich filter expressions: `ModelName.Contains("PXI")`, `SerialNumber = "01BB"`, etc.
- Pagination via `skip`/`take` (max take=1000)
- Order by `LAST_UPDATED_TIMESTAMP` or `ID`
- `returnCount=true` to get total matching assets
- **Filter syntax** differs from Test Monitor (no `@0` substitutions) — uses `.Contains()`, `=`, `!=`, `and`, `or`

**For `asset list --connected`:**

- Translates to filter: `Location.AssetState.SystemConnection = "CONNECTED" and Location.AssetState.AssetPresence = "PRESENT"`
- Merged with any user `--filter` using `and`

**For `asset list --model`:**

- Translates to filter: `ModelName.Contains("<value>")`
- Uses `.Contains()` for partial matching (users may search "DMM", "4071", "PXI-4071")

**For `asset summary`:**

- GET `/niapm/v1/asset-summary` — single endpoint, no pagination
- Returns: total, active, notActive, inUse, notInUse, withAlarms, calibration breakdown

**For `asset calibration`:**

- GET `/niapm/v1/assets/{assetId}/history/calibration` with Skip/Take params
- Returns `CalibrationHistoryResponse` with entries and totalCount

**For `asset location-history`:**

- POST `/niapm/v1/assets/{assetId}/history/query-location` with date range in body
- Returns `ConnectionHistoryResponse` with location/connection events

### No New APIs Required

All proposed commands can be implemented using existing Asset Management v1 APIs.

---

## Implementation Priority

### Phase 1: Core Commands (Initial PR)

- 🔨 `slcli asset list` — with filter, model, serial-number, bus-type, connected, calibratable, workspace, order-by, summary
- 🔨 `slcli asset get <id>` — detailed view with optional calibration include
- 🔨 `slcli asset summary` — fleet statistics

### Phase 2: History Commands

- 🔨 `slcli asset calibration <id>` — calibration history with pagination
- 🔨 `slcli asset location-history <id>` — location history with date range filtering

### Phase 3: Mutation Commands

- 🔨 `slcli asset create` — create assets (with `check_readonly_mode()`)
- 🔨 `slcli asset update` — update asset properties
- 🔨 `slcli asset delete` — delete assets (with confirmation, `--force`)

### Phase 4: Advanced Features

- 🔨 `slcli asset utilization <id>` — utilization history
- 🔨 `slcli asset move-location` — move assets between systems/locations
- 🔨 `slcli asset send-for-calibration` — calibration workflow
- 🔨 `slcli asset receive-from-calibration` — calibration workflow
- 🔨 `slcli asset export` — export to CSV/file service

---

## Implementation Checklist

### Module Structure

```
slcli/
├── asset_click.py          # Command module (register_asset_commands)
└── ...

tests/unit/
├── test_asset_click.py     # Unit tests
└── ...
```

### Requirements (per copilot-instructions.md)

- [ ] Create `slcli/asset_click.py` with `register_asset_commands(cli: Any) -> None`
- [ ] Register in `slcli/main.py`
- [ ] All functions have complete type annotations
- [ ] Use `UniversalResponseHandler` for list/get responses
- [ ] Use `handle_api_error()` for error handling
- [ ] Use `format_success()` for success messages
- [ ] Use `check_readonly_mode()` for mutation commands (Phase 3)
- [ ] All list commands support `--format/-f` (table/json)
- [ ] All list commands support `--take/-t` with default 25
- [ ] Table output with interactive pagination (Y/n)
- [ ] JSON output fetches all results (no pagination)
- [ ] Exit codes use `ExitCodes` enum
- [ ] Unit tests in `tests/unit/test_asset_click.py`
- [ ] Coverage ≥ 80% for new code
- [ ] Linting passes: `poetry run ni-python-styleguide lint`
- [ ] Type checking passes: `poetry run mypy slcli tests`
- [ ] README.md updated with usage examples

### Pagination Strategy

The Asset API uses **skip/take** pagination (not continuation tokens like Test Monitor). Implementation approach:

```python
def _query_all_assets(
    filter_expr: Optional[str],
    order_by: Optional[str],
    descending: bool,
    take: Optional[int] = 10000,
    calibratable_only: bool = False,
) -> List[Dict[str, Any]]:
    """Query assets using skip/take pagination."""
    url = f"{_get_asset_base_url()}/query-assets"
    all_assets: List[Dict[str, Any]] = []
    page_size = 1000  # API max per request
    skip = 0

    while True:
        if take is not None:
            remaining = take - len(all_assets)
            if remaining <= 0:
                break
            batch_size = min(page_size, remaining)
        else:
            batch_size = page_size

        payload: Dict[str, Any] = {
            "skip": skip,
            "take": batch_size,
            "descending": descending,
            "returnCount": True,
        }

        if filter_expr:
            payload["filter"] = filter_expr
        if order_by:
            payload["orderBy"] = order_by
        if calibratable_only:
            payload["calibratableOnly"] = True

        resp = make_api_request("POST", url, payload=payload)
        data = resp.json()
        assets = data.get("assets", []) if isinstance(data, dict) else []

        all_assets.extend(assets)
        skip += len(assets)

        # Stop if we got fewer than requested (last page)
        if len(assets) < batch_size:
            break
        if take is not None and len(all_assets) >= take:
            break

    return all_assets[:take] if take is not None else all_assets
```

For interactive table pagination, use `_fetch_assets_page()` with skip/take:

```python
def _fetch_assets_page(
    filter_expr: Optional[str],
    order_by: Optional[str],
    descending: bool,
    take: int,
    skip: int,
    calibratable_only: bool = False,
) -> Tuple[List[Dict[str, Any]], int]:
    """Fetch a single page of assets. Returns (assets, total_count)."""
    # ... similar to above but single page
```

### Filter Expression Builder

Convenience options are translated to API filter syntax:

```python
def _build_asset_filter(
    model: Optional[str] = None,
    serial_number: Optional[str] = None,
    bus_type: Optional[str] = None,
    asset_type: Optional[str] = None,
    calibration_status: Optional[str] = None,
    connected: bool = False,
    custom_filter: Optional[str] = None,
) -> Optional[str]:
    """Build API filter expression from convenience options."""
    parts: List[str] = []

    if model:
        parts.append(f'ModelName.Contains("{model}")')
    if serial_number:
        parts.append(f'SerialNumber = "{serial_number}"')
    if bus_type:
        parts.append(f'BusType = "{bus_type}"')
    if asset_type:
        parts.append(f'AssetType = "{asset_type}"')
    if calibration_status:
        parts.append(f'CalibrationStatus = "{calibration_status}"')
    if connected:
        parts.append(
            'Location.AssetState.SystemConnection = "CONNECTED"'
            ' and Location.AssetState.AssetPresence = "PRESENT"'
        )
    if custom_filter:
        parts.append(custom_filter)

    return " and ".join(parts) if parts else None
```

**Note:** Unlike Test Monitor's Dynamic LINQ with `@0` substitutions, the Asset API uses direct string values in the filter. Input validation should sanitize user values to prevent filter injection (escape quotes in user-provided strings).

---

## Comparison Table

| Capability                | Workflow Analysis               | This Proposal                                   | Assessment             |
| ------------------------- | ------------------------------- | ----------------------------------------------- | ---------------------- |
| List/query assets         | `asset query`                   | `asset list`                                    | ✅ Consistent naming   |
| Get asset details         | `asset get <id>`                | `asset get <id>`                                | ✅ Equivalent          |
| Find assets by model      | custom commands                 | `asset list --model`                            | ✅ Simpler             |
| Find assets by system     | `asset query --filter minionId` | `asset list --filter 'Location.MinionId = ...'` | ✅ Equivalent          |
| Connected assets          | custom flag                     | `asset list --connected`                        | ✅ Cleaner             |
| Fleet summary             | not proposed                    | `asset summary`                                 | ✅ Added value         |
| Calibration history       | not proposed                    | `asset calibration <id>`                        | ✅ Added value         |
| Location history          | `asset location-history`        | `asset location-history <id>`                   | ✅ Equivalent          |
| Cross-service correlation | specialized commands            | AI agent orchestration                          | ✅ More composable     |
| Find systems by assets    | `system find --has-asset`       | two `asset list` queries                        | ✅ No new abstractions |
| Total commands            | 6+ across groups                | 5 in one group                                  | ✅ Fewer commands      |

---

## Key Design Decisions

### 1. Filter Syntax Documentation

The Asset API uses a **different filter syntax** than Test Monitor:

- **Asset API:** `ModelName.Contains("PXI") and BusType = "PCI_PXI"`
- **Test Monitor:** `name == @0` with substitutions

This should be clearly documented in `--help` text and README. Consider adding a `--help-filter` flag or documenting common filter examples.

### 2. No Parameterized Queries

The Asset API does not support `@0`-style substitutions. User-provided filter values are embedded directly in the filter string. **Input sanitization is required** — escape double quotes in user-provided values for `--model`, `--serial-number`, etc. to prevent filter injection.

### 3. Skip/Take vs Continuation Tokens

The Asset API uses skip/take, which is simpler but has known issues with large datasets (skip-based pagination can miss or duplicate items if data changes during pagination). For interactive table output, this is acceptable. For JSON "fetch all" mode, it's good enough given the 10k safety cap.

### 4. Summary Command

The `asset summary` command is a lightweight addition that provides significant value for AI agents assessing fleet health without needing to paginate through all assets.

### 5. Materialized Search API

The API also offers POST `/niapm/v1/materialized/search-assets` with projection support. This could be used as an optimization for `asset list` when only specific fields are needed, but the standard `query-assets` endpoint is sufficient for Phase 1.
