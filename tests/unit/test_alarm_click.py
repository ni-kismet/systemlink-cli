"""Unit tests for alarm CLI commands."""

import json
from typing import Any, Dict, List

import click
import pytest
from click.testing import CliRunner

from slcli.alarm_click import (
    _build_alarm_filter,
    _extract_alarm_items,
    _extract_json,
    _parse_properties,
    _query_alarm_page,
    _validate_ids,
    register_alarm_commands,
)


class MockResponse:
    """Minimal response object for alarm command tests."""

    def __init__(self, data: Any, status_code: int = 200) -> None:
        """Initialize a response with JSON data."""
        self._data = data
        self.status_code = status_code

    def json(self) -> Any:
        """Return response JSON."""
        return self._data


def make_cli() -> click.Group:
    """Create a CLI containing alarm commands."""

    @click.group()
    def test_cli() -> None:
        pass

    register_alarm_commands(test_cli)
    return test_cli


@pytest.fixture
def runner() -> CliRunner:
    """Create a Click test runner."""
    return CliRunner()


def patch_alarm_config(monkeypatch: Any) -> None:
    """Patch connection and workspace lookups for isolated command tests."""
    monkeypatch.setattr("slcli.alarm_click.get_base_url", lambda: "https://server.example")
    monkeypatch.setattr("slcli.alarm_click.get_workspace_map", lambda: {})


def test_build_alarm_filter_offsets_user_substitutions() -> None:
    """Convenience filters must not capture raw filter substitutions."""
    expression, substitutions, _ = _build_alarm_filter(
        state="active",
        alarm_id="alarm-1",
        display_name=None,
        channel=None,
        resource_type=None,
        min_severity=None,
        max_severity=None,
        workspace=None,
        filter_query="channel == @0",
        substitutions=("tag-channel",),
    )

    assert expression == "active == true && alarmId == @0 && (channel == @1)"
    assert substitutions == ["alarm-1", "tag-channel"]


def test_build_alarm_filter_resolves_workspace(monkeypatch: Any) -> None:
    """Workspace names should be converted to IDs in the query filter."""
    monkeypatch.setattr(
        "slcli.alarm_click.get_workspace_map",
        lambda: {"workspace-1": "Production"},
    )

    expression, substitutions, workspace_map = _build_alarm_filter(
        state="inactive",
        alarm_id=None,
        display_name="disk",
        channel=None,
        resource_type=None,
        min_severity=2,
        max_severity=4,
        workspace="Production",
        filter_query=None,
        substitutions=(),
    )

    assert expression == (
        "active == false && displayName.Contains(@0) && currentSeverityLevel >= @1 "
        "&& currentSeverityLevel <= @2 && workspace == @3"
    )
    assert substitutions == ["disk", 2, 4, "workspace-1"]
    assert workspace_map == {"workspace-1": "Production"}


def test_extract_alarm_items_supports_legacy_shapes() -> None:
    """The parser should tolerate list and legacy service response keys."""
    assert _extract_alarm_items([{"id": "one"}, "ignored"]) == [{"id": "one"}]
    assert _extract_alarm_items({"alarmInstances": [{"id": "two"}]}) == [{"id": "two"}]
    assert _extract_alarm_items({"filterMatches": [{"id": "three"}]}) == [{"id": "three"}]
    assert _extract_alarm_items({"unexpected": []}) == []
    assert _extract_json(object()) == {}


def test_query_alarm_page_includes_optional_query_flags(monkeypatch: Any) -> None:
    """Query pagination and transition options should be sent to the service."""
    patch_alarm_config(monkeypatch)
    payloads: List[Dict[str, Any]] = []

    def mock_request(method: str, url: str, **kwargs: Any) -> MockResponse:
        payloads.append(kwargs["payload"])
        return MockResponse(
            {
                "alarms": [{"instanceId": "one"}],
                "continuationToken": "next",
                "totalCount": 3,
            }
        )

    monkeypatch.setattr("slcli.alarm_click.make_api_request", mock_request)
    alarms, token, total = _query_alarm_page(
        "active == true",
        ["value"],
        10,
        continuation_token="previous",
        include_transitions=True,
        most_recent_only=True,
    )

    assert alarms == [{"instanceId": "one"}]
    assert token == "next"
    assert total == 3
    assert payloads == [
        {
            "take": 10,
            "returnCount": True,
            "orderBy": "UPDATED_AT",
            "orderByDescending": True,
            "filter": "active == true",
            "substitutions": ["value"],
            "continuationToken": "previous",
            "transitionInclusionOption": "ALL",
            "returnMostRecentlyOccurredOnly": True,
        }
    ]


