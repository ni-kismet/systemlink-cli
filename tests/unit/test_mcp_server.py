"""Unit tests for slcli.mcp_server FastMCP tool functions."""

import asyncio
import json
from typing import Any
from unittest.mock import MagicMock

import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def make_mock_response(json_data: Any, status_code: int = 200) -> Any:
    """Return a minimal mock requests response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_data
    resp.raise_for_status.return_value = None
    return resp


# ---------------------------------------------------------------------------
# server instance
# ---------------------------------------------------------------------------


def test_server_is_fastmcp_instance() -> None:
    """The module-level 'server' is a FastMCP instance."""
    from mcp.server.fastmcp import FastMCP  # type: ignore[import-untyped]

    from slcli.mcp_server import server

    assert isinstance(server, FastMCP)


def test_server_has_twenty_four_tools() -> None:
    """The server registers exactly 24 tools (7 Phase 1 + 7 Phase 2 + 6 Phase 3 + 4 Phase 4)."""
    from slcli.mcp_server import server

    tools = asyncio.run(server.list_tools())
    assert len(tools) == 24


def test_server_tool_names() -> None:
    """Tool names match the expected set."""
    from slcli.mcp_server import server

    tools = asyncio.run(server.list_tools())
    names = {t.name for t in tools}
    expected = {
        # Phase 1
        "workspace_list",
        "tag_list",
        "tag_get",
        "system_list",
        "asset_list",
        "testmonitor_result_list",
        "routine_list",
        # Phase 2
        "tag_set_value",
        "system_get",
        "asset_get",
        "testmonitor_result_get",
        "routine_get",
        "routine_enable",
        "routine_disable",
        # Phase 3
        "user_list",
        "testmonitor_step_list",
        "file_list",
        "asset_calibration_summary",
        "testmonitor_result_summary",
        "notebook_list",
        # Phase 4
        "alarm_list",
        "tag_history",
        "workspace_create",
        "workspace_disable",
    }
    assert names == expected


# ---------------------------------------------------------------------------
# workspace_list
# ---------------------------------------------------------------------------


def test_workspace_list_success(monkeypatch: Any) -> None:
    """workspace_list returns the workspaces array as JSON on success."""
    from slcli.mcp_server import workspace_list

    workspaces = [{"id": "ws1", "name": "Default", "enabled": True}]
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")
    monkeypatch.setattr(
        "slcli.utils.make_api_request",
        lambda method, url, **kw: make_mock_response({"workspaces": workspaces}),
    )

    assert json.loads(workspace_list()) == workspaces


def test_workspace_list_custom_take(monkeypatch: Any) -> None:
    """workspace_list forwards the take parameter in the URL."""
    from slcli.mcp_server import workspace_list

    captured_url: list = []
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")

    def mock_request(method: str, url: str, **kw: Any) -> Any:
        captured_url.append(url)
        return make_mock_response({"workspaces": []})

    monkeypatch.setattr("slcli.utils.make_api_request", mock_request)
    workspace_list(take=10)
    assert "take=10" in captured_url[0]


def test_workspace_list_api_error(monkeypatch: Any) -> None:
    """workspace_list propagates exceptions (FastMCP converts them to error responses)."""
    from slcli.mcp_server import workspace_list

    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")
    monkeypatch.setattr(
        "slcli.utils.make_api_request",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("500 Server Error")),
    )

    with pytest.raises(RuntimeError, match="500"):
        workspace_list()


# ---------------------------------------------------------------------------
# tag_list
# ---------------------------------------------------------------------------


def test_tag_list_success(monkeypatch: Any) -> None:
    """tag_list returns tagsWithValues as JSON on success."""
    from slcli.mcp_server import tag_list

    tags = [{"tag": {"path": "sensor.temp"}, "current": {"value": {"value": "22"}}}]
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")
    monkeypatch.setattr(
        "slcli.utils.make_api_request",
        lambda *a, **kw: make_mock_response({"tagsWithValues": tags}),
    )

    assert json.loads(tag_list()) == tags


def test_tag_list_builds_filter(monkeypatch: Any) -> None:
    """tag_list includes path and workspace in the POST payload filter."""
    from slcli.mcp_server import tag_list

    captured_payload: list = []
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")

    def mock_request(method: str, url: str, payload: Any = None, **kw: Any) -> Any:
        captured_payload.append(payload)
        return make_mock_response({"tagsWithValues": []})

    monkeypatch.setattr("slcli.utils.make_api_request", mock_request)
    tag_list(path="sensor.*", workspace="ws1")

    sent = captured_payload[0]
    assert 'path = "sensor.*"' in sent["filter"]
    assert 'workspace = "ws1"' in sent["filter"]


# ---------------------------------------------------------------------------
# tag_get
# ---------------------------------------------------------------------------


def test_tag_get_success(monkeypatch: Any) -> None:
    """tag_get returns tag metadata merged with currentValue."""
    from slcli.mcp_server import tag_get

    call_order: list = []
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")

    def mock_request(method: str, url: str, **kw: Any) -> Any:
        call_order.append(url)
        if "values/current" in url:
            return make_mock_response({"value": {"value": "42"}})
        return make_mock_response({"path": "sensor.temp", "type": "DOUBLE"})

    monkeypatch.setattr("slcli.utils.make_api_request", mock_request)

    result = tag_get(path="sensor.temp")
    payload = json.loads(result)
    assert payload["path"] == "sensor.temp"
    assert payload["currentValue"] is not None
    assert len(call_order) == 2


def test_tag_get_empty_path_raises(monkeypatch: Any) -> None:
    """tag_get raises ValueError when path is empty."""
    from slcli.mcp_server import tag_get

    with pytest.raises(ValueError, match="path"):
        tag_get(path="")


def test_tag_get_current_value_failure(monkeypatch: Any) -> None:
    """tag_get sets currentValue to None when the value endpoint fails."""
    from slcli.mcp_server import tag_get

    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")

    def mock_request(method: str, url: str, **kw: Any) -> Any:
        if "values/current" in url:
            raise RuntimeError("404 Not Found")
        return make_mock_response({"path": "sensor.temp", "type": "DOUBLE"})

    monkeypatch.setattr("slcli.utils.make_api_request", mock_request)

    assert json.loads(tag_get(path="sensor.temp"))["currentValue"] is None


# ---------------------------------------------------------------------------
# system_list
# ---------------------------------------------------------------------------


def test_system_list_success(monkeypatch: Any) -> None:
    """system_list normalises a dict-with-data-key response."""
    from slcli.mcp_server import system_list

    systems = [{"id": "sys1", "alias": "TestSystem"}]
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")
    monkeypatch.setattr(
        "slcli.utils.make_api_request",
        lambda *a, **kw: make_mock_response({"data": systems}),
    )

    assert json.loads(system_list()) == systems


def test_system_list_list_response(monkeypatch: Any) -> None:
    """system_list normalises a list-of-wrapping-dicts response."""
    from slcli.mcp_server import system_list

    raw_list = [{"data": {"id": "sys1", "alias": "TestSystem"}}]
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")
    monkeypatch.setattr(
        "slcli.utils.make_api_request",
        lambda *a, **kw: make_mock_response(raw_list),
    )

    assert json.loads(system_list()) == [{"id": "sys1", "alias": "TestSystem"}]


def test_system_list_state_filter(monkeypatch: Any) -> None:
    """system_list appends a filter when state is supplied."""
    from slcli.mcp_server import system_list

    captured: list = []
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")

    def mock_request(method: str, url: str, payload: Any = None, **kw: Any) -> Any:
        captured.append(payload or {})
        return make_mock_response({"data": []})

    monkeypatch.setattr("slcli.utils.make_api_request", mock_request)
    system_list(state="CONNECTED")

    assert "CONNECTED" in captured[0].get("filter", "")


# ---------------------------------------------------------------------------
# asset_list
# ---------------------------------------------------------------------------


def test_asset_list_success(monkeypatch: Any) -> None:
    """asset_list returns assets array as JSON from the response."""
    from slcli.mcp_server import asset_list

    assets = [{"id": "a1", "name": "DMM"}]
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")
    monkeypatch.setattr(
        "slcli.utils.make_api_request",
        lambda *a, **kw: make_mock_response({"assets": assets}),
    )

    assert json.loads(asset_list()) == assets


def test_asset_list_calibration_filter(monkeypatch: Any) -> None:
    """asset_list includes CalibrationStatus in the POST payload filter."""
    from slcli.mcp_server import asset_list

    captured: list = []
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")

    def mock_request(method: str, url: str, payload: Any = None, **kw: Any) -> Any:
        captured.append(payload or {})
        return make_mock_response({"assets": []})

    monkeypatch.setattr("slcli.utils.make_api_request", mock_request)
    asset_list(calibration_status="PAST_RECOMMENDED_DUE_DATE")

    assert "PAST_RECOMMENDED_DUE_DATE" in captured[0].get("filter", "")


# ---------------------------------------------------------------------------
# testmonitor_result_list
# ---------------------------------------------------------------------------


def test_testmonitor_result_list_success(monkeypatch: Any) -> None:
    """testmonitor_result_list returns results array as JSON on success."""
    from slcli.mcp_server import testmonitor_result_list

    results = [{"id": "r1", "status": "PASSED"}]
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")
    monkeypatch.setattr(
        "slcli.utils.make_api_request",
        lambda *a, **kw: make_mock_response({"results": results}),
    )

    assert json.loads(testmonitor_result_list()) == results


def test_testmonitor_result_list_status_filter(monkeypatch: Any) -> None:
    """testmonitor_result_list uppercases the status filter."""
    from slcli.mcp_server import testmonitor_result_list

    captured: list = []
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")

    def mock_request(method: str, url: str, payload: Any = None, **kw: Any) -> Any:
        captured.append(payload or {})
        return make_mock_response({"results": []})

    monkeypatch.setattr("slcli.utils.make_api_request", mock_request)
    testmonitor_result_list(status="FAILED")

    assert 'Status = "FAILED"' in captured[0].get("filter", "")


def test_testmonitor_result_list_multiple_filters(monkeypatch: Any) -> None:
    """All convenience filters are ANDed together in the payload."""
    from slcli.mcp_server import testmonitor_result_list

    captured: list = []
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")

    def mock_request(method: str, url: str, payload: Any = None, **kw: Any) -> Any:
        captured.append(payload or {})
        return make_mock_response({"results": []})

    monkeypatch.setattr("slcli.utils.make_api_request", mock_request)
    testmonitor_result_list(status="PASSED", program_name="Battery Test", serial_number="SN-001")

    f = captured[0].get("filter", "")
    assert "PASSED" in f
    assert "Battery Test" in f
    assert "SN-001" in f
    assert "&&" in f


def test_testmonitor_result_list_raw_filter(monkeypatch: Any) -> None:
    """A raw filter expression is included in the payload."""
    from slcli.mcp_server import testmonitor_result_list

    captured: list = []
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")

    def mock_request(method: str, url: str, payload: Any = None, **kw: Any) -> Any:
        captured.append(payload or {})
        return make_mock_response({"results": []})

    monkeypatch.setattr("slcli.utils.make_api_request", mock_request)
    raw = 'StartedAt > "2026-01-01T00:00:00Z"'
    testmonitor_result_list(filter=raw)

    assert raw in captured[0].get("filter", "")


# ---------------------------------------------------------------------------
# routine_list
# ---------------------------------------------------------------------------


def test_routine_list_success(monkeypatch: Any) -> None:
    """routine_list returns routines array as JSON on success."""
    from slcli.mcp_server import routine_list

    routines = [{"id": "rt1", "name": "Alarm Handler"}]
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")
    monkeypatch.setattr(
        "slcli.utils.make_api_request",
        lambda *a, **kw: make_mock_response({"routines": routines}),
    )

    assert json.loads(routine_list()) == routines


def test_routine_list_enabled_true(monkeypatch: Any) -> None:
    """routine_list appends Enabled=true to the URL when enabled=True."""
    from slcli.mcp_server import routine_list

    captured_url: list = []
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")

    def mock_request(method: str, url: str, **kw: Any) -> Any:
        captured_url.append(url)
        return make_mock_response({"routines": []})

    monkeypatch.setattr("slcli.utils.make_api_request", mock_request)
    routine_list(enabled=True)

    assert "Enabled=true" in captured_url[0]


def test_routine_list_enabled_false(monkeypatch: Any) -> None:
    """routine_list appends Enabled=false to the URL when enabled=False."""
    from slcli.mcp_server import routine_list

    captured_url: list = []
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")

    def mock_request(method: str, url: str, **kw: Any) -> Any:
        captured_url.append(url)
        return make_mock_response({"routines": []})

    monkeypatch.setattr("slcli.utils.make_api_request", mock_request)
    routine_list(enabled=False)

    assert "Enabled=false" in captured_url[0]


def test_routine_list_v1(monkeypatch: Any) -> None:
    """routine_list uses v1 path when api_version='v1'."""
    from slcli.mcp_server import routine_list

    captured_url: list = []
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")

    def mock_request(method: str, url: str, **kw: Any) -> Any:
        captured_url.append(url)
        return make_mock_response({"routines": []})

    monkeypatch.setattr("slcli.utils.make_api_request", mock_request)
    routine_list(api_version="v1")

    assert "/niroutine/v1/routines" in captured_url[0]


# ---------------------------------------------------------------------------
# tag_set_value
# ---------------------------------------------------------------------------


def test_tag_set_value_explicit_type(monkeypatch: Any) -> None:
    """tag_set_value uses the supplied data_type without fetching metadata."""
    from slcli.mcp_server import tag_set_value

    calls: list = []
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")

    def mock_request(method: str, url: str, payload: Any = None, **kw: Any) -> Any:
        calls.append((method, url, payload))
        return make_mock_response({})

    monkeypatch.setattr("slcli.utils.make_api_request", mock_request)
    result = tag_set_value(path="sensor.temp", value="42.5", data_type="DOUBLE")

    # Only 1 call — the PUT; no metadata fetch
    assert len(calls) == 1
    method, url, payload = calls[0]
    assert method == "PUT"
    assert "values/current" in url
    assert payload["value"]["value"] == "42.5"
    assert payload["value"]["type"] == "DOUBLE"
    assert json.loads(result)["type"] == "DOUBLE"


def test_tag_set_value_auto_detects_type(monkeypatch: Any) -> None:
    """tag_set_value fetches tag metadata to resolve type when none is supplied."""
    from slcli.mcp_server import tag_set_value

    calls: list = []
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")

    def mock_request(method: str, url: str, payload: Any = None, **kw: Any) -> Any:
        calls.append((method, url, payload))
        if method == "GET":
            return make_mock_response({"path": "sensor.temp", "type": "INT"})
        return make_mock_response({})

    monkeypatch.setattr("slcli.utils.make_api_request", mock_request)
    result = tag_set_value(path="sensor.temp", value="7")

    # GET for metadata, then PUT
    methods = [c[0] for c in calls]
    assert methods == ["GET", "PUT"]
    assert json.loads(result)["type"] == "INT"


def test_tag_set_value_boolean_normalised(monkeypatch: Any) -> None:
    """tag_set_value normalises boolean values to lowercase strings."""
    from slcli.mcp_server import tag_set_value

    captured: list = []
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")

    def mock_request(method: str, url: str, payload: Any = None, **kw: Any) -> Any:
        captured.append((method, payload))
        return make_mock_response({})

    monkeypatch.setattr("slcli.utils.make_api_request", mock_request)
    tag_set_value(path="flag", value="True", data_type="BOOLEAN")

    put_payload = next(p for m, p in captured if m == "PUT")
    assert put_payload["value"]["value"] == "true"


def test_tag_set_value_empty_path_raises(monkeypatch: Any) -> None:
    """tag_set_value raises ValueError for empty path."""
    from slcli.mcp_server import tag_set_value

    with pytest.raises(ValueError, match="path"):
        tag_set_value(path="", value="1")


# ---------------------------------------------------------------------------
# system_get
# ---------------------------------------------------------------------------


def test_system_get_success(monkeypatch: Any) -> None:
    """system_get returns the first system's data dict."""
    from slcli.mcp_server import system_get

    system_data = {"id": "sys-1", "alias": "TestRig"}
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")
    monkeypatch.setattr(
        "slcli.utils.make_api_request",
        lambda *a, **kw: make_mock_response([{"data": system_data}]),
    )

    assert json.loads(system_get("sys-1")) == system_data


