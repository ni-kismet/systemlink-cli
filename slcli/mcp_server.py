"""MCP (Model Context Protocol) server for slcli.

Exposes slcli commands as MCP tools for AI assistants (VS Code Copilot,
Claude Desktop, Cursor, etc.).

Run with:
    slcli mcp serve

Or directly:
    slcli-mcp

Requires the ``mcp`` package:
    poetry install --with mcp
    # or: pip install "mcp>=1.0"
"""

import asyncio
import json
import urllib.parse
from typing import Any, Dict, List, Optional


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _tool_error(message: str) -> List[Any]:
    """Return a TextContent block carrying an error payload."""
    from mcp.types import TextContent  # type: ignore[import-untyped]

    return [TextContent(type="text", text=json.dumps({"error": message}))]


def _tool_ok(data: Any) -> List[Any]:
    """Return a TextContent block carrying a JSON-serialised success payload."""
    from mcp.types import TextContent  # type: ignore[import-untyped]

    return [TextContent(type="text", text=json.dumps(data, indent=2, default=str))]


# ---------------------------------------------------------------------------
# Tool handlers — all synchronous; called from the async dispatch layer.
# ---------------------------------------------------------------------------


def _handle_workspace_list(arguments: Dict[str, Any]) -> List[Any]:
    """Return a list of workspaces from the SystemLink server."""
    try:
        from .utils import get_base_url, make_api_request

        take = int(arguments.get("take", 25))
        url = f"{get_base_url()}/niuser/v1/workspaces?take={take}"
        resp = make_api_request("GET", url)
        data = resp.json()
        return _tool_ok(data.get("workspaces", []))
    except Exception as exc:  # noqa: BLE001
        return _tool_error(str(exc))


def _handle_tag_list(arguments: Dict[str, Any]) -> List[Any]:
    """Return tags with optional path glob and workspace filter."""
    try:
        from .utils import get_base_url, make_api_request

        take = int(arguments.get("take", 25))
        path_pattern: str = arguments.get("path", "")
        workspace: str = arguments.get("workspace", "")

        filter_parts: List[str] = []
        if path_pattern:
            filter_parts.append(f'path = "{path_pattern}"')
        if workspace:
            filter_parts.append(f'workspace = "{workspace}"')

        payload: Dict[str, Any] = {
            "filter": " && ".join(filter_parts),
            "take": take,
            "orderBy": "TIMESTAMP",
            "descending": True,
        }
        url = f"{get_base_url()}/nitag/v2/query-tags-with-values"
        resp = make_api_request("POST", url, payload=payload)
        data = resp.json()
        return _tool_ok(data.get("tagsWithValues", []))
    except Exception as exc:  # noqa: BLE001
        return _tool_error(str(exc))


def _handle_tag_get(arguments: Dict[str, Any]) -> List[Any]:
    """Return a single tag (metadata + current value) by path."""
    try:
        from .utils import get_base_url, make_api_request

        path: str = arguments.get("path", "")
        if not path:
            return _tool_error("'path' is required")

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

        return _tool_ok(tag_data)
    except Exception as exc:  # noqa: BLE001
        return _tool_error(str(exc))


def _handle_system_list(arguments: Dict[str, Any]) -> List[Any]:
    """Return a list of managed systems."""
    try:
        from .utils import get_base_url, make_api_request

        take = int(arguments.get("take", 25))
        state: Optional[str] = arguments.get("state")

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
        return _tool_ok(systems)
    except Exception as exc:  # noqa: BLE001
        return _tool_error(str(exc))


def _handle_asset_list(arguments: Dict[str, Any]) -> List[Any]:
    """Return a list of assets."""
    try:
        from .utils import get_base_url, make_api_request

        take = int(arguments.get("take", 25))
        calibration_status: Optional[str] = arguments.get("calibration_status")
        workspace: Optional[str] = arguments.get("workspace")

        filter_parts: List[str] = []
        if calibration_status:
            filter_parts.append(f'CalibrationStatus = "{calibration_status}"')
        if workspace:
            filter_parts.append(f'Workspace = "{workspace}"')

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
        data = resp.json()
        return _tool_ok(data.get("assets", []))
    except Exception as exc:  # noqa: BLE001
        return _tool_error(str(exc))


