"""CLI commands for managing SystemLink Routines.

Supports two API versions:
  v1 (niroutine/v1): Notebook-execution routines with SCHEDULED or TRIGGERED types.
  v2 (niroutine/v2): General event-action routines supporting any event/action types.
"""

import json
import sys
from typing import Any, Dict, List, Optional

import click

from .utils import (
    ExitCodes,
    format_success,
    get_base_url,
    get_workspace_map,
    handle_api_error,
    make_api_request,
)
from .workspace_utils import (
    filter_by_workspace,
    get_workspace_display_name,
    resolve_workspace_filter,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _routine_base_url(api_version: str) -> str:
    """Return the base URL for routines based on the API version.

    Args:
        api_version: Either 'v1' or 'v2'.

    Returns:
        The base URL string for the routines endpoint.
    """
    return f"{get_base_url()}/niroutine/{api_version}/routines"


def _parse_json_option(value: Optional[str], field_name: str) -> Any:
    """Parse a JSON string option, exiting with an error on invalid JSON.

    Args:
        value: JSON string value, or None.
        field_name: Name of the CLI option, used in error messages.

    Returns:
        Parsed Python object, or None if value is None.
    """
    if value is None:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError as exc:
        click.echo(f"✗ Invalid JSON for --{field_name}: {exc}", err=True)
        sys.exit(ExitCodes.INVALID_INPUT)


def _make_v1_formatter(
    workspace_map: Dict[str, str],
) -> Any:
    """Create a v1 routine table row formatter with workspace name resolution.

    Args:
        workspace_map: Mapping of workspace ID to display name.

    Returns:
        Formatter function that accepts a routine dict and returns a row list.
    """

    def formatter(routine: Dict[str, Any]) -> List[str]:
        enabled = "✓" if routine.get("enabled", False) else "✗"
        ws_name = get_workspace_display_name(routine.get("workspace", ""), workspace_map)
        return [
            routine.get("name", ""),
            routine.get("id", ""),
            routine.get("type", ""),
            enabled,
            ws_name,
        ]

    return formatter


def _make_v2_formatter(
    workspace_map: Dict[str, str],
) -> Any:
    """Create a v2 routine table row formatter with workspace name resolution.

    Args:
        workspace_map: Mapping of workspace ID to display name.

    Returns:
        Formatter function that accepts a routine dict and returns a row list.
    """

    def formatter(routine: Dict[str, Any]) -> List[str]:
        enabled = "✓" if routine.get("enabled", False) else "✗"
        event_type = (routine.get("event") or {}).get("type", "")
        ws_name = get_workspace_display_name(routine.get("workspace", ""), workspace_map)
        return [
            routine.get("name", ""),
            routine.get("id", ""),
            event_type,
            enabled,
            ws_name,
        ]

    return formatter


# ---------------------------------------------------------------------------
# Command registration
# ---------------------------------------------------------------------------


def register_routine_commands(cli: Any) -> None:
    """Register the 'routine' command group and its subcommands."""

    @cli.group()
    def routine() -> None:
        """Manage SystemLink routines (v1: notebook scheduling, v2: event-action)."""
        pass

    # ------------------------------------------------------------------
    # list
    # ------------------------------------------------------------------

    @routine.command(name="list")
    @click.option(
        "--api-version",
        type=click.Choice(["v1", "v2"]),
        default="v2",
        show_default=True,
        help="API version to use (v1: notebook routines, v2: event-action routines)",
    )
    @click.option(
        "--format",
        "-f",
        "format_output",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    @click.option(
        "--take",
        "-t",
        type=int,
        default=25,
        show_default=True,
        help="Maximum number of routines to return",
    )
    @click.option(
        "--enabled",
        "enabled_filter",
        flag_value="enabled",
        default=None,
        help="Show only enabled routines",
    )
    @click.option(
        "--disabled",
        "enabled_filter",
        flag_value="disabled",
        help="Show only disabled routines",
    )
    @click.option(
        "--workspace",
        "-w",
        "workspace_filter",
        type=str,
        default=None,
        help="Filter by workspace name or ID",
    )
    @click.option(
        "--type",
        "routine_type",
        type=click.Choice(["TRIGGERED", "SCHEDULED"]),
        default=None,
        help="Filter by routine type (v1 only)",
    )
    @click.option(
        "--event-type",
        "event_type",
        type=str,
        default=None,
        help="Filter by event type (v2 only)",
    )
    @click.option(
        "--filter",
        "name_filter",
        type=str,
        default=None,
        help="Filter by routine name (case-insensitive substring match)",
    )
    def list_routines(
        api_version: str,
        format_output: str,
        take: int,
        enabled_filter: Optional[str],
        routine_type: Optional[str],
        event_type: Optional[str],
        name_filter: Optional[str],
        workspace_filter: Optional[str],
    ) -> None:
        """List routines with optional filtering.

        By default all routines (enabled and disabled) are returned. Use
        --enabled or --disabled to narrow results. The --filter option performs
        case-insensitive substring matching on routine names. The --workspace
        option accepts a workspace name or ID. The --take option controls items
        per page in table mode or the maximum items returned in JSON mode.
        """
        try:
            url = _routine_base_url(api_version)
            params: List[str] = []

            if enabled_filter == "enabled":
                params.append("Enabled=true")
            elif enabled_filter == "disabled":
                params.append("Enabled=false")

            if api_version == "v1" and routine_type:
                params.append(f"Type={routine_type}")

            if api_version == "v2" and event_type:
                params.append(f"EventType={event_type}")

            if params:
                url = url + "?" + "&".join(params)

            resp = make_api_request("GET", url, payload=None)
            data = resp.json()

            routines: List[Dict[str, Any]] = data.get("routines", [])

            # Resolve workspace map once for both filtering and display
            try:
                workspace_map: Dict[str, str] = get_workspace_map()
            except Exception:
                workspace_map = {}

            # Client-side workspace filter (APIs don't support it as a query param)
            if workspace_filter:
                resolved_ws = resolve_workspace_filter(workspace_filter, workspace_map)
                routines = filter_by_workspace(routines, resolved_ws, workspace_map)

            # Client-side name filter (APIs don't support name filtering)
            if name_filter:
                lower_filter = name_filter.lower()
                routines = [r for r in routines if lower_filter in r.get("name", "").lower()]

            if format_output == "json":
                # Apply take limit then output all at once without pagination
                if take > 0:
                    routines = routines[:take]
                click.echo(json.dumps(routines, indent=2))
                return

            if not routines:
                click.echo("No routines found.")
                return

            from .table_utils import output_formatted_list

            if api_version == "v1":
                headers = ["Name", "ID", "Type", "Enabled", "Workspace"]
                widths = [30, 36, 12, 8, 30]
                formatter = _make_v1_formatter(workspace_map)
            else:
                headers = ["Name", "ID", "Event Type", "Enabled", "Workspace"]
                widths = [30, 36, 15, 8, 30]
                formatter = _make_v2_formatter(workspace_map)

            # Interactive pagination: show `take` items per page
            total = len(routines)
            offset = 0

            while True:
                page = routines[offset : offset + take]
                output_formatted_list(
                    page,
                    format_output,
                    headers,
                    widths,
                    formatter,
                    "",
                    "routine(s)",
                )

                offset += len(page)

                if offset >= total:
                    break

                click.echo(f"\nShowing {offset} of {total} routine(s).")

                try:
                    is_tty = sys.stdout.isatty() and sys.stdin.isatty()
                except (OSError, AttributeError):
                    is_tty = False

                if not is_tty:
                    break

                if not click.confirm("Show next page?", default=True):
                    break

        except Exception as exc:
            handle_api_error(exc)

    # ------------------------------------------------------------------
    # get
    # ------------------------------------------------------------------

    @routine.command(name="get")
    @click.argument("routine_id")
    @click.option(
        "--api-version",
        type=click.Choice(["v1", "v2"]),
        default="v2",
        show_default=True,
        help="API version to use",
    )
    @click.option(
        "--format",
        "-f",
        "format_output",
        type=click.Choice(["table", "json"]),
        default="json",
        show_default=True,
        help="Output format",
    )
    def get_routine(routine_id: str, api_version: str, format_output: str) -> None:
        """Get a routine by ID.

        ROUTINE_ID is the unique identifier of the routine to retrieve.
        """
        try:
            url = f"{_routine_base_url(api_version)}/{routine_id}"
            resp = make_api_request("GET", url, payload=None)
            routine = resp.json()

            if format_output == "json":
                click.echo(json.dumps(routine, indent=2))
                return

            from .table_utils import output_formatted_list

            # Only reached for table output — the json branch returned early above.
            # Fetch workspace_map here so it is never called for json requests.
            try:
                workspace_map: Dict[str, str] = get_workspace_map()
            except Exception:
                click.echo(
                    "✗ Warning: Unable to load workspace mapping; "
                    "workspace names will not be shown.",
                    err=True,
                )
                workspace_map = {}

            if api_version == "v1":
                headers = ["Name", "ID", "Type", "Enabled", "Workspace"]
                widths = [30, 36, 12, 8, 30]
                formatter = _make_v1_formatter(workspace_map)
            else:
                headers = ["Name", "ID", "Event Type", "Enabled", "Workspace"]
                widths = [30, 36, 15, 8, 30]
                formatter = _make_v2_formatter(workspace_map)

            output_formatted_list(
                [routine],
                format_output,
                headers,
                widths,
                formatter,
                "",
                "routine(s)",
            )

        except Exception as exc:
            handle_api_error(exc)

    # ------------------------------------------------------------------
    # create
    # ------------------------------------------------------------------

    @routine.command(name="create")
    @click.option(
        "--api-version",
        type=click.Choice(["v1", "v2"]),
        default="v2",
        show_default=True,
        help="API version to use",
    )
    @click.option("--name", "-n", type=str, required=True, help="Name of the routine")
    @click.option("--description", "-d", type=str, default=None, help="Description of the routine")
    @click.option("--workspace", "-w", type=str, default=None, help="Workspace ID")
    @click.option(
        "--enabled/--disabled",
        "enabled",
        default=False,
        show_default=True,
        help="Enable or disable the routine upon creation",
    )
    # v1-specific options
    @click.option(
        "--type",
        "routine_type",
        type=click.Choice(["TRIGGERED", "SCHEDULED"]),
        default=None,
        help="Routine type (v1 only, required for v1)",
    )
    @click.option(
        "--notebook-id",
        type=str,
        default=None,
        help="Notebook ID to execute (v1 only, required for v1)",
    )
    @click.option(
        "--trigger",
        "trigger_json",
        type=str,
        default=None,
        help=(
            "Trigger definition as JSON string (v1 TRIGGERED type). "
            'E.g. \'{"source":"FILES","events":["CREATED"],"filter":"extension=\\".csv\\""}\''
        ),
    )
    @click.option(
        "--schedule",
        "schedule_json",
        type=str,
        default=None,
        help=(
            "Schedule definition as JSON string (v1 SCHEDULED type). "
            'E.g. \'{"startTime":"2026-01-01T00:00:00Z","repeat":"HOUR"}\''
        ),
    )
    # v2-specific options
    @click.option(
        "--event",
        "event_json",
        type=str,
        default=None,
        help=(
            "Event definition as JSON string (v2 only, required for v2). "
            'E.g. \'{"type":"tag","triggers":[{"name":"cond","configuration":{}}]}\''
        ),
    )
    @click.option(
        "--actions",
        "actions_json",
        type=str,
        default=None,
        help=(
            "Actions as a JSON array string (v2 only, required for v2). "
            'E.g. \'[{"type":"alarm","configuration":{"severity":1}}]\''
        ),
    )
    def create_routine(
        api_version: str,
        name: str,
        description: Optional[str],
        workspace: Optional[str],
        enabled: bool,
        routine_type: Optional[str],
        notebook_id: Optional[str],
        trigger_json: Optional[str],
        schedule_json: Optional[str],
        event_json: Optional[str],
        actions_json: Optional[str],
    ) -> None:
        """Create a new routine.

        For v1 (notebook routines): --type and --notebook-id are required.
        For v2 (event-action routines): --event and --actions are required.
        """
        try:
            payload: Dict[str, Any] = {"name": name, "enabled": enabled}

            if description is not None:
                payload["description"] = description
            if workspace is not None:
                payload["workspace"] = workspace

            if api_version == "v1":
                if not routine_type:
                    click.echo("✗ --type is required for --api-version v1", err=True)
                    sys.exit(ExitCodes.INVALID_INPUT)
                if not notebook_id:
                    click.echo("✗ --notebook-id is required for --api-version v1", err=True)
                    sys.exit(ExitCodes.INVALID_INPUT)

                payload["type"] = routine_type
                payload["execution"] = {
                    "type": "NOTEBOOK",
                    "definition": {"notebookId": notebook_id},
                }

                if routine_type == "TRIGGERED":
                    if not trigger_json:
                        click.echo("✗ --trigger is required for --type TRIGGERED", err=True)
                        sys.exit(ExitCodes.INVALID_INPUT)
                    payload["trigger"] = _parse_json_option(trigger_json, "trigger")
                elif routine_type == "SCHEDULED":
                    if not schedule_json:
                        click.echo("✗ --schedule is required for --type SCHEDULED", err=True)
                        sys.exit(ExitCodes.INVALID_INPUT)
                    payload["schedule"] = _parse_json_option(schedule_json, "schedule")

            else:  # v2
                if not event_json:
                    click.echo("✗ --event is required for --api-version v2", err=True)
                    sys.exit(ExitCodes.INVALID_INPUT)
                if not actions_json:
                    click.echo("✗ --actions is required for --api-version v2", err=True)
                    sys.exit(ExitCodes.INVALID_INPUT)

                payload["event"] = _parse_json_option(event_json, "event")
                payload["actions"] = _parse_json_option(actions_json, "actions")

            url = _routine_base_url(api_version)
            resp = make_api_request("POST", url, payload=payload)
            result = resp.json()

            routine_id = result.get("id", "")
            format_success("Routine created", {"id": routine_id, "name": name})

        except SystemExit:
            raise
        except Exception as exc:
            handle_api_error(exc)

    # ------------------------------------------------------------------
    # update
    # ------------------------------------------------------------------

    @routine.command(name="update")
    @click.argument("routine_id")
    @click.option(
        "--api-version",
        type=click.Choice(["v1", "v2"]),
        default="v2",
        show_default=True,
        help="API version to use",
    )
    @click.option("--name", "-n", type=str, default=None, help="New name for the routine")
    @click.option("--description", "-d", type=str, default=None, help="New description")
    @click.option("--workspace", "-w", type=str, default=None, help="New workspace ID")
    @click.option(
        "--enable/--disable",
        "enabled",
        default=None,
        help="Enable or disable the routine",
    )
    # v1-specific options
    @click.option(
        "--notebook-id",
        type=str,
        default=None,
        help="New notebook ID to execute (v1 only)",
    )
    @click.option(
        "--trigger",
        "trigger_json",
        type=str,
        default=None,
        help="Updated trigger definition as JSON string (v1 only)",
    )
    @click.option(
        "--schedule",
        "schedule_json",
        type=str,
        default=None,
        help="Updated schedule definition as JSON string (v1 only)",
    )
    # v2-specific options
    @click.option(
        "--event",
        "event_json",
        type=str,
        default=None,
        help="Updated event definition as JSON string (v2 only)",
    )
    @click.option(
        "--actions",
        "actions_json",
        type=str,
        default=None,
        help="Updated actions as a JSON array string (v2 only)",
    )
    def update_routine(
        routine_id: str,
        api_version: str,
        name: Optional[str],
        description: Optional[str],
        workspace: Optional[str],
        enabled: Optional[bool],
        notebook_id: Optional[str],
        trigger_json: Optional[str],
        schedule_json: Optional[str],
        event_json: Optional[str],
        actions_json: Optional[str],
    ) -> None:
        """Update a routine by ID.

        ROUTINE_ID is the unique identifier of the routine to update.
        Only the provided fields will be updated.
        """
        try:
            payload: Dict[str, Any] = {}

            if name is not None:
                payload["name"] = name
            if description is not None:
                payload["description"] = description
            if workspace is not None:
                payload["workspace"] = workspace
            if enabled is not None:
                payload["enabled"] = enabled

            if api_version == "v1":
                if notebook_id is not None:
                    payload["execution"] = {
                        "type": "NOTEBOOK",
                        "definition": {"notebookId": notebook_id},
                    }
                if trigger_json is not None:
                    payload["trigger"] = _parse_json_option(trigger_json, "trigger")
                if schedule_json is not None:
                    payload["schedule"] = _parse_json_option(schedule_json, "schedule")
            else:  # v2
                if event_json is not None:
                    payload["event"] = _parse_json_option(event_json, "event")
                if actions_json is not None:
                    payload["actions"] = _parse_json_option(actions_json, "actions")

            if not payload:
                click.echo("✗ No update fields provided. Specify at least one option.", err=True)
                sys.exit(ExitCodes.INVALID_INPUT)

            url = f"{_routine_base_url(api_version)}/{routine_id}"
            make_api_request("PATCH", url, payload=payload)

            format_success("Routine updated", {"id": routine_id})

        except SystemExit:
            raise
        except Exception as exc:
            handle_api_error(exc)

    # ------------------------------------------------------------------
    # enable
    # ------------------------------------------------------------------

    @routine.command(name="enable")
    @click.argument("routine_id")
    @click.option(
        "--api-version",
        type=click.Choice(["v1", "v2"]),
        default="v2",
        show_default=True,
        help="API version to use",
    )
    def enable_routine(routine_id: str, api_version: str) -> None:
        """Enable a routine by ID.

        ROUTINE_ID is the unique identifier of the routine to enable.
        """
        try:
            url = f"{_routine_base_url(api_version)}/{routine_id}"
            make_api_request("PATCH", url, payload={"enabled": True})
            format_success("Routine enabled", {"id": routine_id})
        except Exception as exc:
            handle_api_error(exc)

    # ------------------------------------------------------------------
    # disable
    # ------------------------------------------------------------------

    @routine.command(name="disable")
    @click.argument("routine_id")
    @click.option(
        "--api-version",
        type=click.Choice(["v1", "v2"]),
        default="v2",
        show_default=True,
        help="API version to use",
    )
    def disable_routine(routine_id: str, api_version: str) -> None:
        """Disable a routine by ID.

        ROUTINE_ID is the unique identifier of the routine to disable.
        """
        try:
            url = f"{_routine_base_url(api_version)}/{routine_id}"
            make_api_request("PATCH", url, payload={"enabled": False})
            format_success("Routine disabled", {"id": routine_id})
        except Exception as exc:
            handle_api_error(exc)

    # ------------------------------------------------------------------
    # delete
    # ------------------------------------------------------------------

    @routine.command(name="delete")
    @click.argument("routine_id")
    @click.option(
        "--api-version",
        type=click.Choice(["v1", "v2"]),
        default="v2",
        show_default=True,
        help="API version to use",
    )
    @click.option(
        "--yes",
        "-y",
        is_flag=True,
        default=False,
        help="Skip confirmation prompt",
    )
    def delete_routine(routine_id: str, api_version: str, yes: bool) -> None:
        """Delete a routine by ID.

        ROUTINE_ID is the unique identifier of the routine to delete.
        """
        if not yes:
            click.confirm(f"Are you sure you want to delete routine '{routine_id}'?", abort=True)

        try:
            url = f"{_routine_base_url(api_version)}/{routine_id}"
            make_api_request("DELETE", url, payload=None)
            format_success("Routine deleted", {"id": routine_id})
        except Exception as exc:
            handle_api_error(exc)