def test_system_get_not_found_raises(monkeypatch: Any) -> None:
    """system_get raises ValueError when the API returns an empty list."""
    from slcli.mcp_server import system_get

    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")
    monkeypatch.setattr(
        "slcli.utils.make_api_request",
        lambda *a, **kw: make_mock_response([]),
    )

    with pytest.raises(ValueError, match="not found"):
        system_get("missing-id")


def test_system_get_empty_id_raises(monkeypatch: Any) -> None:
    """system_get raises ValueError for empty system_id."""
    from slcli.mcp_server import system_get

    with pytest.raises(ValueError, match="system_id"):
        system_get("")


# ---------------------------------------------------------------------------
# asset_get
# ---------------------------------------------------------------------------


def test_asset_get_success(monkeypatch: Any) -> None:
    """asset_get returns the asset JSON from GET /niapm/v1/assets/{id}."""
    from slcli.mcp_server import asset_get

    asset_data = {"id": "a1", "name": "DMM", "modelName": "NI-DMM"}
    captured_url: list = []
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")

    def mock_request(method: str, url: str, **kw: Any) -> Any:
        captured_url.append(url)
        return make_mock_response(asset_data)

    monkeypatch.setattr("slcli.utils.make_api_request", mock_request)
    result = asset_get("a1")

    assert json.loads(result) == asset_data
    assert "/niapm/v1/assets/a1" in captured_url[0]


