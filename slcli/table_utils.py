"""Table formatting utilities for CLI commands."""

import json
from typing import Any, Callable, Dict, List

import click


def output_formatted_list(
    items: List[Dict[str, Any]],
    output_format: str,
    headers: List[str],
    column_widths: List[int],
    row_formatter_func: Callable[[Dict[str, Any]], List[str]],
    empty_message: str = "No items found.",
    total_label: str = "item(s)",
) -> None:
    """Handle JSON and table output with box-drawing characters for list commands.

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
        click.echo(json.dumps(items, indent=2))
        return

    # Table format with box-drawing characters
    if len(headers) != len(column_widths):
        raise ValueError("Headers and column_widths must have the same length")

    _draw_table_border(column_widths, "top")
    _draw_table_header(headers, column_widths)
    _draw_table_border(column_widths, "middle")
    _draw_table_rows(items, row_formatter_func, column_widths)
    _draw_table_border(column_widths, "bottom")

    # Total count
    click.echo(f"\nTotal: {len(items)} {total_label}")


def _draw_table_border(column_widths: List[int], border_type: str) -> None:
    """Draw table borders with appropriate characters."""
    if border_type == "top":
        left, junction, right = "┌", "┬", "┐"
    elif border_type == "middle":
        left, junction, right = "├", "┼", "┤"
    elif border_type == "bottom":
        left, junction, right = "└", "┴", "┘"
    else:
        raise ValueError("Invalid border_type")

    border_chars = [left] + [("─" * (w + 2)) for w in column_widths]
    border_line = border_chars[0] + border_chars[1]
    for part in border_chars[2:]:
        border_line += junction + part
    border_line += right
    click.echo(border_line)


def _draw_table_header(headers: List[str], column_widths: List[int]) -> None:
    """Draw table header row."""
    header_parts = ["│"]
    for header, width in zip(headers, column_widths):
        header_parts.append(f" {header:<{width}} │")
    click.echo("".join(header_parts))


def _draw_table_rows(
    items: List[Dict[str, Any]],
    row_formatter_func: Callable[[Dict[str, Any]], List[str]],
    column_widths: List[int],
) -> None:
    """Draw table data rows."""
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
