---
name: systemlink-python-test
description: >-
  Create Python-based device test applications that integrate with NI SystemLink.
  Use when the user asks to create a new test, build a test script, integrate a Python
  test with SystemLink, create a functional or parametric test, report test results
  to Test Monitor, handle work items in a test context, package a test as a nipkg,
  or deploy a test application to a SystemLink-managed system. Covers the full lifecycle:
  work item integration, product/spec resolution, test execution with step logging,
  result and file upload, asset/DUT tracking, nipkg packaging, and CI/CD deployment.
---

# SystemLink Python Test Application

Create Python-based functional/parametric device test applications that integrate
with NI SystemLink across the full test lifecycle.

## When to Use

- Creating a new Python test application for an electronic or mechanical device
- Integrating an existing test script with SystemLink (results, work items, assets)
- Setting up test result reporting with steps, measurements, limits, and inputs/outputs
- Packaging a test application as a `.nipkg` for feed deployment
- Creating work item templates for test scheduling

## Prerequisites

- Python 3.10+
- `nisystemlink-clients` package (sole communication layer — no direct HTTP calls)
- SystemLink server with Test Monitor, Asset Management, Work Order, and File services
- Valid API key with appropriate permissions

## Procedure

Follow these phases in order when creating a new test application.

### Phase 1: Project Setup

1. Create the project directory structure:
   ```
   tests/<PART_NUMBER>/
   ├── config.py              # Configuration, credentials, product specs
   ├── initialization.py      # Work item → product/DUT/system resolution
   ├── execution.py           # Result creation, step execution, file upload
   ├── simulator.py           # (Optional) simulated measurements for dev/test
   ├── main.py                # CLI entry point
   ├── requirements.txt       # nisystemlink-clients + hardware drivers
   ├── build_nipkg.bat        # Windows nipkg build script
   ├── package/
   │   ├── control            # nipkg metadata (name, version, deps)
   │   ├── instructions        # maps install/uninstall scripts
   │   ├── postinstall.bat    # creates venv + pip installs
   │   └── preuninstall.bat   # removes venv on uninstall
   └── deploy/
       ├── work-item-template.json
       └── workflow.json
   ```
2. Create `requirements.txt` with `nisystemlink-clients` and any hardware driver packages
3. Create a configuration module (see Phase 1a below)
4. **Never hard-code API keys** — use CLI args, environment variables, or system credentials

### Phase 1a: Configuration Module (`config.py`)

The configuration module handles three credential modes:

```python
import os

from nisystemlink.clients.core import HttpConfiguration

def get_configuration(
    server: str | None = None,
    api_key: str | None = None,
) -> HttpConfiguration | None:
    """Build HttpConfiguration.

    Priority:
      1. Explicit server/api_key args (CLI flags for dev use).
      2. SYSTEMLINK_SERVER_URI / SYSTEMLINK_API_KEY env vars.
      3. None — SDK auto-discovers credentials on a managed system.
    """
    server = server or os.environ.get("SYSTEMLINK_SERVER_URI")
    api_key = api_key or os.environ.get("SYSTEMLINK_API_KEY")

    if server and api_key:
        return HttpConfiguration(server_uri=server, api_key=api_key)
    return None
```

**IMPORTANT**: When `get_configuration()` returns `None`, the SDK's `HttpConfigurationManager`
auto-discovers credentials on a managed system. This is the production path. The explicit
server/api_key path is for **developer machines** that are not SystemLink-managed.

Also define `PRODUCT_SPECS` as a dict of default spec properties. These serve as fallbacks
when the product on the server doesn't have all `spec.*` properties populated:

```python
PRODUCT_SPECS = {
    "spec.voltage_low_limit": "2.5",
    "spec.voltage_high_limit": "4.2",
    # ... all spec properties with string values
}
```

### Phase 1b: CLI Entry Point (`main.py`)

The main module MUST support three execution modes via argparse:

