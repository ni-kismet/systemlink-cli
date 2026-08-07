"""CLI commands for managing SystemLink tags.

Provides CLI commands for creating, reading, updating, deleting, and managing
tag values. All tag operations are scoped to workspaces with proper error handling.
"""

import json
import math
import shutil
import sys
import urllib.parse
from typing import Any, Dict, List, Optional, Tuple

import click
import questionary

from .cli_utils import validate_output_format
from .universal_handlers import FilteredResponse, UniversalResponseHandler
from .utils import (
    ExitCodes,
    format_success,
    get_base_url,
    handle_api_error,
    make_api_request,
)
from .workspace_utils import resolve_workspace_id

_TAG_HISTORY_GRAPH_HEIGHT = 6


def _tag_formatter(item: Dict[str, Any]) -> List[str]:
    """Format a tag for table output.

    Args:
        item: Tag dictionary

    Returns:
        List of formatted column values
    """
    # item might be a TagWithValue object where tag props are in 'tag' field
    tag_data = item.get("tag", item)

    path = tag_data.get("path", "")
    tag_type = tag_data.get("type", "")
    last_updated = tag_data.get("lastUpdated", "")

    # Get current value
    current = item.get("current", {})
    if current and current.get("value"):
        value_obj = current.get("value", {})
        value = str(value_obj.get("value", "N/A"))
    else:
        value = "N/A"

    return [path, tag_type, value, last_updated]


def _tag_history_formatter(item: Dict[str, Any]) -> List[str]:
    """Format one historical tag value for table output."""
    value_data = item.get("value", {})
    if isinstance(value_data, dict):
        value = value_data.get("value", "N/A")
        tag_type = value_data.get("type", item.get("type", "N/A"))
    else:
        value = value_data if value_data is not None else "N/A"
        tag_type = item.get("type", "N/A")

    return [
        str(item.get("timestamp", "N/A")),
        str(value),
        str(tag_type),
    ]


def _tag_history_numeric_value(item: Dict[str, Any]) -> Optional[float]:
    """Return a finite numeric history value, if one is available."""
    value_data = item.get("value")
    value = value_data.get("value") if isinstance(value_data, dict) else value_data
    if value is None or isinstance(value, bool):
        return None

    try:
        numeric_value = float(value)
    except (TypeError, ValueError):
        return None

    return numeric_value if math.isfinite(numeric_value) else None


def _downsample_history(values: List[float], width: int) -> List[float]:
    """Downsample values to fit the available graph width."""
    if len(values) <= width:
        return values
    if width <= 1:
        return [values[-1]]

    return [values[round(index * (len(values) - 1) / (width - 1))] for index in range(width)]


def _format_graph_value(value: float) -> str:
    """Format a graph statistic without unnecessary trailing zeroes."""
    return f"{value:.6g}"


def _render_tag_history_graph(
    tag_path: str, workspace_label: str, history: List[Dict[str, Any]]
) -> None:
    """Render numeric tag history as a terminal sparkline."""
    if not history:
        click.echo(f"No tag history found in workspace '{workspace_label}'")
        return

    chronological_history = list(reversed(history))
    numeric_values = [_tag_history_numeric_value(item) for item in chronological_history]
    if any(value is None for value in numeric_values):
        click.echo(
            f"Cannot graph non-numeric tag history for '{tag_path}' "
            f"in workspace '{workspace_label}'."
        )
        click.echo("Run without --graph to view the history table.")
        return

    values = [value for value in numeric_values if value is not None]
    minimum = min(values)
    maximum = max(values)
    latest = values[-1]
    terminal_width = max(shutil.get_terminal_size().columns, 1)
    graph_width = max(1, min(len(values), terminal_width - 16))
    graph_values = _downsample_history(values, graph_width)
    value_range = maximum - minimum
    point_rows = [
        (
            _TAG_HISTORY_GRAPH_HEIGHT // 2
            if value_range == 0
            else round((maximum - value) / value_range * (_TAG_HISTORY_GRAPH_HEIGHT - 1))
        )
        for value in graph_values
    ]
    graph_rows = [[" "] * len(graph_values) for _ in range(_TAG_HISTORY_GRAPH_HEIGHT)]
    for index, point_row in enumerate(point_rows):
        graph_rows[point_row][index] = "●"
        if index == 0:
            continue

        previous_row = point_rows[index - 1]
        if previous_row == point_row:
            continue

        step = 1 if point_row > previous_row else -1
        for row in range(previous_row + step, point_row, step):
            graph_rows[row][index] = "│"

    first_timestamp = chronological_history[0].get("timestamp", "N/A")
    last_timestamp = chronological_history[-1].get("timestamp", "N/A")
    click.echo(f"Tag history graph for '{tag_path}'")
    click.echo(f"Workspace: {workspace_label}")
    click.echo(f"Range: {first_timestamp} to {last_timestamp}")
    click.echo(
        f"Min: {_format_graph_value(minimum)}  "
        f"Max: {_format_graph_value(maximum)}  "
        f"Latest: {_format_graph_value(latest)}"
    )
    for row, graph_row in enumerate(graph_rows):
        if value_range == 0:
            row_label = (
                _format_graph_value(maximum) if row == _TAG_HISTORY_GRAPH_HEIGHT // 2 else ""
            )
        else:
            row_value = maximum - value_range * row / (_TAG_HISTORY_GRAPH_HEIGHT - 1)
            row_label = _format_graph_value(row_value)
        click.echo(f"  {row_label:>8} ┤{''.join(graph_row)}")
    click.echo(f"  {_format_graph_value(minimum):>8} └{'─' * len(graph_values)}")
    click.echo(f"  oldest{' ' * max(len(graph_values) - 12, 1)}newest")


