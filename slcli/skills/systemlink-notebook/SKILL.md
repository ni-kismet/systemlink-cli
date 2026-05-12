---
name: systemlink-notebook
description: >-
  Create, structure, and deploy Jupyter Notebooks for NI SystemLink.
  Use when the user asks to create a notebook, report, or analysis that runs on
  SystemLink — including Systems Grid reports, test data analysis notebooks,
  asset reports, scheduled notebooks, or any notebook that uses scrapbook (sb.glue)
  to return results. Covers parameter cells, systemlink metadata, output formats,
  papermill integration, and deployment via slcli.
argument-hint: 'Describe the notebook purpose and what data it should report on'
---

# SystemLink Notebook Creation

## When to Use

- Creating a new Jupyter Notebook that will run on SystemLink
- Adding parameters or outputs to a notebook for the SystemLink Notebook Execution Service
- Building a Systems Grid column report
- Creating a test data analysis notebook
- Deploying a notebook to SystemLink via `slcli`

## Important: Python Client Quirks

The `nisystemlink-clients` Python package has a few ergonomics quirks to be aware of:

### API naming inconsistency

Client methods use Python `snake_case`, but request model fields use `camelCase`. This requires careful attention:

```python
# ❌ WRONG: Using Python snake_case (very intuitive but incorrect)
CreateResultRequest(program_name="My Test", file_ids=[file_id])

# ✅ CORRECT: Must use camelCase field names from the request model
CreateResultRequest(programName="My Test", fileIds=[file_id])

# Methods stay snake_case:
client.create_results(request)  # This is correct
client.create_steps(...)         # This is correct
```

Always check the request model constructor signature, not what "feels" Pythonic.

### Partial-success responses

Operations like `create_results()` and `create_steps()` return partial-success wrapper types
(e.g., `CreateStepsPartialSuccess`) even when successful. These contain both success and failure data:

```python
from nisystemlink.clients.testmonitor import TestMonitorClient
from nisystemlink.clients.testmonitor.models import CreateStepRequest

client = TestMonitorClient()
response = client.create_steps([CreateStepRequest(...)])

# Success and failures are both in the response
if response.failed:
    print(f"Failed to create {len(response.failed)} steps")
if response.created:
    print(f"Successfully created {len(response.created)} steps")
```

### Limited service coverage

