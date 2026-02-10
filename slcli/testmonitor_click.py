"""CLI commands for SystemLink Test Monitor (products and test results)."""

import json
import re
import sys
from typing import Any, Dict, Iterable, List, Optional, Tuple

import click

from .cli_utils import validate_output_format
from .universal_handlers import FilteredResponse, UniversalResponseHandler
from .utils import get_base_url, get_workspace_map, handle_api_error, make_api_request
from .workspace_utils import get_workspace_display_name, resolve_workspace_filter


def _get_testmonitor_base_url() -> str:
    """Get the base URL for the Test Monitor API."""
    return f"{get_base_url()}/nitestmonitor/v2"


def _parse_substitutions(values: Iterable[str]) -> List[Any]:
    """Parse substitution values from CLI inputs.

    Args:
        values: Iterable of raw substitution strings.

    Returns:
        Parsed substitution values.
    """
    parsed: List[Any] = []
    for value in values:
        try:
            parsed.append(json.loads(value))
        except (json.JSONDecodeError, TypeError):
            parsed.append(value)
    return parsed


def _offset_substitutions(filter_expr: str, offset: int) -> str:
    """Offset substitution indices in a filter expression.

    Args:
        filter_expr: Filter expression containing @<index> tokens.
        offset: Offset to add to each index.

    Returns:
        Updated filter expression with offset indices.
    """
    if offset <= 0:
        return filter_expr

    def _replace(match: re.Match[str]) -> str:
        return f"@{int(match.group(1)) + offset}"

    return re.sub(r"@(\d+)", _replace, filter_expr)


def _combine_filter_parts(
    base_filter: Optional[str],
    base_substitutions: List[Any],
    extra_filter: Optional[str],
    extra_substitutions: List[Any],
) -> Tuple[Optional[str], List[Any]]:
    """Combine base and extra filters with substitution offset handling.

    Args:
        base_filter: Filter built from structured options.
        base_substitutions: Substitutions for the base filter.
        extra_filter: User-provided filter expression.
        extra_substitutions: Substitutions for the user filter.

    Returns:
        Tuple of combined filter expression and substitutions.
    """
    if not extra_filter:
        return base_filter, base_substitutions

    if base_filter:
        offset_filter = _offset_substitutions(extra_filter, len(base_substitutions))
        combined_filter = f"({base_filter}) && ({offset_filter})"
        combined_subs = base_substitutions + extra_substitutions
        return combined_filter, combined_subs

    return extra_filter, extra_substitutions


def _append_filter(
    filter_parts: List[str], substitutions: List[Any], expression: str, value: Optional[str]
) -> None:
    """Append a filter expression with substitution if value is provided.

    Args:
        filter_parts: List of filter expressions.
        substitutions: List of substitution values.
        expression: Filter expression format using @{index}.
        value: Optional value to insert as a substitution.
    """
    if value is None or value == "":
        return
    index = len(substitutions)
    filter_parts.append(expression.format(index=index))
    substitutions.append(value)


def _format_date(value: str) -> str:
    """Format an ISO-8601 date-time as a date string.

    Args:
        value: ISO-8601 date-time string.

    Returns:
        Date portion of the value, or original value if parsing fails.
    """
    if not value:
        return ""
    if "T" in value:
        return value.split("T", maxsplit=1)[0]
    return value


def _format_duration(value: Any) -> str:
    """Format a duration in seconds.

    Args:
        value: Duration value.

    Returns:
        Formatted duration string.
    """
    if isinstance(value, (int, float)):
        return f"{value:.1f}"
    return str(value) if value is not None else ""