def test_asset_get_empty_id_raises(monkeypatch: Any) -> None:
    """asset_get raises ValueError for empty asset_id."""
    from slcli.mcp_server import asset_get

    with pytest.raises(ValueError, match="asset_id"):
        asset_get("")


# ---------------------------------------------------------------------------
# testmonitor_result_get
# ---------------------------------------------------------------------------


def test_testmonitor_result_get_success(monkeypatch: Any) -> None:
    """testmonitor_result_get returns full result JSON from GET /nitestmonitor/v2/results/{id}."""
    from slcli.mcp_server import testmonitor_result_get

    result_data = {"id": "r1", "status": "PASSED", "programName": "BatteryTest"}
    captured_url: list = []
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")

    def mock_request(method: str, url: str, **kw: Any) -> Any:
        captured_url.append(url)
        return make_mock_response(result_data)

    monkeypatch.setattr("slcli.utils.make_api_request", mock_request)
    result = testmonitor_result_get("r1")

    assert json.loads(result) == result_data
    assert "/nitestmonitor/v2/results/r1" in captured_url[0]


def test_testmonitor_result_get_empty_id_raises(monkeypatch: Any) -> None:
    """testmonitor_result_get raises ValueError for empty result_id."""
    from slcli.mcp_server import testmonitor_result_get

    with pytest.raises(ValueError, match="result_id"):
        testmonitor_result_get("")