The Python client does **not cover all SystemLink services**. The most important gaps for notebooks (see the [client repo](https://github.com/ni/nisystemlink-clients-python) for the current full list):

- ❌ **Notebook Execution** — no Python client for execution lifecycle management
- ❌ **Routines v1/v2** — no Python client for scheduling/triggering
- ❌ **Systems State** — no Python client for system health queries
- ❌ **Comments** — no Python client for resource annotations
- ❌ **User Data** — no Python client for key-value stores
- ❌ **Tag Historian** — no Python client for time-series history

For these services, use REST calls directly via the `requests` library or SystemLink's OpenAPI SDKs.

### Public import paths

This skill uses two distinct Python SDK namespaces — be careful not to mix them:

- **`nisystemlink.clients.*`** — the typed Python client (`nisystemlink-clients` package). Use public top-level imports.
- **`systemlink.clients.nisysmgmt.*`** — a separate OpenAPI-generated SDK used only for Systems queries.

For `nisystemlink.clients`, always import from the public top-level modules, not private `_module` paths:

```python
# ✅ CORRECT: Public paths (nisystemlink-clients)
from nisystemlink.clients.file import FileClient
from nisystemlink.clients.testmonitor import TestMonitorClient
from nisystemlink.clients.testmonitor.models import CreateResultRequest, CreateStepRequest

# ❌ WRONG: Private module paths (may change or be removed)
from nisystemlink.clients.testmonitor._test_monitor_client import TestMonitorClient
from nisystemlink.clients.testmonitor.models._create_result_request import CreateResultRequest

# Separate SDK — used only for Systems queries:
from systemlink.clients.nisysmgmt.api.systems_api import SystemsApi
from systemlink.clients.nisysmgmt.models.query_systems_request import QuerySystemsRequest
```

## Notebook Structure

Every SystemLink notebook follows this cell pattern:

1. **Imports (markdown)** — describe dependencies
2. **Imports (code)** — import modules
3. **Parameters (markdown)** — describe each parameter
4. **Parameters (code)** — declare parameter variables with defaults *(requires special metadata)*
5. **Logic (markdown + code)** — one or more pairs of markdown/code cells
6. **Output (markdown)** — describe the output format
7. **Output (code)** — format results and call `sb.glue('result', result)`
8. **Instructions (markdown)** — how to use the notebook in SystemLink UI

## Parameters Cell Metadata

The parameters cell is the most critical part. It **must** have this metadata structure
in the cell's `.metadata` field for SystemLink to recognize the parameters and outputs.

```json
{
  "papermill": {
    "parameters": {
      "param_name": "default_value"
    }
  },
  "systemlink": {
    "namespaces": [],
    "outputs": [
      {
        "display_name": "Human Readable Output Name",
        "id": "output_snake_case_id",
        "type": "data_frame"
      }
    ],
    "parameters": [
      {
        "display_name": "Human Readable Param Name",
        "id": "param_name",
        "type": "string"
      }
    ],
    "version": 2
  },
  "tags": ["parameters"]
}
```

### Key rules for parameter metadata

- `papermill.parameters` keys **must** match the variable names in the code cell
- `systemlink.parameters[].id` **must** match the variable names in the code cell
- `systemlink.outputs[].id` **must** match the `id` field in each output object in the
  `result` list passed to `sb.glue('result', result)`
- `tags: ["parameters"]` is **required** — this is how papermill identifies the cell
- `systemlink.version` must be `2` for most notebooks, or `1` for **Work Item Automations**
- Supported parameter types: `string`, `integer`, `float`, `boolean`, `string[]`
- Supported output types: `data_frame`, `scalar`, `string`, `string[]`
- **Grafana restriction:** Notebooks intended for use in Grafana dashboards can only
  output `data_frame` and `scalar` types. The `string` and `string[]` output types
  are not supported by the Grafana plugin.

### Work Item Automations pattern

Notebooks with the **Work Item Automations** interface receive work item IDs as a
**list** (`string[]`), not a comma-separated string. Key differences from other notebooks:

- `systemlink.version` must be `1`
- `work_item_ids` parameter type is `"string[]"` and its default value in
  `papermill.parameters` is `[]` (empty list)
- The Python variable must also default to a list: `work_item_ids = []`
- Do NOT split by comma — the parameter is already a list of strings

Example parameters cell metadata for Work Item Automations:
```json
{
  "papermill": {
    "parameters": {
      "work_item_ids": []
    }
  },
  "systemlink": {
    "outputs": [...],
    "parameters": [
      {
        "display_name": "Work item IDs",
        "id": "work_item_ids",
        "type": "string[]"
      }
    ],
    "version": 1
  },
  "tags": ["parameters"]
}
```

## Output Format (sb.glue)

All notebooks must use `scrapbook` to return results. The output cell should:

```python
import scrapbook as sb

# For data_frame outputs:
result = [{
    "display_name": "Human Readable Name",
    "id": "output_id",           # Must match systemlink.outputs[].id
    "type": "data_frame",
    "data": {
        "columns": ["column1", "column2"],
        "values": df.reset_index().values.tolist()
    }
}]
sb.glue('result', result)

# For scalar outputs:
result = [{
    "display_name": "Count",
    "id": "count_output",
    "type": "scalar",
    "data": 42
}]
sb.glue('result', result)
```

### Output validation guardrails

- Ensure `result` is a list of output objects, not a dict.
- Ensure each output object has: `display_name`, `id`, `type`, and `data`.
- Ensure `type` is one of the supported output types and matches metadata.
- Ensure output `id` exactly matches `systemlink.outputs[].id`.
- For `data_frame`, ensure `data.columns` and `data.values` are present and aligned.

For Systems Grid notebooks, validate that:

- The first column is exactly `minion id`.
- The first value in each row is the system ID string.
- For single-column grid reports, use exactly two columns: `minion id` and the report value column.
- If the notebook is intended to populate one grid column, avoid extra columns unless explicitly required.

### Systems Grid reports

When the notebook is used as a Systems Grid column, the `data_frame` output
**must** include `minion id` as the first column. This maps rows to systems.

```python
df_dict = {
    'columns': ['minion id', 'your column name'],
    'values': df.reset_index().values.tolist()  # index = system IDs
}
```

Common Systems Grid pattern for one metric per system:

```python
metric_by_system = {item['id']: item['metric_value'] for item in data.data}
df = pd.DataFrame.from_dict(metric_by_system, orient='index', columns=['metric'])

df_dict = {
  'columns': ['minion id', 'metric'],
  'values': df.reset_index().values.tolist()
}

result = [{
  'display_name': 'Metric',
  'id': 'metric_output',
  'type': 'data_frame',
  'data': df_dict
}]
sb.glue('result', result)
```

## Common Imports

```python
# Always needed
import pandas as pd
import scrapbook as sb

# Systems queries
from systemlink.clients.nisysmgmt.api.systems_api import SystemsApi
from systemlink.clients.nisysmgmt.models.query_systems_request import QuerySystemsRequest

# Test results (remember: camelCase field names in request models)
from nisystemlink.clients.testmonitor import TestMonitorClient
from nisystemlink.clients.testmonitor.models import CreateResultRequest, CreateStepRequest
from nisystemlink.clients.core import HttpConfigurationManager

# Assets
from nisystemlink.clients.assetmanagement import AssetManagementClient

# Direct HTTP (when no typed client exists or for missing services)
import requests
config = HttpConfigurationManager.get_configuration()
base_url = config.server_uri.rstrip("/")
api_keys = getattr(config, "api_keys", {})
api_key = api_keys.get("x-ni-api-key") if isinstance(api_keys, dict) else None
if not api_key:
  raise RuntimeError("Configure an x-ni-api-key before using REST fallbacks.")
headers = {"x-ni-api-key": api_key}
```

### Available Python client services

The Python client covers these **15 main services**:
- `alarm`, `artifact`, `assetmanagement`, `dataframe`, `feeds`, `file`, `notebook`,
  `notification`, `product`, `spec`, `systems`, `tag`, `test_plan`, `testmonitor`, `work_item`

### Missing services (use REST directly)

If you need these services, call the REST API directly using `requests` and the OpenAPI docs:
- **Notebook Execution** — execution lifecycle (use OpenAPI directly)
- **Routines v1/v2** — scheduling/triggering (use OpenAPI directly)
- **Systems State** — system health/connection status (use OpenAPI directly)
- **Comments** — resource annotations (use OpenAPI directly)
- **User Data** — key-value stores (use OpenAPI directly)
- **Tag Historian** — time-series history (use OpenAPI directly)
- **Auth**, **User**, and others — see full list in service-gaps documentation

## Client and API References

- **Python client repository** — full source and examples:
  https://github.com/ni/nisystemlink-clients-python
- **SystemLink OpenAPI docs** — for all services, including those without Python clients:
  https://demo-api.lifecyclesolutions.ni.com/niapis/
- **SystemLink Enterprise examples** — end-to-end patterns:
  https://github.com/ni/systemlink-enterprise-examples/

When using the Python client:
- Always check the request model constructor signature for camelCase field names (they won't match Python snake_case)
- Expect `create_*` operations to return partial-success wrapper types; inspect `.created` and `.failed` attributes
- Use public import paths from top-level modules, not private `_module` paths

When a service lacks a Python client, use OpenAPI docs to discover the endpoint path,
request body shape, and response schema before writing HTTP calls.

## Systems Query Pattern

The `SystemsApi` uses a projection/filter pattern for querying:

```python
api = SystemsApi()

# Projection selects which fields to return
projection = 'new(id, alias, state, packages.data["ni-daqmx"].displayversion)'

# Filter selects which systems to include
filter = '!string.IsNullOrEmpty(id) && packages.data.keys.Contains("ni-daqmx")'

query = QuerySystemsRequest(skip=0, projection=projection, filter=filter)
query_result = api.get_systems_by_query(query=query)
data = await query_result
```

### Async and response handling guardrails

- In notebook cells, prefer top-level `await` over `asyncio.run(...)`.
- Do not call `asyncio.run(...)` inside notebook execution cells; kernels may already have an active event loop.
- `get_systems_by_query` can return typed response objects (for example `QuerySystemsResponse`). Prefer `data.data` (or `getattr(data, 'data', ...)`) over assuming a plain dict/list.

Safe extraction pattern:

```python
query_result = api.get_systems_by_query(query=query)
data = await query_result
systems = getattr(data, 'data', None)
if systems is None:
    systems = data.get('data', data) if isinstance(data, dict) else data
```

### Common filter expressions

| Filter | Description |
|--------|-------------|
| `!string.IsNullOrEmpty(id)` | All systems (default/fallback) |
| `connected.data.state == "CONNECTED"` | Connected systems only |
| `packages.data.keys.Contains("pkg")` | Systems with a specific package |
| `grains.data.kernel == "Windows"` | Windows systems |

## Notebook Interfaces

When deploying, set the notebook interface to tell SystemLink how it will be used.
See [interfaces reference](./references/interfaces.md) for the full list.

Common interfaces:
- **Systems Grid** — report that adds a column to the Systems management grid
- **Test Data Analysis** — analysis of test monitor results
- **Periodic Execution** — scheduled recurring notebook
- **Work Item Automations** — triggered by work item state changes

## Setting Cell Metadata

The VS Code notebook editor tools do **not** persist custom cell metadata (like
`papermill`, `systemlink`, `tags`). You must write cell metadata directly into
the `.ipynb` JSON file using a Python script:

```python
import json

with open('notebook.ipynb') as f:
    nb = json.load(f)

# Find the parameters cell and set its metadata
for cell in nb['cells']:
    src = ''.join(cell.get('source', []))
    if 'parameters' in src and cell['cell_type'] == 'code':
        cell['metadata'] = {
            "papermill": {
                "parameters": {
                    "param_name": "default_value"
                }
            },
            "systemlink": {
                "namespaces": [],
                "outputs": [...],
                "parameters": [...],
                "version": 2
            },
            "tags": ["parameters"],
            "trusted": False,
            "editable": True,
            "slideshow": {"slide_type": ""}
        }
        break

with open('notebook.ipynb', 'w') as f:
    json.dump(nb, f, indent=1)
    f.write('\n')
```

**Critical:** Without this metadata, SystemLink will not display parameters or
outputs in the UI. Always verify metadata was written by inspecting the raw JSON.

Also ensure the notebook-level `kernelspec` metadata is set. Papermill requires
this to execute the notebook — without it you get
`ValueError: No kernel name found in notebook`. The VS Code notebook editor may
clear this when editing cells. Always verify and restore if needed:

```python
nb['metadata']['kernelspec'] = {
    'display_name': 'Python 3',
    'language': 'python',
    'name': 'python3'
}
```

## Deployment

Deploy via `slcli`. **Always read the user's configured workspace** from `slcli info`
and pass it with `--workspace` so the notebook lands in the correct workspace:

```bash
# 1. Read the configured workspace name from the active slcli profile
#    (look for the "Workspace" row in `slcli info` output)

# Create a new notebook with interface and workspace set at creation time (preferred)
slcli notebook manage create --file notebook.ipynb --name "My Notebook" --interface "Systems Grid" --workspace "<WORKSPACE_NAME>"

# Update content of an existing notebook
slcli notebook manage update --id <NOTEBOOK_ID> --content notebook.ipynb

# Update interface or metadata in place when needed
slcli notebook manage update --id <NOTEBOOK_ID> --interface "Systems Grid"

# Delete and re-create only as a fallback if the server rejects the update
slcli notebook manage delete --id <NOTEBOOK_ID> --yes
slcli notebook manage create --file notebook.ipynb --name "My Notebook" --interface "Systems Grid" --workspace "<WORKSPACE_NAME>"
```

**Important:** Prefer setting `--interface` at creation time, but use
`slcli notebook manage update --interface ...` for in-place interface changes when
you are updating an existing notebook. Delete and re-create only as a fallback if
the server rejects the update.

**Important:** Always determine the target workspace by running `slcli info` and
reading the `Workspace` field from the active profile. Do not assume "Default" or
prompt the user unless `slcli info` shows no workspace configured.

## Execution Validation Checklist

After create/update, always validate with a fresh (non-cached) execution before concluding success:

```bash
slcli notebook execute sync -n <NOTEBOOK_ID> -w "<WORKSPACE_NAME>" --no-cache -f json
```

Validation steps:

1. Confirm `status` is `SUCCEEDED` and `errorCode` is `NO_ERROR`.
2. Confirm output `id` and `type` match parameters-cell metadata.
3. Confirm `data.columns` and `data.values` shape matches the target interface.
4. If output still looks old, check `cachedResult`; rerun with `--no-cache`.

## Known Failure Modes and Fixes

- `ValueError: No kernel name found in notebook`: restore notebook-level `metadata.kernelspec`.
- Notebook output not shown in SystemLink UI: restore parameters-cell `systemlink` metadata and `tags: ["parameters"]`.
- Systems Grid format mismatch: ensure first column is `minion id` and output is a valid `data_frame` payload.
- Runtime loop errors (`asyncio.run() cannot be called from a running event loop`): replace `asyncio.run(...)` with top-level `await`.
- Result appears unchanged after update: rerun with `--no-cache` and re-check returned execution JSON.

## Example

See [notebook-patterns.md](./references/notebook-patterns.md) for a complete
annotated example based on the NI PackageVersionExample pattern.
