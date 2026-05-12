# Notebook Interfaces

When deploying a notebook to SystemLink, you can assign an **interface** that tells
SystemLink how the notebook will be used. This affects how parameters are presented
and how the notebook is triggered.

Set the interface during creation or update:

```bash
slcli notebook manage update --id <ID> --interface "Systems Grid"
```

Prefer `create --interface ...` when you are creating a new notebook. Use
`update --interface ...` for in-place interface changes on an existing notebook.
Delete and re-create only if the server rejects the update.

## Service Availability Note

The Python client does not cover every SystemLink service. Key gaps that affect
automation interfaces (see the `nisystemlink-clients` repository for the current
service list):

- ❌ **Notebook Execution** — No Python client for checking execution status or logs
- ❌ **Routines v1/v2** — No Python client for scheduling; use REST directly or `slcli routine` in scheduled shells
- ❌ **Comments** — No Python client for adding resource annotations
- ❌ **User** — No Python client for querying users/workspaces (use REST directly)

For these services in notebooks, call the REST API directly via the `requests`
library and the service-specific SystemLink OpenAPI docs.

## Available Interfaces

Reference: [Publishing a Jupyter Notebook (NI Docs)](https://www.ni.com/docs/en-US/bundle/systemlink-enterprise/page/publishing-a-jupyter-notebook.html)

> **Note:** SystemLink Enterprise does not strictly enforce these interfaces. The specified
> parameters pass to the notebook at execution time even if you do not implement the
> required notebook metadata.

| Interface                    | Use Case                                                                                                                                                                                               | Required Inputs | Required Outputs |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | --------------- | ---------------- |
| **Assets Grid**              | Not currently in use                                                                                                                                                                                   | — | — |
| **Data Space Analysis**      | Analyze parametric data in a data space and calculate statistics                                                                                                                                       | `trace_data`: Dict[string, string] (artifact reference, e.g. `{'artifact_id': '...'}`)  `analysis_options`: string[]  `workspace_id`: string | List of analysis options: `[{display_name, id, type: scalar/vector}]` |
| **File Analysis**            | Analyze a file or create a routine with a file change trigger                                                                                                                                          | `file_ids`: string[] | No output required |
| **Periodic Execution**       | Scheduled recurring notebook (e.g. daily/hourly reports)                                                                                                                                               | No input required | No output required |
| **Resource Changed Routine** | Triggered when a resource changes (via v1 routines)                                                                                                                                                    | `context`: dict containing `routine_id`, `correlation_id`, `triggered_at`, `resource_type`, `before` (snapshot before change), `after` (snapshot after change) | No output required |
| **Specification Analysis**   | Analyze chosen specifications                                                                                                                                                                          | `spec_ids`: string[]  `product_id`: string | No output required |
| **Systems Grid**             | Report that adds a column to the Systems management grid                                                                                                                                               | No input required | `data_frame` with `minion id` as first column. Example: `[{type:"data_frame", data:{values:[["minion-id-1", 3], ["minion-id-2", 0]]}}]` |
| **Test Data Analysis**       | Analyze chosen test results                                                                                                                                                                            | `result_ids`: string[] | No output required |
| **Test Data Extraction**     | Extract parametric data from files (BDC, STDF) and transform into test results, steps, and measurements                                                                                                | `file_id`: string  `part_number`: string  `notebook_id`: string | No output required |
| **Work Item Automations**    | Perform automated actions on one or more work items for customer-specific use cases. Notebooks appear in the work items UI and can be manually triggered on selected items.                             | `work_item_ids`: string[] | No output required |
| **Work Item Operations**     | Invoked by the system through the action of a work item execution                                                                                                                                      | `workItemId`: string  `systemId`: string  (may also receive user-defined parameters) | No output required |
| **Work Item Scheduler**      | Schedule work items using a custom algorithm                                                                                                                                                           | `work_item_ids`: string[] | No output required |

### Grafana Compatibility

Notebooks whose outputs are consumed by the SystemLink Grafana plugin can only use
`data_frame` and `scalar` output types. The `string` and `string[]` types are not
supported by Grafana.

## Common Interface Patterns

### Systems Grid

Parameters typically include:

- `group_by` (string) — always support "System"
- `systems_filter` (string) — filter expression for which systems
- Domain-specific params (e.g. `package` for package version)

Output must be `data_frame` with `minion id` as the first column.

### Test Data Analysis

Parameters typically include:

- `group_by` (string)
- `program_name` (string)
- `status_filter` (string)
- `systems_filter` (string)

### Periodic Execution

No special parameter requirements. Typically uses fixed configuration
or reads from tags/files. Can be scheduled via routines (no Python client available).

**Note:** The Python client does not have a Routines service. Use `slcli routine` to
schedule notebooks, or call the Routines REST API directly.

Create a scheduled routine via CLI:

```bash
slcli routine create --api-version v1 \
  --name "Daily Report" \
  --type SCHEDULED \
  --notebook-id <NOTEBOOK_ID> \
  --schedule '{"startTime":"2026-01-01T00:00:00Z","repeat":"DAY"}'
```

Or create a scheduled routine via REST using `HttpConfigurationManager` and `requests`:

```python
import requests
from nisystemlink.clients.core import HttpConfigurationManager

config = HttpConfigurationManager.get_configuration()
base_url = config.server_uri.rstrip("/")
api_keys = getattr(config, "api_keys", {})
api_key = api_keys.get("x-ni-api-key") if isinstance(api_keys, dict) else None
if not api_key:
    raise RuntimeError("Configure an x-ni-api-key before using REST fallbacks.")
headers = {"x-ni-api-key": api_key}

payload = {
    "name": "Daily Report",
    "type": "SCHEDULED",
    "notebookId": "<NOTEBOOK_ID>",
    "schedule": {"startTime": "<START_TIME_ISO8601>", "repeat": "DAY"}
}

resp = requests.post(f"{base_url}/niroutine/v1/routines", json=payload, headers=headers)
resp.raise_for_status()
```

### Work Item Automations

Use this interface for notebooks that act on selected work items (close, update,
assign, etc.). The notebook appears in the work items UI and can be manually
triggered on one or more selected work items.

Parameters are injected by the work item system:

- `work_item_ids` (string[]) — list of selected work item IDs. Default: `[]`
- `workspace` (string) — workspace context (optional)

**Critical:** `work_item_ids` must be typed as `"string[]"` (not `"string"`),
default to `[]` in both papermill and the code cell, and `systemlink.version`
must be `1`. See the systemlink-notebook skill for the full metadata example.

**Service note:** The Python client has `work_item` service for querying and updating
work items, but does not have a `comments` service. If your automation needs to add
comments or notes, call the Comments REST API directly via `requests` library.

## Using REST When Python Clients Are Missing

If a notebook needs a service without a Python client, use `requests` and the OpenAPI docs:

```python
import requests
from nisystemlink.clients.core import HttpConfigurationManager

config = HttpConfigurationManager.get_configuration()
base_url = config.server_uri.rstrip("/")
api_keys = getattr(config, "api_keys", {})
api_key = api_keys.get("x-ni-api-key") if isinstance(api_keys, dict) else None
if not api_key:
    raise RuntimeError("Configure an x-ni-api-key before using REST fallbacks.")
headers = {"x-ni-api-key": api_key}

# Example: Add a comment to a work item (Comments service not available in Python)
comment_payload = {
    "resourceId": work_item_id,
    "resourceType": "WorkItem",
    "content": "Automated note from notebook"
}

resp = requests.post(
    f"{base_url}/nicomments/v1/comments",
    json=comment_payload,
    headers=headers
)
resp.raise_for_status()
comment = resp.json()
```

Common missing services you might need:

- **Comments** — `/nicomments/v1/comments`
- **Routines v1/v2** — `/niroutine/v1/routines` or `/niroutine/v2/routines`
- **User** — `/niuser/v1/users` or `/niuser/v1/users/query`
- **Systems State** — `/nisystemsstate/v1/states`
- **Tag Historian** — check the service-specific OpenAPI docs instead of assuming `/niapis/...`

Always check the OpenAPI docs to confirm the correct endpoint path and request schema before implementing REST calls.
