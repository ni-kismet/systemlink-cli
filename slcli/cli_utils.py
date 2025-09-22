"""Common utility functions for all CLI commands."""

import sys
from typing import Any, Dict, List, Optional, Callable

import click
import requests

from .utils import ExitCodes, handle_api_error


def resolve_resource_by_name_or_id(
    session: requests.Session,
    base_url: str,
    resource_type: str,
    identifier: str,
    name_field: str = "name",
) -> Optional[Dict[str, Any]]:
    """Resolve a resource by name or ID.

    Args:
        session: Authenticated requests session
        base_url: Base API URL for the resource
        resource_type: Type of resource (for error messages)
        identifier: Name or ID to search for
        name_field: Field name to search by (default: "name")

    Returns:
        Resource data if found, None otherwise
    """
    try:
        # First try as direct ID lookup
        resp = session.get(f"{base_url}/{identifier}")
        if resp.status_code == 200:
            return resp.json()

        # If not found by ID, try name-based search
        resp = session.get(base_url)
        if resp.status_code == 200:
            data = resp.json()
            resources = data if isinstance(data, list) else data.get(resource_type, [])

            # Search by name
            for resource in resources:
                if resource.get(name_field, "").lower() == identifier.lower():
                    return resource

        # Resource not found
        click.echo(f"✗ {resource_type.title()} '{identifier}' not found", err=True)
        return None

    except Exception as exc:
        handle_api_error(exc)
        return None


def confirm_bulk_operation(
    operation: str,
    resource_type: str,
    count: int,
    force: bool = False,
) -> bool:
    """Confirm bulk operations with user prompt.

    Args:
        operation: Operation name (e.g., "delete", "update")
        resource_type: Type of resource
        count: Number of resources affected
        force: Skip confirmation if True

    Returns:
        True if confirmed, False otherwise
    """
    if force:
        return True

    if count == 0:
        click.echo(f"No {resource_type}s to {operation}")
        return False

    if count == 1:
        return click.confirm(f"Are you sure you want to {operation} this {resource_type}?")

    return click.confirm(f"Are you sure you want to {operation} {count} {resource_type}s?")


def validate_output_format(format_output: str) -> str:
    """Validate and normalize output format.

    Args:
        format_output: User-provided format string

    Returns:
        Normalized format string
    """
    valid_formats = ["table", "json"]
    normalized = format_output.lower().strip()

    if normalized not in valid_formats:
        click.echo(
            f"✗ Invalid format '{format_output}'. Valid options: {', '.join(valid_formats)}",
            err=True,
        )
        sys.exit(ExitCodes.INVALID_INPUT)

    return normalized


