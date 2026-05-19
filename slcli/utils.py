"""Shared utility functions for SystemLink CLI."""

import datetime
import json
import os
import sys
from dataclasses import dataclass
from typing import Dict, List, Any, Optional, Callable, Sequence

import click
import keyring
import requests

from .rich_output import print_json


class SystemLinkConfig:
    """Simple configuration class for SystemLink API connection."""

    def __init__(self, server_uri: str, api_key: str, ssl_verify: bool = True):
        """Initialize SystemLink configuration.

        Args:
            server_uri: Base URL for the SystemLink API
            api_key: API key for authentication
            ssl_verify: Whether to verify SSL certificates
        """
        self.server_uri = server_uri
        self.api_key = api_key
        self.ssl_verify = ssl_verify


@dataclass(frozen=True)
class ResolvedConfigValue:
    """Resolved configuration value plus the source that supplied it."""

    value: str
    source: str


class ExitCodes:
    """Standard exit codes for CLI operations."""

    SUCCESS = 0
    GENERAL_ERROR = 1
    INVALID_INPUT = 2
    NOT_FOUND = 3
    PERMISSION_DENIED = 4
    NETWORK_ERROR = 5


def check_readonly_mode(operation: str = "this operation") -> None:
    """Check if the active profile is in readonly mode and exit if it is.

    This function should be called at the start of any mutation command
    (create, update, delete, edit, import, upload, publish, disable) to prevent
    modifications when the profile is in readonly mode.

    Args:
        operation: Description of the operation being attempted (e.g., "delete this resource")

    Raises:
        SystemExit: If the active profile is in readonly mode
    """
    from .profiles import is_active_profile_readonly

    if is_active_profile_readonly():
        click.echo(f"✗ Cannot {operation}: profile is in readonly mode", err=True)
        click.echo(
            "Readonly mode disables all mutation operations "
            "(create, update, delete, edit, import, upload, publish, disable) for safety.",
            err=True,
        )
        sys.exit(ExitCodes.PERMISSION_DENIED)


def _extract_response_error_message(exc: Exception) -> Optional[str]:
    """Extract a human-readable error message from an HTTP error response body.

    Attempts to parse the response JSON and extract the error message from
    common SystemLink error formats (e.g., ``{"error": {"message": "..."}}``)
    or a top-level ``"message"`` field.

    Args:
        exc: The exception, expected to be a ``requests.HTTPError`` with a response.

    Returns:
        The extracted message string, or ``None`` if unavailable.
    """
    response = getattr(exc, "response", None)
    if response is None:
        return None
    try:
        body = response.json()
    except (ValueError, AttributeError):
        return None

    # SystemLink standard: {"error": {"message": "..."}}
    error_obj = body.get("error") if isinstance(body, dict) else None
    if isinstance(error_obj, dict):
        msg = error_obj.get("message")
        if msg:
            return str(msg)

    # Fallback: top-level {"message": "..."}
    if isinstance(body, dict):
        msg = body.get("message")
        if msg:
            return str(msg)

    return None


def _extract_response_status_code(exc: Exception) -> Optional[int]:
    """Extract the HTTP status code from an exception response, if present."""
    response = getattr(exc, "response", None)
    status_code = getattr(response, "status_code", None)
    return status_code if isinstance(status_code, int) else None


def handle_api_error(exc: Exception) -> None:
    """Handle API errors with appropriate exit codes and consistent formatting.

    When the exception originates from an HTTP response that contains a JSON
    error body, the server-provided message is displayed instead of the generic
    HTTP status line so that users get actionable feedback.

    Args:
        exc: The exception to handle
    """
    # Try to get a detailed message from the response body first
    detail = _extract_response_error_message(exc)
    display_msg = detail if detail else str(exc)
    status_code = _extract_response_status_code(exc)

    error_msg = display_msg.lower()
    if status_code == 404 or "not found" in error_msg:
        click.echo(f"✗ Resource not found: {display_msg}", err=True)
        sys.exit(ExitCodes.NOT_FOUND)
    elif status_code in (401, 403) or (
        "permission" in error_msg or "unauthorized" in error_msg or "forbidden" in error_msg
    ):
        click.echo(f"✗ Permission denied: {display_msg}", err=True)
        sys.exit(ExitCodes.PERMISSION_DENIED)
    elif "network" in error_msg or "connection" in error_msg:
        click.echo(f"✗ Network error: {display_msg}", err=True)
        sys.exit(ExitCodes.NETWORK_ERROR)
    else:
        click.echo(f"✗ Error: {display_msg}", err=True)
        sys.exit(ExitCodes.GENERAL_ERROR)