def _handle_interactive_pagination(
    fetch_page_func: Any,
    data_key: str,
    item_name: str,
    format_output: str,
    formatter_func: Any,
    headers: List[str],
    column_widths: List[int],
    empty_message: str,
    take: int,
) -> None:
    """Handle interactive pagination for table output.

    Args:
        fetch_page_func: Function that returns (items, continuation_token) tuple.
        data_key: Key to use for data in the mock response.
        item_name: Name of the item type (e.g., "product", "result").
        format_output: Output format ("table" or "json").
        formatter_func: Function to format each item for display.
        headers: Column headers for the table.
        column_widths: Column widths for the table.
        empty_message: Message to display when no items are found.
        take: Number of items per page.
    """
    cont: Optional[str] = None
    shown_count = 0

    while True:
        page_items, cont = fetch_page_func(cont)

        if not page_items:
            if shown_count == 0:
                click.echo(empty_message)
            break

        shown_count += len(page_items)

        mock_resp = FilteredResponse({data_key: page_items})
        UniversalResponseHandler.handle_list_response(
            resp=mock_resp,
            data_key=data_key,
            item_name=item_name,
            format_output=format_output,
            formatter_func=formatter_func,
            headers=headers,
            column_widths=column_widths,
            empty_message=empty_message,
            enable_pagination=False,
            page_size=take,
            shown_count=shown_count,
        )

        # Flush stdout so the table is visible before prompting
        try:
            sys.stdout.flush()
        except Exception:
            # Best-effort flush; ignore failures to avoid crashing on I/O issues.
            pass

        # Ask if user wants to fetch the next page
        if not cont:
            break

        if not click.confirm("Show next set of results?", default=True):
            break


def _warn_if_large_dataset(
    endpoint: str,
    filter_expr: Optional[str],
    substitutions: List[Any],
    product_filter: Optional[str],
    product_substitutions: List[Any],
    order_by: Optional[str] = None,
    descending: bool = False,
) -> None:
    """Check dataset size and warn user if fetching large number of items.

    Args:
        endpoint: API endpoint ("query-products" or "query-results").
        filter_expr: Optional Dynamic LINQ filter expression.
        substitutions: Substitution values for the filter.
        product_filter: Optional product filter (for results only).
        product_substitutions: Product filter substitutions (for results only).
        order_by: Field to order by (included in count check for consistency).
        descending: Whether results should be in descending order.
    """
    url = f"{_get_testmonitor_base_url()}/{endpoint}"
    payload: Dict[str, Any] = {
        "take": 1,  # Only fetch 1 item to check count
        "returnCount": True,  # Request total count
        "descending": descending,
    }

    if order_by:
        payload["orderBy"] = order_by

    if filter_expr:
        payload["filter"] = filter_expr
        if substitutions:
            payload["substitutions"] = substitutions

    if product_filter:
        payload["productFilter"] = product_filter
        if product_substitutions:
            payload["productSubstitutions"] = product_substitutions

    try:
        resp = make_api_request("POST", url, payload=payload)
        data = resp.json()
        total_count = data.get("totalCount", 0) if isinstance(data, dict) else 0

        if total_count > 10000:
            click.echo(
                f"⚠️  Warning: {total_count} items found. Fetching up to 10,000...",
                err=True,
            )
        elif total_count > 1000:
            click.echo(
                f"ℹ️  Fetching {total_count} items...",
                err=True,
            )
    except Exception:
        # If count check fails, proceed without warning
        pass


def _query_all_products(
    filter_expr: Optional[str],
    substitutions: List[Any],
    order_by: Optional[str],
    descending: bool,
    take: Optional[int] = 10000,
) -> List[Dict[str, Any]]:
    """Query products using continuation token pagination.

    Fetches up to take items (default 10,000 for performance).

    Args:
        filter_expr: Optional Dynamic LINQ filter expression.
        substitutions: Substitution values for the filter.
        order_by: Field to order by.
        descending: Whether to return results in descending order.
        take: Maximum number of items to fetch. Defaults to 10,000 to prevent
              performance issues with very large datasets.

    Returns:
        List of product objects (up to take count).
    """
    url = f"{_get_testmonitor_base_url()}/query-products"
    all_products: List[Dict[str, Any]] = []
    continuation_token: Optional[str] = None
    page_size = 100  # Fetch in larger batches for efficiency

    while True:
        # Calculate how many items to request in this batch
        if take is not None:
            remaining = take - len(all_products)
            if remaining <= 0:
                break
            batch_size = min(page_size, remaining)
        else:
            batch_size = page_size

        payload: Dict[str, Any] = {
            "take": batch_size,
            "descending": descending,
        }

        if order_by:
            payload["orderBy"] = order_by
        if filter_expr:
            payload["filter"] = filter_expr
            if substitutions:
                payload["substitutions"] = substitutions
        if continuation_token:
            payload["continuationToken"] = continuation_token

        resp = make_api_request("POST", url, payload=payload)
        data = resp.json()

        products = data.get("products", []) if isinstance(data, dict) else []
        all_products.extend(products)

        continuation_token = data.get("continuationToken") if isinstance(data, dict) else None
        # Stop if no more pages or we've reached the limit
        if not continuation_token:
            break
        if take is not None and len(all_products) >= take:
            break

    return all_products[:take] if take is not None else all_products