```python
parser.add_argument("--work-item-id", help="Work item ID. Omit for interactive.")
parser.add_argument("--server", help="SystemLink server URI. For dev use.")
parser.add_argument("--api-key", help="SystemLink API key. For dev use.")
```

- **Interactive mode**: no `--work-item-id` → prompts operator
- **Automated mode**: `--work-item-id` passed → no prompts, headless
- **Developer mode**: `--server` + `--api-key` → uses explicit credentials on non-managed machine

### Phase 2: Initialization Module (`initialization.py`)

Build the initialization logic that runs before any test steps execute.

1. **Accept work item ID** — via CLI argument or interactive prompt
2. **Query the work item** — `WorkItemClient(configuration).get_work_item(work_item_id)`
3. **Resolve the product** — query by part number; if missing, create with `PRODUCT_SPECS` defaults (interactive only)
4. **Resolve spec properties** — read product `properties` for limits. Fall back to `PRODUCT_SPECS` for any missing `spec.*` key
5. **Resolve the DUT** — query Asset API using `work_item.resources.duts.selections[0].id`
6. **Resolve the system/minionId** — see Phase 2a
7. **Check fixture calibration** — warn if `PAST_RECOMMENDED_DUE_DATE`
8. **Read work item properties** — available as test parameters
9. **Validate** — abort if required parameters missing
10. **Display summary** — in interactive mode, show parameters for operator confirmation

### Phase 2a: System ID / MinionId Resolution

The `system_id` is critical — it links results and files to the correct test system.

**Two modes:**

- **Managed system** (production, `configuration is None`): Read the local minionId from disk:
  - Windows: `C:\ProgramData\National Instruments\salt\conf\minion_id`
  - Linux: `/etc/salt/minion_id`
  - The file contains a plain-text minion ID string

- **Developer system** (`configuration is not None`): Use the system resource assigned to the
  work item: `work_item.resources.systems.selections[0].id`

```python
def _resolve_system_id(work_item: WorkItem, is_dev_mode: bool) -> str | None:
    if not is_dev_mode:
        minion_id = _read_local_minion_id()
        if minion_id:
            return minion_id
    # Dev mode or local read failed: use work item system resource
    if work_item.resources and work_item.resources.systems:
        selections = work_item.resources.systems.selections or []
        if selections and selections[0].id:
            return selections[0].id
    return None
```

### Phase 3: Test Execution (`execution.py`)

Build the test runner that creates results and steps.

1. **Create a test result** with status `RUNNING` before any steps execute. Include:
   - `program_name`, `serial_number`, `part_number`, `operator`, `host_name`, `started_at`
   - `system_id` (the resolved minionId)
   - Property `workItemId` set to the originating work item ID
   - `workspace` from the work item
2. **Transition work item** to `IN_PROGRESS`
3. **Execute steps sequentially** — see Phase 3a
4. **Upload files** — see Phase 3b
5. **Update the result** — set final status, `total_time_in_seconds`, `file_ids`
6. **Transition work item** to `PENDING_APPROVAL` (NOT `CLOSED`)
   - `CLOSED` requires a separate APPROVE action from a reviewer
   - Transitioning directly to `CLOSED` in code bypasses the approval gate
   - Use `UpdateWorkItemRequest(id=work_item_id, state="PENDING_APPROVAL")`

### Phase 3a: Step Creation

**CRITICAL SDK requirements for `CreateStepRequest`:**

- `step_id` is **required** — generate with `str(uuid.uuid4())`
- `result_id` is **required**
- `name` is **required**
- Use `NamedValue` objects for `inputs` and `outputs` lists
- Use `StepData` with `Measurement` objects for parametric data
- Use `Status(status_type=StatusType.PASSED)` for status