# ---------------------------------------------------------------------------
# routine_get
# ---------------------------------------------------------------------------


def test_routine_get_success(monkeypatch: Any) -> None:
    """routine_get returns full routine JSON from GET /niroutine/v2/routines/{id}."""
    from slcli.mcp_server import routine_get

    routine_data = {"id": "rt1", "name": "Alarm Handler", "enabled": True}
    captured_url: list = []
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")

    def mock_request(method: str, url: str, **kw: Any) -> Any:
        captured_url.append(url)
        return make_mock_response(routine_data)

    monkeypatch.setattr("slcli.utils.make_api_request", mock_request)
    result = routine_get("rt1")

    assert json.loads(result) == routine_data
    assert "/niroutine/v2/routines/rt1" in captured_url[0]


def test_routine_get_v1(monkeypatch: Any) -> None:
    """routine_get uses v1 path when api_version='v1'."""
    from slcli.mcp_server import routine_get

    captured_url: list = []
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")

    def mock_request(method: str, url: str, **kw: Any) -> Any:
        captured_url.append(url)
        return make_mock_response({"id": "rt1"})

    monkeypatch.setattr("slcli.utils.make_api_request", mock_request)
    routine_get("rt1", api_version="v1")

    assert "/niroutine/v1/routines/rt1" in captured_url[0]


def test_routine_get_empty_id_raises(monkeypatch: Any) -> None:
    """routine_get raises ValueError for empty routine_id."""
    from slcli.mcp_server import routine_get

    with pytest.raises(ValueError, match="routine_id"):
        routine_get("")


# ---------------------------------------------------------------------------
# routine_enable
# ---------------------------------------------------------------------------


def test_routine_enable_sends_patch(monkeypatch: Any) -> None:
    """routine_enable sends PATCH with enabled=True and returns confirmation."""
    from slcli.mcp_server import routine_enable

    calls: list = []
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")

    def mock_request(method: str, url: str, payload: Any = None, **kw: Any) -> Any:
        calls.append((method, url, payload))
        return make_mock_response({})

    monkeypatch.setattr("slcli.utils.make_api_request", mock_request)
    result = routine_enable("rt1")

    assert len(calls) == 1
    method, url, payload = calls[0]
    assert method == "PATCH"
    assert "/niroutine/v2/routines/rt1" in url
    assert payload == {"enabled": True}
    assert json.loads(result) == {"id": "rt1", "enabled": True}


def test_routine_enable_empty_id_raises(monkeypatch: Any) -> None:
    """routine_enable raises ValueError for empty routine_id."""
    from slcli.mcp_server import routine_enable

    with pytest.raises(ValueError, match="routine_id"):
        routine_enable("")


# ---------------------------------------------------------------------------
# routine_disable
# ---------------------------------------------------------------------------


def test_routine_disable_sends_patch(monkeypatch: Any) -> None:
    """routine_disable sends PATCH with enabled=False and returns confirmation."""
    from slcli.mcp_server import routine_disable

    calls: list = []
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")

    def mock_request(method: str, url: str, payload: Any = None, **kw: Any) -> Any:
        calls.append((method, url, payload))
        return make_mock_response({})

    monkeypatch.setattr("slcli.utils.make_api_request", mock_request)
    result = routine_disable("rt1")

    assert len(calls) == 1
    method, url, payload = calls[0]
    assert method == "PATCH"
    assert "/niroutine/v2/routines/rt1" in url
    assert payload == {"enabled": False}
    assert json.loads(result) == {"id": "rt1", "enabled": False}


