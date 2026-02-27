"""MCP (Model Context Protocol) server for slcli.

Exposes slcli commands as MCP tools for AI assistants (VS Code Copilot,
Claude Desktop, Cursor, etc.).

Run with:
    slcli mcp serve

Or directly:
    slcli-mcp

Test with the MCP Inspector (SSE transport, no AI client needed):
    slcli mcp serve --transport sse

Requires the ``mcp`` package:
    poetry install --with mcp
    # or: pip install "mcp>=1.0"
"""

import asyncio
import json
import sys
import urllib.parse
from typing import Any, Dict, List, Literal, Optional

from mcp.server.fastmcp import FastMCP  # type: ignore[import-untyped]

# Module-level FastMCP instance — also usable directly via `mcp dev slcli/mcp_server.py`
server = FastMCP("slcli")


# ---------------------------------------------------------------------------
# Capabilities resource — read this to answer "what can I do?" without
# expanding all 24 tool schemas.  URI: slcli://capabilities
# ---------------------------------------------------------------------------

_CAPABILITIES = """# slcli MCP capabilities

## Read tools
- workspace_list(take) — list workspaces; returns id/name/enabled
- tag_list(path, workspace, take) — list tags with current value; path supports globs
- tag_get(path) — single tag metadata + current value
- tag_history(path, take) — historical tag values, most recent first
- system_list(state, take) — list NI hardware systems; state=CONNECTED|DISCONNECTED
- system_get(system_id) — full system details
- asset_list(calibration_status, workspace, model, take) — list assets; model is a substring match
- asset_get(asset_id) — full asset details
- asset_calibration_summary() — fleet-wide calibration counts
- alarm_list(severity, workspace, take) — active alarms; severity=CRITICAL|HIGH|MEDIUM|LOW
- testmonitor_result_list(status, program_name, serial_number, part_number, operator,
    host_name, workspace, filter, skip, take)
    — status values: PASSED|FAILED|RUNNING|ERRORED|TERMINATED|TIMEDOUT|WAITING|SKIPPED
    — filter is a raw Dynamic LINQ expression, e.g. 'StartedAt > "2026-01-01T00:00:00Z"'
    — use skip+take to paginate: skip=0/100/200...
    — default take=100; max take=1000
- testmonitor_result_get(result_id) — full test result
- testmonitor_result_summary(workspace, program_name, serial_number, part_number, host_name, filter)
    — returns total + byStatus counts; uses take=0/returnCount=True so very efficient
    — use this for "how many" questions before fetching full results
- testmonitor_step_list(result_id, take) — steps for a result
- routine_list(enabled, api_version, take) — automation routines; v2=tag-event, v1=notebooks
- routine_get(routine_id, api_version) — full routine details
- user_list(take, include_disabled, workspace, filter) — users
- file_list(take, workspace, name_filter) — uploaded files
- notebook_list(take, workspace) — Jupyter notebooks (SLS + SLE)

## Write tools
- tag_set_value(path, value, data_type) — write a tag value
- routine_enable(routine_id, api_version) — enable a routine
- routine_disable(routine_id, api_version) — disable a routine
- workspace_create(name) — create a workspace
- workspace_disable(workspace_id, workspace_name) — disable a workspace

## Usage tips
- Start with workspace_list to get workspace IDs used by other tools.
- For "how many" questions use testmonitor_result_summary (no data fetch, just counts).
- For large datasets: testmonitor_result_list returns up to 100 results by default.
  Paginate with skip=100, skip=200, etc.
- For station/host queries use host_name filter (substring match against HostName field).
- Group-by aggregation (by operator, program family, etc.) is not natively supported;
  the model must paginate and aggregate client-side, or use multiple summary calls.
"""


@server.resource("slcli://capabilities")
def capabilities() -> str:
    """Compact overview of all slcli MCP tools. Read this before asking what the server can do."""
    return _CAPABILITIES


def _esc(v: str) -> str:
    """Escape double-quotes in a filter string value so the LINQ expression stays valid."""
    return v.replace('"', '\\"')


# ---------------------------------------------------------------------------
# Tools — function signatures drive the JSON schema automatically.
# Raise an exception to signal an error; FastMCP converts it to an error response.
# ---------------------------------------------------------------------------


