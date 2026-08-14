"""MCP (Model Context Protocol) server for slcli.

Exposes SystemLink resources through a query-oriented MCP tool surface so AI
clients can discover, filter, and retrieve resources consistently.
"""

import asyncio
import json
import sys
import urllib.parse
from pathlib import Path
from typing import Annotated, Any, Callable, Dict, List, Literal, Optional, TypeVar

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations
from pydantic import BaseModel, Field

from ._version import __version__

server = MCPServer(
    name="slcli",
    title="SystemLink CLI",
    description="Query-oriented tools for discovering and retrieving NI SystemLink resources.",
    instructions=(
        "Use query_* tools to discover SystemLink resources and get_* tools when an ID or path "
        "is already known. Resolve workspace names to IDs when a service requires an ID. "
        "Filters are service-specific; use substitutions for Dynamic LINQ values. Results are "
        "scoped to the active slcli profile and workspace. An empty result means no matching "
        "visible data was found; it does not prove that a resource does not exist."
    ),
    version=__version__,
)
T = TypeVar("T")

_READ_ONLY_TOOL_ANNOTATIONS = ToolAnnotations(
    read_only_hint=True,
    destructive_hint=False,
    idempotent_hint=True,
    open_world_hint=False,
)

_REFERENCE_ROOT = Path(__file__).parent / "skills" / "slcli" / "references"


class WorkspaceQueryResponse(BaseModel):
    """Structured response returned by workspace discovery."""

    items: List[Dict[str, Any]] = Field(description="Workspaces matching the supplied filters.")
    count: int = Field(description="Number of workspaces in items.")


_CAPABILITIES = """# slcli MCP capabilities

The server exposes query-oriented tools for the main SystemLink resource types.

Core discovery tools:
- query_workspaces, query_users
- search_tags, read_tag_values, get_tag_by_path, query_tag_history
- query_systems, query_assets, query_alarms
- query_test_results, get_test_steps
- query_files, query_notebooks
- query_workitems, query_workitem_templates, query_workflows
- query_feeds, query_feed_packages
- query_webapps
- query_policies, query_comments

Use the corresponding get_* tool when you already know the resource ID/path.
Most query tools support a small set of structured filters plus a raw service
filter when the underlying API supports it.

Detailed references are available as read-only resources:
- slcli://docs/commands
- slcli://docs/filtering
"""


@server.resource("slcli://capabilities")
def capabilities() -> str:
    """Return the tool-selection rules and reference resource index."""
    return _CAPABILITIES


def _read_reference(filename: str) -> str:
    """Read a packaged slcli skill reference for an MCP resource."""
    return (_REFERENCE_ROOT / filename).read_text(encoding="utf-8")


@server.resource("slcli://docs/commands", mime_type="text/markdown")
def commands_reference() -> str:
    """Return the complete slcli command and resource reference."""
    return _read_reference("commands.md")


@server.resource("slcli://docs/filtering", mime_type="text/markdown")
def filtering_reference() -> str:
    """Return filtering and substitution guidance for SystemLink services."""
    return _read_reference("filtering.md")


@server.prompt(
    name="investigate_failed_test_results",
    title="Investigate failed test results",
    description="Prepare a repeatable investigation of failed SystemLink test results.",
)
def investigate_failed_test_results(
    workspace: Annotated[
        Optional[str], Field(description="Workspace name or ID to scope the investigation.")
    ] = None,
    program_name: Annotated[
        Optional[str], Field(description="Optional program name to filter the failed results.")
    ] = None,
    serial_number: Annotated[
        Optional[str], Field(description="Optional DUT serial number to filter the results.")
    ] = None,
    take: Annotated[
        int, Field(ge=1, le=100, description="Maximum number of failed results to inspect.")
    ] = 25,
) -> str:
    """Prepare a tool-driven investigation of failed test results."""
    scope = f"workspace '{workspace}'" if workspace else "the active workspace scope"
    filters = ["status='FAILED'"]
    if program_name:
        filters.append(f"program_name='{program_name}'")
    if serial_number:
        filters.append(f"serial_number='{serial_number}'")
    filter_text = ", ".join(filters)

    return (
        f"Investigate failed SystemLink test results in {scope}. "
        f"Start with query_test_results using {filter_text} and take={take}. "
        "For each result, use get_test_result_by_id and get_test_steps to collect "
        "the failure reason, failing step, DUT identity, program, operator, host, "
        "and timestamps. Group recurring failures by symptom, test step, and "
        "hardware or software identity. Report the evidence, distinguish observed "
        "facts from hypotheses, and identify the next useful diagnostic query."
    )


