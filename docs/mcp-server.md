# slcli MCP Server

The slcli MCP (Model Context Protocol) server lets AI assistants — VS Code
Copilot Agent mode, Claude Desktop, Cursor, and any other MCP-compatible
client — call SystemLink APIs directly as structured tools.

## How it works

```
AI assistant (VS Code / Claude Desktop / Cursor)
  │
  │  MCP stdio protocol
  ▼
slcli mcp serve  ←── reads credentials from keyring / active profile
  │
  │  HTTPS + API key
  ▼
SystemLink server
```

The server runs as a subprocess on your local machine. The MCP client
(VS Code, Claude Desktop, etc.) spawns it on demand by executing:

```
slcli mcp serve
```

Because the server runs locally it reuses your existing `slcli` credentials
and profile — no separate authentication step is needed, and your API keys
are never sent to any third party.

## Installation

The `mcp` package is included in the `slcli` dev dependencies. If you are
using a standalone binary or a minimal source install, add it explicitly:

```bash
pip install "mcp>=1.0"
# or in a Poetry project:
poetry add mcp
```

## Registering with AI clients

Use `slcli mcp install` to write the correct configuration file for your
client automatically:

```bash
# VS Code Copilot Agent mode (.vscode/mcp.json in the current directory)
slcli mcp install

# Claude Desktop (global platform config file)
slcli mcp install --target claude

# Cursor (.cursor/mcp.json in the current directory)
slcli mcp install --target cursor

# Codex CLI (.codex/mcp.json in the current directory)
slcli mcp install --target codex

# All four at once
slcli mcp install --target all
```

The install command reads any existing config file and **merges** the slcli
entry — it will not overwrite other servers you have already configured.

### Manual configuration

If you prefer to edit config files by hand, add the following entry.

#### VS Code — `.vscode/mcp.json`

```json
{
  "servers": {
    "slcli": {
      "type": "stdio",
      "command": "slcli",
      "args": ["mcp", "serve"]
    }
  }
}
```

#### Claude Desktop — `claude_desktop_config.json`

| Platform | Path                                                              |
| -------- | ----------------------------------------------------------------- |
| macOS    | `~/Library/Application Support/Claude/claude_desktop_config.json` |
| Windows  | `%APPDATA%\Claude\claude_desktop_config.json`                     |
| Linux    | `~/.config/claude/claude_desktop_config.json`                     |

```json
{
  "mcpServers": {
    "slcli": {
      "command": "slcli",
      "args": ["mcp", "serve"]
    }
  }
}
```

#### Cursor — `.cursor/mcp.json`

```json
{
  "mcpServers": {
    "slcli": {
      "command": "slcli",
      "args": ["mcp", "serve"]
    }
  }
}
```

#### OpenAI Codex CLI — `.codex/mcp.json`

```json
{
  "mcpServers": {
    "slcli": {
      "command": "slcli",
      "args": ["mcp", "serve"]
    }
  }
}
```

After editing the config file, restart (or reload) the AI client to pick up
the new server.

## SSE transport

