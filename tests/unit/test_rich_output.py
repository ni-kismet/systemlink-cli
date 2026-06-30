"""Unit tests for Rich-backed output helpers."""

import json
from io import StringIO
from typing import Any, cast

import click
from rich.json import JSON
from rich.table import Table
from rich.text import Text

from slcli import rich_output
from slcli.rich_output import (
    _rich_echo,
    _style_plain_message,
    _style_table_cell,
    install_rich_output,
    print_json,
    render_table,
)


class FakeConsole:
    """Minimal console stub for capturing Rich print calls in tests."""

    def __init__(self, is_terminal: bool = True) -> None:
        """Initialize the fake console with a configurable terminal flag."""
        self.is_terminal = is_terminal
        self.calls: list[dict[str, Any]] = []

    def print(self, *args: Any, **kwargs: Any) -> None:
        self.calls.append({"args": args, "kwargs": kwargs})


def test_style_table_cell_marks_good_statuses() -> None:
    """Good statuses render with the success table style."""
    result = _style_table_cell("SUCCEEDED")

    assert isinstance(result, Text)
    assert result.style == "status.good"
    assert result.plain == "SUCCEEDED"


def test_style_table_cell_marks_warning_statuses() -> None:
    """Warning-like statuses render with the warning table style."""
    result = _style_table_cell("RUNNING")

    assert isinstance(result, Text)
    assert result.style == "status.warn"
    assert result.plain == "RUNNING"


def test_style_table_cell_marks_bad_statuses() -> None:
    """Failure statuses render with the error table style."""
    result = _style_table_cell("TIMED_OUT")

    assert isinstance(result, Text)
    assert result.style == "status.bad"
    assert result.plain == "TIMED_OUT"


def test_style_plain_message_applies_error_style() -> None:
    """Error output should style plain text lines consistently."""
    result = _style_plain_message("plain error", err=True)

    assert isinstance(result, Text)
    assert result.plain == "plain error"
    assert len(result.spans) == 1
    assert result.spans[0].style == "error.message"


def test_install_rich_output_is_idempotent(monkeypatch: Any) -> None:
    """Installing Rich output twice should keep the same patched functions."""
    monkeypatch.setattr(rich_output, "_PATCH_INSTALLED", False)
    monkeypatch.setattr(click, "echo", rich_output._ORIGINAL_CLICK_ECHO)
    monkeypatch.setattr(click, "secho", rich_output._ORIGINAL_CLICK_SECHO)
    monkeypatch.setattr(click.utils, "echo", rich_output._ORIGINAL_CLICK_ECHO)

    install_rich_output()
    first_echo = click.echo
    first_secho = click.secho

    install_rich_output()

    assert click.echo is first_echo
    assert click.secho is first_secho
    assert click.utils.echo is first_echo


def test_print_json_uses_original_echo_when_not_interactive(monkeypatch: Any) -> None:
    """Non-interactive JSON output should remain raw JSON."""
    recorded: list[dict[str, Any]] = []

    monkeypatch.setattr(rich_output, "_should_use_rich_json", lambda err=False: False)
    monkeypatch.setattr(
        rich_output,
        "_ORIGINAL_CLICK_ECHO",
        lambda **kwargs: recorded.append(kwargs),
    )

    print_json({"name": "demo"})

    assert recorded == [{"message": json.dumps({"name": "demo"}, indent=2), "err": False}]


def test_print_json_uses_rich_console_when_interactive(monkeypatch: Any) -> None:
    """Interactive JSON output should use Rich syntax highlighting."""
    console = FakeConsole()

    monkeypatch.setattr(rich_output, "_should_use_rich_json", lambda err=False: True)
    monkeypatch.setattr(rich_output, "_get_console", lambda err=False: console)

    print_json({"name": "demo"})

    assert len(console.calls) == 1
    assert isinstance(console.calls[0]["args"][0], JSON)


def test_render_table_prints_table_and_total(monkeypatch: Any) -> None:
    """Table rendering should print both the table and the summary footer."""
    console = FakeConsole()

    monkeypatch.setattr(rich_output, "_get_console", lambda err=False: console)

    render_table(["Name", "Status"], [10, 10], [["demo", "SUCCEEDED"]], show_total=True)

    assert isinstance(console.calls[0]["args"][0], Table)
    assert console.calls[0]["args"][0].row_count == 1
    assert console.calls[1]["args"] == ()
    assert isinstance(console.calls[2]["args"][0], Text)
    assert console.calls[2]["args"][0].plain == "Total: 1 item(s)"


