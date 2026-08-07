"""CLI commands for SystemLink Alarm Management."""

import datetime
import json
import re
import sys
import time
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote

import click
import questionary

from .cli_utils import confirm_bulk_operation, validate_output_format
from .rich_output import render_table
from .universal_handlers import FilteredResponse, UniversalResponseHandler
from .utils import (
    ExitCodes,
    check_readonly_mode,
    format_success,
    get_base_url,
    get_workspace_map,
    handle_api_error,
    make_api_request,
)
from .workspace_utils import get_effective_workspace, resolve_workspace_filter

_MAX_QUERY_TAKE = 1000
_MAX_ACKNOWLEDGE_IDS = 1000
_MAX_DELETE_IDS = 5000
_MAX_SEVERITY = 2_147_483_647


def _get_alarm_base_url() -> str:
    """Get the base URL for the Alarm Management API."""
    return f"{get_base_url()}/nialarm/v1"


def _parse_substitutions(values: Tuple[str, ...]) -> List[Any]:
    """Parse CLI substitution values as JSON when possible."""
    parsed: List[Any] = []
    for value in values:
        try:
            parsed.append(json.loads(value))
        except (json.JSONDecodeError, TypeError):
            parsed.append(value)
    return parsed


def _append_filter(parts: List[str], substitutions: List[Any], expression: str, value: Any) -> None:
    """Append a parameterized filter expression when a value is provided."""
    if value is None or value == "":
        return
    index = len(substitutions)
    parts.append(expression.format(index=index))
    substitutions.append(value)


def _offset_filter_substitutions(filter_query: str, offset: int) -> str:
    """Offset substitution indexes in a user-provided filter expression."""
    return re.sub(
        r"@(\d+)",
        lambda match: f"@{int(match.group(1)) + offset}",
        filter_query,
    )


def _build_alarm_filter(
    state: str,
    alarm_id: Optional[str],
    display_name: Optional[str],
    channel: Optional[str],
    resource_type: Optional[str],
    min_severity: Optional[int],
    max_severity: Optional[int],
    workspace: Optional[str],
    filter_query: Optional[str],
    substitutions: Tuple[str, ...],
) -> Tuple[Optional[str], List[Any], Dict[str, str]]:
    """Build a Dynamic LINQ alarm filter and resolve workspace display data."""
    parts: List[str] = []
    filter_substitutions: List[Any] = []
    workspace_map: Dict[str, str] = {}

    if state == "active":
        parts.append("active == true")
    elif state == "inactive":
        parts.append("active == false")

    _append_filter(parts, filter_substitutions, "alarmId == @{index}", alarm_id)
    _append_filter(parts, filter_substitutions, "displayName.Contains(@{index})", display_name)
    _append_filter(parts, filter_substitutions, "channel.Contains(@{index})", channel)
    _append_filter(parts, filter_substitutions, "resourceType == @{index}", resource_type)
    _append_filter(parts, filter_substitutions, "currentSeverityLevel >= @{index}", min_severity)
    _append_filter(parts, filter_substitutions, "currentSeverityLevel <= @{index}", max_severity)

    effective_workspace = get_effective_workspace(workspace)
    if effective_workspace:
        try:
            workspace_map = get_workspace_map()
        except Exception:
            workspace_map = {}
        workspace_id = resolve_workspace_filter(effective_workspace, workspace_map)
        _append_filter(parts, filter_substitutions, "workspace == @{index}", workspace_id)

    user_substitutions = _parse_substitutions(substitutions)
    if filter_query:
        if parts:
            offset_filter = _offset_filter_substitutions(filter_query, len(filter_substitutions))
            parts.append(f"({offset_filter})")
            filter_substitutions.extend(user_substitutions)
        else:
            parts.append(filter_query)
            filter_substitutions = user_substitutions

    return (" && ".join(parts) if parts else None), filter_substitutions, workspace_map


