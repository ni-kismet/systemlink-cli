"""CLI commands for managing SystemLink assets.

Provides CLI commands for listing, querying, and managing assets in the
Asset Management service (niapm v1). Supports filtering by model, serial
number, bus type, asset type, calibration status, and connection state.
"""

import json
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


def _get_asset_base_url() -> str:
    """Get the base URL for the Asset Management API."""
    return f"{get_base_url()}/niapm/v1"


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


def _build_asset_filter(
    model: Optional[str] = None,
    serial_number: Optional[str] = None,
    bus_type: Optional[str] = None,
    asset_type: Optional[str] = None,
    calibration_status: Optional[str] = None,
    connected: bool = False,
    workspace_id: Optional[str] = None,
    custom_filter: Optional[str] = None,
) -> Optional[str]:
    """Build API filter expression from convenience options.

    Args:
        model: Filter by model name (contains match).
        serial_number: Filter by serial number (exact match).
        bus_type: Filter by bus type.
        asset_type: Filter by asset type.
        calibration_status: Filter by calibration status.
        connected: Show only connected/present assets.
        workspace_id: Filter by workspace ID.
        custom_filter: Advanced user-provided filter expression.

    Returns:
        Combined filter expression string, or None if no filters.
    """
    parts: List[str] = []

    if model:
        escaped = _escape_filter_value(model)
        parts.append(f'ModelName.Contains("{escaped}")')
    if serial_number:
        escaped = _escape_filter_value(serial_number)
        parts.append(f'SerialNumber = "{escaped}"')
    if bus_type:
        parts.append(f'BusType = "{bus_type}"')
    if asset_type:
        parts.append(f'AssetType = "{asset_type}"')
    if calibration_status:
        parts.append(f'CalibrationStatus = "{calibration_status}"')
    if connected:
        parts.append(
            'Location.AssetState.SystemConnection = "CONNECTED"'
            ' and Location.AssetState.AssetPresence = "PRESENT"'
        )
    if workspace_id:
        escaped = _escape_filter_value(workspace_id)
        parts.append(f'Workspace = "{escaped}"')
    if custom_filter:
        parts.append(custom_filter)

    return " and ".join(parts) if parts else None


def _query_all_assets(
    filter_expr: Optional[str],
    order_by: Optional[str],
    descending: bool,
    take: Optional[int] = 10000,
    calibratable_only: bool = False,
) -> List[Dict[str, Any]]:
    """Query assets using skip/take pagination.

    Fetches up to ``take`` items (default 10,000 for performance).

    Args:
        filter_expr: Optional API filter expression.
        order_by: Field to order by.
        descending: Whether to return results in descending order.
        take: Maximum number of items to fetch.
        calibratable_only: Only return calibratable assets.

    Returns:
        List of asset objects (up to ``take`` count).
    """
    url = f"{_get_asset_base_url()}/query-assets"
    all_assets: List[Dict[str, Any]] = []
    page_size = 1000  # API max per request
    skip = 0

    while True:
        if take is not None:
            remaining = take - len(all_assets)
            if remaining <= 0:
                break
            batch_size = min(page_size, remaining)
        else:
            batch_size = page_size

        payload: Dict[str, Any] = {
            "skip": skip,
            "take": batch_size,
            "descending": descending,
            "returnCount": True,
        }

        if filter_expr:
            payload["filter"] = filter_expr
        if order_by:
            payload["orderBy"] = order_by
        if calibratable_only:
            payload["calibratableOnly"] = True

        resp = make_api_request("POST", url, payload=payload)
        data = resp.json()
        assets = data.get("assets", []) if isinstance(data, dict) else []

        all_assets.extend(assets)
        skip += len(assets)

        # Stop if we got fewer than requested (last page)
        if len(assets) < batch_size:
            break
        if take is not None and len(all_assets) >= take:
            break

    return all_assets[:take] if take is not None else all_assets