def handle_pagination(
    session: requests.Session,
    url: str,
    page_size: int = 100,
    max_items: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Handle paginated API responses.

    Args:
        session: Authenticated requests session
        url: API endpoint URL
        page_size: Items per page
        max_items: Maximum items to retrieve (None for all)

    Returns:
        List of all retrieved items
    """
    all_items: List[Dict[str, Any]] = []
    page = 0

    while True:
        try:
            params = {"take": page_size, "skip": page * page_size}
            resp = session.get(url, params=params)
            resp.raise_for_status()

            data = resp.json()
            items = data if isinstance(data, list) else data.get("items", [])

            if not items:
                break

            all_items.extend(items)

            # Check if we've reached max_items limit
            if max_items and len(all_items) >= max_items:
                all_items = all_items[:max_items]
                break

            # Check if we've reached the end
            if len(items) < page_size:
                break

            page += 1

        except Exception as exc:
            handle_api_error(exc)
            break

    return all_items


def extract_id_from_response(response: requests.Response) -> Optional[str]:
    """Extract ID from API response.

    Args:
        response: API response

    Returns:
        Extracted ID if found, None otherwise
    """
    try:
        data = response.json()

        # Common ID field names
        id_fields = ["id", "resourceId", "workspaceId", "templateId", "userId"]

        for field in id_fields:
            if field in data:
                return str(data[field])

        # If direct ID not found, try nested structures
        if "metadata" in data and "id" in data["metadata"]:
            return str(data["metadata"]["id"])

        return None

    except (ValueError, TypeError, KeyError):
        return None


def build_query_params(
    filters: Optional[Dict[str, Any]] = None,
    sort_by: Optional[str] = None,
    sort_order: str = "asc",
    page_size: Optional[int] = None,
    page: Optional[int] = None,
) -> Dict[str, Any]:
    """Build standardized query parameters.

    Args:
        filters: Filter dictionary
        sort_by: Field to sort by
        sort_order: Sort order ("asc" or "desc")
        page_size: Number of items per page
        page: Page number (0-based)

    Returns:
        Query parameters dictionary
    """
    params = {}

    if filters:
        for key, value in filters.items():
            if value is not None:
                params[key] = value

    if sort_by:
        params["sortBy"] = sort_by
        params["sortOrder"] = sort_order

    if page_size is not None:
        params["take"] = page_size

    if page is not None:
        params["skip"] = page * (page_size or 100)

    return params


def format_error_message(
    operation: str,
    resource_type: str,
    identifier: Optional[str] = None,
    details: Optional[str] = None,
) -> str:
    """Format standardized error messages.

    Args:
        operation: Operation that failed
        resource_type: Type of resource
        identifier: Resource identifier (optional)
        details: Additional error details (optional)

    Returns:
        Formatted error message
    """
    base_message = f"✗ Failed to {operation} {resource_type}"

    if identifier:
        base_message += f" '{identifier}'"

    if details:
        base_message += f": {details}"

    return base_message


def validate_required_fields(
    data: Dict[str, Any],
    required_fields: List[str],
    resource_type: str,
) -> bool:
    """Validate that required fields are present in data.

    Args:
        data: Data dictionary to validate
        required_fields: List of required field names
        resource_type: Type of resource (for error messages)

    Returns:
        True if all required fields present, False otherwise
    """
    missing_fields = []

    for field in required_fields:
        if field not in data or data[field] is None:
            missing_fields.append(field)

    if missing_fields:
        fields_str = ", ".join(missing_fields)
        click.echo(
            f"✗ Missing required fields for {resource_type}: {fields_str}",
            err=True,
        )
        return False

    return True


def safe_get_nested(
    data: Dict[str, Any],
    path: str,
    default: Any = None,
    separator: str = ".",
) -> Any:
    """Safely get nested dictionary values.

    Args:
        data: Dictionary to search
        path: Dot-separated path (e.g., "metadata.tags.name")
        default: Default value if path not found
        separator: Path separator character

    Returns:
        Value at path or default
    """
    try:
        keys = path.split(separator)
        value = data

        for key in keys:
            value = value[key]

        return value

    except (KeyError, TypeError, AttributeError):
        return default


def truncate_string(text: str, max_length: int = 50, suffix: str = "...") -> str:
    """Truncate string for table display.

    Args:
        text: Text to truncate
        max_length: Maximum length
        suffix: Suffix for truncated text

    Returns:
        Truncated string
    """
    if not text or len(text) <= max_length:
        return text or ""

    return text[: max_length - len(suffix)] + suffix


def paginate_list_output(
    items: List[Dict[str, Any]],
    page_size: int = 25,
    format_output: str = "table",
    formatter_func: Optional[Callable[[Dict[str, Any]], List[str]]] = None,
    headers: Optional[List[str]] = None,
    column_widths: Optional[List[int]] = None,
    empty_message: str = "No items found.",
    total_label: str = "item(s)",
) -> None:
    """Paginate list output with user prompts to continue.

    For table format, shows pages of results with user prompts.
    For JSON format, shows all results at once (no pagination).

    Args:
        items: List of items to paginate
        page_size: Number of items per page (default: 25)
        format_output: 'json' or 'table'
        formatter_func: Function to format table rows
        headers: Table headers
        column_widths: Table column widths
        empty_message: Message when no items found
        total_label: Label for count display
    """
    if not items:
        if format_output.lower() == "json":
            click.echo("[]")
        else:
            click.echo(empty_message)
        return

    # For JSON format, show all results at once (no pagination)
    if format_output.lower() == "json":
        import json

        click.echo(json.dumps(items, indent=2))
        return

    # Table format with pagination
    total_items = len(items)
    current_page = 0
    items_shown = 0

    while items_shown < total_items:
        # Calculate slice for current page
        start_idx = current_page * page_size
        end_idx = min(start_idx + page_size, total_items)
        page_items = items[start_idx:end_idx]

        # Show the page using table_utils
        if formatter_func and headers and column_widths:
            # For individual pages, don't show the total count footer
            # We'll handle that in our pagination logic
            _output_formatted_page(
                page_items,
                headers,
                column_widths,
                formatter_func,
            )
        else:
            # Fallback to simple display
            for item in page_items:
                click.echo(str(item))

        items_shown = end_idx

        # Show pagination info and prompt if there are more items
        if items_shown < total_items:
            remaining = total_items - items_shown
            click.echo(
                f"\nShowing {items_shown} of {total_items} {total_label}. "
                f"{remaining} more available."
            )

            # Check if we're in an interactive environment
            # If stdin is not a TTY or we're in a test environment, disable interactive pagination
            import os
            import sys

            is_non_interactive = (
                not sys.stdin.isatty()  # Piped input
                or not sys.stdout.isatty()  # Piped output
                or os.getenv("CI") == "true"  # CI environment
                or os.getenv("PYTEST_CURRENT_TEST") is not None  # pytest
                or os.getenv("SLCLI_NON_INTERACTIVE") == "true"  # Explicit override
            )

            if is_non_interactive:
                click.echo("Non-interactive environment detected. Showing all remaining results...")
                # Continue to show all remaining pages without prompting
                current_page += 1
                continue

            if not click.confirm("Show next 25 results?", default=True):
                break

            click.echo()  # Add blank line between pages
            current_page += 1
        else:
            # Show final count
            click.echo(f"\nTotal: {total_items} {total_label}")
            break


def _output_formatted_page(
    items: List[Dict[str, Any]],
    headers: List[str],
    column_widths: List[int],
    row_formatter_func: Callable[[Dict[str, Any]], List[str]],
) -> None:
    """Output a single page of formatted table data without footer.

    Args:
        items: List of items to output
        headers: List of header names for table output
        column_widths: List of column widths for table formatting
        row_formatter_func: Function that converts item to list of column values
    """
    if not items:
        return

    # Table format with box-drawing characters (without footer)
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