@server.tool()
def workspace_list(take: int = 25) -> str:
    """List workspaces (id, name, enabled, default). Call first to get workspace IDs."""
    from .utils import get_base_url, make_api_request

    url = f"{get_base_url()}/niuser/v1/workspaces?take={take}"
    resp = make_api_request("GET", url)
    return json.dumps(resp.json().get("workspaces", []), default=str)


@server.tool()
def tag_list(path: str = "", workspace: str = "", take: int = 25) -> str:
    """List tags with current value. Filter by path glob (e.g. 'sensor.*') or workspace ID."""
    from .utils import get_base_url, make_api_request

    filter_parts: List[str] = []
    if path:
        filter_parts.append(f'path = "{_esc(path)}"')
    if workspace:
        filter_parts.append(f'workspace = "{_esc(workspace)}"')

    payload: Dict[str, Any] = {
        "filter": " && ".join(filter_parts),
        "take": take,
        "orderBy": "TIMESTAMP",
        "descending": True,
    }
    url = f"{get_base_url()}/nitag/v2/query-tags-with-values"
    resp = make_api_request("POST", url, payload=payload)
    return json.dumps(resp.json().get("tagsWithValues", []), default=str)


@server.tool()
def tag_get(path: str) -> str:
    """Get a single tag's metadata and current value. Use tag_list to discover paths."""
    from .utils import get_base_url, make_api_request

    if not path:
        raise ValueError("'path' is required")

    encoded_path = urllib.parse.quote(path, safe="")
    tag_url = f"{get_base_url()}/nitag/v2/tags/{encoded_path}"
    tag_resp = make_api_request("GET", tag_url)
    tag_data: Dict[str, Any] = tag_resp.json()

    # Augment with the current value (best-effort; may 404 if tag has no value yet)
    try:
        val_url = f"{get_base_url()}/nitag/v2/tags/{encoded_path}/values/current"
        val_resp = make_api_request("GET", val_url)
        tag_data["currentValue"] = val_resp.json()
    except Exception:  # noqa: BLE001
        tag_data["currentValue"] = None

    return json.dumps(tag_data, default=str)


@server.tool()
def system_list(
    state: Optional[Literal["CONNECTED", "DISCONNECTED"]] = None,
    take: int = 25,
) -> str:
    """List NI hardware systems (id, alias, host, state, OS). Filter by connection state."""
    from .utils import get_base_url, make_api_request

    payload: Dict[str, Any] = {"take": take}
    if state:
        payload["filter"] = f'connected.data.state = "{state.upper()}"'

    url = f"{get_base_url()}/nisysmgmt/v1/query-systems"
    resp = make_api_request("POST", url, payload=payload)
    data = resp.json()

    # The systems API can return either a list (one entry per system) or a
    # dict with a "data" key — normalise to a flat list.
    if isinstance(data, list):
        systems = [item.get("data", item) for item in data if isinstance(item, dict)]
    else:
        systems = data.get("data", data.get("systems", []))
    return json.dumps(systems, default=str)


@server.tool()
def asset_list(
    calibration_status: Optional[
        Literal["OK", "APPROACHING_RECOMMENDED_DUE_DATE", "PAST_RECOMMENDED_DUE_DATE"]
    ] = None,
    workspace: Optional[str] = None,
    model: Optional[str] = None,
    take: int = 25,
) -> str:
    """List assets (id, name, model, serial). Filter by calibration_status, workspace, model."""
    from .utils import get_base_url, make_api_request

    filter_parts: List[str] = []
    if calibration_status:
        filter_parts.append(f'CalibrationStatus = "{calibration_status}"')
    if workspace:
        filter_parts.append(f'Workspace = "{_esc(workspace)}"')
    if model:
        filter_parts.append(f'ModelName.Contains("{_esc(model)}")')

    payload: Dict[str, Any] = {
        "skip": 0,
        "take": take,
        "descending": False,
        "returnCount": True,
    }
    if filter_parts:
        payload["filter"] = " and ".join(filter_parts)

    url = f"{get_base_url()}/niapm/v1/query-assets"
    resp = make_api_request("POST", url, payload=payload)
    return json.dumps(resp.json().get("assets", []), default=str)


