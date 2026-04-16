"""E2E tests for the slcli MCP server over streamable HTTP.

These tests connect to a locally running MCP server started with:

    poetry run slcli mcp serve --transport streamable-http

Environment variables:
- SLCLI_MCP_E2E_URL: MCP endpoint URL (default: http://127.0.0.1:8000/mcp)
- SLCLI_MCP_E2E_TIMEOUT: transport timeout in seconds (default: 5)
- SLCLI_MCP_E2E_<RESOURCE>: optional resource overrides for sparse environments
"""

import asyncio
import json
import os
from typing import Any, Dict, List, Optional, Tuple

import httpx
import pytest
from mcp import ClientSession
from mcp.client.streamable_http import streamable_http_client
from mcp.types import CallToolResult, ListToolsResult, TextContent

DEFAULT_MCP_URL = "http://127.0.0.1:8000/mcp"
DEFAULT_TIMEOUT_SECONDS = 5
MISSING_RESOURCE_SENTINEL = "mcp-e2e-missing-resource"
MISSING_TAG_PATH = "mcp.e2e.missing.tag"

EXPECTED_TOOL_NAMES = {
    "query_workspaces",
    "query_users",
    "get_user_by_id",
    "search_tags",
    "read_tag_values",
    "get_tag_by_path",
    "query_tag_history",
    "query_systems",
    "get_system_by_id",
    "query_assets",
    "get_asset_by_id",
    "query_alarms",
    "query_test_results",
    "get_test_result_by_id",
    "get_test_steps",
    "query_routines",
    "get_routine_by_id",
    "query_files",
    "get_file_by_id",
    "query_notebooks",
    "get_notebook_by_id",
    "query_workitems",
    "query_workitem_templates",
    "query_workflows",
    "query_feeds",
    "get_feed_by_id",
    "query_feed_packages",
    "query_webapps",
    "get_webapp_by_id",
    "query_policies",
    "get_policy_by_id",
    "query_comments",
}


def _env(name: str, default: Optional[str] = None) -> Optional[str]:
    """Return an environment override when present."""
    value = os.getenv(name)
    if value is None:
        return default
    stripped = value.strip()
    return stripped or default


def _tool_result_text(result: CallToolResult) -> str:
    """Return the concatenated text payload from a tool result."""
    parts: List[str] = []
    for item in result.content:
        if isinstance(item, TextContent):
            parts.append(item.text)
            continue

        text = getattr(item, "text", None)
        if isinstance(text, str):
            parts.append(text)

    if not parts:
        pytest.fail("MCP tool result did not contain any text content")
    return "\n".join(parts)


def _tool_result_json(result: CallToolResult) -> Any:
    """Parse the JSON payload returned by an MCP tool."""
    return json.loads(_tool_result_text(result))


def _first_id(items: Any) -> Optional[str]:
    """Return the first top-level item ID from a list response."""
    if not isinstance(items, list):
        return None
    for item in items:
        if isinstance(item, dict):
            value = item.get("id")
            if isinstance(value, str) and value:
                return value
    return None


def _first_tag_path(items: Any) -> Optional[str]:
    """Return the first tag path from a search_tags response."""
    if not isinstance(items, list):
        return None
    for item in items:
        if not isinstance(item, dict):
            continue
        tag_data = item.get("tag", item)
        if isinstance(tag_data, dict):
            path = tag_data.get("path")
            if isinstance(path, str) and path:
                return path
    return None


def _resource_value(
    state: Dict[str, Any],
    state_key: str,
    env_name: str,
    fallback: str,
) -> Tuple[str, bool]:
    """Return a discovered or configured resource value and whether it is synthetic."""
    value = state.get(state_key)
    if isinstance(value, str) and value:
        return value, False

    env_value = _env(env_name)
    if env_value:
        return env_value, False

    return fallback, True


def _comment_target(state: Dict[str, Any]) -> Tuple[str, str]:
    """Choose a valid resource type and ID pair for query_comments."""
    comment_type = _env("SLCLI_MCP_E2E_COMMENT_RESOURCE_TYPE")
    comment_id = _env("SLCLI_MCP_E2E_COMMENT_RESOURCE_ID")
    if comment_type and comment_id:
        return comment_type, comment_id

    target_pairs = [
        ("workitem:workitem", state.get("workitem_id")),
        ("niapm:Asset", state.get("asset_id")),
        ("nisysmgmt:System", state.get("system_id")),
        ("testmonitor:Result", state.get("result_id")),
    ]

    for resource_type, resource_id in target_pairs:
        if isinstance(resource_id, str) and resource_id:
            return resource_type, resource_id

    return "workitem:workitem", MISSING_RESOURCE_SENTINEL