```python
import uuid

def _build_step(result_id, name, step_type, measurement_value, low_limit, high_limit, units, ...):
    status_type = _compare(measurement_value, low_limit, high_limit)
    return CreateStepRequest(
        step_id=str(uuid.uuid4()),   # REQUIRED — must be unique
        result_id=result_id,          # REQUIRED
        name=name,                    # REQUIRED
        step_type=step_type,
        status=Status(status_type=status_type),
        inputs=[NamedValue(name="input.load_current", value="2.5 A")],
        outputs=[NamedValue(name="output.voltage", value=str(value))],
        data=StepData(
            text=name,
            parameters=[
                Measurement(
                    name=name,
                    status=status_type.value,
                    measurement=str(measurement_value),
                    lowLimit=str(low_limit),
                    highLimit=str(high_limit),
                    units=units,
                    comparisonType="GELE",
                )
            ],
        ),
        properties={
            "step.startedAt": started_at.isoformat(),
            "step.duration": str(round(duration, 3)),
            "step.limitSource": f"product:{part_number}",
        },
    )
```

**Spec lookup with fallback:**

```python
def _get_spec(product_props: dict, key: str) -> float:
    value = product_props.get(key) or PRODUCT_SPECS.get(key)
    if value is None:
        raise RuntimeError(f"Missing product spec: {key}")
    return float(value)
```

### Phase 3b: File Upload

**CRITICAL SDK requirements for `FileClient.upload_file()`:**

- The `file` parameter takes a **`BinaryIO`** object (not a file path)
- Returns a **`str`** (the file ID), not an object with `.id`
- The `metadata` parameter is a `dict[str, str]` — the SDK calls `json.dumps()` internally

```python
with open(log_path, "rb") as fp:
    file_id = file_client.upload_file(
        file=fp,
        metadata={
            "resultId": result_id,
            "workItemId": ctx.work_item_id,
            "minionId": ctx.system_id or "",
            "fileType": "test-log",
        },
        workspace=ctx.work_item.workspace,
    )
```

**CRITICAL — always open log files with `encoding="utf-8"`:**

```python
with open(log_path, "w", encoding="utf-8") as f:
    f.write(log_content)
```

Windows defaults to the system code page (e.g. cp1252). Any measurement unit that
uses a non-ASCII character — such as Ω (ohm), µ (micro), ° (degree) — will raise
`UnicodeEncodeError` at runtime if the file is opened without an explicit encoding.
This is a silent packaging defect; the test runs locally but fails when deployed to
a managed system with a different locale. Always specify `encoding="utf-8"` for every
file write.

### Phase 4: Result and Step Schema

**Required result fields (CreateResultRequest):**

| Field | Required | Notes |
|---|---|---|
| `status` | Yes | `Status(status_type=StatusType.RUNNING)` |
| `program_name` | Yes | String |
| `started_at` | No | `datetime` with UTC timezone |
| `system_id` | No | MinionId string |
| `host_name` | No | `socket.gethostname()` |
| `part_number` | No | From work item |
| `serial_number` | No | From DUT asset |
| `operator` | No | From work item `assigned_to` |
| `properties` | No | Dict — include `workItemId` |
| `keywords` | No | List of strings |
| `workspace` | No | From work item |

**Required step fields (CreateStepRequest):**

| Field | Required | Notes |
|---|---|---|
| `step_id` | **Yes** | `str(uuid.uuid4())` — MUST be provided |
| `result_id` | **Yes** | From created result |
| `name` | **Yes** | Step display name |
| `status` | No | `Status(status_type=...)` |
| `step_type` | No | `NumericLimit`, `StringValue`, `PassFail` |
| `inputs` | No | `List[NamedValue]` |
| `outputs` | No | `List[NamedValue]` |
| `data` | No | `StepData` with `Measurement` list |
| `properties` | No | Dict for `step.*` and `input.*`/`output.*` |

**UpdateResultRequest** — only `id` is required. Set `status`, `total_time_in_seconds`, `file_ids`, `properties`.

### Phase 5: SDK Client Usage

All SystemLink communication MUST use `nisystemlink-clients`. No direct HTTP.