def _fetch_assets_page(
    filter_expr: Optional[str],
    order_by: Optional[str],
    descending: bool,
    take: int,
    skip: int,
    calibratable_only: bool = False,
) -> Tuple[List[Dict[str, Any]], int]:
    """Fetch a single page of assets.

    Args:
        filter_expr: Optional API filter expression.
        order_by: Field to order by.
        descending: Whether to return results in descending order.
        take: Number of items to fetch.
        skip: Number of items to skip.
        calibratable_only: Only return calibratable assets.

    Returns:
        Tuple of (assets list, total count from server).
    """
    url = f"{_get_asset_base_url()}/query-assets"
    payload: Dict[str, Any] = {
        "skip": skip,
        "take": take,
        "descending": descending,
        "returnCount": True,
    }

    if filter_expr:
        payload["filter"] = filter_expr
    if order_by:
        payload["orderBy"] = order_by
    if calibratable_only:
        payload["calibratableOnly"] = True

    resp = make_api_request("POST", url, payload=payload)
    data = resp.json()

    assets = data.get("assets", []) if isinstance(data, dict) else []
    total_count = data.get("totalCount", 0) if isinstance(data, dict) else 0

    return assets, total_count


def _handle_asset_interactive_pagination(
    filter_expr: Optional[str],
    order_by: Optional[str],
    descending: bool,
    take: int,
    calibratable_only: bool,
    formatter_func: Any,
    headers: List[str],
    column_widths: List[int],
    empty_message: str,
) -> None:
    """Handle interactive skip/take pagination for table output.

    Args:
        filter_expr: Optional API filter expression.
        order_by: Field to order by.
        descending: Whether to return results in descending order.
        take: Number of items per page.
        calibratable_only: Only return calibratable assets.
        formatter_func: Function to format each item for display.
        headers: Column headers for the table.
        column_widths: Column widths for the table.
        empty_message: Message to display when no items are found.
    """
    skip = 0
    shown_count = 0

    while True:
        page_items, total_count = _fetch_assets_page(
            filter_expr, order_by, descending, take, skip, calibratable_only
        )

        if not page_items:
            if shown_count == 0:
                click.echo(empty_message)
            break

        shown_count += len(page_items)
        skip += len(page_items)

        mock_resp: Any = FilteredResponse({"assets": page_items})
        UniversalResponseHandler.handle_list_response(
            resp=mock_resp,
            data_key="assets",
            item_name="asset",
            format_output="table",
            formatter_func=formatter_func,
            headers=headers,
            column_widths=column_widths,
            empty_message=empty_message,
            enable_pagination=False,
            page_size=take,
            total_count=total_count,
            shown_count=shown_count,
        )

        # Flush stdout so the table is visible before prompting
        try:
            sys.stdout.flush()
        except Exception:
            # stdout may be closed or invalid (e.g., when piped); ignore flush errors
            pass

        # Check if there are more results
        if shown_count >= total_count:
            break

        if not click.confirm("Show next set of results?", default=True):
            break


def _warn_if_large_dataset(
    filter_expr: Optional[str],
    calibratable_only: bool = False,
) -> None:
    """Check dataset size and warn user if fetching large number of items.

    Args:
        filter_expr: Optional API filter expression.
        calibratable_only: Only count calibratable assets.
    """
    url = f"{_get_asset_base_url()}/query-assets"
    payload: Dict[str, Any] = {
        "skip": 0,
        "take": 1,
        "returnCount": True,
    }

    if filter_expr:
        payload["filter"] = filter_expr
    if calibratable_only:
        payload["calibratableOnly"] = True

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
        # Best-effort warning: if we cannot determine total count
        # (e.g., network error), continue without the size warning.
        pass


def _get_asset_location_display(asset: Dict[str, Any]) -> str:
    """Get a display string for an asset's location.

    Args:
        asset: Asset dictionary.

    Returns:
        Location display string.
    """
    location = asset.get("location")
    if not isinstance(location, dict):
        return ""

    minion_id = location.get("minionId", "")
    physical = location.get("physicalLocation", "")
    slot = location.get("slotNumber")

    display = minion_id or physical
    if slot is not None:
        display = f"{display} (Slot {slot})" if display else f"Slot {slot}"

    return display