def test_routine_disable_empty_id_raises(monkeypatch: Any) -> None:
    """routine_disable raises ValueError for empty routine_id."""
    from slcli.mcp_server import routine_disable

    with pytest.raises(ValueError, match="routine_id"):
        routine_disable("")


# ---------------------------------------------------------------------------
# _detect_tag_type helper
# ---------------------------------------------------------------------------


def test_detect_tag_type_boolean() -> None:
    """_detect_tag_type returns BOOLEAN for true/false strings."""
    from slcli.mcp_server import _detect_tag_type

    assert _detect_tag_type("true") == "BOOLEAN"
    assert _detect_tag_type("false") == "BOOLEAN"
    assert _detect_tag_type("True") == "BOOLEAN"
    assert _detect_tag_type("FALSE") == "BOOLEAN"


def test_detect_tag_type_int() -> None:
    """_detect_tag_type returns INT for integer strings."""
    from slcli.mcp_server import _detect_tag_type

    assert _detect_tag_type("42") == "INT"
    assert _detect_tag_type("-7") == "INT"


def test_detect_tag_type_double() -> None:
    """_detect_tag_type returns DOUBLE for decimal strings."""
    from slcli.mcp_server import _detect_tag_type

    assert _detect_tag_type("3.14") == "DOUBLE"
    assert _detect_tag_type("0.0") == "DOUBLE"


def test_detect_tag_type_string() -> None:
    """_detect_tag_type returns STRING for non-numeric, non-boolean values."""
    from slcli.mcp_server import _detect_tag_type

    assert _detect_tag_type("hello") == "STRING"
    assert _detect_tag_type("") == "STRING"


# ---------------------------------------------------------------------------
# user_list
# ---------------------------------------------------------------------------


def test_user_list_success(monkeypatch: Any) -> None:
    """user_list returns users array as JSON on success."""
    from slcli.mcp_server import user_list

    users = [{"id": "u1", "firstName": "Alice", "status": "active"}]
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")
    monkeypatch.setattr(
        "slcli.utils.make_api_request",
        lambda *a, **kw: make_mock_response({"users": users}),
    )

    assert json.loads(user_list()) == users


def test_user_list_active_filter_default(monkeypatch: Any) -> None:
    """user_list filters to active users by default."""
    from slcli.mcp_server import user_list

    captured: list = []
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")

    def mock_request(method: str, url: str, payload: Any = None, **kw: Any) -> Any:
        captured.append(payload or {})
        return make_mock_response({"users": []})

    monkeypatch.setattr("slcli.utils.make_api_request", mock_request)
    user_list()

    assert 'status = "active"' in captured[0].get("filter", "")


def test_user_list_include_disabled_omits_filter(monkeypatch: Any) -> None:
    """user_list omits active filter when include_disabled=True."""
    from slcli.mcp_server import user_list

    captured: list = []
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")

    def mock_request(method: str, url: str, payload: Any = None, **kw: Any) -> Any:
        captured.append(payload or {})
        return make_mock_response({"users": []})

    monkeypatch.setattr("slcli.utils.make_api_request", mock_request)
    user_list(include_disabled=True)

    assert "status" not in captured[0].get("filter", "")


def test_user_list_raw_filter(monkeypatch: Any) -> None:
    """user_list ANDs a raw filter with the default active filter."""
    from slcli.mcp_server import user_list

    captured: list = []
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")

    def mock_request(method: str, url: str, payload: Any = None, **kw: Any) -> Any:
        captured.append(payload or {})
        return make_mock_response({"users": []})

    monkeypatch.setattr("slcli.utils.make_api_request", mock_request)
    user_list(filter='email.Contains("ni.com")')

    f = captured[0].get("filter", "")
    assert 'status = "active"' in f
    assert 'email.Contains("ni.com")' in f


# ---------------------------------------------------------------------------
# testmonitor_step_list
# ---------------------------------------------------------------------------


def test_testmonitor_step_list_success(monkeypatch: Any) -> None:
    """testmonitor_step_list returns steps array for a given result_id."""
    from slcli.mcp_server import testmonitor_step_list

    steps = [{"name": "Initialize", "status": {"statusType": "PASSED"}}]
    captured: list = []
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")

    def mock_request(method: str, url: str, payload: Any = None, **kw: Any) -> Any:
        captured.append((method, url, payload))
        return make_mock_response({"steps": steps})

    monkeypatch.setattr("slcli.utils.make_api_request", mock_request)
    result = testmonitor_step_list("r1")

    assert json.loads(result) == steps
    method, url, payload = captured[0]
    assert method == "POST"
    assert "query-steps" in url
    assert payload["substitutions"] == ["r1"]
    assert "resultId" in payload["filter"]


def test_testmonitor_step_list_empty_id_raises(monkeypatch: Any) -> None:
    """testmonitor_step_list raises ValueError for empty result_id."""
    from slcli.mcp_server import testmonitor_step_list

    with pytest.raises(ValueError, match="result_id"):
        testmonitor_step_list("")


# ---------------------------------------------------------------------------
# file_list
# ---------------------------------------------------------------------------


def test_file_list_success(monkeypatch: Any) -> None:
    """file_list returns files array from the search-files endpoint."""
    from slcli.mcp_server import file_list

    files = [{"id": "f1", "properties": {"Name": "data.csv"}}]
    captured_url: list = []
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")

    def mock_request(method: str, url: str, **kw: Any) -> Any:
        captured_url.append(url)
        return make_mock_response({"files": files})

    monkeypatch.setattr("slcli.utils.make_api_request", mock_request)
    result = file_list()

    assert json.loads(result) == files
    assert "search-files" in captured_url[0]


