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


def get_workspace_map() -> Dict[str, str]:
    """Return a mapping of workspace id to workspace name."""
    url = f"{get_base_url()}/niuser/v1/workspaces"
    resp = requests.get(url, headers=get_headers(), verify=get_ssl_verify())
    resp.raise_for_status()
    ws_data = resp.json()
    return {ws.get("id"): ws.get("name", ws.get("id")) for ws in ws_data.get("workspaces", [])}


def get_workspace_id_by_name(name: str) -> str:
    """Return the workspace id for a given workspace name (case-sensitive). Raises if not found."""
    ws_map = get_workspace_map()
    for ws_id, ws_name in ws_map.items():
        if ws_name == name:
            return ws_id
    raise ValueError(f"Workspace name '{name}' not found.")


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
