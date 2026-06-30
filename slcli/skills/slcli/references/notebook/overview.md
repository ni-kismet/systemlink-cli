# SystemLink Notebook Creation

Load this overview when the task is about a notebook that runs on SystemLink.
Stay in this file first, then load the notebook references only when the task
needs interface-specific metadata or notebook structure examples.

## Progressive loading

| Need | Read |
| --- | --- |
| Interface-specific inputs and outputs | [interfaces.md](./interfaces.md) |
| Example notebook structure and authoring patterns | [notebook-patterns.md](./notebook-patterns.md) |

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
# WRONG: Using Python snake_case (very intuitive but incorrect)
CreateResultRequest(program_name="My Test", file_ids=[file_id])

# CORRECT: Must use camelCase field names from the request model
CreateResultRequest(programName="My Test", fileIds=[file_id])

# Methods stay snake_case:
client.create_results(request)
client.create_steps(...)
```

Always check the request model constructor signature, not what feels Pythonic.

### Partial-success responses

Operations like `create_results()` and `create_steps()` return partial-success wrapper types
(e.g., `CreateStepsPartialSuccess`) even when successful. These contain both success and failure data:

```python
from nisystemlink.clients.testmonitor import TestMonitorClient
from nisystemlink.clients.testmonitor.models import CreateStepRequest

client = TestMonitorClient()
response = client.create_steps([CreateStepRequest(...)])

if response.failed:
    print(f"Failed to create {len(response.failed)} steps")
if response.created:
    print(f"Successfully created {len(response.created)} steps")
```

### Limited service coverage

The Python client does not cover all SystemLink services. The most important gaps for notebooks are:

- Notebook Execution
- Routines v1/v2
- Systems State
- Comments
- User Data
- Tag Historian

For these services, use REST calls directly via `requests` or the relevant SystemLink OpenAPI SDKs.

### Public import paths

This workflow uses two distinct Python SDK namespaces. Do not mix them:

- `nisystemlink.clients.*` for the typed Python client.
- `systemlink.clients.nisysmgmt.*` for Systems queries.

For `nisystemlink.clients`, always import from the public top-level modules, not private `_module` paths.

## Notebook Structure

Every SystemLink notebook follows this cell pattern:

1. Imports (markdown)
2. Imports (code)
3. Parameters (markdown)
4. Parameters (code)
5. Logic (markdown + code)
6. Output (markdown)
7. Output (code)
8. Instructions (markdown)

## Parameters Cell Metadata

The parameters cell is the most critical part. It must have metadata that aligns:

- `papermill.parameters` keys with the parameter variable names
- `systemlink.parameters[].id` with the parameter variable names
- `systemlink.outputs[].id` with the output objects returned through `sb.glue('result', result)`
- `tags: ["parameters"]` so papermill recognizes the cell

Core rules:

- `systemlink.version` is `2` for most notebooks.
- `systemlink.version` is `1` for Work Item Automations.
- Supported parameter types are `string`, `integer`, `float`, `boolean`, and `string[]`.
- Supported scrapbook output types are `data_frame`, `scalar`, `string`, and `string[]`.
- Grafana-facing notebooks can only emit `data_frame` and `scalar` outputs.

## Work Item Automations pattern

Notebooks with the Work Item Automations interface receive work item IDs as a list, not a comma-separated string.

Rules:

- `systemlink.version` must be `1`.
- `work_item_ids` must be typed as `string[]`.
- The default parameter value must be `[]`.
- The Python variable must also default to `[]`.
- Do not split the parameter by comma.

## Output Format

All notebooks must use `scrapbook` to return results.

Rules:

- `result` must be a list of output objects, not a dict.
- Each output must include `display_name`, `id`, `type`, and `data`.
- Output `id` values must exactly match the configured metadata.
- For `data_frame`, `data.columns` and `data.values` must both be present and aligned.

For Systems Grid notebooks:

- the first column must be exactly `minion id`
- the first value in each row must be the system ID string
- single-column reports should usually emit only `minion id` plus one value column

## Common imports

```python
import pandas as pd
import scrapbook as sb

from nisystemlink.clients.core import HttpConfigurationManager
from nisystemlink.clients.testmonitor import TestMonitorClient
from systemlink.clients.nisysmgmt.api.systems_api import SystemsApi
from systemlink.clients.nisysmgmt.models.query_systems_request import QuerySystemsRequest
```

Use `requests` directly when there is no typed client for the required service.

## Systems query pattern

The `SystemsApi` uses a projection/filter pattern.

- Projection selects which fields to return.
- Filter selects which systems to include.
- In notebook cells, prefer top-level `await` over `asyncio.run(...)`.

## When to go deeper

- Load [interfaces.md](./interfaces.md) when the notebook must satisfy a specific SystemLink interface contract.
- Load [notebook-patterns.md](./notebook-patterns.md) when you need a fuller cell-by-cell notebook template.