def _handle_testmonitor_result_list(arguments: Dict[str, Any]) -> List[Any]:
    """Return a list of test results."""
    try:
        from .utils import get_base_url, make_api_request

        take = int(arguments.get("take", 25))

        filter_parts: List[str] = []
        if arguments.get("status"):
            filter_parts.append(f'Status = "{str(arguments["status"]).upper()}"')
        if arguments.get("program_name"):
            filter_parts.append(f'ProgramName.Contains("{arguments["program_name"]}")')
        if arguments.get("serial_number"):
            filter_parts.append(f'SerialNumber.Contains("{arguments["serial_number"]}")')
        if arguments.get("part_number"):
            filter_parts.append(f'PartNumber.Contains("{arguments["part_number"]}")')
        if arguments.get("operator"):
            filter_parts.append(f'Operator.Contains("{arguments["operator"]}")')
        if arguments.get("workspace"):
            filter_parts.append(f'Workspace = "{arguments["workspace"]}"')
        if arguments.get("filter"):
            filter_parts.append(str(arguments["filter"]))

        payload: Dict[str, Any] = {"take": take, "descending": True}
        if filter_parts:
            payload["filter"] = " && ".join(filter_parts)

        url = f"{get_base_url()}/nitestmonitor/v2/query-results"
        resp = make_api_request("POST", url, payload=payload)
        data = resp.json()
        return _tool_ok(data.get("results", []))
    except Exception as exc:  # noqa: BLE001
        return _tool_error(str(exc))


def _handle_routine_list(arguments: Dict[str, Any]) -> List[Any]:
    """Return a list of routines."""
    try:
        from .utils import get_base_url, make_api_request

        take = int(arguments.get("take", 25))
        api_version = str(arguments.get("api_version", "v2"))
        enabled: Optional[bool] = arguments.get("enabled")

        params: List[str] = [f"take={take}"]
        if enabled is True:
            params.append("Enabled=true")
        elif enabled is False:
            params.append("Enabled=false")

        url = f"{get_base_url()}/niroutine/{api_version}/routines?{'&'.join(params)}"
        resp = make_api_request("GET", url)
        data = resp.json()
        return _tool_ok(data.get("routines", []))
    except Exception as exc:  # noqa: BLE001
        return _tool_error(str(exc))


# ---------------------------------------------------------------------------
# Dispatch table
# ---------------------------------------------------------------------------

_HANDLERS: Dict[str, Any] = {
    "workspace_list": _handle_workspace_list,
    "tag_list": _handle_tag_list,
    "tag_get": _handle_tag_get,
    "system_list": _handle_system_list,
    "asset_list": _handle_asset_list,
    "testmonitor_result_list": _handle_testmonitor_result_list,
    "routine_list": _handle_routine_list,
}


# ---------------------------------------------------------------------------
# Tool definitions
# ---------------------------------------------------------------------------