def _extract_json(resp: Any) -> Any:
    """Return a response body when it contains JSON, otherwise an empty object."""
    try:
        return resp.json()
    except (AttributeError, ValueError):
        return {}


def _extract_alarm_items(data: Any) -> List[Dict[str, Any]]:
    """Extract alarm records from current and legacy response shapes."""
    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]
    if not isinstance(data, dict):
        return []
    for key in ("alarms", "alarmInstances", "filterMatches", "instances", "items"):
        values = data.get(key)
        if isinstance(values, list):
            return [item for item in values if isinstance(item, dict)]
    return []


def _query_alarm_page(
    filter_expr: Optional[str],
    substitutions: List[Any],
    take: int,
    continuation_token: Optional[str] = None,
    include_transitions: bool = False,
    most_recent_only: bool = False,
) -> Tuple[List[Dict[str, Any]], Optional[str], Optional[int]]:
    """Query one page of alarms using the non-deprecated filter endpoint."""
    payload: Dict[str, Any] = {
        "take": take,
        "returnCount": True,
        "orderBy": "UPDATED_AT",
        "orderByDescending": True,
    }
    if filter_expr:
        payload["filter"] = filter_expr
    if substitutions:
        payload["substitutions"] = substitutions
    if continuation_token:
        payload["continuationToken"] = continuation_token
    if include_transitions:
        payload["transitionInclusionOption"] = "ALL"
    if most_recent_only:
        payload["returnMostRecentlyOccurredOnly"] = True

    resp = make_api_request(
        "POST",
        f"{_get_alarm_base_url()}/query-instances-with-filter",
        payload=payload,
    )
    data = _extract_json(resp)
    total_count = data.get("totalCount") if isinstance(data, dict) else None
    next_token = data.get("continuationToken") if isinstance(data, dict) else None
    return _extract_alarm_items(data), next_token, total_count


def _query_all_alarms(
    filter_expr: Optional[str],
    substitutions: List[Any],
    max_items: int,
    include_transitions: bool,
    most_recent_only: bool,
) -> List[Dict[str, Any]]:
    """Fetch pages up to the requested JSON result limit."""
    alarms: List[Dict[str, Any]] = []
    continuation_token: Optional[str] = None

    while len(alarms) < max_items:
        remaining = max_items - len(alarms)
        page, continuation_token, _ = _query_alarm_page(
            filter_expr,
            substitutions,
            min(_MAX_QUERY_TAKE, remaining),
            continuation_token,
            include_transitions,
            most_recent_only,
        )
        alarms.extend(page[:remaining])
        if not continuation_token or not page:
            break

    return alarms[:max_items]


def _format_timestamp(value: Any) -> str:
    """Format a timestamp for a compact table cell."""
    if not value:
        return ""
    text = str(value)
    return text.replace("T", " ", 1).replace("Z", "", 1)[:19]


def _alarm_formatter(item: Dict[str, Any], workspace_map: Dict[str, str]) -> List[str]:
    """Format an alarm for table output."""
    state = "ACTIVE" if item.get("active") else "INACTIVE"
    flags = []
    if item.get("clear"):
        flags.append("CLEAR")
    if item.get("acknowledged"):
        flags.append("ACK")
    if flags:
        state = f"{state}/{'+'.join(flags)}"

    workspace_id = item.get("workspace", "")
    workspace_name = (
        workspace_map.get(workspace_id, workspace_id) if workspace_map else workspace_id
    )

    return [
        state,
        str(item.get("currentSeverityLevel", "")),
        item.get("displayName") or item.get("alarmId", ""),
        item.get("alarmId", ""),
        _format_timestamp(item.get("occurredAt")),
        workspace_name,
        item.get("instanceId", ""),
    ]


def _get_transition_count(item: Dict[str, Any]) -> int:
    """Return the number of transitions when the response contains a list."""
    transitions = item.get("transitions")
    return len(transitions) if isinstance(transitions, list) else 0