def _calculate_column_widths() -> List[int]:
    """Calculate dynamic column widths based on terminal size.

    Returns:
        List of column widths: [path_width, type_width, value_width, last_updated_width]
    """
    # Get terminal width, default to 120 if detection fails
    try:
        terminal_width = shutil.get_terminal_size().columns
    except Exception:
        terminal_width = 120

    # Fixed widths for non-path columns
    type_width = 12
    value_width = 30
    last_updated_width = 20

    # Account for column separators and cell padding for 4 columns.
    # Using 14 to account for rendering overhead and terminal variations.
    border_overhead = 14

    # Calculate remaining space for path
    fixed_columns = type_width + value_width + last_updated_width
    path_width = terminal_width - fixed_columns - border_overhead

    # Ensure minimum path width of 30, maximum of 100
    path_width = max(30, min(100, path_width))

    return [path_width, type_width, value_width, last_updated_width]


def _escape_query_value(value: str) -> str:
    """Escape double quotes in query filter values.

    Args:
        value: Raw filter value

    Returns:
        Escaped value safe for use in query strings
    """
    return value.replace('"', '\\"')


def _parse_keywords(keywords: Optional[str]) -> List[str]:
    """Parse comma-separated keywords string into list.

    Args:
        keywords: Comma-separated keywords string

    Returns:
        List of trimmed keyword strings
    """
    if not keywords:
        return []
    return [k.strip() for k in keywords.split(",") if k.strip()]


def _parse_properties(properties: tuple) -> Dict[str, str]:
    """Parse properties tuple into dictionary.

    Args:
        properties: Tuple of key=value strings

    Returns:
        Dictionary of property key-value pairs

    Raises:
        ValueError: If property format is invalid
    """
    properties_dict: Dict[str, str] = {}
    for prop in properties:
        if "=" not in prop:
            raise ValueError(f"Invalid property format: {prop}. Use key=value")
        key, val = prop.split("=", 1)
        properties_dict[key.strip()] = val.strip()
    return properties_dict


def _detect_value_type(value_str: str) -> Tuple[Any, str]:
    """Detect the type of a value from its string representation.

    Args:
        value_str: String representation of the value

    Returns:
        Tuple of (converted_value, type_string) where type_string is
        'BOOLEAN', 'INT', 'DOUBLE', or 'STRING'
    """
    # Check for boolean
    if value_str.lower() in ("true", "false"):
        is_true = value_str.lower() == "true"
        return is_true, "BOOLEAN"

    # Check for integer (excluding scientific notation)
    if "." not in value_str and "e" not in value_str.lower():
        try:
            int_val = int(value_str)
            return int_val, "INT"
        except ValueError:
            pass

    # Check for double/float
    try:
        float_val = float(value_str)
        return float_val, "DOUBLE"
    except ValueError:
        pass

    # Default to string
    return value_str, "STRING"