def _get_tool_definitions() -> Any:
    """Return the list of MCP Tool definitions registered by this server."""
    from mcp import types  # type: ignore[import-untyped]

    return [
        types.Tool(
            name="workspace_list",
            description=(
                "List workspaces available on the SystemLink server. "
                "Returns id, name, enabled, and default status for each workspace. "
                "Use this first to discover workspace IDs needed by other tools."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "take": {
                        "type": "integer",
                        "description": "Maximum number of workspaces to return (default 25)",
                        "default": 25,
                    },
                },
            },
        ),
        types.Tool(
            name="tag_list",
            description=(
                "List SystemLink tags, optionally filtered by path glob or workspace. "
                "Returns tag metadata (path, type, keywords) and current value. "
                "Use path patterns like 'sensor.*' or 'machine.line1.*' to filter by prefix."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": (
                            "Glob path filter, e.g. 'sensor.*' " "or 'machine.*.temperature'"
                        ),
                    },
                    "workspace": {
                        "type": "string",
                        "description": "Filter by workspace ID or name",
                    },
                    "take": {
                        "type": "integer",
                        "description": "Maximum results to return (default 25)",
                        "default": 25,
                    },
                },
            },
        ),
        types.Tool(
            name="tag_get",
            description=(
                "Get a single SystemLink tag by its exact path. "
                "Returns tag metadata and current value. "
                "Use tag_list with a path filter first to discover tag paths."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {
                        "type": "string",
                        "description": ("Exact tag path, e.g. 'machine.line1.temperature'"),
                    },
                },
                "required": ["path"],
            },
        ),
        types.Tool(
            name="system_list",
            description=(
                "List managed systems (NI hardware targets) on the SystemLink server. "
                "Returns id, alias, host, connection state, OS, and workspace for each system. "
                "Useful for fleet health checks or finding system IDs for test result queries."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "state": {
                        "type": "string",
                        "description": "Filter by connection state",
                        "enum": ["CONNECTED", "DISCONNECTED"],
                    },
                    "take": {
                        "type": "integer",
                        "description": "Maximum results to return (default 25)",
                        "default": 25,
                    },
                },
            },
        ),
        types.Tool(
            name="asset_list",
            description=(
                "List assets tracked by the SystemLink Asset Management service. "
                "Returns id, name, model, serial number, calibration status, and workspace. "
                "Use calibration_status='PAST_RECOMMENDED_DUE_DATE' to find overdue instruments."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "calibration_status": {
                        "type": "string",
                        "description": "Filter by calibration status",
                        "enum": [
                            "OK",
                            "APPROACHING_RECOMMENDED_DUE_DATE",
                            "PAST_RECOMMENDED_DUE_DATE",
                        ],
                    },
                    "workspace": {
                        "type": "string",
                        "description": "Filter by workspace ID",
                    },
                    "take": {
                        "type": "integer",
                        "description": "Maximum results to return (default 25)",
                        "default": 25,
                    },
                },
            },
        ),
        types.Tool(
            name="testmonitor_result_list",
            description=(
                "List test results from SystemLink Test Monitor. "
                "Returns id, status, programName, serialNumber, partNumber, operator, "
                "startedAt, totalTimeInSeconds, and workspace for each result. "
                "Status values: PASSED, FAILED, RUNNING, ERRORED, TERMINATED, TIMEDOUT, "
                "WAITING, SKIPPED. "
                "Supports filtering by status, program name, serial number, part number, "
                "operator, workspace, and raw Dynamic LINQ filter expressions."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "description": "Filter by test result status",
                        "enum": [
                            "PASSED",
                            "FAILED",
                            "RUNNING",
                            "ERRORED",
                            "TERMINATED",
                            "TIMEDOUT",
                            "WAITING",
                            "SKIPPED",
                        ],
                    },
                    "program_name": {
                        "type": "string",
                        "description": "Filter by test program name (substring match)",
                    },
                    "serial_number": {
                        "type": "string",
                        "description": "Filter by DUT serial number (substring match)",
                    },
                    "part_number": {
                        "type": "string",
                        "description": "Filter by part number (substring match)",
                    },
                    "operator": {
                        "type": "string",
                        "description": "Filter by operator name (substring match)",
                    },
                    "workspace": {
                        "type": "string",
                        "description": "Filter by workspace ID or name",
                    },
                    "filter": {
                        "type": "string",
                        "description": (
                            "Raw Dynamic LINQ filter expression for advanced queries, "
                            "e.g. 'StartedAt > \"2025-01-01T00:00:00Z\"'"
                        ),
                    },
                    "take": {
                        "type": "integer",
                        "description": "Maximum results to return (default 25, max 1000)",
                        "default": 25,
                    },
                },
            },
        ),
        types.Tool(
            name="routine_list",
            description=(
                "List automation routines on the SystemLink server. "
                "v2 routines use tag-event triggers and alarm actions. "
                "v1 routines are scheduled/triggered notebook executions. "
                "Returns id, name, description, enabled, event type, and workspace."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "enabled": {
                        "type": "boolean",
                        "description": "Filter by enabled state (omit to return all)",
                    },
                    "api_version": {
                        "type": "string",
                        "description": (
                            "API version: 'v2' (tag-event / alarm-actions, default) "
                            "or 'v1' (notebook scheduling)"
                        ),
                        "enum": ["v1", "v2"],
                        "default": "v2",
                    },
                    "take": {
                        "type": "integer",
                        "description": "Maximum results to return (default 25)",
                        "default": 25,
                    },
                },
            },
        ),
    ]


# ---------------------------------------------------------------------------
# Server construction
# ---------------------------------------------------------------------------


def build_server() -> Any:
    """Build and return the MCP Server with all tools registered.

    Returns:
        Configured mcp.server.Server instance.
    """
    from mcp.server import Server  # type: ignore[import-untyped]

    server: Any = Server("slcli")

    @server.list_tools()  # type: ignore[misc]
    async def handle_list_tools() -> List[Any]:
        return _get_tool_definitions()

    @server.call_tool()  # type: ignore[misc]
    async def handle_call_tool(name: str, arguments: Dict[str, Any]) -> List[Any]:
        handler = _HANDLERS.get(name)
        if not handler:
            return _tool_error(f"Unknown tool: {name}")
        return handler(arguments)

    return server


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def _run() -> None:
    """Run the MCP server connected to stdio."""
    from mcp.server.stdio import stdio_server  # type: ignore[import-untyped]

    server = build_server()
    init_options = server.create_initialization_options()
    async with stdio_server() as (read_stream, write_stream):
        await server.run(read_stream, write_stream, init_options)


def main() -> None:
    """Entry point for the ``slcli-mcp`` executable.

    Starts the stdio MCP server. Clients (VS Code Copilot, Claude Desktop,
    Cursor) should configure this as:
        command: slcli
        args: [mcp, serve]
    """
    asyncio.run(_run())


if __name__ == "__main__":
    main()