def _display_alarm_list(
    alarms: List[Dict[str, Any]],
    format_output: str,
    workspace_map: Dict[str, str],
    total_count: Optional[int] = None,
    shown_count: Optional[int] = None,
    include_transitions: bool = False,
) -> None:
    """Render alarms in JSON or a compact operational table."""

    def formatter(item: Dict[str, Any]) -> List[str]:
        return _alarm_formatter(item, workspace_map)

    UniversalResponseHandler.handle_list_response(
        resp=FilteredResponse({"alarms": alarms}),
        data_key="alarms",
        item_name="alarm",
        format_output=format_output,
        formatter_func=formatter,
        headers=["State", "Severity", "Name", "Alarm ID", "Occurred", "Workspace", "Instance ID"],
        column_widths=[18, 8, 28, 28, 20, 20, 28],
        empty_message="No alarms found.",
        enable_pagination=False,
        page_size=len(alarms) or 1,
        total_count=total_count,
        shown_count=shown_count,
    )

    if include_transitions and format_output.lower() == "table":
        transition_count = sum(_get_transition_count(item) for item in alarms)
        if transition_count:
            click.echo(f"Transitions included: {transition_count}")


def _get_alarm_details(data: Dict[str, Any], format_output: str) -> None:
    """Render one alarm record."""
    if format_output.lower() == "json":
        click.echo(json.dumps(data, indent=2))
        return

    scalar_fields = [
        ("Instance ID", data.get("instanceId", "")),
        ("Alarm ID", data.get("alarmId", "")),
        ("Display Name", data.get("displayName", "")),
        ("State", "ACTIVE" if data.get("active") else "INACTIVE"),
        ("Clear", data.get("clear", "")),
        ("Acknowledged", data.get("acknowledged", "")),
        ("Current Severity", data.get("currentSeverityLevel", "")),
        ("Highest Severity", data.get("highestSeverityLevel", "")),
        ("Occurred", data.get("occurredAt", "")),
        ("Updated", data.get("updatedAt", "")),
        ("Workspace", data.get("workspace", "")),
        ("Channel", data.get("channel", "")),
        ("Resource Type", data.get("resourceType", "")),
        ("Description", data.get("description", "")),
        ("Keywords", ", ".join(data.get("keywords", []))),
        ("Properties", json.dumps(data.get("properties", {}), sort_keys=True)),
        ("Notes", json.dumps(data.get("notes", []), sort_keys=True)),
        ("Transitions", str(_get_transition_count(data))),
    ]
    render_table(
        headers=["FIELD", "VALUE"],
        column_widths=[20, 100],
        rows=[[label, str(value)] for label, value in scalar_fields],
        show_total=False,
    )


def _parse_properties(values: Tuple[str, ...]) -> Dict[str, str]:
    """Parse repeated key=value options."""
    properties: Dict[str, str] = {}
    for value in values:
        if "=" not in value:
            raise ValueError(f"Invalid property '{value}'. Use key=value.")
        key, property_value = value.split("=", 1)
        if not key.strip():
            raise ValueError(f"Invalid property '{value}'. The key cannot be empty.")
        properties[key.strip()] = property_value.strip()
    return properties


def _emit_action_result(
    data: Any,
    format_output: str,
    message: str,
    success_key: Optional[str] = None,
    failed_key: Optional[str] = None,
) -> None:
    """Render an action response consistently."""
    if format_output.lower() == "json":
        click.echo(json.dumps(data if data else {}, indent=2))
        return

    format_success(message)
    if isinstance(data, dict):
        if success_key and data.get(success_key):
            click.echo(f"  {success_key}: {', '.join(data[success_key])}")
        if failed_key and data.get(failed_key):
            click.echo(f"  {failed_key}: {', '.join(data[failed_key])}", err=True)
        if data.get("error"):
            error = data["error"]
            if isinstance(error, dict):
                click.echo(f"  Error: {error.get('message', error)}", err=True)
            else:
                click.echo(f"  Error: {error}", err=True)


