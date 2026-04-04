"""Rich-backed output helpers for slcli.

This module centralizes terminal rendering so existing Click-based commands can
benefit from Rich styling without rewriting every command implementation.
"""

from __future__ import annotations

import json
import os
import re
import sys
from typing import Any, Iterable, Optional, Sequence

import click
from rich.box import ROUNDED
from rich.console import Console
from rich.json import JSON
from rich.table import Table
from rich.text import Text
from rich.theme import Theme


_THEME = Theme(
    {
        "brand": "bold cyan",
        "success.symbol": "bold green",
        "success.message": "green",
        "error.symbol": "bold red",
        "error.message": "red",
        "warning.symbol": "bold yellow",
        "warning.message": "yellow",
        "label": "bold cyan",
        "section": "bold bright_white",
        "divider": "dim",
        "bullet": "bold cyan",
        "status.good": "green",
        "status.bad": "red",
        "status.warn": "yellow",
        "table.header": "bold white",
        "table.border": "bold cyan",
        "table.body": "bright_white",
        "summary": "dim cyan",
    }
)

_ORIGINAL_CLICK_ECHO = click.echo
_ORIGINAL_CLICK_SECHO = click.secho
_PATCH_INSTALLED = False
_STDOUT_CONSOLE: Optional[Console] = None
_STDERR_CONSOLE: Optional[Console] = None

_LABEL_RE = re.compile(r"^(\s*)([A-Za-z0-9][A-Za-z0-9 _./()'-]{0,60}:)(\s+.*)?$")


def install_rich_output() -> None:
    """Patch Click output once for the current process."""
    global _PATCH_INSTALLED

    if _PATCH_INSTALLED:
        return

    click.echo = _rich_echo
    click.secho = _rich_secho
    click.utils.echo = _rich_echo
    _PATCH_INSTALLED = True


def print_json(data: Any, err: bool = False) -> None:
    """Render JSON data through Rich."""
    if _should_use_rich_json(err=err):
        _get_console(err=err).print(JSON.from_data(data))
        return

    _ORIGINAL_CLICK_ECHO(message=json.dumps(data, indent=2), err=err)


def render_table(
    headers: Sequence[str],
    column_widths: Sequence[int],
    rows: Iterable[Sequence[Any]],
    *,
    show_total: bool = False,
    total_label: str = "item(s)",
    total_count: Optional[int] = None,
) -> None:
    """Render a boxed table using Rich.

    Args:
        headers: Column headers.
        column_widths: Maximum widths for each column.
        rows: Row values.
        show_total: Whether to print a total footer.
        total_label: Label for the total footer.
        total_count: Optional explicit total count for the footer.
    """
    table = Table(
        box=ROUNDED,
        header_style="table.header",
        border_style="table.border",
        show_lines=False,
        pad_edge=True,
    )

    for header, width in zip(headers, column_widths):
        table.add_column(
            header,
            overflow="ellipsis",
            width=width,
            no_wrap=True,
        )

    row_count = 0
    for row in rows:
        styled_row = [_style_table_cell(value) for value in row]
        table.add_row(*styled_row)
        row_count += 1

    _get_console().print(table)

    if show_total:
        count = total_count if total_count is not None else row_count
        _get_console().print()
        _get_console().print(Text.assemble(("Total: ", "summary"), str(count), f" {total_label}"))


def _rich_echo(
    message: Any = None,
    file: Optional[Any] = None,
    nl: bool = True,
    err: bool = False,
    color: Optional[bool] = None,
) -> None:
    """Rich-backed replacement for click.echo."""
    del color

    stream = sys.stderr if err else sys.stdout
    if file is not None and file is not stream:
        _ORIGINAL_CLICK_ECHO(message=message, file=file, nl=nl, err=err)
        return

    console = _get_console(err=err)
    end = "\n" if nl else ""

    if message is None:
        console.print(end=end)
        return

    if isinstance(message, bytes):
        _ORIGINAL_CLICK_ECHO(message=message, file=file, nl=nl, err=err)
        return

    if not isinstance(message, str):
        console.print(message, end=end)
        return

    json_data = _try_parse_json(message)
    if json_data is not None:
        if _should_use_rich_json(err=err):
            console.print(JSON.from_data(json_data), end=end)
        else:
            _ORIGINAL_CLICK_ECHO(message=message, file=file, nl=nl, err=err)
        return

    if "\x1b[" in message:
        console.print(Text.from_ansi(message), end=end)
        return

    console.print(_style_plain_message(message, err=err), end=end, soft_wrap=True)