@server.prompt(
    name="review_fleet_calibration",
    title="Review fleet calibration",
    description="Prepare a repeatable review of SystemLink asset calibration status.",
)
def review_fleet_calibration(
    workspace: Annotated[
        Optional[str], Field(description="Workspace name or ID to scope the asset review.")
    ] = None,
    calibration_status: Annotated[
        Optional[
            Literal[
                "OK",
                "APPROACHING_RECOMMENDED_DUE_DATE",
                "PAST_RECOMMENDED_DUE_DATE",
            ]
        ],
        Field(description="Optional calibration status to focus the review on."),
    ] = None,
    model: Annotated[
        Optional[str], Field(description="Optional asset model name to filter the review.")
    ] = None,
    take: Annotated[
        int, Field(ge=1, le=500, description="Maximum number of assets to inspect.")
    ] = 100,
) -> str:
    """Prepare a tool-driven review of fleet calibration status."""
    scope = f"workspace '{workspace}'" if workspace else "the active workspace scope"
    filters = []
    if calibration_status:
        filters.append(f"calibration_status='{calibration_status}'")
    if model:
        filters.append(f"model='{model}'")
    filter_text = f" with {', '.join(filters)}" if filters else ""

    return (
        f"Review SystemLink asset calibration status for {scope}{filter_text}. "
        f"Start with query_assets using take={take}. Summarize counts by calibration "
        "status, model, and workspace when those fields are present. For assets "
        "approaching or past their recommended due date, use get_asset_by_id to "
        "verify the metadata and identify the owner, location, last calibration, "
        "and recommended due date. Separate overdue assets from assets that are "
        "healthy, call out missing calibration fields, and propose a prioritized "
        "follow-up list grounded in the returned records."
    )


def _dump(data: Any) -> str:
    """Serialize MCP tool output as JSON."""
    return json.dumps(data, default=str)


def _esc(value: str) -> str:
    """Escape double quotes for Dynamic LINQ style filters."""
    return value.replace('"', '\\"')


def _require(value: Optional[str], name: str) -> str:
    """Validate a required string parameter."""
    if not value:
        raise ValueError(f"'{name}' is required")
    return value


def _get_json(url: str) -> Any:
    """Issue a GET request and return JSON."""
    from .utils import make_api_request

    return make_api_request("GET", url, handle_errors=False).json()


def _post_json(url: str, payload: Dict[str, Any]) -> Any:
    """Issue a POST request and return JSON."""
    from .utils import make_api_request

    return make_api_request("POST", url, payload=payload, handle_errors=False).json()


def _call_cli_helper(fn: Callable[..., T], *args: Any, **kwargs: Any) -> T:
    """Convert CLI-style SystemExit failures into regular MCP tool exceptions."""
    try:
        return fn(*args, **kwargs)
    except SystemExit as exc:
        raise RuntimeError(f"CLI helper exited with code {exc.code}") from exc


def _append_filter(
    filter_parts: List[str],
    substitutions: List[Any],
    expression: str,
    value: Optional[str],
) -> None:
    """Append a substitution-based filter clause when a value is provided."""
    if value is None or value == "":
        return
    index = len(substitutions)
    filter_parts.append(expression.format(index=index))
    substitutions.append(value)


def _normalize_systems(data: Any) -> List[Dict[str, Any]]:
    """Normalize the systems API response into a flat list of system records."""
    if isinstance(data, list):
        return [item.get("data", item) for item in data if isinstance(item, dict)]
    if isinstance(data, dict):
        items = data.get("data", data.get("systems", []))
        if isinstance(items, list):
            return [item.get("data", item) if isinstance(item, dict) else item for item in items]
    return []


