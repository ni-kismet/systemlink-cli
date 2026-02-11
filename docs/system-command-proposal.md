# System Command Proposal: Analysis & Recommendations

**Date:** February 10, 2026
**Context:** Review of slcli-workflow-analysis.md against nisysmgmt OpenAPI spec, following slcli best practices

---

## Executive Summary

The workflow analysis proposes several granular system commands (`system find`, `system get-snapshot`, `system query-by-assets`, `system query-by-software`) that split functionality across too many specialized verbs. This doesn't align with:

1. The nisysmgmt v1 REST API structure
2. Established slcli command patterns (single `list`/`get` verbs with rich filtering)
3. Actual user mental models

**Recommendation:** Create a `slcli system` command group with standard `list`, `get`, `summary`, `update`, and `remove` commands — enhanced with targeted flags for the specific workflow requirements (package search, job management).

---

## API Assessment

### Available Endpoints (nisysmgmt v1)

#### System Endpoints

- ✅ `GET /nisysmgmt/v1/systems?id=<id>` — Get system(s) by ID
- ✅ `POST /nisysmgmt/v1/query-systems` — Query systems with filter/projection/orderBy/skip/take
- ✅ `GET /nisysmgmt/v1/get-systems-summary` — Connected/disconnected/virtual counts
- ✅ `GET /nisysmgmt/v1/get-pending-systems-summary` — Pending approval count
- ✅ `POST /nisysmgmt/v1/update-systems` — Batch update system metadata
- ✅ `PATCH /nisysmgmt/v1/systems/managed/{id}` — Update single system
- ✅ `POST /nisysmgmt/v1/remove-systems` — Remove/unregister systems
- ✅ `POST /nisysmgmt/v1/generate-systems-report` — Generate SOFTWARE/HARDWARE report

#### Virtual System Endpoints

- ✅ `POST /nisysmgmt/v1/virtual` — Create virtual system
- ✅ `POST /nisysmgmt/v1/virtual/generate-system-apikey` — Generate API key for virtual system

#### Job Endpoints

- ✅ `GET /nisysmgmt/v1/jobs` — Get jobs (by systemId, jid, state, function)
- ✅ `POST /nisysmgmt/v1/query-jobs` — Query jobs with filter/projection/orderBy/skip/take
- ✅ `POST /nisysmgmt/v1/jobs` — Create job (run salt function on target systems)
- ✅ `POST /nisysmgmt/v1/cancel-jobs` — Cancel jobs
- ✅ `GET /nisysmgmt/v1/get-jobs-summary` — Active/failed/succeeded counts

#### Key Management Endpoints

- ✅ `GET /nisysmgmt/v1/get-systems-keys` — Get all system keys (pending/denied/approved/rejected)
- ✅ `POST /nisysmgmt/v1/get-systems-keys` — Get keys for specific system IDs
- ✅ `POST /nisysmgmt/v1/manage-systems-keys` — Accept/reject/delete keys

### System Data Model

From the API example response, a system object contains:

```json
{
  "id": "6b70e1df-ae93-4ded-9fe0-dc775732289b",
  "alias": "MySystem",
  "scanCode": "e20aadfb-91fe-4596-97e8-e8cb67ff786a",
  "createdTimestamp": "2026-02-10T20:37:48Z",
  "lastUpdatedTimestamp": "2026-02-10T20:37:48Z",
  "connected": {
    "data": { "state": "CONNECTED" }
  },
  "grains": {
    "data": {
      "kernel": "Windows",
      "osversion": "10.0.19042.928",
      "osmanufacturer": "Microsoft Corporation",
      "host": "MyComputer",
      "cpuarch": "AMD64",
      "deviceclass": "Desktop"
    }
  },
  "status": {
    "data": { "http_connected": true }
  },
  "packages": {
    "data": {
      "ni-daqmx": {
        "arch": "windows_x64",
        "displayname": "NI-DAQmx",
        "displayversion": "2023 Q1",
        "version": "23.0.0.49253-0+f101",
        "group": "Infrastructure"
      }
    }
  },
  "feeds": {
    "data": { ... }
  },
  "keywords": {
    "data": ["Running", "InUse"]
  },
  "properties": {
    "data": {
      "RunningTestsVersion": "3.9.2",
      "TestStandVersion": "2020"
    }
  },
  "workspace": "6b70e1df-ae93-4ded-9fe0-dc775732289b",
  "orgId": "e740733d-da55-4031-b32f-fb7cd8961810",
  "removed": false
}
```

### Filter Syntax (QuerySystemsRequest)

The query-systems API uses the same filter syntax as the asset service:

```
Operators: =, !=, >, >=, <, <=, and/&&, or/||, .Contains(), !.Contains()
```

