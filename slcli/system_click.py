"""CLI commands for managing SystemLink systems.

Provides CLI commands for listing, querying, and managing systems in the
Systems Management service (nisysmgmt v1). Supports filtering by alias,
connection state, OS, installed packages, keywords, and properties.
Also provides job management and system metadata updates.
"""

import concurrent.futures
import datetime
import json
import shutil
import sys
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import quote_plus

import click
import questionary
import requests as requests_lib

from .cli_utils import validate_output_format
from .rich_output import render_table
from .system_query_utils import (
    DEFAULT_SYSTEM_JSON_FIELDS,
    DEFAULT_SYSTEM_LIST_PROJECTION,
    EXTENDED_SYSTEM_JSON_FIELDS,
    FULL_SYSTEM_LIST_PROJECTION,
    MATERIALIZED_SYSTEM_LIST_PROJECTION,
    build_materialized_system_search_filter as _build_materialized_system_search_filter,
    build_system_projection as _build_system_projection,
    get_system_query_url as _get_system_query_url,
    get_system_search_url as _get_system_search_url,
    is_system_search_endpoint_unavailable as _is_system_search_endpoint_unavailable,
    parse_system_property_filter as _parse_system_property_filter,
    quote_search_value as _quote_search_value,
)
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
from .workspace_utils import (
    get_effective_workspace,
    get_workspace_display_name,
    resolve_workspace_filter,
)


def _get_sysmgmt_base_url() -> str:
    """Get the base URL for the Systems Management API."""
    return f"{get_base_url()}/nisysmgmt/v1"


def _get_apm_base_url() -> str:
    """Get the base URL for the Asset Performance Management API."""
    return f"{get_base_url()}/niapm/v1"


def _get_alarm_base_url() -> str:
    """Get the base URL for the Alarm Management API."""
    return f"{get_base_url()}/nialarm/v1"


def _get_testmonitor_base_url() -> str:
    """Get the base URL for the Test Monitor API."""
    return f"{get_base_url()}/nitestmonitor/v2"


def _get_workitem_base_url() -> str:
    """Get the base URL for the Work Items API."""
    return f"{get_base_url()}/niworkitem/v1"


# Projection for list queries — only include fields needed for display.
# This dramatically reduces response payload size.
# Uses the dot-path ``as`` alias syntax supported by the systems API.
_DEFAULT_SYSTEM_JSON_FIELDS = DEFAULT_SYSTEM_JSON_FIELDS
_EXTENDED_SYSTEM_JSON_FIELDS = EXTENDED_SYSTEM_JSON_FIELDS
_SLIM_LIST_PROJECTION = DEFAULT_SYSTEM_LIST_PROJECTION
_LIST_PROJECTION = FULL_SYSTEM_LIST_PROJECTION
_MATERIALIZED_LIST_PROJECTION = MATERIALIZED_SYSTEM_LIST_PROJECTION


def _calculate_column_widths() -> List[int]:
    """Calculate dynamic column widths based on terminal size.

    The ID column expands to fill available terminal width.

    Returns:
        List of column widths: [alias, host, state, os, workspace, id]
    """
    # Get terminal width, default to 120 if detection fails
    try:
        terminal_width = shutil.get_terminal_size().columns
    except Exception:
        terminal_width = 120

    # Fixed widths for non-ID columns
    alias_width = 24
    host_width = 18
    state_width = 14
    os_width = 10
    workspace_width = 16

    # Account for column separators and cell padding for 6 columns.
    border_overhead = 19

    # Calculate remaining space for ID column
    fixed_columns = alias_width + host_width + state_width + os_width + workspace_width
    id_width = terminal_width - fixed_columns - border_overhead

    # Ensure minimum ID width of 20, maximum of 80
    id_width = max(20, min(80, id_width))

    return [alias_width, host_width, state_width, os_width, workspace_width, id_width]


def _calculate_job_column_widths() -> List[int]:
    """Calculate dynamic column widths for job list based on terminal size.

    The Target System column expands to fill available terminal width.

    Returns:
        List of column widths: [jid, state, created, target]
    """
    try:
        terminal_width = shutil.get_terminal_size().columns
    except Exception:
        terminal_width = 120

    # Fixed widths for non-target columns
    jid_width = 36
    state_width = 14
    created_width = 24

    # Account for column separators and cell padding for 4 columns.
    border_overhead = 13

    # Calculate remaining space for Target System column
    fixed_columns = jid_width + state_width + created_width
    target_width = terminal_width - fixed_columns - border_overhead

    # Ensure minimum target width of 20, maximum of 80
    target_width = max(20, min(80, target_width))

    return [jid_width, state_width, created_width, target_width]


def _escape_filter_value(value: str) -> str:
    """Escape double quotes in filter values to prevent injection.

    Args:
        value: Raw filter value from user input.

    Returns:
        Escaped value safe for embedding in filter expressions.
    """
    return value.replace('"', '\\"')


def _parse_properties(properties: Tuple[str, ...]) -> Dict[str, str]:
    """Parse key=value property strings into a dictionary.

    Args:
        properties: Tuple of strings in "key=value" format.

    Returns:
        Dictionary mapping property keys to values.

    Raises:
        SystemExit: If any property string is not in key=value format.
    """
    props_dict: Dict[str, str] = {}
    for prop in properties:
        if "=" not in prop:
            click.echo(
                f"✗ Invalid property format: {prop}. Use key=value",
                err=True,
            )
            sys.exit(ExitCodes.INVALID_INPUT)
        key, val = prop.split("=", 1)
        props_dict[key.strip()] = val.strip()
    return props_dict


def _build_system_filter(
    alias: Optional[str] = None,
    state: Optional[str] = None,
    os_filter: Optional[str] = None,
    host: Optional[str] = None,
    has_keyword: Optional[Tuple[str, ...]] = None,
    property_filters: Optional[Tuple[str, ...]] = None,
    workspace_id: Optional[str] = None,
    custom_filter: Optional[str] = None,
) -> Optional[str]:
    """Build API filter expression from convenience options.

    Args:
        alias: Filter by system alias (contains match).
        state: Filter by connection state.
        os_filter: Filter by OS kernel (contains match).
        host: Filter by hostname (contains match).
        has_keyword: Filter by keywords (systems must have these keywords).
        property_filters: Filter by property key=value pairs.
        workspace_id: Filter by workspace ID.
        custom_filter: Advanced user-provided filter expression.

    Returns:
        Combined filter expression string, or None if no filters.
    """
    parts: List[str] = []

    if alias:
        escaped = _escape_filter_value(alias)
        parts.append(f'alias.Contains("{escaped}")')
    if state:
        parts.append(f'connected.data.state = "{state}"')
    if os_filter:
        escaped = _escape_filter_value(os_filter)
        parts.append(f'grains.data.kernel.Contains("{escaped}")')
    if host:
        escaped = _escape_filter_value(host)
        parts.append(f'grains.data.host.Contains("{escaped}")')
    if has_keyword:
        for kw in has_keyword:
            escaped = _escape_filter_value(kw)
            parts.append(f'keywords.data.Contains("{escaped}")')
    if property_filters:
        for prop in property_filters:
            key, value = _parse_system_property_filter(prop)
            escaped_val = _escape_filter_value(value)
            parts.append(f'properties.data.{key} = "{escaped_val}"')
    if workspace_id:
        escaped = _escape_filter_value(workspace_id)
        parts.append(f'workspace = "{escaped}"')
    if custom_filter:
        parts.append(custom_filter)

    return " and ".join(parts) if parts else None


def _prefer_materialized_system_search(
    filter_query: Optional[str],
    has_package: Optional[str],
    include_fields: Tuple[str, ...],
    all_fields: bool,
) -> bool:
    """Return whether system list can safely use materialized search-systems."""
    return filter_query is None and has_package is None and not include_fields and not all_fields


def _resolve_system_json_projection(
    include_fields: Tuple[str, ...],
    all_fields: bool,
) -> Optional[str]:
    """Return the query-systems projection for an explicit extended JSON schema request."""
    normalized_fields = tuple(field_name.lower() for field_name in include_fields)
    if all_fields:
        return _LIST_PROJECTION
    if not normalized_fields:
        return None

    requested_fields = _DEFAULT_SYSTEM_JSON_FIELDS + tuple(
        field_name for field_name in _EXTENDED_SYSTEM_JSON_FIELDS if field_name in normalized_fields
    )
    return _build_system_projection(requested_fields)


def _parse_systems_response(data: Any) -> List[Dict[str, Any]]:
    """Parse the systems query API response into a flat list.

    The systems API returns a complex response that may be either:
    - A list of ``{data: {...}, count: N}`` objects (one per system), or
    - A dict with ``{data: [...], count: N}``.

    Args:
        data: Raw JSON response from the systems query API.

    Returns:
        Flat list of system dictionaries.
    """
    items: List[Dict[str, Any]] = []

    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                inner = item.get("data", item)
                if isinstance(inner, dict):
                    items.append(inner)
                elif isinstance(inner, list):
                    items.extend(inner)
    elif isinstance(data, dict):
        inner = data.get("data", [])
        if isinstance(inner, list):
            items.extend(inner)
        elif isinstance(inner, dict):
            items.append(inner)

    return items


def _flatten_materialized_system(item: Dict[str, Any]) -> Dict[str, Any]:
    """Flatten a materialized search result into the list projection shape."""
    advanced_grains = item.get("advancedGrains")
    host = ""
    kernel = ""
    if isinstance(advanced_grains, dict):
        host = str(advanced_grains.get("host") or "")
        kernel = str(advanced_grains.get("os") or "")

    flattened: Dict[str, Any] = {
        "id": item.get("id", ""),
        "alias": item.get("alias", ""),
        "workspace": item.get("workspace", ""),
        "connected": item.get("connected") or "UNKNOWN",
        "host": host,
        "kernel": kernel,
    }
    if "packages" in item:
        flattened["packages"] = item.get("packages")
    return flattened


def _parse_materialized_search_systems_response(data: Any) -> List[Dict[str, Any]]:
    """Parse search-systems response into the system list projection shape."""
    if not isinstance(data, dict):
        return []

    if "systems" not in data:
        return _parse_systems_response(data)

    systems = data.get("systems", [])
    if not isinstance(systems, list):
        return []

    return [_flatten_materialized_system(item) for item in systems if isinstance(item, dict)]


def _parse_simple_response(data: Any) -> List[Dict[str, Any]]:
    """Parse a simple query API response into a flat list.

    Expects either ``{data: [...]}`` or a bare list.

    Args:
        data: Raw JSON response.

    Returns:
        Flat list of item dictionaries.
    """
    if isinstance(data, dict):
        inner = data.get("data", [])
        if isinstance(inner, list):
            return inner
    elif isinstance(data, list):
        return data
    return []