@server.tool(
    title="Query SystemLink workspaces",
    annotations=_READ_ONLY_TOOL_ANNOTATIONS,
)
def query_workspaces(
    name: Annotated[
        Optional[str], Field(description="Case-insensitive substring of the workspace name.")
    ] = None,
    enabled: Annotated[
        Optional[bool], Field(description="Return only enabled or disabled workspaces.")
    ] = None,
    take: Annotated[
        int, Field(ge=1, le=500, description="Maximum number of workspaces to return.")
    ] = 100,
) -> WorkspaceQueryResponse:
    """Discover workspaces visible to the active SystemLink profile.

    Use this tool to resolve a workspace name to its ID before calling a
    workspace-scoped query tool.
    """
    from .utils import get_base_url

    url = f"{get_base_url()}/niuser/v1/workspaces?take={take}"
    workspaces = _get_json(url).get("workspaces", [])

    filtered: List[Dict[str, Any]] = []
    name_lower = name.lower() if name else None
    for workspace in workspaces:
        if name_lower and name_lower not in str(workspace.get("name", "")).lower():
            continue
        if enabled is not None and bool(workspace.get("enabled")) != enabled:
            continue
        filtered.append(workspace)

    return WorkspaceQueryResponse(items=filtered, count=len(filtered))


@server.tool(
    title="Query SystemLink users",
    annotations=_READ_ONLY_TOOL_ANNOTATIONS,
)
def query_users(
    search: Annotated[
        Optional[str], Field(description="Text matched against first name, last name, or email.")
    ] = None,
    user_type: Annotated[
        Literal["all", "user", "service"], Field(description="User category to include.")
    ] = "all",
    include_disabled: Annotated[
        bool, Field(description="Include disabled users in the result.")
    ] = False,
    take: Annotated[
        int, Field(ge=1, le=500, description="Maximum number of users to return.")
    ] = 100,
) -> str:
    """Discover users by text, category, and enabled status."""
    from .user_click import _query_all_users

    combined_filter: Optional[str] = None
    if search:
        escaped = _esc(search)
        combined_filter = (
            f'firstName.Contains("{escaped}") or '
            f'lastName.Contains("{escaped}") or '
            f'email.Contains("{escaped}")'
        )

    if user_type != "all":
        type_filter = f'type = "{user_type}"'
        combined_filter = (
            f"({combined_filter}) and {type_filter}" if combined_filter else type_filter
        )

    users = _call_cli_helper(
        _query_all_users,
        filter_str=combined_filter,
        sortby="firstName",
        order="asc",
        include_disabled=include_disabled,
        max_items=take,
    )
    return _dump(users)


@server.tool(
    title="Get a SystemLink user",
    annotations=_READ_ONLY_TOOL_ANNOTATIONS,
)
def get_user_by_id(user_id: str) -> str:
    """Get one user when its SystemLink user ID is already known."""
    from .utils import get_base_url

    user_id = _require(user_id, "user_id")
    url = f"{get_base_url()}/niuser/v1/users/{urllib.parse.quote(user_id, safe='')}"
    return _dump(_get_json(url))


@server.tool(annotations=_READ_ONLY_TOOL_ANNOTATIONS)
def search_tags(
    path: Optional[str] = None,
    workspace: Optional[str] = None,
    keywords: Optional[List[str]] = None,
    take: int = 100,
) -> str:
    """Query tags with current values by path substring, workspace, and keywords."""
    from .utils import get_base_url

    filter_parts: List[str] = []
    if workspace:
        filter_parts.append(f'workspace = "{_esc(workspace)}"')
    if path:
        filter_parts.append(f'path = "*{_esc(path)}*"')
    for keyword in keywords or []:
        if keyword:
            filter_parts.append(f'keywords.Contains("{_esc(keyword)}")')

    payload: Dict[str, Any] = {
        "take": take,
        "orderBy": "TIMESTAMP",
        "descending": True,
    }
    if filter_parts:
        payload["filter"] = " && ".join(filter_parts)

    url = f"{get_base_url()}/nitag/v2/query-tags-with-values"
    return _dump(_post_json(url, payload).get("tagsWithValues", []))