def format_success(message: str, data: Optional[Any] = None) -> None:
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
    table_data_func: Callable[[Dict[str, Any]], List[str]],
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
        print_json(items)
    else:
        from .rich_output import render_table

        rows = [table_data_func(item) for item in items]
        column_widths = []
        for index, header in enumerate(headers):
            max_width = len(header)
            for row in rows:
                max_width = max(max_width, len(str(row[index] or "")))
            column_widths.append(min(max_width, 40))

        render_table(headers, column_widths, rows, show_total=False)


def output_formatted_list(
    items: List[Dict[str, Any]],
    output_format: str,
    headers: List[str],
    column_widths: List[int],
    row_formatter_func: Callable[[Dict[str, Any]], List[Any]],
    empty_message: str = "No items found.",
    total_label: str = "item(s)",
) -> None:
    """Handle JSON and table output with Rich-backed table rendering.

    Args:
        items: List of items to output
        output_format: 'json' or 'table'
        headers: List of header names for table output
        column_widths: List of column widths for table formatting
        row_formatter_func: Function that converts item to list of column values
        empty_message: Message to display when no items are found
        total_label: Label for total count (e.g., "configuration(s)", "template(s)")
    """
    from .table_utils import output_formatted_list as output_formatted_list_rich

    output_formatted_list_rich(
        items,
        output_format,
        headers,
        column_widths,
        row_formatter_func,
        empty_message,
        total_label,
    )


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
def get_http_configuration() -> SystemLinkConfig:
    """Return a configured SystemLink configuration using profiles, environment, or keyring.

    Preference order:
    1. Environment variables (SYSTEMLINK_API_URL, SYSTEMLINK_API_KEY)
    2. Active profile from config file
    3. Keyring (legacy fallback)
    """
    server_uri = get_base_url()
    api_key = get_api_key()

    ssl_verify = get_ssl_verify()

    return SystemLinkConfig(
        server_uri=server_uri,
        api_key=api_key,
        ssl_verify=ssl_verify,
    )


def _get_env_override(env_names: Sequence[str]) -> Optional[ResolvedConfigValue]:
    """Return the first non-empty environment override from the provided names."""
    for env_name in env_names:
        value = os.environ.get(env_name)
        if value:
            return ResolvedConfigValue(value=value, source=f"env:{env_name}")
    return None


def source_is_env(source: str) -> bool:
    """Return True when the resolved source came from an environment variable."""
    return source.startswith("env:")


def describe_config_source(source: str) -> str:
    """Return a user-facing description of a resolved configuration source."""
    if source.startswith("env:"):
        return f"Environment ({source.split(':', 1)[1]})"
    if source.startswith("profile:"):
        return f"Profile '{source.split(':', 1)[1]}'"
    if source.startswith("keyring:"):
        return f"Legacy keyring ({source.split(':', 1)[1]})"
    if source.startswith("default:"):
        return f"Default ({source.split(':', 1)[1]})"
    if source.startswith("derived:"):
        derived_from = source.split(":", 1)[1]
        return f"Derived from API URL via {describe_config_source(derived_from)}"
    return source


def get_base_url_resolution() -> ResolvedConfigValue:
    """Resolve the SystemLink API base URL and record where it came from.

    Preference order:
    1. Environment variable SLCLI_API_URL (preferred) or SYSTEMLINK_API_URL
    2. Active profile from config file
    3. Combined keyring config (legacy)
    4. Legacy keyring entry SYSTEMLINK_API_URL
    5. Default fallback to localhost
    """
    override = _get_env_override(("SLCLI_API_URL", "SYSTEMLINK_API_URL"))
    if override is not None:
        return ResolvedConfigValue(override.value.rstrip("/"), override.source)

    try:
        from .profiles import get_active_profile

        profile = get_active_profile()
        if profile and profile.server:
            return ResolvedConfigValue(profile.server.rstrip("/"), f"profile:{profile.name}")
    except (FileNotFoundError, json.JSONDecodeError, KeyError, AttributeError):
        pass

    cfg = _get_keyring_config()
    if cfg and isinstance(cfg, dict):
        config_url = cfg.get("api_url")
        if config_url:
            return ResolvedConfigValue(str(config_url).rstrip("/"), "keyring:SYSTEMLINK_CONFIG")

    try:
        url = keyring.get_password("systemlink-cli", "SYSTEMLINK_API_URL")
    except Exception:
        url = None
    if url:
        return ResolvedConfigValue(url.rstrip("/"), "keyring:SYSTEMLINK_API_URL")

    return ResolvedConfigValue("http://localhost:8000", "default:localhost")


