---
name: systemlink-notebook
description: >-
  Create, structure, and deploy Jupyter notebooks for NI SystemLink. Use when
  the task is about parameter cells, `sb.glue` outputs, Systems Grid reports,
  scheduled notebook execution, or notebook deployment via `slcli`.
argument-hint: >-
  Describe what the notebook should report, which SystemLink data it should use,
  and how the result should appear in SystemLink.
---

# SystemLink Notebooks

Use this skill when the notebook will run on SystemLink rather than as a purely
local exploratory notebook.

## Reference docs

| Need | Read |
| --- | --- |
| Overview and workflow | [overview.md](../slcli/references/notebook/overview.md) |
| Interface-specific behavior | [interfaces.md](../slcli/references/notebook/interfaces.md) |
| Example notebook structures | [notebook-patterns.md](../slcli/references/notebook/notebook-patterns.md) |
| Related CLI command syntax | [commands.md](../slcli/references/commands.md#notebook--jupyter-notebook-management-and-execution) |

## Default approach

1. Define the parameter cell and SystemLink metadata first.
2. Keep the output contract explicit with `sb.glue('result', ...)`.
3. Use SystemLink-compatible parameter and output IDs from the start.
4. Prefer the minimal interface-specific metadata that matches the notebook’s role.