@server.tool(annotations=_READ_ONLY_TOOL_ANNOTATIONS)
def read_tag_values(paths: List[str]) -> str:
    """Read current values for multiple tag paths."""
    from .utils import get_base_url, make_api_request

    if not paths:
        raise ValueError("'paths' must contain at least one tag path")

    results: List[Dict[str, Any]] = []
    for path in paths:
        encoded_path = urllib.parse.quote(path, safe="")
        url = f"{get_base_url()}/nitag/v2/tags/{encoded_path}/values/current"
        try:
            current_value = make_api_request("GET", url, handle_errors=False).json()
            results.append({"path": path, "currentValue": current_value})
        except Exception as exc:  # noqa: BLE001
            results.append({"path": path, "currentValue": None, "error": str(exc)})

    return _dump(results)


@server.tool(annotations=_READ_ONLY_TOOL_ANNOTATIONS)
def get_tag_by_path(path: str) -> str:
    """Get tag metadata and current value for a single tag path."""
    from .utils import get_base_url, make_api_request

    path = _require(path, "path")
    encoded_path = urllib.parse.quote(path, safe="")
    tag_url = f"{get_base_url()}/nitag/v2/tags/{encoded_path}"
    tag_data: Dict[str, Any] = make_api_request("GET", tag_url, handle_errors=False).json()

    try:
        value_url = f"{get_base_url()}/nitag/v2/tags/{encoded_path}/values/current"
        tag_data["currentValue"] = make_api_request("GET", value_url, handle_errors=False).json()
    except Exception:  # noqa: BLE001
        tag_data["currentValue"] = None

    return _dump(tag_data)


@server.tool(annotations=_READ_ONLY_TOOL_ANNOTATIONS)
def query_tag_history(path: str, take: int = 100) -> str:
    """Query historical values for a single tag path."""
    from .utils import get_base_url

    path = _require(path, "path")
    encoded_path = urllib.parse.quote(path, safe="")
    url = f"{get_base_url()}/nitag/v2/tags/{encoded_path}/values/history?take={take}"
    data = _get_json(url)
    if isinstance(data, list):
        return _dump(data)
    return _dump(data.get("values", data.get("tagsWithAggregates", [])))


@server.tool(
    title="Query SystemLink systems",
    annotations=_READ_ONLY_TOOL_ANNOTATIONS,
)
def query_systems(
    alias: Optional[str] = None,
    state: Optional[Literal["CONNECTED", "DISCONNECTED"]] = None,
    workspace: Optional[str] = None,
    filter: Optional[str] = None,  # noqa: A002
    take: Annotated[
        int, Field(ge=1, le=500, description="Maximum number of systems to return.")
    ] = 100,
) -> str:
    """Discover managed systems by alias, connection state, workspace, or raw filter."""
    import requests as requests_lib

    from .system_query_utils import (
        MATERIALIZED_SYSTEM_MCP_PROJECTION,
        build_materialized_system_search_filter,
        get_system_query_url,
        get_system_search_url,
    )
    from .utils import make_api_request

    materialized_filter = None
    if filter is None:
        materialized_filter = build_materialized_system_search_filter(
            alias=alias,
            state=state,
            workspace_id=workspace,
        )

    if filter is None:
        search_payload: Dict[str, Any] = {
            "take": take,
            "projection": MATERIALIZED_SYSTEM_MCP_PROJECTION,
        }
        if materialized_filter:
            search_payload["filter"] = materialized_filter
        try:
            data = make_api_request(
                "POST",
                get_system_search_url(),
                payload=search_payload,
                handle_errors=False,
            ).json()
            return _dump(_normalize_systems(data))
        except requests_lib.RequestException:
            pass

    filter_parts: List[str] = []
    if alias:
        filter_parts.append(f'alias.Contains("{_esc(alias)}")')
    if state:
        filter_parts.append(f'connected.data.state = "{state}"')
    if workspace:
        filter_parts.append(f'workspace = "{_esc(workspace)}"')
    if filter:
        filter_parts.append(filter)

    query_payload: Dict[str, Any] = {"take": take}
    if filter_parts:
        query_payload["filter"] = " and ".join(filter_parts)

    data = make_api_request(
        "POST",
        get_system_query_url(),
        payload=query_payload,
        handle_errors=False,
    ).json()
    return _dump(_normalize_systems(data))


