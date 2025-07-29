"""Shared utility functions for SystemLink CLI."""

import datetime
import json
import os
import sys
from typing import Dict, List, Any, Optional

import click
import keyring
import requests
from nisystemlink.clients.core._http_configuration import HttpConfiguration


class ExitCodes:
    """Standard exit codes for CLI operations."""

    SUCCESS = 0
    GENERAL_ERROR = 1
    INVALID_INPUT = 2
    NOT_FOUND = 3
    PERMISSION_DENIED = 4
    NETWORK_ERROR = 5


def handle_api_error(exc: Exception) -> None:
    """Handle API errors with appropriate exit codes and consistent formatting.

    Args:
        exc: The exception to handle
    """
    error_msg = str(exc).lower()
    if "not found" in error_msg:
        click.echo(f"✗ Resource not found: {exc}", err=True)
        sys.exit(ExitCodes.NOT_FOUND)
    elif "permission" in error_msg or "unauthorized" in error_msg:
        click.echo(f"✗ Permission denied: {exc}", err=True)
        sys.exit(ExitCodes.PERMISSION_DENIED)
    elif "network" in error_msg or "connection" in error_msg:
        click.echo(f"✗ Network error: {exc}", err=True)
        sys.exit(ExitCodes.NETWORK_ERROR)
    else:
        click.echo(f"✗ Error: {exc}", err=True)
        sys.exit(ExitCodes.GENERAL_ERROR)


def format_success(message: str, data=None) -> None:
    """Format success messages consistently.

    Args:
        message: Success message to display
        data: Optional data to display with the message
    """
    if data:
        click.echo(f"✓ {message}")
        for key, value in data.items():
            click.echo(f"  {key}: {value}")
    else:
        click.echo(f"✓ {message}")


def output_list_data(
    items: List[Dict[str, Any]],
    output_format: str,
    headers: List[str],
    table_data_func,
    empty_message: str = "No items found.",
) -> None:
    """Handle JSON and table output for list commands consistently.

    Args:
        items: List of items to output
        output_format: 'json' or 'table'
        headers: List of header names for table output
        table_data_func: Function that converts items to table rows
        empty_message: Message to display when no items are found
    """
    if not items:
        if output_format.lower() == "json":
            click.echo("[]")
        else:
            click.echo(empty_message)
        return

    if output_format.lower() == "json":
        click.echo(json.dumps(items, indent=2))
    else:
        from tabulate import tabulate
        from click import style as cstyle

        def color_row(row):
            """Color table rows with consistent styling."""
            ws = str(row[0])
            ws_short = ws[:15] + ("…" if len(ws) > 15 else "")
            return [
                cstyle(ws_short, fg="blue"),
                cstyle(str(row[1]), fg="green"),
                cstyle(str(row[2]), fg="blue"),
            ]

        table = []
        for item in items:
            table.append(color_row(table_data_func(item)))

        styled_headers = [
            cstyle(headers[0], fg="blue", bold=True),
            cstyle(headers[1], fg="green", bold=True),
            cstyle(headers[2], fg="blue", bold=True),
        ]
        click.echo(tabulate(table, headers=styled_headers, tablefmt="github"))


def output_formatted_list(
    items: List[Dict[str, Any]],
    output_format: str,
    headers: List[str],
    column_widths: List[int],
    row_formatter_func,
    empty_message: str = "No items found.",
    total_label: str = "item(s)",
) -> None:
    """Handle JSON and table output with box-drawing characters for list commands.

    Args:
        items: List of items to output
        output_format: 'json' or 'table'
        headers: List of header names for table output
        column_widths: List of column widths for table formatting
        row_formatter_func: Function that converts item to list of column values
        empty_message: Message to display when no items are found
        total_label: Label for total count (e.g., "configuration(s)", "template(s)")
    """
    if not items:
        if output_format.lower() == "json":
            click.echo("[]")
        else:
            click.echo(empty_message)
        return

    if output_format.lower() == "json":
        click.echo(json.dumps(items, indent=2))
        return

    # Table format with box-drawing characters
    if len(headers) != len(column_widths):
        raise ValueError("Headers and column_widths must have the same length")

    # Top border
    border_chars = ["┌"] + [("─" * (w + 2)) for w in column_widths]
    border_line = border_chars[0] + border_chars[1]
    for part in border_chars[2:]:
        border_line += "┬" + part
    border_line += "┐"
    click.echo(border_line)

    # Header row
    header_parts = ["│"]
    for header, width in zip(headers, column_widths):
        header_parts.append(f" {header:<{width}} │")
    click.echo("".join(header_parts))

    # Middle border
    border_chars = ["├"] + [("─" * (w + 2)) for w in column_widths]
    border_line = border_chars[0] + border_chars[1]
    for part in border_chars[2:]:
        border_line += "┼" + part
    border_line += "┤"
    click.echo(border_line)

    # Data rows
    for item in items:
        row_data = row_formatter_func(item)
        if len(row_data) != len(column_widths):
            raise ValueError("Row data must match column count")

        row_parts = ["│"]
        for value, width in zip(row_data, column_widths):
            # Truncate if necessary
            str_value = str(value or "")[:width]
            row_parts.append(f" {str_value:<{width}} │")
        click.echo("".join(row_parts))

    # Bottom border
    border_chars = ["└"] + [("─" * (w + 2)) for w in column_widths]
    border_line = border_chars[0] + border_chars[1]
    for part in border_chars[2:]:
        border_line += "┴" + part
    border_line += "┘"
    click.echo(border_line)

    # Total count
    click.echo(f"\nTotal: {len(items)} {total_label}")