def test_file_list_name_filter(monkeypatch: Any) -> None:
    """file_list includes name filter in POST payload."""
    from slcli.mcp_server import file_list

    captured: list = []
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")

    def mock_request(method: str, url: str, payload: Any = None, **kw: Any) -> Any:
        captured.append(payload or {})
        return make_mock_response({"files": []})

    monkeypatch.setattr("slcli.utils.make_api_request", mock_request)
    file_list(name_filter=".csv")

    assert ".csv" in captured[0].get("filter", "")


def test_file_list_workspace_filter(monkeypatch: Any) -> None:
    """file_list adds workspaceId filter when workspace is provided."""
    from slcli.mcp_server import file_list

    captured: list = []
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")

    def mock_request(method: str, url: str, payload: Any = None, **kw: Any) -> Any:
        captured.append(payload or {})
        return make_mock_response({"files": []})

    monkeypatch.setattr("slcli.utils.make_api_request", mock_request)
    file_list(workspace="ws-99")

    assert "ws-99" in captured[0].get("filter", "")


# ---------------------------------------------------------------------------
# asset_calibration_summary
# ---------------------------------------------------------------------------


def test_asset_calibration_summary_success(monkeypatch: Any) -> None:
    """asset_calibration_summary returns the asset-summary JSON."""
    from slcli.mcp_server import asset_calibration_summary

    summary = {
        "total": 42,
        "approachingRecommendedDueDate": 5,
        "pastRecommendedDueDate": 2,
        "outForCalibration": 1,
    }
    captured_url: list = []
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")

    def mock_request(method: str, url: str, **kw: Any) -> Any:
        captured_url.append(url)
        return make_mock_response(summary)

    monkeypatch.setattr("slcli.utils.make_api_request", mock_request)
    result = asset_calibration_summary()

    assert json.loads(result) == summary
    assert "/niapm/v1/asset-summary" in captured_url[0]


# ---------------------------------------------------------------------------
# testmonitor_result_summary
# ---------------------------------------------------------------------------


def test_testmonitor_result_summary_success(monkeypatch: Any) -> None:
    """testmonitor_result_summary returns total and byStatus counts."""
    from slcli.mcp_server import testmonitor_result_summary

    call_count = 0

    def mock_request(method: str, url: str, payload: Any = None, **kw: Any) -> Any:
        nonlocal call_count
        call_count += 1
        # Total query has no status filter; status queries have substitutions
        subs = (payload or {}).get("substitutions", [])
        if not subs:
            return make_mock_response({"totalCount": 100})
        # Return predictable counts per status
        status = subs[-1]
        count_map = {
            "PASSED": 80,
            "FAILED": 15,
            "RUNNING": 3,
            "ERRORED": 2,
            "TERMINATED": 0,
            "TIMEDOUT": 0,
        }
        return make_mock_response({"totalCount": count_map.get(status, 0)})

    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")
    monkeypatch.setattr("slcli.utils.make_api_request", mock_request)

    result = json.loads(testmonitor_result_summary())

    assert result["total"] == 100
    assert result["byStatus"]["PASSED"] == 80
    assert result["byStatus"]["FAILED"] == 15
    # Should have made 7 POST requests (1 total + 6 per-status)
    assert call_count == 7


def test_testmonitor_result_summary_program_name_filter(monkeypatch: Any) -> None:
    """testmonitor_result_summary passes program_name to all sub-queries."""
    from slcli.mcp_server import testmonitor_result_summary

    captured: list = []

    def mock_request(method: str, url: str, payload: Any = None, **kw: Any) -> Any:
        captured.append(payload or {})
        return make_mock_response({"totalCount": 0})

    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")
    monkeypatch.setattr("slcli.utils.make_api_request", mock_request)

    testmonitor_result_summary(program_name="BatteryTest")

    # All payloads should include ProgramName filter
    for p in captured:
        assert "ProgramName" in p.get("filter", "")


# ---------------------------------------------------------------------------
# notebook_list
# ---------------------------------------------------------------------------


def test_notebook_list_sle_success(monkeypatch: Any) -> None:
    """notebook_list returns notebooks array from SLE query endpoint."""
    from slcli.mcp_server import notebook_list

    notebooks = [{"id": "nb1", "name": "Analysis"}]
    captured_url: list = []
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")
    monkeypatch.setattr("slcli.platform.get_platform", lambda: "SLE")

    def mock_request(method: str, url: str, **kw: Any) -> Any:
        captured_url.append(url)
        return make_mock_response({"notebooks": notebooks})

    monkeypatch.setattr("slcli.utils.make_api_request", mock_request)
    result = notebook_list()

    assert json.loads(result) == notebooks
    assert "/ninotebook/v1/notebook/query" in captured_url[0]


def test_notebook_list_sls_success(monkeypatch: Any) -> None:
    """notebook_list uses /ninbexec/v2/query-notebooks on SLS platform."""
    from slcli.mcp_server import notebook_list

    captured_url: list = []
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")
    monkeypatch.setattr("slcli.platform.get_platform", lambda: "SLS")

    def mock_request(method: str, url: str, **kw: Any) -> Any:
        captured_url.append(url)
        return make_mock_response({"notebooks": []})

    monkeypatch.setattr("slcli.utils.make_api_request", mock_request)
    notebook_list()

    assert "/ninbexec/v2/query-notebooks" in captured_url[0]


def test_notebook_list_workspace_filter(monkeypatch: Any) -> None:
    """notebook_list adds workspace filter to the POST payload."""
    from slcli.mcp_server import notebook_list

    captured: list = []
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")
    monkeypatch.setattr("slcli.platform.get_platform", lambda: "SLE")

    def mock_request(method: str, url: str, payload: Any = None, **kw: Any) -> Any:
        captured.append(payload or {})
        return make_mock_response({"notebooks": []})

    monkeypatch.setattr("slcli.utils.make_api_request", mock_request)
    notebook_list(workspace="ws-1")

    assert "ws-1" in captured[0].get("filter", "")