def _get_tag_history(tag_path: str, workspace_id: Optional[str], take: int) -> List[Dict[str, Any]]:
    """Fetch historical values for a tag.

    Args:
        tag_path: Tag path.
        workspace_id: Optional workspace ID.
        take: Maximum number of history entries to return.

    Returns:
        Historical tag value dictionaries, most recent first.
    """
    query_payload: Dict[str, Any] = {
        "path": tag_path,
        "startTime": "0001-01-01T00:00:00Z",
        "endTime": "9999-12-31T23:59:59Z",
        "take": take,
        "sortOrder": "DESCENDING",
    }
    if workspace_id:
        query_payload["workspace"] = workspace_id

    url = f"{get_base_url()}/nitaghistorian/v2/tags/query-history"
    resp = make_api_request("POST", url, payload=query_payload)
    data = resp.json()

    if isinstance(data, list):
        return [item for item in data if isinstance(item, dict)]

    if not isinstance(data, dict):
        return []

    value_type = data.get("type")

    def normalize_entries(entries: Any) -> List[Dict[str, Any]]:
        if not isinstance(entries, list):
            return []
        normalized: List[Dict[str, Any]] = []
        for item in entries:
            if not isinstance(item, dict):
                continue
            if isinstance(value_type, str) and "type" not in item:
                item = {**item, "type": value_type}
            normalized.append(item)
        return normalized

    for key in ("values", "history", "tagsWithAggregates", "data"):
        entries = data.get(key)
        if isinstance(entries, list):
            return normalize_entries(entries)

    return []