def _fetch_products_page(
    filter_expr: Optional[str],
    substitutions: List[Any],
    order_by: Optional[str],
    descending: bool,
    take: int = 25,
    continuation_token: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Fetch a single page of products.

    Args:
        filter_expr: Optional Dynamic LINQ filter expression.
        substitutions: Substitution values for the filter.
        order_by: Field to order by.
        descending: Whether to return results in descending order.
        take: Number of items to fetch.
        continuation_token: Optional token to resume from a previous query.

    Returns:
        Tuple of (products list, next continuation token or None).
    """
    url = f"{_get_testmonitor_base_url()}/query-products"
    payload: Dict[str, Any] = {
        "take": take,
        "descending": descending,
    }

    if order_by:
        payload["orderBy"] = order_by
    if filter_expr:
        payload["filter"] = filter_expr
        if substitutions:
            payload["substitutions"] = substitutions
    if continuation_token:
        payload["continuationToken"] = continuation_token

    resp = make_api_request("POST", url, payload=payload)
    data = resp.json()

    products = data.get("products", []) if isinstance(data, dict) else []
    next_token = data.get("continuationToken") if isinstance(data, dict) else None

    return products, next_token


def _fetch_results_page(
    filter_expr: Optional[str],
    substitutions: List[Any],
    product_filter: Optional[str],
    product_substitutions: List[Any],
    order_by: Optional[str],
    descending: bool,
    take: int = 25,
    continuation_token: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Fetch a single page of test results.

    Args:
        filter_expr: Optional Dynamic LINQ filter expression for results.
        substitutions: Substitution values for the results filter.
        product_filter: Optional Dynamic LINQ filter expression for products.
        product_substitutions: Substitution values for the product filter.
        order_by: Field to order by.
        descending: Whether to return results in descending order.
        take: Number of items to fetch.
        continuation_token: Optional token to resume from a previous query.

    Returns:
        Tuple of (results list, next continuation token or None).
    """
    url = f"{_get_testmonitor_base_url()}/query-results"
    payload: Dict[str, Any] = {
        "take": take,
        "descending": descending,
    }

    if order_by:
        payload["orderBy"] = order_by
    if filter_expr:
        payload["filter"] = filter_expr
        if substitutions:
            payload["substitutions"] = substitutions
    if product_filter:
        payload["productFilter"] = product_filter
        if product_substitutions:
            payload["productSubstitutions"] = product_substitutions
    if continuation_token:
        payload["continuationToken"] = continuation_token

    resp = make_api_request("POST", url, payload=payload)
    data = resp.json()

    results = data.get("results", []) if isinstance(data, dict) else []
    next_token = data.get("continuationToken") if isinstance(data, dict) else None

    return results, next_token


def _query_all_results(
    filter_expr: Optional[str],
    substitutions: List[Any],
    product_filter: Optional[str],
    product_substitutions: List[Any],
    order_by: Optional[str],
    descending: bool,
    take: Optional[int] = 10000,
) -> List[Dict[str, Any]]:
    """Query test results using continuation token pagination.

    Fetches up to take items (default 10,000 for performance).

    Args:
        filter_expr: Optional Dynamic LINQ filter expression for results.
        substitutions: Substitution values for the results filter.
        product_filter: Optional Dynamic LINQ filter expression for products.
        product_substitutions: Substitution values for the product filter.
        order_by: Field to order by.
        descending: Whether to return results in descending order.
        take: Maximum number of items to fetch. Defaults to 10,000 to prevent
              performance issues with very large datasets.

    Returns:
        List of test result objects (up to take count).
    """
    url = f"{_get_testmonitor_base_url()}/query-results"
    all_results: List[Dict[str, Any]] = []
    continuation_token: Optional[str] = None
    page_size = 100  # Fetch in larger batches for efficiency

    while True:
        # Calculate how many items to request in this batch
        if take is not None:
            remaining = take - len(all_results)
            if remaining <= 0:
                break
            batch_size = min(page_size, remaining)
        else:
            batch_size = page_size

        payload: Dict[str, Any] = {
            "take": batch_size,
            "descending": descending,
        }

        if order_by:
            payload["orderBy"] = order_by
        if filter_expr:
            payload["filter"] = filter_expr
            if substitutions:
                payload["substitutions"] = substitutions
        if product_filter:
            payload["productFilter"] = product_filter
            if product_substitutions:
                payload["productSubstitutions"] = product_substitutions
        if continuation_token:
            payload["continuationToken"] = continuation_token

        resp = make_api_request("POST", url, payload=payload)
        data = resp.json()

        results = data.get("results", []) if isinstance(data, dict) else []
        all_results.extend(results)

        continuation_token = data.get("continuationToken") if isinstance(data, dict) else None
        # Stop if no more pages or we've reached the limit
        if not continuation_token:
            break
        if take is not None and len(all_results) >= take:
            break

    return all_results[:take] if take is not None else all_results


def _summarize_results(
    results: List[Dict[str, Any]],
    group_by_field: Optional[str] = None,
) -> Dict[str, Any]:
    """Summarize test results by aggregating status and other metrics.

    Args:
        results: List of result objects.
        group_by_field: Field to group by (status, programName, etc.)

    Returns:
        Dictionary with summary statistics.
    """
    if not results:
        return {"total": 0, "groups": {}}

    summary: Dict[str, Any] = {
        "total": len(results),
        "groups": {},
    }

    # Group results
    groups: Dict[str, List[Dict[str, Any]]] = {}
    if group_by_field:
        for result in results:
            # Special case for status field - extract statusType
            if group_by_field == "status":
                status_value = result.get("status", {})
                if isinstance(status_value, dict):
                    key = str(status_value.get("statusType", "N/A"))
                else:
                    key = str(status_value)
            else:
                key = str(result.get(group_by_field, "N/A"))
            if key not in groups:
                groups[key] = []
            groups[key].append(result)
    else:
        # Default grouping by status
        for result in results:
            status = result.get("status", {})
            status_type = status.get("statusType", "N/A")
            if status_type not in groups:
                groups[status_type] = []
            groups[status_type].append(result)

    # Calculate statistics per group - store as integers, not dicts
    for group_key, group_results in groups.items():
        summary["groups"][group_key] = len(group_results)

    return summary


def _summarize_products(products: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Summarize product data.

    Args:
        products: List of product objects.

    Returns:
        Dictionary with summary statistics.
    """
    return {
        "total": len(products),
        "families": len(set(p.get("family") or "N/A" for p in products)),
    }


def register_testmonitor_commands(cli: Any) -> None:
    """Register the 'testmonitor' command group and its subcommands."""

    @cli.group()
    def testmonitor() -> None:
        """Commands for test monitor products and results."""

    @testmonitor.group()
    def product() -> None:
        """Manage test monitor products."""

    @testmonitor.group()
    def result() -> None:
        """Manage test monitor test results."""

    @product.command(name="list")
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
    @click.option("--name", help="Filter by product name (contains)")
    @click.option("--part-number", help="Filter by product part number (contains)")
    @click.option("--family", help="Filter by product family (contains)")
    @click.option("--workspace", "-w", help="Filter by workspace name or ID")
    @click.option(
        "--filter",
        "filter_query",
        help="Dynamic LINQ filter expression for products",
    )
    @click.option(
        "--substitution",
        "substitutions",
        multiple=True,
        help="Substitution value for --filter (repeatable)",
    )
    @click.option(
        "--order-by",
        type=click.Choice(
            ["ID", "PART_NUMBER", "NAME", "FAMILY", "UPDATED_AT"], case_sensitive=False
        ),
        help="Order by field",
    )
    @click.option(
        "--descending/--ascending",
        default=True,
        help="Sort order (default: descending)",
    )
    @click.option(
        "--summary",
        is_flag=True,
        help="Show summary statistics (total count and number of families)",
    )
    def list_products(
        format: str,
        take: int,
        name: Optional[str],
        part_number: Optional[str],
        family: Optional[str],
        workspace: Optional[str],
        filter_query: Optional[str],
        substitutions: Tuple[str, ...],
        order_by: Optional[str],
        descending: bool,
        summary: bool,
    ) -> None:
        """List products in Test Monitor."""
        format_output = validate_output_format(format)

        try:
            # Fetch workspace map once for both filter resolution and display
            try:
                workspace_map = get_workspace_map()
            except Exception:
                workspace_map = {}

            filter_parts: List[str] = []
            filter_substitutions: List[Any] = []

            _append_filter(filter_parts, filter_substitutions, "name.Contains(@{index})", name)
            _append_filter(
                filter_parts, filter_substitutions, "partNumber.Contains(@{index})", part_number
            )
            _append_filter(filter_parts, filter_substitutions, "family.Contains(@{index})", family)

            if workspace:
                workspace_id = resolve_workspace_filter(workspace, workspace_map)
                _append_filter(
                    filter_parts, filter_substitutions, "workspace == @{index}", workspace_id
                )

            base_filter = " && ".join(filter_parts) if filter_parts else None
            user_subs = _parse_substitutions(substitutions)

            filter_expr, merged_subs = _combine_filter_parts(
                base_filter, filter_substitutions, filter_query, user_subs
            )

            if order_by:
                order_by = order_by.upper()

            def product_formatter(item: Dict[str, Any]) -> List[str]:
                ws_id = item.get("workspace", "")
                ws_name = get_workspace_display_name(ws_id, workspace_map)
                return [
                    item.get("name", ""),
                    item.get("partNumber", ""),
                    item.get("family", ""),
                    _format_date(item.get("updatedAt", "")),
                    ws_name,
                    item.get("id", ""),
                ]

            # If JSON output, fetch all pages
            if format_output.lower() == "json":
                # Check total count first to warn about large datasets
                _warn_if_large_dataset(
                    endpoint="query-products",
                    filter_expr=filter_expr,
                    substitutions=merged_subs,
                    product_filter=None,
                    product_substitutions=[],
                    order_by=order_by,
                    descending=descending,
                )
                products = _query_all_products(filter_expr, merged_subs, order_by, descending)

                # Handle --summary flag for JSON output
                if summary:
                    summary_stats = _summarize_products(products)
                    click.echo(json.dumps(summary_stats, indent=2))
                else:
                    mock_resp: Any = FilteredResponse({"products": products})
                    UniversalResponseHandler.handle_list_response(
                        resp=mock_resp,
                        data_key="products",
                        item_name="product",
                        format_output=format_output,
                        formatter_func=product_formatter,
                        headers=["Name", "Part Number", "Family", "Updated", "Workspace", "ID"],
                        column_widths=[30, 18, 16, 12, 20, 36],
                        empty_message="No products found.",
                        enable_pagination=False,
                        page_size=take,
                    )
            else:
                # Interactive pagination for table output
                def fetch_page(
                    cont: Optional[str] = None,
                ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
                    return _fetch_products_page(
                        filter_expr, merged_subs, order_by, descending, take, cont
                    )

                # For table output with summary, collect all data first
                if summary:
                    # Check total count first to warn about large datasets
                    _warn_if_large_dataset(
                        endpoint="query-products",
                        filter_expr=filter_expr,
                        substitutions=merged_subs,
                        product_filter=None,
                        product_substitutions=[],
                        order_by=order_by,
                        descending=descending,
                    )
                    all_products = _query_all_products(
                        filter_expr, merged_subs, order_by, descending
                    )
                    summary_stats = _summarize_products(all_products)
                    click.echo("\nProduct Summary Statistics:")
                    click.echo(f"  Total Products: {summary_stats['total']}")
                    click.echo(f"  Families: {summary_stats['families']}")
                    click.echo()
                else:
                    _handle_interactive_pagination(
                        fetch_page_func=fetch_page,
                        data_key="products",
                        item_name="product",
                        format_output=format_output,
                        formatter_func=product_formatter,
                        headers=["Name", "Part Number", "Family", "Updated", "Workspace", "ID"],
                        column_widths=[30, 18, 16, 12, 20, 36],
                        empty_message="No products found.",
                        take=take,
                    )
        except Exception as exc:  # noqa: BLE001
            handle_api_error(exc)

    @result.command(name="list")
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
    @click.option("--status", help="Filter by status type (e.g., PASSED, FAILED)")
    @click.option("--program-name", help="Filter by program name (contains)")
    @click.option("--serial-number", help="Filter by serial number (contains)")
    @click.option("--part-number", help="Filter by part number (contains)")
    @click.option("--operator", help="Filter by operator name (contains)")
    @click.option("--host-name", help="Filter by host name (contains)")
    @click.option("--system-id", help="Filter by system ID")
    @click.option("--workspace", "-w", help="Filter by workspace name or ID")
    @click.option(
        "--filter",
        "filter_query",
        help="Dynamic LINQ filter expression for results",
    )
    @click.option(
        "--substitution",
        "substitutions",
        multiple=True,
        help="Substitution value for --filter (repeatable)",
    )
    @click.option(
        "--product-filter",
        help="Dynamic LINQ filter expression for associated products",
    )
    @click.option(
        "--product-substitution",
        "product_substitutions",
        multiple=True,
        help="Substitution value for --product-filter (repeatable)",
    )
    @click.option(
        "--order-by",
        type=click.Choice(
            [
                "ID",
                "STARTED_AT",
                "UPDATED_AT",
                "PROGRAM_NAME",
                "SYSTEM_ID",
                "HOST_NAME",
                "OPERATOR",
                "SERIAL_NUMBER",
                "PART_NUMBER",
                "PROPERTIES",
                "TOTAL_TIME_IN_SECONDS",
            ],
            case_sensitive=False,
        ),
        help="Order by field",
    )
    @click.option(
        "--descending/--ascending",
        default=True,
        help="Sort order (default: descending)",
    )
    @click.option(
        "--summary",
        is_flag=True,
        help="Show summary statistics grouped by status or specified field",
    )
    @click.option(
        "--group-by",
        type=click.Choice(
            ["status", "programName", "serialNumber", "operator", "hostName", "systemId"],
            case_sensitive=False,
        ),
        help="Group summary by field (implies --summary)",
    )
    def list_results(
        format: str,
        take: int,
        status: Optional[str],
        program_name: Optional[str],
        serial_number: Optional[str],
        part_number: Optional[str],
        operator: Optional[str],
        host_name: Optional[str],
        system_id: Optional[str],
        workspace: Optional[str],
        filter_query: Optional[str],
        substitutions: Tuple[str, ...],
        product_filter: Optional[str],
        product_substitutions: Tuple[str, ...],
        order_by: Optional[str],
        descending: bool,
        summary: bool,
        group_by: Optional[str],
    ) -> None:
        """List test results in Test Monitor."""
        format_output = validate_output_format(format)

        try:
            filter_parts: List[str] = []
            filter_substitutions: List[Any] = []

            if status:
                normalized_status = status.upper().replace("-", "_")
                _append_filter(
                    filter_parts,
                    filter_substitutions,
                    "status.statusType == @{index}",
                    normalized_status,
                )

            _append_filter(
                filter_parts,
                filter_substitutions,
                "programName.Contains(@{index})",
                program_name,
            )
            _append_filter(
                filter_parts,
                filter_substitutions,
                "serialNumber.Contains(@{index})",
                serial_number,
            )
            _append_filter(
                filter_parts,
                filter_substitutions,
                "partNumber.Contains(@{index})",
                part_number,
            )
            _append_filter(
                filter_parts, filter_substitutions, "operator.Contains(@{index})", operator
            )
            _append_filter(
                filter_parts, filter_substitutions, "hostName.Contains(@{index})", host_name
            )
            _append_filter(filter_parts, filter_substitutions, "systemId == @{index}", system_id)

            if workspace:
                workspace_map = get_workspace_map()
                workspace_id = resolve_workspace_filter(workspace, workspace_map)
                _append_filter(
                    filter_parts, filter_substitutions, "workspace == @{index}", workspace_id
                )

            base_filter = " && ".join(filter_parts) if filter_parts else None
            user_subs = _parse_substitutions(substitutions)

            filter_expr, merged_subs = _combine_filter_parts(
                base_filter, filter_substitutions, filter_query, user_subs
            )

            product_filter_expr: Optional[str] = None
            product_subs: List[Any] = []

            if product_filter:
                product_subs = _parse_substitutions(product_substitutions)
                product_filter_expr = product_filter

            if order_by:
                order_by = order_by.upper()

            def result_formatter(item: Dict[str, Any]) -> List[str]:
                status_obj = item.get("status", {}) if isinstance(item, dict) else {}
                status_value = status_obj.get("statusType") or status_obj.get("statusName", "")
                return [
                    status_value,
                    item.get("programName", ""),
                    item.get("partNumber", ""),
                    item.get("serialNumber", ""),
                    _format_date(item.get("startedAt", "")),
                    _format_duration(item.get("totalTimeInSeconds")),
                    item.get("id", ""),
                ]

            # If JSON output, fetch all pages
            if format_output.lower() == "json":
                # Check total count first to warn about large datasets
                _warn_if_large_dataset(
                    endpoint="query-results",
                    filter_expr=filter_expr,
                    substitutions=merged_subs,
                    product_filter=product_filter_expr,
                    product_substitutions=product_subs,
                    order_by=order_by,
                    descending=descending,
                )
                results = _query_all_results(
                    filter_expr,
                    merged_subs,
                    product_filter_expr,
                    product_subs,
                    order_by,
                    descending,
                )

                # Handle --summary flag for JSON output
                if summary or group_by:
                    group_key = group_by.lower() if group_by else "status"
                    group_field_map = {
                        "status": None,  # Use default status grouping in _summarize_results
                        "programname": "programName",
                        "serialnumber": "serialNumber",
                        "operator": "operator",
                        "hostname": "hostName",
                        "systemid": "systemId",
                    }
                    group_field = group_field_map.get(group_key, group_by)
                    summary_stats = _summarize_results(results, group_field)
                    click.echo(json.dumps(summary_stats, indent=2))
                else:
                    mock_resp: Any = FilteredResponse({"results": results})
                    UniversalResponseHandler.handle_list_response(
                        resp=mock_resp,
                        data_key="results",
                        item_name="result",
                        format_output=format_output,
                        formatter_func=result_formatter,
                        headers=[
                            "Status",
                            "Program",
                            "Part Number",
                            "Serial",
                            "Started",
                            "Duration(s)",
                            "ID",
                        ],
                        column_widths=[12, 30, 16, 16, 12, 12, 36],
                        empty_message="No test results found.",
                        enable_pagination=False,
                        page_size=take,
                    )
            else:
                # Interactive pagination for table output
                def fetch_page(
                    cont: Optional[str] = None,
                ) -> Tuple[List[Dict[str, Any]], Optional[str]]:
                    return _fetch_results_page(
                        filter_expr,
                        merged_subs,
                        product_filter_expr,
                        product_subs,
                        order_by,
                        descending,
                        take,
                        cont,
                    )

                # For table output with summary, collect all data first
                if summary or group_by:
                    # Check total count first to warn about large datasets
                    _warn_if_large_dataset(
                        endpoint="query-results",
                        filter_expr=filter_expr,
                        substitutions=merged_subs,
                        product_filter=product_filter_expr,
                        product_substitutions=product_subs,
                        order_by=order_by,
                        descending=descending,
                    )
                    all_results = _query_all_results(
                        filter_expr,
                        merged_subs,
                        product_filter_expr,
                        product_subs,
                        order_by,
                        descending,
                    )
                    group_key = group_by.lower() if group_by else "status"
                    group_field_map = {
                        "status": None,  # Use default status grouping in _summarize_results
                        "programname": "programName",
                        "serialnumber": "serialNumber",
                        "operator": "operator",
                        "hostname": "hostName",
                        "systemid": "systemId",
                    }
                    group_field = group_field_map.get(group_key, group_by)
                    summary_stats = _summarize_results(all_results, group_field)

                    # Display appropriate label based on grouping
                    group_label = group_key if group_key != "status" else "statusType"
                    click.echo(f"\nTest Results Summary (grouped by {group_label}):")
                    click.echo(f"  Total Results: {summary_stats['total']}")
                    if "groups" in summary_stats:
                        for group_name, count in summary_stats["groups"].items():
                            click.echo(f"    {group_name}: {count}")
                    click.echo()
                else:
                    _handle_interactive_pagination(
                        fetch_page_func=fetch_page,
                        data_key="results",
                        item_name="result",
                        format_output=format_output,
                        formatter_func=result_formatter,
                        headers=[
                            "Status",
                            "Program",
                            "Part Number",
                            "Serial",
                            "Started",
                            "Duration(s)",
                            "ID",
                        ],
                        column_widths=[12, 30, 16, 16, 12, 12, 36],
                        empty_message="No test results found.",
                        take=take,
                    )
        except Exception as exc:  # noqa: BLE001
            handle_api_error(exc)

    @product.command(name="get")
    @click.argument("product_id")
    @click.option("--format", "-f", type=click.Choice(["table", "json"]), default="table")
    def get_product(product_id: str, format: str) -> None:
        """Get detailed information about a specific product.

        Args:
            product_id: The ID of the product to retrieve.
            format: Output format (table or json).
        """
        try:
            validate_output_format(format)
            url = f"{_get_testmonitor_base_url()}/products/{product_id}"
            resp = make_api_request("GET", url)
            resp.raise_for_status()

            product = resp.json()

            if format == "json":
                click.echo(json.dumps(product, indent=2))
            else:
                # Table format
                click.echo(f"\nProduct: {product.get('name', 'N/A')} ({product.get('id', 'N/A')})")
                click.echo(f"Part Number: {product.get('partNumber', 'N/A')}")
                click.echo(f"Family: {product.get('family', 'N/A')}")
                workspace = product.get("workspace", "N/A")
                if workspace != "N/A":
                    workspace_name = get_workspace_display_name(workspace)
                    click.echo(f"Workspace: {workspace_name} ({workspace})")
                click.echo(f"Updated: {_format_date(product.get('updatedAt', 'N/A'))}")

                # Display keywords and properties if present
                if product.get("keywords"):
                    click.echo(f"Keywords: {', '.join(product['keywords'])}")
                if product.get("properties"):
                    click.echo("Properties:")
                    for key, value in product["properties"].items():
                        click.echo(f"  {key}: {value}")
                click.echo()
        except Exception as exc:  # noqa: BLE001
            handle_api_error(exc)

    @result.command(name="get")
    @click.argument("result_id")
    @click.option("--include-steps", is_flag=True, help="Include step details in output.")
    @click.option(
        "--include-measurements",
        is_flag=True,
        help="Include measurement data from steps.",
    )
    @click.option("--format", "-f", type=click.Choice(["table", "json"]), default="table")
    def get_result(
        result_id: str, include_steps: bool, include_measurements: bool, format: str
    ) -> None:
        """Get detailed information about a specific test result.

        Args:
            result_id: The ID of the result to retrieve.
            include_steps: Include step details in output.
            include_measurements: Include measurement data from steps.
            format: Output format (table or json).
        """
        try:
            validate_output_format(format)
            url = f"{_get_testmonitor_base_url()}/results/{result_id}"
            resp = make_api_request("GET", url)
            resp.raise_for_status()

            result = resp.json()

            # Fetch steps if requested
            steps: List[Dict[str, Any]] = []
            if include_steps or include_measurements:
                steps_url = f"{_get_testmonitor_base_url()}/query-steps"
                steps_body = {"filter": "resultId == @0", "substitutions": [result_id]}
                steps_resp = make_api_request("POST", steps_url, payload=steps_body)
                steps_resp.raise_for_status()
                steps = steps_resp.json().get("steps", [])
                result["steps"] = steps

            if format == "json":
                click.echo(json.dumps(result, indent=2))
            else:
                # Table format - detailed view
                status = result.get("status", {})
                status_type = status.get("statusType", "N/A")
                click.echo(f"\nTest Result: {result.get('programName', 'N/A')} ({result_id})")
                click.echo(f"Status: {status_type}")
                click.echo(f"Part Number: {result.get('partNumber', 'N/A')}")
                click.echo(f"Serial Number: {result.get('serialNumber', 'N/A')}")
                click.echo(f"Started: {_format_date(result.get('startedAt', 'N/A'))}")
                click.echo(f"Updated: {_format_date(result.get('updatedAt', 'N/A'))}")
                click.echo(f"Duration: {_format_duration(result.get('totalTimeInSeconds', 0))}")
                click.echo(f"System ID: {result.get('systemId', 'N/A')}")
                click.echo(f"Host: {result.get('hostName', 'N/A')}")
                click.echo(f"Operator: {result.get('operator', 'N/A')}")

                # Display steps if requested or when measurements are requested
                if (include_steps or include_measurements) and steps:
                    click.echo("\nSteps:")
                    for i, step in enumerate(steps, 1):
                        step_status = step.get("status", {})
                        step_status_type = step_status.get("statusType", "N/A")
                        click.echo(
                            f"  {i}. {step.get('name', 'N/A')} [{step_status_type}] "
                            f"({_format_duration(step.get('totalTimeInSeconds', 0))})"
                        )

                        # Display measurements if requested
                        if include_measurements and step.get("outputs"):
                            for output in step["outputs"]:
                                output_name = output.get("name", "N/A")
                                output_value = output.get("value", "N/A")
                                click.echo(f"      • {output_name}: {output_value}")
                click.echo()
        except Exception as exc:  # noqa: BLE001
            handle_api_error(exc)
