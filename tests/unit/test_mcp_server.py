"""Unit tests for the query-oriented slcli MCP server."""

import asyncio
import json
from typing import Any, cast
from unittest.mock import MagicMock

import pytest
from mcp.types import GetPromptResult, TextContent


def make_mock_response(json_data: Any, status_code: int = 200) -> Any:
    """Return a minimal mock response object."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status.return_value = None
    return resp


def test_server_is_mcpserver_instance() -> None:
    """The module-level server is an MCPServer instance."""
    from mcp.server.mcpserver import MCPServer

    from slcli.mcp_server import server

    assert isinstance(server, MCPServer)


def test_server_publishes_client_guidance() -> None:
    """The initialization metadata gives clients the universal tool-routing rules."""
    from slcli._version import __version__
    from slcli.mcp_server import server

    assert server.version == __version__
    instructions = server.instructions
    assert isinstance(instructions, str)
    assert "query_* tools" in instructions
    assert "get_* tools" in instructions
    assert "substitutions" in instructions


def test_server_lists_reference_resources() -> None:
    """The server exposes the capabilities index and detailed packaged references."""
    from slcli.mcp_server import server

    resources = asyncio.run(server.list_resources())
    resource_uris = {resource.uri for resource in resources}

    assert resource_uris == {
        "slcli://capabilities",
        "slcli://docs/commands",
        "slcli://docs/filtering",
    }


def test_server_lists_workflow_prompts() -> None:
    """The server exposes repeatable, user-selected investigation workflows."""
    from slcli.mcp_server import server

    prompts = asyncio.run(server.list_prompts())
    prompt_names = {prompt.name for prompt in prompts}

    assert prompt_names == {"investigate_failed_test_results", "review_fleet_calibration"}


def test_failed_results_prompt_renders_tool_workflow() -> None:
    """The failed-results prompt carries selected filters into its workflow."""
    from slcli.mcp_server import server

    result = cast(
        GetPromptResult,
        asyncio.run(
            server.get_prompt(
                "investigate_failed_test_results",
                {
                    "workspace": "Production",
                    "program_name": "Battery",
                    "serial_number": "DUT-42",
                    "take": 10,
                },
            )
        ),
    )

    message = result.messages[0].content
    assert isinstance(message, TextContent)
    assert "query_test_results" in message.text
    assert "workspace 'Production'" in message.text
    assert "program_name='Battery'" in message.text
    assert "take=10" in message.text
    assert "get_test_steps" in message.text


def test_calibration_prompt_renders_tool_workflow() -> None:
    """The calibration prompt carries selected filters into its workflow."""
    from slcli.mcp_server import server

    result = cast(
        GetPromptResult,
        asyncio.run(
            server.get_prompt(
                "review_fleet_calibration",
                {
                    "workspace": "Production",
                    "calibration_status": "PAST_RECOMMENDED_DUE_DATE",
                    "model": "PXI",
                    "take": 20,
                },
            )
        ),
    )

    message = result.messages[0].content
    assert isinstance(message, TextContent)
    assert "query_assets" in message.text
    assert "calibration_status='PAST_RECOMMENDED_DUE_DATE'" in message.text
    assert "model='PXI'" in message.text
    assert "get_asset_by_id" in message.text


def test_core_tool_metadata_describes_workspace_contract() -> None:
    """The workspace discovery tool publishes titles, annotations, and constraints."""
    from slcli.mcp_server import server

    tools = asyncio.run(server.list_tools())
    workspace_tool = next(tool for tool in tools if tool.name == "query_workspaces")

    assert workspace_tool.title == "Query SystemLink workspaces"
    assert workspace_tool.annotations is not None
    assert workspace_tool.annotations.read_only_hint is True
    assert workspace_tool.annotations.idempotent_hint is True

    take_schema = workspace_tool.input_schema["properties"]["take"]
    assert take_schema["minimum"] == 1
    assert take_schema["maximum"] == 500
    description = take_schema["description"]
    assert isinstance(description, str)
    assert "Maximum number of workspaces" in description


def test_workspace_tool_publishes_structured_output_schema() -> None:
    """Workspace discovery advertises its typed items/count response."""
    from slcli.mcp_server import server

    tools = asyncio.run(server.list_tools())
    workspace_tool = next(tool for tool in tools if tool.name == "query_workspaces")

    assert workspace_tool.output_schema is not None
    assert workspace_tool.output_schema["properties"]["items"]["type"] == "array"
    assert workspace_tool.output_schema["properties"]["count"]["type"] == "integer"


def test_workspace_tool_returns_structured_content(monkeypatch: Any) -> None:
    """An MCP client receives the typed workspace envelope in both result channels."""
    from mcp import Client

    from slcli.mcp_server import server

    workspaces = [{"id": "ws1", "name": "Default", "enabled": True}]
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")
    monkeypatch.setattr(
        "slcli.utils.make_api_request",
        lambda *a, **kw: make_mock_response({"workspaces": workspaces}),
    )

    async def call_workspace_tool() -> Any:
        async with Client(server) as client:
            return await client.call_tool("query_workspaces", {"name": "def"})

    result = asyncio.run(call_workspace_tool())

    assert result.structured_content == {"items": workspaces, "count": 1}
    assert json.loads(result.content[0].text) == {"items": workspaces, "count": 1}


def test_reference_resources_read_packaged_skill_content() -> None:
    """Reference resources use the packaged skill files as their source of truth."""
    from slcli.mcp_server import commands_reference, filtering_reference

    assert commands_reference().startswith("# CLI Command Reference")
    assert filtering_reference().startswith("# Filtering Reference")


def test_reference_resources_use_frozen_layout_candidates(monkeypatch: Any, tmp_path: Any) -> None:
    """Reference resources resolve correctly from the frozen packaged layout."""
    import slcli.mcp_server as mcp_server

    references_dir = tmp_path / "skills" / "slcli" / "references"
    references_dir.mkdir(parents=True)
    (references_dir / "commands.md").write_text("# Frozen Commands", encoding="utf-8")
    (references_dir / "filtering.md").write_text("# Frozen Filtering", encoding="utf-8")

    monkeypatch.setattr(
        mcp_server,
        "_reference_root_candidates",
        lambda: [references_dir],
    )

    assert mcp_server.commands_reference() == "# Frozen Commands"
    assert mcp_server.filtering_reference() == "# Frozen Filtering"


def test_run_streamable_http_passes_host_and_port_to_mcp_2() -> None:
    """The MCP 2 server receives HTTP settings through run arguments."""
    import slcli.mcp_server as mcp_server_module

    captured: dict[str, Any] = {}

    class MockServer:
        def run(self, **kwargs: Any) -> None:
            captured.update(kwargs)

    original_server = mcp_server_module.server
    mcp_server_module.server = MockServer()  # type: ignore[assignment]
    try:
        mcp_server_module.run_streamable_http(host="0.0.0.0", port=9000)
    finally:
        mcp_server_module.server = original_server

    assert captured == {"transport": "streamable-http", "host": "0.0.0.0", "port": 9000}


def test_server_tool_names() -> None:
    """The server registers the canonical query-oriented MCP tools."""
    from slcli.mcp_server import server

    tools = asyncio.run(server.list_tools())
    names = {tool.name for tool in tools}
    expected = {
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

    assert names == expected


def test_is_reachability_failure_detects_nested_exception_group() -> None:
    """Nested connection failures should still be treated as unreachable local MCP servers."""
    from slcli.mcp_reachability import is_reachability_failure

    exc = ExceptionGroup("task group failure", [OSError("Connection refused")])

    assert is_reachability_failure(exc) is True


def test_is_reachability_failure_rejects_unrelated_exception_group() -> None:
    """Unrelated exception groups should not be mistaken for local reachability failures."""
    from slcli.mcp_reachability import is_reachability_failure

    exc = ExceptionGroup("task group failure", [RuntimeError("boom")])

    assert is_reachability_failure(exc) is False


def test_is_reachability_failure_detects_nested_cause_in_exception_group() -> None:
    """Nested causes inside exception-group members should still be classified as unreachable."""
    from slcli.mcp_reachability import is_reachability_failure

    try:
        raise RuntimeError("wrapper") from OSError("Connection refused")
    except RuntimeError as exc:
        grouped = ExceptionGroup("task group failure", [exc])

    assert is_reachability_failure(grouped) is True


def test_is_reachability_failure_detects_nested_context_in_exception_group() -> None:
    """Nested contexts inside exception-group members should still be classified as unreachable."""
    from slcli.mcp_reachability import is_reachability_failure

    try:
        raise TimeoutError("timed out")
    except TimeoutError:
        try:
            raise RuntimeError("wrapper")
        except RuntimeError as exc:
            grouped = ExceptionGroup("task group failure", [exc])

    assert is_reachability_failure(grouped) is True


def test_is_reachability_failure_detects_http_status_from_non_mcp_endpoint() -> None:
    """HTTP status failures from a non-usable local /mcp endpoint should be skipped."""
    from slcli.mcp_reachability import is_reachability_failure

    exc = RuntimeError("Server error '500 Server error' for url 'http://127.0.0.1:8000/mcp'")

    assert is_reachability_failure(exc) is True


def test_query_workspaces_filters_client_side(monkeypatch: Any) -> None:
    """query_workspaces filters the fetched workspace list by name and enabled state."""
    from slcli.mcp_server import query_workspaces

    workspaces = [
        {"id": "ws1", "name": "Default", "enabled": True},
        {"id": "ws2", "name": "Archive", "enabled": False},
    ]
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")
    monkeypatch.setattr(
        "slcli.utils.make_api_request",
        lambda *a, **kw: make_mock_response({"workspaces": workspaces}),
    )

    result = query_workspaces(name="def", enabled=True)
    assert result.model_dump() == {
        "items": [{"id": "ws1", "name": "Default", "enabled": True}],
        "count": 1,
    }


def test_search_tags_builds_expected_filter(monkeypatch: Any) -> None:
    """search_tags combines workspace, path, and keyword filters in the payload."""
    from slcli.mcp_server import search_tags

    captured_payload: list = []
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")

    def mock_request(method: str, url: str, payload: Any = None, **kw: Any) -> Any:
        captured_payload.append(payload)
        return make_mock_response({"tagsWithValues": []})

    monkeypatch.setattr("slcli.utils.make_api_request", mock_request)

    search_tags(path="temp", workspace="ws1", keywords=["critical", "sensor"])

    filter_str = captured_payload[0]["filter"]
    assert 'workspace = "ws1"' in filter_str
    assert 'path = "*temp*"' in filter_str
    assert 'keywords.Contains("critical")' in filter_str
    assert 'keywords.Contains("sensor")' in filter_str


def test_read_tag_values_reads_each_path(monkeypatch: Any) -> None:
    """read_tag_values performs one current-value read per requested path."""
    from slcli.mcp_server import read_tag_values

    seen_urls: list = []
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")

    def mock_request(method: str, url: str, **kw: Any) -> Any:
        seen_urls.append(url)
        return make_mock_response({"value": {"value": "42"}})

    monkeypatch.setattr("slcli.utils.make_api_request", mock_request)

    result = json.loads(read_tag_values(paths=["tag.one", "tag.two"]))

    assert len(result) == 2
    assert result[0]["path"] == "tag.one"
    assert result[1]["path"] == "tag.two"
    assert all("values/current" in url for url in seen_urls)


def test_query_tag_history_uses_tag_historian(monkeypatch: Any) -> None:
    """query_tag_history calls the Tag Historian query endpoint."""
    from slcli.mcp_server import query_tag_history

    seen_calls: list = []
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")

    def mock_request(method: str, url: str, payload: Any = None, **kw: Any) -> Any:
        seen_calls.append({"method": method, "url": url, "payload": payload})
        return make_mock_response(
            {"type": "DOUBLE", "values": [{"timestamp": "2024-01-01T00:00:00Z", "value": "42"}]}
        )

    monkeypatch.setattr("slcli.utils.make_api_request", mock_request)

    result = json.loads(query_tag_history(path="tag.one", take=2))

    assert result == [{"timestamp": "2024-01-01T00:00:00Z", "value": "42", "type": "DOUBLE"}]
    assert seen_calls == [
        {
            "method": "POST",
            "url": "https://test.host/nitaghistorian/v2/tags/query-history",
            "payload": {
                "path": "tag.one",
                "startTime": "0001-01-01T00:00:00Z",
                "endTime": "9999-12-31T23:59:59Z",
                "take": 2,
                "sortOrder": "DESCENDING",
            },
        }
    ]


def test_query_systems_normalizes_wrapped_response(monkeypatch: Any) -> None:
    """query_systems prefers search-systems and normalizes materialized responses."""
    from slcli.mcp_server import query_systems

    seen_calls: list = []
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")
    monkeypatch.setattr("slcli.system_query_utils.get_base_url", lambda: "https://test.host")

    def mock_request(method: str, url: str, **kw: Any) -> Any:
        seen_calls.append({"url": url, "payload": kw.get("payload", {})})
        return make_mock_response({"systems": [{"id": "sys1", "alias": "PXI"}]})

    monkeypatch.setattr("slcli.utils.make_api_request", mock_request)

    assert json.loads(query_systems()) == [{"id": "sys1", "alias": "PXI"}]
    assert seen_calls == [
        {
            "url": "https://test.host/nisysmgmt/v1/materialized/search-systems",
            "payload": {
                "take": 100,
                "projection": [
                    "id",
                    "alias",
                    "workspace",
                    "connected",
                    "advancedGrains.host",
                    "advancedGrains.os",
                ],
            },
        }
    ]


def test_query_systems_falls_back_to_query_systems(monkeypatch: Any) -> None:
    """query_systems falls back to query-systems when search-systems is unavailable."""
    import requests

    from slcli.mcp_server import query_systems

    seen_urls: list = []
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")
    monkeypatch.setattr("slcli.system_query_utils.get_base_url", lambda: "https://test.host")

    def mock_request(method: str, url: str, **kw: Any) -> Any:
        seen_urls.append(url)
        if "materialized/search-systems" in url:
            response = requests.models.Response()
            response.status_code = 404
            raise requests.HTTPError("not found", response=response)
        return make_mock_response([{"data": {"id": "sys1", "alias": "PXI"}}])

    monkeypatch.setattr("slcli.utils.make_api_request", mock_request)

    assert json.loads(query_systems(alias="PXI")) == [{"id": "sys1", "alias": "PXI"}]
    assert seen_urls == [
        "https://test.host/nisysmgmt/v1/materialized/search-systems",
        "https://test.host/nisysmgmt/v1/query-systems",
    ]


def test_query_systems_falls_back_to_query_systems_on_search_error(monkeypatch: Any) -> None:
    """query_systems falls back when search-systems returns a server error."""
    import requests

    from slcli.mcp_server import query_systems

    seen_urls: list = []
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")
    monkeypatch.setattr("slcli.system_query_utils.get_base_url", lambda: "https://test.host")

    def mock_request(method: str, url: str, **kw: Any) -> Any:
        seen_urls.append(url)
        if "materialized/search-systems" in url:
            response = requests.models.Response()
            response.status_code = 500
            raise requests.HTTPError("server error", response=response)
        return make_mock_response([{"data": {"id": "sys1", "alias": "PXI"}}])

    monkeypatch.setattr("slcli.utils.make_api_request", mock_request)

    assert json.loads(query_systems(alias="PXI")) == [{"id": "sys1", "alias": "PXI"}]
    assert seen_urls == [
        "https://test.host/nisysmgmt/v1/materialized/search-systems",
        "https://test.host/nisysmgmt/v1/query-systems",
    ]


def test_query_test_results_combines_structured_and_raw_filters(monkeypatch: Any) -> None:
    """query_test_results preserves substitution offsets when appending a raw filter."""
    from slcli.mcp_server import query_test_results

    captured_payload: list = []
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")

    def mock_request(method: str, url: str, payload: Any = None, **kw: Any) -> Any:
        captured_payload.append(payload)
        return make_mock_response({"results": []})

    monkeypatch.setattr("slcli.utils.make_api_request", mock_request)

    query_test_results(
        status="FAILED",
        program_name="Battery",
        filter="startedAt > @0",
        substitutions=["2026-01-01T00:00:00Z"],
    )

    payload = captured_payload[0]
    assert "status.statusType == @0" in payload["filter"]
    assert "programName.Contains(@1)" in payload["filter"]
    assert "startedAt > @2" in payload["filter"]
    assert payload["substitutions"] == [
        "FAILED",
        "Battery",
        "2026-01-01T00:00:00Z",
    ]


def test_get_test_steps_includes_continuation_token(monkeypatch: Any) -> None:
    """get_test_steps forwards continuationToken and returns it in the result."""
    from slcli.mcp_server import get_test_steps

    captured_payload: list = []
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")

    def mock_request(method: str, url: str, payload: Any = None, **kw: Any) -> Any:
        captured_payload.append(payload)
        return make_mock_response({"steps": [{"id": "s1"}], "continuationToken": "next"})

    monkeypatch.setattr("slcli.utils.make_api_request", mock_request)

    result = json.loads(get_test_steps(result_id="res1", continuation_token="token-1"))

    assert captured_payload[0]["continuationToken"] == "token-1"
    assert result["continuationToken"] == "next"
    assert result["steps"] == [{"id": "s1"}]


def test_query_files_uses_fallback_helper(monkeypatch: Any) -> None:
    """query_files delegates to the CLI fallback helper and returns availableFiles."""
    from slcli.mcp_server import query_files

    captured: list = []

    def mock_search_files_with_fallback(**kwargs: Any) -> Any:
        captured.append(kwargs)
        return make_mock_response({"availableFiles": [{"id": "file1"}]})

    monkeypatch.setattr(
        "slcli.file_click._search_files_with_fallback", mock_search_files_with_fallback
    )

    result = json.loads(query_files(workspace="ws1", name_filter="report", take=10))

    assert result == [{"id": "file1"}]
    assert captured[0]["workspace_id"] == "ws1"
    assert captured[0]["name_filter"] == "report"
    assert captured[0]["take"] == 10


def test_query_notebooks_delegates_to_notebook_helper(monkeypatch: Any) -> None:
    """query_notebooks reuses the platform-specific notebook query helper."""
    from slcli.mcp_server import query_notebooks

    captured: list = []

    def mock_query_notebooks_http(filter_str: Any = None, take: int = 1000) -> Any:
        captured.append({"filter_str": filter_str, "take": take})
        return [{"id": "nb1"}, {"id": "nb2"}]

    monkeypatch.setattr("slcli.notebook_click._query_notebooks_http", mock_query_notebooks_http)

    result = json.loads(query_notebooks(filter='name.Contains("analysis")', take=1))

    assert result == [{"id": "nb1"}]
    assert captured[0] == {"filter_str": 'name.Contains("analysis")', "take": 1}


def test_get_notebook_by_id_delegates_to_notebook_helper(monkeypatch: Any) -> None:
    """get_notebook_by_id reuses the notebook detail helper."""
    from slcli.mcp_server import get_notebook_by_id

    monkeypatch.setattr(
        "slcli.notebook_click._get_notebook_http",
        lambda notebook_id: {"id": notebook_id, "name": "analysis.ipynb"},
    )

    result = json.loads(get_notebook_by_id("nb1"))

    assert result == {"id": "nb1", "name": "analysis.ipynb"}


def test_query_workitems_delegates_to_workitem_helper(monkeypatch: Any) -> None:
    """query_workitems reuses the work item pagination helper."""
    from slcli.mcp_server import query_workitems

    captured: list = []

    def mock_query_all_workitems(**kwargs: Any) -> Any:
        captured.append(kwargs)
        return [{"id": "wi1"}]

    monkeypatch.setattr("slcli.workitem_click._query_all_workitems", mock_query_all_workitems)

    result = json.loads(query_workitems(filter="state == @0", substitutions=["OPEN"], take=5))

    assert result == [{"id": "wi1"}]
    assert captured[0] == {
        "filter_expr": "state == @0",
        "substitutions": ["OPEN"],
        "workspace_filter": None,
        "max_items": 5,
    }


def test_query_policies_builds_expected_url(monkeypatch: Any) -> None:
    """query_policies forwards the CLI policy filters as query parameters."""
    from slcli.mcp_server import query_policies

    captured_urls: list = []
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")

    def mock_request(method: str, url: str, **kw: Any) -> Any:
        captured_urls.append(url)
        return make_mock_response({"policies": []})

    monkeypatch.setattr("slcli.utils.make_api_request", mock_request)

    query_policies(policy_type="custom", builtin=True, name="admin", take=10, skip=2)

    url = captured_urls[0]
    assert "type=custom" in url
    assert "builtIn=true" in url
    assert "name=%2Aadmin%2A" in url
    assert "take=10" in url
    assert "skip=2" in url


def test_query_feeds_builds_expected_url(monkeypatch: Any) -> None:
    """query_feeds forwards platform and workspace filters as query params."""
    from slcli.mcp_server import query_feeds

    captured_urls: list = []
    monkeypatch.setattr("slcli.feed_click._get_feed_base_url", lambda: "https://test.host/nipm/v1")
    monkeypatch.setattr("slcli.feed_click._normalize_platform", lambda platform: platform.upper())

    def mock_request(method: str, url: str, **kw: Any) -> Any:
        captured_urls.append(url)
        return make_mock_response({"feeds": []})

    monkeypatch.setattr("slcli.utils.make_api_request", mock_request)

    query_feeds(platform="windows", workspace="ws1")

    url = captured_urls[0]
    assert "platform=WINDOWS" in url
    assert "workspace=ws1" in url


def test_query_webapps_delegates_to_webapp_helper(monkeypatch: Any) -> None:
    """query_webapps reuses the continuation-token webapp helper."""
    from slcli.mcp_server import query_webapps

    captured: list = []

    def mock_query_webapps_http(filter_str: str, max_items: int = 1000) -> Any:
        captured.append({"filter_str": filter_str, "max_items": max_items})
        return [{"id": "webapp1"}]

    monkeypatch.setattr("slcli.webapp_click._query_webapps_http", mock_query_webapps_http)

    result = json.loads(query_webapps(filter='name.Contains("dashboard")', take=7))

    assert result == [{"id": "webapp1"}]
    assert captured[0] == {"filter_str": 'name.Contains("dashboard")', "max_items": 7}


def test_get_webapp_by_id_builds_expected_url(monkeypatch: Any) -> None:
    """get_webapp_by_id fetches the webapp detail endpoint by ID."""
    from slcli.mcp_server import get_webapp_by_id

    captured_urls: list = []

    def mock_get_webapp_base_url() -> str:
        return "https://test.host/niapp/v1"

    monkeypatch.setattr("slcli.webapp_click._get_webapp_base_url", mock_get_webapp_base_url)

    def mock_request(method: str, url: str, **kw: Any) -> Any:
        captured_urls.append(url)
        return make_mock_response({"id": "app1"})

    monkeypatch.setattr("slcli.utils.make_api_request", mock_request)

    result = json.loads(get_webapp_by_id("app1"))

    assert result == {"id": "app1"}
    assert captured_urls[0].endswith("/webapps/app1")


def test_query_comments_uses_pascal_case_query_params(monkeypatch: Any) -> None:
    """query_comments uses the comment service's required PascalCase query params."""
    from slcli.mcp_server import query_comments

    monkeypatch.setattr(
        "slcli.comment_click._get_comment_base_url", lambda: "https://test.host/nicomments/v1"
    )
    captured_urls: list = []

    def mock_request(method: str, url: str, **kw: Any) -> Any:
        captured_urls.append(url)
        return make_mock_response({"comments": [{"id": "c1"}]})

    monkeypatch.setattr("slcli.utils.make_api_request", mock_request)

    result = json.loads(query_comments(resource_type="workitem:workitem", resource_id="wi1"))

    assert result == [{"id": "c1"}]
    assert "ResourceType=workitem%3Aworkitem" in captured_urls[0]
    assert "ResourceId=wi1" in captured_urls[0]


def test_get_file_by_id_raises_when_not_found(monkeypatch: Any) -> None:
    """get_file_by_id raises a ValueError when neither file lookup path finds a file."""
    from slcli.mcp_server import get_file_by_id

    monkeypatch.setattr("slcli.file_click._get_file_by_id_via_query_files", lambda file_id: None)
    monkeypatch.setattr(
        "slcli.file_click._get_file_by_id_via_query_files_linq", lambda file_id: None
    )

    with pytest.raises(ValueError, match="not found"):
        get_file_by_id("missing")
