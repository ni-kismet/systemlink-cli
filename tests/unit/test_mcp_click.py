"""Unit tests for slcli mcp CLI commands (serve, dev, and install)."""

import json
import sys
from pathlib import Path
from typing import Any

import click
import pytest
from click.testing import CliRunner

from slcli.mcp_click import (
    _claude_server_entry,
    _merge_and_write_json,
    _slcli_exe,
    _vscode_server_entry,
    register_mcp_commands,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def make_cli() -> click.Group:
    """Return a Click group with the mcp commands registered."""

    @click.group()
    def test_cli() -> None:
        pass

    register_mcp_commands(test_cli)
    return test_cli


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


# ---------------------------------------------------------------------------
# Unit helpers
# ---------------------------------------------------------------------------


def test_slcli_exe_returns_path_when_found(monkeypatch: Any) -> None:
    """_slcli_exe returns the resolved path when shutil.which finds slcli."""
    monkeypatch.setattr("shutil.which", lambda name: "/usr/local/bin/slcli")
    assert _slcli_exe() == "/usr/local/bin/slcli"


def test_slcli_exe_returns_fallback_when_not_found(monkeypatch: Any) -> None:
    """_slcli_exe returns the bare string 'slcli' when which returns None."""
    monkeypatch.setattr("shutil.which", lambda name: None)
    assert _slcli_exe() == "slcli"


def test_vscode_server_entry_format() -> None:
    """_vscode_server_entry returns the correct VS Code MCP object."""
    entry = _vscode_server_entry("/usr/local/bin/slcli")
    assert entry == {
        "type": "stdio",
        "command": "/usr/local/bin/slcli",
        "args": ["mcp", "serve"],
    }


def test_claude_server_entry_format() -> None:
    """_claude_server_entry returns the correct Claude / Cursor MCP object (no 'type' key)."""
    entry = _claude_server_entry("/usr/local/bin/slcli")
    assert entry == {
        "command": "/usr/local/bin/slcli",
        "args": ["mcp", "serve"],
    }
    assert "type" not in entry


# ---------------------------------------------------------------------------
# _merge_and_write_json
# ---------------------------------------------------------------------------


def test_merge_and_write_json_creates_new_file(tmp_path: Path) -> None:
    """Creates the config file (and parent dirs) when it does not exist."""
    config_file = tmp_path / "sub" / "mcp.json"
    _merge_and_write_json(config_file, "servers", "slcli", {"command": "slcli"})

    assert config_file.exists()
    data = json.loads(config_file.read_text())
    assert data["servers"]["slcli"] == {"command": "slcli"}


def test_merge_and_write_json_merges_with_existing(tmp_path: Path) -> None:
    """Does not remove pre-existing server entries when writing."""
    config_file = tmp_path / "mcp.json"
    config_file.write_text(
        json.dumps({"servers": {"other-server": {"command": "other"}}}), encoding="utf-8"
    )

    _merge_and_write_json(config_file, "servers", "slcli", {"command": "slcli"})

    data = json.loads(config_file.read_text())
    assert "other-server" in data["servers"]
    assert "slcli" in data["servers"]


def test_merge_and_write_json_overwrites_existing_entry(tmp_path: Path) -> None:
    """Overwrites the slcli entry if it already exists."""
    config_file = tmp_path / "mcp.json"
    config_file.write_text(
        json.dumps({"servers": {"slcli": {"command": "oldslcli"}}}), encoding="utf-8"
    )

    _merge_and_write_json(config_file, "servers", "slcli", {"command": "newslcli"})

    data = json.loads(config_file.read_text())
    assert data["servers"]["slcli"]["command"] == "newslcli"


# ---------------------------------------------------------------------------
# slcli mcp serve
# ---------------------------------------------------------------------------


def test_mcp_serve_calls_mcp_server_main(monkeypatch: Any, runner: CliRunner) -> None:
    """The serve command invokes mcp_server.main() on success."""
    import slcli.mcp_server as _mcp_server_module

    called: list = []

    def mock_main() -> None:
        called.append(True)

    monkeypatch.setattr(_mcp_server_module, "main", mock_main)

    cli = make_cli()
    result = runner.invoke(cli, ["mcp", "serve"])
    assert result.exit_code == 0
    assert called == [True]


def test_mcp_serve_import_error_shows_helpful_message(monkeypatch: Any, runner: CliRunner) -> None:
    """Serve exits non-zero with a helpful message when mcp_server is unavailable."""
    # Setting sys.modules entry to None causes ImportError on `from .mcp_server import ...`
    monkeypatch.setitem(sys.modules, "slcli.mcp_server", None)  # type: ignore[arg-type]

    cli = make_cli()
    result = runner.invoke(cli, ["mcp", "serve"])
    assert result.exit_code != 0
    assert "mcp" in result.output.lower() or "mcp" in (result.stderr or "").lower()


# ---------------------------------------------------------------------------
# slcli mcp serve --transport sse
# ---------------------------------------------------------------------------


def test_mcp_serve_sse_calls_server_run_sse(monkeypatch: Any, runner: CliRunner) -> None:
    """Running serve --transport sse calls server.run(transport='sse') on success."""
    import slcli.mcp_server as _mcp_server_module

    captured: list = []

    class MockSettings:
        host: str = "127.0.0.1"
        port: int = 8000

    mock_settings = MockSettings()
    monkeypatch.setattr(_mcp_server_module.server, "settings", mock_settings)
    monkeypatch.setattr(
        _mcp_server_module.server,
        "run",
        lambda transport="stdio": captured.append(transport),
    )
    monkeypatch.setattr(_mcp_server_module, "main", lambda: None)

    cli = make_cli()
    result = runner.invoke(cli, ["mcp", "serve", "--transport", "sse"])
    assert result.exit_code == 0
    assert captured == ["sse"]


def test_mcp_serve_sse_custom_port(monkeypatch: Any, runner: CliRunner) -> None:
    """Running serve --transport sse applies --port and --host to server.settings."""
    import slcli.mcp_server as _mcp_server_module

    class MockSettings:
        host: str = "127.0.0.1"
        port: int = 8000

    mock_settings = MockSettings()
    monkeypatch.setattr(_mcp_server_module.server, "settings", mock_settings)
    monkeypatch.setattr(_mcp_server_module.server, "run", lambda transport="stdio": None)
    monkeypatch.setattr(_mcp_server_module, "main", lambda: None)

    cli = make_cli()
    runner.invoke(
        cli, ["mcp", "serve", "--transport", "sse", "--port", "9000", "--host", "0.0.0.0"]
    )
    assert mock_settings.host == "0.0.0.0"
    assert mock_settings.port == 9000


def test_mcp_serve_sse_shows_inspector_instructions(monkeypatch: Any, runner: CliRunner) -> None:
    """Running serve --transport sse prints the Inspector URL and SSE endpoint."""
    import slcli.mcp_server as _mcp_server_module

    class MockSettings:
        host: str = "127.0.0.1"
        port: int = 8000

    monkeypatch.setattr(_mcp_server_module.server, "settings", MockSettings())
    monkeypatch.setattr(_mcp_server_module.server, "run", lambda transport="stdio": None)
    monkeypatch.setattr(_mcp_server_module, "main", lambda: None)

    cli = make_cli()
    result = runner.invoke(cli, ["mcp", "serve", "--transport", "sse"])
    assert "127.0.0.1:8000/sse" in result.output
    assert "inspector" in result.output.lower()


def test_mcp_serve_sse_import_error_shows_helpful_message(
    monkeypatch: Any, runner: CliRunner
) -> None:
    """Running serve --transport sse exits non-zero when mcp_server is unavailable."""
    monkeypatch.setitem(sys.modules, "slcli.mcp_server", None)  # type: ignore[arg-type]

    cli = make_cli()
    result = runner.invoke(cli, ["mcp", "serve", "--transport", "sse"])
    assert result.exit_code != 0
    assert "mcp" in result.output.lower() or "mcp" in (result.stderr or "").lower()


# ---------------------------------------------------------------------------
# slcli mcp install --target vscode
# ---------------------------------------------------------------------------


def test_mcp_install_vscode_creates_file(monkeypatch: Any, runner: CliRunner) -> None:
    """Running install --target vscode creates .vscode/mcp.json in cwd."""
    monkeypatch.setattr("shutil.which", lambda name: "/usr/local/bin/slcli")

    with runner.isolated_filesystem():
        cli = make_cli()
        result = runner.invoke(cli, ["mcp", "install", "--target", "vscode"])
        assert result.exit_code == 0

        config_file = Path(".vscode") / "mcp.json"
        assert config_file.exists(), f".vscode/mcp.json not found; output: {result.output}"
        data = json.loads(config_file.read_text())
        assert data["servers"]["slcli"]["type"] == "stdio"
        assert data["servers"]["slcli"]["args"] == ["mcp", "serve"]


def test_mcp_install_vscode_default_target(monkeypatch: Any, runner: CliRunner) -> None:
    """Running install with no --target option defaults to vscode."""
    monkeypatch.setattr("shutil.which", lambda name: "/usr/local/bin/slcli")

    with runner.isolated_filesystem():
        cli = make_cli()
        result = runner.invoke(cli, ["mcp", "install"])
        assert result.exit_code == 0
        assert Path(".vscode/mcp.json").exists()


def test_mcp_install_vscode_custom_exe(monkeypatch: Any, runner: CliRunner) -> None:
    """The --exe option overrides the auto-detected executable path."""
    with runner.isolated_filesystem():
        cli = make_cli()
        result = runner.invoke(
            cli, ["mcp", "install", "--target", "vscode", "--exe", "/custom/slcli"]
        )
        assert result.exit_code == 0
        data = json.loads(Path(".vscode/mcp.json").read_text())
        assert data["servers"]["slcli"]["command"] == "/custom/slcli"


# ---------------------------------------------------------------------------
# slcli mcp install --target claude
# ---------------------------------------------------------------------------


def test_mcp_install_claude_creates_file(
    monkeypatch: Any, runner: CliRunner, tmp_path: Path
) -> None:
    """Running install --target claude creates the Claude Desktop config file."""
    config_path = tmp_path / "claude_desktop_config.json"
    monkeypatch.setattr("slcli.mcp_click._find_claude_config_file", lambda: config_path)
    monkeypatch.setattr("shutil.which", lambda name: "/usr/local/bin/slcli")

    cli = make_cli()
    result = runner.invoke(cli, ["mcp", "install", "--target", "claude"])
    assert result.exit_code == 0

    assert config_path.exists(), f"config file not found; output: {result.output}"
    data = json.loads(config_path.read_text())
    assert "slcli" in data["mcpServers"]
    assert data["mcpServers"]["slcli"]["command"] == "/usr/local/bin/slcli"
    assert "type" not in data["mcpServers"]["slcli"]


def test_mcp_install_claude_merges_with_existing(
    monkeypatch: Any, runner: CliRunner, tmp_path: Path
) -> None:
    """Running install --target claude preserves pre-existing mcpServers entries."""
    config_path = tmp_path / "claude_desktop_config.json"
    config_path.write_text(
        json.dumps({"mcpServers": {"myother": {"command": "other"}}}), encoding="utf-8"
    )
    monkeypatch.setattr("slcli.mcp_click._find_claude_config_file", lambda: config_path)
    monkeypatch.setattr("shutil.which", lambda name: "slcli")

    cli = make_cli()
    runner.invoke(cli, ["mcp", "install", "--target", "claude"])

    data = json.loads(config_path.read_text())
    assert "myother" in data["mcpServers"]
    assert "slcli" in data["mcpServers"]


# ---------------------------------------------------------------------------
# slcli mcp install --target cursor
# ---------------------------------------------------------------------------


def test_mcp_install_cursor_creates_file(monkeypatch: Any, runner: CliRunner) -> None:
    """Running install --target cursor creates .cursor/mcp.json in cwd."""
    monkeypatch.setattr("shutil.which", lambda name: "/usr/local/bin/slcli")

    with runner.isolated_filesystem():
        cli = make_cli()
        result = runner.invoke(cli, ["mcp", "install", "--target", "cursor"])
        assert result.exit_code == 0

        config_file = Path(".cursor") / "mcp.json"
        assert config_file.exists(), f".cursor/mcp.json not found; output: {result.output}"
        data = json.loads(config_file.read_text())
        assert "slcli" in data["mcpServers"]
        assert data["mcpServers"]["slcli"]["command"] == "/usr/local/bin/slcli"


# ---------------------------------------------------------------------------
# slcli mcp install --target all
# ---------------------------------------------------------------------------


def test_mcp_install_codex_creates_file(monkeypatch: Any, runner: CliRunner) -> None:
    """Running install --target codex creates .codex/mcp.json in cwd."""
    monkeypatch.setattr("shutil.which", lambda name: "/usr/local/bin/slcli")

    with runner.isolated_filesystem():
        cli = make_cli()
        result = runner.invoke(cli, ["mcp", "install", "--target", "codex"])
        assert result.exit_code == 0

        config_file = Path(".codex") / "mcp.json"
        assert config_file.exists(), f".codex/mcp.json not found; output: {result.output}"
        data = json.loads(config_file.read_text())
        assert "slcli" in data["mcpServers"]
        assert data["mcpServers"]["slcli"]["command"] == "/usr/local/bin/slcli"


def test_mcp_install_all_targets(monkeypatch: Any, runner: CliRunner, tmp_path: Path) -> None:
    """Running install --target all writes configs for vscode, claude, cursor, and windsurf."""
    claude_config = tmp_path / "claude_desktop_config.json"
    monkeypatch.setattr("slcli.mcp_click._find_claude_config_file", lambda: claude_config)
    monkeypatch.setattr("shutil.which", lambda name: "slcli")

    with runner.isolated_filesystem():
        cli = make_cli()
        result = runner.invoke(cli, ["mcp", "install", "--target", "all"])
        assert result.exit_code == 0

        assert Path(".vscode/mcp.json").exists(), "VS Code config missing"
        assert Path(".cursor/mcp.json").exists(), "Cursor config missing"
        assert Path(".codex/mcp.json").exists(), "Codex config missing"

    assert claude_config.exists(), "Claude config missing"
    assert "vscode" in result.output.lower() or "VS Code" in result.output
