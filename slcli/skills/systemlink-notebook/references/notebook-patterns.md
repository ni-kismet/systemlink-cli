# Notebook Patterns

Annotated examples of common SystemLink notebook patterns.

---

## Pattern 1: Systems Grid Column Report

This is the most common pattern. The notebook queries system data and returns
a `data_frame` output that the Systems Grid can display as a column.

### Full annotated example (Package Version)

**Cell 1 — Imports description (markdown)**
```markdown
### Imports
Import Python modules for executing the notebook.
 - Pandas is used for building and handling dataframes.
 - Scrapbook is used for recording data for the Notebook Execution Service.
 - SystemsApi is an NI provided package for communicating with the SystemLink Systems service.
```

**Cell 2 — Imports (code)**
```python
import pandas as pd
import scrapbook as sb

from systemlink.clients.nisysmgmt.api.systems_api import SystemsApi
from systemlink.clients.nisysmgmt.models.query_systems_request import QuerySystemsRequest
```

**Cell 3 — Parameters description (markdown)**
```markdown
### Parameters
 - `group_by`: The property by which data is grouped. For the data to appear
   as a column in the Systems Grid, we must support 'System' here.
 - `package`: The Package Name of the software to display the version of.
 - `systems_filter`: A filter specifying which systems to query.
   An empty filter matches all systems.
```

**Cell 4 — Parameters (code, with metadata)**

The code cell declares variables with defaults:
```python
group_by = "System"
package = "ni-daqmx"
systems_filter = ""
```

The cell metadata must include:
```json
{
  "papermill": {
    "parameters": {
      "group_by": "System",
      "package": "ni-daqmx",
      "systems_filter": ""
    }
  },
  "systemlink": {
    "namespaces": [],
    "outputs": [
      {
        "display_name": "Package Version",
        "id": "package_version",
        "type": "data_frame"
      }
    ],
    "parameters": [
      {
        "display_name": "Group by",
        "id": "group_by",
        "type": "string"
      },
      {
        "display_name": "Package",
        "id": "package",
        "type": "string"
      },
      {
        "display_name": "Systems Filter",
        "id": "systems_filter",
        "type": "string"
      }
    ],
    "version": 2
  },
  "tags": ["parameters"]
}
```

**Cell 5 — Query description (markdown)**
```markdown
### Query for Systems with the specified package and get the Package Version
```

**Cell 6 — Query (code)**
```python
api = SystemsApi()

projection = f'new(id, packages.data["{package}"].displayversion, packages.data["{package}"].version)'
filter = (systems_filter or "!string.IsNullOrEmpty(id)") + f' && packages.data.keys.Contains("{package}")'

query_sys_request = QuerySystemsRequest(skip=0, projection=projection, filter=filter)
query_result = api.get_systems_by_query(query=query_sys_request)
data = await query_result
```

**Cell 7 — Dataframe description (markdown)**
```markdown
### Extract Package data from query results and create pandas dataframe
```

**Cell 8 — Dataframe (code)**
```python
pkg_version = { item['id'] : item['displayversion'] for item in data.data }
df = pd.DataFrame.from_dict(pkg_version, orient='index', columns=['Package Version'])
df
```

**Cell 9 — Output description (markdown)**
```markdown
### Convert dataframe to result format that the Systems Grid can interpret
```

**Cell 10 — Output with sb.glue (code)**
```python
df_dict = {
    'columns': ['minion id', 'package version'],
    'values': df.reset_index().values.tolist()
}

result = [{
    "display_name": "Package Version",
    "id": "package_version",
    "type": "data_frame",
    "data": df_dict
}]

sb.glue('result', result)
```

**Cell 11 — Usage instructions (markdown)**
```markdown
### View the output of this report in the Systems Grid
1. Upload this notebook to the reports folder in SystemLink Jupyter
2. From the Systems page, press the edit grid button
3. Press '+ ADD' and select 'Notebook' as the data source
4. Select this report, choose 'Package Version' as the output
5. Enter the package name and update interval
6. Enter a column name and press Done
```

---

## Pattern 2: Test Data Analysis

Query test results and return a summary. Uses `nisystemlink.clients.testmonitor`.

**Parameters cell metadata:**
```json
{
  "papermill": {
    "parameters": {
      "group_by": "System",
      "program_name": "",
      "status_filter": "",
      "systems_filter": ""
    }
  },
  "systemlink": {
    "namespaces": [],
    "outputs": [
      {
        "display_name": "Test Summary",
        "id": "test_summary",
        "type": "data_frame"
      }
    ],
    "parameters": [
      {"display_name": "Group by", "id": "group_by", "type": "string"},
      {"display_name": "Program Name", "id": "program_name", "type": "string"},
      {"display_name": "Status Filter", "id": "status_filter", "type": "string"},
      {"display_name": "Systems Filter", "id": "systems_filter", "type": "string"}
    ],
    "version": 2
  },
  "tags": ["parameters"]
}
```

**Query pattern:**
```python
from nisystemlink.clients.testmonitor import TestMonitorClient
from nisystemlink.clients.core import HttpConfigurationManager

config = HttpConfigurationManager.get_configuration()
client = TestMonitorClient(config)

# Use the client to query results with filters
results = client.get_results(
    filter=f'status.statusType == "{status_filter}"' if status_filter else None,
    take=1000
)
```

**Output pattern (same as Pattern 1):**
```python
result = [{
    "display_name": "Test Summary",
    "id": "test_summary",
    "type": "data_frame",
    "data": {
        "columns": ["minion id", "pass rate"],
        "values": df.reset_index().values.tolist()
    }
}]
sb.glue('result', result)
```

---

## Pattern 3: Scalar Output

When the notebook returns a single value instead of a table.

**Output metadata:**
```json
{
  "systemlink": {
    "outputs": [
      {
        "display_name": "Total Count",
        "id": "total_count",
        "type": "scalar"
      }
    ]
  }
}
```

**Output code:**
```python
result = [{
    "display_name": "Total Count",
    "id": "total_count",
    "type": "scalar",
    "data": len(df)
}]
sb.glue('result', result)
```