**Filterable system properties:**

- `id` — System ID
- `alias` — System alias
- `createdTimestamp` / `lastUpdatedTimestamp` — ISO-8601 timestamps
- `connected.data.state` — Connection state enum (CONNECTED, DISCONNECTED, VIRTUAL, etc.)
- `grains.data.*` — System info (os, kernel, host, cpuarch, deviceclass, etc.)
- `packages.data.*` — Installed packages and versions
- `feeds.data.*` — Configured feeds
- `keywords.data` — Keywords array (`.Contains()`)
- `properties.data.*` — Custom properties
- `status.data.http_connected` — HTTP connection status

### Connection States

```
ACTIVATED_WITHOUT_CONNECTION | APPROVED | DISCONNECTED |
CONNECTED_REFRESH_PENDING | CONNECTED | CONNECTED_REFRESH_FAILED | VIRTUAL
```

### Job States

```
SUCCEEDED | OUTOFQUEUE | INQUEUE | INPROGRESS | CANCELED | FAILED
```

---

## Workflow Analysis Proposals vs. Recommended Implementation

### Workflow 2: "What was the SN of the PXI-4071 used to measure DUT SN 1234567?"

**Workflow Analysis Proposes:**

```bash
slcli system get <systemId> --projection "id,alias,hostname,workspaceId"
slcli system get-snapshot <system-id> --at-time "2025-12-01T10:30:00Z" --include assets
```

**Recommended Implementation:**

```bash
# Simple get by ID — no snapshot API exists
slcli system get <systemId> --format json
```

**Assessment:** ✅ `system get` covers the system lookup step

- The workflow analysis's `get-snapshot` requires historical state APIs that don't exist
- The cross-service correlation (test → system → asset) is best handled by Copilot's reasoning layer, not a single CLI command
- `slcli system get` provides the system details needed for the next step (`slcli asset list --model "PXI-4071"`)

---

### Workflow 4: "Find me a system that has a DMM and a scope"

**Workflow Analysis Proposes:**

```bash
slcli system find --has-asset "DMM" --has-asset "scope" --available --output table
slcli system query-by-assets --requires "DMM,scope" --match-all --show-asset-details
```

**Recommended Implementation:**

```bash
# Step 1: Use asset commands to find minionIds (already implemented)
slcli asset list --model "DMM" --connected true --format json \
  | jq -r '.[].location.minionId'

# Step 2: Query systems by those IDs
slcli system list --state CONNECTED --format json

# Step 3: Copilot correlates minionIds to system IDs client-side
```

**Assessment:** ⚠️ Cross-service correlation is a Copilot task

- The nisysmgmt API has no asset awareness — `--has-asset` would require client-side orchestration
- Creating a fake `find` command that hides multi-API calls is fragile and opinionated
- Better to provide solid `system list` with rich filtering, and let Copilot compose the workflow
- The `system list` command can filter by `connected.data.state` to find available systems

---

### Workflow 5: "Find me a system with package X installed"

**Workflow Analysis Proposes:**

```bash
slcli system find --with-package "DAQmx" --version ">= 22.0" --output table
slcli system query-by-software --package-name "DAQmx" --output json
```

**Recommended Implementation:**

```bash
# The query-systems API DOES support filtering by packages.data!
slcli system list \
  --filter 'packages.data.ni-daqmx.version != ""' \
  --format table

# Or with a convenience flag:
slcli system list \
  --has-package "ni-daqmx" \
  --state CONNECTED \
  --format table
```

**Assessment:** ✅ Achievable with existing API

- The `QuerySystemsRequest` filter explicitly documents `packages.data.*` as filterable
- A `--has-package` convenience option translates to the filter expression `packages.data.<name>.version != ""`
- No need for a separate `query-by-software` command — it's just a filter on `system list`
- For fuzzy package matching, client-side filtering is needed (query all systems with packages projection, then filter)

---

## Concrete Proposal

### Keep Command Structure Simple, Follow Established Patterns

#### Proposed structure:

```
slcli system
├── list        [query systems with filters, pagination, table/JSON]
├── get         [get detailed system info by ID]
├── summary     [connected/disconnected/virtual/pending counts]
├── update      [update system metadata: alias, keywords, properties, workspace]
├── remove      [remove/unregister systems]
├── report      [generate software/hardware report]
├── job
│   ├── list    [query jobs with filters]
│   ├── get     [get job details by ID]
│   ├── summary [active/failed/succeeded counts]
│   └── cancel  [cancel a job]
└── key
    ├── list    [list system keys by state]
    └── manage  [accept/reject/delete keys]
```

**NOT creating separate:**

