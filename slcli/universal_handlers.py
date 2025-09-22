"""Enhanced response handlers for all CLI commands."""

import json
import sys
from typing import Dict, List, Any, Optional, Union, Callable

import click
import requests

from .utils import ExitCodes, handle_api_error, format_success


class FilteredResponse:
    """Mock response class for use with UniversalResponseHandler.

    This class mimics a requests.Response object to allow filtered data
    to be passed to UniversalResponseHandler without making additional API calls.
    """

    def __init__(self, data: Dict[str, Any], status_code: int = 200):
        """Initialize with data and optional status code.

        Args:
            data: Dictionary containing the response data
            status_code: HTTP status code to return (default: 200)
        """
        self._data = data
        self._status_code = status_code

    def json(self) -> Dict[str, Any]:
        """Return the response data as JSON."""
        return self._data

    @property
    def status_code(self) -> int:
        """Return the HTTP status code."""
        return self._status_code


class UniversalResponseHandler:
    """Universal response handler for all CLI commands."""

    @staticmethod
    def handle_list_response(
        resp: Union[requests.Response, "FilteredResponse"],
        data_key: str,
        item_name: str,
        format_output: str,
        formatter_func: Optional[Callable[[Dict[str, Any]], List[str]]] = None,
        headers: Optional[List[str]] = None,
        column_widths: Optional[List[int]] = None,
        empty_message: Optional[str] = None,
        enable_pagination: bool = True,
        page_size: int = 25,
    ) -> None:
        """Handle list response with standardized formatting and optional pagination.

        Args:
            resp: API response
            data_key: Key to extract items from response
            item_name: Name of item type (for messages)
            format_output: 'table' or 'json'
            formatter_func: Function to format table rows
            headers: Table headers
            column_widths: Table column widths
            empty_message: Message when no items found
            enable_pagination: Whether to enable pagination for table output
            page_size: Number of items per page
        """
        from .cli_utils import paginate_list_output
        from .table_utils import output_formatted_list

        try:
            data = resp.json()
            items = data.get(data_key, []) if isinstance(data, dict) else []

            if not empty_message:
                empty_message = f"No {item_name}s found."

            if enable_pagination and format_output.lower() == "table":
                # Use pagination for table output
                paginate_list_output(
                    items,
                    page_size=page_size,
                    format_output=format_output,
                    formatter_func=formatter_func,
                    headers=headers,
                    column_widths=column_widths,
                    empty_message=empty_message,
                    total_label=f"{item_name}(s)",
                )
            elif format_output.lower() == "json":
                # For JSON format, always output all items (no display pagination)
                click.echo(json.dumps(items, indent=2))
            elif formatter_func and headers and column_widths:
                # Use traditional output (no pagination)
                output_formatted_list(
                    items,
                    format_output,
                    headers,
                    column_widths,
                    formatter_func,
                    empty_message,
                    f"{item_name}(s)",
                )
            else:
                # Fallback to simple JSON/basic formatting
                if format_output.lower() == "json":
                    click.echo(json.dumps(items, indent=2))
                else:
                    if not items:
                        click.echo(empty_message)
                    else:
                        for item in items:
                            click.echo(f"• {item.get('name', item.get('id', 'Unknown'))}")
                        click.echo(f"\nTotal: {len(items)} {item_name}(s)")

        except Exception as exc:
            handle_api_error(exc)

    @staticmethod
    def handle_get_response(
        resp: requests.Response,
        item_name: str,
        format_output: str,
        table_formatter_func: Optional[Callable[[Dict[str, Any]], List[str]]] = None,
    ) -> None:
        """Handle get response with standardized formatting."""
        try:
            data = resp.json()

            if format_output.lower() == "json":
                click.echo(json.dumps(data, indent=2))
            else:
                if table_formatter_func:
                    table_formatter_func(data)
                else:
                    # Fallback to basic info display
                    click.echo(f"{item_name.title()} Details")
                    click.echo("=" * 50)
                    for key, value in data.items():
                        if isinstance(value, (str, int, bool, float)):
                            click.echo(f"{key.title()}: {value}")

        except Exception as exc:
            handle_api_error(exc)

    @staticmethod
    def handle_create_response(
        resp: requests.Response,
        item_name: str,
        success_message_template: str = "✓ {item_name} created successfully.",
    ) -> None:
        """Handle create response with standardized success messaging."""
        try:
            if resp.status_code in (200, 201):
                data = resp.json() if resp.text.strip() else {}
                message = success_message_template.format(item_name=item_name.title())

                format_success(message, data)
            else:
                click.echo(f"✗ Failed to create {item_name}", err=True)
                sys.exit(ExitCodes.GENERAL_ERROR)

        except Exception as exc:
            handle_api_error(exc)

    @staticmethod
    def handle_update_response(
        resp: requests.Response,
        item_name: str,
        success_message_template: str = "✓ {item_name} updated successfully.",
    ) -> None:
        """Handle update response with standardized success messaging."""
        try:
            if resp.status_code in (200, 204):
                data = resp.json() if resp.text.strip() else {}
                message = success_message_template.format(item_name=item_name.title())

                format_success(message, data)
            else:
                click.echo(f"✗ Failed to update {item_name}", err=True)
                sys.exit(ExitCodes.GENERAL_ERROR)

        except Exception as exc:
            handle_api_error(exc)

    @staticmethod
    def handle_delete_response(
        resp: requests.Response,
        item_name: str,
        item_count: int = 1,
        success_message_template: str = "✓ {count} {item_name}(s) deleted successfully.",
    ) -> None:
        """Handle delete response with standardized success messaging."""
        try:
            if resp.status_code in (200, 204):
                message = success_message_template.format(count=item_count, item_name=item_name)
                click.echo(message)
            else:
                click.echo(f"✗ Failed to delete {item_name}(s)", err=True)
                sys.exit(ExitCodes.GENERAL_ERROR)

        except Exception as exc:
            handle_api_error(exc)

    @staticmethod
    def handle_export_response(
        resp: requests.Response,
        item_name: str,
        output_file: str,
        success_message_template: str = "✓ {item_name} exported to {output_file}",
    ) -> None:
        """Handle export response with file saving."""
        from .utils import save_json_file

        try:
            data = resp.json()
            save_json_file(data, output_file)

            message = success_message_template.format(
                item_name=item_name.title(), output_file=output_file
            )
            click.echo(message)

        except Exception as exc:
            handle_api_error(exc)


