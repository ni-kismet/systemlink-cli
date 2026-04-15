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

## Available Interfaces

| Interface                    | Use Case                                                                                                                                                                                               |
| ---------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| **Assets Grid**              | Report that adds a column to the Assets management grid                                                                                                                                                |
| **Data Table Analysis**      | Analysis of data table contents                                                                                                                                                                        |
| **Data Space Analysis**      | Analysis of data space contents                                                                                                                                                                        |
| **File Analysis**            | Analysis of uploaded files                                                                                                                                                                             |
| **Periodic Execution**       | Scheduled recurring notebook (e.g. daily/hourly reports)                                                                                                                                               |
| **Resource Changed Routine** | Triggered when a resource changes (via v1 routines)                                                                                                                                                    |
| **Specification Analysis**   | Analysis against specifications/limits                                                                                                                                                                 |
| **Systems Grid**             | Report that adds a column to the Systems management grid                                                                                                                                               |
| **Test Data Analysis**       | Analysis of test monitor results                                                                                                                                                                       |
| **Test Data Extraction**     | Extract and transform test data                                                                                                                                                                        |
| **Work Item Automations**    | Notebooks that can be manually executed on selected work items, or triggered by work item lifecycle events. **Use this for any notebook that acts on work items** (e.g. close, update status, assign). |
| **Work Item Operations**     | Internal operations performed on work items by the system                                                                                                                                              |
| **Work Item Scheduler**      | Scheduling logic for work items                                                                                                                                                                        |

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
or reads from tags/files. Can be scheduled via routines:

```bash
slcli routine create --api-version v1 \
  --name "Daily Report" \
  --type SCHEDULED \
  --notebook-id <NOTEBOOK_ID> \
  --schedule '{"startTime":"2026-01-01T00:00:00Z","repeat":"DAY"}'
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
