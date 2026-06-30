---
name: slcli
description: >-
  Query and manage NI SystemLink resources using the slcli command-line interface.
  Use when the user asks about test results, assets, systems, work items,
  specifications, webapps, notebooks, dataframes, files, feeds, tags,
  authorization, users, or other SystemLink resource workflows.
argument-hint: >-
  Describe the SystemLink workflow you want to inspect, automate, scaffold, or
  troubleshoot.
---

# SystemLink CLI

Use this skill when the task is primarily about `slcli` commands or a
SystemLink resource workflow that should be driven from the CLI.

## When to use it

- Querying or managing SystemLink resources through `slcli`
- Looking up exact command syntax, flags, or JSON output patterns
- Building command sequences for analysis, provisioning, packaging, or cleanup
- Troubleshooting CLI behavior, platform gating, or command selection

## Reference docs

Load only what the current task needs.

| Topic | File | When to load |
| --- | --- | --- |
| CLI command reference | [commands.md](./references/commands.md) | Looking up command syntax, options, or examples |
| Datasheet-to-spec workflow | [datasheet-workflow.md](./references/datasheet-workflow.md) | Importing specifications from PDF, CSV, or structured text |
| Filtering guide | [filtering.md](./references/filtering.md) | Advanced filters, LINQ syntax, and query composition |
| Analysis recipes | [analysis-recipes.md](./references/analysis-recipes.md) | Multi-step analysis workflows and reporting patterns |
| Troubleshooting | [troubleshooting.md](./references/troubleshooting.md) | SSL, workspace IDs, encoding, or scripting pitfalls |
| Notebook workflow | [notebook/overview.md](./references/notebook/overview.md) | Creating notebooks for SystemLink |
| Webapp workflow | [webapp/overview.md](./references/webapp/overview.md) | Hosted Angular webapp scaffolding and deployment |
| Python test workflow | [python-test/overview.md](./references/python-test/overview.md) | Python test app structure and deployment |
| Job debugging | [job-debugging/overview.md](./references/job-debugging/overview.md) | Salt job triage and recovery |
| NI package files | [nipkg/overview.md](./references/nipkg/overview.md) | File-package assembly and `nipkg pack` guidance |

## Default approach

1. Prefer long-form flags in generated commands.
2. Use JSON output when the result will be filtered or transformed.
3. Stay scoped to the user’s requested resource or workflow.
4. Load deeper references only when the command surface alone is not enough.