def _format_asset_detail(asset: Dict[str, Any], workspace_map: Dict[str, str]) -> None:
    """Format and display detailed asset information.

    Args:
        asset: Asset dictionary.
        workspace_map: Workspace ID to name mapping.
    """
    name = asset.get("name", "Unknown")
    asset_id = asset.get("id", "")
    click.echo(f"Asset: {name} ({asset_id})")
    click.echo(f"  Model: {asset.get('modelName', 'N/A')}")
    click.echo(f"  Serial Number: {asset.get('serialNumber', 'N/A')}")
    click.echo(f"  Part Number: {asset.get('partNumber', 'N/A')}")
    click.echo(f"  Vendor: {asset.get('vendorName', 'N/A')}")
    click.echo(f"  Bus Type: {asset.get('busType', 'N/A')}")
    click.echo(f"  Asset Type: {asset.get('assetType', 'N/A')}")
    click.echo(f"  Firmware: {asset.get('firmwareVersion', 'N/A')}")
    click.echo(f"  Hardware: {asset.get('hardwareVersion', 'N/A')}")

    # Workspace
    ws_id = asset.get("workspace", "")
    ws_name = get_workspace_display_name(ws_id, workspace_map)
    click.echo(f"  Workspace: {ws_name} ({ws_id})")

    # Location
    location = asset.get("location")
    if isinstance(location, dict):
        loc_display = _get_asset_location_display(asset)
        click.echo(f"  Location: {loc_display}")

        state = location.get("state")
        if isinstance(state, dict):
            click.echo(f"  Presence: {state.get('assetPresence', 'N/A')}")
            click.echo(f"  System Connection: {state.get('systemConnection', 'N/A')}")

    # Calibration
    click.echo(f"  Calibration Status: {asset.get('calibrationStatus', 'N/A')}")

    ext_cal = asset.get("externalCalibration")
    if isinstance(ext_cal, dict):
        click.echo(f"  Last Calibrated: {ext_cal.get('date', 'N/A')}")
        click.echo(f"  Next Due: {ext_cal.get('nextRecommendedDate', 'N/A')}")

    # Keywords
    keywords = asset.get("keywords")
    if keywords and isinstance(keywords, list):
        click.echo(f"  Keywords: {', '.join(str(k) for k in keywords)}")

    # Properties
    properties = asset.get("properties")
    if properties and isinstance(properties, dict):
        click.echo("  Properties:")
        for key, value in properties.items():
            click.echo(f"    {key}: {value}")