@server.tool(annotations=_READ_ONLY_TOOL_ANNOTATIONS)
def get_system_by_id(system_id: str) -> str:
    """Get a single system by ID."""
    from .utils import get_base_url

    system_id = _require(system_id, "system_id")
    url = f"{get_base_url()}/nisysmgmt/v1/systems?id={urllib.parse.quote(system_id, safe='')}"
    items = _normalize_systems(_get_json(url))
    if not items:
        raise ValueError(f"System '{system_id}' not found")
    return _dump(items[0])


@server.tool(
    title="Query SystemLink assets",
    annotations=_READ_ONLY_TOOL_ANNOTATIONS,
)
def query_assets(
    calibration_status: Optional[
        Literal["OK", "APPROACHING_RECOMMENDED_DUE_DATE", "PAST_RECOMMENDED_DUE_DATE"]
    ] = None,
    workspace: Optional[str] = None,
    model: Optional[str] = None,
    filter: Optional[str] = None,  # noqa: A002
    take: Annotated[
        int, Field(ge=1, le=500, description="Maximum number of assets to return.")
    ] = 100,
) -> str:
    """Discover assets by calibration status, workspace, model, or raw filter."""
    from .utils import get_base_url

    filter_parts: List[str] = []
    if calibration_status:
        filter_parts.append(f'CalibrationStatus = "{calibration_status}"')
    if workspace:
        filter_parts.append(f'Workspace = "{_esc(workspace)}"')
    if model:
        filter_parts.append(f'ModelName.Contains("{_esc(model)}")')
    if filter:
        filter_parts.append(filter)

    payload: Dict[str, Any] = {
        "skip": 0,
        "take": take,
        "descending": False,
        "returnCount": True,
    }
    if filter_parts:
        payload["filter"] = " and ".join(filter_parts)

    url = f"{get_base_url()}/niapm/v1/query-assets"
    return _dump(_post_json(url, payload).get("assets", []))


@server.tool(annotations=_READ_ONLY_TOOL_ANNOTATIONS)
def get_asset_by_id(asset_id: str) -> str:
    """Get a single asset by ID."""
    from .utils import get_base_url

    asset_id = _require(asset_id, "asset_id")
    url = f"{get_base_url()}/niapm/v1/assets/{urllib.parse.quote(asset_id, safe='')}"
    return _dump(_get_json(url))


@server.tool(annotations=_READ_ONLY_TOOL_ANNOTATIONS)
def query_alarms(
    severity: Optional[Literal["CRITICAL", "HIGH", "MEDIUM", "LOW"]] = None,
    workspace: Optional[str] = None,
    take: int = 100,
) -> str:
    """Query active alarm instances by severity and workspace."""
    from .utils import get_base_url

    params: List[str] = [f"take={take}"]
    if severity:
        params.append(f"severity={urllib.parse.quote(severity, safe='')}")
    if workspace:
        params.append(f"workspace={urllib.parse.quote(workspace, safe='')}")

    url = f"{get_base_url()}/nialarm/v1/active-instances?{'&'.join(params)}"
    data = _get_json(url)
    if isinstance(data, list):
        return _dump(data)
    return _dump(data.get("alarmInstances", data.get("instances", data.get("items", []))))


