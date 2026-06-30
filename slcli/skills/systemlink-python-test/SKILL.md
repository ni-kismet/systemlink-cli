---
name: systemlink-python-test
description: >-
  Create Python-based device test applications that integrate with NI
  SystemLink. Use when the task involves work items, Test Monitor results,
  assets or DUTs, result-file upload, packaging a test as a `.nipkg`, or
  deploying a test app to a managed system.
argument-hint: >-
  Describe the device test flow, required hardware or limits, and how the app
  should integrate with SystemLink.
---

# SystemLink Python Test Applications

Use this skill for end-to-end Python test applications that should run with
SystemLink work items, results, and deployment workflows.

## Reference docs

| Need | Read |
| --- | --- |
| End-to-end test app workflow | [overview.md](../slcli/references/python-test/overview.md) |
| NI package file layout and `nipkg pack` guidance | [nipkg overview](../slcli/references/nipkg/overview.md) |
| Related CLI command syntax | [commands.md](../slcli/references/commands.md#workitem--work-item-template-and-workflow-management) |

## Default approach

1. Resolve the work item, product, DUT, and target system before running steps.
2. Create the result in `RUNNING` state before executing the first step.
3. Report measurements and limits explicitly instead of burying them in free text.
4. Package only after the execution path works locally or in simulation.