# ---------------------------------------------------------------------------
# alarm_list
# ---------------------------------------------------------------------------


def test_alarm_list_success(monkeypatch: Any) -> None:
    """alarm_list returns alarmInstances array from GET /nialarm/v1/active-instances."""
    from slcli.mcp_server import alarm_list

    alarms = [{"instanceId": "a1", "message": "CPU overtemp", "severity": "HIGH"}]
    captured_url: list = []
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")

    def mock_request(method: str, url: str, **kw: Any) -> Any:
        captured_url.append(url)
        return make_mock_response({"alarmInstances": alarms})

    monkeypatch.setattr("slcli.utils.make_api_request", mock_request)
    result = alarm_list()

    assert json.loads(result) == alarms
    assert "/nialarm/v1/active-instances" in captured_url[0]


def test_alarm_list_severity_filter(monkeypatch: Any) -> None:
    """alarm_list appends severity query param when provided."""
    from slcli.mcp_server import alarm_list

    captured_url: list = []
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")

    def mock_request(method: str, url: str, **kw: Any) -> Any:
        captured_url.append(url)
        return make_mock_response({"alarmInstances": []})

    monkeypatch.setattr("slcli.utils.make_api_request", mock_request)
    alarm_list(severity="CRITICAL")

    assert "severity=CRITICAL" in captured_url[0]


def test_alarm_list_flat_list_response(monkeypatch: Any) -> None:
    """alarm_list handles a flat list response (no wrapper dict)."""
    from slcli.mcp_server import alarm_list

    alarms = [{"instanceId": "a1"}]
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")
    monkeypatch.setattr(
        "slcli.utils.make_api_request",
        lambda *a, **kw: make_mock_response(alarms),
    )

    assert json.loads(alarm_list()) == alarms


# ---------------------------------------------------------------------------
# tag_history
# ---------------------------------------------------------------------------


def test_tag_history_success(monkeypatch: Any) -> None:
    """tag_history returns values array from GET /nitag/v2/tags/{path}/values/history."""
    from slcli.mcp_server import tag_history

    history = [
        {"value": {"value": "22.5"}, "timestamp": "2026-01-01T00:00:00Z"},
        {"value": {"value": "22.3"}, "timestamp": "2026-01-01T00:01:00Z"},
    ]
    captured_url: list = []
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")

    def mock_request(method: str, url: str, **kw: Any) -> Any:
        captured_url.append(url)
        return make_mock_response({"values": history})

    monkeypatch.setattr("slcli.utils.make_api_request", mock_request)
    result = tag_history("sensor.temp")

    assert json.loads(result) == history
    assert "/nitag/v2/tags/sensor.temp/values/history" in captured_url[0]
    assert "take=25" in captured_url[0]


def test_tag_history_custom_take(monkeypatch: Any) -> None:
    """tag_history forwards the take parameter in the URL."""
    from slcli.mcp_server import tag_history

    captured_url: list = []
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")

    def mock_request(method: str, url: str, **kw: Any) -> Any:
        captured_url.append(url)
        return make_mock_response({"values": []})

    monkeypatch.setattr("slcli.utils.make_api_request", mock_request)
    tag_history("sensor.temp", take=50)

    assert "take=50" in captured_url[0]


def test_tag_history_empty_path_raises(monkeypatch: Any) -> None:
    """tag_history raises ValueError for empty path."""
    from slcli.mcp_server import tag_history

    with pytest.raises(ValueError, match="path"):
        tag_history("")


def test_tag_history_path_is_url_encoded(monkeypatch: Any) -> None:
    """tag_history URL-encodes special characters in the path."""
    from slcli.mcp_server import tag_history

    captured_url: list = []
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")

    def mock_request(method: str, url: str, **kw: Any) -> Any:
        captured_url.append(url)
        return make_mock_response({"values": []})

    monkeypatch.setattr("slcli.utils.make_api_request", mock_request)
    tag_history("machine/line1/temperature")

    assert (
        "%2F" in captured_url[0]
        or "/" not in captured_url[0].split("/history")[0].split("tags/")[1]
    )


# ---------------------------------------------------------------------------
# workspace_create
# ---------------------------------------------------------------------------


def test_workspace_create_success(monkeypatch: Any) -> None:
    """workspace_create POSTs to /niuser/v1/workspaces and returns the created object."""
    from slcli.mcp_server import workspace_create

    created = {"id": "ws-new", "name": "My Workspace", "enabled": True}
    calls: list = []
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")

    def mock_request(method: str, url: str, payload: Any = None, **kw: Any) -> Any:
        calls.append((method, url, payload))
        return make_mock_response(created)

    monkeypatch.setattr("slcli.utils.make_api_request", mock_request)
    result = workspace_create("My Workspace")

    assert json.loads(result) == created
    method, url, payload = calls[0]
    assert method == "POST"
    assert "/niuser/v1/workspaces" in url
    assert payload["name"] == "My Workspace"
    assert payload["enabled"] is True


def test_workspace_create_empty_name_raises(monkeypatch: Any) -> None:
    """workspace_create raises ValueError for empty name."""
    from slcli.mcp_server import workspace_create

    with pytest.raises(ValueError, match="name"):
        workspace_create("")


# ---------------------------------------------------------------------------
# workspace_disable
# ---------------------------------------------------------------------------


