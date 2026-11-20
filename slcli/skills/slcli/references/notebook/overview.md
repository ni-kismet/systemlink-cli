# SystemLink Notebook Creation

Load this overview when the task is about a notebook that runs on SystemLink.
Stay in this file first, then load the notebook references only when the task
needs interface-specific metadata or notebook structure examples.

## Progressive loading

| Need | Read |
| --- | --- |
| Parameters cell metadata, input types, and result format | [metadata.md](./metadata.md) |
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

The parameters cell is the most critical part. Load [metadata.md](./metadata.md)
before writing or editing it. Its metadata must align:

- `papermill.parameters` keys with the parameter variable names
- `systemlink.parameters[].id` with the parameter variable names
- `systemlink.outputs[].id` with the output objects returned through `sb.glue('result', result)`
- `tags: ["parameters"]` so papermill recognizes the cell

Core rules:

- `systemlink.version` is `2` for most notebooks.
- `systemlink.version` is `1` for Work Item Automations.
- Supported parameter types are `string`, `integer`, `float`, `boolean`,
  `number`, `string[]`, and `test_monitor_result_query`.
- Add `options` to a `string` parameter for a dropdown, or `[true, false]` to
  a `boolean` parameter; the default must be one of the options.
- Add `default_display` to a `test_monitor_result_query` parameter to set the
  query builder's initial state.
- Set `systemlink.namespaces` to `["ni-testmanagement"]` for Test Monitor
  notebooks.
- Report output types are `data_frame`, `scalar`, and `array`. Action notebooks
  also declare `string` and `string[]` outputs.
- Grafana-facing notebooks can only emit `data_frame`, `scalar`, and `array`
  outputs.

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
- Each output must include `id` and `type`; `display_name` is optional.
- Output `id` values must exactly match the configured metadata.
- `scalar` outputs put the value in `value`, not `data`.
- For `data_frame`, `data.columns` and `data.values` must both be present and
  aligned. For dashboard and Grafana outputs, build `columns` with
  `pd.io.json.build_table_schema(df, index=False)["fields"]` so each column is a
  `{"name", "type"}` object.

For Systems Grid notebooks:

- the first column must be exactly `minion id`
- the first value in each row must be the system ID string
- single-column reports should usually emit only `minion id` plus one value column

## Create and publish workflow

1. Scaffold the notebook, or validate an existing one, with the bundled helper.
   Pass the interface you will publish with so its required inputs are checked:

   ```bash
   python .agents/skills/slcli/scripts/notebook_helper.py init \
     --spec notebook-spec.json --interface "Test Data Analysis" --output report.ipynb
   python .agents/skills/slcli/scripts/notebook_helper.py validate report.ipynb \
     --interface "Test Data Analysis"
   ```

   Fix every error before publishing. Review warnings such as defaults that are
   not in `options`.
2. Implement the analysis and output cells, then validate again.
3. Publish to SystemLink Enterprise with the same interface:

   ```bash
   slcli notebook manage create --file report.ipynb --name "Report" \
     --workspace WORKSPACE --interface "Test Data Analysis"
   ```

   For an existing notebook, use
   `slcli notebook manage update --id NOTEBOOK_ID --content report.ipynb`.
   Users can also publish from the browser: in **Analysis » Scripts**,
   right-click the notebook, select **Publish to SystemLink**, and choose the
   workspace and **Interface**.
4. Run it with injected parameters and confirm the glued result:

   ```bash
   slcli notebook execute sync --notebook-id NOTEBOOK_ID --workspace WORKSPACE \
     --parameters '{"result_ids": ["RESULT_ID"]}' --format json
   ```

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

- Load [metadata.md](./metadata.md) when you write or review the parameters cell or the glued result.
- Load [interfaces.md](./interfaces.md) when the notebook must satisfy a specific SystemLink interface contract.
- Load [notebook-patterns.md](./notebook-patterns.md) when you need a fuller cell-by-cell notebook template.