def _rich_secho(
    message: Any = None,
    file: Optional[Any] = None,
    nl: bool = True,
    err: bool = False,
    color: Optional[bool] = None,
    **styles: Any,
) -> None:
    """Rich-backed replacement for click.secho."""
    styled = click.style(message, **styles)
    _rich_echo(message=styled, file=file, nl=nl, err=err, color=color)


def _configure_consoles() -> None:
    """Create stdout and stderr consoles from environment policy."""
    global _STDOUT_CONSOLE, _STDERR_CONSOLE

    color_mode = os.environ.get("SLCLI_COLOR", "auto").strip().lower()
    no_color = os.environ.get("NO_COLOR") is not None or color_mode == "never"
    stdout_is_tty = _stream_is_tty(err=False)
    stderr_is_tty = _stream_is_tty(err=True)
    force_stdout_terminal = color_mode == "always" or stdout_is_tty
    force_stderr_terminal = color_mode == "always" or stderr_is_tty

    _STDOUT_CONSOLE = Console(
        theme=_THEME,
        stderr=False,
        no_color=no_color,
        force_terminal=force_stdout_terminal,
        highlight=False,
        soft_wrap=False,
        width=None if force_stdout_terminal else 160,
    )
    _STDERR_CONSOLE = Console(
        theme=_THEME,
        stderr=True,
        no_color=no_color,
        force_terminal=force_stderr_terminal,
        highlight=False,
        soft_wrap=False,
        width=None if force_stderr_terminal else 160,
    )


def _get_console(err: bool = False) -> Console:
    """Return the configured Rich console."""
    if _console_needs_refresh(err=err):
        _configure_consoles()
    return _STDERR_CONSOLE if err else _STDOUT_CONSOLE  # type: ignore[return-value]


def _console_needs_refresh(err: bool = False) -> bool:
    """Return whether the cached console should be rebuilt."""
    console = _STDERR_CONSOLE if err else _STDOUT_CONSOLE
    if console is None:
        return True

    color_mode = os.environ.get("SLCLI_COLOR", "auto").strip().lower()
    if color_mode in {"always", "never"}:
        return False

    stream_is_tty = _stream_is_tty(err=err)
    return bool(stream_is_tty != console.is_terminal)


def _try_parse_json(message: str) -> Optional[Any]:
    """Parse a JSON-looking string and return the decoded object if valid."""
    stripped = message.strip()
    if not stripped or stripped[0] not in "[{":
        return None

    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        return None


def _should_use_rich_json(err: bool = False) -> bool:
    """Return whether JSON should be syntax highlighted instead of echoed raw."""
    color_mode = os.environ.get("SLCLI_COLOR", "auto").strip().lower()
    if os.environ.get("NO_COLOR") is not None or color_mode == "never":
        return False
    if color_mode == "always":
        return True
    return _stream_is_tty(err=err)


def _stream_is_tty(err: bool = False) -> bool:
    """Return whether the target stream is an interactive terminal."""
    stream = sys.stderr if err else sys.stdout
    try:
        return bool(stream.isatty())
    except Exception:
        return False


def _style_plain_message(message: str, err: bool = False) -> Text:
    """Apply lightweight semantic styling to plain text output."""
    if "████" in message:
        return Text(message, style="brand")

    output = Text()
    lines = message.splitlines(keepends=True)
    for line in lines:
        has_newline = line.endswith("\n")
        body = line[:-1] if has_newline else line
        output.append_text(_style_line(body, err=err))
        if has_newline:
            output.append("\n")
    return output