def test_workspace_disable_success(monkeypatch: Any) -> None:
    """workspace_disable sends PUT with enabled=False and returns confirmation."""
    from slcli.mcp_server import workspace_disable

    calls: list = []
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")

    def mock_request(method: str, url: str, payload: Any = None, **kw: Any) -> Any:
        calls.append((method, url, payload))
        return make_mock_response({})

    monkeypatch.setattr("slcli.utils.make_api_request", mock_request)
    result = workspace_disable("ws-1", "Production")

    assert len(calls) == 1
    method, url, payload = calls[0]
    assert method == "PUT"
    assert "/niuser/v1/workspaces/ws-1" in url
    assert payload == {"name": "Production", "enabled": False}
    assert json.loads(result) == {"id": "ws-1", "name": "Production", "enabled": False}


def test_workspace_disable_empty_id_raises(monkeypatch: Any) -> None:
    """workspace_disable raises ValueError for empty workspace_id."""
    from slcli.mcp_server import workspace_disable

    with pytest.raises(ValueError, match="workspace_id"):
        workspace_disable("", "Production")


def test_workspace_disable_empty_name_raises(monkeypatch: Any) -> None:
    """workspace_disable raises ValueError for empty workspace_name."""
    from slcli.mcp_server import workspace_disable

    with pytest.raises(ValueError, match="workspace_name"):
        workspace_disable("ws-1", "")


# ---------------------------------------------------------------------------
# asset_list — model filter (new)
# ---------------------------------------------------------------------------


def test_asset_list_model_filter(monkeypatch: Any) -> None:
    """asset_list includes ModelName.Contains filter when model is supplied."""
    from slcli.mcp_server import asset_list

    captured: list = []
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")

    def mock_request(method: str, url: str, payload: Any = None, **kw: Any) -> Any:
        captured.append(payload or {})
        return make_mock_response({"assets": []})

    monkeypatch.setattr("slcli.utils.make_api_request", mock_request)
    asset_list(model="SLSC-12101")

    assert "ModelName.Contains" in captured[0].get("filter", "")
    assert "SLSC-12101" in captured[0].get("filter", "")


# ---------------------------------------------------------------------------
# testmonitor_result_list — host_name filter, skip, and default take (new)
# ---------------------------------------------------------------------------


def test_testmonitor_result_list_host_name_filter(monkeypatch: Any) -> None:
    """testmonitor_result_list adds HostName.Contains filter when host_name is supplied."""
    from slcli.mcp_server import testmonitor_result_list

    captured: list = []
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")

    def mock_request(method: str, url: str, payload: Any = None, **kw: Any) -> Any:
        captured.append(payload or {})
        return make_mock_response({"results": []})

    monkeypatch.setattr("slcli.utils.make_api_request", mock_request)
    testmonitor_result_list(host_name="SCHLUMBERGER")

    f = captured[0].get("filter", "")
    assert "HostName.Contains" in f
    assert "SCHLUMBERGER" in f


def test_testmonitor_result_list_skip_forwarded(monkeypatch: Any) -> None:
    """testmonitor_result_list passes skip to the API payload."""
    from slcli.mcp_server import testmonitor_result_list

    captured: list = []
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")

    def mock_request(method: str, url: str, payload: Any = None, **kw: Any) -> Any:
        captured.append(payload or {})
        return make_mock_response({"results": []})

    monkeypatch.setattr("slcli.utils.make_api_request", mock_request)
    testmonitor_result_list(skip=100)

    assert captured[0].get("skip") == 100


def test_testmonitor_result_list_default_take_is_100(monkeypatch: Any) -> None:
    """testmonitor_result_list uses take=100 by default."""
    from slcli.mcp_server import testmonitor_result_list

    captured: list = []
    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")

    def mock_request(method: str, url: str, payload: Any = None, **kw: Any) -> Any:
        captured.append(payload or {})
        return make_mock_response({"results": []})

    monkeypatch.setattr("slcli.utils.make_api_request", mock_request)
    testmonitor_result_list()

    assert captured[0].get("take") == 100


# ---------------------------------------------------------------------------
# testmonitor_result_summary — serial_number, part_number, host_name (new)
# ---------------------------------------------------------------------------


def test_testmonitor_result_summary_serial_number_filter(monkeypatch: Any) -> None:
    """testmonitor_result_summary passes serial_number filter to all sub-queries."""
    from slcli.mcp_server import testmonitor_result_summary

    captured: list = []

    def mock_request(method: str, url: str, payload: Any = None, **kw: Any) -> Any:
        captured.append(payload or {})
        return make_mock_response({"totalCount": 0})

    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")
    monkeypatch.setattr("slcli.utils.make_api_request", mock_request)

    testmonitor_result_summary(serial_number="SN-001")

    for p in captured:
        assert "SerialNumber" in p.get("filter", "")


def test_testmonitor_result_summary_part_number_filter(monkeypatch: Any) -> None:
    """testmonitor_result_summary passes part_number filter to all sub-queries."""
    from slcli.mcp_server import testmonitor_result_summary

    captured: list = []

    def mock_request(method: str, url: str, payload: Any = None, **kw: Any) -> Any:
        captured.append(payload or {})
        return make_mock_response({"totalCount": 0})

    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")
    monkeypatch.setattr("slcli.utils.make_api_request", mock_request)

    testmonitor_result_summary(part_number="BATT-8")

    for p in captured:
        assert "PartNumber" in p.get("filter", "")


def test_testmonitor_result_summary_host_name_filter(monkeypatch: Any) -> None:
    """testmonitor_result_summary passes host_name filter to all sub-queries."""
    from slcli.mcp_server import testmonitor_result_summary

    captured: list = []

    def mock_request(method: str, url: str, payload: Any = None, **kw: Any) -> Any:
        captured.append(payload or {})
        return make_mock_response({"totalCount": 0})

    monkeypatch.setattr("slcli.utils.get_base_url", lambda: "https://test.host")
    monkeypatch.setattr("slcli.utils.make_api_request", mock_request)

    testmonitor_result_summary(host_name="My-Host")

    for p in captured:
        assert "HostName" in p.get("filter", "")
