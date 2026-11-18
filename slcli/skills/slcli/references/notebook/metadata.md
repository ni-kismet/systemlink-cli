# Notebook Parameters Cell and Output Contract

Load this reference when you create, edit, review, or publish a notebook that
SystemLink runs with papermill. It defines the parameters cell metadata, the
supported input and output types, and the result format SystemLink reads back.

## How SystemLink runs a notebook

1. SystemLink reads the parameters cell metadata to render inputs in the UI
   (dashboards, Grafana, routines, and the Systems Grid).
2. papermill inserts an `injected-parameters` cell directly after the cell
   tagged `parameters`. The injected values override the defaults.
3. The notebook records results with `scrapbook` (`sb.glue`). SystemLink reads
   these scraps after the execution finishes.

The parameters cell metadata, the papermill defaults, and the variables
assigned in the cell must describe the same parameters.

## Canonical parameters cell

Code cell source:

```python
my_input = ""
my_enum = "Day"
my_query = 'startedWithin <= "30.0:0:0"'
```

Cell metadata:

```json
{
  "papermill": {
    "parameters": {
      "my_enum": "Day",
      "my_input": "",
      "my_query": "startedWithin <= \"30.0:0:0\""
    }
  },
  "systemlink": {
    "namespaces": ["ni-testmanagement"],
    "outputs": [
      { "display_name": "My Output", "id": "my_output", "type": "data_frame" },
      { "display_name": "My Output2", "id": "my_output2", "type": "scalar" }
    ],
    "parameters": [
      { "display_name": "My Input", "id": "my_input", "type": "string" },
      {
        "display_name": "My Enum",
        "id": "my_enum",
        "options": ["Day", "System", "Test Program", "Operator", "Part Number", "Workspace"],
        "type": "string"
      },
      {
        "default_display": {
          "products_filter": [],
          "results_filter": [
            {
              "queryOperandUnit": "DAYS",
              "queryOperandValue": 30,
              "queryOperator": "LESS_THAN_OR_EQUAL",
              "queryOperatorName": "startedWithin"
            }
          ]
        },
        "display_name": "My Query",
        "id": "my_query",
        "type": "test_monitor_result_query"
      }
    ],
    "version": 2
  },
  "tags": ["parameters"]
}
```

JupyterLab may also add `editable`, `slideshow`, and `trusted` keys. They are
harmless and SystemLink ignores them.

## Alignment rules

- Tag exactly one code cell with `parameters`.
- Every `systemlink.parameters[].id` must be a key in `papermill.parameters`
  and must be assigned in the cell source. Use valid Python variable names.
- Keep the defaults in `papermill.parameters` and in the cell source equal.
- A `papermill.parameters` key without a `systemlink.parameters` entry is still
  injected but is not shown in the SystemLink UI.
- Every `systemlink.outputs[].id` must match the `id` of an object in the
  glued `result` list.
- Set `options` defaults to one of the listed options. Grafana discards a
  saved value that is not in the list.

## `systemlink` keys

| Key | Value |
| --- | --- |
| `version` | `2` for report and analysis notebooks. `1` for Work Item Automations and other action notebooks that glue labeled values (see below). Grafana only lists version `2` notebooks. |
| `namespaces` | List of strings. NI examples set `["ni-testmanagement"]` for notebooks that query Test Monitor data and `[]` otherwise. |
| `parameters` | Inputs rendered in the UI. Each entry needs `id`, `display_name`, and `type`. |
| `outputs` | Outputs a caller can select. Each entry needs `id`, `display_name`, and `type`. Grafana requires at least one output. |

## Parameter types

| `type` | Python default | Notes |
| --- | --- | --- |
| `string` | `""` | Text input. Add `options` for a dropdown. |
| `integer` | `0` | Use a Python `int`, not `bool`. |
| `float` | `0.0` | Use a Python `int` or `float`. |
| `number` | `0.0` | Numeric input used by NI dashboard examples. |
| `boolean` | `False` | Use a Python `bool`. Add `options: [true, false]` for a dropdown. |
| `string[]` | `[]` | Interfaces pass resource ID lists such as `result_ids` and `work_item_ids`. Do not split a comma-separated string. |
| `test_monitor_result_query` | `'startedWithin <= "30.0:0:0"'` | Renders the test result query builder. The injected value is a Dynamic LINQ filter string. Add `default_display`. |

### Grafana inputs

The Grafana notebook data source renders `number` as a number box and a
parameter with `options` as a dropdown. Every other type, including `integer`,
`float`, `boolean`, and `string[]`, renders as a text box and is sent as text.
For Grafana-facing notebooks:

