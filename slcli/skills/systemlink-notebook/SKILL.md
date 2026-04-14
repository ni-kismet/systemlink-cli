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
- `systemlink.outputs[].id` **must** match the key used in the result dict passed to `sb.glue`
- `tags: ["parameters"]` is **required** — this is how papermill identifies the cell
- `systemlink.version` must be `2` for most notebooks, or `1` for **Work Item Automations**
- Supported parameter types: `string`, `integer`, `float`, `boolean`, `string[]`
- Supported output types: `data_frame`, `scalar`, `string`, `string[]`

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

### Systems Grid reports

When the notebook is used as a Systems Grid column, the `data_frame` output
**must** include `minion id` as the first column. This maps rows to systems.

```python
df_dict = {
    'columns': ['minion id', 'your column name'],
    'values': df.reset_index().values.tolist()  # index = system IDs
}
```

## Common Imports

```python
# Always needed
import pandas as pd
import scrapbook as sb

# Systems queries
from systemlink.clients.nisysmgmt.api.systems_api import SystemsApi
from systemlink.clients.nisysmgmt.models.query_systems_request import QuerySystemsRequest

# Test results
from nisystemlink.clients.testmonitor import TestMonitorClient
from nisystemlink.clients.core import HttpConfigurationManager

# Assets
from nisystemlink.clients.assetmanagement import AssetManagementClient

# Direct HTTP (when no typed client exists)
import requests
from nisystemlink.clients.core import HttpConfigurationManager
config = HttpConfigurationManager.get_configuration()
base_url = config.server_uri.rstrip("/")
headers = {"x-ni-api-key": config.api_keys[0]}
```

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

# Delete and re-create (recommended when changing interface or if update fails)
slcli notebook manage delete --id <NOTEBOOK_ID> --yes
slcli notebook manage create --file notebook.ipynb --name "My Notebook" --interface "Systems Grid" --workspace "<WORKSPACE_NAME>"
```

**Important:** Always set `--interface` at creation time. The `update --interface`
command may fail on some server configurations. If you need to change the interface,
delete and re-create the notebook.

**Important:** Always determine the target workspace by running `slcli info` and
reading the `Workspace` field from the active profile. Do not assume "Default" or
prompt the user unless `slcli info` shows no workspace configured.

## Example

See [notebook-patterns.md](./references/notebook-patterns.md) for a complete
annotated example based on the NI PackageVersionExample pattern.