- ❌ `system find` (redundant with `system list` + filters)
- ❌ `system get-snapshot` (no historical API exists)
- ❌ `system query-by-assets` (cross-service correlation is a Copilot task)
- ❌ `system query-by-software` (use `system list --has-package`)

---

## Command Specifications

### Phase 1 — Core Read Operations

#### 1. `slcli system list`

**Purpose:** Query and list systems with comprehensive filtering.

**API:** `POST /nisysmgmt/v1/query-systems`

```bash
slcli system list \
  --alias "MySystem" \
  --state CONNECTED \
  --os "Windows" \
  --has-package "ni-daqmx" \
  --has-keyword "Running" \
  --workspace "Production" \
  --filter 'grains.data.deviceclass = "PXIe Chassis"' \
  --order-by ALIAS \
  --take 25 \
  --format table
```

**Options:**

| Option             | Type               | Description                                                        |
| ------------------ | ------------------ | ------------------------------------------------------------------ |
| `--alias / -a`     | `str`              | Filter by system alias (contains match)                            |
| `--state / -s`     | `Choice`           | Filter by connection state: CONNECTED, DISCONNECTED, VIRTUAL, etc. |
| `--os`             | `str`              | Filter by OS (grains.data.kernel contains match)                   |
| `--host`           | `str`              | Filter by hostname (grains.data.host contains match)               |
| `--has-package`    | `str`              | Filter for systems with specified package installed                |
| `--has-keyword`    | `str` (repeatable) | Filter systems that have the specified keyword                     |
| `--property`       | `str` (repeatable) | Filter by property `key=value`                                     |
| `--workspace / -w` | `str`              | Filter by workspace ID or name                                     |
| `--filter`         | `str`              | Custom filter expression (API-native syntax)                       |
| `--order-by`       | `Choice`           | Order by: ALIAS, CREATED_AT, UPDATED_AT, STATE, HOST               |
| `--take / -t`      | `int`              | Number of items per page (default: 25)                             |
| `--format / -f`    | `Choice`           | Output format: table (default), json                               |

**Table columns:**

```
┌─────────────────────────────┬──────────────────┬────────────┬──────────────┬───────────────────┐
│ Alias                       │ Host             │ State      │ OS           │ ID                │
├─────────────────────────────┼──────────────────┼────────────┼──────────────┼───────────────────┤
│ PXI-TestStand-01            │ PXIE-8840-01     │ CONNECTED  │ Windows      │ HVM_domU--SN-...  │
│ Lab-Controller-West         │ DESKTOP-CTRL     │ CONNECTED  │ Windows      │ 6b70e1df-ae93...  │
│ Build-Server-03             │ buildsvr03       │ DISCONNECT │ Linux        │ e740733d-da55...  │
└─────────────────────────────┴──────────────────┴────────────┴──────────────┴───────────────────┘
```

**Filter building logic:**

- `--alias "MySystem"` → `alias.Contains("MySystem")`
- `--state CONNECTED` → `connected.data.state = "CONNECTED"`
- `--os "Windows"` → `grains.data.kernel.Contains("Windows")`
- `--host "PXIE"` → `grains.data.host.Contains("PXIE")`
- `--has-package "ni-daqmx"` → client-side filter (query with packages projection, match key names containing the search term)
- `--has-keyword "Running"` → `keywords.data.Contains("Running")`
- `--property "owner=admin"` → `properties.data.owner = "admin"`
- `--workspace` → resolve workspace ID if name given, then `workspace = "<id>"`
- Multiple filters combined with `and`

**Implementation notes:**

- `--has-package` requires special handling: the API filter `packages.data.<name>.version != ""` works for **exact** package names, but fuzzy matching needs client-side filtering. Implementation: if the package name looks like an exact match (no wildcards), use server-side filter; otherwise, fetch with packages projection and filter client-side.
- Use skip/take pagination (max 1000 per request), same pattern as `_query_all_assets()`.
- Projection: use `new(id,alias,connected,grains,keywords,properties,workspace,packages)` to minimize payload when not filtering by packages, or omit projection to get full data when `--has-package` is used.

---

#### 2. `slcli system get <system_id>`

**Purpose:** Get detailed information about a single system.

**API:** `GET /nisysmgmt/v1/systems?id=<system_id>`

```bash
slcli system get HVM_domU--SN-ec20418e --format json
slcli system get HVM_domU--SN-ec20418e --include-packages --include-feeds
```

**Options:**

| Option               | Type     | Description                          |
| -------------------- | -------- | ------------------------------------ |
| `--include-packages` | `flag`   | Include installed packages in output |
| `--include-feeds`    | `flag`   | Include configured feeds in output   |
| `--format / -f`      | `Choice` | Output format: table (default), json |