def test_list_outputs_json_and_uses_alarm_filter_endpoint(
    runner: CliRunner, monkeypatch: Any
) -> None:
    """List should use the current filter endpoint and return alarm records."""
    patch_alarm_config(monkeypatch)
    requests: List[Dict[str, Any]] = []

    def mock_request(method: str, url: str, **kwargs: Any) -> MockResponse:
        requests.append({"method": method, "url": url, "payload": kwargs.get("payload")})
        return MockResponse(
            {
                "alarms": [{"instanceId": "instance-1", "alarmId": "alarm-1", "active": True}],
                "totalCount": 1,
            }
        )

    monkeypatch.setattr("slcli.alarm_click.make_api_request", mock_request)
    result = runner.invoke(
        make_cli(),
        [
            "alarm",
            "list",
            "--state",
            "all",
            "--alarm-id",
            "alarm-1",
            "--filter",
            "channel == @0",
            "--substitution",
            "tag-channel",
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == [
        {"instanceId": "instance-1", "alarmId": "alarm-1", "active": True}
    ]
    assert requests[0]["url"].endswith("/nialarm/v1/query-instances-with-filter")
    assert requests[0]["payload"] == {
        "take": 25,
        "returnCount": True,
        "orderBy": "UPDATED_AT",
        "orderByDescending": True,
        "filter": "alarmId == @0 && (channel == @1)",
        "substitutions": ["alarm-1", "tag-channel"],
    }


def test_alarm_list_json_stops_paging_at_take(runner: CliRunner, monkeypatch: Any) -> None:
    """JSON list output should stop requesting pages at the requested limit."""
    patch_alarm_config(monkeypatch)
    requests: List[Dict[str, Any]] = []

    def mock_request(method: str, url: str, **kwargs: Any) -> MockResponse:
        requests.append(kwargs["payload"])
        return MockResponse(
            {
                "alarms": [{"instanceId": "instance-1"}],
                "continuationToken": "next",
            }
        )

    monkeypatch.setattr("slcli.alarm_click.make_api_request", mock_request)
    result = runner.invoke(make_cli(), ["alarm", "list", "--format", "json", "--take", "1"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == [{"instanceId": "instance-1"}]
    assert len(requests) == 1
    assert requests[0]["take"] == 1


def test_get_alarm_quotes_instance_id(runner: CliRunner, monkeypatch: Any) -> None:
    """Get should safely encode an instance ID in the URL path."""
    patch_alarm_config(monkeypatch)
    requests: List[str] = []

    def mock_request(method: str, url: str, **kwargs: Any) -> MockResponse:
        requests.append(url)
        return MockResponse({"instanceId": "id/with space", "active": True})

    monkeypatch.setattr("slcli.alarm_click.make_api_request", mock_request)
    result = runner.invoke(make_cli(), ["alarm", "get", "id/with space", "-f", "json"])

    assert result.exit_code == 0, result.output
    assert requests == ["https://server.example/nialarm/v1/instances/id%2Fwith%20space"]
    assert json.loads(result.output)["instanceId"] == "id/with space"


def test_get_alarm_table_includes_details(runner: CliRunner, monkeypatch: Any) -> None:
    """The default get format should render useful alarm metadata."""
    patch_alarm_config(monkeypatch)
    monkeypatch.setattr(
        "slcli.alarm_click.make_api_request",
        lambda method, url, **kwargs: MockResponse(
            {
                "instanceId": "instance-1",
                "alarmId": "alarm-1",
                "active": False,
                "keywords": ["system-health"],
                "properties": {"rack": "12"},
                "transitions": [{"transitionType": "CLEAR"}],
            }
        ),
    )
    result = runner.invoke(make_cli(), ["alarm", "get", "instance-1"])

    assert result.exit_code == 0, result.output
    assert "alarm-1" in result.output
    assert "system-health" in result.output
    assert "Transitions" in result.output


def test_acknowledge_alarms_posts_instance_ids(runner: CliRunner, monkeypatch: Any) -> None:
    """Acknowledge should post the selected IDs without a destructive prompt."""
    patch_alarm_config(monkeypatch)
    requests: List[Dict[str, Any]] = []

    def mock_request(method: str, url: str, **kwargs: Any) -> MockResponse:
        requests.append({"method": method, "url": url, "payload": kwargs.get("payload")})
        return MockResponse({"acknowledged": ["one", "two"], "failed": []})

    monkeypatch.setattr("slcli.alarm_click.make_api_request", mock_request)
    monkeypatch.setattr("slcli.alarm_click.check_readonly_mode", lambda operation: None)
    result = runner.invoke(make_cli(), ["alarm", "acknowledge", "one", "two"])

    assert result.exit_code == 0, result.output
    assert requests[0]["payload"] == {"instanceIds": ["one", "two"], "forceClear": False}
    assert "acknowledged: one, two" in result.output


def test_force_clear_uses_force_clear_payload(runner: CliRunner, monkeypatch: Any) -> None:
    """Force-clear should acknowledge and clear in one API request."""
    patch_alarm_config(monkeypatch)
    payloads: List[Dict[str, Any]] = []

    def mock_request(method: str, url: str, **kwargs: Any) -> MockResponse:
        payloads.append(kwargs["payload"])
        return MockResponse({"acknowledged": ["one"], "failed": []})

    monkeypatch.setattr("slcli.alarm_click.make_api_request", mock_request)
    monkeypatch.setattr("slcli.alarm_click.check_readonly_mode", lambda operation: None)
    result = runner.invoke(make_cli(), ["alarm", "force-clear", "one", "--yes"])

    assert result.exit_code == 0, result.output
    assert payloads == [{"instanceIds": ["one"], "forceClear": True}]


def test_delete_uses_bulk_endpoint_and_yes_flag(runner: CliRunner, monkeypatch: Any) -> None:
    """Delete should use the partial-success batch endpoint."""
    patch_alarm_config(monkeypatch)
    requests: List[Dict[str, Any]] = []

    def mock_request(method: str, url: str, **kwargs: Any) -> MockResponse:
        requests.append({"method": method, "url": url, "payload": kwargs.get("payload")})
        return MockResponse({}, status_code=204)

    monkeypatch.setattr("slcli.alarm_click.make_api_request", mock_request)
    monkeypatch.setattr("slcli.alarm_click.check_readonly_mode", lambda operation: None)
    result = runner.invoke(make_cli(), ["alarm", "delete", "one", "two", "--yes"])

    assert result.exit_code == 0, result.output
    assert requests[0]["url"].endswith("/nialarm/v1/delete-instances-by-instance-id")
    assert requests[0]["payload"] == {"instanceIds": ["one", "two"]}
    assert "deleted: one, two" in result.output


def test_force_clear_can_be_cancelled(runner: CliRunner, monkeypatch: Any) -> None:
    """A declined force-clear should not make an API request."""
    patch_alarm_config(monkeypatch)
    requests: List[Dict[str, Any]] = []
    monkeypatch.setattr("slcli.alarm_click.check_readonly_mode", lambda operation: None)
    monkeypatch.setattr("slcli.alarm_click.confirm_bulk_operation", lambda *args, **kwargs: False)
    monkeypatch.setattr(
        "slcli.alarm_click.make_api_request",
        lambda method, url, **kwargs: requests.append(kwargs),
    )

    result = runner.invoke(make_cli(), ["alarm", "force-clear", "one"])

    assert result.exit_code == 0, result.output
    assert requests == []


def test_alarm_list_renders_table_and_transitions(runner: CliRunner, monkeypatch: Any) -> None:
    """Table list output should show state and transition summary."""
    patch_alarm_config(monkeypatch)
    monkeypatch.setattr(
        "slcli.alarm_click.make_api_request",
        lambda method, url, **kwargs: MockResponse(
            {
                "alarms": [
                    {
                        "instanceId": "instance-1",
                        "alarmId": "alarm-1",
                        "active": True,
                        "clear": True,
                        "acknowledged": True,
                        "currentSeverityLevel": 3,
                        "occurredAt": "2026-08-06T12:00:00Z",
                        "transitions": [{}],
                    }
                ],
                "totalCount": 1,
            }
        ),
    )
    result = runner.invoke(make_cli(), ["alarm", "list", "--include-transitions"])

    assert result.exit_code == 0, result.output
    assert "ACTIVE/CLEAR+ACK" in result.output
    assert "Transitions included: 1" in result.output


def test_alarm_list_empty_table(runner: CliRunner, monkeypatch: Any) -> None:
    """Empty table queries should produce a descriptive message."""
    patch_alarm_config(monkeypatch)
    monkeypatch.setattr(
        "slcli.alarm_click.make_api_request",
        lambda method, url, **kwargs: MockResponse({"alarms": []}),
    )
    result = runner.invoke(make_cli(), ["alarm", "list"])

    assert result.exit_code == 0, result.output
    assert "No alarms found." in result.output


def test_alarm_list_ignores_malformed_transitions(runner: CliRunner, monkeypatch: Any) -> None:
    """Malformed transition values should not crash table rendering."""
    patch_alarm_config(monkeypatch)
    monkeypatch.setattr(
        "slcli.alarm_click.make_api_request",
        lambda method, url, **kwargs: MockResponse(
            {"alarms": [{"instanceId": "instance-1", "transitions": None}]}
        ),
    )

    result = runner.invoke(make_cli(), ["alarm", "list", "--include-transitions"])

    assert result.exit_code == 0, result.output
    assert "instance-1" in result.output
    assert "Transitions included" not in result.output


def test_transition_clear_defaults_to_negative_one(runner: CliRunner, monkeypatch: Any) -> None:
    """CLEAR transitions should send the service's sentinel severity."""
    patch_alarm_config(monkeypatch)
    payloads: List[Dict[str, Any]] = []

    def mock_request(method: str, url: str, **kwargs: Any) -> MockResponse:
        payloads.append(kwargs["payload"])
        return MockResponse({"instanceId": "instance-1"})

    monkeypatch.setattr("slcli.alarm_click.make_api_request", mock_request)
    monkeypatch.setattr("slcli.alarm_click.check_readonly_mode", lambda operation: None)
    result = runner.invoke(
        make_cli(),
        ["alarm", "transition", "alarm-1", "--transition", "clear"],
    )

    assert result.exit_code == 0, result.output
    assert payloads == [
        {
            "alarmId": "alarm-1",
            "transition": {"transitionType": "CLEAR", "severityLevel": -1},
        }
    ]


def test_transition_includes_optional_fields_and_properties(
    runner: CliRunner, monkeypatch: Any
) -> None:
    """Transition should pass supported alarm metadata to the API."""
    patch_alarm_config(monkeypatch)
    monkeypatch.setattr(
        "slcli.alarm_click.get_workspace_map",
        lambda: {"workspace-1": "Production"},
    )
    payloads: List[Dict[str, Any]] = []

    def mock_request(method: str, url: str, **kwargs: Any) -> MockResponse:
        payloads.append(kwargs["payload"])
        return MockResponse({"instanceId": "instance-1"})

    monkeypatch.setattr("slcli.alarm_click.make_api_request", mock_request)
    monkeypatch.setattr("slcli.alarm_click.check_readonly_mode", lambda operation: None)
    result = runner.invoke(
        make_cli(),
        [
            "alarm",
            "transition",
            "alarm-1",
            "--workspace",
            "Production",
            "--severity",
            "4",
            "--value",
            "95",
            "--condition",
            "> 90",
            "--short-text",
            "High disk use",
            "--detail-text",
            "Disk use exceeded threshold",
            "--channel",
            "disk",
            "--resource-type",
            "Tag",
            "--display-name",
            "Disk alarm",
            "--description",
            "Disk is nearly full",
            "--created-by",
            "Monitor",
            "--keyword",
            "system-health",
            "--property",
            "rack=12",
        ],
    )

    assert result.exit_code == 0, result.output
    assert payloads == [
        {
            "alarmId": "alarm-1",
            "workspace": "workspace-1",
            "transition": {
                "transitionType": "SET",
                "severityLevel": 4,
                "value": "95",
                "condition": "> 90",
                "shortText": "High disk use",
                "detailText": "Disk use exceeded threshold",
            },
            "channel": "disk",
            "resourceType": "Tag",
            "displayName": "Disk alarm",
            "description": "Disk is nearly full",
            "createdBy": "Monitor",
            "keywords": ["system-health"],
            "properties": {"rack": "12"},
        }
    ]


@pytest.mark.parametrize(
    ("transition", "severity", "message"),
    [
        ("SET", "0", "SET transitions require --severity at least 1."),
        ("CLEAR", "1", "CLEAR transitions require --severity -1."),
        ("SET", "2147483648", "Severity cannot be greater than 2147483647."),
    ],
)
def test_transition_rejects_invalid_severity(
    runner: CliRunner,
    monkeypatch: Any,
    transition: str,
    severity: str,
    message: str,
) -> None:
    """Transition severity must match the service's SET/CLEAR contract."""
    patch_alarm_config(monkeypatch)
    requests: List[Dict[str, Any]] = []
    monkeypatch.setattr(
        "slcli.alarm_click.make_api_request", lambda *args, **kwargs: requests.append(kwargs)
    )
    monkeypatch.setattr("slcli.alarm_click.check_readonly_mode", lambda operation: None)

    result = runner.invoke(
        make_cli(),
        [
            "alarm",
            "transition",
            "alarm-1",
            "--transition",
            transition,
            "--severity",
            severity,
        ],
    )

    assert result.exit_code == 2, result.output
    assert message in result.output
    assert requests == []


def test_parse_properties_rejects_missing_equals() -> None:
    """Property options must use key=value syntax."""
    with pytest.raises(ValueError, match="Use key=value"):
        _parse_properties(("invalid",))


def test_validate_ids_rejects_oversized_batch() -> None:
    """Batch actions should reject IDs beyond the service limit."""
    with pytest.raises(SystemExit) as exc_info:
        _validate_ids(tuple(str(index) for index in range(2)), 1, "test")
    assert exc_info.value.code == 2


def test_monitor_once_queries_and_exits(runner: CliRunner, monkeypatch: Any) -> None:
    """One-shot monitoring should render a snapshot and return."""
    patch_alarm_config(monkeypatch)
    monkeypatch.setattr(
        "slcli.alarm_click.make_api_request",
        lambda method, url, **kwargs: MockResponse(
            {"alarms": [{"instanceId": "instance-1", "active": True}]}
        ),
    )
    result = runner.invoke(make_cli(), ["alarm", "monitor", "--once"])

    assert result.exit_code == 0, result.output
    assert "Alarm monitor" in result.output
    assert "instance-1" in result.output


def test_monitor_once_json_is_parseable(runner: CliRunner, monkeypatch: Any) -> None:
    """One-shot JSON monitoring should emit only the JSON snapshot."""
    patch_alarm_config(monkeypatch)
    monkeypatch.setattr(
        "slcli.alarm_click.make_api_request",
        lambda method, url, **kwargs: MockResponse(
            {"alarms": [{"instanceId": "instance-1", "active": True}]}
        ),
    )

    result = runner.invoke(make_cli(), ["alarm", "monitor", "--once", "--format", "json"])

    assert result.exit_code == 0, result.output
    assert json.loads(result.output) == [{"instanceId": "instance-1", "active": True}]


def test_alarm_table_does_not_refetch_empty_workspace_map(
    runner: CliRunner, monkeypatch: Any
) -> None:
    """Formatting all-workspace results should not fetch workspace data per alarm."""
    calls = 0

    def get_workspace_map() -> Dict[str, str]:
        nonlocal calls
        calls += 1
        return {}

    monkeypatch.setattr("slcli.alarm_click.get_workspace_map", get_workspace_map)
    monkeypatch.setattr("slcli.alarm_click.get_base_url", lambda: "https://server.example")
    monkeypatch.setattr(
        "slcli.alarm_click.make_api_request",
        lambda method, url, **kwargs: MockResponse(
            {"alarms": [{"instanceId": "instance-1", "workspace": "workspace-1"}]}
        ),
    )

    result = runner.invoke(make_cli(), ["alarm", "list", "--workspace", "all"])

    assert result.exit_code == 0, result.output
    assert "workspace-1" in result.output
    assert calls == 0


def test_monitor_stops_cleanly_on_keyboard_interrupt(runner: CliRunner, monkeypatch: Any) -> None:
    """A long-running monitor should provide a clean Ctrl+C exit message."""
    patch_alarm_config(monkeypatch)
    monkeypatch.setattr(
        "slcli.alarm_click.make_api_request",
        lambda method, url, **kwargs: MockResponse({"alarms": []}),
    )

    def stop_monitor(interval: float) -> None:
        raise KeyboardInterrupt

    monkeypatch.setattr("slcli.alarm_click.time.sleep", stop_monitor)
    result = runner.invoke(make_cli(), ["alarm", "monitor", "--interval", "0.1"])

    assert result.exit_code == 0, result.output
    assert "Alarm monitor stopped." in result.output
