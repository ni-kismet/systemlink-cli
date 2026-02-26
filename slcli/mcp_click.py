"""CLI commands for the slcli MCP server.

Provides 'slcli mcp serve' and 'slcli mcp install' subcommands.
"""

import json
import platform
import shutil
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import click

from .utils import ExitCodes


def _slcli_exe() -> str:
    """Return the absolute path to the slcli executable, or 'slcli' as a fallback."""
    exe = shutil.which("slcli")
    return exe if exe else "slcli"


def _vscode_server_entry(slcli_exe: str) -> Dict[str, Any]:
    """Return the VS Code MCP server JSON object for slcli."""
    return {
        "type": "stdio",
        "command": slcli_exe,
        "args": ["mcp", "serve"],
    }


def _claude_server_entry(slcli_exe: str) -> Dict[str, Any]:
    """Return the Claude Desktop / Cursor MCP server JSON object for slcli."""
    return {
        "command": slcli_exe,
        "args": ["mcp", "serve"],
    }


def _find_claude_config_file() -> Path:
    """Return the platform-specific path to Claude Desktop's config file."""
    system = platform.system()
    if system == "Darwin":
        base = Path.home() / "Library" / "Application Support" / "Claude"
    elif system == "Windows":
        base = Path(str(Path.home() / "AppData" / "Roaming" / "Claude"))
    else:
        # Linux / other
        base = Path.home() / ".config" / "claude"
    return base / "claude_desktop_config.json"


def _merge_and_write_json(
    config_file: Path,
    top_key: str,
    server_name: str,
    server_entry: Dict[str, Any],
) -> None:
    """Read (or create) a JSON config file, upsert the server entry, and write it back.

    Args:
        config_file: Path to the JSON config file.
        top_key: Top-level JSON key that holds the server map (e.g. 'servers' or 'mcpServers').
        server_name: Name to use as the key inside the server map.
        server_entry: Server entry dict to write.
    """
    if config_file.exists():
        existing: Dict[str, Any] = json.loads(config_file.read_text(encoding="utf-8"))
    else:
        config_file.parent.mkdir(parents=True, exist_ok=True)
        existing = {}

    existing.setdefault(top_key, {})
    existing[top_key][server_name] = server_entry
    config_file.write_text(json.dumps(existing, indent=2) + "\n", encoding="utf-8")


def _install_vscode(slcli_exe: str) -> None:
    """Write / update .vscode/mcp.json in the current directory."""
    config_file = Path(".vscode") / "mcp.json"
    _merge_and_write_json(
        config_file,
        top_key="servers",
        server_name="slcli",
        server_entry=_vscode_server_entry(slcli_exe),
    )
    click.echo(f"✓ VS Code MCP config written to {config_file}")
    click.echo("  Restart VS Code (or reload the window) to activate the server.")


def _install_claude(slcli_exe: str) -> None:
    """Merge slcli into Claude Desktop's config file."""
    config_file = _find_claude_config_file()
    _merge_and_write_json(
        config_file,
        top_key="mcpServers",
        server_name="slcli",
        server_entry=_claude_server_entry(slcli_exe),
    )
    click.echo(f"✓ Claude Desktop MCP config updated: {config_file}")
    click.echo("  Restart Claude Desktop to activate the server.")


def _install_cursor(slcli_exe: str) -> None:
    """Write / update .cursor/mcp.json in the current directory."""
    config_file = Path(".cursor") / "mcp.json"
    _merge_and_write_json(
        config_file,
        top_key="mcpServers",
        server_name="slcli",
        server_entry=_claude_server_entry(slcli_exe),
    )
    click.echo(f"✓ Cursor MCP config written to {config_file}")
    click.echo("  Reload Cursor to activate the server.")


_INSTALLERS: Dict[str, Any] = {
    "vscode": _install_vscode,
    "claude": _install_claude,
    "cursor": _install_cursor,
}

_TARGET_CHOICES: List[str] = ["vscode", "claude", "cursor", "all"]


def register_mcp_commands(cli: Any) -> None:
    """Register the 'mcp' command group and its subcommands."""

    @cli.group()
    def mcp() -> None:
        """MCP (Model Context Protocol) server integration for AI assistants."""

    @mcp.command(name="serve")
    def serve() -> None:
        """Start the stdio MCP server.

        AI clients (VS Code Copilot, Claude Desktop, Cursor) should be configured
        to run this command as an MCP stdio server:

        \b
            command: slcli
            args: [mcp, serve]

        Use 'slcli mcp install' to write that configuration automatically.
        """
        try:
            from .mcp_server import main as run_mcp_server
        except ImportError:
            click.echo(
                "✗ The 'mcp' package is not installed.\n"
                "  Install it with: pip install 'mcp>=1.0'\n"
                "  Or in a Poetry project: poetry add mcp",
                err=True,
            )
            sys.exit(ExitCodes.GENERAL_ERROR)

        run_mcp_server()

    @mcp.command(name="install")
    @click.option(
        "--target",
        "-t",
        type=click.Choice(_TARGET_CHOICES),
        default="vscode",
        show_default=True,
        help=(
            "AI client to configure: vscode (.vscode/mcp.json), "
            "claude (Claude Desktop global config), "
            "cursor (.cursor/mcp.json), "
            "or all."
        ),
    )
    @click.option(
        "--exe",
        "slcli_exe",
        default=None,
        help=(
            "Path to the slcli executable to use in the config "
            "(auto-detected from PATH if not specified)"
        ),
    )
    def install(target: str, slcli_exe: Optional[str]) -> None:
        """Write MCP server configuration for an AI client.

        Automatically creates or updates the client's config file so it can
        discover and launch the slcli MCP server.

        \b
        Examples:
            slcli mcp install                      # VS Code (default)
            slcli mcp install --target claude      # Claude Desktop
            slcli mcp install --target cursor      # Cursor
            slcli mcp install --target all         # all three
        """
        exe = slcli_exe or _slcli_exe()

        targets_to_run: List[str] = list(_INSTALLERS.keys()) if target == "all" else [target]

        for t in targets_to_run:
            installer = _INSTALLERS[t]
            try:
                installer(exe)
            except Exception as exc:  # noqa: BLE001
                click.echo(f"✗ Failed to configure {t}: {exc}", err=True)