def resolve_workspace_filter(workspace: str, workspace_map: Dict[str, str]) -> str:
    """Resolve workspace name to ID for filtering.

    Args:
        workspace: Workspace name or ID to resolve
        workspace_map: Dictionary mapping workspace IDs to names

    Returns:
        Workspace ID (either the original if it was an ID, or resolved from name)
    """
    if not workspace:
        return workspace

    # Check if it's already an ID (exists as key in workspace_map)
    if workspace in workspace_map:
        return workspace

    # Try to find by name (case-insensitive)
    for ws_id, ws_name in workspace_map.items():
        if ws_name and workspace.lower() == ws_name.lower():
            return ws_id

    # Return original if no match found
    return workspace


def filter_by_workspace(
    items: List[Dict[str, Any]],
    workspace: str,
    workspace_map: Dict[str, str],
    workspace_field: str = "workspace",
) -> List[Dict[str, Any]]:
    """Filter items by workspace name or ID.

    Args:
        items: List of items to filter
        workspace: Workspace name or ID to filter by
        workspace_map: Dictionary mapping workspace IDs to names
        workspace_field: Field name in items that contains workspace ID

    Returns:
        Filtered list of items
    """
    if not workspace:
        return items

    filtered_items = []
    for item in items:
        item_workspace = item.get(workspace_field, "")
        item_workspace_name = workspace_map.get(item_workspace, item_workspace)

        # Match by ID or name (case-insensitive)
        if workspace.lower() == item_workspace.lower() or (
            item_workspace_name and workspace.lower() == item_workspace_name.lower()
        ):
            filtered_items.append(item)

    return filtered_items


# --- SystemLink HTTP Configuration ---
def get_http_configuration() -> HttpConfiguration:
    """Return a configured SystemLink HttpConfiguration using environment or keyring credentials."""
    server_uri = (
        os.environ.get("SYSTEMLINK_API_URL")
        or keyring.get_password("systemlink-cli", "SYSTEMLINK_API_URL")
        or "http://localhost:8000"
    )
    api_key = os.environ.get("SYSTEMLINK_API_KEY") or keyring.get_password(
        "systemlink-cli", "SYSTEMLINK_API_KEY"
    )
    if not api_key:
        raise RuntimeError("API key not found. Please set SYSTEMLINK_API_KEY or run 'slcli login'.")
    return HttpConfiguration(
        server_uri=server_uri,
        api_key=api_key,
    )


def get_base_url() -> str:
    """Retrieve the SystemLink API base URL from environment or keyring."""
    url = os.environ.get("SYSTEMLINK_API_URL")
    if not url:
        url = keyring.get_password("systemlink-cli", "SYSTEMLINK_API_URL")
    return url or "http://localhost:8000"


def get_api_key() -> str:
    """Retrieve the SystemLink API key from environment or keyring."""
    import click

    api_key = os.environ.get("SYSTEMLINK_API_KEY")
    if not api_key:
        api_key = keyring.get_password("systemlink-cli", "SYSTEMLINK_API_KEY")
    if not api_key:
        click.echo(
            "Error: API key not found. Please set the SYSTEMLINK_API_KEY "
            "environment variable or run 'slcli login'."
        )
        raise click.ClickException("API key not found.")
    return api_key


