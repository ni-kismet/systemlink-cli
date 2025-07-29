"""Standardized API response handling utilities for DFF commands."""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import click
from requests import Response

from .utils import ExitCodes


class DFFResponseHandler:
    """Standardized response handling for DFF API operations."""

    @staticmethod
    def handle_list_response(
        response: Response,
        item_type: str,
        format_output: str = "table",
        workspace_filter: Optional[str] = None,
        output_formatter: Optional[Any] = None,
    ) -> None:
        """Handle API response for list operations.

        Args:
            response: HTTP response object
            item_type: Type of items being listed (e.g., "configurations", "groups")
            format_output: Output format ("table", "json", "csv")
            workspace_filter: Optional workspace filter
            output_formatter: Formatter function for the output
        """
        if response.status_code == 200:
            data = response.json()
            items = data.get(item_type, [])

            # Apply workspace filtering if specified
            if workspace_filter:
                items = [item for item in items if item.get("workspace") == workspace_filter]

            if not items:
                filter_msg = f" in workspace '{workspace_filter}'" if workspace_filter else ""
                click.echo(f"No {item_type} found{filter_msg}")
                return

            # Use provided formatter or default JSON output
            if output_formatter:
                output_formatter(items, format_output)
            else:
                DFFResponseHandler._default_output(items, format_output)

        else:
            DFFResponseHandler._handle_error_response(response, f"list {item_type}")

    @staticmethod
    def handle_export_response(
        response: Response,
        output_file: str,
        item_type: str,
        workspace_filter: Optional[str] = None,
    ) -> None:
        """Handle API response for export operations.

        Args:
            response: HTTP response object
            output_file: Output file path
            item_type: Type of items being exported
            workspace_filter: Optional workspace filter
        """
        if response.status_code == 200:
            data = response.json()
            items = data.get(item_type, [])

            # Apply workspace filtering if specified
            if workspace_filter:
                items = [item for item in items if item.get("workspace") == workspace_filter]
                data[item_type] = items

            try:
                Path(output_file).write_text(json.dumps(data, indent=2))
                filter_msg = f" (workspace: {workspace_filter})" if workspace_filter else ""
                click.echo(f"✓ Exported {len(items)} {item_type} to {output_file}{filter_msg}")
            except IOError as e:
                click.echo(f"✗ Failed to write to {output_file}: {e}", err=True)
                sys.exit(ExitCodes.GENERAL_ERROR)
        else:
            DFFResponseHandler._handle_error_response(response, f"export {item_type}")

    @staticmethod
    def handle_import_response(
        response: Response,
        item_count: int,
        item_type: str,
        operation: str = "imported",
    ) -> None:
        """Handle API response for import operations.

        Args:
            response: HTTP response object
            item_count: Number of items being imported
            item_type: Type of items being imported
            operation: Operation description (e.g., "imported", "created")
        """
        if response.status_code in [200, 201]:
            click.echo(f"✓ Successfully {operation} {item_count} {item_type}")
        else:
            DFFResponseHandler._handle_error_response(response, f"import {item_type}")

    @staticmethod
    def handle_delete_response(
        response: Response,
        item_identifier: str,
        item_type: str,
    ) -> None:
        """Handle API response for delete operations.

        Args:
            response: HTTP response object
            item_identifier: Identifier of the deleted item
            item_type: Type of item being deleted
        """
        if response.status_code == 204:
            click.echo(f"✓ Successfully deleted {item_type}: {item_identifier}")
        elif response.status_code == 404:
            click.echo(f"✗ {item_type.capitalize()} not found: {item_identifier}", err=True)
            sys.exit(ExitCodes.NOT_FOUND)
        else:
            DFFResponseHandler._handle_error_response(response, f"delete {item_type}")

    @staticmethod
    def handle_create_response(
        response: Response,
        item_data: Dict[str, Any],
        item_type: str,
    ) -> None:
        """Handle API response for create operations.

        Args:
            response: HTTP response object
            item_data: Data of the created item
            item_type: Type of item being created
        """
        if response.status_code == 201:
            item_id = item_data.get("key") or item_data.get("name", "unknown")
            click.echo(f"✓ Successfully created {item_type}: {item_id}")
        elif response.status_code == 409:
            item_id = item_data.get("key") or item_data.get("name", "unknown")
            click.echo(f"✗ {item_type.capitalize()} already exists: {item_id}", err=True)
            sys.exit(ExitCodes.INVALID_INPUT)
        else:
            DFFResponseHandler._handle_error_response(response, f"create {item_type}")

    @staticmethod
    def handle_update_response(
        response: Response,
        item_identifier: str,
        item_type: str,
    ) -> None:
        """Handle API response for update operations.

        Args:
            response: HTTP response object
            item_identifier: Identifier of the updated item
            item_type: Type of item being updated
        """
        if response.status_code == 200:
            click.echo(f"✓ Successfully updated {item_type}: {item_identifier}")
        elif response.status_code == 404:
            click.echo(f"✗ {item_type.capitalize()} not found: {item_identifier}", err=True)
            sys.exit(ExitCodes.NOT_FOUND)
        else:
            DFFResponseHandler._handle_error_response(response, f"update {item_type}")

    @staticmethod
    def handle_get_response(
        response: Response,
        item_identifier: str,
        item_type: str,
        format_output: str = "json",
        output_formatter: Optional[Any] = None,
    ) -> None:
        """Handle API response for get operations.

        Args:
            response: HTTP response object
            item_identifier: Identifier of the item being retrieved
            item_type: Type of item being retrieved
            format_output: Output format
            output_formatter: Optional custom formatter
        """
        if response.status_code == 200:
            data = response.json()

            if output_formatter:
                output_formatter([data], format_output)
            else:
                DFFResponseHandler._default_output(data, format_output)

        elif response.status_code == 404:
            click.echo(f"✗ {item_type.capitalize()} not found: {item_identifier}", err=True)
            sys.exit(ExitCodes.NOT_FOUND)
        else:
            DFFResponseHandler._handle_error_response(response, f"get {item_type}")

    @staticmethod
    def _handle_error_response(response: Response, operation: str) -> None:
        """Handle error responses with standardized messaging.

        Args:
            response: HTTP response object
            operation: Description of the operation that failed
        """
        try:
            error_data = response.json()
            error_message = error_data.get("message", "Unknown error")
            click.echo(f"✗ Failed to {operation}: {error_message}", err=True)
        except (ValueError, KeyError):
            click.echo(
                f"✗ Failed to {operation}: HTTP {response.status_code}",
                err=True,
            )

        # Map HTTP status codes to appropriate exit codes
        if response.status_code == 400:
            sys.exit(ExitCodes.INVALID_INPUT)
        elif response.status_code == 401:
            sys.exit(ExitCodes.PERMISSION_DENIED)
        elif response.status_code == 403:
            sys.exit(ExitCodes.PERMISSION_DENIED)
        elif response.status_code == 404:
            sys.exit(ExitCodes.NOT_FOUND)
        elif response.status_code == 409:
            sys.exit(ExitCodes.INVALID_INPUT)
        else:
            sys.exit(ExitCodes.GENERAL_ERROR)

    @staticmethod
    def _default_output(data: Any, format_output: str) -> None:
        """Default output formatting for response data.

        Args:
            data: Data to output
            format_output: Format for output
        """
        if format_output == "json":
            click.echo(json.dumps(data, indent=2))
        else:
            # For non-JSON formats, convert to JSON as fallback
            click.echo(json.dumps(data, indent=2))