def get_web_url_resolution() -> ResolvedConfigValue:
    """Resolve the SystemLink web UI URL and record where it came from.

    Preference order:
    1. Environment variable SLCLI_WEB_URL (preferred) or SYSTEMLINK_WEB_URL
    2. Active profile from config file
    3. Combined keyring config (legacy)
    4. Legacy keyring entry SYSTEMLINK_WEB_URL
    5. Derived from the effective API base URL
    """
    override = _get_env_override(("SLCLI_WEB_URL", "SYSTEMLINK_WEB_URL"))
    if override is not None:
        return ResolvedConfigValue(override.value.rstrip("/"), override.source)

    try:
        from .profiles import get_active_profile

        profile = get_active_profile()
        if profile and profile.web_url:
            return ResolvedConfigValue(profile.web_url.rstrip("/"), f"profile:{profile.name}")
    except (FileNotFoundError, json.JSONDecodeError, KeyError, AttributeError):
        pass

    cfg = _get_keyring_config()
    if cfg and isinstance(cfg, dict):
        maybe = cfg.get("web_url") or cfg.get("webUrl") or cfg.get("web_ui_url")
        if maybe:
            return ResolvedConfigValue(str(maybe).rstrip("/"), "keyring:SYSTEMLINK_CONFIG")

    try:
        url = keyring.get_password("systemlink-cli", "SYSTEMLINK_WEB_URL")
    except Exception:
        url = None
    if url:
        return ResolvedConfigValue(url.rstrip("/"), "keyring:SYSTEMLINK_WEB_URL")

    base_resolution = get_base_url_resolution()
    base = base_resolution.value
    try:
        from urllib.parse import urlparse

        parsed = urlparse(base if base.startswith("http") else "https://" + base)
        host = parsed.netloc or parsed.path
        if not host:
            return ResolvedConfigValue("https://localhost", f"derived:{base_resolution.source}")
        return ResolvedConfigValue(
            f"https://{host.rstrip('/')}",
            f"derived:{base_resolution.source}",
        )
    except Exception:
        return ResolvedConfigValue("https://localhost", f"derived:{base_resolution.source}")


def get_api_key_resolution(emit_error: bool = True) -> ResolvedConfigValue:
    """Resolve the SystemLink API key and record where it came from.

    Preference order:
    1. Environment variable SLCLI_API_KEY (preferred) or SYSTEMLINK_API_KEY
    2. Active profile from config file
    3. Combined keyring config (legacy)
    4. Legacy keyring entry SYSTEMLINK_API_KEY
    """
    override = _get_env_override(("SLCLI_API_KEY", "SYSTEMLINK_API_KEY"))
    if override is not None:
        return override

    try:
        from .profiles import get_active_profile

        profile = get_active_profile()
        if profile and profile.api_key:
            return ResolvedConfigValue(profile.api_key, f"profile:{profile.name}")
    except (FileNotFoundError, json.JSONDecodeError, KeyError, AttributeError):
        pass

    cfg = _get_keyring_config()
    if cfg and isinstance(cfg, dict):
        maybe = cfg.get("api_key") or cfg.get("apiKey") or cfg.get("apiToken")
        if maybe:
            return ResolvedConfigValue(str(maybe), "keyring:SYSTEMLINK_CONFIG")

    try:
        api_key = keyring.get_password("systemlink-cli", "SYSTEMLINK_API_KEY")
    except Exception:
        api_key = None
    if api_key:
        return ResolvedConfigValue(api_key, "keyring:SYSTEMLINK_API_KEY")

    if emit_error:
        click.echo(
            "\u2717 API key not found. Please set the SLCLI_API_KEY environment variable "
            "(or legacy SYSTEMLINK_API_KEY) or run 'slcli login --profile <name>'.",
            err=True,
        )
    raise click.ClickException("API key not found.")


def get_base_url() -> str:
    """Retrieve the SystemLink API base URL.

    Preference order:
    1. Environment variable SLCLI_API_URL (preferred) or SYSTEMLINK_API_URL
    2. Active profile from config file
    3. Combined keyring config (legacy)
    4. Legacy keyring entry SYSTEMLINK_API_URL
    5. Default fallback to localhost
    """
    return get_base_url_resolution().value