def get_headers(content_type: str = "") -> Dict[str, str]:
    """Return headers for SystemLink API requests.

    Allows caller to override Content-Type. If content_type is None or empty, omit the header.
    """
    headers = {
        "x-ni-api-key": get_api_key(),
        "User-Agent": "SystemLink-CLI/1.0 (cross-platform)",
    }
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def get_ssl_verify() -> bool:
    """Return SSL verification setting from environment variable. Defaults to True."""
    env = os.environ.get("SLCLI_SSL_VERIFY")
    if env is not None:
        return env.lower() not in ("0", "false", "no")
    return True


def get_workspace_id_by_name(name: str) -> str:
    """Return the workspace id for a given workspace name (case-sensitive). Raises if not found."""
    ws_map = get_workspace_map()
    for ws_id, ws_name in ws_map.items():
        if ws_name == name:
            return ws_id
    raise ValueError(f"Workspace name '{name}' not found.")


def get_workspace_map() -> Dict[str, str]:
    """Get a mapping of workspace IDs to names.

    Returns:
        Dictionary mapping workspace ID to workspace name
    """
    try:
        url = f"{get_base_url()}/niuser/v1/workspaces?take=1000"
        resp = make_api_request("GET", url, payload=None, handle_errors=False)
        data = resp.json()
        workspaces = data.get("workspaces", [])
        return {ws.get("id"): ws.get("name") for ws in workspaces if ws.get("id")}
    except Exception:
        return {}


