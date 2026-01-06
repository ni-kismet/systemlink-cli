"""CLI commands for managing SystemLink tags.

Provides CLI commands for creating, reading, updating, deleting, and managing
tag values. All tag operations are scoped to workspaces with proper error handling.
"""

import json
import shutil
import urllib.parse
from typing import Any, Dict, List, Optional

import click

from .cli_utils import validate_output_format
from .universal_handlers import FilteredResponse, UniversalResponseHandler
from .utils import (
    format_success,
    get_base_url,
    handle_api_error,
    make_api_request,
)
from .workspace_utils import resolve_workspace_id


def _get_default_workspace_id() -> str:
    """Get the default workspace ID from configuration.

    Returns:
        The default workspace ID

    Raises:
        Exception: If default workspace cannot be determined
    """
    try:
        url = f"{get_base_url()}/niuser/v1/workspaces"
        resp = make_api_request("GET", url, payload=None)
        data = resp.json()
        workspaces = data.get("workspaces", [])
        if workspaces:
            # Return the first workspace as default
            return workspaces[0]["id"]
        raise Exception("No workspaces available")
    except Exception as exc:
        raise Exception(f"Failed to get default workspace: {str(exc)}")


def _resolve_workspace(workspace_id: Optional[str] = None) -> str:
    """Resolve workspace ID, using default if not provided.

    Args:
        workspace_id: Optional workspace ID or name. If None, uses default workspace.

    Returns:
        The resolved workspace ID

    Raises:
        Exception: If workspace cannot be resolved
    """
    if workspace_id:
        return resolve_workspace_id(workspace_id)
    return _get_default_workspace_id()


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


def _get_tag_value_display(tag_data: Dict[str, Any]) -> str:
    """Format tag value for display.

    Args:
        tag_data: Tag data with value information

    Returns:
        Formatted value string
    """
    # handle nested structure if present
    current = tag_data.get("current", tag_data)
    if not current:
        return "No value"

    value_obj = current.get("value", {})
    value = value_obj.get("value", "N/A")
    timestamp = current.get("timestamp", "")

    if timestamp:
        return f"{value} (at {timestamp})"
    return str(value)


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

    # Account for table borders and padding: 5 vertical bars + 8 spaces (2 per column)
    border_overhead = 14

    # Calculate remaining space for path
    fixed_columns = type_width + value_width + last_updated_width
    path_width = terminal_width - fixed_columns - border_overhead

    # Ensure minimum path width of 30, maximum of 100
    path_width = max(30, min(100, path_width))

    return [path_width, type_width, value_width, last_updated_width]