def _query_all_items(
    url: str,
    filter_expr: Optional[str],
    order_by: Optional[str],
    response_parser: Any,
    projection: Optional[str] = None,
    take: Optional[int] = 10000,
) -> List[Dict[str, Any]]:
    """Query items using skip/take pagination.

    Generic helper that works for both systems and jobs.
    Fetches up to ``take`` items (default 10,000 for performance).

    Args:
        url: The API endpoint URL.
        filter_expr: Optional API filter expression.
        order_by: Field to order by.
        response_parser: Callable that converts raw JSON into a list of dicts.
        projection: Optional projection string for selecting fields.
        take: Maximum number of items to fetch.

    Returns:
        List of item objects (up to ``take`` count).
    """
    all_items: List[Dict[str, Any]] = []
    page_size = 100  # Use conservative batch size to avoid 500 errors
    skip = 0

    while True:
        if take is not None:
            remaining = take - len(all_items)
            if remaining <= 0:
                break
            batch_size = min(page_size, remaining)
        else:
            batch_size = page_size

        payload: Dict[str, Any] = {
            "skip": skip,
            "take": batch_size,
        }

        if filter_expr:
            payload["filter"] = filter_expr
        if order_by:
            payload["orderBy"] = order_by
        if projection:
            payload["projection"] = projection

        resp = make_api_request("POST", url, payload=payload)
        page_items = response_parser(resp.json())
        page_count = len(page_items)

        if page_count == 0:
            break

        all_items.extend(page_items)
        skip += page_count

        # Stop if we got fewer than requested (last page)
        if page_count < batch_size:
            break
        if take is not None and len(all_items) >= take:
            break

    return all_items[:take] if take is not None else all_items


def _get_materialized_search_order(
    order_by: Optional[str],
) -> Tuple[Optional[str], bool]:
    """Map CLI order-by values to materialized systems search order fields."""
    if not order_by:
        return None, False

    order_mapping: Dict[str, Tuple[str, bool]] = {
        "ALIAS": ("ALIAS", False),
        "CREATED_AT": ("CREATED_TIMESTAMP", True),
        "UPDATED_AT": ("LAST_UPDATED_TIMESTAMP", True),
    }
    return order_mapping.get(order_by.upper(), (None, False))


def _fetch_materialized_system_page(
    filter_expr: Optional[str],
    order_by: Optional[str],
    descending: bool,
    take: int,
    skip: int,
) -> List[Dict[str, Any]]:
    """Fetch a single page from materialized search-systems."""
    payload: Dict[str, Any] = {
        "skip": skip,
        "take": take,
        "projection": _MATERIALIZED_LIST_PROJECTION,
    }

    if filter_expr:
        payload["filter"] = filter_expr
    if order_by:
        payload["orderBy"] = order_by
        payload["descending"] = descending

    resp = make_api_request(
        "POST",
        _get_system_search_url(),
        payload=payload,
        handle_errors=False,
    )
    return _parse_materialized_search_systems_response(resp.json())


def _query_materialized_systems_with_fallback(
    search_filter_expr: Optional[str],
    search_order_by: Optional[str],
    search_descending: bool,
    fallback_filter_expr: Optional[str],
    fallback_order_by: Optional[str],
    take: Optional[int] = 10000,
) -> List[Dict[str, Any]]:
    """Query systems using search-systems when available, otherwise query-systems."""
    all_items: List[Dict[str, Any]] = []
    page_size = 100
    skip = 0
    use_materialized_search = True

    while True:
        if take is not None:
            remaining = take - len(all_items)
            if remaining <= 0:
                break
            batch_size = min(page_size, remaining)
        else:
            batch_size = page_size

        if use_materialized_search:
            try:
                page_items = _fetch_materialized_system_page(
                    search_filter_expr,
                    search_order_by,
                    search_descending,
                    batch_size,
                    skip,
                )
            except requests_lib.HTTPError as exc:
                if not _is_system_search_endpoint_unavailable(exc):
                    raise
                use_materialized_search = False
                page_items = _fetch_page(
                    _get_system_query_url(),
                    fallback_filter_expr,
                    fallback_order_by,
                    batch_size,
                    skip,
                    response_parser=_parse_systems_response,
                    projection=_SLIM_LIST_PROJECTION,
                )
        else:
            page_items = _fetch_page(
                _get_system_query_url(),
                fallback_filter_expr,
                fallback_order_by,
                batch_size,
                skip,
                response_parser=_parse_systems_response,
                projection=_SLIM_LIST_PROJECTION,
            )

        page_count = len(page_items)
        if page_count == 0:
            break

        all_items.extend(page_items)
        skip += page_count

        if page_count < batch_size:
            break
        if take is not None and len(all_items) >= take:
            break

    return all_items[:take] if take is not None else all_items