# --- File I/O Utilities ---
def load_json_file(filepath: str) -> Dict[str, Any]:
    """Load and parse JSON file with consistent error handling.

    Args:
        filepath: Path to JSON file to load

    Returns:
        Parsed JSON data as dictionary

    Raises:
        click.ClickException: If file cannot be loaded or parsed
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        click.echo(f"✗ File not found: {filepath}", err=True)
        sys.exit(ExitCodes.NOT_FOUND)
    except json.JSONDecodeError as exc:
        click.echo(f"✗ Invalid JSON in file {filepath}: {exc}", err=True)
        sys.exit(ExitCodes.INVALID_INPUT)
    except Exception as exc:
        click.echo(f"✗ Error reading file {filepath}: {exc}", err=True)
        sys.exit(ExitCodes.GENERAL_ERROR)


def save_json_file(data: Any, filepath: str, custom_serializer=None) -> None:
    """Save data to JSON file with consistent formatting and error handling.

    Args:
        data: Data to save as JSON
        filepath: Path where to save the JSON file
        custom_serializer: Optional custom JSON serializer function
    """

    def _default_json_serializer(obj):
        """Default JSON serializer for common types."""
        if isinstance(obj, (datetime.datetime, datetime.date)):
            return obj.isoformat()
        return str(obj)

    serializer = custom_serializer or _default_json_serializer

    try:
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, default=serializer)
    except Exception as exc:
        click.echo(f"✗ Error writing file {filepath}: {exc}", err=True)
        sys.exit(ExitCodes.GENERAL_ERROR)


# --- API Request Utilities ---
def make_api_request(
    method: str,
    url: str,
    payload: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    handle_errors: bool = True,
) -> requests.Response:
    """Make API request with consistent error handling and configuration.

    Args:
        method: HTTP method (GET, POST, etc.)
        url: API endpoint URL
        payload: Request payload for POST/PUT requests
        headers: Additional headers (will be merged with default headers)
        handle_errors: Whether to handle errors with consistent formatting

    Returns:
        Response object

    Raises:
        Handled via handle_api_error() if handle_errors=True
    """
    try:
        # Merge provided headers with default headers
        default_headers = get_headers()
        if headers:
            default_headers.update(headers)

        ssl_verify = get_ssl_verify()

        if method.upper() == "GET":
            resp = requests.get(url, headers=default_headers, verify=ssl_verify)
        elif method.upper() == "POST":
            resp = requests.post(url, headers=default_headers, json=payload, verify=ssl_verify)
        elif method.upper() == "PUT":
            resp = requests.put(url, headers=default_headers, json=payload, verify=ssl_verify)
        elif method.upper() == "DELETE":
            resp = requests.delete(url, headers=default_headers, verify=ssl_verify)
        else:
            raise ValueError(f"Unsupported HTTP method: {method}")

        resp.raise_for_status()
        return resp

    except requests.RequestException as exc:
        if handle_errors:
            handle_api_error(exc)
            # This line is never reached due to sys.exit() in handle_api_error(),
            # but is needed for type checking
            return None  # type: ignore
        else:
            raise


# --- Workspace Validation Utilities ---
def get_workspace_id_with_fallback(workspace_name: str) -> str:
    """Get workspace ID by name with fallback to original name if not found.

    This is a common pattern used across commands where workspace parameter
    can be either a name or an ID.

    Args:
        workspace_name: Workspace name or ID

    Returns:
        Workspace ID (validated name converted to ID, or original value as fallback)
    """
    try:
        return get_workspace_id_by_name(workspace_name)
    except (ValueError, Exception):
        # If workspace name lookup fails, use the original value as-is
        # This allows for direct workspace ID usage
        return workspace_name


def validate_workspace_access(workspace_name: str, warn_on_error: bool = True) -> str:
    """Validate workspace access with optional warning on failure.

    Args:
        workspace_name: Workspace name to validate
        warn_on_error: Whether to show warning if workspace not found

    Returns:
        Workspace ID if found, original name if not found
    """
    try:
        ws_id = get_workspace_id_by_name(workspace_name)
        if not isinstance(ws_id, str):
            raise ValueError("Workspace ID must be a string.")
        return ws_id
    except Exception:
        if warn_on_error:
            click.echo(
                f"✗ Warning: Workspace '{workspace_name}' not found, using as-is.",
                err=True,
            )
        return workspace_name


def sanitize_filename(name: str, fallback_prefix: str = "file") -> str:
    """Sanitize a name to create a safe filename.

    Removes invalid characters, converts spaces to hyphens, and makes lowercase.

    Args:
        name: The original name to sanitize
        fallback_prefix: Prefix to use if name is empty after sanitization

    Returns:
        A safe filename string
    """
    if not name:
        return fallback_prefix

    # Keep only alphanumeric characters, spaces, hyphens, and underscores
    safe_name = "".join(c for c in name if c.isalnum() or c in (" ", "-", "_")).rstrip()

    # Replace spaces with hyphens and convert to lowercase
    safe_name = safe_name.replace(" ", "-").lower()

    # Remove multiple consecutive hyphens
    import re

    safe_name = re.sub(r"-+", "-", safe_name)

    # Remove leading/trailing hyphens
    safe_name = safe_name.strip("-")

    # Return fallback if name becomes empty
    return safe_name if safe_name else fallback_prefix


def extract_error_type(error_name: str) -> str:
    """Extract a readable error type from a full class name.

    Args:
        error_name: Full error class name (e.g., "Skyline.WorkOrder.WorkflowNotFoundOrNoAccess")

    Returns:
        Short error type (e.g., "WorkflowNotFoundOrNoAccess")
    """
    if not error_name:
        return ""
    return error_name.split(".")[-1] if "." in error_name else error_name


def parse_inner_errors(inner_errors: List[Dict[str, Any]]) -> List[Dict[str, str]]:
    """Parse inner errors from API response into a standardized format.

    Args:
        inner_errors: List of inner error objects from API response

    Returns:
        List of parsed error dictionaries with standardized keys
    """
    parsed_errors = []
    for inner_error in inner_errors:
        error_name = inner_error.get("name", "")
        error_message = inner_error.get("message", "Unknown error")
        resource_id = inner_error.get("resourceId", "")
        resource_type = inner_error.get("resourceType", "")

        parsed_errors.append(
            {
                "name": error_name,
                "type": extract_error_type(error_name),
                "message": error_message,
                "resource_id": resource_id,
                "resource_type": resource_type,
            }
        )

    return parsed_errors


def display_api_errors(
    operation_name: str, response_data: Dict[str, Any], detailed: bool = True
) -> None:
    """Display API errors in a consistent format.

    Args:
        operation_name: Name of the operation that failed
        response_data: API response data containing error information
        detailed: Whether to show detailed inner errors
    """
    import sys

    click.echo(f"✗ {operation_name}:", err=True)

    # Check for error structure
    error = response_data.get("error", {})
    if not error:
        # Fallback to simple message if no detailed error structure
        message = response_data.get("message", "Unknown error")
        click.echo(f"  {message}", err=True)
        sys.exit(ExitCodes.GENERAL_ERROR)

    # Display main error message
    main_message = error.get("message", "Unknown error")
    click.echo(f"  {main_message}", err=True)

    # Parse inner errors for detailed validation messages
    if detailed:
        inner_errors = error.get("innerErrors", [])
        if inner_errors:
            click.echo("  Detailed errors:", err=True)
            parsed_errors = parse_inner_errors(inner_errors)
            for parsed_error in parsed_errors:
                error_type = parsed_error["type"]
                error_message = parsed_error["message"]

                if error_type:
                    click.echo(f"    - {error_type}: {error_message}", err=True)
                else:
                    click.echo(f"    - {error_message}", err=True)

    sys.exit(ExitCodes.GENERAL_ERROR)