@server.tool(
    title="Query SystemLink test results",
    annotations=_READ_ONLY_TOOL_ANNOTATIONS,
)
def query_test_results(
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
    substitutions: Optional[List[str]] = None,
    skip: Annotated[int, Field(ge=0, description="Number of matching results to skip.")] = 0,
    take: Annotated[
        int, Field(ge=1, le=500, description="Maximum number of results to return.")
    ] = 100,
) -> str:
    """Discover test results with structured filters and an optional raw filter."""
    from .utils import get_base_url

    filter_parts: List[str] = []
    filter_substitutions: List[Any] = []
    _append_filter(
        filter_parts,
        filter_substitutions,
        "status.statusType == @{index}",
        status,
    )
    _append_filter(
        filter_parts, filter_substitutions, "programName.Contains(@{index})", program_name
    )
    _append_filter(
        filter_parts, filter_substitutions, "serialNumber.Contains(@{index})", serial_number
    )
    _append_filter(
        filter_parts,
        filter_substitutions,
        "partNumber.Contains(@{index})",
        part_number,
    )
    _append_filter(
        filter_parts,
        filter_substitutions,
        "operator.Contains(@{index})",
        operator,
    )
    _append_filter(
        filter_parts,
        filter_substitutions,
        "hostName.Contains(@{index})",
        host_name,
    )
    _append_filter(
        filter_parts,
        filter_substitutions,
        "workspace == @{index}",
        workspace,
    )

    combined_filter: Optional[str] = None
    if filter:
        extra_filter = filter
        for index, _ in enumerate(substitutions or []):
            extra_filter = extra_filter.replace(
                f"@{index}", f"@{index + len(filter_substitutions)}"
            )
        if filter_parts:
            combined_filter = f"({' && '.join(filter_parts)}) && ({extra_filter})"
        else:
            combined_filter = extra_filter
    elif filter_parts:
        combined_filter = " && ".join(filter_parts)

    payload: Dict[str, Any] = {"skip": skip, "take": take, "descending": True}
    if combined_filter:
        payload["filter"] = combined_filter
    if filter_substitutions or substitutions:
        payload["substitutions"] = filter_substitutions + list(substitutions or [])

    url = f"{get_base_url()}/nitestmonitor/v2/query-results"
    return _dump(_post_json(url, payload).get("results", []))


@server.tool(annotations=_READ_ONLY_TOOL_ANNOTATIONS)
def get_test_result_by_id(result_id: str) -> str:
    """Get a single test result by ID."""
    from .utils import get_base_url

    result_id = _require(result_id, "result_id")
    url = f"{get_base_url()}/nitestmonitor/v2/results/{urllib.parse.quote(result_id, safe='')}"
    return _dump(_get_json(url))


@server.tool(annotations=_READ_ONLY_TOOL_ANNOTATIONS)
def get_test_steps(
    result_id: str,
    take: int = 100,
    continuation_token: Optional[str] = None,
) -> str:
    """Get test steps for a result, with continuation token support."""
    from .utils import get_base_url

    result_id = _require(result_id, "result_id")
    payload: Dict[str, Any] = {
        "filter": "resultId == @0",
        "substitutions": [result_id],
        "take": take,
    }
    if continuation_token:
        payload["continuationToken"] = continuation_token

    url = f"{get_base_url()}/nitestmonitor/v2/query-steps"
    data = _post_json(url, payload)
    return _dump(
        {
            "steps": data.get("steps", []),
            "continuationToken": data.get("continuationToken"),
        }
    )


@server.tool(annotations=_READ_ONLY_TOOL_ANNOTATIONS)
def query_routines(
    enabled: Optional[bool] = None,
    api_version: Literal["v1", "v2"] = "v2",
    take: int = 100,
) -> str:
    """Query automation routines by enabled state and API version."""
    from .utils import get_base_url

    params: List[str] = [f"take={take}"]
    if enabled is True:
        params.append("Enabled=true")
    elif enabled is False:
        params.append("Enabled=false")

    url = f"{get_base_url()}/niroutine/{api_version}/routines?{'&'.join(params)}"
    return _dump(_get_json(url).get("routines", []))


@server.tool(annotations=_READ_ONLY_TOOL_ANNOTATIONS)
def get_routine_by_id(
    routine_id: str,
    api_version: Literal["v1", "v2"] = "v2",
) -> str:
    """Get a single routine by ID."""
    from .utils import get_base_url

    routine_id = _require(routine_id, "routine_id")
    url = f"{get_base_url()}/niroutine/{api_version}/routines/{urllib.parse.quote(routine_id, safe='')}"
    return _dump(_get_json(url))