def _detect_value_type(value_str: str) -> tuple[Any, str]:
    """Detect the type of a value from its string representation.

    Args:
        value_str: String representation of the value

    Returns:
        Tuple of (converted_value, type_string) where type_string is
        'BOOLEAN', 'INT', 'DOUBLE', or 'STRING'
    """
    # Check for boolean
    if value_str.lower() in ("true", "false"):
        return value_str.lower() == "true", "BOOLEAN"

    # Check for integer
    try:
        int_val = int(value_str)
        # Make sure it's not a float disguised as int
        if "." not in value_str:
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
        help="Filter by tag path (e.g., '*.temperature')",
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
            ws_id = _resolve_workspace(workspace)

            # Build filter string
            # API requires workspace in the filter
            filter_parts = [f'workspace = "{ws_id}"']

            if filter:
                filter_parts.append(f'path = "*{filter}*"')

            if keywords:
                for k in keywords.split(","):
                    k_clean = k.strip()
                    if k_clean:
                        filter_parts.append(f'keywords.Contains("{k_clean}")')

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
                    if click.confirm(f"Show next {take} results?", default=True):
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
            ws_id = _resolve_workspace(workspace)
            encoded_path = urllib.parse.quote(tag_path, safe="")

            # Get tag metadata
            url = f"{get_base_url()}/nitag/v2/tags/{ws_id}/{encoded_path}"
            tag_resp = make_api_request("GET", url, payload=None)
            tag_data = tag_resp.json()

            # Get tag value with aggregates
            value_url = f"{get_base_url()}/nitag/v2/tags/{ws_id}/{encoded_path}/values"
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
        type=click.Choice(["DOUBLE", "INT", "STRING", "BOOLEAN", "U_INT64", "DATE_TIME"]),
        required=True,
        help="Tag data type",
    )
    @click.option(
        "--workspace",
        "-w",
        type=str,
        default=None,
        help="Workspace ID (defaults to default workspace)",
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
        type: str,
        workspace: Optional[str],
        keywords: Optional[str],
        properties: tuple,
        collect_aggregates: bool,
    ) -> None:
        """Create a new tag."""
        try:
            ws_id = _resolve_workspace(workspace)

            # Parse keywords
            keywords_list = []
            if keywords:
                keywords_list = [k.strip() for k in keywords.split(",")]

            # Parse properties
            properties_dict: Dict[str, str] = {}
            for prop in properties:
                if "=" not in prop:
                    raise ValueError(f"Invalid property format: {prop}. Use key=value")
                key, val = prop.split("=", 1)
                properties_dict[key.strip()] = val.strip()

            # Create tag payload
            tag_payload = {
                "path": tag_path,
                "type": type,
                "workspace": ws_id,
                "collectAggregates": collect_aggregates,
            }

            if keywords_list:
                tag_payload["keywords"] = keywords_list

            if properties_dict:
                tag_payload["properties"] = properties_dict

            encoded_path = urllib.parse.quote(tag_path, safe="")
            url = f"{get_base_url()}/nitag/v2/tags/{ws_id}/{encoded_path}"
            make_api_request("PUT", url, payload=tag_payload)

            format_success("Tag created", {"path": tag_path, "type": type, "workspace": ws_id})

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
        try:
            ws_id = _resolve_workspace(workspace)

            # Parse keywords
            keywords_list = []
            if keywords:
                keywords_list = [k.strip() for k in keywords.split(",")]

            # Parse properties
            properties_dict: Dict[str, str] = {}
            for prop in properties:
                if "=" not in prop:
                    raise ValueError(f"Invalid property format: {prop}. Use key=value")
                key, val = prop.split("=", 1)
                properties_dict[key.strip()] = val.strip()

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
        try:
            ws_id = _resolve_workspace(workspace)
            encoded_path = urllib.parse.quote(tag_path, safe="")

            url = f"{get_base_url()}/nitag/v2/tags/{ws_id}/{encoded_path}"
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
        "--timestamp",
        type=str,
        default=None,
        help="Timestamp in ISO-8601 format (defaults to now)",
    )
    def set_tag_value(
        tag_path: str, value: str, workspace: Optional[str], timestamp: Optional[str]
    ) -> None:
        """Write a value to a tag.

        TAG_PATH is the path identifier of the tag.
        VALUE is the value to write.

        Automatically detects value type:
        - 'true' or 'false' (case-insensitive) -> BOOLEAN
        - Integer numbers -> INT
        - Decimal numbers -> DOUBLE
        - Everything else -> STRING
        """
        try:
            ws_id = _resolve_workspace(workspace)
            encoded_path = urllib.parse.quote(tag_path, safe="")

            # Detect value type and convert
            converted_value, value_type = _detect_value_type(value)

            # API expects value as string
            if value_type == "BOOLEAN":
                api_value_str = "True" if converted_value else "False"
            else:
                # Keep the original string representation for numbers
                api_value_str = value

            # Create value payload
            value_payload: Dict[str, Any] = {
                "value": {
                    "value": api_value_str,
                    "type": value_type,
                }
            }

            if timestamp:
                value_payload["timestamp"] = timestamp

            url = f"{get_base_url()}/nitag/v2/tags/{ws_id}/{encoded_path}/values/current"
            resp = make_api_request("PUT", url, payload=value_payload)

            # Handle both 200 and 202 responses
            if resp.status_code in (200, 202):
                format_success(
                    "Tag value updated",
                    {"path": tag_path, "value": converted_value, "type": value_type},
                )
            else:
                raise Exception(f"Unexpected response status: {resp.status_code}")

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
            ws_id = _resolve_workspace(workspace)
            encoded_path = urllib.parse.quote(tag_path, safe="")

            url = f"{get_base_url()}/nitag/v2/tags/{ws_id}/{encoded_path}/values"
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