def test_rich_echo_uses_original_echo_for_non_stream_file(monkeypatch: Any) -> None:
    """Explicit file objects should bypass Rich rendering."""
    recorded: list[dict[str, Any]] = []

    monkeypatch.setattr(
        rich_output,
        "_ORIGINAL_CLICK_ECHO",
        lambda **kwargs: recorded.append(kwargs),
    )

    destination = StringIO()
    _rich_echo(message="hello", file=destination)

    assert recorded == [{"message": "hello", "file": destination, "nl": True, "err": False}]


def test_rich_echo_uses_original_echo_for_bytes(monkeypatch: Any) -> None:
    """Binary output should be passed through untouched."""
    recorded: list[dict[str, Any]] = []
    console = FakeConsole()

    monkeypatch.setattr(rich_output, "_get_console", lambda err=False: console)
    monkeypatch.setattr(
        rich_output,
        "_ORIGINAL_CLICK_ECHO",
        lambda **kwargs: recorded.append(kwargs),
    )

    _rich_echo(message=b"hello")

    assert recorded == [{"message": b"hello", "file": None, "nl": True, "err": False}]
    assert console.calls == []


def test_rich_echo_renders_ansi_text(monkeypatch: Any) -> None:
    """ANSI input should be converted through Rich instead of echoed raw."""
    console = FakeConsole()

    monkeypatch.setattr(rich_output, "_get_console", lambda err=False: console)

    _rich_echo(message="\x1b[31mred\x1b[0m")

    rendered = console.calls[0]["args"][0]
    assert isinstance(rendered, Text)
    assert rendered.plain == "red"


def test_rich_echo_falls_back_for_noninteractive_json(monkeypatch: Any) -> None:
    """JSON strings stay raw when Rich JSON output is disabled."""
    recorded: list[dict[str, Any]] = []
    console = FakeConsole()

    monkeypatch.setattr(rich_output, "_get_console", lambda err=False: console)
    monkeypatch.setattr(rich_output, "_should_use_rich_json", lambda err=False: False)
    monkeypatch.setattr(
        rich_output,
        "_ORIGINAL_CLICK_ECHO",
        lambda **kwargs: recorded.append(kwargs),
    )

    _rich_echo(message='{"name": "demo"}')

    assert recorded == [{"message": '{"name": "demo"}', "file": None, "nl": True, "err": False}]
    assert console.calls == []


def test_rich_echo_prints_plain_messages_with_rich(monkeypatch: Any) -> None:
    """Plain text should be styled and printed through the Rich console."""
    console = FakeConsole()

    monkeypatch.setattr(rich_output, "_get_console", lambda err=False: console)

    _rich_echo(message="✓ done")

    rendered = console.calls[0]["args"][0]
    assert isinstance(rendered, Text)
    assert rendered.plain == "✓ done"


def test_should_use_rich_json_honors_color_env(monkeypatch: Any) -> None:
    """Color environment settings should control Rich JSON usage."""
    monkeypatch.setenv("SLCLI_COLOR", "always")
    monkeypatch.delenv("NO_COLOR", raising=False)

    assert rich_output._should_use_rich_json() is True

    monkeypatch.setenv("SLCLI_COLOR", "never")
    assert rich_output._should_use_rich_json() is False


def test_get_console_refreshes_when_tty_becomes_available(monkeypatch: Any) -> None:
    """The cached console is rebuilt if terminal capability changes before output."""

    class FakeConsole:
        def __init__(self, is_terminal: bool) -> None:
            self.is_terminal = is_terminal

    monkeypatch.setattr(rich_output, "_STDOUT_CONSOLE", cast(Any, FakeConsole(False)))
    monkeypatch.setattr(rich_output, "_STDERR_CONSOLE", cast(Any, FakeConsole(False)))
    monkeypatch.setattr(rich_output, "_stream_is_tty", lambda err=False: True)

    recreated = FakeConsole(True)

    def fake_configure() -> None:
        rich_output._STDOUT_CONSOLE = cast(Any, recreated)
        rich_output._STDERR_CONSOLE = cast(Any, recreated)

    monkeypatch.setattr(rich_output, "_configure_consoles", fake_configure)

    assert rich_output._get_console() is recreated


def test_console_refreshes_when_tty_becomes_unavailable(monkeypatch: Any) -> None:
    """The cached console is rebuilt if output stops targeting a terminal."""

    class TerminalConsole:
        def __init__(self, is_terminal: bool) -> None:
            self.is_terminal = is_terminal

    monkeypatch.setattr(rich_output, "_STDOUT_CONSOLE", cast(Any, TerminalConsole(True)))
    monkeypatch.setattr(rich_output, "_STDERR_CONSOLE", cast(Any, TerminalConsole(True)))
    monkeypatch.setattr(rich_output, "_stream_is_tty", lambda err=False: False)

    recreated = TerminalConsole(False)

    def fake_configure() -> None:
        rich_output._STDOUT_CONSOLE = cast(Any, recreated)
        rich_output._STDERR_CONSOLE = cast(Any, recreated)

    monkeypatch.setattr(rich_output, "_configure_consoles", fake_configure)

    assert rich_output._get_console() is recreated