@server.tool(annotations=_READ_ONLY_TOOL_ANNOTATIONS)
def query_files(
    workspace: Optional[str] = None,
    id_filter: Optional[str] = None,
    name_filter: Optional[str] = None,
    take: int = 100,
) -> str:
    """Query files with the same endpoint-fallback behavior as the CLI."""
    from .file_click import _search_files_with_fallback

    filter_parts: List[str] = []
    if workspace:
        filter_parts.append(f'workspaceId:("{workspace}")')
    if id_filter:
        ids = [f'"{file_id.strip()}"' for file_id in id_filter.split(",") if file_id.strip()]
        if ids:
            filter_parts.append(f"id:({' OR '.join(ids)})")
    if name_filter:
        filter_parts.append(f'(name:("*{name_filter}*") OR extension:("*{name_filter}*"))')

    payload: Dict[str, Any] = {
        "take": take,
        "orderBy": "updated",
        "orderByDescending": True,
    }
    if filter_parts:
        payload["filter"] = " AND ".join(filter_parts)

    resp = _call_cli_helper(
        _search_files_with_fallback,
        payload=payload,
        take=take,
        workspace_id=workspace,
        name_filter=name_filter,
        id_filter=id_filter,
    )
    return _dump(resp.json().get("availableFiles", []))


@server.tool(annotations=_READ_ONLY_TOOL_ANNOTATIONS)
def get_file_by_id(file_id: str) -> str:
    """Get file metadata by ID with query-files/query-files-linq fallback."""
    from .file_click import _get_file_by_id_via_query_files, _get_file_by_id_via_query_files_linq

    file_id = _require(file_id, "file_id")
    file_data = _call_cli_helper(_get_file_by_id_via_query_files, file_id)
    if file_data is None:
        file_data = _call_cli_helper(_get_file_by_id_via_query_files_linq, file_id)
    if file_data is None:
        raise ValueError(f"File '{file_id}' not found")
    return _dump(file_data)


@server.tool(annotations=_READ_ONLY_TOOL_ANNOTATIONS)
def query_notebooks(filter: Optional[str] = None, take: int = 100) -> str:  # noqa: A002
    """Query notebooks with the platform-specific notebook service."""
    from .notebook_click import _query_notebooks_http

    return _dump(_query_notebooks_http(filter_str=filter, take=take)[:take])


@server.tool(annotations=_READ_ONLY_TOOL_ANNOTATIONS)
def get_notebook_by_id(notebook_id: str) -> str:
    """Get a single notebook by ID or path, depending on platform."""
    from .notebook_click import _get_notebook_http

    notebook_id = _require(notebook_id, "notebook_id")
    return _dump(_get_notebook_http(notebook_id))


@server.tool(annotations=_READ_ONLY_TOOL_ANNOTATIONS)
def query_workitems(
    filter: Optional[str] = None,  # noqa: A002
    substitutions: Optional[List[str]] = None,
    workspace: Optional[str] = None,
    take: int = 100,
) -> str:
    """Query work items with continuation-token pagination."""
    from .workitem_click import _query_all_workitems

    items = _call_cli_helper(
        _query_all_workitems,
        filter_expr=filter,
        substitutions=substitutions,
        workspace_filter=workspace,
        max_items=take,
    )
    return _dump(items)


@server.tool(annotations=_READ_ONLY_TOOL_ANNOTATIONS)
def query_workitem_templates(
    filter: Optional[str] = None,  # noqa: A002
    substitutions: Optional[List[str]] = None,
    workspace: Optional[str] = None,
    take: int = 100,
) -> str:
    """Query work item templates with continuation-token pagination."""
    from .workitem_click import _query_all_templates

    items = _call_cli_helper(
        _query_all_templates,
        filter_expr=filter,
        substitutions=substitutions,
        workspace_filter=workspace,
        max_items=take,
    )
    return _dump(items)


@server.tool(annotations=_READ_ONLY_TOOL_ANNOTATIONS)
def query_workflows(workspace: Optional[str] = None, take: int = 100) -> str:
    """Query workflows with continuation-token pagination."""
    from .workitem_click import _query_all_workflows

    return _dump(_call_cli_helper(_query_all_workflows, workspace_filter=workspace, max_items=take))


@server.tool(annotations=_READ_ONLY_TOOL_ANNOTATIONS)
def query_feeds(
    platform: Optional[str] = None,
    workspace: Optional[str] = None,
) -> str:
    """Query feeds by platform and workspace."""
    from .feed_click import _get_feed_base_url, _normalize_platform

    params: List[str] = []
    if platform:
        params.append(f"platform={urllib.parse.quote(_normalize_platform(platform), safe='')}")
    if workspace:
        params.append(f"workspace={urllib.parse.quote(workspace, safe='')}")

    url = f"{_get_feed_base_url()}/feeds"
    if params:
        url = f"{url}?{'&'.join(params)}"

    return _dump(_get_json(url).get("feeds", []))