@server.tool()
def testmonitor_result_list(
    status: Optional[
        Literal[
            "PASSED",
            "FAILED",
            "RUNNING",
            "ERRORED",
            "TERMINATED",
            "TIMEDOUT",
            "WAITING",
            "SKIPPED",
        ]
    ] = None,
    program_name: Optional[str] = None,
    serial_number: Optional[str] = None,
    part_number: Optional[str] = None,
    operator: Optional[str] = None,
    host_name: Optional[str] = None,
    workspace: Optional[str] = None,
    filter: Optional[str] = None,  # noqa: A002
    skip: int = 0,
    take: int = 100,
) -> str:
    """List test results. Filter by status, program_name, serial_number, host_name, etc."""
    from .utils import get_base_url, make_api_request

    filter_parts: List[str] = []
    if status:
        filter_parts.append(f'Status = "{status.upper()}"')
    if program_name:
        filter_parts.append(f'ProgramName.Contains("{_esc(program_name)}")')
    if serial_number:
        filter_parts.append(f'SerialNumber.Contains("{_esc(serial_number)}")')
    if part_number:
        filter_parts.append(f'PartNumber.Contains("{_esc(part_number)}")')
    if operator:
        filter_parts.append(f'Operator.Contains("{_esc(operator)}")')
    if host_name:
        filter_parts.append(f'HostName.Contains("{_esc(host_name)}")')
    if workspace:
        filter_parts.append(f'Workspace = "{_esc(workspace)}"')
    if filter:
        filter_parts.append(filter)

    payload: Dict[str, Any] = {"skip": skip, "take": take, "descending": True}
    if filter_parts:
        payload["filter"] = " && ".join(filter_parts)

    url = f"{get_base_url()}/nitestmonitor/v2/query-results"
    resp = make_api_request("POST", url, payload=payload)
    return json.dumps(resp.json().get("results", []), default=str)


@server.tool()
def routine_list(
    enabled: Optional[bool] = None,
    api_version: Literal["v1", "v2"] = "v2",
    take: int = 25,
) -> str:
    """List automation routines. v2=tag-event/alarm (default), v1=notebook. Filter by enabled."""
    from .utils import get_base_url, make_api_request

    params: List[str] = [f"take={take}"]
    if enabled is True:
        params.append("Enabled=true")
    elif enabled is False:
        params.append("Enabled=false")

    url = f"{get_base_url()}/niroutine/{api_version}/routines?{'&'.join(params)}"
    resp = make_api_request("GET", url)
    return json.dumps(resp.json().get("routines", []), default=str)


# ---------------------------------------------------------------------------
# Phase 2 tools — get-by-ID and first mutation operations
# ---------------------------------------------------------------------------


def _detect_tag_type(value_str: str) -> str:
    """Infer a SystemLink tag type from the string representation of a value.

    Returns one of: BOOLEAN, INT, DOUBLE, STRING.
    """
    if value_str.lower() in ("true", "false"):
        return "BOOLEAN"
    if "." not in value_str and "e" not in value_str.lower():
        try:
            int(value_str)
            return "INT"
        except ValueError:
            pass
    try:
        float(value_str)
        return "DOUBLE"
    except ValueError:
        pass
    return "STRING"


@server.tool()
def tag_set_value(
    path: str,
    value: str,
    data_type: Optional[
        Literal["DOUBLE", "INT", "STRING", "BOOLEAN", "U_INT64", "DATE_TIME"]
    ] = None,
) -> str:
    """Write a value to a tag by exact path. Auto-detects type if data_type is omitted."""
    from .utils import get_base_url, make_api_request

    if not path:
        raise ValueError("'path' is required")
    if value is None:
        raise ValueError("'value' is required")

    encoded_path = urllib.parse.quote(path, safe="")

    # Resolve the type to use
    if data_type:
        tag_type: str = data_type
    else:
        # Fetch tag metadata to use the registered type
        try:
            meta_resp = make_api_request("GET", f"{get_base_url()}/nitag/v2/tags/{encoded_path}")
            tag_type = meta_resp.json().get("type") or _detect_tag_type(value)
        except Exception:  # noqa: BLE001
            tag_type = _detect_tag_type(value)

    # Normalise the value string for the API
    api_value: str = value
    if tag_type == "BOOLEAN":
        api_value = "true" if value.lower() == "true" else "false"
    # U_INT64 and DATE_TIME: pass value through as-is

    payload: Dict[str, Any] = {"value": {"value": api_value, "type": tag_type}}
    url = f"{get_base_url()}/nitag/v2/tags/{encoded_path}/values/current"
    make_api_request("PUT", url, payload=payload)

    return json.dumps({"path": path, "value": api_value, "type": tag_type})