Pass `--transport sse` to run the server over HTTP/SSE instead of stdio.
This is useful for browser-based tooling, the
[MCP Inspector](https://github.com/modelcontextprotocol/inspector), or any
client that prefers a persistent HTTP connection over process spawning.

```bash
# Start the server (default: http://127.0.0.1:8000/sse)
slcli mcp serve --transport sse

# Custom host/port
slcli mcp serve --transport sse --host 0.0.0.0 --port 9000

# In a second terminal, launch the inspector UI
npx @modelcontextprotocol/inspector
```

Then open the inspector in your browser and connect to
`http://127.0.0.1:8000/sse` (SSE transport). You can browse all available
tools, call them with custom arguments, and inspect the JSON responses.

The server uses your existing Poetry / venv Python environment,
so no `uv` or PyPI access is needed.

## Available tools

### Phase 1 — Read-only foundation

| Tool                      | Description                                                           |
| ------------------------- | --------------------------------------------------------------------- |
| `workspace_list`          | List workspaces, returns id/name/enabled/default                      |
| `tag_list`                | List tags by path glob and/or workspace, includes current value       |
| `tag_get`                 | Get a single tag by exact path (metadata + current value)             |
| `system_list`             | List managed systems, optionally filter by connection state           |
| `asset_list`              | List assets, optionally filter by calibration status or workspace     |
| `testmonitor_result_list` | List test results with rich filtering (status, program, serial, etc.) |
| `routine_list`            | List automation routines (v2 event/action or v1 notebook scheduling)  |

### Phase 2 — Get-by-ID and mutations

| Tool                      | Type  | Description                                          |
| ------------------------- | ----- | ---------------------------------------------------- |
| `tag_set_value`           | write | Write a value to a tag by path (type auto-detected)  |
| `system_get`              | read  | Full details of a single system by ID                |
| `asset_get`               | read  | Full details of a single asset by ID                 |
| `testmonitor_result_get`  | read  | Full test result object by ID                        |
| `routine_get`             | read  | Full details of a single routine by ID               |
| `routine_enable`          | write | Enable a routine by ID                               |
| `routine_disable`         | write | Disable a routine by ID                              |

### Phase 3 — Broader coverage

| Tool                          | Description                                                         |
| ----------------------------- | ------------------------------------------------------------------- |
| `user_list`                   | List users, optionally filtered by workspace or expression          |
| `testmonitor_step_list`       | List test steps for a given result ID                               |
| `file_list`                   | List uploaded files, optionally filtered by name or workspace       |
| `asset_calibration_summary`   | Fleet-wide calibration counts (total, approaching, past due, etc.)  |
| `testmonitor_result_summary`  | Pass/fail/error counts for test results (efficient, no data fetch)  |
| `notebook_list`               | List Jupyter notebooks (SLS and SLE compatible)                     |

### Phase 4 — Alarms, tag history, and workspace mutations

| Tool                | Type  | Description                                                   |
| ------------------- | ----- | ------------------------------------------------------------- |
| `alarm_list`        | read  | List active alarm instances, filter by severity or workspace  |
| `tag_history`       | read  | Historical values for a tag, most recent first                |
| `workspace_create`  | write | Create a new workspace by name                                |
| `workspace_disable` | write | Disable an existing workspace (requires id + current name)    |

All tools return JSON. Error responses are also JSON: `{"error": "<message>"}`.

### `workspace_list`

Returns id, name, enabled state, and default flag for each workspace.
Call this first to discover workspace IDs used by other tools.

```json
{ "take": 25 }
```

### `tag_list`

Returns tag metadata and current value for each tag matching the filter.

```json
{
  "path": "machine.line1.*",
  "workspace": "<workspace-id>",
  "take": 50
}
```

`path` accepts glob patterns (e.g. `sensor.*`, `*.temperature`).

### `tag_get`

```json
{ "path": "machine.line1.temperature" }
```

Returns the full tag object plus a `currentValue` field.

### `system_list`

```json
{
  "state": "CONNECTED",
  "take": 50
}
```

`state` accepts `CONNECTED` or `DISCONNECTED`.

### `asset_list`

```json
{
  "calibration_status": "PAST_RECOMMENDED_DUE_DATE",
  "workspace": "<workspace-id>",
  "take": 50
}
```

`calibration_status` accepts `OK`, `APPROACHING_RECOMMENDED_DUE_DATE`,
or `PAST_RECOMMENDED_DUE_DATE`.

### `testmonitor_result_list`

```json
{
  "status": "FAILED",
  "program_name": "Battery Test",
  "serial_number": "SN-001",
  "part_number": "PN-123",
  "operator": "jsmith",
  "workspace": "<workspace-id>",
  "filter": "StartedAt > \"2026-01-01T00:00:00Z\"",
  "take": 100
}
```

Status values: `PASSED`, `FAILED`, `RUNNING`, `ERRORED`, `TERMINATED`,
`TIMEDOUT`, `WAITING`, `SKIPPED`.

The `filter` field accepts a raw Dynamic LINQ expression for advanced queries.
Convenience filters (`status`, `program_name`, etc.) are ANDed together
and ANDed with `filter` if both are supplied.

### `routine_list`

```json
{
  "enabled": true,
  "api_version": "v2",
  "take": 25
}
```

`api_version` is `v2` (default, tag-event/alarm-action routines) or `v1`
(notebook scheduling routines).

### `tag_set_value`

```json
{
  "path": "machine.line1.setpoint",
  "value": "72.5",
  "data_type": "DOUBLE"
}
```

Write a value to a tag. If `data_type` is omitted the server fetches the
tag's registered type automatically.
Auto-detection order when the tag has no registered type:
`"true"/"false"` → `BOOLEAN`, integer string → `INT`,
decimal string → `DOUBLE`, everything else → `STRING`.

### `system_get`

```json
{ "system_id": "<system-id>" }
```

Returns the full system record for a single managed system.
Use `system_list` to discover IDs.

### `asset_get`

```json
{ "asset_id": "<asset-id>" }
```

Returns the full asset record including calibration status.
Use `asset_list` to discover IDs.

### `testmonitor_result_get`

```json
{ "result_id": "<result-id>" }
```

Returns the full test result object.
Use `testmonitor_result_list` to discover IDs.

### `routine_get`

```json
{
  "routine_id": "<routine-id>",
  "api_version": "v2"
}
```

Returns the full routine record. Use `routine_list` to discover IDs.

### `routine_enable` / `routine_disable`

```json
{
  "routine_id": "<routine-id>",
  "api_version": "v2"
}
```

Enables or disables a routine. Returns `{"id": "...", "enabled": true/false}`.### `user_list`

```json
{
  "take": 25,
  "include_disabled": false,
  "workspace": "<workspace-id>",
  "filter": "email.Contains(\"ni.com\")"
}
```

Returns user objects including id, firstName, lastName, email, and status.
Active users only by default; set `include_disabled=true` to include all.

### `testmonitor_step_list`

```json
{
  "result_id": "<result-id>",
  "take": 100
}
```

Returns all steps for a test result including name, status, measurements,
and timing. Use `testmonitor_result_list` to find result IDs.

### `file_list`

```json
{
  "take": 25,
  "workspace": "<workspace-id>",
  "name_filter": ".csv"
}
```

Returns file metadata (id, name, size, created date, workspace).
`name_filter` is a substring match across file name and extension.

### `asset_calibration_summary`

No parameters. Returns a single JSON object with fleet-wide counts:

```json
{
  "total": 250,
  "approachingRecommendedDueDate": 12,
  "pastRecommendedDueDate": 3,
  "outForCalibration": 1,
  "totalCalibrated": 200
}
```

### `testmonitor_result_summary`

```json
{
  "workspace": "<workspace-id>",
  "program_name": "Battery Test",
  "filter": "StartedAt > \"2026-01-01T00:00:00Z\""
}
```

Makes efficient count-only queries (no data transferred) and returns:

```json
{
  "total": 500,
  "byStatus": {
    "PASSED": 450,
    "FAILED": 40,
    "ERRORED": 5,
    "RUNNING": 3,
    "TERMINATED": 2,
    "TIMEDOUT": 0
  }
}
```

### `notebook_list`

```json
{
  "take": 25,
  "workspace": "<workspace-id>"
}
```

Works on both SystemLink Server (SLS, uses `/ninbexec/v2`) and
SystemLink Enterprise (SLE, uses `/ninotebook/v1`). The platform is
detected automatically from the active profile.

### `alarm_list`

```json
{
  "severity": "HIGH",
  "workspace": "<workspace-id>",
  "take": 25
}
```

Returns active (unresolved) alarm instances including instanceId, alarmId,
message, severity, and tagPath. `severity` accepts `CRITICAL`, `HIGH`,
`MEDIUM`, or `LOW`.

### `tag_history`

```json
{
  "path": "machine.line1.temperature",
  "take": 50
}
```

Returns a list of past tag values with timestamps, most recent first.
Use `tag_get` to inspect the current value or `tag_list` to discover paths.

### `workspace_create`

```json
{ "name": "Line 2 Testing" }
```

Creates a new workspace with the given name. The workspace is enabled by
default. Returns the created workspace object including the new id.

### `workspace_disable`

```json
{
  "workspace_id": "<workspace-id>",
  "workspace_name": "Line 2 Testing"
}
```

Disables the workspace. Both `workspace_id` and `workspace_name` are
required (the API PUT endpoint updates the full record). Use
`workspace_list` to look up the id and current name before calling this
tool. Returns `{"id": "...", "name": "...", "enabled": false}`.

## Readonly mode

If your active `slcli` profile has readonly mode enabled
(`slcli login --readonly`), all tool calls that attempt mutations will
return an error response rather than modifying data. The current tool set
is read-only by design; this note is relevant to future mutation tools.

## Selecting a profile

The MCP server inherits the active `slcli` profile, including any
`SLCLI_PROFILE` environment variable the client process has set.

To point the server at a specific environment, create a named profile and
set the env var in the client config. Example for VS Code:

```json
{
  "servers": {
    "slcli-prod": {
      "type": "stdio",
      "command": "slcli",
      "args": ["mcp", "serve"],
      "env": {
        "SLCLI_PROFILE": "prod"
      }
    }
  }
}
```

## Implementation notes

- All `mcp` package imports are **lazy** (inside function bodies). The module
  is safe to import even if `mcp` is not installed; only `slcli mcp serve`
  will fail.
- Tool handlers are **synchronous** and called from the async MCP dispatch
  loop. They use `make_api_request` from `slcli.utils`, which is the same
  HTTP helper used by all other slcli commands.
- The `slcli-mcp` entry point (`pyproject.toml`) is a direct alias for
  `slcli mcp serve`, provided for clients that prefer a single-word command.

## Roadmap

### Phase 1 — Read-only foundation ✅ (complete)

7 tools covering the five most common resources:
`workspace_list`, `tag_list`, `tag_get`, `system_list`, `asset_list`,
`testmonitor_result_list`, `routine_list`

### Phase 2 — Get-by-ID and first mutations ✅ (complete)

7 tools that complete the core read surface and add safe write operations:

| Tool | Type | Description |
| --- | --- | --- |
| `tag_set_value` | write | Write a value to a tag by path |
| `system_get` | read | Full details of one system |
| `asset_get` | read | Full details of one asset |
| `testmonitor_result_get` | read | Full result with step summary |
| `routine_get` | read | Full details of one routine |
| `routine_enable` | write | Enable a routine by ID |
| `routine_disable` | write | Disable a routine by ID |

### Phase 3 — Broader coverage ✅ (complete)

6 tools expanding coverage to users, files, notebooks, steps, and summary aggregations:

| Tool | Description |
| --- | --- |
| `user_list` | List users (niuser/v1/users) |
| `testmonitor_step_list` | List test steps for a result |
| `file_list` | List uploaded files (nifile-manager) |
| `asset_calibration_summary` | Aggregate counts by calibration status |
| `testmonitor_result_summary` | Pass/fail counts per program / workspace |
| `notebook_list` | List Jupyter notebooks |

### Phase 4 — Alarms, tag history, workspace mutations, Codex CLI ✅ (complete)

| Tool / Feature | Description |
| --- | --- |
| `alarm_list` | List active alarms (nialarm/v1), filter by severity |
| `tag_history` | Historical tag values |
| `workspace_create` | Create a workspace by name |
| `workspace_disable` | Disable a workspace by ID + name |
| `slcli mcp install --target codex` | OpenAI Codex CLI install target (.codex/mcp.json) |
