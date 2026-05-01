# State Command Proposal: Analysis & Recommendations

**Date:** April 27, 2026  
**Context:** Planning a new `slcli state` command group against the `nisystemsstate` v1 OpenAPI

---

## Executive Summary

The `nisystemsstate` API is a good fit for a new `slcli state` command group, but the CLI should be scoped to what the service actually does:

1. The service manages **state definitions and state content**, not end-to-end deployment workflows.
2. A state can be created in two materially different ways:
   - as a package/feed definition via JSON
   - as an imported `.sls` file via multipart upload
3. State lifecycle operations matter as much as CRUD: import, export, replace content, version history, and revert are first-class operations.
4. The Swagger reviewed here does **not** expose an endpoint to install, apply, or restore a saved state onto a target system.

**Recommendation:** Add a focused `slcli state` group that covers the supported state-management lifecycle and explicitly defers apply-to-system workflows until the backing API is identified.

```bash
slcli state list
slcli state get <state-id>
slcli state create
slcli state update <state-id>
slcli state delete <state-id>
slcli state import
slcli state export <state-id>
slcli state capture <system-id>
slcli state replace-content <state-id>
slcli state history <state-id>
slcli state version <state-id> <version>
slcli state revert <state-id> <version>
```

This gives users the workflows the service actually supports today:

- discover saved states
- inspect or edit metadata
- create package/feed states
- import or replace arbitrary `.sls` content
- export a saved state or capture a system into a portable state file
- inspect history and roll back a state definition to an earlier version

---

## API Assessment

### Available Endpoints

#### State resource endpoints

- `GET /nisystemsstate/v1/states` — list states
- `POST /nisystemsstate/v1/states` — create state from JSON body
- `GET /nisystemsstate/v1/states/{stateId}` — get full state
- `PATCH /nisystemsstate/v1/states/{stateId}` — update state fields
- `DELETE /nisystemsstate/v1/states/{stateId}` — delete one state
- `POST /nisystemsstate/v1/delete-states` — delete multiple states

#### State content endpoints

- `POST /nisystemsstate/v1/import-state` — create state from uploaded `.sls`
- `POST /nisystemsstate/v1/replace-state-content` — replace `.sls` content for an existing state
- `POST /nisystemsstate/v1/export-state` — export a saved state as a file
- `POST /nisystemsstate/v1/export-state-from-system` — capture a system into a portable state file

#### State history endpoints

- `GET /nisystemsstate/v1/states/{stateId}/history` — list versions for one state
- `GET /nisystemsstate/v1/states/{stateId}/history/{version}` — fetch a specific historical version
- `POST /nisystemsstate/v1/revert-state-version` — revert a state to an older version

### Data Model Shape

The service exposes two useful response shapes:

- list metadata via `StateMetadata`
- full state documents via `StateResponse`

Important fields for CLI output:

- `id`, `name`, `description`
- `distribution`, `architecture`
- `workspace`
- `properties`
- `createdTimestamp`, `lastUpdatedTimestamp`
- `feeds[]`, `packages[]`, `systemImage`
- `containsExtraOperations`

The `containsExtraOperations` flag is especially important because it tells users whether the state is more than a package/feed manifest and likely came from imported SLS content.

### Important Constraints

#### 1. List filtering is limited

Unlike several other services already wrapped by `slcli`, `GET /states` only supports:

- `Workspace`
- `Architecture`
- `Distribution`
- `Skip`
- `Take`

There is no query endpoint with arbitrary filter expressions. That means `state list` should keep its convenience filtering narrow and honest instead of inventing a fake `--filter` surface.

#### 2. There are two creation paths

`POST /states` and `POST /import-state` are not interchangeable.

- `create` should target JSON-defined package/feed states.
- `import` should target uploaded `.sls` content.

Trying to hide both under one command would blur important validation and file-handling differences.

#### 3. Export and capture return binary content

Both `export-state` and `export-state-from-system` return a file body, not JSON metadata. The CLI needs explicit file-output behavior and should avoid trying to funnel binary content through the normal response handlers.

#### 4. “Apply to system” is not present in this spec

This API can:

- store states
- export states
- capture state content from a system
- revert a saved state definition

It does **not** expose an endpoint in this Swagger to install or restore a saved state on a target system. That workflow should be deferred until the correct execution API is identified, likely in another service.

#### 5. Some endpoints have unusual success/failure semantics

- `delete-states` may return `204` on success but `200` with an error payload on failure.
- `revert-state-version` may return `204` on success but also documents `200` for failure.

The CLI implementation should normalize those behaviors through explicit response checks rather than assuming status-code conventions used by other services.

---