def register_asset_commands(cli: Any) -> None:
    """Register the 'asset' command group and its subcommands.

    Args:
        cli: Click CLI group to register commands on.
    """

    @cli.group()
    def asset() -> None:
        """Manage SystemLink assets.

        Query, inspect, and manage hardware assets tracked by the Asset
        Management service.  Supports filtering by model, serial number, bus
        type, calibration status, and connection state.

        Filter syntax uses the Asset API expression language:
          ModelName.Contains("PXI"), SerialNumber = "01BB877A",
          BusType = "PCI_PXI", and/or operators.
        """

    # ------------------------------------------------------------------
    # Phase 1: list, get, summary
    # ------------------------------------------------------------------

    @asset.command(name="list")
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
    @click.option("--model", help="Filter by model name (contains match)")
    @click.option("--serial-number", help="Filter by serial number (exact match)")
    @click.option(
        "--bus-type",
        type=click.Choice(
            ["BUILT_IN_SYSTEM", "PCI_PXI", "USB", "GPIB", "VXI", "SERIAL", "TCP_IP", "CRIO"],
            case_sensitive=True,
        ),
        help="Filter by bus type",
    )
    @click.option(
        "--asset-type",
        type=click.Choice(
            ["GENERIC", "DEVICE_UNDER_TEST", "FIXTURE", "SYSTEM"],
            case_sensitive=True,
        ),
        help="Filter by asset type",
    )
    @click.option(
        "--calibration-status",
        type=click.Choice(
            [
                "OK",
                "APPROACHING_RECOMMENDED_DUE_DATE",
                "PAST_RECOMMENDED_DUE_DATE",
                "OUT_FOR_CALIBRATION",
            ],
            case_sensitive=True,
        ),
        help="Filter by calibration status",
    )
    @click.option(
        "--connected",
        is_flag=True,
        help="Show only assets in connected systems (CONNECTED + PRESENT)",
    )
    @click.option(
        "--calibratable",
        is_flag=True,
        help="Show only calibratable assets",
    )
    @click.option("--workspace", "-w", help="Filter by workspace name or ID")
    @click.option(
        "--filter",
        "filter_query",
        help=(
            "Advanced API filter expression "
            '(e.g., \'ModelName.Contains("PXI") and BusType = "PCI_PXI"\')'
        ),
    )
    @click.option(
        "--order-by",
        type=click.Choice(["LAST_UPDATED_TIMESTAMP", "ID"], case_sensitive=False),
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
        help="Show summary statistics instead of listing assets",
    )
    def list_assets(
        format: str,
        take: int,
        model: Optional[str],
        serial_number: Optional[str],
        bus_type: Optional[str],
        asset_type: Optional[str],
        calibration_status: Optional[str],
        connected: bool,
        calibratable: bool,
        workspace: Optional[str],
        filter_query: Optional[str],
        order_by: Optional[str],
        descending: bool,
        summary: bool,
    ) -> None:
        """List and query assets with optional filtering.

        Supports convenience filters (--model, --serial-number, --bus-type,
        etc.) that are translated to API filter expressions.  Combine multiple
        options — they are joined with 'and'.

        For advanced queries use --filter with the Asset API filter syntax:
        ModelName.Contains("PXI") and BusType = "PCI_PXI"
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

            filter_expr = _build_asset_filter(
                model=model,
                serial_number=serial_number,
                bus_type=bus_type,
                asset_type=asset_type,
                calibration_status=calibration_status,
                connected=connected,
                workspace_id=workspace_id,
                custom_filter=filter_query,
            )

            if order_by:
                order_by = order_by.upper()

            def asset_formatter(item: Dict[str, Any]) -> List[str]:
                ws_id = item.get("workspace", "")
                ws_name = get_workspace_display_name(ws_id, workspace_map)
                return [
                    item.get("name", ""),
                    item.get("modelName", ""),
                    item.get("serialNumber", ""),
                    item.get("busType", ""),
                    item.get("calibrationStatus", ""),
                    _get_asset_location_display(item),
                    ws_name,
                    item.get("id", ""),
                ]

            headers = [
                "Name",
                "Model",
                "Serial Number",
                "Bus Type",
                "Calibration",
                "Location",
                "Workspace",
                "ID",
            ]
            column_widths = [24, 20, 16, 12, 16, 16, 16, 36]

            if format_output.lower() == "json":
                _warn_if_large_dataset(filter_expr, calibratable)
                assets = _query_all_assets(
                    filter_expr, order_by, descending, calibratable_only=calibratable
                )

                if summary:
                    summary_stats = _summarize_assets(assets)
                    click.echo(json.dumps(summary_stats, indent=2))
                else:
                    mock_resp: Any = FilteredResponse({"assets": assets})
                    UniversalResponseHandler.handle_list_response(
                        resp=mock_resp,
                        data_key="assets",
                        item_name="asset",
                        format_output=format_output,
                        formatter_func=asset_formatter,
                        headers=headers,
                        column_widths=column_widths,
                        empty_message="No assets found.",
                        enable_pagination=False,
                        page_size=take,
                    )
            else:
                if summary:
                    _warn_if_large_dataset(filter_expr, calibratable)
                    all_assets = _query_all_assets(
                        filter_expr, order_by, descending, calibratable_only=calibratable
                    )
                    summary_stats = _summarize_assets(all_assets)
                    click.echo("\nAsset Summary Statistics:")
                    click.echo(f"  Total Assets: {summary_stats['total']}")
                    click.echo(
                        f"  Bus Types: {', '.join(summary_stats.get('busTypes', {}).keys()) or 'N/A'}"
                    )
                    if summary_stats.get("truncated"):
                        click.echo(f"  Note: {summary_stats['note']}", err=True)
                    click.echo()
                else:
                    _handle_asset_interactive_pagination(
                        filter_expr=filter_expr,
                        order_by=order_by,
                        descending=descending,
                        take=take,
                        calibratable_only=calibratable,
                        formatter_func=asset_formatter,
                        headers=headers,
                        column_widths=column_widths,
                        empty_message="No assets found.",
                    )
        except Exception as exc:  # noqa: BLE001
            handle_api_error(exc)

    @asset.command(name="get")
    @click.argument("asset_id")
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    @click.option(
        "--include-calibration",
        is_flag=True,
        help="Include calibration history in output",
    )
    def get_asset(
        asset_id: str,
        format: str,
        include_calibration: bool,
    ) -> None:
        """Get detailed information about a specific asset.

        ASSET_ID is the unique identifier of the asset.
        """
        format_output = validate_output_format(format)

        try:
            url = f"{_get_asset_base_url()}/assets/{asset_id}"
            resp = make_api_request("GET", url)
            asset_data = resp.json()

            # Optionally fetch calibration history
            if include_calibration:
                try:
                    cal_url = f"{_get_asset_base_url()}/assets/{asset_id}/history/calibration"
                    cal_resp = make_api_request("GET", cal_url)
                    cal_data = cal_resp.json()
                    cal_entries = (
                        cal_data.get("calibrationHistory", []) if isinstance(cal_data, dict) else []
                    )
                    asset_data["calibrationHistory"] = cal_entries
                except Exception:
                    asset_data["calibrationHistory"] = []

            if format_output.lower() == "json":
                click.echo(json.dumps(asset_data, indent=2))
            else:
                try:
                    workspace_map = get_workspace_map()
                except Exception:
                    workspace_map = {}
                _format_asset_detail(asset_data, workspace_map)

                if include_calibration and asset_data.get("calibrationHistory"):
                    click.echo("\nCalibration History:")
                    for entry in asset_data["calibrationHistory"]:
                        date = entry.get("date", "N/A")
                        entry_type = entry.get("entryType", "N/A")
                        click.echo(f"  {date} — {entry_type}")

        except Exception as exc:  # noqa: BLE001
            handle_api_error(exc)

    @asset.command(name="summary")
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    def asset_summary(format: str) -> None:
        """Show fleet-wide asset summary statistics.

        Displays counts for total, active, in-use assets and calibration
        status breakdown.
        """
        format_output = validate_output_format(format)

        try:
            url = f"{_get_asset_base_url()}/asset-summary"
            resp = make_api_request("GET", url)
            data = resp.json()

            if format_output.lower() == "json":
                click.echo(json.dumps(data, indent=2))
            else:
                click.echo("\nAsset Fleet Summary:")
                click.echo(f"  Total Assets: {data.get('total', 0)}")
                click.echo(f"  Active (in connected system): {data.get('active', 0)}")
                click.echo(f"  Not Active: {data.get('notActive', 0)}")
                click.echo(f"  In Use: {data.get('inUse', 0)}")
                click.echo(f"  Not In Use: {data.get('notInUse', 0)}")
                click.echo(f"  With Alarms: {data.get('withAlarms', 0)}")
                click.echo("\nCalibration Status:")
                click.echo(
                    f"  Approaching Due Date: " f"{data.get('approachingRecommendedDueDate', 0)}"
                )
                click.echo(f"  Past Due Date: {data.get('pastRecommendedDueDate', 0)}")
                click.echo(f"  Out for Calibration: {data.get('outForCalibration', 0)}")
                click.echo(f"  Total Calibratable: {data.get('totalCalibrated', 0)}")
                click.echo()

        except Exception as exc:  # noqa: BLE001
            handle_api_error(exc)

    # ------------------------------------------------------------------
    # Phase 2: calibration, location-history
    # ------------------------------------------------------------------

    @asset.command(name="calibration")
    @click.argument("asset_id")
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
        help="Number of history entries to return",
    )
    def asset_calibration(
        asset_id: str,
        format: str,
        take: int,
    ) -> None:
        """Get calibration history for a specific asset.

        ASSET_ID is the unique identifier of the asset.
        """
        format_output = validate_output_format(format)

        try:
            url = (
                f"{_get_asset_base_url()}/assets/{asset_id}/history/calibration"
                f"?Skip=0&Take={take}"
            )
            resp = make_api_request("GET", url)
            data = resp.json()

            entries = data.get("calibrationHistory", []) if isinstance(data, dict) else []

            def calibration_formatter(item: Dict[str, Any]) -> List[str]:
                return [
                    item.get("date", ""),
                    item.get("entryType", ""),
                    str(item.get("isLimited", "")),
                    item.get("resolvedDueDate", ""),
                    str(item.get("recommendedInterval", "")),
                    item.get("comments", ""),
                ]

            if format_output.lower() == "json":
                click.echo(json.dumps(entries, indent=2))
            else:
                mock_resp: Any = FilteredResponse({"calibrationHistory": entries})
                UniversalResponseHandler.handle_list_response(
                    resp=mock_resp,
                    data_key="calibrationHistory",
                    item_name="calibration entry",
                    format_output=format_output,
                    formatter_func=calibration_formatter,
                    headers=[
                        "Date",
                        "Type",
                        "Limited",
                        "Next Due",
                        "Interval (mo)",
                        "Comments",
                    ],
                    column_widths=[20, 12, 8, 20, 14, 30],
                    empty_message="No calibration history found.",
                    enable_pagination=True,
                    page_size=take,
                )

        except Exception as exc:  # noqa: BLE001
            handle_api_error(exc)

    @asset.command(name="location-history")
    @click.argument("asset_id")
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
        help="Number of history entries to return",
    )
    @click.option(
        "--from",
        "date_from",
        type=str,
        default=None,
        help="Start of date range (ISO-8601, e.g., 2025-12-01T00:00:00Z)",
    )
    @click.option(
        "--to",
        "date_to",
        type=str,
        default=None,
        help="End of date range (ISO-8601, e.g., 2025-12-02T00:00:00Z)",
    )
    def asset_location_history(
        asset_id: str,
        format: str,
        take: int,
        date_from: Optional[str],
        date_to: Optional[str],
    ) -> None:
        """Get location/connection history for a specific asset.

        ASSET_ID is the unique identifier of the asset.

        Use --from and --to for temporal correlation (e.g., confirming an
        asset was present in a system at the time of a test).
        """
        format_output = validate_output_format(format)

        try:
            url = f"{_get_asset_base_url()}/assets/{asset_id}/history/query-location"
            payload: Dict[str, Any] = {
                "skip": 0,
                "take": take,
            }
            if date_from:
                payload["startTimestamp"] = date_from
            if date_to:
                payload["endTimestamp"] = date_to

            resp = make_api_request("POST", url, payload=payload)
            data = resp.json()

            entries = data.get("connectionHistory", []) if isinstance(data, dict) else []

            def location_formatter(item: Dict[str, Any]) -> List[str]:
                return [
                    item.get("timestamp", ""),
                    item.get("minionId", ""),
                    str(item.get("slotNumber", "")),
                    item.get("systemConnection", ""),
                    item.get("assetPresence", ""),
                ]

            if format_output.lower() == "json":
                click.echo(json.dumps(entries, indent=2))
            else:
                mock_resp: Any = FilteredResponse({"connectionHistory": entries})
                UniversalResponseHandler.handle_list_response(
                    resp=mock_resp,
                    data_key="connectionHistory",
                    item_name="location entry",
                    format_output=format_output,
                    formatter_func=location_formatter,
                    headers=["Timestamp", "Minion ID", "Slot", "Connection", "Presence"],
                    column_widths=[24, 30, 6, 14, 12],
                    empty_message="No location history found.",
                    enable_pagination=True,
                    page_size=take,
                )

        except Exception as exc:  # noqa: BLE001
            handle_api_error(exc)

    # ------------------------------------------------------------------
    # Phase 3: create, update, delete (mutations)
    # ------------------------------------------------------------------

    @asset.command(name="create")
    @click.option("--model-name", required=True, help="Model name of the asset")
    @click.option("--model-number", default=None, help="Model number")
    @click.option("--serial-number", default=None, help="Serial number")
    @click.option("--vendor-name", default=None, help="Vendor name")
    @click.option("--vendor-number", default=None, help="Vendor number")
    @click.option("--part-number", default=None, help="Part number")
    @click.option("--name", "asset_name", default=None, help="Display name for the asset")
    @click.option(
        "--bus-type",
        type=click.Choice(
            ["BUILT_IN_SYSTEM", "PCI_PXI", "USB", "GPIB", "VXI", "SERIAL", "TCP_IP", "CRIO"],
            case_sensitive=True,
        ),
        default=None,
        help="Bus type",
    )
    @click.option(
        "--asset-type",
        type=click.Choice(
            ["GENERIC", "DEVICE_UNDER_TEST", "FIXTURE", "SYSTEM"],
            case_sensitive=True,
        ),
        default=None,
        help="Asset type",
    )
    @click.option("--firmware-version", default=None, help="Firmware version")
    @click.option("--hardware-version", default=None, help="Hardware version")
    @click.option("--workspace", "-w", default=None, help="Workspace name or ID")
    @click.option(
        "--keyword",
        "keywords",
        multiple=True,
        help="Keyword to associate (repeatable)",
    )
    @click.option(
        "--property",
        "properties",
        multiple=True,
        help="Property in key=value format (repeatable)",
    )
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    def create_asset(
        model_name: str,
        model_number: Optional[str],
        serial_number: Optional[str],
        vendor_name: Optional[str],
        vendor_number: Optional[str],
        part_number: Optional[str],
        asset_name: Optional[str],
        bus_type: Optional[str],
        asset_type: Optional[str],
        firmware_version: Optional[str],
        hardware_version: Optional[str],
        workspace: Optional[str],
        keywords: Tuple[str, ...],
        properties: Tuple[str, ...],
        format: str,
    ) -> None:
        """Create a new asset.

        Requires at minimum a --model-name.  Additional fields can be set
        via options.
        """
        check_readonly_mode("create an asset")
        format_output = validate_output_format(format)

        try:
            asset_data: Dict[str, Any] = {
                "modelName": model_name,
            }

            if model_number:
                asset_data["modelNumber"] = model_number
            if serial_number:
                asset_data["serialNumber"] = serial_number
            if vendor_name:
                asset_data["vendorName"] = vendor_name
            if vendor_number:
                asset_data["vendorNumber"] = vendor_number
            if part_number:
                asset_data["partNumber"] = part_number
            if asset_name:
                asset_data["name"] = asset_name
            if bus_type:
                asset_data["busType"] = bus_type
            if asset_type:
                asset_data["assetType"] = asset_type
            if firmware_version:
                asset_data["firmwareVersion"] = firmware_version
            if hardware_version:
                asset_data["hardwareVersion"] = hardware_version

            # Resolve workspace
            if workspace:
                try:
                    ws_map = get_workspace_map()
                    ws_id = resolve_workspace_filter(workspace, ws_map)
                    asset_data["workspace"] = ws_id
                except Exception:
                    asset_data["workspace"] = workspace

            if keywords:
                asset_data["keywords"] = list(keywords)

            if properties:
                asset_data["properties"] = _parse_properties(properties)

            url = f"{_get_asset_base_url()}/assets"
            payload: Dict[str, Any] = {"assets": [asset_data]}
            resp = make_api_request("POST", url, payload=payload)

            if format_output.lower() == "json":
                click.echo(json.dumps(resp.json(), indent=2))
            else:
                format_success(
                    "Asset created",
                    {"Model": model_name, "Serial": serial_number or "N/A"},
                )

        except Exception as exc:  # noqa: BLE001
            handle_api_error(exc)

    @asset.command(name="update")
    @click.argument("asset_id")
    @click.option("--name", "asset_name", default=None, help="Update display name")
    @click.option("--model-name", default=None, help="Update model name")
    @click.option("--model-number", default=None, help="Update model number")
    @click.option("--serial-number", default=None, help="Update serial number")
    @click.option("--vendor-name", default=None, help="Update vendor name")
    @click.option("--part-number", default=None, help="Update part number")
    @click.option("--firmware-version", default=None, help="Update firmware version")
    @click.option("--hardware-version", default=None, help="Update hardware version")
    @click.option(
        "--keyword",
        "keywords",
        multiple=True,
        help="Replace keywords (repeatable)",
    )
    @click.option(
        "--property",
        "properties",
        multiple=True,
        help="Replace properties in key=value format (repeatable)",
    )
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    def update_asset(
        asset_id: str,
        asset_name: Optional[str],
        model_name: Optional[str],
        model_number: Optional[str],
        serial_number: Optional[str],
        vendor_name: Optional[str],
        part_number: Optional[str],
        firmware_version: Optional[str],
        hardware_version: Optional[str],
        keywords: Tuple[str, ...],
        properties: Tuple[str, ...],
        format: str,
    ) -> None:
        """Update an existing asset's properties.

        ASSET_ID is the unique identifier of the asset to update.
        Only the specified fields are changed; others remain unchanged.
        """
        check_readonly_mode("update an asset")
        format_output = validate_output_format(format)

        try:
            # Build update payload — include ID and only changed fields
            update_data: Dict[str, Any] = {"id": asset_id}

            if asset_name is not None:
                update_data["name"] = asset_name
            if model_name is not None:
                update_data["modelName"] = model_name
            if model_number is not None:
                update_data["modelNumber"] = model_number
            if serial_number is not None:
                update_data["serialNumber"] = serial_number
            if vendor_name is not None:
                update_data["vendorName"] = vendor_name
            if part_number is not None:
                update_data["partNumber"] = part_number
            if firmware_version is not None:
                update_data["firmwareVersion"] = firmware_version
            if hardware_version is not None:
                update_data["hardwareVersion"] = hardware_version

            if keywords:
                update_data["keywords"] = list(keywords)

            if properties:
                update_data["properties"] = _parse_properties(properties)

            url = f"{_get_asset_base_url()}/update-assets"
            payload: Dict[str, Any] = {"assets": [update_data]}
            resp = make_api_request("POST", url, payload=payload)

            if format_output.lower() == "json":
                click.echo(json.dumps(resp.json(), indent=2))
            else:
                format_success("Asset updated", {"ID": asset_id})

        except Exception as exc:  # noqa: BLE001
            handle_api_error(exc)

    @asset.command(name="delete")
    @click.argument("asset_id")
    @click.option(
        "--force",
        is_flag=True,
        help="Delete without confirmation",
    )
    def delete_asset(
        asset_id: str,
        force: bool,
    ) -> None:
        """Delete an asset.

        ASSET_ID is the unique identifier of the asset to delete.
        """
        check_readonly_mode("delete an asset")

        try:
            # Fetch asset info for confirmation display
            try:
                info_url = f"{_get_asset_base_url()}/assets/{asset_id}"
                info_resp = make_api_request("GET", info_url)
                info = info_resp.json()
                display_name = info.get("name") or info.get("modelName") or asset_id
            except Exception:
                display_name = asset_id

            if not force:
                if not click.confirm(f"Are you sure you want to delete asset '{display_name}'?"):
                    click.echo("Delete cancelled.")
                    sys.exit(ExitCodes.SUCCESS)

            url = f"{_get_asset_base_url()}/delete-assets"
            payload: Dict[str, Any] = {"ids": [asset_id]}
            make_api_request("POST", url, payload=payload)

            format_success("Asset deleted", {"Name": display_name, "ID": asset_id})

        except Exception as exc:  # noqa: BLE001
            handle_api_error(exc)


def _summarize_assets(
    assets: List[Dict[str, Any]],
    max_items: Optional[int] = 10000,
) -> Dict[str, Any]:
    """Summarize asset data by aggregating bus types and calibration status.

    Args:
        assets: List of asset objects.
        max_items: Maximum items that were fetched.

    Returns:
        Dictionary with summary statistics.
    """
    summary: Dict[str, Any] = {"total": len(assets)}

    if max_items is not None and len(assets) >= max_items:
        summary["truncated"] = True
        summary["note"] = f"Results limited to {max_items} items"

    # Group by bus type
    bus_types: Dict[str, int] = {}
    for a in assets:
        bt = str(a.get("busType", "N/A"))
        bus_types[bt] = bus_types.get(bt, 0) + 1
    summary["busTypes"] = bus_types

    # Group by calibration status
    cal_statuses: Dict[str, int] = {}
    for a in assets:
        cs = str(a.get("calibrationStatus", "N/A"))
        cal_statuses[cs] = cal_statuses.get(cs, 0) + 1
    summary["calibrationStatuses"] = cal_statuses

    return summary