**Verified import paths:**

```python
from nisystemlink.clients.core import HttpConfiguration
from nisystemlink.clients.testmonitor import TestMonitorClient
from nisystemlink.clients.testmonitor.models import (
    CreateResultRequest, CreateStepRequest, UpdateResultRequest,
    Measurement, NamedValue, Status, StatusType, StepData,
)
from nisystemlink.clients.product import ProductClient
from nisystemlink.clients.product.models import CreateProductRequest, QueryProductsRequest
from nisystemlink.clients.work_item import WorkItemClient
from nisystemlink.clients.work_item.models import (
    WorkItem, UpdateWorkItemRequest, UpdateWorkItemsRequest,
)
from nisystemlink.clients.assetmanagement import AssetManagementClient
from nisystemlink.clients.assetmanagement.models import (
    Asset, AssetType, CalibrationStatus, QueryAssetsRequest,
)
from nisystemlink.clients.file import FileClient
```

**SDK gotchas:**

| Pitfall | Correct Usage |
|---|---|
| `CreateStepRequest` missing `step_id` | Always set `step_id=str(uuid.uuid4())` |
| `FileClient.upload_file(file=path)` | Pass `BinaryIO`, not `Path`: `open(path, "rb")` |
| `upload_file()` returns object with `.id` | Returns `str` directly |
| `get_configuration()` returns `None` on managed system | SDK auto-discovers — do not raise error |
| `StatusType` enum values | Use `StatusType.PASSED`, not string `"PASSED"` |
| `Measurement` fields are strings | `measurement=str(value)`, `lowLimit=str(limit)` |
| Product properties may be incomplete | Fall back to `PRODUCT_SPECS` defaults |
| Work item state transitions | Use string values: `"IN_PROGRESS"`, `"PENDING_APPROVAL"` (not `"CLOSED"`) |

### Phase 6: Packaging and Deployment

Package the test application as a `.nipkg` file package for distribution through
SystemLink feeds. Refer to the **nipkg-file-package** skill
(`../nipkg-file-package/SKILL.md`) for:

- Required package layout (`debian-binary`, `control/`, `data/`)
- Valid Windows target root names (use `ProgramFiles`, not `Program Files`)
- Control file fields (`XB-Plugin: file`, architecture constraints)
- Instructions file format
- Build script pattern (nipkg CLI resolution, `nipkg pack` arguments)
- Common failure modes and fixes

**Test-application specifics** not covered by the packaging skill:

- The `postinstall.bat` should create a Python venv and pip-install `requirements.txt`.
- The `preuninstall.bat` should remove the venv directory.
- Upload with: `slcli feed package upload --feed "<feed-name>" --file dist/<package>.nipkg`
- On the target system the package installs to `C:\Program Files\NI\<package-name>\`
  and is invoked as:

```bat
"C:\Program Files\NI\<package-name>\venv\Scripts\python.exe" ^
  "C:\Program Files\NI\<package-name>\main.py" --work-item-id <ID>
```

**System provisioning**: If Python is not pre-installed on target systems, create
a Salt state file (`deploy/install.sls`) that installs Python, the nipkg, and sets
up the venv. The SLS must be **valid YAML with no Jinja templates** — SystemLink's
import-state endpoint rejects Jinja syntax. Hardcode all values directly.
See the **nipkg-file-package** skill for the SLS pattern, quoting guidance, and
the SystemLink Systems State API upload procedure. Apply via SystemLink Systems
Manager or `salt-call --local`.

### Phase 7: Work Item Template and Workflow

Create and publish a work item template with an associated workflow.

#### 7a: Workflow (`deploy/workflow.json`)

Define the state machine for work item lifecycle. Standard states:

```
NEW → DEFINED → REVIEWED → SCHEDULED → IN_PROGRESS → PENDING_APPROVAL → CLOSED
                                         ↕ PAUSED                        CANCELED