class BatchResponseHandler:
    """Handler for batch operations with progress tracking."""

    @staticmethod
    def handle_batch_operation(
        items: List[Dict[str, Any]],
        operation_func: Callable[[Dict[str, Any]], None],
        operation_name: str,
        item_name: str,
        show_progress: bool = True,
    ) -> None:
        """Handle batch operations with progress tracking."""
        total = len(items)
        success_count = 0
        failed_items = []

        for i, item in enumerate(items):
            if show_progress and total > 1:
                click.echo(f"Processing {operation_name} {i + 1}/{total}...", nl=False)

            try:
                operation_func(item)
                success_count += 1
                if show_progress and total > 1:
                    click.echo(" ✓")
            except Exception as exc:
                failed_items.append({"item": item, "error": str(exc)})
                if show_progress and total > 1:
                    click.echo(f" ✗ ({exc})")

        # Summary
        if success_count > 0:
            click.echo(f"✓ {success_count} {item_name}(s) {operation_name}d successfully.")

        if failed_items:
            click.echo(f"✗ {len(failed_items)} {item_name}(s) failed:", err=True)
            for failed in failed_items:
                item_id = failed["item"].get("id", failed["item"].get("name", "Unknown"))  # type: ignore
                click.echo(f"  - {item_id}: {failed['error']}", err=True)

        if failed_items and success_count == 0:
            sys.exit(ExitCodes.GENERAL_ERROR)
        elif failed_items:
            sys.exit(ExitCodes.INVALID_INPUT)