def register_tag_commands(cli: Any) -> None:
    """Register the 'tag' command group and its subcommands."""

    @cli.group()
    def tag() -> None:
        """Manage SystemLink tags."""
        pass

    @tag.command(name="list")
    @click.option(
        "--workspace",
        "-w",
        type=str,
        default=None,
        help="Workspace ID or name (defaults to default workspace)",
    )
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    @click.option(
        "--filter",
        type=str,
        default=None,
        help="Filter by tag path substring (e.g., 'temperature')",
    )
    @click.option(
        "--keywords",
        type=str,
        default=None,
        help="Comma-separated keywords to filter by",
    )
    @click.option(
        "--take",
        "-t",
        type=int,
        default=None,
        help="Limit number of results (table: 25, json: 1000)",
    )
    def list_tags(
        workspace: Optional[str],
        format: str,
        filter: Optional[str],
        keywords: Optional[str],
        take: Optional[int],
    ) -> None:
        """List tags in a workspace with optional filtering."""
        validate_output_format(format)

        try:
            ws_id = resolve_workspace_id(workspace)

            # Build filter string
            filter_parts = []

            # Only add workspace filter if workspace is provided
            if ws_id:
                filter_parts.append(f'workspace = "{ws_id}"')

            if filter:
                escaped_filter = _escape_query_value(filter)
                filter_parts.append(f'path = "*{escaped_filter}*"')

            if keywords:
                for k in keywords.split(","):
                    k_clean = k.strip()
                    if k_clean:
                        escaped_keyword = _escape_query_value(k_clean)
                        filter_parts.append(f'keywords.Contains("{escaped_keyword}")')

            query_filter = " && ".join(filter_parts)

            # Set defaults based on format
            if take is None:
                take = 25 if format == "table" else 1000

            # Build query request
            query_params: Dict[str, Any] = {
                "filter": query_filter,
                "take": take,
                "orderBy": "TIMESTAMP",
                "descending": True,
            }

            url = f"{get_base_url()}/nitag/v2/query-tags-with-values"
            resp = make_api_request("POST", url, payload=query_params)
            data = resp.json()

            tags = data.get("tagsWithValues", [])
            total_count = data.get("totalCount", len(tags))
            continuation_token = data.get("continuationToken")

            # For table format with continuation, show interactive pagination
            if format == "table" and continuation_token:
                from .table_utils import output_formatted_list

                cumulative_count = 0
                column_widths = _calculate_column_widths()

                while True:
                    # Display current page
                    output_formatted_list(
                        items=tags,
                        output_format="table",
                        headers=["Path", "Type", "Value", "Last Updated"],
                        row_formatter_func=_tag_formatter,
                        column_widths=column_widths,
                    )

                    # Update cumulative count and show pagination info
                    cumulative_count += len(tags)
                    click.echo(f"\nShowing {cumulative_count} of {total_count} tags")

                    # Check if there are more results
                    if not continuation_token:
                        break

                    # Ask if user wants more
                    if questionary.confirm(f"Show next {take} results?", default=True).ask():
                        query_params["continuationToken"] = continuation_token
                        resp = make_api_request("POST", url, payload=query_params)
                        data = resp.json()
                        tags = data.get("tagsWithValues", [])
                        continuation_token = data.get("continuationToken")

                        if not tags:
                            click.echo("No more results.")
                            break
                    else:
                        break
            else:
                # No continuation or JSON format - use standard handler
                column_widths = _calculate_column_widths()
                combined_resp = FilteredResponse({"tagsWithValues": tags})
                UniversalResponseHandler.handle_list_response(
                    resp=combined_resp,
                    data_key="tagsWithValues",
                    item_name="tag",
                    format_output=format,
                    formatter_func=_tag_formatter,
                    headers=["Path", "Type", "Value", "Last Updated"],
                    column_widths=column_widths,
                    enable_pagination=False,
                    page_size=25,
                )

                if format == "table" and total_count > len(tags):
                    click.echo(f"\nShowing {len(tags)} of {total_count} tags")

        except Exception as exc:
            handle_api_error(exc)

    @tag.command(name="history")
    @click.argument("tag_path")
    @click.option(
        "--workspace",
        "-w",
        type=str,
        default=None,
        help="Workspace ID or name (defaults to default workspace)",
    )
    @click.option(
        "--take",
        "-t",
        type=click.IntRange(min=1),
        default=100,
        show_default=True,
        help="Maximum number of historical values to return",
    )
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    @click.option(
        "--graph",
        is_flag=True,
        help="Render numeric history as a terminal sparkline (table format only)",
    )
    def tag_history(
        tag_path: str,
        workspace: Optional[str],
        take: int,
        format: str,
        graph: bool,
    ) -> None:
        """Show historical values for a tag.

        TAG_PATH is the path identifier of the tag.
        """
        validate_output_format(format)
        if graph and format == "json":
            click.echo("✗ --graph cannot be used with --format json", err=True)
            sys.exit(ExitCodes.INVALID_INPUT)

        try:
            ws_id = resolve_workspace_id(workspace)
            history = _get_tag_history(tag_path, ws_id, take)
            workspace_label = ws_id or workspace or "default workspace"

            if graph:
                _render_tag_history_graph(tag_path, workspace_label, history)
                return

            history_resp = FilteredResponse({"values": history})

            UniversalResponseHandler.handle_list_response(
                resp=history_resp,
                data_key="values",
                item_name="tag history entry",
                format_output=format,
                formatter_func=_tag_history_formatter,
                headers=["Timestamp", "Value", "Type"],
                column_widths=[28, 30, 12],
                empty_message=f"No tag history found in workspace '{workspace_label}'",
                enable_pagination=False,
                page_size=take,
            )
        except Exception as exc:
            handle_api_error(exc)

    @tag.command(name="get")
    @click.argument("tag_path")
    @click.option(
        "--workspace",
        "-w",
        type=str,
        default=None,
        help="Workspace ID or name (defaults to default workspace)",
    )
    @click.option(
        "--include-aggregates",
        is_flag=True,
        help="Include min/max/avg/count aggregates",
    )
    def get_tag(tag_path: str, workspace: Optional[str], include_aggregates: bool) -> None:
        """View tag metadata and current value.

        TAG_PATH is the path identifier of the tag (e.g., 'system.temperature').
        """
        try:
            ws_id = resolve_workspace_id(workspace)
            encoded_path = urllib.parse.quote(tag_path, safe="")
            ws_path = f"{ws_id}/" if ws_id else ""

            # Get tag metadata
            url = f"{get_base_url()}/nitag/v2/tags/{ws_path}{encoded_path}"
            tag_resp = make_api_request("GET", url, payload=None)
            tag_data = tag_resp.json()

            # Get tag value with aggregates
            value_url = f"{get_base_url()}/nitag/v2/tags/{ws_path}{encoded_path}/values"
            value_resp = make_api_request("GET", value_url, payload=None)

            # Handle 204 No Content (tag has no value yet)
            value_data = {} if value_resp.status_code == 204 else value_resp.json()

            click.echo(f"\n✓ Tag: {tag_path}")
            click.echo("-" * 60)
            click.echo(f"  Type:              {tag_data.get('type', 'Unknown')}")
            click.echo(f"  Workspace:         {ws_id}")

            keywords = tag_data.get("keywords", [])
            if keywords:
                click.echo(f"  Keywords:          {', '.join(keywords)}")

            properties = tag_data.get("properties", {})
            if properties:
                click.echo(f"  Properties:")
                for key, val in properties.items():
                    click.echo(f"    {key}: {val}")

            click.echo(f"  Last Updated:      {tag_data.get('lastUpdated', 'N/A')}")
            click.echo(f"  Collect Aggregates: {tag_data.get('collectAggregates', False)}")

            # Show current value
            current = value_data.get("current")
            if current:
                value_obj = current.get("value", {})
                click.echo(f"\n  Current Value:")
                click.echo(f"    Value:        {value_obj.get('value', 'N/A')}")
                click.echo(f"    Timestamp:    {current.get('timestamp', 'N/A')}")
            else:
                click.echo(f"\n  Current Value:     No value assigned yet")

            # Show aggregates if requested
            if include_aggregates:
                aggregates = value_data.get("aggregates", {})
                if aggregates:
                    click.echo(f"\n  Aggregates:")
                    click.echo(f"    Min:   {aggregates.get('min', 'N/A')}")
                    click.echo(f"    Max:   {aggregates.get('max', 'N/A')}")
                    click.echo(f"    Avg:   {aggregates.get('avg', 'N/A')}")
                    click.echo(f"    Count: {aggregates.get('count', 'N/A')}")
            click.echo()

        except Exception as exc:
            handle_api_error(exc)

    @tag.command(name="create")
    @click.argument("tag_path")
    @click.option(
        "--type",
        "-t",
        "tag_type",
        type=click.Choice(["DOUBLE", "INT", "STRING", "BOOLEAN", "U_INT64", "DATE_TIME"]),
        required=True,
        help="Tag data type",
    )
    @click.option(
        "--workspace",
        "-w",
        type=str,
        default=None,
        help="Workspace ID or name (defaults to default workspace)",
    )
    @click.option(
        "--keywords",
        "-k",
        type=str,
        default=None,
        help="Comma-separated keywords",
    )
    @click.option(
        "--properties",
        "-p",
        type=str,
        multiple=True,
        help="Properties as key=value (can be used multiple times)",
    )
    @click.option(
        "--collect-aggregates",
        is_flag=True,
        help="Enable aggregate value collection",
    )
    def create_tag(
        tag_path: str,
        tag_type: str,
        workspace: Optional[str],
        keywords: Optional[str],
        properties: tuple,
        collect_aggregates: bool,
    ) -> None:
        """Create a new tag."""
        from .utils import check_readonly_mode

        check_readonly_mode("create a tag")

        try:
            ws_id = resolve_workspace_id(workspace)

            # Parse keywords and properties
            keywords_list = _parse_keywords(keywords)
            properties_dict = _parse_properties(properties)

            # Create tag payload
            tag_payload = {
                "path": tag_path,
                "type": tag_type,
                "workspace": ws_id,
                "collectAggregates": collect_aggregates,
            }

            if keywords_list:
                tag_payload["keywords"] = keywords_list

            if properties_dict:
                tag_payload["properties"] = properties_dict

            encoded_path = urllib.parse.quote(tag_path, safe="")
            ws_path = f"{ws_id}/" if ws_id else ""
            url = f"{get_base_url()}/nitag/v2/tags/{ws_path}{encoded_path}"
            make_api_request("PUT", url, payload=tag_payload)

            format_success("Tag created", {"path": tag_path, "type": tag_type, "workspace": ws_id})

        except Exception as exc:
            handle_api_error(exc)

    @tag.command(name="update")
    @click.argument("tag_path")
    @click.option(
        "--workspace",
        "-w",
        type=str,
        default=None,
        help="Workspace ID or name (defaults to default workspace)",
    )
    @click.option(
        "--keywords",
        "-k",
        type=str,
        default=None,
        help="Comma-separated keywords",
    )
    @click.option(
        "--properties",
        "-p",
        type=str,
        multiple=True,
        help="Properties as key=value (can be used multiple times)",
    )
    @click.option(
        "--merge",
        is_flag=True,
        help="Merge with existing keywords/properties (vs replace)",
    )
    def update_tag(
        tag_path: str,
        workspace: Optional[str],
        keywords: Optional[str],
        properties: tuple,
        merge: bool,
    ) -> None:
        """Update tag metadata (keywords, properties)."""
        from .utils import check_readonly_mode

        check_readonly_mode("update a tag")

        try:
            ws_id = resolve_workspace_id(workspace)

            # Parse keywords and properties
            keywords_list = _parse_keywords(keywords)
            properties_dict = _parse_properties(properties)

            # Validate at least one field is provided
            if not keywords_list and not properties_dict:
                click.echo(
                    "✗ Error: At least one of --keywords or --properties must be specified",
                    err=True,
                )
                sys.exit(ExitCodes.INVALID_INPUT)

            # Create update payload
            tag_update: Dict[str, Any] = {
                "path": tag_path,
            }
            if keywords_list:
                tag_update["keywords"] = keywords_list
            if properties_dict:
                tag_update["properties"] = properties_dict

            update_payload = {
                "tags": [tag_update],
                "merge": merge,
            }

            url = f"{get_base_url()}/nitag/v2/update-tags"
            make_api_request("POST", url, payload=update_payload)

            format_success("Tag updated", {"path": tag_path, "workspace": ws_id})

        except Exception as exc:
            handle_api_error(exc)

    @tag.command(name="delete")
    @click.argument("tag_path")
    @click.option(
        "--workspace",
        "-w",
        type=str,
        default=None,
        help="Workspace ID or name (defaults to default workspace)",
    )
    @click.confirmation_option(prompt="Are you sure you want to delete this tag?")
    def delete_tag(tag_path: str, workspace: Optional[str]) -> None:
        """Delete a tag.

        TAG_PATH is the path identifier of the tag to delete.
        """
        from .utils import check_readonly_mode

        check_readonly_mode("delete a tag")

        try:
            ws_id = resolve_workspace_id(workspace)
            encoded_path = urllib.parse.quote(tag_path, safe="")
            ws_path = f"{ws_id}/" if ws_id else ""

            url = f"{get_base_url()}/nitag/v2/tags/{ws_path}{encoded_path}"
            make_api_request("DELETE", url, payload=None)

            format_success("Tag deleted", {"path": tag_path, "workspace": ws_id})

        except Exception as exc:
            handle_api_error(exc)

    @tag.command(name="set-value")
    @click.argument("tag_path")
    @click.argument("value")
    @click.option(
        "--workspace",
        "-w",
        type=str,
        default=None,
        help="Workspace ID or name (defaults to default workspace)",
    )
    @click.option(
        "--type",
        "-t",
        "data_type",
        type=click.Choice(["DOUBLE", "INT", "STRING", "BOOLEAN", "U_INT64", "DATE_TIME"]),
        default=None,
        help="Override the value data type (auto-detected from the tag definition by default)",
    )
    @click.option(
        "--timestamp",
        type=str,
        default=None,
        help="Timestamp in ISO-8601 format (defaults to now)",
    )
    def set_tag_value(
        tag_path: str,
        value: str,
        workspace: Optional[str],
        data_type: Optional[str],
        timestamp: Optional[str],
    ) -> None:
        """Write a value to a tag.

        TAG_PATH is the path identifier of the tag.
        VALUE is the value to write.

        If you receive a "Conflict" error, the inferred type does not match the
        tag's registered data type. Use --type to specify the correct type explicitly.

        \b
        Auto-detected value type (when --type is not provided):
        - 'true' or 'false' (case-insensitive) -> BOOLEAN
        - Integer numbers -> INT
        - Decimal numbers -> DOUBLE
        - Everything else -> STRING
        """
        try:
            ws_id = resolve_workspace_id(workspace)
            encoded_path = urllib.parse.quote(tag_path, safe="")
            ws_path = f"{ws_id}/" if ws_id else ""

            if data_type:
                # User explicitly specified the type — no need to fetch metadata
                tag_type: Optional[str] = data_type
            else:
                # Retrieve tag metadata to align value type with the tag definition
                tag_meta_url = f"{get_base_url()}/nitag/v2/tags/{ws_path}{encoded_path}"
                tag_resp = make_api_request("GET", tag_meta_url, payload=None)
                tag_data = tag_resp.json()
                tag_type = tag_data.get("type")

            # Detect value type and convert (used for converted_value and as fallback type)
            converted_value, value_type = _detect_value_type(value)

            # Always use the tag's registered type (or user-supplied --type) when available,
            # so the API receives the correct type even if auto-detection disagrees.
            if tag_type:
                value_type = tag_type

            # API expects value as string
            api_value_str = value

            # If the tag is U_INT64, enforce non-negative integer and set correct type
            if tag_type == "U_INT64":
                try:
                    numeric_val = int(value)
                except ValueError:
                    click.echo(
                        "✗ Error: U_INT64 tags require a non-negative integer value",
                        err=True,
                    )
                    sys.exit(ExitCodes.INVALID_INPUT)

                if numeric_val < 0:
                    click.echo(
                        "✗ Error: U_INT64 tags require a non-negative integer value",
                        err=True,
                    )
                    sys.exit(ExitCodes.INVALID_INPUT)

                converted_value = numeric_val
                api_value_str = value
            elif tag_type == "DATE_TIME":
                # For date-time tags, pass the value through as-is
                converted_value = value
                api_value_str = value
            elif value_type == "BOOLEAN":
                # Normalize boolean string values to lowercase
                api_value_str = "true" if converted_value else "false"

            # Create value payload
            value_payload: Dict[str, Any] = {
                "value": {
                    "value": api_value_str,
                    "type": value_type,
                }
            }

            if timestamp:
                value_payload["timestamp"] = timestamp

            url = f"{get_base_url()}/nitag/v2/tags/{ws_path}{encoded_path}/values/current"
            make_api_request("PUT", url, payload=value_payload)

            # make_api_request raises on HTTP error status codes, so if we reach here it succeeded
            format_success(
                "Tag value updated",
                {"path": tag_path, "value": converted_value, "type": value_type},
            )

        except Exception as exc:
            handle_api_error(exc)

    @tag.command(name="get-value")
    @click.argument("tag_path")
    @click.option(
        "--workspace",
        "-w",
        type=str,
        default=None,
        help="Workspace ID or name (defaults to default workspace)",
    )
    @click.option(
        "--include-aggregates",
        is_flag=True,
        help="Include min/max/avg/count aggregates",
    )
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    def get_tag_value(
        tag_path: str,
        workspace: Optional[str],
        include_aggregates: bool,
        format: str,
    ) -> None:
        """Read the current value of a tag.

        TAG_PATH is the path identifier of the tag.
        """
        validate_output_format(format)

        try:
            ws_id = resolve_workspace_id(workspace)
            encoded_path = urllib.parse.quote(tag_path, safe="")
            ws_path = f"{ws_id}/" if ws_id else ""

            url = f"{get_base_url()}/nitag/v2/tags/{ws_path}{encoded_path}/values"
            resp = make_api_request("GET", url, payload=None)

            # Handle 204 No Content (tag has no value yet)
            if resp.status_code == 204:
                if format.lower() == "json":
                    click.echo("{}")
                else:
                    click.echo("No value found")
                return

            value_data = resp.json()

            if format.lower() == "json":
                click.echo(json.dumps(value_data, indent=2))
            else:
                # Table format
                current = value_data.get("current")
                if not current:
                    click.echo("No value found")
                    return

                value_obj = current.get("value", {})
                click.echo(f"\n✓ Tag Value: {tag_path}")
                click.echo("-" * 60)
                click.echo(f"  Value:     {value_obj.get('value', 'N/A')}")
                click.echo(f"  Type:      {value_obj.get('type', 'N/A')}")
                click.echo(f"  Timestamp: {current.get('timestamp', 'N/A')}")

                if include_aggregates:
                    aggregates = value_data.get("aggregates", {})
                    if aggregates:
                        click.echo(f"\n  Aggregates:")
                        click.echo(f"    Min:   {aggregates.get('min', 'N/A')}")
                        click.echo(f"    Max:   {aggregates.get('max', 'N/A')}")
                        click.echo(f"    Avg:   {aggregates.get('avg', 'N/A')}")
                        click.echo(f"    Count: {aggregates.get('count', 'N/A')}")
                click.echo()

        except Exception as exc:
            handle_api_error(exc)