## Recommended CLI Structure

### Core Resource Commands

#### `slcli state list`

Purpose: discover saved states.

Recommended options:

- `--workspace, -w TEXT` — workspace name or ID
- `--architecture [ARM|X64|X86|ANY]`
- `--distribution [NI_LINUXRT|NI_LINUXRT_NXG|WINDOWS|ANY]`
- `--take, -t INTEGER` — default 25 for table output
- `--format, -f [table|json]`

Recommended table columns:

- `Name`
- `Distribution`
- `Architecture`
- `Workspace`
- `Extra Ops`
- `Updated`
- `ID`

Implementation notes:

- Use `GET /states` directly.
- Preserve standard `slcli` behavior: paginate in table mode, show all results in JSON mode.
- Resolve workspace names to IDs using existing workspace helpers.

#### `slcli state get <state-id>`

Purpose: inspect a single state.

Recommended options:

- `--format, -f [table|json]`

Recommended table output:

- summary section for metadata
- counts for `feeds` and `packages`
- `containsExtraOperations`
- optional preview rows for feeds and packages if present

Implementation notes:

- Use `GET /states/{stateId}`.
- JSON output should preserve the full service shape.

#### `slcli state create`

Purpose: create a package/feed state without uploading an `.sls` file.

Recommended options:

- `--name TEXT` — required
- `--description TEXT`
- `--distribution [NI_LINUXRT|NI_LINUXRT_NXG|WINDOWS|ANY]` — required
- `--architecture [ARM|X64|X86|ANY]` — required
- `--workspace, -w TEXT`
- `--property TEXT` — repeatable `key=value`
- `--feed TEXT` — repeatable JSON object or `@file.json`
- `--package TEXT` — repeatable JSON object or `@file.json`
- `--system-image TEXT` — JSON object or `@file.json`
- `--request FILE` — optional raw JSON request for advanced use
- `--format, -f [table|json]`

Implementation notes:

- Use `POST /states`.
- Prefer typed convenience flags for common fields.
- Allow `--request FILE` because feeds/packages are structured objects and would otherwise make the CLI awkward.

#### `slcli state update <state-id>`

Purpose: update state metadata and JSON-defined state content.

Recommended options:

- `--name TEXT`
- `--description TEXT`
- `--distribution [NI_LINUXRT|NI_LINUXRT_NXG|WINDOWS|ANY]`
- `--architecture [ARM|X64|X86|ANY]`
- `--workspace, -w TEXT`
- `--property TEXT` — repeatable `key=value`
- `--request FILE` — raw patch object for advanced updates
- `--format, -f [table|json]`

Implementation notes:

- Use `PATCH /states/{stateId}`.
- Keep the default flag set metadata-focused in v1.
- Reserve more complex package/feed replacement for `--request FILE` unless real user demand justifies a larger typed surface.

#### `slcli state delete <state-id>`

Purpose: remove one state.

Recommended options:

- `--yes` — bypass confirmation

Implementation notes:

- Use `DELETE /states/{stateId}`.
- Follow existing confirmation patterns for destructive commands.

### Content Lifecycle Commands

#### `slcli state import`

Purpose: create a state from an uploaded `.sls` file.

Recommended options:

- `--name TEXT` — required
- `--description TEXT`
- `--distribution [NI_LINUXRT|NI_LINUXRT_NXG|WINDOWS|ANY]` — required
- `--architecture [ARM|X64|X86|ANY]` — required
- `--workspace, -w TEXT`
- `--property TEXT` — repeatable `key=value`
- `--file, -i FILE` — required `.sls` input
- `--format, -f [table|json]`

Implementation notes:

- Use multipart `POST /import-state`.
- Serialize `properties` as a JSON string because that is what the endpoint expects in form data.
- Validate the input path locally before issuing the request.

#### `slcli state replace-content <state-id>`

Purpose: replace the uploaded SLS content of an existing state.

Recommended options:

- `--file, -i FILE` — required
- `--change-description TEXT`
- `--format, -f [table|json]`

Implementation notes:

- Use multipart `POST /replace-state-content`.
- Keep this separate from `update` because it is a file upload with distinct semantics.

#### `slcli state export <state-id>`

Purpose: export a saved state to a portable file.

Recommended options:

- `--version TEXT` — optional version to export
- `--inline` — print content to stdout instead of forcing attachment handling
- `--output, -o FILE` — write the response body to disk

Implementation notes:

- Use `POST /export-state` with `stateID` and optional `stateVersion`.
- `--output` should be the normal path for binary downloads.
- If neither `--inline` nor `--output` is given, default to a sensible filename in the current directory.