@server.tool()
def system_get(system_id: str) -> str:
    """Get full details of a single system by ID. Use system_list to discover IDs."""
    from .utils import get_base_url, make_api_request

    if not system_id:
        raise ValueError("'system_id' is required")

    url = f"{get_base_url()}/nisysmgmt/v1/systems?id={urllib.parse.quote(system_id, safe='')}"
    resp = make_api_request("GET", url)
    data = resp.json()

    # Response is a list of wrapped entries — take the first match
    items: List[Any] = data if isinstance(data, list) else data.get("data", [])
    if not items:
        raise ValueError(f"System '{system_id}' not found")

    first = items[0]
    system_data: Any = first.get("data", first) if isinstance(first, dict) else first
    return json.dumps(system_data, default=str)


@server.tool()
def asset_get(asset_id: str) -> str:
    """Get full asset details including calibration history. Use asset_list to find IDs."""
    from .utils import get_base_url, make_api_request

    if not asset_id:
        raise ValueError("'asset_id' is required")

    url = f"{get_base_url()}/niapm/v1/assets/{urllib.parse.quote(asset_id, safe='')}"
    resp = make_api_request("GET", url)
    return json.dumps(resp.json(), default=str)


@server.tool()
def testmonitor_result_get(result_id: str) -> str:
    """Get full test result details. Use testmonitor_result_list to find IDs."""
    from .utils import get_base_url, make_api_request

    if not result_id:
        raise ValueError("'result_id' is required")

    url = f"{get_base_url()}/nitestmonitor/v2/results/{urllib.parse.quote(result_id, safe='')}"
    resp = make_api_request("GET", url)
    return json.dumps(resp.json(), default=str)


@server.tool()
def routine_get(routine_id: str, api_version: Literal["v1", "v2"] = "v2") -> str:
    """Get full details of a single routine by ID. Use routine_list to discover IDs."""
    from .utils import get_base_url, make_api_request

    if not routine_id:
        raise ValueError("'routine_id' is required")

    url = f"{get_base_url()}/niroutine/{api_version}/routines/{urllib.parse.quote(routine_id, safe='')}"
    resp = make_api_request("GET", url)
    return json.dumps(resp.json(), default=str)


@server.tool()
def routine_enable(routine_id: str, api_version: Literal["v1", "v2"] = "v2") -> str:
    """Enable an automation routine by ID."""
    from .utils import get_base_url, make_api_request

    if not routine_id:
        raise ValueError("'routine_id' is required")

    url = f"{get_base_url()}/niroutine/{api_version}/routines/{urllib.parse.quote(routine_id, safe='')}"
    make_api_request("PATCH", url, payload={"enabled": True})
    return json.dumps({"id": routine_id, "enabled": True})


@server.tool()
def routine_disable(routine_id: str, api_version: Literal["v1", "v2"] = "v2") -> str:
    """Disable an automation routine by ID."""
    from .utils import get_base_url, make_api_request

    if not routine_id:
        raise ValueError("'routine_id' is required")

    url = f"{get_base_url()}/niroutine/{api_version}/routines/{urllib.parse.quote(routine_id, safe='')}"
    make_api_request("PATCH", url, payload={"enabled": False})
    return json.dumps({"id": routine_id, "enabled": False})


# ---------------------------------------------------------------------------
# Phase 3 tools — broader coverage
# ---------------------------------------------------------------------------


@server.tool()
def user_list(
    take: int = 25,
    include_disabled: bool = False,
    workspace: Optional[str] = None,
    filter: Optional[str] = None,  # noqa: A002
) -> str:
    """List users (id, firstName, lastName, email, status). Set include_disabled=True for all."""
    from .utils import get_base_url, make_api_request

    filter_parts: List[str] = []
    if not include_disabled:
        filter_parts.append('status = "active"')
    if workspace:
        filter_parts.append(f'workspace = "{workspace}"')
    if filter:
        filter_parts.append(filter)

    payload: Dict[str, Any] = {
        "take": take,
        "sortby": "firstName",
        "order": "ascending",
    }
    if filter_parts:
        payload["filter"] = " and ".join(filter_parts)

    url = f"{get_base_url()}/niuser/v1/users/query"
    resp = make_api_request("POST", url, payload=payload)
    return json.dumps(resp.json().get("users", []), default=str)