def _validate_ids(instance_ids: Tuple[str, ...], maximum: int, action: str) -> None:
    """Validate a batch of instance IDs."""
    if not instance_ids:
        click.echo(f"No alarm instance IDs supplied for {action}.", err=True)
        sys.exit(ExitCodes.INVALID_INPUT)
    if len(instance_ids) > maximum:
        click.echo(
            f"A maximum of {maximum} alarm instance IDs can be supplied for {action}.",
            err=True,
        )
        sys.exit(ExitCodes.INVALID_INPUT)


def _confirm_alarm_operation(action: str, count: int, force: bool) -> bool:
    """Confirm an alarm operation unless explicitly skipped."""
    return confirm_bulk_operation(action, "alarm", count, force=force)


def _list_alarm_options(function: Any) -> Any:
    """Apply shared list/search options to a Click command."""
    options = [
        click.option(
            "--format",
            "-f",
            type=click.Choice(["table", "json"]),
            default="table",
            show_default=True,
            help="Output format",
        ),
        click.option(
            "--take",
            "-t",
            type=click.IntRange(min=1, max=_MAX_QUERY_TAKE),
            default=25,
            show_default=True,
            help="Maximum alarms to return (table page/snapshot size; JSON list total)",
        ),
        click.option(
            "--state",
            type=click.Choice(["active", "inactive", "all"]),
            default="active",
            show_default=True,
            help="Alarm state to include",
        ),
        click.option("--alarm-id", help="Match an exact alarm ID"),
        click.option("--display-name", help="Match display name text"),
        click.option("--channel", help="Match channel text"),
        click.option("--resource-type", help="Match an exact resource type"),
        click.option("--min-severity", type=int, help="Minimum current severity"),
        click.option("--max-severity", type=int, help="Maximum current severity"),
        click.option(
            "--workspace", "-w", help="Workspace name or ID; use 'all' for every workspace"
        ),
        click.option("--filter", "filter_query", help="Dynamic LINQ filter expression"),
        click.option(
            "--substitution",
            "substitutions",
            multiple=True,
            help="Value for --filter substitutions (repeatable; JSON is parsed when valid)",
        ),
        click.option(
            "--include-transitions",
            is_flag=True,
            help="Include all stored alarm transitions",
        ),
        click.option(
            "--most-recent-only",
            is_flag=True,
            help="Return only the most recent instance for each alarm ID",
        ),
    ]
    for option in options:
        function = option(function)
    return function


def _run_list_alarms(
    format: str,
    take: int,
    state: str,
    alarm_id: Optional[str],
    display_name: Optional[str],
    channel: Optional[str],
    resource_type: Optional[str],
    min_severity: Optional[int],
    max_severity: Optional[int],
    workspace: Optional[str],
    filter_query: Optional[str],
    substitutions: Tuple[str, ...],
    include_transitions: bool,
    most_recent_only: bool,
) -> None:
    """Execute the shared alarm list/search workflow."""
    format_output = validate_output_format(format)
    if min_severity is not None and max_severity is not None and min_severity > max_severity:
        click.echo("✗ --min-severity cannot be greater than --max-severity", err=True)
        sys.exit(ExitCodes.INVALID_INPUT)

    filter_expr, filter_substitutions, workspace_map = _build_alarm_filter(
        state,
        alarm_id,
        display_name,
        channel,
        resource_type,
        min_severity,
        max_severity,
        workspace,
        filter_query,
        substitutions,
    )

    if format_output.lower() == "json":
        alarms = _query_all_alarms(
            filter_expr,
            filter_substitutions,
            take,
            include_transitions,
            most_recent_only,
        )
        _display_alarm_list(
            alarms, format_output, workspace_map, include_transitions=include_transitions
        )
        return

    continuation_token: Optional[str] = None
    shown_count = 0
    while True:
        alarms, continuation_token, total_count = _query_alarm_page(
            filter_expr,
            filter_substitutions,
            take,
            continuation_token,
            include_transitions,
            most_recent_only,
        )
        if not alarms:
            if shown_count == 0:
                click.echo("No alarms found.")
            break

        shown_count += len(alarms)
        _display_alarm_list(
            alarms,
            format_output,
            workspace_map,
            total_count=total_count,
            shown_count=shown_count,
            include_transitions=include_transitions,
        )
        if not continuation_token:
            break
        if not questionary.confirm("Show next set of alarms?", default=True).ask():
            break


