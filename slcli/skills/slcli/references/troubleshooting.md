# Troubleshooting & Tips

Common issues and workarounds when using `slcli` or scripting against SystemLink APIs.

## Update preflight

Before deeper troubleshooting, check the CLI and the active installed skill once per session:

```bash
slcli version check
slcli skill check --client <CLIENT> --scope <SCOPE>
```

Use `--directory <PATH>` instead of `--client` and `--scope` for a custom skill location. If
the CLI is outdated, recommend the manager-specific command printed by `version check`. If the
skill check reports `missing`, `unversioned`, or `outdated`, recommend updating the same target:

```bash
slcli skill install --client <CLIENT> --scope <SCOPE> --force
```

Obtain the user's approval before running an update. If either check fails because the command
is unavailable or the network cannot be reached, note that version status is unknown and
continue troubleshooting. Give version skew more weight when the failure involves unknown
commands, changed options, output shape, packaging, or skill instructions.

## Effective profile and workspace scope

Resolve the workspace and profile independently before querying resources. A
workspace name is not a profile name. Use `slcli config list --format json` to
find profiles mapped to the workspace, then pass the selected profile before
each command with `slcli --profile NAME ...`.

When `slcli info --format json` shows different values, use
`active_profile_name` for the effective profile and `api_url_source` for the
effective endpoint. `current_profile` is only the persisted config pointer and
may be stale relative to a CLI or environment override.

## Live-data snapshots

Queries are live and may change between commands. Record the query time and
avoid presenting counts from separate commands as one atomic snapshot. If
multiple aggregations must agree exactly, fetch one bounded JSON result set and
derive all aggregations locally.

## Workspace IDs vs names

Some API endpoints (notably **file upload**) require the workspace **UUID**, not
the human-readable name. When a command fails with a 400 error and you passed a
workspace name, retry with the workspace ID:

```bash
# Resolve workspace name → ID
slcli workspace list -f json | jq '.[] | select(.name=="MyWorkspace") | .id'

# Then use the ID
slcli file upload "file.pdf" -w "d503640b-db60-41c7-9b97-4ce2e53851f3"
```

As a general rule, **prefer workspace IDs over names** in scripted or automated
workflows to avoid ambiguity.

## Windows terminal encoding

On Windows, set `PYTHONUTF8=1` before running slcli to avoid `charmap` codec
errors when the output contains Unicode characters (✓, ✗, box-drawing):

```powershell
$env:PYTHONUTF8 = "1"
slcli spec list --product "My Product" --take 25
```

## PowerShell quoting

PowerShell mangles inline Python f-strings that contain dictionary key access
(e.g. `p["name"]`). When running Python one-liners from PowerShell:

- Write the script to a `.py` file and execute it, or
- Use `python -m <module>` to run a module, or
- Avoid f-strings with bracket notation in `-c` arguments.

## Large file uploads

File uploads to SystemLink can take 30+ seconds for multi-MB PDFs. If the
command appears to hang, give it time — the upload is still in progress.
Set a generous timeout (60–120 s) when automating uploads.

## Feature not available on this server

If a command exits with code 2 and a message like:

```
✗ Error: DataFrames is not available on SystemLink Server.
  This feature requires the DataFrame service.
```

The connected server does not have the required microservice deployed.
This is expected for features that only exist on SystemLink Enterprise (SLE).

**Diagnose:**

```bash
# Check which services are reachable
slcli info -f json | jq '.services'

# Force a fresh probe (bypasses 5-minute cache)
slcli info
```

**Gated command groups:** `dataframe`, `comment`, `template`,
`workitem template`, `workitem workflow`, `customfield`, `notebook`, `routine` (v2).

**Workaround:** If you believe the service should be available, verify the
server URL is correct (`slcli config view`) and that the service is installed
and running on the target server. Set `SLCLI_SERVICE_PROBE_CACHE_TTL_SECONDS=0`
to disable probe caching for debugging stale results.
