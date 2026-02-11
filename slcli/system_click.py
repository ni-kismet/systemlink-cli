"""CLI commands for managing SystemLink systems.

Provides CLI commands for listing, querying, and managing systems in the
Systems Management service (nisysmgmt v1). Supports filtering by alias,
connection state, OS, installed packages, keywords, and properties.
Also provides job management and system metadata updates.
"""

import json
import re
import shutil
import sys
from typing import Any, Dict, List, Optional, Tuple

import click

from .cli_utils import validate_output_format
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
from .workspace_utils import get_workspace_display_name, resolve_workspace_filter


def _get_sysmgmt_base_url() -> str:
    """Get the base URL for the Systems Management API."""
    return f"{get_base_url()}/nisysmgmt/v1"


# Projection for list queries — only include fields needed for display.
# This dramatically reduces response payload size.
# Uses the dot-path ``as`` alias syntax supported by the systems API.
_LIST_PROJECTION = (
    "new(id, alias, workspace, "
    "connected.data.state as connected, "
    "grains.data.kernel as kernel, "
    "grains.data.osversion as osversion, "
    "grains.data.host as host, "
    "grains.data.cpuarch as cpuarch, "
    "grains.data.deviceclass as deviceclass, "
    "keywords.data as keywords, "
    "packages.data as packages)"
)


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

    # Account for table borders and padding for 6 columns.
    # Row layout: "│ c1 │ c2 │ c3 │ c4 │ c5 │ c6 │" = 7 bars + 12 spaces = 19
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

    # Account for table borders and padding for 4 columns.
    # Row layout: "│ c1 │ c2 │ c3 │ c4 │" = 5 bars + 8 spaces = 13
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
            if "=" not in prop:
                click.echo(
                    f"✗ Invalid property filter '{prop}': expected KEY=VALUE format",
                    err=True,
                )
                sys.exit(ExitCodes.INVALID_INPUT)
            key, val = prop.split("=", 1)
            key = key.strip()
            if not re.match(r"^[A-Za-z0-9_.]+$", key):
                click.echo(
                    f"✗ Invalid property key '{key}': "
                    "only alphanumeric characters, underscores, and dots are allowed",
                    err=True,
                )
                sys.exit(ExitCodes.INVALID_INPUT)
            escaped_val = _escape_filter_value(val.strip())
            parts.append(f'properties.data.{key} = "{escaped_val}"')
    if workspace_id:
        escaped = _escape_filter_value(workspace_id)
        parts.append(f'workspace = "{escaped}"')
    if custom_filter:
        parts.append(custom_filter)

    return " and ".join(parts) if parts else None


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
    # When using client-side filtering we fetch larger batches
    fetch_size = 1000 if client_filter else take

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

        if not click.confirm("More results may be available. Show next set?", default=True):
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
        help="Maximum number of items to return",
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
    ) -> None:
        """List and query systems with optional filtering.

        Supports convenience filters (--alias, --state, --os, --host,
        --has-keyword, --property) that are translated to API filter
        expressions.  Combine multiple options — they are joined with 'and'.

        Use --has-package for client-side package filtering (contains match).

        For advanced queries use --filter with the Systems Management filter
        syntax: connected.data.state = "CONNECTED" and grains.data.kernel = "Windows"
        """
        format_output = validate_output_format(format)

        try:
            # Resolve workspace if provided
            workspace_id: Optional[str] = None
            try:
                workspace_map = get_workspace_map()
            except Exception:
                workspace_map = {}

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

            query_url = f"{_get_sysmgmt_base_url()}/query-systems"

            if format_output.lower() == "json":
                systems = _query_all_items(
                    query_url,
                    filter_expr,
                    api_order_by,
                    _parse_systems_response,
                    projection=_LIST_PROJECTION,
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
        help="Include configured feeds in output",
    )
    def get_system(
        system_id: str,
        format: str,
        include_packages: bool,
        include_feeds: bool,
    ) -> None:
        """Get detailed information about a specific system.

        SYSTEM_ID is the unique identifier (minion ID) of the system.
        """
        format_output = validate_output_format(format)

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

            if format_output.lower() == "json":
                # Optionally strip packages/feeds for smaller output
                output_data = dict(system_data)
                if not include_packages:
                    output_data.pop("packages", None)
                if not include_feeds:
                    output_data.pop("feeds", None)
                click.echo(json.dumps(output_data, indent=2))
            else:
                try:
                    workspace_map = get_workspace_map()
                except Exception:
                    workspace_map = {}
                _format_system_detail(system_data, workspace_map)

                if include_packages:
                    _format_packages_table(system_data)

                if include_feeds:
                    _format_feeds_table(system_data)

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
                click.echo("\nSystem Fleet Summary")
                click.echo("──────────────────────────────────────")
                click.echo(f"  Connected:      {connected}")
                click.echo(f"  Disconnected:   {disconnected}")
                click.echo(f"  Virtual:        {virtual}")
                click.echo(f"  Pending:        {pending}")
                click.echo("  ─────────────────")
                click.echo(f"  Total:          {total}")
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
                if not click.confirm(f"Are you sure you want to remove system '{display_name}'?"):
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