class DFFBatchResponseHandler:
    """Handler for batch operations with multiple API calls."""

    def __init__(self, operation_name: str):
        """Initialize batch response handler.

        Args:
            operation_name: Name of the batch operation
        """
        self.operation_name = operation_name
        self.successes: List[str] = []
        self.failures: List[tuple[str, str]] = []

    def add_success(self, item_identifier: str) -> None:
        """Record a successful operation.

        Args:
            item_identifier: Identifier of the successfully processed item
        """
        self.successes.append(item_identifier)

    def add_failure(self, item_identifier: str, error_message: str) -> None:
        """Record a failed operation.

        Args:
            item_identifier: Identifier of the item that failed
            error_message: Error message for the failure
        """
        self.failures.append((item_identifier, error_message))

    def process_response(
        self,
        response: Response,
        item_identifier: str,
        expected_status: int = 200,
    ) -> bool:
        """Process a single response in the batch operation.

        Args:
            response: HTTP response object
            item_identifier: Identifier of the item being processed
            expected_status: Expected HTTP status code for success

        Returns:
            True if successful, False if failed
        """
        if response.status_code == expected_status:
            self.add_success(item_identifier)
            return True
        else:
            try:
                error_data = response.json()
                error_message = error_data.get("message", f"HTTP {response.status_code}")
            except (ValueError, KeyError):
                error_message = f"HTTP {response.status_code}"

            self.add_failure(item_identifier, error_message)
            return False

    def report_results(self, exit_on_failure: bool = True) -> None:
        """Report the final results of the batch operation.

        Args:
            exit_on_failure: Whether to exit with error code if any failures occurred
        """
        total = len(self.successes) + len(self.failures)

        if self.successes:
            click.echo(f"✓ Successfully {self.operation_name} {len(self.successes)}/{total} items")

        if self.failures:
            click.echo(
                f"✗ Failed to {self.operation_name} {len(self.failures)}/{total} items:", err=True
            )
            for item_id, error in self.failures:
                click.echo(f"  - {item_id}: {error}", err=True)

            if exit_on_failure:
                sys.exit(ExitCodes.GENERAL_ERROR)


def handle_file_validation(file_path: str, operation: str) -> Dict[str, Any]:
    """Validate and load JSON file for DFF operations.

    Args:
        file_path: Path to the JSON file
        operation: Operation being performed (for error messages)

    Returns:
        Loaded JSON data

    Raises:
        SystemExit: If file validation fails
    """
    try:
        from .utils import load_json_file

        return load_json_file(file_path)
    except FileNotFoundError:
        click.echo(f"✗ File not found: {file_path}", err=True)
        sys.exit(ExitCodes.NOT_FOUND)
    except json.JSONDecodeError as e:
        click.echo(f"✗ Invalid JSON in {file_path}: {e}", err=True)
        sys.exit(ExitCodes.INVALID_INPUT)
    except Exception as e:
        click.echo(f"✗ Failed to read {file_path} for {operation}: {e}", err=True)
        sys.exit(ExitCodes.GENERAL_ERROR)
