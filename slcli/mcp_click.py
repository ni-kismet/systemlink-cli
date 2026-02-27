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


def _install_codex(slcli_exe: str) -> None:
    """Write / update .codex/mcp.json in the current directory."""
    config_file = Path(".codex") / "mcp.json"
    _merge_and_write_json(
        config_file,
        top_key="mcpServers",
        server_name="slcli",
        server_entry=_claude_server_entry(slcli_exe),
    )
    click.echo(f"✓ Codex MCP config written to {config_file}")
    click.echo("  Reload Codex to activate the server.")


_INSTALLERS: Dict[str, Any] = {
    "vscode": _install_vscode,
    "claude": _install_claude,
    "cursor": _install_cursor,
    "codex": _install_codex,
}

_TARGET_CHOICES: List[str] = ["vscode", "claude", "cursor", "codex", "all"]


def register_mcp_commands(cli: Any) -> None:
    """Register the 'mcp' command group and its subcommands."""

    @cli.group()
    def mcp() -> None:
        """MCP (Model Context Protocol) server integration for AI assistants."""

    @mcp.command(name="serve")
    @click.option(
        "--transport",
        "-T",
        type=click.Choice(["stdio", "sse"]),
        default="stdio",
        show_default=True,
        help="Transport layer: 'stdio' for AI client integration, 'sse' for HTTP/SSE.",
    )
    @click.option(
        "--port",
        "-p",
        default=8000,
        show_default=True,
        help="Port to bind to (SSE transport only).",
    )
    @click.option(
        "--host",
        default="127.0.0.1",
        show_default=True,
        help="Host to bind to (SSE transport only).",
    )
    def serve(transport: str, port: int, host: str) -> None:
        """Start the MCP server.

        Defaults to stdio transport for direct AI client integration (VS Code
        Copilot, Claude Desktop, Cursor).  Switch to SSE transport to serve
        over HTTP — useful for the MCP Inspector, browser-based tooling, or
        any client that prefers a persistent HTTP connection.

        \b
        Stdio (default — configure once with 'slcli mcp install'):
            slcli mcp serve

        \b
        SSE (HTTP server on http://127.0.0.1:8000/sse):
            slcli mcp serve --transport sse
            slcli mcp serve --transport sse --host 0.0.0.0 --port 9000

        \b
        Test with the MCP Inspector (SSE):
            slcli mcp serve --transport sse
            npx @modelcontextprotocol/inspector
            # connect to http://127.0.0.1:8000/sse (transport: SSE)
        """
        try:
            from .mcp_server import main as run_mcp_server
            from .mcp_server import server as mcp_server
        except ImportError:
            click.echo(
                "✗ The 'mcp' package is not installed.\n"
                "  Install it with: pip install 'mcp>=1.0'\n"
                "  Or in a Poetry project: poetry add mcp",
                err=True,
            )
            sys.exit(ExitCodes.GENERAL_ERROR)

        if transport == "stdio":
            run_mcp_server()
        else:
            mcp_server.settings.host = host
            mcp_server.settings.port = port

            click.echo(f"✓ slcli MCP server starting in SSE mode on http://{host}:{port}/sse")
            click.echo("  Open the Inspector:  npx @modelcontextprotocol/inspector")
            click.echo(f"  Then connect to:     http://{host}:{port}/sse  (transport: SSE)")
            click.echo("  Press Ctrl+C to stop.\n")

            try:
                mcp_server.run(transport="sse")
            except KeyboardInterrupt:
                click.echo("\nslcli MCP server stopped")
                sys.exit(0)

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
            "codex (.codex/mcp.json), "
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
            slcli mcp install --target codex       # OpenAI Codex CLI
            slcli mcp install --target all         # all four
        """
        exe = slcli_exe or _slcli_exe()

        targets_to_run: List[str] = list(_INSTALLERS.keys()) if target == "all" else [target]

        for t in targets_to_run:
            installer = _INSTALLERS[t]
            try:
                installer(exe)
            except Exception as exc:  # noqa: BLE001
                click.echo(f"✗ Failed to configure {t}: {exc}", err=True)