**Table output (default — without packages/feeds):**

```
System Details
──────────────────────────────────────
  ID:            HVM_domU--SN-ec20418e-d93b-2de3-b957-28e29379cade--MAC-12-9D-96-E7-CA-51
  Alias:         PXI-TestStand-01
  State:         CONNECTED
  Workspace:     6b70e1df-ae93-4ded-9fe0-dc775732289b

  System Info:
    Host:          PXIE-8840-01
    OS:            Windows (10.0.19042.928)
    Architecture:  AMD64
    Device Class:  PXIe Chassis

  Keywords:        Running, InUse

  Properties:
    RunningTestsVersion: 3.9.2
    TestStandVersion:    2020

  Timestamps:
    Created:       2026-01-15 10:30:00 UTC
    Last Updated:  2026-02-10 20:37:48 UTC
    Last Present:  2026-02-10 20:37:48 UTC
```

**With `--include-packages`:** appends a packages table:

```
  Installed Packages (42):
  ┌──────────────────────────────────┬──────────────┬──────────────────┐
  │ Package                          │ Version      │ Group            │
  ├──────────────────────────────────┼──────────────┼──────────────────┤
  │ NI-DAQmx                         │ 2023 Q1      │ Infrastructure   │
  │ NI Curl                          │ 21.3.0       │ Infrastructure   │
  │ ...                              │ ...          │ ...              │
  └──────────────────────────────────┴──────────────┴──────────────────┘
```

**Implementation notes:**

- The `GET /nisysmgmt/v1/systems?id=<id>` returns an array; take the first element.
- Grains data provides OS info: `kernel`, `osversion`, `osmanufacturer`, `host`, `cpuarch`, `deviceclass`.
- Packages data is a dict where keys are package names and values contain `displayname`, `displayversion`, `version`, `group`, `arch`, etc.
- Feeds data is a dict where keys are feed URLs and values are arrays of feed config objects.

---

#### 3. `slcli system summary`

**Purpose:** Show fleet summary — connected, disconnected, virtual, and pending counts.

**APIs:**

- `GET /nisysmgmt/v1/get-systems-summary` → `connectedCount`, `disconnectedCount`, `virtualCount`
- `GET /nisysmgmt/v1/get-pending-systems-summary` → `pendingCount`

```bash
slcli system summary --format table
slcli system summary --format json
```

**Options:**

| Option          | Type     | Description                          |
| --------------- | -------- | ------------------------------------ |
| `--format / -f` | `Choice` | Output format: table (default), json |

**Table output:**

```
System Fleet Summary
──────────────────────────────────────
  Connected:      42
  Disconnected:   8
  Virtual:        3
  Pending:        2
  ─────────────────
  Total:          55
```

**JSON output:**

```json
{
  "connectedCount": 42,
  "disconnectedCount": 8,
  "virtualCount": 3,
  "pendingCount": 2,
  "totalCount": 55
}
```

**Implementation notes:**

- Two API calls (systems summary + pending summary), can be made in sequence.
- `totalCount` is computed client-side: `connected + disconnected + virtual + pending`.

---

### Phase 2 — Mutation Operations & Jobs

#### 4. `slcli system update <system_id>`

**Purpose:** Update a system's metadata (alias, keywords, properties, workspace, location).

**API:** `PATCH /nisysmgmt/v1/systems/managed/{id}`

```bash
slcli system update HVM_domU--SN-ec20418e \
  --alias "PXI-Lab-Controller" \
  --keyword "Production" \
  --keyword "Calibrated" \
  --property "owner=jsmith" \
  --property "location=Lab-B" \
  --workspace "33eba2fe-fe42-48a1-a47f-a6669479a8aa"
```

**Options:**

| Option          | Type               | Description                                         |
| --------------- | ------------------ | --------------------------------------------------- |
| `--alias`       | `str`              | New alias for the system                            |
| `--keyword`     | `str` (repeatable) | Keywords to set (replaces all keywords)             |
| `--property`    | `str` (repeatable) | Properties as `key=value` (replaces all properties) |
| `--workspace`   | `str`              | Workspace ID or name to move system to              |
| `--scan-code`   | `str`              | New scan code                                       |
| `--location-id` | `str`              | New location ID                                     |
| `--format / -f` | `Choice`           | Output format: table (default), json                |

**Implementation notes:**