@server.tool(annotations=_READ_ONLY_TOOL_ANNOTATIONS)
def get_feed_by_id(feed_id: str) -> str:
    """Get a single feed by ID."""
    from .feed_click import _get_feed

    feed_id = _require(feed_id, "feed_id")
    return _dump(_call_cli_helper(_get_feed, feed_id))


@server.tool(annotations=_READ_ONLY_TOOL_ANNOTATIONS)
def query_feed_packages(feed_id: str) -> str:
    """List packages in a feed."""
    from .feed_click import _list_packages

    feed_id = _require(feed_id, "feed_id")
    return _dump(_call_cli_helper(_list_packages, feed_id))


@server.tool(annotations=_READ_ONLY_TOOL_ANNOTATIONS)
def query_webapps(filter: str = "", take: int = 100) -> str:
    """Query webapps using the webapp service continuation-token flow."""
    from .webapp_click import _query_webapps_http

    return _dump(_query_webapps_http(filter, max_items=take))


@server.tool(annotations=_READ_ONLY_TOOL_ANNOTATIONS)
def get_webapp_by_id(webapp_id: str) -> str:
    """Get a single webapp by ID."""
    from .webapp_click import _get_webapp_base_url

    webapp_id = _require(webapp_id, "webapp_id")
    url = f"{_get_webapp_base_url()}/webapps/{urllib.parse.quote(webapp_id, safe='')}"
    return _dump(_get_json(url))


@server.tool(annotations=_READ_ONLY_TOOL_ANNOTATIONS)
def query_policies(
    policy_type: Optional[Literal["default", "internal", "custom", "role"]] = None,
    builtin: bool = False,
    name: Optional[str] = None,
    sortby: Literal["name", "created", "updated"] = "name",
    order: Literal["asc", "desc"] = "asc",
    take: int = 100,
    skip: int = 0,
) -> str:
    """Query authorization policies with the same filter model as the CLI."""
    from .utils import get_base_url

    params: Dict[str, Any] = {
        "take": take,
        "skip": skip,
        "sortby": sortby,
        "order": "ascending" if order == "asc" else "descending",
    }
    if policy_type:
        params["type"] = policy_type
    if builtin:
        params["builtIn"] = "true"
    if name:
        params["name"] = f"*{name}*"

    query = urllib.parse.urlencode(params)
    url = f"{get_base_url()}/niauth/v1/policies?{query}"
    return _dump(_get_json(url).get("policies", []))


@server.tool(annotations=_READ_ONLY_TOOL_ANNOTATIONS)
def get_policy_by_id(policy_id: str) -> str:
    """Get a single authorization policy by ID."""
    from .utils import get_base_url

    policy_id = _require(policy_id, "policy_id")
    url = f"{get_base_url()}/niauth/v1/policies/{urllib.parse.quote(policy_id, safe='')}"
    return _dump(_get_json(url))


@server.tool(annotations=_READ_ONLY_TOOL_ANNOTATIONS)
def query_comments(
    resource_type: str,
    resource_id: str,
) -> str:
    """Query comments for a specific resource type and resource ID."""
    from .comment_click import _get_comment_base_url

    resource_type = _require(resource_type, "resource_type")
    resource_id = _require(resource_id, "resource_id")
    params = urllib.parse.urlencode({"ResourceType": resource_type, "ResourceId": resource_id})
    url = f"{_get_comment_base_url()}/comments?{params}"
    return _dump(_get_json(url).get("comments", []))


async def _run() -> None:
    """Run the MCP server over stdio."""
    print("slcli MCP server ready — waiting for client", file=sys.stderr, flush=True)
    await server.run_stdio_async()


def run_streamable_http(host: str, port: int) -> None:
    """Run the MCP server over streamable HTTP."""
    server.run(transport="streamable-http", host=host, port=port)


def main() -> None:
    """Entry point for the slcli MCP server executable."""
    try:
        asyncio.run(_run())
    except KeyboardInterrupt:
        print("slcli MCP server stopped", file=sys.stderr, flush=True)
        sys.exit(0)


if __name__ == "__main__":
    main()