```

The workflow JSON contains:
- **`actions`**: Named actions with `executionAction` (ABORT, APPROVE, CANCEL, END, PAUSE, REJECT, RESUME, SCHEDULE, START, SUBMIT, UNSCHEDULE)
- **`states`**: Each with `substates` and `availableActions` that define valid transitions

Import with: `slcli workitem workflow import --file deploy/workflow.json -w <WORKSPACE>`
Update with: `slcli workitem workflow update --id <WORKFLOW_ID> --file deploy/workflow.json`

#### 7b: Template (`deploy/work-item-template.json`)

**IMPORTANT**: Use `partNumbers` (array of strings), NOT `partNumberFilter`.
Include `workflowId` to associate the workflow.

Always add an `executionActions` array to trigger the test automatically when a work
item is started, rather than requiring a manual run:

```json
{
  "name": "My Test Name",
  "type": "testplan",
  "templateGroup": "My Test Group",
  "partNumbers": ["PART-NUMBER-HERE"],
  "workflowId": "<WORKFLOW_ID>",
  "description": "...",
  "summary": "...",
  "resources": {
    "systems": { "count": 1, "filter": "" },
    "duts": { "count": 1, "filter": "AssetType == \"DEVICE_UNDER_TEST\"" },
    "fixtures": { "count": 0, "filter": "" }
  },
  "properties": {
    "param_key": "default_value"
  },
  "executionActions": [
    {
      "jobs": [
        {
          "functions": ["cmd.run"],
          "arguments": [
            [
              "\"C:\\Program Files\\NI\\<package-name>\\venv\\Scripts\\python.exe\" -X utf8 \"C:\\Program Files\\NI\\<package-name>\\main.py\" --work-item-id <id>",
              { "__kwarg__": true, "shell": "cmd" }
            ]
          ],
          "metadata": { "timeout": 3600, "queued": true }
        }
      ],
      "action": "START",
      "type": "JOB"
    }
  ]
}
```

**Key points for `executionActions`:**
- `type: JOB` overrides the workflow's MANUAL START — SystemLink dispatches the Salt
  job to the system assigned to the work item automatically when START is triggered
- `<id>` is a SystemLink template variable replaced at dispatch time with the work item ID
- Use `cmd.run` with `shell: cmd` and the `-X utf8` Python flag to ensure non-ASCII
  unit characters (Ω, µ, °) don't cause `UnicodeEncodeError` on Windows targets
- Set `timeout` in seconds (3600 = 1 hour); `queued: true` ensures the job is
  delivered even if the minion is temporarily offline
- The `executionActions` entry **overrides** the workflow-level action for that state;
  it does not modify the workflow itself

**Deploying / updating the template via API** (when `slcli workitem template update`
returns 400, use the raw endpoint directly):

```python
import json, ssl, urllib.request, pathlib

body = json.loads(pathlib.Path('deploy/work-item-template.json').read_text())
wrapped = {'WorkItemTemplates': [dict(body, id='<TEMPLATE_ID>')]}
data = json.dumps(wrapped).encode()
req = urllib.request.Request(
    'https://<server>/niworkitem/v1/update-workitem-templates',
    data=data, method='POST'
)
req.add_header('x-ni-api-key', '<API_KEY>')
req.add_header('Content-Type', 'application/json')
req.add_header('User-Agent', 'SystemLink-CLI/1.0')
ctx = ssl.create_default_context()
with urllib.request.urlopen(req, context=ctx) as resp:
    print(resp.read().decode())
