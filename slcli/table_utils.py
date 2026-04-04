"""Table formatting utilities for CLI commands."""

from typing import Any, Callable, Dict, List

import click

from .rich_output import print_json, render_table


def output_formatted_list(
    items: List[Dict[str, Any]],
    output_format: str,
    headers: List[str],
    column_widths: List[int],
    row_formatter_func: Callable[[Dict[str, Any]], List[str]],
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
    if not items:
        if output_format.lower() == "json":
            click.echo("[]")
        else:
            click.echo(empty_message)
        return

    if output_format.lower() == "json":
        print_json(items)
        return

    if len(headers) != len(column_widths):
        raise ValueError("Headers and column_widths must have the same length")

    rows = []
    for item in items:
        row_data = row_formatter_func(item)
        if len(row_data) != len(column_widths):
            raise ValueError("Row data must match column count")
        rows.append(row_data)

    render_table(headers, column_widths, rows, show_total=True, total_label=total_label)


class TableConfig:
    """Configuration class for standardized table layouts."""

    # Standard column configurations
    WORKSPACE_NAME_CONFIG_ID = {
        "headers": ["Workspace", "Name", "Configuration ID"],
        "widths": [36, 40, 36],
    }

    WORKSPACE_NAME_KEY = {"headers": ["Workspace", "Name", "Key"], "widths": [23, 32, 39]}

    WORKSPACE_RESOURCE_TABLE = {
        "headers": ["Workspace", "Resource Type", "Resource ID", "Table ID"],
        "widths": [36, 30, 18, 36],
    }

    WORKSPACE_NAME_ID = {"headers": ["Workspace", "Name", "ID"], "widths": [36, 40, 36]}


def get_table_config(config_name: str) -> Dict[str, List]:
    """Get predefined table configuration by name."""
    config = getattr(TableConfig, config_name, None)
    if not config:
        raise ValueError(f"Unknown table configuration: {config_name}")
    return config