@server.tool()
def testmonitor_step_list(
    result_id: str,
    take: int = 100,
) -> str:
    """List steps for a result ID. Use testmonitor_result_list to find result IDs."""
    from .utils import get_base_url, make_api_request

    if not result_id:
        raise ValueError("'result_id' is required")

    payload: Dict[str, Any] = {
        "filter": "resultId == @0",
        "substitutions": [result_id],
        "take": take,
    }
    url = f"{get_base_url()}/nitestmonitor/v2/query-steps"
    resp = make_api_request("POST", url, payload=payload)
    return json.dumps(resp.json().get("steps", []), default=str)


@server.tool()
def file_list(
    take: int = 25,
    workspace: Optional[str] = None,
    name_filter: Optional[str] = None,
) -> str:
    """List files (id, name, size, created). Filter by workspace or name_filter."""
    from .utils import get_base_url, make_api_request

    filter_parts: List[str] = []
    if workspace:
        filter_parts.append(f'workspaceId:("{workspace}")')
    if name_filter:
        filter_parts.append(f'(name:("*{name_filter}*") OR extension:("*{name_filter}*"))')

    payload: Dict[str, Any] = {
        "take": take,
        "orderBy": "updated",
        "orderByDescending": True,
    }
    if filter_parts:
        payload["filter"] = " AND ".join(filter_parts)

    url = f"{get_base_url()}/nifile/v1/service-groups/Default/search-files"
    resp = make_api_request("POST", url, payload=payload)
    data = resp.json()
    # API returns either a list directly or a dict with a "files" key
    files: Any = data if isinstance(data, list) else data.get("files", data.get("data", []))
    return json.dumps(files, default=str)


@server.tool()
def asset_calibration_summary() -> str:
    """Fleet-wide calibration counts: total, approaching due, past due, out for calibration."""
    from .utils import get_base_url, make_api_request

    url = f"{get_base_url()}/niapm/v1/asset-summary"
    resp = make_api_request("GET", url)
    return json.dumps(resp.json(), default=str)


@server.tool()
def testmonitor_result_summary(
    workspace: Optional[str] = None,
    program_name: Optional[str] = None,
    serial_number: Optional[str] = None,
    part_number: Optional[str] = None,
    host_name: Optional[str] = None,
    filter: Optional[str] = None,  # noqa: A002
) -> str:
    """Count test results by status, no data fetch. Filter by program, serial, part, host."""
    from .utils import get_base_url, make_api_request

    # Build base filter parts (applied to every per-status query)
    base_filter_parts: List[str] = []
    base_subs: List[Any] = []
    if workspace:
        idx = len(base_subs)
        base_filter_parts.append(f"Workspace == @{idx}")
        base_subs.append(workspace)
    if program_name:
        idx = len(base_subs)
        base_filter_parts.append(f"ProgramName.Contains(@{idx})")
        base_subs.append(program_name)
    if serial_number:
        idx = len(base_subs)
        base_filter_parts.append(f"SerialNumber.Contains(@{idx})")
        base_subs.append(serial_number)
    if part_number:
        idx = len(base_subs)
        base_filter_parts.append(f"PartNumber.Contains(@{idx})")
        base_subs.append(part_number)
    if host_name:
        idx = len(base_subs)
        base_filter_parts.append(f"HostName.Contains(@{idx})")
        base_subs.append(host_name)
    if filter:
        base_filter_parts.append(filter)

    url = f"{get_base_url()}/nitestmonitor/v2/query-results"

    def _count(extra_filter: Optional[str], extra_subs: List[Any]) -> int:
        """Return totalCount for a filtered query (take=0, returnCount=True)."""
        parts = list(base_filter_parts)
        subs = list(base_subs)
        if extra_filter:
            parts.append(extra_filter)
            subs.extend(extra_subs)
        payload: Dict[str, Any] = {"take": 0, "returnCount": True}
        if parts:
            payload["filter"] = " && ".join(parts)
        if subs:
            payload["substitutions"] = subs
        try:
            r = make_api_request("POST", url, payload=payload)
            return int(r.json().get("totalCount", 0))
        except Exception:  # noqa: BLE001
            return -1

    total = _count(None, [])

    status_types = ["PASSED", "FAILED", "RUNNING", "ERRORED", "TERMINATED", "TIMEDOUT"]
    counts: Dict[str, int] = {}
    for status in status_types:
        idx = len(base_subs)
        counts[status] = _count(f"status.statusType == @{idx}", [status])

    return json.dumps({"total": total, "byStatus": counts})