- Use `number` for numeric inputs, and convert to `int` in code when needed.
- For a boolean dropdown, add `options: [true, false]` to a `boolean`
  parameter with a Python `True`/`False` default. Grafana shows `true`/`false`
  choices. Keep converting text to `bool` in code, because a saved panel or
  template variable can still send `"true"`/`"false"`.
- Accept `string[]` inputs as either a list or comma-separated text.

### Enum parameters (`options`)

Add `options` to a `string` parameter to render a dropdown. The papermill
default must be one of the options.

### Test result query parameters (`default_display`)

`default_display` sets the initial state of the query builder. It does not
change the injected value, so keep the papermill default equivalent.

| `default_display` key | Meaning |
| --- | --- |
| `products_filter` | Initial product filter rows. Usually `[]`. |
| `results_filter` | Initial result filter rows. |
| `results_filter[].queryOperatorName` | Result field, such as `startedWithin`. |
| `results_filter[].queryOperator` | Operator, such as `LESS_THAN_OR_EQUAL`. |
| `results_filter[].queryOperandValue` | Operand value, such as `30`. |
| `results_filter[].queryOperandUnit` | Operand unit, such as `DAYS`. |

`30` `DAYS` with `LESS_THAN_OR_EQUAL` on `startedWithin` corresponds to the
filter `startedWithin <= "30.0:0:0"` (a `days.hours:minutes:seconds` time
span). Pass the injected string to Test Monitor queries as the filter.

papermill logs `Unable to parse line ...` for a default that contains `<`,
`>`, or `=`. The warning only affects papermill's parameter inspection; the
injected value still overrides the default.

## Report outputs (`version: 2`)

Glue one list named `result`. Each object needs `id` and `type` that match an
entry in `systemlink.outputs`. Adding `display_name` is optional but helpful.

```python
result = [
    {
        "id": "my_output",
        "type": "data_frame",
        "data": {
            "columns": pd.io.json.build_table_schema(df, index=False)["fields"],
            "values": df.values.tolist(),
        },
    },
    {"id": "my_output2", "type": "scalar", "value": 42},
]
sb.glue("result", result)
```

| Output `type` | Result fields | Notes |
| --- | --- | --- |
| `scalar` | `value` | A single number, string, or boolean. Do not put scalars in `data`. |
| `data_frame` (table) | `data.columns`, `data.values` | `columns` is a list of `{"name", "type"}` objects. Column types are `string`, `number`, `integer`, `boolean`, or `datetime` (add `"tz": "UTC"` for UTC strings). `values` is a list of rows in column order. |
| `data_frame` (series) | `data` list of `{"format": "XY", "x", "y"}` or `{"format": "INDEX", "y"}` | Optional `config.graph` keys: `title`, `axis_labels`, `plot_labels`, `tick_labels`. |
| `array` | `data` list of strings or numbers | |
| `vector` | | Data Space Analysis outputs. See the NI Data Space example. |

`pd.io.json.build_table_schema(df, index=False)["fields"]` produces the
expected column objects. Convert values to JSON-safe types (for example,
`df.values.tolist()` and ISO 8601 strings for timestamps). Dashboards and
Grafana render only `scalar`, `data_frame`, and `array` results.

The Systems Grid reads the first column as the system (minion) ID. See
[interfaces.md](./interfaces.md).

## Action outputs (`version: 1`)

Work item and test plan automation notebooks glue individual labeled values
that SystemLink shows with the execution. Declare them in
`systemlink.outputs` with `scalar`, `string`, or `string[]` types:

```python
sb.glue("Total work items", len(work_item_ids))
sb.glue("Work items updated", ", ".join(updated_ids) or "--")
```

## Validate before publishing

Use the bundled helper to scaffold a notebook or to check an existing one. It
reports misaligned ids, unassigned defaults, type mismatches, missing
`sb.glue("result", ...)` calls, and missing interface inputs:

```bash
python .agents/skills/slcli/scripts/notebook_helper.py init \
  --spec notebook-spec.json --output report.ipynb
python .agents/skills/slcli/scripts/notebook_helper.py validate report.ipynb \
  --interface "Test Data Analysis"
```

A spec lists `title`, `version`, `namespaces`, `parameters`, and `outputs`.
Parameters accept `id`, `display_name`, `type`, and optional `default`,
`options`, and `default_display`; outputs accept `id`, `display_name`, and
`type`. `init --interface NAME` adds the inputs that interface passes.
