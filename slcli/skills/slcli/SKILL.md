---
name: slcli
description: >-
  Query and manage NI SystemLink resources using the slcli command-line interface.
  Use when the user asks about test results, assets, systems, work items,
  specifications, webapps, notebooks, dataframes, files, feeds, tags,
  authorization, users, example fixture authoring, example config.yaml files,
  or other SystemLink resource workflows. Use it when the user asks to create,
  validate, review, install, or troubleshoot a SystemLink example fixture.
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
- Creating, validating, or reviewing `slcli example` fixture YAML
- Troubleshooting CLI behavior, platform gating, or command selection

## Reference docs

Load only what the current task needs.

| Topic | File | When to load |
| --- | --- | --- |
| CLI command reference | [commands.md](./references/commands.md) | Looking up command syntax, options, or examples |
| Example fixture authoring | [example-authoring.md](./references/example-authoring.md) | Creating or reviewing `config.yaml`, resource references, file-backed fixtures, or validation behavior |
| Datasheet-to-spec workflow | [datasheet-workflow.md](./references/datasheet-workflow.md) | Importing specifications from PDF, CSV, or structured text |
| Minimal spec import payload | [import-specs.min.json](./references/import-specs.min.json) | Need a bundled create-compatible starter payload or conditions |
| Spec import helper | [spec_import_helper.py](./scripts/spec_import_helper.py) | Scaffold or validate a datasheet spec import payload |
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
2. Use `--format json` when the result will be filtered, transformed, or piped
   into other tools.
3. Use `--summary --group-by` for aggregation before fetching large raw result sets.
4. Use convenience filters first, then fall back to `--filter` with `--substitution` for complex queries.
5. Stay scoped to the user’s requested resource or workflow.
6. Load deeper references only when the command surface alone is not enough.
7. For example authoring or review, load `example-authoring.md` before proposing YAML.
8. Prefer workspace IDs over names in scripted workflows when an endpoint is strict about identity.
9. Use `make_api_request` from `slcli.utils` for helper scripts so auth, SSL, and error handling stay consistent.
10. For datasheet imports, default to autonomy when the product or workspace can be resolved unambiguously.

## Common command groups

| Group | Purpose | Key subcommands |
| --- | --- | --- |
| `testmonitor` | Test results and products | `result list/get`, `product list/create/update` |
| `alarm` | Alarm monitoring and lifecycle actions | `list`, `get`, `acknowledge`, `force-clear`, `delete`, `transition`, `monitor` |
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
| `webapp` | Web applications | `new`, `pack`, `publish`, `list` |
| `config` | Connection profiles | `list`, `use`, `add`, `delete` |
| `user` | User management | `list`, `get`, `create`, `update` |
| `auth` | Authorization policies | `policy list/create`, `template list` |
| `workspace` | Workspaces | `list`, `get` |
| `skill` | AI skill installation | `install`, `check` |
| `example` | Demo provisioning | `list`, `install`, `delete` |

Example package fixtures are declared as `package` resources after a `feed`
resource. Use `source.type: dummy` for deterministic packages, `file` for a
fixture-relative `.nipkg`, or `repository` for an explicit HTTPS package URL.
The repository catalog can identify packages and feeds, but package bytes must
come from a direct package URL or an existing feed download path.

## Mandatory scope resolution

Before the first resource query, resolve the profile and workspace separately.
Treat a workspace supplied by the user as a workspace identifier, never as a
profile name. Match it exactly against either the workspace name or UUID.

1. Run `slcli config list --format json` and select profiles whose `workspace`
  field matches the requested workspace name. If the user supplied a UUID,
  probe configured profiles sequentially instead. Do not infer a profile from
  a similar name such as `demo-fred` or `fred-roaster`.
2. Use the global `--profile NAME` override on every command. The option goes
  before the command group, for example:

  ```bash
  slcli --profile PROFILE_NAME workspace list --format json
  ```

  This preserves the user's global active profile.
3. If several profiles match, probe them sequentially with
  `slcli --profile NAME info --skip-health --format json`. Continue past a
  missing credential, unavailable endpoint, or permission error. Confirm the
  selected candidate with one read-only workspace query before issuing the
  actual resource query. Do not fan out the same query across candidates.