```

Publish: `slcli workitem template create --file deploy/work-item-template.json -w <WORKSPACE>`
Update (CLI): `slcli workitem template update <TEMPLATE_ID> --file deploy/work-item-template.json`
Update (API): wrap body as `{"WorkItemTemplates": [<template_json_with_id>]}` and POST to `/niworkitem/v1/update-workitem-templates`

#### 7c: Deployment order

1. Import workflow first → get `<WORKFLOW_ID>`
2. Add `workflowId` and `executionActions` to template JSON
3. Create/update template

### Phase 8: Error Handling

| Scenario | Behavior |
|---|---|
| Step out of limits | Record FAILED, continue remaining steps |
| Hardware timeout | Retry once, abort with ERRORED and diagnostics |
| Server unreachable | Queue result locally, retry on next cycle |
| Missing serial/part number | Abort, do not create partial result |
| API key expired | Log error, halt, alert operator |

Retry transient HTTP errors (429, 500, 502, 503) with exponential backoff, up to 3 attempts.

## Key Rules

1. **`nisystemlink-clients` only** — no direct HTTP calls to SystemLink APIs
2. **No hard-coded credentials** — use CLI args, environment variables, or system credentials
3. **`step_id` on every step** — `CreateStepRequest` requires `step_id=str(uuid.uuid4())`
4. **`workItemId` on every result** — links results to originating work order
5. **Limits from product specs with fallback** — read from product properties, fall back to `PRODUCT_SPECS` defaults
6. **File upload uses `BinaryIO`** — `open(path, "rb")`, not `Path`; returns `str` file ID
7. **MinionId from local file on managed systems** — Windows: `C:\ProgramData\National Instruments\salt\conf\minion_id`, Linux: `/etc/salt/minion_id`; dev mode uses work item system resource
8. **Work item template uses `partNumbers` array** — not `partNumberFilter` string
9. **Continue after step failure** — do not abort on first failed step
10. **Three execution modes** — interactive (prompt), automated (headless), developer (explicit creds)
11. **Always `encoding="utf-8"` on log file writes** — Windows code page (cp1252) cannot encode unit symbols like Ω, µ, °; omitting `encoding=` is a latent bug that surfaces only on deployed systems
12. **Work item terminal state is `PENDING_APPROVAL`, not `CLOSED`** — the test code must NOT transition to `CLOSED`; that step belongs to a human reviewer via the APPROVE action in the workflow
13. **Use `-X utf8` when invoking Python remotely via Salt `cmd.run`** — Salt's environment does not inherit the managed system's UTF-8 locale settings; pass `python.exe -X utf8 main.py` in the execution action job command

## Full End-to-End Deployment Checklist

Use this as a repeatable checklist when creating and deploying a new Python test:

### Build
- [ ] Edit `execution.py` — all file writes use `encoding="utf-8"`
- [ ] Edit `execution.py` — work item final transition is `PENDING_APPROVAL`
- [ ] Run `build_nipkg.bat` — produces `dist/<package>_<version>_windows_all.nipkg`
- [ ] Version auto-stamped into `control` and `deploy/install.sls` by build script

### Feed
- [ ] Upload nipkg via API (field name `package`, not `file`):
  ```python
  # POST /nifeed/v1/feeds/<FEED_ID>/packages   multipart, field: package
  ```
- [ ] Verify with `GET /nifeed/v1/feeds/<FEED_ID>/packages`

### Provisioning State
- [ ] Update `deploy/install.sls` with new package version (auto-done by build script)
- [ ] Upload SLS via `POST /nisystemsstate/v1/replace-state-content`
- [ ] Dispatch `state.apply <STATE_ID>` job via `/nisysmgmt/v1/jobs` to each target system
- [ ] Poll job to `SUCCEEDED` — check `retcode == [0]`

### Work Item Template
- [ ] `executionActions` array has `action: START`, `type: JOB`, cmd.run with `-X utf8`
- [ ] Update template via `POST /niworkitem/v1/update-workitem-templates`
  with `{"WorkItemTemplates": [{...template..., "id": "<TEMPLATE_ID>"}]}`

### Smoke Test
- [ ] Create a work item from template
- [ ] Schedule + START → confirm Salt job dispatched and completes with retcode 0
- [ ] Confirm result appears in Test Monitor with PASSED/FAILED status
- [ ] Confirm work item lands in `PENDING_APPROVAL` (not `CLOSED`)