@server.tool()
def notebook_list(
    take: int = 25,
    workspace: Optional[str] = None,
) -> str:
    """List Jupyter notebooks (id, name, description). Works on both SLS and SLE platforms."""
    from .platform import PLATFORM_SLS, get_platform
    from .utils import get_base_url, make_api_request

    is_sls = get_platform() == PLATFORM_SLS
    if is_sls:
        base = f"{get_base_url()}/ninbexec/v2"
        query_url = f"{base}/query-notebooks"
    else:
        base = f"{get_base_url()}/ninotebook/v1"
        query_url = f"{base}/notebook/query"

    payload: Dict[str, Any] = {"take": take}
    if workspace:
        payload["filter"] = f'workspace = "{workspace}"'

    resp = make_api_request("POST", query_url, payload=payload)
    return json.dumps(resp.json().get("notebooks", []), default=str)


# ---------------------------------------------------------------------------
# Phase 4 tools — alarms, tag history, workspace mutations
# ---------------------------------------------------------------------------


@server.tool()
def alarm_list(
    severity: Optional[Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]] = None,
    workspace: Optional[str] = None,
    take: int = 25,
) -> str:
    """List active alarm instances. Filter by severity (CRITICAL/HIGH/MEDIUM/LOW) or workspace."""
    from .utils import get_base_url, make_api_request

    params: List[str] = [f"take={take}"]
    if severity:
        params.append(f"severity={severity}")
    if workspace:
        params.append(f"workspace={urllib.parse.quote(workspace, safe='')}")

    url = f"{get_base_url()}/nialarm/v1/active-instances?{'&'.join(params)}"
    resp = make_api_request("GET", url)
    data = resp.json()
    # API may return either a list or a dict with an "alarmInstances" / "instances" key
    if isinstance(data, list):
        return json.dumps(data, default=str)
    return json.dumps(
        data.get("alarmInstances", data.get("instances", data.get("items", []))),
        default=str,
    )


@server.tool()
def tag_history(path: str, take: int = 25) -> str:
    """Get historical tag values by exact path, most recent first. Use tag_get for current value."""
    from .utils import get_base_url, make_api_request

    if not path:
        raise ValueError("'path' is required")

    encoded_path = urllib.parse.quote(path, safe="")
    url = f"{get_base_url()}/nitag/v2/tags/{encoded_path}/values/history?take={take}"
    resp = make_api_request("GET", url)
    data = resp.json()
    # API returns {"tagsWithAggregates": [...]} or a list or a "values" key
    if isinstance(data, list):
        return json.dumps(data, default=str)
    return json.dumps(
        data.get("values", data.get("tagsWithAggregates", [])),
        default=str,
    )


@server.tool()
def workspace_create(name: str) -> str:
    """Create a new workspace by name (enabled by default). Returns the object with generated ID."""
    from .utils import get_base_url, make_api_request

    if not name:
        raise ValueError("'name' is required")

    url = f"{get_base_url()}/niuser/v1/workspaces"
    payload: Dict[str, Any] = {"name": name, "enabled": True}
    resp = make_api_request("POST", url, payload=payload)
    return json.dumps(resp.json(), default=str)


@server.tool()
def workspace_disable(workspace_id: str, workspace_name: str) -> str:
    """Disable a workspace (data preserved). Both id and name required; use workspace_list first."""
    from .utils import get_base_url, make_api_request

    if not workspace_id:
        raise ValueError("'workspace_id' is required")
    if not workspace_name:
        raise ValueError("'workspace_name' is required")

    url = f"{get_base_url()}/niuser/v1/workspaces/{urllib.parse.quote(workspace_id, safe='')}"
    payload: Dict[str, Any] = {"name": workspace_name, "enabled": False}
    make_api_request("PUT", url, payload=payload)
    return json.dumps({"id": workspace_id, "name": workspace_name, "enabled": False})


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def _run() -> None:
    """Run the MCP server connected to stdio."""
    print("slcli MCP server ready — waiting for client", file=sys.stderr, flush=True)
    await server.run_stdio_async()


def main() -> None:
    """Entry point for the ``slcli-mcp`` executable.

    Starts the stdio MCP server. Clients (VS Code Copilot, Claude Desktop,
    Cursor) should configure this as:
        command: slcli
        args: [mcp, serve]
    """
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        print("slcli MCP server stopped", file=sys.stderr, flush=True)
        sys.exit(0)


if __name__ == "__main__":
    main()