def _is_reachability_failure(exc: Exception) -> bool:
    """Return True when an exception indicates the local MCP server is unreachable."""
    if isinstance(exc, (OSError, TimeoutError)):
        return True

    message = str(exc).lower()
    return any(
        token in message
        for token in (
            "connection refused",
            "connect error",
            "all connection attempts failed",
            "timed out",
            "timeout",
            "name or service not known",
            "nodename nor servname provided",
            "server disconnected",
        )
    )


async def _call_tool(
    session: ClientSession,
    name: str,
    arguments: Dict[str, Any],
    *,
    allow_error: bool = False,
) -> CallToolResult:
    """Call an MCP tool and fail on unexpected MCP-level errors."""
    result = await session.call_tool(name, arguments)
    if result.isError and not allow_error:
        pytest.fail(f"Tool '{name}' returned an unexpected error: {_tool_result_text(result)}")
    return result


async def _exercise_mcp_tools(mcp_url: str, timeout_seconds: int) -> None:
    """Connect to the live streamable HTTP server and exercise the MCP tool surface."""
    state: Dict[str, Any] = {}

    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout_seconds)) as http_client:
            async with streamable_http_client(
                mcp_url,
                http_client=http_client,
            ) as (read_stream, write_stream, _):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()

                    tools: ListToolsResult = await session.list_tools()
                    tool_names = {tool.name for tool in tools.tools}
                    assert tool_names == EXPECTED_TOOL_NAMES

                    workspaces = _tool_result_json(
                        await _call_tool(session, "query_workspaces", {"take": 5})
                    )
                    state["workspace_id"] = _first_id(workspaces)

                    users = _tool_result_json(await _call_tool(session, "query_users", {"take": 5}))
                    state["user_id"] = _first_id(users)

                    tags = _tool_result_json(await _call_tool(session, "search_tags", {"take": 5}))
                    state["tag_path"] = _first_tag_path(tags)

                    systems = _tool_result_json(
                        await _call_tool(session, "query_systems", {"take": 5})
                    )
                    state["system_id"] = _first_id(systems)

                    assets = _tool_result_json(
                        await _call_tool(session, "query_assets", {"take": 5})
                    )
                    state["asset_id"] = _first_id(assets)

                    await _call_tool(session, "query_alarms", {"take": 5}, allow_error=True)

                    results = _tool_result_json(
                        await _call_tool(session, "query_test_results", {"take": 5})
                    )
                    state["result_id"] = _first_id(results)

                    routines = _tool_result_json(
                        await _call_tool(session, "query_routines", {"take": 5})
                    )
                    state["routine_id"] = _first_id(routines)

                    files = _tool_result_json(await _call_tool(session, "query_files", {"take": 5}))
                    state["file_id"] = _first_id(files)

                    notebooks = _tool_result_json(
                        await _call_tool(session, "query_notebooks", {"take": 5})
                    )
                    state["notebook_id"] = _first_id(notebooks)

                    workitems = _tool_result_json(
                        await _call_tool(session, "query_workitems", {"take": 5})
                    )
                    state["workitem_id"] = _first_id(workitems)

                    templates = _tool_result_json(
                        await _call_tool(session, "query_workitem_templates", {"take": 5})
                    )
                    state["template_id"] = _first_id(templates)

                    workflows = _tool_result_json(
                        await _call_tool(session, "query_workflows", {"take": 5})
                    )
                    state["workflow_id"] = _first_id(workflows)

                    feeds = _tool_result_json(await _call_tool(session, "query_feeds", {}))
                    state["feed_id"] = _first_id(feeds)

                    webapps = _tool_result_json(
                        await _call_tool(session, "query_webapps", {"take": 5})
                    )
                    state["webapp_id"] = _first_id(webapps)

                    policy_result = await _call_tool(
                        session,
                        "query_policies",
                        {"take": 5},
                        allow_error=True,
                    )
                    if not policy_result.isError:
                        policies = _tool_result_json(policy_result)
                        state["policy_id"] = _first_id(policies)

                    comment_resource_type, comment_resource_id = _comment_target(state)
                    await _call_tool(
                        session,
                        "query_comments",
                        {
                            "resource_type": comment_resource_type,
                            "resource_id": comment_resource_id,
                        },
                    )

                    user_id, missing_user = _resource_value(
                        state,
                        "user_id",
                        "SLCLI_MCP_E2E_USER_ID",
                        MISSING_RESOURCE_SENTINEL,
                    )
                    await _call_tool(
                        session,
                        "get_user_by_id",
                        {"user_id": user_id},
                        allow_error=True,
                    )

                    tag_path, missing_tag = _resource_value(
                        state,
                        "tag_path",
                        "SLCLI_MCP_E2E_TAG_PATH",
                        MISSING_TAG_PATH,
                    )
                    await _call_tool(session, "read_tag_values", {"paths": [tag_path]})
                    await _call_tool(
                        session,
                        "get_tag_by_path",
                        {"path": tag_path},
                        allow_error=True,
                    )
                    await _call_tool(
                        session,
                        "query_tag_history",
                        {"path": tag_path, "take": 5},
                        allow_error=True,
                    )

                    system_id, missing_system = _resource_value(
                        state,
                        "system_id",
                        "SLCLI_MCP_E2E_SYSTEM_ID",
                        MISSING_RESOURCE_SENTINEL,
                    )
                    await _call_tool(
                        session,
                        "get_system_by_id",
                        {"system_id": system_id},
                        allow_error=True,
                    )

                    asset_id, missing_asset = _resource_value(
                        state,
                        "asset_id",
                        "SLCLI_MCP_E2E_ASSET_ID",
                        MISSING_RESOURCE_SENTINEL,
                    )
                    await _call_tool(
                        session,
                        "get_asset_by_id",
                        {"asset_id": asset_id},
                        allow_error=True,
                    )

                    result_id, missing_result = _resource_value(
                        state,
                        "result_id",
                        "SLCLI_MCP_E2E_RESULT_ID",
                        MISSING_RESOURCE_SENTINEL,
                    )
                    await _call_tool(
                        session,
                        "get_test_result_by_id",
                        {"result_id": result_id},
                        allow_error=True,
                    )
                    await _call_tool(
                        session,
                        "get_test_steps",
                        {"result_id": result_id, "take": 5},
                        allow_error=True,
                    )

                    routine_id, missing_routine = _resource_value(
                        state,
                        "routine_id",
                        "SLCLI_MCP_E2E_ROUTINE_ID",
                        MISSING_RESOURCE_SENTINEL,
                    )
                    await _call_tool(
                        session,
                        "get_routine_by_id",
                        {"routine_id": routine_id},
                        allow_error=True,
                    )

                    file_id, missing_file = _resource_value(
                        state,
                        "file_id",
                        "SLCLI_MCP_E2E_FILE_ID",
                        MISSING_RESOURCE_SENTINEL,
                    )
                    await _call_tool(
                        session,
                        "get_file_by_id",
                        {"file_id": file_id},
                        allow_error=True,
                    )

                    notebook_id, missing_notebook = _resource_value(
                        state,
                        "notebook_id",
                        "SLCLI_MCP_E2E_NOTEBOOK_ID",
                        MISSING_RESOURCE_SENTINEL,
                    )
                    await _call_tool(
                        session,
                        "get_notebook_by_id",
                        {"notebook_id": notebook_id},
                        allow_error=True,
                    )

                    await _call_tool(
                        session,
                        "query_workitems",
                        {"take": 5, "workspace": state.get("workspace_id")},
                    )
                    await _call_tool(
                        session,
                        "query_workitem_templates",
                        {"take": 5, "workspace": state.get("workspace_id")},
                    )
                    await _call_tool(
                        session,
                        "query_workflows",
                        {"take": 5, "workspace": state.get("workspace_id")},
                    )

                    feed_id, missing_feed = _resource_value(
                        state,
                        "feed_id",
                        "SLCLI_MCP_E2E_FEED_ID",
                        MISSING_RESOURCE_SENTINEL,
                    )
                    await _call_tool(
                        session,
                        "get_feed_by_id",
                        {"feed_id": feed_id},
                        allow_error=True,
                    )
                    await _call_tool(
                        session,
                        "query_feed_packages",
                        {"feed_id": feed_id},
                        allow_error=True,
                    )

                    webapp_id, missing_webapp = _resource_value(
                        state,
                        "webapp_id",
                        "SLCLI_MCP_E2E_WEBAPP_ID",
                        MISSING_RESOURCE_SENTINEL,
                    )
                    await _call_tool(
                        session,
                        "get_webapp_by_id",
                        {"webapp_id": webapp_id},
                        allow_error=True,
                    )

                    policy_id, missing_policy = _resource_value(
                        state,
                        "policy_id",
                        "SLCLI_MCP_E2E_POLICY_ID",
                        MISSING_RESOURCE_SENTINEL,
                    )
                    await _call_tool(
                        session,
                        "get_policy_by_id",
                        {"policy_id": policy_id},
                        allow_error=True,
                    )
    except Exception as exc:
        if _is_reachability_failure(exc):
            pytest.skip(f"Local MCP server is not reachable at {mcp_url}: {exc}")
        raise


@pytest.mark.e2e
@pytest.mark.slow
class TestMcpStreamableHttpE2E:
    """End-to-end tests for a locally running slcli MCP streamable HTTP server."""

    def test_exercise_all_tools(self) -> None:
        """Connect to the local streamable HTTP server and exercise the full MCP tool set."""
        mcp_url = _env("SLCLI_MCP_E2E_URL", DEFAULT_MCP_URL) or DEFAULT_MCP_URL
        timeout_seconds = int(_env("SLCLI_MCP_E2E_TIMEOUT", str(DEFAULT_TIMEOUT_SECONDS)) or 5)
        asyncio.run(_exercise_mcp_tools(mcp_url, timeout_seconds))