#### `slcli state capture <system-id>`

Purpose: capture software state from an existing system into a portable file.

Recommended options:

- `--inline` — print content to stdout
- `--output, -o FILE` — write exported state file

Implementation notes:

- Use `POST /export-state-from-system`.
- Name this command `capture` instead of exposing the raw API name; it matches user intent better.
- This command exports a file from a system. It does **not** create a server-side state record by itself.

### History Commands

#### `slcli state history <state-id>`

Purpose: inspect version history for one state.

Recommended options:

- `--take, -t INTEGER` — default 25
- `--format, -f [table|json]`

Recommended table columns:

- `Version`
- `Description`
- `Created`
- `User ID`

Implementation notes:

- Use `GET /states/{stateId}/history`.
- Treat this like a normal list command with pagination.

#### `slcli state version <state-id> <version>`

Purpose: fetch a single historical version as a full state document.

Recommended options:

- `--format, -f [table|json]`

Implementation notes:

- Use `GET /states/{stateId}/history/{version}`.

#### `slcli state revert <state-id> <version>`

Purpose: roll the current state back to a historical version.

Recommended options:

- `--yes` — bypass confirmation

Implementation notes:

- Use `POST /revert-state-version`.
- Because the API has atypical response semantics, inspect both status code and body carefully before printing success.

---

## Commands To Defer

### Do not add `slcli state apply` or `slcli state restore` yet

Reason:

- the reviewed Swagger has no endpoint that applies a stored state to a target system
- forcing an `apply` command now would either be speculative or would hide orchestration across another service that has not been verified yet

If users need that workflow, the next design step should be identifying the execution API that actually performs deployment, not stretching `nisystemsstate` beyond its current contract.

### Defer bulk delete in v1 unless there is clear demand

The API supports `POST /delete-states`, but a single-state delete command is likely enough for the first user-facing version. Bulk delete can be added later if state cleanup becomes a frequent automation task.

---

## Implementation Plan

### Phase 1: Read path and core lifecycle

Ship first:

- `state list`
- `state get`
- `state create`
- `state update`
- `state delete`
- `state import`
- `state export`

Why first:

- covers discovery and basic authoring
- covers both creation models
- establishes JSON, multipart, and binary-response handling patterns needed by the rest of the group

### Phase 2: Capture and history workflows

Ship next:

- `state capture`
- `state replace-content`
- `state history`
- `state version`
- `state revert`

Why second:

- these commands are valuable but more specialized
- they introduce atypical file and response semantics that are easier to add once the base module exists

### Phase 3: UX and polish

Add after the command group is working:

- richer table formatting for feeds/packages in `get`
- smarter default filenames for export/capture
- optional `--request FILE` support for advanced create/update payloads if early users need it
- README examples for package-only states vs imported SLS states

---

## Implementation Notes For This Repo

### Module layout

- add `slcli/state_click.py`
- register the group from `slcli/main.py`
- add unit tests in `tests/unit/test_state_click.py`

### Shared helpers to reuse

- workspace resolution helpers from `workspace_utils.py`
- standard output validation from `cli_utils.py`
- standardized success and error handling from `utils.py`
- `UniversalResponseHandler` for normal list/get table and JSON flows

### Handling differences from existing commands

- use `UniversalResponseHandler` for `list`, `get`, and `history`
- use explicit file handling for `import`, `replace-content`, `export`, and `capture`
- use direct status validation for `delete`, `revert`, and any endpoint with inconsistent response contracts

### Tests to include

- list states in table and JSON formats
- get state by ID
- create state from JSON body
- update metadata fields
- delete with confirmation bypass
- import multipart upload
- replace-content multipart upload
- export to file and inline output
- capture from system to file and inline output
- history listing and version fetch
- revert success and revert error-body handling
- workspace name to ID resolution
- conflict and not-found error handling

---

## Open Questions

1. Which service actually performs installing or restoring a saved state onto a target system?
2. Should `state create` and `state update` expose typed `--package` and `--feed` flags immediately, or should v1 lean on `--request FILE` for structured bodies?
3. Should `state export` and `state capture` require `--output` by default for safety, or allow stdout when the response is textual SLS content?
4. Do we want a future `state validate` helper that checks local SLS syntax before upload, or should that stay outside the CLI for now?

---

## Recommended First Slice

If the goal is to land this incrementally with the least implementation risk, start with:

```bash
slcli state list
slcli state get <state-id>
slcli state import
slcli state export <state-id>
```

That first slice proves the four distinct integration patterns this service requires:

- normal list response
- normal detail response
- multipart upload
- binary download

Once those are solid, the rest of the command group becomes much more mechanical.