def get_web_url() -> str:
    """Return the SystemLink primary web UI URL.

    Preference order:
    1. Environment variable SLCLI_WEB_URL (preferred) or SYSTEMLINK_WEB_URL
    2. Active profile from config file
    3. Combined keyring config (legacy)
    4. Legacy keyring entry SYSTEMLINK_WEB_URL
    5. Derived from get_base_url()
    """
    return get_web_url_resolution().value


def _get_keyring_config() -> Dict[str, Any]:
    """Attempt to read a single JSON config entry from keyring.

    This allows storing a combined config (api_url, api_key, web_url) under
    one key (e.g. SERVICE='systemlink-cli', key='SYSTEMLINK_CONFIG'). The
    function returns a dict on success or an empty dict on failure.
    """
    try:
        cfg_text = keyring.get_password("systemlink-cli", "SYSTEMLINK_CONFIG")
        if not cfg_text:
            return {}
        import json

        parsed = json.loads(cfg_text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:
        pass
    return {}


def get_api_key() -> str:
    """Retrieve the SystemLink API key.

    Preference order:
    1. Environment variable SLCLI_API_KEY (preferred) or SYSTEMLINK_API_KEY
    2. Active profile from config file
    3. Combined keyring config (legacy)
    4. Legacy keyring entry SYSTEMLINK_API_KEY
    """
    return get_api_key_resolution().value


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

    Fetches all workspaces using pagination (max 100 per request).

    Returns:
        Dictionary mapping workspace ID to workspace name
    """
    try:
        workspace_map: Dict[str, str] = {}
        skip = 0
        page_size = 100  # API max take is 100

        while True:
            url = f"{get_base_url()}/niuser/v1/workspaces?take={page_size}&skip={skip}"
            resp = make_api_request("GET", url, payload=None, handle_errors=False)
            data = resp.json()
            workspaces = data.get("workspaces", [])

            # Add workspaces from this page to the map
            for ws in workspaces:
                if ws.get("id"):
                    workspace_map[ws.get("id")] = ws.get("name")

            # Check if we got all workspaces
            total_count = data.get("totalCount", 0)
            if skip + len(workspaces) >= total_count:
                break

            skip += page_size

        return workspace_map
    except Exception:
        return {}


# --- File I/O Utilities ---
def load_json_file(filepath: str) -> Any:
    """Load and parse JSON file with consistent error handling.

    Args:
        filepath: Path to JSON file to load

    Returns:
        Parsed JSON data (dict or list or any JSON value)

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


def save_json_file(
    data: Any, filepath: str, custom_serializer: Optional[Callable[[Any], Any]] = None
) -> None:
    """Save data to JSON file with consistent formatting and error handling.

    Args:
        data: Data to save as JSON
        filepath: Path where to save the JSON file
        custom_serializer: Optional custom JSON serializer function
    """

    def _default_json_serializer(obj: Any) -> Any:
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
    files: Optional[Dict[str, Any]] = None,
    data: Optional[Dict[str, Any]] = None,
    stream: bool = False,
) -> requests.Response:
    """Make API request with consistent error handling and configuration.

    Args:
        method: HTTP method (GET, POST, etc.)
        url: API endpoint URL
        payload: Request payload for POST/PUT requests (JSON body)
        headers: Additional headers (will be merged with default headers)
        handle_errors: Whether to handle errors with consistent formatting
        files: Files to upload (for multipart form data)
        data: Form data (for multipart requests, used with files)
        stream: Whether to stream the response (for large file downloads)

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

        # For multipart file uploads, remove Content-Type to let requests set it
        if files:
            default_headers.pop("Content-Type", None)

        ssl_verify = get_ssl_verify()

        if method.upper() == "GET":
            resp = requests.get(url, headers=default_headers, verify=ssl_verify, stream=stream)
        elif method.upper() == "POST":
            if files:
                # Multipart file upload
                resp = requests.post(
                    url,
                    headers=default_headers,
                    files=files,
                    data=data,
                    verify=ssl_verify,
                    stream=stream,
                )
            else:
                resp = requests.post(
                    url,
                    headers=default_headers,
                    json=payload,
                    verify=ssl_verify,
                    stream=stream,
                )
        elif method.upper() == "PUT":
            resp = requests.put(url, headers=default_headers, json=payload, verify=ssl_verify)
        elif method.upper() == "PATCH":
            resp = requests.patch(url, headers=default_headers, json=payload, verify=ssl_verify)
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