def register_alarm_commands(cli: Any) -> None:
    """Register the 'alarm' command group and its subcommands."""

    @cli.group()
    def alarm() -> None:
        """View and manage SystemLink alarms."""

    @alarm.command(name="list")
    @_list_alarm_options
    def list_alarms(
        format: str,
        take: int,
        state: str,
        alarm_id: Optional[str],
        display_name: Optional[str],
        channel: Optional[str],
        resource_type: Optional[str],
        min_severity: Optional[int],
        max_severity: Optional[int],
        workspace: Optional[str],
        filter_query: Optional[str],
        substitutions: Tuple[str, ...],
        include_transitions: bool,
        most_recent_only: bool,
    ) -> None:
        """List active alarms or search alarm history."""
        try:
            _run_list_alarms(
                format,
                take,
                state,
                alarm_id,
                display_name,
                channel,
                resource_type,
                min_severity,
                max_severity,
                workspace,
                filter_query,
                substitutions,
                include_transitions,
                most_recent_only,
            )
        except Exception as exc:  # noqa: BLE001
            handle_api_error(exc)

    @alarm.command(name="get")
    @click.argument("instance_id")
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    def get_alarm(instance_id: str, format: str) -> None:
        """View a single alarm instance by INSTANCE_ID."""
        try:
            format_output = validate_output_format(format)
            resp = make_api_request(
                "GET",
                f"{_get_alarm_base_url()}/instances/{quote(instance_id, safe='')}",
            )
            data = _extract_json(resp)
            if not isinstance(data, dict):
                raise ValueError("Alarm response was not an object")
            _get_alarm_details(data, format_output)
        except Exception as exc:  # noqa: BLE001
            handle_api_error(exc)

    @alarm.command(name="acknowledge")
    @click.argument("instance_ids", nargs=-1, required=True)
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    def acknowledge_alarms(instance_ids: Tuple[str, ...], format: str) -> None:
        """Acknowledge one or more alarm instances."""
        check_readonly_mode("acknowledge alarms")
        _validate_ids(instance_ids, _MAX_ACKNOWLEDGE_IDS, "acknowledgment")
        try:
            format_output = validate_output_format(format)
            resp = make_api_request(
                "POST",
                f"{_get_alarm_base_url()}/acknowledge-instances-by-instance-id",
                payload={"instanceIds": list(instance_ids), "forceClear": False},
            )
            data = _extract_json(resp)
            _emit_action_result(
                data,
                format_output,
                "Alarm acknowledgment completed",
                success_key="acknowledged",
                failed_key="failed",
            )
        except Exception as exc:  # noqa: BLE001
            handle_api_error(exc)

    @alarm.command(name="force-clear")
    @click.argument("instance_ids", nargs=-1, required=True)
    @click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    def force_clear_alarms(instance_ids: Tuple[str, ...], yes: bool, format: str) -> None:
        """Acknowledge and clear one or more alarm instances."""
        check_readonly_mode("force-clear alarms")
        _validate_ids(instance_ids, _MAX_ACKNOWLEDGE_IDS, "force-clear")
        if not _confirm_alarm_operation("force-clear", len(instance_ids), yes):
            return
        try:
            format_output = validate_output_format(format)
            resp = make_api_request(
                "POST",
                f"{_get_alarm_base_url()}/acknowledge-instances-by-instance-id",
                payload={"instanceIds": list(instance_ids), "forceClear": True},
            )
            data = _extract_json(resp)
            _emit_action_result(
                data,
                format_output,
                "Alarm force-clear completed",
                success_key="acknowledged",
                failed_key="failed",
            )
        except Exception as exc:  # noqa: BLE001
            handle_api_error(exc)

    @alarm.command(name="delete")
    @click.argument("instance_ids", nargs=-1, required=True)
    @click.option("--yes", "-y", is_flag=True, help="Skip confirmation prompt")
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    def delete_alarms(instance_ids: Tuple[str, ...], yes: bool, format: str) -> None:
        """Permanently delete one or more alarm instances."""
        check_readonly_mode("delete alarms")
        _validate_ids(instance_ids, _MAX_DELETE_IDS, "deletion")
        if not _confirm_alarm_operation("delete", len(instance_ids), yes):
            return
        try:
            format_output = validate_output_format(format)
            resp = make_api_request(
                "POST",
                f"{_get_alarm_base_url()}/delete-instances-by-instance-id",
                payload={"instanceIds": list(instance_ids)},
            )
            data = _extract_json(resp)
            if not data:
                data = {"deleted": list(instance_ids), "failed": []}
            _emit_action_result(
                data,
                format_output,
                "Alarm deletion completed",
                success_key="deleted",
                failed_key="failed",
            )
        except Exception as exc:  # noqa: BLE001
            handle_api_error(exc)

    @alarm.command(name="transition")
    @click.argument("alarm_id")
    @click.option(
        "--transition",
        type=click.Choice(["SET", "CLEAR"], case_sensitive=False),
        default="SET",
        show_default=True,
        help="Transition to report",
    )
    @click.option("--workspace", "-w", help="Workspace name or ID")
    @click.option("--severity", type=int, help="Severity level; CLEAR defaults to -1")
    @click.option("--value", help="Value that caused the transition")
    @click.option("--condition", help="Condition associated with the transition")
    @click.option("--short-text", help="Short condition description")
    @click.option("--detail-text", help="Detailed condition description")
    @click.option("--channel", help="Tag or resource associated with the alarm")
    @click.option("--resource-type", help="Type of resource associated with the alarm")
    @click.option("--display-name", help="Display name used when creating the alarm")
    @click.option("--description", help="Description used when creating the alarm")
    @click.option("--created-by", help="Identifier for the creating rule or application")
    @click.option("--keyword", "keywords", multiple=True, help="Alarm keyword (repeatable)")
    @click.option(
        "--property",
        "properties",
        multiple=True,
        help="Alarm property in key=value form (repeatable)",
    )
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    def transition_alarm(
        alarm_id: str,
        transition: str,
        workspace: Optional[str],
        severity: Optional[int],
        value: Optional[str],
        condition: Optional[str],
        short_text: Optional[str],
        detail_text: Optional[str],
        channel: Optional[str],
        resource_type: Optional[str],
        display_name: Optional[str],
        description: Optional[str],
        created_by: Optional[str],
        keywords: Tuple[str, ...],
        properties: Tuple[str, ...],
        format: str,
    ) -> None:
        """Create an alarm or report a SET/CLEAR transition for ALARM_ID."""
        check_readonly_mode("report an alarm transition")
        try:
            format_output = validate_output_format(format)
            effective_workspace = get_effective_workspace(workspace)
            workspace_id: Optional[str] = None
            if effective_workspace:
                try:
                    workspace_id = resolve_workspace_filter(
                        effective_workspace, get_workspace_map()
                    )
                except Exception:
                    workspace_id = effective_workspace

            transition_type = transition.upper()
            if severity is not None and severity > _MAX_SEVERITY:
                raise ValueError(f"Severity cannot be greater than {_MAX_SEVERITY}.")
            if transition_type == "CLEAR" and severity not in (None, -1):
                raise ValueError("CLEAR transitions require --severity -1.")
            if transition_type == "SET" and severity is not None and severity < 1:
                raise ValueError("SET transitions require --severity at least 1.")
            transition_data: Dict[str, Any] = {"transitionType": transition_type}
            if severity is not None:
                transition_data["severityLevel"] = severity
            elif transition_type == "CLEAR":
                transition_data["severityLevel"] = -1
            for key, value in (
                ("value", value),
                ("condition", condition),
                ("shortText", short_text),
                ("detailText", detail_text),
            ):
                if value is not None:
                    transition_data[key] = value

            payload: Dict[str, Any] = {"alarmId": alarm_id, "transition": transition_data}
            if workspace_id:
                payload["workspace"] = workspace_id
            for key, value in (
                ("channel", channel),
                ("resourceType", resource_type),
                ("displayName", display_name),
                ("description", description),
                ("createdBy", created_by),
            ):
                if value is not None:
                    payload[key] = value
            if keywords:
                payload["keywords"] = list(keywords)
            if properties:
                payload["properties"] = _parse_properties(properties)

            resp = make_api_request("POST", f"{_get_alarm_base_url()}/instances", payload=payload)
            data = _extract_json(resp)
            _emit_action_result(data, format_output, "Alarm transition recorded")
        except ValueError as exc:
            click.echo(f"✗ {exc}", err=True)
            sys.exit(ExitCodes.INVALID_INPUT)
        except Exception as exc:  # noqa: BLE001
            handle_api_error(exc)

    @alarm.command(name="monitor")
    @_list_alarm_options
    @click.option(
        "--interval",
        type=click.FloatRange(min=0.1),
        default=5.0,
        show_default=True,
        help="Seconds between refreshes",
    )
    @click.option("--once", is_flag=True, help="Render one snapshot and exit")
    @click.option("--no-clear", is_flag=True, help="Keep previous snapshots in the terminal")
    def monitor_alarms(
        format: str,
        take: int,
        state: str,
        alarm_id: Optional[str],
        display_name: Optional[str],
        channel: Optional[str],
        resource_type: Optional[str],
        min_severity: Optional[int],
        max_severity: Optional[int],
        workspace: Optional[str],
        filter_query: Optional[str],
        substitutions: Tuple[str, ...],
        include_transitions: bool,
        most_recent_only: bool,
        interval: float,
        once: bool,
        no_clear: bool,
    ) -> None:
        """Continuously refresh an alarm dashboard until Ctrl+C."""
        format_output = validate_output_format(format)
        if min_severity is not None and max_severity is not None and min_severity > max_severity:
            click.echo("✗ --min-severity cannot be greater than --max-severity", err=True)
            sys.exit(ExitCodes.INVALID_INPUT)

        try:
            filter_expr, filter_substitutions, workspace_map = _build_alarm_filter(
                state,
                alarm_id,
                display_name,
                channel,
                resource_type,
                min_severity,
                max_severity,
                workspace,
                filter_query,
                substitutions,
            )
            previous_snapshot: Optional[str] = None
            while True:
                alarms, _, _ = _query_alarm_page(
                    filter_expr,
                    filter_substitutions,
                    take,
                    include_transitions=include_transitions,
                    most_recent_only=most_recent_only,
                )
                snapshot = json.dumps(alarms, sort_keys=True, default=str)
                if snapshot != previous_snapshot:
                    if (
                        format_output.lower() == "table"
                        and previous_snapshot is not None
                        and not no_clear
                    ):
                        click.clear()
                    if format_output.lower() == "table":
                        click.echo(
                            f"Alarm monitor | {datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds')} | {len(alarms)} alarm(s)"
                        )
                    _display_alarm_list(
                        alarms,
                        format_output,
                        workspace_map,
                        include_transitions=include_transitions,
                    )
                    previous_snapshot = snapshot

                if once:
                    break
                time.sleep(interval)
        except KeyboardInterrupt:
            click.echo("\nAlarm monitor stopped.")
        except Exception as exc:  # noqa: BLE001
            handle_api_error(exc)