4. Use the first authorized candidate. Ask the user only when several
  candidates are authorized and the choice could change the answer.
5. With the selected profile, run `workspace list --format json` and resolve
  the requested workspace by exact name or UUID. Carry both the display name
  and UUID, but use the UUID for subsequent queries when the command accepts
  it.

When reading `slcli info --format json`, use `active_profile_name` as the
effective profile after CLI or environment overrides. `current_profile` is the
persisted config pointer and may differ. Use `api_url_source` to confirm where
the effective endpoint came from; never use `current_profile` alone to decide
which profile served a query.

## Mandatory non-interactive webapp deployment protocol

For every webapp creation, publish, redeploy, or update task, load
[deployment.md](./references/webapp/deployment.md) and follow its ordered
protocol. Do not build or upload an artifact until the deployment target has
been resolved. The protocol is non-interactive: use JSON output and bounded
inventory commands, and do not rely on table pagination or terminal prompts.

1. Discover the installed command surface before composing commands:
  ```bash
  slcli config list --format json
  slcli webapp publish -h
  slcli webapp list -h
  ```
  Installed `--help` wins over this skill and its references. Confirm every
  option on the installed CLI; `webapp publish` currently has `--id`, `--name`,
  and `--workspace`, while `webapp list` has bounded JSON output and `-f`.
  Prefer long options in generated commands after confirming they exist.
2. Resolve the effective profile and target workspace separately. Probe a
  candidate with `info --skip-health --format json`, resolve the workspace
  display name to its UUID with `workspace list --format json`, and carry the
  UUID into every later command. Never use a similar profile name as a
  substitute for workspace identity.
3. Resolve the exact webapp target before building or uploading. Use a
  bounded, filtered, non-interactive inventory, for example:
  ```bash
  slcli --profile PROFILE webapp list \
    --workspace WORKSPACE_ID --filter "Coffee Tasting" \
    --take 10 --format json
  ```
  The server-side `--filter` is a substring filter, so compare returned names
  locally. One exact name match means update that webapp with its returned ID
  by default. Multiple exact matches are ambiguous and require a selected ID.
  No exact match means report that a new resource would be created and obtain
  explicit confirmation or an explicit create instruction before using
  `--name`; never create a duplicate as an implicit fallback.
4. Inspect the project contract before running its dev server or production
  build. Read `package.json` and `angular.json`; do not append `--host` when
  the package script already supplies it. Remove or correct legacy Angular
  options such as `buildOptimizer` and `vendorChunk` when they make `ng serve`
  reject the configuration. Run the production build, detect its actual
  output directory, and verify the hosted routing, CSP, authentication, and
  service/workspace contract. The Test Monitor results service prefix is
  `/nitest/v2/query-results`, not `/nitestmonitor/v2/query-results`; do not
  hardcode `workspace=Default` when the target workspace was resolved.
5. Publish only after steps 1-4 pass. Pass the resolved workspace for a new
  webapp, or the exact existing webapp ID for an update. Capture the returned
  webapp ID, published URL, and publish timestamp in the task record.
6. Validate at three levels: deployment metadata with `webapp get`, an
  authenticated CLI query for the target workspace and required resources,
  and an authenticated browser check of the hosted URL. A reachable URL is
  not proof of an authenticated app. If the browser redirects to login or
  returns 401, report exactly: `deployment reachable, interactive hosted
  validation pending.`

## Product lookup and overview defaults

For product discovery, use this order:

1. Try an exact or likely part number with `testmonitor product list
  --part-number`.
2. Try the name and family convenience filters.
3. If a convenience filter returns `[]`, treat that as inconclusive. Scan the
  resolved workspace catalog with a bounded JSON query and match name or part
  number locally with `jq`.
4. Fetch the selected product with `testmonitor product get <PRODUCT_ID>`.

For a product overview, fetch the product record and directly linked metadata
only. Use `--summary` for counts and statuses, and grouped summaries for
profiles, programs, or other supported dimensions. For result data, use only
dimensions exposed by the command, such as `status` and `programName`. Fetch
only the latest 5 to 10 results, projecting relevant fields with `jq`. Fetch
full result details only for a specific run or failure. Record an explicit UTC
`as of` time and treat counts from separate live queries as separate
observations.