def _fetch_page(
    url: str,
    filter_expr: Optional[str],
    order_by: Optional[str],
    take: int,
    skip: int,
    response_parser: Any,
    projection: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Fetch a single page of items from a query API.

    Args:
        url: The API endpoint URL.
        filter_expr: Optional API filter expression.
        order_by: Field to order by.
        take: Number of items to fetch.
        skip: Number of items to skip.
        response_parser: Callable that converts raw JSON into a list of dicts.
        projection: Optional projection string.

    Returns:
        List of item objects for this page.
    """
    payload: Dict[str, Any] = {
        "skip": skip,
        "take": take,
    }

    if filter_expr:
        payload["filter"] = filter_expr
    if order_by:
        payload["orderBy"] = order_by
    if projection:
        payload["projection"] = projection

    resp = make_api_request("POST", url, payload=payload)
    return response_parser(resp.json())


def _handle_interactive_pagination(
    url: str,
    filter_expr: Optional[str],
    order_by: Optional[str],
    take: int,
    formatter_func: Any,
    headers: List[str],
    column_widths: List[int],
    empty_message: str,
    item_label: str,
    response_parser: Any,
    client_filter: Any = None,
    projection: Optional[str] = None,
) -> None:
    """Handle interactive skip/take pagination for table output.

    Generic helper that works for both systems and jobs.  The API does
    not return a total count, so we use a skip-based approach: if a page
    returns exactly ``take`` items, more may be available.

    Args:
        url: The API endpoint URL.
        filter_expr: Optional API filter expression.
        order_by: Field to order by.
        take: Number of items per page.
        formatter_func: Function to format each item for display.
        headers: Column headers for the table.
        column_widths: Column widths for the table.
        empty_message: Message to display when no items are found.
        item_label: Label for the items (e.g. "systems", "jobs").
        response_parser: Callable that converts raw JSON into a list of dicts.
        client_filter: Optional callable for client-side filtering of items.
        projection: Optional projection string.
    """
    from .table_utils import output_formatted_list

    skip = 0
    shown_count = 0
    # When using client-side filtering we fetch larger batches, but use
    # conservative size (100) to avoid HTTP 500 errors from the Systems API
    fetch_size = 100 if client_filter else take

    while True:
        page_items = _fetch_page(
            url,
            filter_expr,
            order_by,
            fetch_size,
            skip,
            response_parser=response_parser,
            projection=projection,
        )

        if not page_items:
            if shown_count == 0:
                click.echo(empty_message)
            break

        page_was_full = len(page_items) >= fetch_size

        # Client-side filtering (e.g. package name search)
        if client_filter:
            page_items = client_filter(page_items)

        if not page_items:
            skip += fetch_size
            if not page_was_full:
                # Last page from server and nothing matched
                if shown_count == 0:
                    click.echo(empty_message)
                break
            continue

        # Take only the page size worth of items for display
        display_items = page_items[:take]
        shown_count += len(display_items)
        skip += fetch_size if client_filter else len(display_items)

        output_formatted_list(
            items=display_items,
            output_format="table",
            headers=headers,
            row_formatter_func=formatter_func,
            column_widths=column_widths,
        )

        click.echo(f"\nShowing {shown_count} {item_label}")

        # Flush stdout so the table is visible before prompting
        try:
            sys.stdout.flush()
        except Exception:
            # stdout may be closed or invalid (e.g., when piped); ignore flush errors
            pass

        # If the page was full, more may be available
        if not page_was_full:
            break

        if not questionary.confirm(
            "More results may be available. Show next set?", default=True
        ).ask():
            break


def _handle_materialized_system_pagination_with_fallback(
    search_filter_expr: Optional[str],
    search_order_by: Optional[str],
    search_descending: bool,
    fallback_filter_expr: Optional[str],
    fallback_order_by: Optional[str],
    take: int,
    formatter_func: Any,
    headers: List[str],
    column_widths: List[int],
    empty_message: str,
    item_label: str,
) -> None:
    """Paginate systems using search-systems when available, with query-systems fallback."""
    from .table_utils import output_formatted_list

    skip = 0
    shown_count = 0
    use_materialized_search = True

    while True:
        if use_materialized_search:
            try:
                page_items = _fetch_materialized_system_page(
                    search_filter_expr,
                    search_order_by,
                    search_descending,
                    take,
                    skip,
                )
            except requests_lib.HTTPError as exc:
                if not _is_system_search_endpoint_unavailable(exc):
                    raise
                use_materialized_search = False
                page_items = _fetch_page(
                    _get_system_query_url(),
                    fallback_filter_expr,
                    fallback_order_by,
                    take,
                    skip,
                    response_parser=_parse_systems_response,
                    projection=_SLIM_LIST_PROJECTION,
                )
        else:
            page_items = _fetch_page(
                _get_system_query_url(),
                fallback_filter_expr,
                fallback_order_by,
                take,
                skip,
                response_parser=_parse_systems_response,
                projection=_SLIM_LIST_PROJECTION,
            )

        if not page_items:
            if shown_count == 0:
                click.echo(empty_message)
            break

        shown_count += len(page_items)
        skip += len(page_items)

        output_formatted_list(
            items=page_items,
            output_format="table",
            headers=headers,
            row_formatter_func=formatter_func,
            column_widths=column_widths,
        )

        click.echo(f"\nShowing {shown_count} {item_label}")

        try:
            sys.stdout.flush()
        except Exception:
            pass

        if len(page_items) < take:
            break

        if not questionary.confirm(
            "More results may be available. Show next set?", default=True
        ).ask():
            break


def _filter_by_package(
    systems: List[Dict[str, Any]],
    package_search: str,
) -> List[Dict[str, Any]]:
    """Filter systems by installed package name (case-insensitive contains).

    Args:
        systems: List of system objects.
        package_search: Package name to search for (case-insensitive).

    Returns:
        Filtered list of systems that have a matching package installed.
    """
    search_lower = package_search.lower()
    result: List[Dict[str, Any]] = []
    for system in systems:
        packages = system.get("packages")
        if isinstance(packages, dict):
            # Non-projected shape: packages -> {data: {...}}
            pkg_data = packages.get("data")
            if isinstance(pkg_data, dict):
                pkg_names = pkg_data
            else:
                # Projected shape: packages is the data dict directly
                pkg_names = packages
        else:
            continue
        for pkg_name in pkg_names:
            if search_lower in pkg_name.lower():
                result.append(system)
                break
    return result


def _get_system_state(system: Dict[str, Any]) -> str:
    """Extract connection state string from a system object.

    Args:
        system: System dictionary.

    Returns:
        Connection state string.
    """
    connected = system.get("connected")
    if isinstance(connected, dict):
        data = connected.get("data")
        if isinstance(data, dict):
            return data.get("state", "UNKNOWN")
    return "UNKNOWN"


def _get_system_grains(system: Dict[str, Any]) -> Dict[str, Any]:
    """Extract grains data from a system object.

    Args:
        system: System dictionary.

    Returns:
        Grains data dictionary.
    """
    grains = system.get("grains")
    if isinstance(grains, dict):
        data = grains.get("data")
        if isinstance(data, dict):
            return data
    return {}


def _format_system_detail(system: Dict[str, Any], workspace_map: Dict[str, str]) -> None:
    """Format and display detailed system information.

    Args:
        system: System dictionary.
        workspace_map: Workspace ID to name mapping.
    """
    alias = system.get("alias", "N/A")
    sys_id = system.get("id", "")
    state = _get_system_state(system)
    grains = _get_system_grains(system)

    click.echo(f"\nSystem Details")
    click.echo("──────────────────────────────────────")
    click.echo(f"  ID:            {sys_id}")
    click.echo(f"  Alias:         {alias}")
    click.echo(f"  State:         {state}")

    # Workspace
    ws_id = system.get("workspace", "")
    ws_name = get_workspace_display_name(ws_id, workspace_map)
    click.echo(f"  Workspace:     {ws_name} ({ws_id})")

    # Grains / System Info
    if grains:
        click.echo("")
        click.echo("  System Info:")
        click.echo(f"    Host:          {grains.get('host', 'N/A')}")
        kernel = grains.get("kernel", "N/A")
        osversion = grains.get("osversion", "")
        os_display = f"{kernel} ({osversion})" if osversion else kernel
        click.echo(f"    OS:            {os_display}")
        click.echo(f"    Architecture:  {grains.get('cpuarch', 'N/A')}")
        click.echo(f"    Device Class:  {grains.get('deviceclass', 'N/A')}")

    # Keywords
    keywords = system.get("keywords")
    if isinstance(keywords, dict):
        kw_data = keywords.get("data")
        if isinstance(kw_data, list) and kw_data:
            click.echo(f"\n  Keywords:        {', '.join(str(k) for k in kw_data)}")

    # Properties
    properties = system.get("properties")
    if isinstance(properties, dict):
        prop_data = properties.get("data")
        if isinstance(prop_data, dict) and prop_data:
            click.echo("\n  Properties:")
            for key, value in prop_data.items():
                click.echo(f"    {key}: {value}")

    # Timestamps
    click.echo("")
    click.echo("  Timestamps:")
    click.echo(f"    Created:       {system.get('createdTimestamp', 'N/A')}")
    click.echo(f"    Last Updated:  {system.get('lastUpdatedTimestamp', 'N/A')}")
    connected = system.get("connected")
    if isinstance(connected, dict):
        click.echo(f"    Last Present:  {connected.get('lastPresentTimestamp', 'N/A')}")


def _format_packages_table(system: Dict[str, Any]) -> None:
    """Display installed packages in a formatted table.

    Args:
        system: System dictionary.
    """
    packages = system.get("packages")
    if not isinstance(packages, dict):
        click.echo("\n  No package information available.")
        return

    pkg_data = packages.get("data")
    if not isinstance(pkg_data, dict) or not pkg_data:
        click.echo("\n  No packages installed.")
        return

    pkg_list: List[Dict[str, str]] = []
    for pkg_name, pkg_info in sorted(pkg_data.items()):
        if isinstance(pkg_info, dict):
            display_name = pkg_info.get("displayname") or pkg_name
            display_ver = pkg_info.get("displayversion") or pkg_info.get("version") or ""
            group = pkg_info.get("group") or ""
            pkg_list.append(
                {
                    "name": str(display_name),
                    "version": str(display_ver),
                    "group": str(group),
                }
            )
        else:
            pkg_list.append({"name": pkg_name, "version": str(pkg_info), "group": ""})

    click.echo(f"\n  Installed Packages ({len(pkg_list)}):")

    def pkg_formatter(item: Dict[str, Any]) -> List[str]:
        return [
            item.get("name", ""),
            item.get("version", ""),
            item.get("group", ""),
        ]

    mock_resp: Any = FilteredResponse({"packages": pkg_list})
    UniversalResponseHandler.handle_list_response(
        resp=mock_resp,
        data_key="packages",
        item_name="package",
        format_output="table",
        formatter_func=pkg_formatter,
        headers=["Package", "Version", "Group"],
        column_widths=[36, 16, 20],
        empty_message="  No packages installed.",
        enable_pagination=False,
    )


def _format_feeds_table(system: Dict[str, Any]) -> None:
    """Display configured feeds in a formatted table.

    Args:
        system: System dictionary.
    """
    feeds = system.get("feeds")
    if not isinstance(feeds, dict):
        click.echo("\n  No feed information available.")
        return

    feed_data = feeds.get("data")
    if not isinstance(feed_data, dict) or not feed_data:
        click.echo("\n  No feeds configured.")
        return

    feed_list: List[Dict[str, str]] = []
    for feed_url, feed_configs in feed_data.items():
        if isinstance(feed_configs, list):
            for cfg in feed_configs:
                if isinstance(cfg, dict):
                    feed_list.append(
                        {
                            "name": str(cfg.get("name") or ""),
                            "enabled": str(cfg.get("enabled", "")),
                            "uri": str(cfg.get("uri") or feed_url),
                        }
                    )
        else:
            feed_list.append({"name": "", "enabled": "", "uri": feed_url})

    click.echo(f"\n  Configured Feeds ({len(feed_list)}):")

    def feed_formatter(item: Dict[str, Any]) -> List[str]:
        return [
            item.get("name", ""),
            item.get("enabled", ""),
            item.get("uri", ""),
        ]

    mock_resp: Any = FilteredResponse({"feeds": feed_list})
    UniversalResponseHandler.handle_list_response(
        resp=mock_resp,
        data_key="feeds",
        item_name="feed",
        format_output="table",
        formatter_func=feed_formatter,
        headers=["Name", "Enabled", "URI"],
        column_widths=[30, 8, 50],
        empty_message="  No feeds configured.",
        enable_pagination=False,
    )


# ------------------------------------------------------------------
# Related-resource fetch helpers
# ------------------------------------------------------------------


def _fetch_assets_for_system(system_id: str, take: int) -> Tuple[List[Dict[str, Any]], int]:
    """Fetch assets associated with a system.

    Args:
        system_id: System minion ID.
        take: Maximum number of assets to return.

    Returns:
        Tuple of (list of assets, total count).
    """
    escaped = _escape_filter_value(system_id)
    payload: Dict[str, Any] = {
        "filter": f'location.minionId = "{escaped}"',
        "take": take,
        "returnCount": True,
        "projection": (
            "new(id,name,modelName,modelNumber,vendorName,vendorNumber,serialNumber,"
            "workspace,properties,keywords,location.minionId,location.parent,"
            "location.slotNumber,"
            "location.physicalLocation,location.state.assetPresence,"
            "location.state.systemConnection,discoveryType,supportsSelfTest,"
            "supportsSelfCalibration,supportsReset,supportsExternalCalibration,"
            "scanCode,temperatureSensors.reading,externalCalibration.resolvedDueDate,"
            "selfCalibration.date)"
        ),
    }
    resp = make_api_request("POST", f"{_get_apm_base_url()}/query-assets", payload=payload)
    data = resp.json()
    assets = data.get("assets", []) if isinstance(data, dict) else []
    total = (data.get("totalCount") or len(assets)) if isinstance(data, dict) else len(assets)
    return assets, total


def _fetch_alarms_for_system(system_id: str, take: int) -> Tuple[List[Dict[str, Any]], int]:
    """Fetch active alarm instances for a system.

    Args:
        system_id: System minion ID.
        take: Maximum number of alarm instances to return.

    Returns:
        Tuple of (list of alarm instances, total count).
    """
    escaped = _escape_filter_value(system_id)
    payload: Dict[str, Any] = {
        "filter": f'properties.minionId == "{escaped}"',
        "take": take,
    }
    resp = make_api_request(
        "POST",
        f"{_get_alarm_base_url()}/query-instances-with-filter",
        payload=payload,
    )
    data = resp.json()
    alarms = data.get("alarmInstances", []) if isinstance(data, dict) else []
    total = (data.get("totalCount") or len(alarms)) if isinstance(data, dict) else len(alarms)
    return alarms, total


def _fetch_recent_jobs_for_system(system_id: str, take: int) -> Tuple[List[Dict[str, Any]], int]:
    """Fetch recent jobs for a system.

    Args:
        system_id: System minion ID.
        take: Maximum number of jobs to return.

    Returns:
        Tuple of (list of jobs, total count).
    """
    escaped = _escape_filter_value(system_id)
    payload: Dict[str, Any] = {
        "filter": f'id = "{escaped}"',
        "orderBy": "state descending, lastUpdatedTimestamp descending",
        "take": take,
    }
    resp = make_api_request(
        "POST",
        f"{_get_sysmgmt_base_url()}/query-jobs",
        payload=payload,
    )
    data = resp.json()
    jobs_list = data.get("jobs", []) if isinstance(data, dict) else []
    total = (data.get("totalCount") or len(jobs_list)) if isinstance(data, dict) else len(jobs_list)
    return jobs_list, total


def _fetch_results_for_system(system_id: str, take: int) -> Tuple[List[Dict[str, Any]], int]:
    """Fetch recent test results for a system.

    Args:
        system_id: System minion ID.
        take: Maximum number of results to return.

    Returns:
        Tuple of (list of results, total count).
    """
    escaped = _escape_filter_value(system_id)
    payload: Dict[str, Any] = {
        "productFilter": "",
        "filter": f'(systemId == "{escaped}")',
        "projection": [
            "ID",
            "PART_NUMBER",
            "PROGRAM_NAME",
            "PROPERTIES",
            "SERIAL_NUMBER",
            "STARTED_AT",
            "STATUS",
            "SYSTEM_ID",
            "TOTAL_TIME_IN_SECONDS",
            "WORKSPACE",
        ],
        "orderBy": "STARTED_AT",
        "descending": True,
        "orderByComparisonType": "DEFAULT",
        "take": take,
    }
    resp = make_api_request(
        "POST",
        f"{_get_testmonitor_base_url()}/query-results",
        payload=payload,
    )
    data = resp.json()
    results = data.get("results", []) if isinstance(data, dict) else []
    total = (data.get("totalCount") or len(results)) if isinstance(data, dict) else len(results)
    return results, total


def _fetch_workitems_for_system(
    system_id: str, take: int, days: int
) -> Tuple[List[Dict[str, Any]], int]:
    """Fetch upcoming/recent work items (test plan instances) scheduled for a system.

    Queries work items where the system is a scheduled resource within a window
    of ``days`` days before/after today (i.e. a centred ±days window).

    Args:
        system_id: System minion ID.
        take: Maximum number of work items to return.
        days: Half-width of the time window in days (centre = now).

    Returns:
        Tuple of (list of work items, total count).
    """
    now = datetime.datetime.now(datetime.timezone.utc)
    start = (now - datetime.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    end = (now + datetime.timedelta(days=days)).strftime("%Y-%m-%dT%H:%M:%S.000Z")
    escaped = _escape_filter_value(system_id)
    filter_expr = (
        '((!(schedule.plannedStartDateTime = null || schedule.plannedStartDateTime = "") && '
        '!(schedule.plannedEndDateTime = null || schedule.plannedEndDateTime = "") && '
        f'DateTime(schedule.plannedStartDateTime) < DateTime.parse("{end}") && '
        f'DateTime(schedule.plannedEndDateTime) > DateTime.parse("{start}")) && '
        f'resources.systems.selections.Any(s => s.id == "{escaped}")) && type == "testplan"'
    )
    payload: Dict[str, Any] = {
        "filter": filter_expr,
        "orderBy": "UPDATED_AT",
        "descending": True,
        "take": take,
    }
    url = (
        f"{_get_workitem_base_url()}/query-workitems"
        "?ff-userdefinedworkflowsfortestplaninstances=true"
    )
    resp = make_api_request("POST", url, payload=payload)
    data = resp.json()
    if isinstance(data, dict):
        workitems: List[Dict[str, Any]] = list(data.get("workItems") or data.get("workitems") or [])
        total: int = int(data.get("totalCount") or len(workitems))
    else:
        workitems = []
        total = 0
    return workitems, total


# ------------------------------------------------------------------
# Related-resource format section helpers
# ------------------------------------------------------------------


def _format_assets_section(assets: List[Dict[str, Any]], total: int, take: int) -> None:
    """Display an assets section in the system detail view.

    Args:
        assets: List of asset records.
        total: Total count from the API (may exceed len(assets) if take < total).
        take: Requested limit (used to build the "showing N of M" suffix).
    """
    showing = len(assets)
    suffix = f" (showing {showing} of {total})" if total > showing else ""
    click.echo(f"\n  Assets ({total}){suffix}:")

    def fmt(item: Dict[str, Any]) -> List[str]:
        return [
            item.get("name", ""),
            str(item.get("assetType", "")),
            item.get("modelName", ""),
            item.get("serialNumber", ""),
            item.get("busType", ""),
        ]

    mock: Any = FilteredResponse({"assets": assets})
    UniversalResponseHandler.handle_list_response(
        resp=mock,
        data_key="assets",
        item_name="asset",
        format_output="table",
        formatter_func=fmt,
        headers=["Name", "Type", "Model", "Serial", "Bus"],
        column_widths=[30, 16, 24, 16, 12],
        empty_message="  No assets.",
        enable_pagination=False,
    )


def _format_alarms_section(alarms: List[Dict[str, Any]], total: int, take: int) -> None:
    """Display an active alarms section in the system detail view.

    Args:
        alarms: List of alarm instance records.
        total: Total count from the API.
        take: Requested limit.
    """
    showing = len(alarms)
    suffix = f" (showing {showing} of {total})" if total > showing else ""
    click.echo(f"\n  Active Alarms ({total}){suffix}:")

    def fmt(item: Dict[str, Any]) -> List[str]:
        rule = item.get("alarmRule") or {}
        return [
            rule.get("displayName", item.get("channel", "")),
            str(item.get("severity", "")),
            item.get("channel", ""),
            item.get("setAt", item.get("createdAt", "")),
        ]

    mock: Any = FilteredResponse({"alarms": alarms})
    UniversalResponseHandler.handle_list_response(
        resp=mock,
        data_key="alarms",
        item_name="alarm",
        format_output="table",
        formatter_func=fmt,
        headers=["Name", "Severity", "Channel", "Set At"],
        column_widths=[32, 10, 28, 28],
        empty_message="  No active alarms.",
        enable_pagination=False,
    )


def _format_jobs_section(jobs: List[Dict[str, Any]], total: int, take: int) -> None:
    """Display a recent jobs section in the system detail view.

    Args:
        jobs: List of job records.
        total: Total count from the API.
        take: Requested limit.
    """
    showing = len(jobs)
    suffix = f" (showing {showing} of {total})" if total > showing else ""
    click.echo(f"\n  Recent Jobs ({total}){suffix}:")

    def fmt(item: Dict[str, Any]) -> List[str]:
        fields = _get_job_display_fields(item)
        return [fields["jid"], fields["state"], fields["created"]]

    mock: Any = FilteredResponse({"jobs": jobs})
    UniversalResponseHandler.handle_list_response(
        resp=mock,
        data_key="jobs",
        item_name="job",
        format_output="table",
        formatter_func=fmt,
        headers=["Job ID", "State", "Created"],
        column_widths=[36, 14, 28],
        empty_message="  No jobs found.",
        enable_pagination=False,
    )


def _format_results_section(results: List[Dict[str, Any]], total: int, take: int) -> None:
    """Display a recent test results section in the system detail view.

    Args:
        results: List of test result records.
        total: Total count from the API.
        take: Requested limit.
    """
    showing = len(results)
    suffix = f" (showing {showing} of {total})" if total > showing else ""
    click.echo(f"\n  Test Results ({total}){suffix}:")

    def fmt(item: Dict[str, Any]) -> List[str]:
        status_obj = item.get("status") or {}
        if isinstance(status_obj, dict):
            status = status_obj.get("statusType", str(status_obj))
        else:
            status = str(status_obj)
        return [
            item.get("programName", ""),
            status,
            item.get("startedAt", item.get("startedWithApiAt", "")),
        ]

    mock: Any = FilteredResponse({"results": results})
    UniversalResponseHandler.handle_list_response(
        resp=mock,
        data_key="results",
        item_name="result",
        format_output="table",
        formatter_func=fmt,
        headers=["Program", "Status", "Started"],
        column_widths=[36, 12, 28],
        empty_message="  No test results found.",
        enable_pagination=False,
    )


def _format_workitems_section(
    workitems: List[Dict[str, Any]], total: int, take: int, days: int
) -> None:
    """Display scheduled work items (test plans) for a system.

    Args:
        workitems: List of work item records.
        total: Total count from the API.
        take: Requested limit.
        days: The time-window half-width used in the query (for display).
    """
    showing = len(workitems)
    suffix = f" (showing {showing} of {total})" if total > showing else ""
    click.echo(f"\n  Scheduled Work Items \u00b1{days}d ({total}){suffix}:")

    def fmt(item: Dict[str, Any]) -> List[str]:
        schedule = item.get("schedule") or {}
        return [
            item.get("name", ""),
            item.get("state", ""),
            schedule.get("plannedStartDateTime", ""),
            schedule.get("plannedEndDateTime", ""),
        ]

    mock: Any = FilteredResponse({"workItems": workitems})
    UniversalResponseHandler.handle_list_response(
        resp=mock,
        data_key="workItems",
        item_name="work item",
        format_output="table",
        formatter_func=fmt,
        headers=["Name", "State", "Planned Start", "Planned End"],
        column_widths=[36, 14, 28, 28],
        empty_message="  No work items scheduled.",
        enable_pagination=False,
    )


# ------------------------------------------------------------------
# Job helpers
# ------------------------------------------------------------------


def _build_job_filter(
    system_id: Optional[str] = None,
    state: Optional[str] = None,
    function: Optional[str] = None,
    custom_filter: Optional[str] = None,
) -> Optional[str]:
    """Build API filter expression for job queries.

    Args:
        system_id: Filter by target system ID.
        state: Filter by job state.
        function: Filter by salt function name.
        custom_filter: Advanced user-provided filter expression.

    Returns:
        Combined filter expression string, or None if no filters.
    """
    parts: List[str] = []

    if system_id:
        escaped = _escape_filter_value(system_id)
        parts.append(f'id = "{escaped}"')
    if state:
        parts.append(f'state = "{state}"')
    if function:
        escaped = _escape_filter_value(function)
        parts.append(f'config.fun.Contains("{escaped}")')
    if custom_filter:
        parts.append(custom_filter)

    return " and ".join(parts) if parts else None


def _get_job_display_fields(job: Dict[str, Any]) -> Dict[str, str]:
    """Extract display fields from a job object.

    Args:
        job: Job dictionary.

    Returns:
        Dictionary with formatted display fields.
    """
    config = job.get("config") or {}
    result = job.get("result") or {}
    targets = config.get("tgt", [])
    functions = config.get("fun", [])

    return {
        "jid": job.get("jid", ""),
        "state": job.get("state", ""),
        "created": job.get("createdTimestamp", ""),
        "target": targets[0] if targets else job.get("id", ""),
        "functions": ", ".join(functions) if functions else "",
        "success": str(result.get("success", "")),
    }


# ==================================================================
# Command registration
# ==================================================================


def _resolve_system(identifier: str) -> Dict[str, Any]:
    """Resolve a system by ID or alias.

    First attempts a direct ID lookup. If that fails, queries by alias.

    Args:
        identifier: System minion ID or alias.

    Returns:
        System data dictionary.

    Raises:
        SystemExit: If the system cannot be found or an API error occurs.
    """
    # Try direct ID lookup first
    try:
        encoded_identifier = quote_plus(identifier)
        url = f"{_get_sysmgmt_base_url()}/systems?id={encoded_identifier}"
        resp = make_api_request("GET", url, handle_errors=False)
        resp.raise_for_status()
        data = resp.json()
        if isinstance(data, list) and data:
            return data[0]
        if isinstance(data, dict) and data.get("id"):
            return data
    except requests_lib.HTTPError as exc:
        if exc.response is not None and exc.response.status_code == 404:
            pass
        else:
            handle_api_error(exc)
    except requests_lib.RequestException as exc:
        handle_api_error(exc)

    # Fall back to alias search
    try:
        systems: List[Dict[str, Any]]
        try:
            systems = _fetch_materialized_system_page(
                f"alias:{_quote_search_value(identifier)}",
                None,
                False,
                2,
                0,
            )
            systems = [system for system in systems if system.get("id")]
            if len(systems) == 1:
                return _resolve_system(str(systems[0]["id"]))
            if len(systems) > 1:
                click.echo(
                    f"✗ Multiple systems match alias '{identifier}'. Use the system ID instead.",
                    err=True,
                )
                sys.exit(ExitCodes.INVALID_INPUT)
        except requests_lib.HTTPError as exc:
            if not _is_system_search_endpoint_unavailable(exc):
                raise
        escaped = _escape_filter_value(identifier)
        payload: Dict[str, Any] = {
            "filter": f'alias = "{escaped}"',
            "take": 2,
        }
        resp = make_api_request("POST", _get_system_query_url(), payload=payload)
        systems = _parse_systems_response(resp.json())

        if len(systems) == 1:
            return systems[0]
        if len(systems) > 1:
            click.echo(
                f"✗ Multiple systems match alias '{identifier}'. Use the system ID instead.",
                err=True,
            )
            sys.exit(ExitCodes.INVALID_INPUT)
    except SystemExit:
        raise
    except Exception as exc:  # noqa: BLE001
        handle_api_error(exc)

    click.echo(f"✗ System not found: {identifier}", err=True)
    sys.exit(ExitCodes.NOT_FOUND)


def _get_packages(system: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Extract the packages dictionary from a system record.

    Args:
        system: System data dictionary.

    Returns:
        Mapping of package name to package info.
    """
    packages = system.get("packages")
    if isinstance(packages, dict):
        pkg_data = packages.get("data")
        if isinstance(pkg_data, dict):
            return pkg_data
    return {}


def _compare_packages(
    pkgs_a: Dict[str, Dict[str, Any]],
    pkgs_b: Dict[str, Dict[str, Any]],
    alias_a: str,
    alias_b: str,
    format_output: str,
) -> Dict[str, Any]:
    """Compare software packages between two systems.

    Args:
        pkgs_a: Packages from system A.
        pkgs_b: Packages from system B.
        alias_a: Display name for system A.
        alias_b: Display name for system B.
        format_output: Output format (table or json).

    Returns:
        Comparison result dictionary for JSON output.
    """
    all_keys = sorted(set(pkgs_a.keys()) | set(pkgs_b.keys()))
    only_a: List[str] = []
    only_b: List[str] = []
    version_diffs: List[Dict[str, str]] = []
    matching: List[str] = []

    def _normalize_package_entry(entry: Any, key: str) -> Dict[str, str]:
        """Normalize a package entry to a dict shape for safe comparison."""
        if isinstance(entry, dict):
            displayname = entry.get("displayname") or key
            version = entry.get("version") or ""
            displayversion = entry.get("displayversion") or ""
            return {
                "displayname": str(displayname),
                "version": str(version),
                "displayversion": str(displayversion),
            }

        if isinstance(entry, str):
            return {
                "displayname": key,
                "version": entry,
                "displayversion": entry,
            }

        if entry is None:
            normalized_value = ""
        else:
            normalized_value = str(entry)

        return {
            "displayname": key,
            "version": normalized_value,
            "displayversion": normalized_value,
        }

    for key in all_keys:
        in_a = key in pkgs_a
        in_b = key in pkgs_b
        if in_a and not in_b:
            only_a.append(key)
        elif in_b and not in_a:
            only_b.append(key)
        else:
            pkg_a = _normalize_package_entry(pkgs_a[key], key)
            pkg_b = _normalize_package_entry(pkgs_b[key], key)
            ver_a = pkg_a.get("version") or pkg_a.get("displayversion") or ""
            ver_b = pkg_b.get("version") or pkg_b.get("displayversion") or ""
            if ver_a != ver_b:
                name = pkg_a.get("displayname") or pkg_b.get("displayname") or key
                version_diffs.append({"package": name, "version_a": ver_a, "version_b": ver_b})
            else:
                matching.append(key)

    result: Dict[str, Any] = {
        "only_system_a": only_a,
        "only_system_b": only_b,
        "version_differences": version_diffs,
        "matching_count": len(matching),
    }

    if format_output.lower() != "json":
        click.echo("\n  Software Comparison")
        click.echo("  " + "─" * 60)

        if not only_a and not only_b and not version_diffs:
            click.echo("  ✓ Software is identical across both systems.")
        else:
            if only_a:
                click.echo(f"\n  Only on {alias_a}:")
                for key in only_a:
                    pkg_a = _normalize_package_entry(pkgs_a[key], key)
                    name = pkg_a.get("displayname") or key
                    ver = pkg_a.get("displayversion") or pkg_a.get("version") or ""
                    click.echo(f"    + {name}  ({ver})" if ver else f"    + {name}")

            if only_b:
                click.echo(f"\n  Only on {alias_b}:")
                for key in only_b:
                    pkg_b = _normalize_package_entry(pkgs_b[key], key)
                    name = pkg_b.get("displayname") or key
                    ver = pkg_b.get("displayversion") or pkg_b.get("version") or ""
                    click.echo(f"    + {name}  ({ver})" if ver else f"    + {name}")

            if version_diffs:
                click.echo("\n  Version Differences:")
                for diff in version_diffs:
                    ver_a = diff["version_a"]
                    ver_b = diff["version_b"]
                    # Determine which version is newer
                    try:
                        from packaging.version import Version

                        newer_is_a = Version(ver_a) > Version(ver_b)
                    except Exception:
                        newer_is_a = ver_a > ver_b
                    if newer_is_a:
                        mark_a, mark_b = "+", "-"
                    else:
                        mark_a, mark_b = "-", "+"
                    click.echo(f"    {diff['package']}:")
                    click.echo(f"      {mark_a} {alias_a}: {ver_a}")
                    click.echo(f"      {mark_b} {alias_b}: {ver_b}")

        click.echo(
            f"\n  Summary: {len(matching)} matching, "
            f"{len(only_a)} only on {alias_a}, "
            f"{len(only_b)} only on {alias_b}, "
            f"{len(version_diffs)} version differences"
        )

    return result


def _compare_assets(
    assets_a: List[Dict[str, Any]],
    assets_b: List[Dict[str, Any]],
    alias_a: str,
    alias_b: str,
    format_output: str,
) -> Dict[str, Any]:
    """Compare assets connected to two systems.

    Assets are considered equivalent if they share the same model and vendor.
    A mismatch in the set of (model, vendor) pairs is listed under only_system_a
    or only_system_b.  Matching assets in different slots are listed under
    slot_differences.

    Args:
        assets_a: Assets connected to system A.
        assets_b: Assets connected to system B.
        alias_a: Display name for system A.
        alias_b: Display name for system B.
        format_output: Output format (table or json).

    Returns:
        Comparison result dictionary for JSON output.
    """

    def _asset_identity(asset: Dict[str, Any]) -> Tuple[str, str]:
        return (asset.get("modelName") or "", asset.get("vendorName") or "")

    def _asset_slot(asset: Dict[str, Any]) -> str:
        loc = asset.get("location")
        if isinstance(loc, dict):
            slot = loc.get("slotNumber")
            if slot is not None:
                return str(slot)
        return ""

    # Group assets by (model, vendor) identity
    groups_a: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for a in assets_a:
        groups_a.setdefault(_asset_identity(a), []).append(a)

    groups_b: Dict[Tuple[str, str], List[Dict[str, Any]]] = {}
    for b in assets_b:
        groups_b.setdefault(_asset_identity(b), []).append(b)

    all_identities = sorted(set(groups_a.keys()) | set(groups_b.keys()))

    only_a: List[Dict[str, Any]] = []
    only_b: List[Dict[str, Any]] = []
    count_mismatches: List[Dict[str, Any]] = []
    slot_diffs: List[Dict[str, Any]] = []
    matching: List[Dict[str, str]] = []

    def _asset_slot_sort_key(asset: Dict[str, Any]) -> Tuple[int, int, str, str]:
        """Build a deterministic sort key that compares numeric slot values numerically."""
        slot = _asset_slot(asset).strip()
        if slot.isdigit():
            return (0, int(slot), "", "")

        stable_fallback = json.dumps(asset, sort_keys=True, default=str)
        return (1, sys.maxsize, slot, stable_fallback)

    for identity in all_identities:
        model, vendor = identity
        in_a = groups_a.get(identity, [])
        in_b = groups_b.get(identity, [])

        count_a = len(in_a)
        count_b = len(in_b)

        if count_a and not count_b:
            only_a.append({"model": model, "vendor": vendor, "count": count_a})
        elif count_b and not count_a:
            only_b.append({"model": model, "vendor": vendor, "count": count_b})
        elif count_a != count_b:
            count_mismatches.append(
                {
                    "model": model,
                    "vendor": vendor,
                    "count_system_a": count_a,
                    "count_system_b": count_b,
                }
            )
        else:
            # Same count — compare slots pairwise (sorted by numeric slot when possible)
            sorted_a = sorted(in_a, key=_asset_slot_sort_key)
            sorted_b = sorted(in_b, key=_asset_slot_sort_key)
            all_match = True
            for a_item, b_item in zip(sorted_a, sorted_b):
                slot_a = _asset_slot(a_item)
                slot_b = _asset_slot(b_item)
                if slot_a != slot_b:
                    all_match = False
                    slot_diffs.append(
                        {
                            "model": model,
                            "vendor": vendor,
                            "slot_a": slot_a,
                            "slot_b": slot_b,
                        }
                    )
            if all_match:
                matching.append({"model": model, "vendor": vendor})

    result: Dict[str, Any] = {
        "only_system_a": only_a,
        "only_system_b": only_b,
        "count_mismatches": count_mismatches,
        "slot_differences": slot_diffs,
        "matching_count": len(matching),
    }

    if format_output.lower() != "json":
        click.echo("\n  Asset Comparison")
        click.echo("  " + "─" * 60)

        has_diffs = only_a or only_b or count_mismatches or slot_diffs
        if not has_diffs:
            click.echo("  ✓ Assets are identical across both systems.")
        else:
            if only_a:
                click.echo(f"\n  Only on {alias_a}:")
                for item in only_a:
                    label = (
                        f"{item['model']} ({item['vendor']})"
                        if item["vendor"]
                        else item["model"] or "(unknown)"
                    )
                    suffix = f"  x{item['count']}" if item["count"] > 1 else ""
                    click.echo(f"    + {label}{suffix}")

            if only_b:
                click.echo(f"\n  Only on {alias_b}:")
                for item in only_b:
                    label = (
                        f"{item['model']} ({item['vendor']})"
                        if item["vendor"]
                        else item["model"] or "(unknown)"
                    )
                    suffix = f"  x{item['count']}" if item["count"] > 1 else ""
                    click.echo(f"    + {label}{suffix}")

            if count_mismatches:
                click.echo("\n  Count Mismatches:")
                for item in count_mismatches:
                    label = (
                        f"{item['model']} ({item['vendor']})"
                        if item["vendor"]
                        else item["model"] or "(unknown)"
                    )
                    click.echo(f"    {label}:")
                    click.echo(f"      {alias_a}: {item['count_system_a']} installed")
                    click.echo(f"      {alias_b}: {item['count_system_b']} installed")

            if slot_diffs:
                click.echo("\n  Slot Differences:")
                for item in slot_diffs:
                    label = (
                        f"{item['model']} ({item['vendor']})"
                        if item["vendor"]
                        else item["model"] or "(unknown)"
                    )
                    click.echo(f"    {label}:")
                    click.echo(f"      {alias_a}: slot {item['slot_a'] or '(none)'}")
                    click.echo(f"      {alias_b}: slot {item['slot_b'] or '(none)'}")

        click.echo(
            f"\n  Summary: {len(matching)} matching, "
            f"{len(only_a)} only on {alias_a}, "
            f"{len(only_b)} only on {alias_b}, "
            f"{len(count_mismatches)} count mismatches, "
            f"{len(slot_diffs)} slot differences"
        )

    return result


def register_system_commands(cli: Any) -> None:
    """Register the 'system' command group and its subcommands.

    Args:
        cli: Click CLI group to register commands on.
    """

    @cli.group()
    def system() -> None:
        """Manage SystemLink systems.

        Query, inspect, and manage systems registered with the Systems
        Management service. Supports filtering by alias, connection state,
        OS, hostname, keywords, and installed packages.

        Filter syntax uses the Systems Management filter language:
          alias.Contains("PXI"), connected.data.state = "CONNECTED",
          grains.data.kernel = "Windows", and/or operators.
        """

    # ------------------------------------------------------------------
    # Phase 1: list, get, summary
    # ------------------------------------------------------------------

    @system.command(name="list")
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    @click.option(
        "--take",
        "-t",
        type=int,
        default=100,
        show_default=True,
        help=(
            "Number of items per page for table output; maximum number of items "
            "to return for JSON"
        ),
    )
    @click.option("--alias", "-a", help="Filter by system alias (contains match)")
    @click.option(
        "--state",
        "-s",
        type=click.Choice(
            [
                "CONNECTED",
                "DISCONNECTED",
                "VIRTUAL",
                "APPROVED",
                "CONNECTED_REFRESH_PENDING",
                "CONNECTED_REFRESH_FAILED",
                "ACTIVATED_WITHOUT_CONNECTION",
            ],
            case_sensitive=True,
        ),
        help="Filter by connection state",
    )
    @click.option("--os", "os_filter", help="Filter by OS (kernel contains match)")
    @click.option("--host", help="Filter by hostname (contains match)")
    @click.option(
        "--has-package",
        help="Filter for systems with specified package installed (contains match)",
    )
    @click.option(
        "--has-keyword",
        multiple=True,
        help="Filter systems that have this keyword (repeatable)",
    )
    @click.option(
        "--property",
        "property_filters",
        multiple=True,
        help="Filter by property key=value (repeatable)",
    )
    @click.option("--workspace", "-w", help="Filter by workspace name or ID")
    @click.option(
        "--filter",
        "filter_query",
        help=("Advanced API filter expression " "(e.g., 'connected.data.state = \"CONNECTED\"')"),
    )
    @click.option(
        "--order-by",
        type=click.Choice(
            ["ALIAS", "CREATED_AT", "UPDATED_AT"],
            case_sensitive=False,
        ),
        help="Order by field",
    )
    @click.option(
        "--field",
        "include_fields",
        multiple=True,
        type=click.Choice(list(_EXTENDED_SYSTEM_JSON_FIELDS), case_sensitive=False),
        help=(
            "Add extended fields to JSON output. " "Forces the legacy query path for the request."
        ),
    )
    @click.option(
        "--all-fields",
        is_flag=True,
        help=(
            "Return the full legacy system list JSON schema. "
            "Forces the legacy query path for the request."
        ),
    )
    def list_systems(
        format: str,
        take: int,
        alias: Optional[str],
        state: Optional[str],
        os_filter: Optional[str],
        host: Optional[str],
        has_package: Optional[str],
        has_keyword: Tuple[str, ...],
        property_filters: Tuple[str, ...],
        workspace: Optional[str],
        filter_query: Optional[str],
        order_by: Optional[str],
        include_fields: Tuple[str, ...],
        all_fields: bool,
    ) -> None:
        """List and query systems with optional filtering.

        Supports convenience filters (--alias, --state, --os, --host,
        --has-keyword, --property) that are translated to API filter
        expressions.  Combine multiple options — they are joined with 'and'.

        Use --has-package for client-side package filtering (contains match).

        JSON output uses a slim schema by default for performance. Use
        --field to add specific extended fields, or --all-fields to
        request the full legacy list schema.

        For advanced queries use --filter with the Systems Management filter
        syntax: connected.data.state = "CONNECTED" and grains.data.kernel = "Windows"
        """
        format_output = validate_output_format(format)

        if all_fields and include_fields:
            click.echo("✗ Use either --field or --all-fields, not both.", err=True)
            sys.exit(ExitCodes.INVALID_INPUT)
        if format_output.lower() != "json" and (include_fields or all_fields):
            click.echo(
                "✗ --field and --all-fields are only supported with --format json.",
                err=True,
            )
            sys.exit(ExitCodes.INVALID_INPUT)

        try:
            # Resolve workspace if provided
            workspace_id: Optional[str] = None
            try:
                workspace_map = get_workspace_map()
            except Exception:
                workspace_map = {}

            workspace = get_effective_workspace(workspace)
            if workspace:
                workspace_id = resolve_workspace_filter(workspace, workspace_map)

            # Map order-by choices to API field names
            order_by_map: Dict[str, str] = {
                "ALIAS": "alias",
                "CREATED_AT": "createdTimestamp descending",
                "UPDATED_AT": "lastUpdatedTimestamp descending",
            }
            api_order_by = order_by_map.get(order_by.upper()) if order_by else None

            filter_expr = _build_system_filter(
                alias=alias,
                state=state,
                os_filter=os_filter,
                host=host,
                has_keyword=has_keyword if has_keyword else None,
                property_filters=property_filters if property_filters else None,
                workspace_id=workspace_id,
                custom_filter=filter_query,
            )

            def system_formatter(item: Dict[str, Any]) -> List[str]:
                ws_id = item.get("workspace", "")
                ws_name = get_workspace_display_name(ws_id, workspace_map)
                # Projected responses have flat top-level keys (e.g. "host")
                # while non-projected responses use nested structures.
                if "host" in item or "kernel" in item:
                    # Flat projected shape
                    host = item.get("host", "")
                    state = item.get("connected", "UNKNOWN")
                    kernel = item.get("kernel", "")
                else:
                    # Nested shape (fallback)
                    grains = _get_system_grains(item)
                    host = grains.get("host", "")
                    state = _get_system_state(item)
                    kernel = grains.get("kernel", "")
                return [
                    item.get("alias", ""),
                    host,
                    state,
                    kernel,
                    ws_name,
                    item.get("id", ""),
                ]

            headers = ["Alias", "Host", "State", "OS", "Workspace", "ID"]
            column_widths = _calculate_column_widths()
            explicit_json_projection = _resolve_system_json_projection(include_fields, all_fields)

            query_url = _get_system_query_url()
            use_materialized_search = _prefer_materialized_system_search(
                filter_query,
                has_package,
                include_fields,
                all_fields,
            )
            materialized_filter_expr = None
            materialized_order_by = None
            materialized_descending = False

            if use_materialized_search:
                materialized_filter_expr = _build_materialized_system_search_filter(
                    alias=alias,
                    state=state,
                    os_filter=os_filter,
                    host=host,
                    has_keyword=has_keyword if has_keyword else None,
                    property_filters=property_filters if property_filters else None,
                    workspace_id=workspace_id,
                )
                materialized_order_by, materialized_descending = _get_materialized_search_order(
                    order_by
                )

            if format_output.lower() == "json":
                if use_materialized_search:
                    systems = _query_materialized_systems_with_fallback(
                        materialized_filter_expr,
                        materialized_order_by,
                        materialized_descending,
                        filter_expr,
                        api_order_by,
                        take=take,
                    )
                else:
                    systems = _query_all_items(
                        query_url,
                        filter_expr,
                        api_order_by,
                        _parse_systems_response,
                        projection=explicit_json_projection or _LIST_PROJECTION,
                        take=take,
                    )
                if has_package:
                    systems = _filter_by_package(systems, has_package)
                mock_resp: Any = FilteredResponse({"systems": systems})
                UniversalResponseHandler.handle_list_response(
                    resp=mock_resp,
                    data_key="systems",
                    item_name="system",
                    format_output=format_output,
                    formatter_func=system_formatter,
                    headers=headers,
                    column_widths=column_widths,
                    empty_message="No systems found.",
                    enable_pagination=False,
                    page_size=take,
                )
            else:
                pkg_filter = (
                    (lambda items: _filter_by_package(items, has_package)) if has_package else None
                )
                if use_materialized_search:
                    _handle_materialized_system_pagination_with_fallback(
                        search_filter_expr=materialized_filter_expr,
                        search_order_by=materialized_order_by,
                        search_descending=materialized_descending,
                        fallback_filter_expr=filter_expr,
                        fallback_order_by=api_order_by,
                        take=take,
                        formatter_func=system_formatter,
                        headers=headers,
                        column_widths=column_widths,
                        empty_message="No systems found.",
                        item_label="systems",
                    )
                else:
                    _handle_interactive_pagination(
                        url=query_url,
                        filter_expr=filter_expr,
                        order_by=api_order_by,
                        take=take,
                        formatter_func=system_formatter,
                        headers=headers,
                        column_widths=column_widths,
                        empty_message="No systems found.",
                        item_label="systems",
                        response_parser=_parse_systems_response,
                        client_filter=pkg_filter,
                        projection=_LIST_PROJECTION,
                    )
        except Exception as exc:  # noqa: BLE001
            handle_api_error(exc)

    @system.command(name="get")
    @click.argument("system_id")
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    @click.option(
        "--include-packages",
        is_flag=True,
        help="Include installed packages in output",
    )
    @click.option(
        "--include-feeds",
        is_flag=True,
        help="Include configured feeds from the system record",
    )
    @click.option(
        "--include-assets",
        is_flag=True,
        help="Include assets associated with this system (niapm)",
    )
    @click.option(
        "--include-alarms",
        is_flag=True,
        help="Include active alarm instances for this system",
    )
    @click.option(
        "--include-jobs",
        is_flag=True,
        help="Include recent jobs dispatched to this system",
    )
    @click.option(
        "--include-results",
        is_flag=True,
        help="Include recent test results for this system",
    )
    @click.option(
        "--include-workitems",
        is_flag=True,
        help="Include scheduled work items (test plans) that reference this system",
    )
    @click.option(
        "--include-all",
        is_flag=True,
        help="Include all related resources (packages, feeds, assets, alarms, jobs, results, work items)",
    )
    @click.option(
        "--take",
        "-t",
        type=int,
        default=10,
        show_default=True,
        help="Maximum rows to show per related-resource section",
    )
    @click.option(
        "--workitem-days",
        type=int,
        default=30,
        show_default=True,
        help="Time-window half-width in days for --include-workitems (centre = today)",
    )
    def get_system(
        system_id: str,
        format: str,
        include_packages: bool,
        include_feeds: bool,
        include_assets: bool,
        include_alarms: bool,
        include_jobs: bool,
        include_results: bool,
        include_workitems: bool,
        include_all: bool,
        take: int,
        workitem_days: int,
    ) -> None:
        """Get detailed information about a specific system.

        SYSTEM_ID is the unique identifier (minion ID) of the system.

        Use --include-* flags to pull in related resources from other services
        in parallel.  --include-all enables every section at once.
        """
        format_output = validate_output_format(format)

        # Resolve effective include flags
        eff_packages = include_all or include_packages
        eff_feeds = include_all or include_feeds
        eff_assets = include_all or include_assets
        eff_alarms = include_all or include_alarms
        eff_jobs = include_all or include_jobs
        eff_results = include_all or include_results
        eff_workitems = include_all or include_workitems

        any_related = eff_assets or eff_alarms or eff_jobs or eff_results or eff_workitems

        try:
            url = f"{_get_sysmgmt_base_url()}/systems?id={system_id}"
            resp = make_api_request("GET", url)
            data = resp.json()

            # API returns an array — take the first element
            if isinstance(data, list) and data:
                system_data = data[0]
            elif isinstance(data, dict):
                system_data = data
            else:
                click.echo(f"✗ System not found: {system_id}", err=True)
                sys.exit(ExitCodes.NOT_FOUND)

            # ---------------------------------------------------------------
            # Fetch related resources in parallel
            # ---------------------------------------------------------------
            assets: List[Dict[str, Any]] = []
            assets_total = 0
            alarms: List[Dict[str, Any]] = []
            alarms_total = 0
            jobs_list: List[Dict[str, Any]] = []
            jobs_total = 0
            results: List[Dict[str, Any]] = []
            results_total = 0
            workitems: List[Dict[str, Any]] = []
            workitems_total = 0
            fetch_errors: Dict[str, str] = {}

            if any_related:
                task_map: Dict[str, Any] = {}
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    if eff_assets:
                        task_map["assets"] = executor.submit(
                            _fetch_assets_for_system, system_id, take
                        )
                    if eff_alarms:
                        task_map["alarms"] = executor.submit(
                            _fetch_alarms_for_system, system_id, take
                        )
                    if eff_jobs:
                        task_map["jobs"] = executor.submit(
                            _fetch_recent_jobs_for_system, system_id, take
                        )
                    if eff_results:
                        task_map["results"] = executor.submit(
                            _fetch_results_for_system, system_id, take
                        )
                    if eff_workitems:
                        task_map["workitems"] = executor.submit(
                            _fetch_workitems_for_system, system_id, take, workitem_days
                        )

                for key, future in task_map.items():
                    try:
                        result_pair = future.result()
                        if key == "assets":
                            assets, assets_total = result_pair
                        elif key == "alarms":
                            alarms, alarms_total = result_pair
                        elif key == "jobs":
                            jobs_list, jobs_total = result_pair
                        elif key == "results":
                            results, results_total = result_pair
                        elif key == "workitems":
                            workitems, workitems_total = result_pair
                    except Exception as exc:  # noqa: BLE001
                        fetch_errors[key] = str(exc)

            # ---------------------------------------------------------------
            # Output
            # ---------------------------------------------------------------
            if format_output.lower() == "json":
                output_data = dict(system_data)
                if not eff_packages:
                    output_data.pop("packages", None)
                if not eff_feeds:
                    output_data.pop("feeds", None)
                if eff_assets:
                    output_data["_assets"] = {
                        "totalCount": assets_total,
                        "items": assets,
                        "error": fetch_errors.get("assets"),
                    }
                if eff_alarms:
                    output_data["_alarms"] = {
                        "totalCount": alarms_total,
                        "items": alarms,
                        "error": fetch_errors.get("alarms"),
                    }
                if eff_jobs:
                    output_data["_jobs"] = {
                        "totalCount": jobs_total,
                        "items": jobs_list,
                        "error": fetch_errors.get("jobs"),
                    }
                if eff_results:
                    output_data["_results"] = {
                        "totalCount": results_total,
                        "items": results,
                        "error": fetch_errors.get("results"),
                    }
                if eff_workitems:
                    output_data["_workitems"] = {
                        "totalCount": workitems_total,
                        "items": workitems,
                        "error": fetch_errors.get("workitems"),
                    }
                click.echo(json.dumps(output_data, indent=2))
            else:
                try:
                    workspace_map = get_workspace_map()
                except Exception:
                    workspace_map = {}
                _format_system_detail(system_data, workspace_map)

                if eff_packages:
                    _format_packages_table(system_data)

                if eff_feeds:
                    _format_feeds_table(system_data)

                if eff_assets:
                    if "assets" in fetch_errors:
                        click.echo(
                            f"\n  ✗ Failed to load assets: {fetch_errors['assets']}", err=True
                        )
                    else:
                        _format_assets_section(assets, assets_total, take)

                if eff_alarms:
                    if "alarms" in fetch_errors:
                        click.echo(
                            f"\n  ✗ Failed to load alarms: {fetch_errors['alarms']}", err=True
                        )
                    else:
                        _format_alarms_section(alarms, alarms_total, take)

                if eff_jobs:
                    if "jobs" in fetch_errors:
                        click.echo(f"\n  ✗ Failed to load jobs: {fetch_errors['jobs']}", err=True)
                    else:
                        _format_jobs_section(jobs_list, jobs_total, take)

                if eff_results:
                    if "results" in fetch_errors:
                        click.echo(
                            f"\n  ✗ Failed to load results: {fetch_errors['results']}", err=True
                        )
                    else:
                        _format_results_section(results, results_total, take)

                if eff_workitems:
                    if "workitems" in fetch_errors:
                        click.echo(
                            f"\n  ✗ Failed to load work items: {fetch_errors['workitems']}",
                            err=True,
                        )
                    else:
                        _format_workitems_section(workitems, workitems_total, take, workitem_days)

                click.echo()

        except Exception as exc:  # noqa: BLE001
            handle_api_error(exc)

    @system.command(name="summary")
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    def system_summary(format: str) -> None:
        """Show fleet-wide system summary.

        Displays counts for connected, disconnected, virtual, and pending
        systems.
        """
        format_output = validate_output_format(format)

        try:
            # Fetch both summaries
            summary_url = f"{_get_sysmgmt_base_url()}/get-systems-summary"
            summary_resp = make_api_request("GET", summary_url)
            summary_data = summary_resp.json()

            pending_url = f"{_get_sysmgmt_base_url()}/get-pending-systems-summary"
            pending_resp = make_api_request("GET", pending_url)
            pending_data = pending_resp.json()

            connected = summary_data.get("connectedCount", 0)
            disconnected = summary_data.get("disconnectedCount", 0)
            virtual = summary_data.get("virtualCount", 0)
            pending = pending_data.get("pendingCount", 0)
            total = connected + disconnected + virtual + pending

            if format_output.lower() == "json":
                result = {
                    "connectedCount": connected,
                    "disconnectedCount": disconnected,
                    "virtualCount": virtual,
                    "pendingCount": pending,
                    "totalCount": total,
                }
                click.echo(json.dumps(result, indent=2))
            else:
                click.echo()
                click.echo("System Fleet Summary:")
                render_table(
                    headers=["STATE", "COUNT"],
                    column_widths=[16, 7],
                    rows=[
                        ["Connected", connected],
                        ["Disconnected", disconnected],
                        ["Virtual", virtual],
                        ["Pending", pending],
                        ["Total", total],
                    ],
                    show_total=False,
                )
                click.echo()

        except Exception as exc:  # noqa: BLE001
            handle_api_error(exc)

    # ------------------------------------------------------------------
    # Phase 2: update, remove, report, job subgroup
    # ------------------------------------------------------------------

    @system.command(name="update")
    @click.argument("system_id")
    @click.option("--alias", help="New alias for the system")
    @click.option(
        "--keyword",
        "keywords",
        multiple=True,
        help="Keywords to set (replaces all keywords, repeatable)",
    )
    @click.option(
        "--property",
        "properties",
        multiple=True,
        help="Property in key=value format (replaces all properties, repeatable)",
    )
    @click.option("--workspace", "-w", help="Workspace ID or name to move system to")
    @click.option("--scan-code", help="New scan code")
    @click.option("--location-id", help="New location ID")
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    def update_system(
        system_id: str,
        alias: Optional[str],
        keywords: Tuple[str, ...],
        properties: Tuple[str, ...],
        workspace: Optional[str],
        scan_code: Optional[str],
        location_id: Optional[str],
        format: str,
    ) -> None:
        """Update a system's metadata.

        SYSTEM_ID is the unique identifier of the system to update.
        Only the specified fields are changed; others remain unchanged.
        """
        check_readonly_mode("update a system")
        format_output = validate_output_format(format)

        try:
            patch_data: Dict[str, Any] = {}

            if alias is not None:
                patch_data["alias"] = alias
            if keywords:
                patch_data["keywords"] = list(keywords)
            if properties:
                patch_data["properties"] = _parse_properties(properties)
            if workspace is not None:
                try:
                    ws_map = get_workspace_map()
                    ws_id = resolve_workspace_filter(workspace, ws_map)
                    patch_data["workspace"] = ws_id
                except Exception:
                    patch_data["workspace"] = workspace
            if scan_code is not None:
                patch_data["scanCode"] = scan_code
            if location_id is not None:
                patch_data["locationId"] = location_id

            if not patch_data:
                click.echo("✗ No fields specified to update.", err=True)
                sys.exit(ExitCodes.INVALID_INPUT)

            url = f"{_get_sysmgmt_base_url()}/systems/managed/{system_id}"
            make_api_request("PATCH", url, payload=patch_data)

            if format_output.lower() == "json":
                # PATCH returns 204 on success, so output the sent data
                result = {"id": system_id, **patch_data}
                click.echo(json.dumps(result, indent=2))
            else:
                format_success("System updated", {"ID": system_id})

        except Exception as exc:  # noqa: BLE001
            handle_api_error(exc)

    @system.command(name="remove")
    @click.argument("system_id")
    @click.option(
        "--force",
        is_flag=True,
        help="Skip confirmation and remove immediately from database",
    )
    def remove_system(
        system_id: str,
        force: bool,
    ) -> None:
        """Remove/unregister a system from SystemLink.

        SYSTEM_ID is the unique identifier of the system to remove.

        Without --force, prompts for confirmation and waits for the
        unregister job to complete. With --force, removes the system
        from the database immediately.
        """
        check_readonly_mode("remove a system")

        try:
            # Fetch system info for confirmation display
            display_name = system_id
            try:
                info_url = f"{_get_sysmgmt_base_url()}/systems?id={system_id}"
                info_resp = make_api_request("GET", info_url)
                info_data = info_resp.json()
                if isinstance(info_data, list) and info_data:
                    display_name = info_data[0].get("alias", system_id)
            except Exception:  # noqa: BLE001
                # Best-effort only: if we cannot fetch system info, fall back to
                # using the ID as the display name for the confirmation prompt.
                display_name = system_id

            if not force:
                if not questionary.confirm(
                    f"Are you sure you want to remove system '{display_name}'?",
                    default=False,
                ).ask():
                    click.echo("Remove cancelled.")
                    sys.exit(ExitCodes.SUCCESS)

            url = f"{_get_sysmgmt_base_url()}/remove-systems"
            payload: Dict[str, Any] = {
                "tgt": [system_id],
                "force": force,
            }
            resp = make_api_request("POST", url, payload=payload)
            data = resp.json()

            # Check for failed removals
            failed = data.get("failedIds", []) if isinstance(data, dict) else []
            if failed:
                for fail in failed:
                    fail_id = fail.get("id", "") if isinstance(fail, dict) else str(fail)
                    fail_err = (
                        fail.get("error", {}).get("message", "Unknown error")
                        if isinstance(fail, dict)
                        else "Unknown error"
                    )
                    click.echo(f"✗ Failed to remove {fail_id}: {fail_err}", err=True)
                sys.exit(ExitCodes.GENERAL_ERROR)

            format_success(
                "System removed",
                {"Name": display_name, "ID": system_id},
            )

        except Exception as exc:  # noqa: BLE001
            handle_api_error(exc)

    @system.command(name="report")
    @click.option(
        "--type",
        "report_type",
        type=click.Choice(["SOFTWARE", "HARDWARE"], case_sensitive=True),
        required=True,
        help="Report type to generate",
    )
    @click.option(
        "--filter",
        "filter_query",
        help="Filter expression to scope which systems to include",
    )
    @click.option(
        "--output",
        "-o",
        "output_path",
        type=click.Path(),
        required=True,
        help="File path to save the report",
    )
    def system_report(
        report_type: str,
        filter_query: Optional[str],
        output_path: str,
    ) -> None:
        """Generate a software or hardware report for systems.

        The report is saved to the specified output file.
        """
        check_readonly_mode("generate a system report")

        try:
            url = f"{_get_sysmgmt_base_url()}/generate-systems-report"
            payload: Dict[str, Any] = {"type": report_type}
            if filter_query:
                payload["filter"] = filter_query

            resp = make_api_request("POST", url, payload=payload)

            with open(output_path, "wb") as f:
                f.write(resp.content if hasattr(resp, "content") else resp.text.encode())

            format_success(
                "Report generated",
                {"Type": report_type, "Output": output_path},
            )

        except Exception as exc:  # noqa: BLE001
            handle_api_error(exc)

    # ------------------------------------------------------------------
    # Job subgroup
    # ------------------------------------------------------------------

    @system.group()
    def job() -> None:
        """Manage system jobs.

        Query, inspect, and cancel jobs dispatched to managed systems.
        """

    @job.command(name="list")
    @click.option(
        "--format",
        "-f",
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
        help="Items per page (table output only)",
    )
    @click.option("--system-id", help="Filter jobs by target system ID")
    @click.option(
        "--state",
        type=click.Choice(
            ["SUCCEEDED", "FAILED", "INPROGRESS", "INQUEUE", "OUTOFQUEUE", "CANCELED"],
            case_sensitive=True,
        ),
        help="Filter by job state",
    )
    @click.option("--function", help="Filter by salt function name (contains match)")
    @click.option(
        "--filter",
        "filter_query",
        help="Advanced API filter expression for jobs",
    )
    @click.option(
        "--order-by",
        type=click.Choice(
            ["CREATED_AT", "UPDATED_AT", "STATE"],
            case_sensitive=False,
        ),
        help="Order by field (default: created descending)",
    )
    def list_jobs(
        format: str,
        take: int,
        system_id: Optional[str],
        state: Optional[str],
        function: Optional[str],
        filter_query: Optional[str],
        order_by: Optional[str],
    ) -> None:
        """List and query jobs with optional filtering.

        Supports convenience filters (--system-id, --state, --function)
        that are translated to API filter expressions.
        """
        format_output = validate_output_format(format)

        try:
            job_order_map: Dict[str, str] = {
                "CREATED_AT": "createdTimestamp descending",
                "UPDATED_AT": "lastUpdatedTimestamp descending",
                "STATE": "state",
            }
            api_order_by = (
                job_order_map.get(order_by.upper()) if order_by else "createdTimestamp descending"
            )

            filter_expr = _build_job_filter(
                system_id=system_id,
                state=state,
                function=function,
                custom_filter=filter_query,
            )

            def job_formatter(item: Dict[str, Any]) -> List[str]:
                fields = _get_job_display_fields(item)
                return [
                    fields["jid"],
                    fields["state"],
                    fields["created"],
                    fields["target"],
                ]

            headers = ["Job ID", "State", "Created", "Target System"]
            column_widths = _calculate_job_column_widths()

            query_url = f"{_get_sysmgmt_base_url()}/query-jobs"

            if format_output.lower() == "json":
                jobs = _query_all_items(
                    query_url,
                    filter_expr,
                    api_order_by,
                    _parse_simple_response,
                )
                mock_resp: Any = FilteredResponse({"jobs": jobs})
                UniversalResponseHandler.handle_list_response(
                    resp=mock_resp,
                    data_key="jobs",
                    item_name="job",
                    format_output=format_output,
                    formatter_func=job_formatter,
                    headers=headers,
                    column_widths=column_widths,
                    empty_message="No jobs found.",
                    enable_pagination=False,
                    page_size=take,
                )
            else:
                _handle_interactive_pagination(
                    url=query_url,
                    filter_expr=filter_expr,
                    order_by=api_order_by,
                    take=take,
                    formatter_func=job_formatter,
                    headers=headers,
                    column_widths=column_widths,
                    empty_message="No jobs found.",
                    item_label="jobs",
                    response_parser=_parse_simple_response,
                )

        except Exception as exc:  # noqa: BLE001
            handle_api_error(exc)

    @job.command(name="get")
    @click.argument("job_id")
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    def get_job(
        job_id: str,
        format: str,
    ) -> None:
        """Get detailed information about a specific job.

        JOB_ID is the unique identifier of the job.
        """
        format_output = validate_output_format(format)

        try:
            url = f"{_get_sysmgmt_base_url()}/jobs?jid={job_id}"
            resp = make_api_request("GET", url)
            data = resp.json()

            # API returns an array — take the first element
            if isinstance(data, list) and data:
                job_data = data[0]
            elif isinstance(data, dict):
                job_data = data
            else:
                click.echo(f"✗ Job not found: {job_id}", err=True)
                sys.exit(ExitCodes.NOT_FOUND)

            if format_output.lower() == "json":
                click.echo(json.dumps(job_data, indent=2))
            else:
                config = job_data.get("config") or {}
                result = job_data.get("result") or {}
                targets = config.get("tgt", [])
                functions = config.get("fun", [])

                click.echo("\nJob Details")
                click.echo("──────────────────────────────────────")
                click.echo(f"  Job ID:        {job_data.get('jid', 'N/A')}")
                click.echo(f"  State:         {job_data.get('state', 'N/A')}")
                click.echo(
                    f"  Target:        {targets[0] if targets else job_data.get('id', 'N/A')}"
                )
                click.echo(f"  Functions:     {', '.join(functions) if functions else 'N/A'}")

                click.echo("")
                click.echo("  Timestamps:")
                click.echo(f"    Created:       {job_data.get('createdTimestamp', 'N/A')}")
                click.echo(f"    Updated:       {job_data.get('lastUpdatedTimestamp', 'N/A')}")
                click.echo(f"    Dispatched:    {job_data.get('dispatchedTimestamp', 'N/A')}")

                if result:
                    click.echo("")
                    click.echo("  Result:")
                    ret_codes = result.get("retcode", [])
                    ret_values = result.get("return", [])
                    successes = result.get("success", [])
                    click.echo(f"    Return Code:   " f"{ret_codes[0] if ret_codes else 'N/A'}")
                    click.echo(f"    Return:        " f"{ret_values[0] if ret_values else 'N/A'}")
                    click.echo(f"    Success:       " f"{successes[0] if successes else 'N/A'}")

                click.echo()

        except Exception as exc:  # noqa: BLE001
            handle_api_error(exc)

    @job.command(name="summary")
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    def job_summary(format: str) -> None:
        """Show job summary — active, failed, and succeeded counts."""
        format_output = validate_output_format(format)

        try:
            url = f"{_get_sysmgmt_base_url()}/get-jobs-summary"
            resp = make_api_request("GET", url)
            data = resp.json()

            active = data.get("activeCount", 0)
            succeeded = data.get("succeededCount", 0)
            failed = data.get("failedCount", 0)
            total = active + succeeded + failed

            if format_output.lower() == "json":
                result = {
                    "activeCount": active,
                    "succeededCount": succeeded,
                    "failedCount": failed,
                    "totalCount": total,
                }
                click.echo(json.dumps(result, indent=2))
            else:
                click.echo("\nJob Summary")
                click.echo("──────────────────────────────────────")
                click.echo(f"  Active:       {active}")
                click.echo(f"  Succeeded:    {succeeded}")
                click.echo(f"  Failed:       {failed}")
                click.echo("  ─────────────────")
                click.echo(f"  Total:        {total}")
                click.echo()

        except Exception as exc:  # noqa: BLE001
            handle_api_error(exc)

    @job.command(name="cancel")
    @click.argument("job_id")
    @click.option("--system-id", help="Target system ID (for disambiguation)")
    def cancel_job(
        job_id: str,
        system_id: Optional[str],
    ) -> None:
        """Cancel a running job.

        JOB_ID is the unique identifier of the job to cancel.
        """
        check_readonly_mode("cancel a job")

        try:
            url = f"{_get_sysmgmt_base_url()}/cancel-jobs"
            cancel_request: Dict[str, Any] = {"jid": job_id}
            if system_id:
                cancel_request["systemId"] = system_id

            payload: Dict[str, Any] = {"jobs": [cancel_request]}
            make_api_request("POST", url, payload=payload)

            format_success("Job cancelled", {"Job ID": job_id})

        except Exception as exc:  # noqa: BLE001
            handle_api_error(exc)

    @system.command(name="compare")
    @click.argument("system_a")
    @click.argument("system_b")
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format.",
    )
    def compare_systems(
        system_a: str,
        system_b: str,
        format: str,
    ) -> None:
        """Compare two systems by software and connected assets.

        SYSTEM_A and SYSTEM_B are system IDs or aliases. The command
        fetches installed software and connected assets for each system,
        then highlights differences in packages, versions, slot numbers,
        models, and vendors.
        """
        format_output = validate_output_format(format)

        try:
            # Resolve both systems (by ID or alias)
            sys_a = _resolve_system(system_a)
            sys_b = _resolve_system(system_b)

            id_a = sys_a.get("id", system_a)
            id_b = sys_b.get("id", system_b)
            alias_a = sys_a.get("alias") or id_a
            alias_b = sys_b.get("alias") or id_b

            # Fetch assets for both systems in parallel. The current helper
            # supports a take limit, so explicitly guard against silently
            # comparing truncated results when a system has more assets than
            # the fetch cap.
            asset_fetch_limit = 1000
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future_assets_a = executor.submit(_fetch_assets_for_system, id_a, asset_fetch_limit)
                future_assets_b = executor.submit(_fetch_assets_for_system, id_b, asset_fetch_limit)

            assets_a, total_assets_a = future_assets_a.result()
            assets_b, total_assets_b = future_assets_b.result()

            truncated_systems: List[str] = []
            if total_assets_a > asset_fetch_limit:
                truncated_systems.append(
                    f"{alias_a} ({total_assets_a} assets, limit {asset_fetch_limit})"
                )
            if total_assets_b > asset_fetch_limit:
                truncated_systems.append(
                    f"{alias_b} ({total_assets_b} assets, limit {asset_fetch_limit})"
                )

            if truncated_systems:
                click.echo(
                    "✗ Error: system comparison would be incomplete because "
                    "asset retrieval is limited to the first "
                    f"{asset_fetch_limit} assets. Affected system(s): "
                    + ", ".join(truncated_systems),
                    err=True,
                )
                sys.exit(ExitCodes.GENERAL_ERROR)

            # Extract packages
            pkgs_a = _get_packages(sys_a)
            pkgs_b = _get_packages(sys_b)

            if format_output.lower() == "json":
                output: Dict[str, Any] = {
                    "system_a": {"id": id_a, "alias": alias_a},
                    "system_b": {"id": id_b, "alias": alias_b},
                    "software": _compare_packages(pkgs_a, pkgs_b, alias_a, alias_b, format_output),
                    "assets": _compare_assets(assets_a, assets_b, alias_a, alias_b, format_output),
                }
                click.echo(json.dumps(output, indent=2))
            else:
                click.echo(f"\n  Comparing: {alias_a}  ↔  {alias_b}")
                click.echo("  " + "═" * 60)
                _compare_packages(pkgs_a, pkgs_b, alias_a, alias_b, format_output)
                _compare_assets(assets_a, assets_b, alias_a, alias_b, format_output)
                click.echo()

        except SystemExit:
            raise
        except Exception as exc:  # noqa: BLE001
            handle_api_error(exc)