def test_rich_secho_uses_click_styling(monkeypatch: Any) -> None:
    """click.secho replacement should pass a styled string through Rich echo."""
    recorded: list[dict[str, Any]] = []

    monkeypatch.setattr(rich_output, "_rich_echo", lambda **kwargs: recorded.append(kwargs))

    rich_output._rich_secho(message="done", fg="green", bold=True)

    assert len(recorded) == 1
    assert "\x1b[" in recorded[0]["message"]


def test_configure_consoles_respects_terminal_detection(monkeypatch: Any) -> None:
    """Console construction should follow per-stream terminal detection."""
    monkeypatch.setenv("SLCLI_COLOR", "auto")
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setattr(rich_output, "_stream_is_tty", lambda err=False: not err)

    rich_output._configure_consoles()

    assert rich_output._STDOUT_CONSOLE is not None
    assert rich_output._STDERR_CONSOLE is not None
    assert rich_output._STDOUT_CONSOLE.is_terminal is True
    assert rich_output._STDERR_CONSOLE.is_terminal is False


def test_console_needs_refresh_respects_explicit_color_mode(monkeypatch: Any) -> None:
    """Explicit color settings should disable auto-refresh decisions."""

    class TerminalConsole:
        def __init__(self, is_terminal: bool) -> None:
            self.is_terminal = is_terminal

    monkeypatch.setattr(rich_output, "_STDOUT_CONSOLE", cast(Any, TerminalConsole(False)))
    monkeypatch.setenv("SLCLI_COLOR", "always")
    monkeypatch.setattr(rich_output, "_stream_is_tty", lambda err=False: True)

    assert rich_output._console_needs_refresh() is False

    monkeypatch.setenv("SLCLI_COLOR", "never")
    assert rich_output._console_needs_refresh() is False


def test_try_parse_json_handles_valid_and_invalid_input() -> None:
    """JSON parsing should accept JSON-looking strings and reject the rest."""
    assert rich_output._try_parse_json('{"ok": true}') == {"ok": True}
    assert rich_output._try_parse_json("not json") is None
    assert rich_output._try_parse_json("{broken") is None


def test_stream_is_tty_handles_stream_errors(monkeypatch: Any) -> None:
    """TTY detection should fail closed when the stream raises."""

    class BrokenStream:
        def isatty(self) -> bool:
            raise RuntimeError("boom")

    monkeypatch.setattr(rich_output.sys, "stdout", BrokenStream())

    assert rich_output._stream_is_tty() is False


def test_style_plain_message_brands_ascii_art() -> None:
    """ASCII banner output should use the brand style."""
    result = _style_plain_message("████ banner")

    assert isinstance(result, Text)
    assert result.style == "brand"


def test_style_line_covers_common_variants() -> None:
    """Line styling should cover dividers, labels, sections, bullets, and warnings."""
    divider = rich_output._style_line("----")
    label = rich_output._style_line("  Name: value")
    section = rich_output._style_line("# Section:")
    bullet = rich_output._style_line("  - item")
    plain = rich_output._style_line("plain")
    warning = rich_output._style_status_line("⚠ heads up")

    assert divider.style == "divider"
    assert label.spans[0].style == "label"
    assert section.style == "section"
    assert bullet.spans[0].style == "bullet"
    assert plain.plain == "plain"
    assert warning is not None
    assert warning.plain == "⚠ heads up"


def test_style_table_cell_covers_identifier_name_and_default_paths() -> None:
    """Table cell styling should handle identifiers, titles, short codes, and plain text."""
    uuid_cell = _style_table_cell("123e4567-e89b-12d3-a456-426614174000")
    title_cell = _style_table_cell("Demo Workspace")
    code_cell = _style_table_cell("ABC_123")
    plain_cell = _style_table_cell("value-1")

    assert uuid_cell.style == "label"
    assert title_cell.style == "table.body"
    assert code_cell.style == "label"
    assert plain_cell.style == ""


def test_name_and_short_code_helpers_apply_limits() -> None:
    """Helper predicates should enforce their intended matching limits."""
    assert rich_output._looks_like_name_or_title("Demo Workspace") is True
    assert rich_output._looks_like_name_or_title("Demo 123") is False
    assert rich_output._looks_like_short_code("READY_OK") is True
    assert rich_output._looks_like_short_code("mixedCase") is False
