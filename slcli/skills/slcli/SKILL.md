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
| Minimal spec import payload | [import-specs.min.json](./references/import-specs.min.json) | Need a bundled create-compatible starter payload or conditions |
| Spec import helper | [spec_import_helper.py](./scripts/spec_import_helper.py) | Scaffold or validate a datasheet spec import payload |
| Filtering guide | [filtering.md](./references/filtering.md) | Advanced filters, LINQ syntax, and query composition |
| Analysis recipes | [analysis-recipes.md](./references/analysis-recipes.md) | Multi-step analysis workflows and reporting patterns |
| Troubleshooting | [troubleshooting.md](./references/troubleshooting.md) | SSL, workspace IDs, encoding, or scripting pitfalls |
| Eval workflow | [evals/README.md](./evals/README.md) | Developing, grading, and benchmarking this skill |
| Notebook workflow | [notebook/overview.md](./references/notebook/overview.md) | Creating notebooks for SystemLink |
| Webapp workflow | [webapp/overview.md](./references/webapp/overview.md) | Hosted Angular webapp scaffolding and deployment |
| Python test workflow | [python-test/overview.md](./references/python-test/overview.md) | Python test app structure and deployment |
| Job debugging | [job-debugging/overview.md](./references/job-debugging/overview.md) | Salt job triage and recovery |
| NI package files | [nipkg/overview.md](./references/nipkg/overview.md) | File-package assembly and `nipkg pack` guidance |

## Default approach

1. Prefer long-form flags in generated commands.
2. Use `-f json` when the result will be filtered, transformed, or piped into other tools.
3. Use `--summary --group-by` for aggregation before fetching large raw result sets.
4. Use convenience filters first, then fall back to `--filter` with `--substitution` for complex queries.
5. Stay scoped to the user’s requested resource or workflow.
6. Load deeper references only when the command surface alone is not enough.
7. Prefer workspace IDs over names in scripted workflows when an endpoint is strict about identity.
8. Use `make_api_request` from `slcli.utils` for helper scripts so auth, SSL, and error handling stay consistent.
9. For datasheet imports, default to autonomy when the product or workspace can be resolved unambiguously.

## Common command groups

| Group | Purpose | Key subcommands |
| --- | --- | --- |
| `testmonitor` | Test results and products | `result list/get`, `product list/create/update` |
| `spec` | Specifications | `list`, `query`, `get`, `create`, `import`, `export` |
| `asset` | Assets and calibration | `list`, `get`, `summary`, `calibration` |
| `system` | System fleet | `list`, `get`, `compare`, `summary`, `job` |
| `tag` | Tag read/write | `list`, `get-value`, `set-value`, `create` |
| `routine` | Event-action routines | `list`, `create`, `enable/disable` |
| `comment` | Resource comments | `list`, `add`, `update`, `delete` |
| `workitem` | Work items and workflows | `list`, `create`, `schedule`, `template`, `workflow` |
| `file` | File management | `list`, `upload`, `download`, `query`, `watch` |
| `notebook` | Jupyter notebooks | `manage list/create`, `execute start/sync` |
| `feed` | Package feeds | `list`, `create`, `package upload` |
| `customfield` | Dynamic form fields | `list`, `create`, `export`, `edit` |
| `template` | Test plan templates | `list`, `import`, `export` |
| `webapp` | Web applications | `init`, `pack`, `publish`, `list` |
| `config` | Connection profiles | `list`, `use`, `add`, `delete` |
| `user` | User management | `list`, `get`, `create`, `update` |
| `auth` | Authorization policies | `policy list/create`, `template list` |
| `workspace` | Workspaces | `list`, `get` |
| `skill` | AI skill installation | `install` |
| `example` | Demo provisioning | `list`, `install`, `delete` |