def _style_line(line: str, err: bool = False) -> Text:
    """Style a single line of plain text."""
    if not line:
        return Text()

    status_line = _style_status_line(line)
    if status_line is not None:
        return status_line

    if set(line) <= {"=", "-", "─"}:
        return Text(line, style="divider")

    label_match = _LABEL_RE.match(line)
    if label_match:
        indent, label, value = label_match.groups()
        return Text.assemble(
            indent,
            (label, "label"),
            value or "",
        )

    stripped = line.strip()
    if stripped.endswith(":") and len(stripped) <= 80:
        return Text(line, style="section")

    if line.lstrip().startswith("- "):
        indent = line[: len(line) - len(line.lstrip())]
        content = line.lstrip()[2:]
        return Text.assemble(indent, ("-", "bullet"), f" {content}")

    if err:
        return Text(line, style="error.message")

    return Text(line)


def _style_status_line(line: str) -> Optional[Text]:
    """Style common status-line prefixes."""
    for symbol, symbol_style, message_style in (
        ("✓", "success.symbol", "success.message"),
        ("✗", "error.symbol", "error.message"),
        ("⚠", "warning.symbol", "warning.message"),
    ):
        if line.startswith(symbol):
            rest = line[len(symbol) :]
            return Text.assemble((symbol, symbol_style), (rest, message_style))
    return None


def _style_table_cell(value: Any) -> Text:
    """Apply semantic styling to common table values."""
    text_value = "" if value is None else str(value)
    stripped = text_value.strip()
    upper_value = stripped.upper()

    if not stripped:
        return Text(text_value)

    if stripped in {"✓", "Yes", "Active", "Enabled", "CONNECTED", "Default", "User"}:
        return Text(text_value, style="status.good")
    if stripped in {"✗", "No", "Inactive", "Disabled", "ERROR", "FAILED"}:
        return Text(text_value, style="status.bad")
    if stripped in {"Pending", "WARNING", "WARN"}:
        return Text(text_value, style="status.warn")

    if upper_value in {
        "ACTIVE",
        "AUTOMATIC",
        "AVAILABLE",
        "COMPLETED",
        "COMPLETE",
        "CONNECTED",
        "DEFAULT",
        "ENABLED",
        "HEALTHY",
        "INSTALLED",
        "OK",
        "ONLINE",
        "PASS",
        "PASSED",
        "PRESENT",
        "READY",
        "RUNNABLE",
        "SUCCEEDED",
        "SUCCESS",
        "TRUE",
        "USER",
        "VALID",
    }:
        return Text(text_value, style="status.good")

    if upper_value in {
        "ABSENT",
        "CANCELED",
        "CANCELLED",
        "DISABLED",
        "DISCONNECTED",
        "ERROR",
        "FAILED",
        "FAILURE",
        "FALSE",
        "INACTIVE",
        "INVALID",
        "MISSING",
        "NO",
        "OFFLINE",
        "PAST_DUE",
        "TIMED_OUT",
        "UNAVAILABLE",
    }:
        return Text(text_value, style="status.bad")

    if upper_value in {
        "IN_PROGRESS",
        "PENDING",
        "QUEUED",
        "RETRYING",
        "RUNNING",
        "SCHEDULED",
        "STARTING",
        "UNKNOWN",
        "WARN",
        "WARNING",
    }:
        return Text(text_value, style="status.warn")

    if re.fullmatch(r"[0-9a-fA-F-]{8,}", stripped):
        return Text(text_value, style="label")

    if _looks_like_name_or_title(stripped):
        return Text(text_value, style="table.body")

    if _looks_like_short_code(stripped):
        return Text(text_value, style="label")

    return Text(text_value)


def _looks_like_name_or_title(value: str) -> bool:
    """Return whether the value looks like a human-readable name/title cell."""
    if len(value) < 3 or len(value) > 48:
        return False
    if any(char.isdigit() for char in value):
        return False
    return bool(re.fullmatch(r"[A-Za-z][A-Za-z0-9 ._()/:-]*", value))


def _looks_like_short_code(value: str) -> bool:
    """Return whether the value looks like a compact identifier or enum code."""
    if len(value) < 2 or len(value) > 24:
        return False
    return bool(re.fullmatch(r"[A-Z0-9_:-]+", value))