- Uses `PATCH /nisysmgmt/v1/systems/managed/{id}` with `SystemPatchRequest` body.
- Only include fields that are explicitly provided (don't send nulls for unchanged fields).
- `--keyword` is repeatable and replaces all existing keywords (API behavior).
- `--property` is repeatable, parsed with `_parse_properties()` helper (same as asset commands).
- Protected by `check_readonly_mode()`.

---

#### 5. `slcli system remove <system_id>`

**Purpose:** Remove/unregister a system from SystemLink.

**API:** `POST /nisysmgmt/v1/remove-systems`

```bash
slcli system remove HVM_domU--SN-ec20418e
slcli system remove HVM_domU--SN-ec20418e --force
```

**Options:**

| Option    | Type   | Description                                                                                                   |
| --------- | ------ | ------------------------------------------------------------------------------------------------------------- |
| `--force` | `flag` | Skip confirmation prompt; also controls API `force` parameter (immediate removal vs. wait for unregister job) |

**Behavior:**

- Without `--force`: show confirmation prompt ("Remove system 'PXI-TestStand-01' (HVM_domU--SN-...)? [y/N]"), API `force=false` (wait for unregister job).
- With `--force`: no prompt, API `force=true` (remove from database immediately).
- Protected by `check_readonly_mode()`.
- Display success: `✓ System removed: HVM_domU--SN-ec20418e`
- If API returns `failedIds`, display errors for each.

---

#### 6. `slcli system report`

**Purpose:** Generate a software or hardware report for systems.

**API:** `POST /nisysmgmt/v1/generate-systems-report`

```bash
slcli system report --type SOFTWARE --output software-report.csv
slcli system report --type HARDWARE --filter 'connected.data.state = "CONNECTED"' --output hw-report.csv
```

**Options:**

| Option          | Type     | Description                                         |
| --------------- | -------- | --------------------------------------------------- |
| `--type`        | `Choice` | Report type: SOFTWARE, HARDWARE (required)          |
| `--filter`      | `str`    | Filter expression to scope which systems to include |
| `--output / -o` | `Path`   | File path to save the report (required)             |

**Implementation notes:**

- API returns binary data (report file). Stream to output file.
- The `SystemsReportRequest` takes `type` and `filter`.
- Protected by `check_readonly_mode()` (generates a report file).

---

#### 7. `slcli system job list`

**Purpose:** Query and list jobs.

**API:** `POST /nisysmgmt/v1/query-jobs`

```bash
slcli system job list --state FAILED --format table
slcli system job list --system-id HVM_domU--SN-ec20418e --format json
slcli system job list --filter 'config.fun.Contains("nisysmgmt.set_blackout")' --take 10
```

**Options:**

| Option          | Type     | Description                                                                       |
| --------------- | -------- | --------------------------------------------------------------------------------- |
| `--system-id`   | `str`    | Filter jobs by target system ID                                                   |
| `--state`       | `Choice` | Filter by job state: SUCCEEDED, FAILED, INPROGRESS, INQUEUE, OUTOFQUEUE, CANCELED |
| `--function`    | `str`    | Filter by salt function name                                                      |
| `--filter`      | `str`    | Custom filter expression                                                          |
| `--order-by`    | `Choice` | Order by: CREATED_AT (default desc), UPDATED_AT, STATE                            |
| `--take / -t`   | `int`    | Items per page (default: 25)                                                      |
| `--format / -f` | `Choice` | Output format: table (default), json                                              |

**Table columns:**

```
┌──────────────────────────────────────┬──────────────┬──────────────────────┬──────────────────────────────┐
│ Job ID                               │ State        │ Created              │ Target System                │
├──────────────────────────────────────┼──────────────┼──────────────────────┼──────────────────────────────┤
│ 54af4b95-ea89-48df-b21f-dddf5608...  │ SUCCEEDED    │ 2026-02-10 15:15:13  │ HVM_domU--SN-ec20418e...     │
│ d762dfad-f644-4470-8ecd-6b9e0769...  │ FAILED       │ 2026-02-09 10:30:00  │ PXIE-8840-01                 │
└──────────────────────────────────────┴──────────────┴──────────────────────┴──────────────────────────────┘
```

**Filter building logic:**

- `--system-id` → `id = "<system-id>"` (Note: in job model, `id` is the target system)
- `--state FAILED` → `state = "FAILED"`
- `--function "set_blackout"` → `config.fun.Contains("set_blackout")`
- Default order: `createdTimestamp descending`

---

#### 8. `slcli system job get <job_id>`

**Purpose:** Get detailed information about a specific job.

**API:** `GET /nisysmgmt/v1/jobs?jid=<job_id>`

```bash
slcli system job get 54af4b95-ea89-48df-b21f-dddf56083476 --format json
```

**Options:**

| Option          | Type     | Description                          |
| --------------- | -------- | ------------------------------------ |
| `--format / -f` | `Choice` | Output format: table (default), json |

**Table output:**

```
Job Details
──────────────────────────────────────
  Job ID:        54af4b95-ea89-48df-b21f-dddf56083476
  State:         SUCCEEDED
  Target:        HVM_domU--SN-ec20418e-d93b-2de3-b957-28e29379cade
  Functions:     system.set_computer_desc

  Timestamps:
    Created:       2026-02-10 15:15:13 UTC
    Updated:       2026-02-10 15:15:14 UTC
    Dispatched:    2026-02-10 15:15:13 UTC

  Result:
    Return Code:   0
    Return:        SUCCESS
    Success:       true
```

---

#### 9. `slcli system job summary`

**Purpose:** Show job summary — active, failed, succeeded counts.

**API:** `GET /nisysmgmt/v1/get-jobs-summary`

```bash
slcli system job summary --format table
```

**Table output:**

```
Job Summary
──────────────────────────────────────
  Active:       3
  Succeeded:    127
  Failed:       5
  ─────────────────
  Total:        135
```

---

#### 10. `slcli system job cancel <job_id>`

**Purpose:** Cancel a running job.

**API:** `POST /nisysmgmt/v1/cancel-jobs`

```bash
slcli system job cancel 54af4b95-ea89-48df-b21f-dddf56083476
slcli system job cancel 54af4b95-ea89-48df-b21f-dddf56083476 --system-id HVM_domU--SN-ec20418e
```

**Options:**

| Option        | Type  | Description                                     |
| ------------- | ----- | ----------------------------------------------- |
| `--system-id` | `str` | Target system ID (optional, for disambiguation) |

**Implementation notes:**

- `CancelJobRequest` takes `jid` and optional `systemId`.
- Protected by `check_readonly_mode()`.
- Display success: `✓ Job cancelled: 54af4b95-...`

---

### Phase 3 — Key Management (Future)

#### 11. `slcli system key list`

**Purpose:** List system keys by state (pending, approved, denied, rejected).

**API:** `GET /nisysmgmt/v1/get-systems-keys`

```bash
slcli system key list --state pending --format table
slcli system key list --format json
```

**Options:**

| Option          | Type     | Description                                                                               |
| --------------- | -------- | ----------------------------------------------------------------------------------------- |
| `--state`       | `Choice` | Filter by key state: PENDING, APPROVED, DENIED, REJECTED (optional, shows all if omitted) |
| `--format / -f` | `Choice` | Output format: table (default), json                                                      |

---

#### 12. `slcli system key manage <system_id>`

**Purpose:** Accept, reject, or delete a system key.

**API:** `POST /nisysmgmt/v1/manage-systems-keys`

```bash
slcli system key manage HVM_domU--SN-ec20418e --action ACCEPT
slcli system key manage HVM_domU--SN-ec20418e --action REJECT
slcli system key manage HVM_domU--SN-ec20418e --action DELETE --workspace "Production"
```

**Options:**

| Option        | Type     | Description                               |
| ------------- | -------- | ----------------------------------------- |
| `--action`    | `Choice` | Action: ACCEPT, REJECT, DELETE (required) |
| `--workspace` | `str`    | Workspace ID or name (for ACCEPT action)  |

---

## Addressing Specific Workflow Requirements

### Workflow 2: "What was the SN of the PXI-4071 used to measure DUT SN 1234567?"

**Using proposed commands:**

```bash
# Step 1: Get test result (testmonitor - already exists)
slcli testmonitor result list \
  --serial-number "1234567" \
  --format json
# → Extract systemId from result

# Step 2: Get system details
slcli system get <systemId> --format json
# → System ID is the minionId for asset lookup

# Step 3: Query assets on that system (asset - already exists)
slcli asset list \
  --model "PXI-4071" \
  --connected true \
  --format json
# → Copilot correlates by minionId
```

**Assessment:** All steps achievable with `system get`. The cross-service correlation is handled by Copilot's reasoning layer, which is the correct architecture for multi-service workflows.

---

### Workflow 4: "Find me a system that has a DMM and a scope"

**Using proposed commands:**

```bash
# Step 1: Find DMM assets (asset - already exists)
slcli asset list --model "DMM" --format json
# → Extract minionIds

# Step 2: Find scope assets (asset - already exists)
slcli asset list --model "scope" --format json
# → Extract minionIds

# Step 3: Get system details for common minionIds
slcli system list --state CONNECTED --format json
# → Copilot computes intersection of minionIds with system IDs
```

**Assessment:** No new API needed. Copilot performs the set intersection logic.

---

### Workflow 5: "Find me a system with package X installed"

**Using proposed commands:**

```bash
# Direct server-side filter (exact package name)
slcli system list --has-package "ni-daqmx" --state CONNECTED --format table

# Or with custom filter
slcli system list --filter 'packages.data.ni-daqmx.version != ""' --format table

# Fuzzy package search (client-side filtering)
slcli system list --has-package "daq" --format json
# → Implementation: fetch systems with packages projection, filter client-side
# → Show all systems where any package key contains "daq"
```

**Assessment:** ✅ Fully supported. The `--has-package` option makes this a single command for the most common case. For exact package names, server-side filtering is efficient. For fuzzy matching, the command fetches all systems and filters client-side.

---

## Rationale for Simplified Structure

### 1. Aligns with API Structure

The nisysmgmt API is organized around three primary entities:

- **Systems** — The core entity (query, get, update, remove)
- **Jobs** — Operations dispatched to systems (query, create, cancel)
- **Keys** — System key management (accept, reject, delete)

This maps naturally to our command hierarchy: `system`, `system job`, `system key`.

### 2. Matches User Mental Model

Users think in terms of:

- "List all connected systems" → `system list --state CONNECTED`
- "What packages does this system have?" → `system get <id> --include-packages`
- "Find systems with DAQmx" → `system list --has-package "ni-daqmx"`
- "Check fleet health" → `system summary`

They don't think:

- "Query by software" (it's just a filter on system list)
- "Get snapshot at time" (no historical API exists)
- "Find by assets" (that's a cross-service operation for Copilot)

### 3. Reduces Command Explosion

Workflow analysis proposes:

- `system find` (new verb, overlaps with list)
- `system get-snapshot` (no API support)
- `system query-by-assets` (cross-service, not a system API feature)
- `system query-by-software` (just a filter on list)
  = **4 new specialized commands that don't generalize**

Our proposal:

- `system list` (with rich filtering including `--has-package`)
- `system get` (detailed view with optional packages/feeds)
- `system summary` (fleet overview)
- `system update` / `system remove` (mutation operations)
- `system report` (hardware/software reports)
- `system job list/get/summary/cancel` (job management)
- `system key list/manage` (key management, future)
  = **12 commands covering ALL available API endpoints**

### 4. Follows Established Patterns

```bash
# Asset commands (just implemented)
slcli asset list       # Query with filters
slcli asset get <id>   # Get details
slcli asset summary    # Fleet overview
slcli asset create     # Mutation
slcli asset update     # Mutation
slcli asset delete     # Mutation

# System commands (proposed — same pattern!)
slcli system list      # Query with filters
slcli system get <id>  # Get details
slcli system summary   # Fleet overview
slcli system update    # Mutation
slcli system remove    # Mutation (API says "remove", not "delete")
slcli system report    # Unique to systems
```

---

## Comparison Table

| Capability                | Workflow Analysis                       | Counter-Proposal                             | Assessment                        |
| ------------------------- | --------------------------------------- | -------------------------------------------- | --------------------------------- |
| List systems with filters | `system list`                           | `system list`                                | ✅ Equivalent                     |
| Get system details        | `system get`                            | `system get`                                 | ✅ Equivalent                     |
| Find by installed package | `system find --with-package` (new verb) | `system list --has-package` (filter on list) | ✅ Simpler, no new verb           |
| Find by assets            | `system query-by-assets`                | Copilot orchestration                        | ✅ Correct separation of concerns |
| Historical snapshot       | `system get-snapshot --at-time`         | Not implemented (no API)                     | ✅ Honest about API limitations   |
| Fleet summary             | Not proposed                            | `system summary`                             | ✅ Added value                    |
| Job management            | Not proposed                            | `system job list/get/summary/cancel`         | ✅ Full API coverage              |
| Key management            | Not proposed                            | `system key list/manage`                     | ✅ Full API coverage              |
| System reports            | Not proposed                            | `system report`                              | ✅ Full API coverage              |
| Update metadata           | Not proposed                            | `system update`                              | ✅ Full API coverage              |
| Remove systems            | Not proposed                            | `system remove`                              | ✅ Full API coverage              |

---

## Implementation Priority

### Phase 1: Core Read Operations (Immediate)

- 🔨 `slcli system list` — Query systems with filters, pagination, table/JSON
- 🔨 `slcli system get <id>` — Detailed system info with optional packages/feeds
- 🔨 `slcli system summary` — Connected/disconnected/virtual/pending counts

### Phase 2: Mutation Operations & Jobs (Short-term)

- 🔨 `slcli system update <id>` — Update alias, keywords, properties, workspace
- 🔨 `slcli system remove <id>` — Remove/unregister with confirmation
- 🔨 `slcli system report` — Generate software/hardware reports
- 🔨 `slcli system job list` — Query jobs with filters
- 🔨 `slcli system job get <id>` — Job details
- 🔨 `slcli system job summary` — Active/failed/succeeded counts
- 🔨 `slcli system job cancel <id>` — Cancel running jobs

### Phase 3: Key Management (Future)

- 🔨 `slcli system key list` — List keys by state
- 🔨 `slcli system key manage` — Accept/reject/delete keys

### Phase 4: Future Enhancements

- 🔨 `slcli system create-virtual` — Create virtual systems
- 🔨 Enhanced `--has-package` with version comparison operators
- 🔨 `system list --include-packages` for bulk package inventory
- 🔨 Cross-reference with assets (if unified query API becomes available)

---

## API Requirements

### Existing APIs (All Available Now)

**System APIs:**

- ✅ `POST /nisysmgmt/v1/query-systems` — Full query with filter, projection, orderBy, skip, take
- ✅ `GET /nisysmgmt/v1/systems?id=<id>` — Get single system with all data
- ✅ `GET /nisysmgmt/v1/get-systems-summary` — Connected/disconnected/virtual counts
- ✅ `GET /nisysmgmt/v1/get-pending-systems-summary` — Pending count
- ✅ `POST /nisysmgmt/v1/update-systems` — Batch update system metadata
- ✅ `PATCH /nisysmgmt/v1/systems/managed/{id}` — Update single system
- ✅ `POST /nisysmgmt/v1/remove-systems` — Remove systems
- ✅ `POST /nisysmgmt/v1/generate-systems-report` — Generate reports

**Job APIs:**

- ✅ `GET /nisysmgmt/v1/jobs` — Get jobs by systemId/jid/state/function
- ✅ `POST /nisysmgmt/v1/query-jobs` — Query jobs with filter/projection/orderBy/skip/take
- ✅ `POST /nisysmgmt/v1/jobs` — Create jobs
- ✅ `POST /nisysmgmt/v1/cancel-jobs` — Cancel jobs
- ✅ `GET /nisysmgmt/v1/get-jobs-summary` — Job summary

**Key APIs:**

- ✅ `GET /nisysmgmt/v1/get-systems-keys` — Get all keys
- ✅ `POST /nisysmgmt/v1/get-systems-keys` — Get keys for specific systems
- ✅ `POST /nisysmgmt/v1/manage-systems-keys` — Manage keys (accept/reject/delete)

### No New APIs Required

All proposed commands can be implemented using existing nisysmgmt v1 APIs through:

- **Query API:** Full filter/projection/pagination on systems and jobs
- **Package filtering:** Server-side via `packages.data.<name>` filters, or client-side for fuzzy matching
- **System metadata:** PATCH API for individual updates, POST for batch updates
- **Reports:** Existing report generation endpoint

### Implementation Notes

**For `system list --has-package`:**

- Exact name: server-side filter `packages.data.<name>.version != ""`
- Fuzzy name: query all systems with packages in projection, client-side filter by matching package key names containing the search term
- Performance consideration: fuzzy package search over many systems may require pagination through all results. Add `_warn_if_large_dataset()` similar to asset commands.

**For `system list` pagination:**

- Use `QuerySystemsRequest` with `skip`/`take` (max 1000 per request)
- Implement `_query_all_systems()` helper matching the `_query_all_assets()` pattern
- Enable interactive pagination in table mode (25 items/page, Y/n prompt)

**For `system get --include-packages`:**

- The `GET /nisysmgmt/v1/systems?id=<id>` returns packages by default
- Parse `packages.data` dict: keys are package names, values contain `displayname`, `displayversion`, `version`, `group`, `arch`, etc.
- Sort packages alphabetically by display name for table output

**For `system report`:**

- API returns binary data (likely CSV)
- Stream response to output file
- Show progress indicator for large reports

---

## Testing Strategy

### Unit Tests (tests/unit/test_system_click.py)

```python
# Test classes matching the pattern from test_asset_click.py:
class TestBuildSystemFilter:           # Filter construction from CLI options
class TestListSystems:                  # system list command variations
class TestGetSystem:                    # system get with/without packages/feeds
class TestSystemSummary:                # system summary response handling
class TestUpdateSystem:                 # system update with various options
class TestRemoveSystem:                 # system remove with/without --force
class TestSystemReport:                 # system report generation
class TestJobList:                      # system job list with filters
class TestJobGet:                       # system job get details
class TestJobSummary:                   # system job summary
class TestJobCancel:                    # system job cancel
```

### Coverage targets:

- ≥80% coverage for new code
- All filter combinations tested
- Error paths tested (404, 401, network errors)
- `--has-package` tested with exact and fuzzy matching
- Pagination tested (single page, multi-page, empty results)
- Mutation commands tested with readonly mode
