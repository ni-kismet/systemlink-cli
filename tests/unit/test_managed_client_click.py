"""Tests for the opt-in managed-client CLI commands."""

import subprocess
import sys
from pathlib import Path
from typing import Any

import click
import pytest
from click.testing import CliRunner

from slcli.managed_client.models import TransportError
from slcli.managed_client.state import StateStore
from slcli.managed_client_click import register_managed_client_commands
from slcli.utils import ExitCodes


def test_importing_cli_does_not_load_managed_client_protocol() -> None:
    """Importing the base CLI keeps optional protocol modules unloaded."""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import slcli.main; "
                "assert 'slcli.managed_client.protocol' not in sys.modules"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


@pytest.fixture
def cli() -> Any:
    """Return a small command group with managed-client commands registered."""

    @click.group()
    def test_cli() -> None:
        pass

    register_managed_client_commands(test_cli)
    return test_cli


def test_managed_client_help_lists_commands(cli: Any) -> None:
    """The explicit group exposes only the supported foreground commands."""
    result = CliRunner().invoke(cli, ["managed-client", "--help"])

    assert result.exit_code == 0
    assert "run" in result.output
    assert "reset" in result.output

    result = CliRunner().invoke(cli, ["managed-client", "run", "--help"])

    assert result.exit_code == 0
    assert "--max-reconnect-attempts INTEGER" in result.output
    assert "[default: 5" in result.output


def test_reset_removes_only_identity_state(cli: Any, tmp_path: Path) -> None:
    """Reset removes identity files while preserving the state directory."""
    StateStore(tmp_path).load_or_create_identity("slcli-test")

    result = CliRunner().invoke(
        cli,
        ["managed-client", "reset", "--state-dir", str(tmp_path), "--yes"],
    )

    assert result.exit_code == 0
    assert "Reset managed-client identity state" in result.output
    assert tmp_path.is_dir()
    assert not list(tmp_path.iterdir())


def test_reset_requires_confirmation(cli: Any, tmp_path: Path) -> None:
    """Reset aborts without confirmation for destructive cleanup."""
    StateStore(tmp_path).load_or_create_identity("slcli-test")

    result = CliRunner().invoke(
        cli,
        ["managed-client", "reset", "--state-dir", str(tmp_path)],
        input="n\n",
    )

    assert result.exit_code != 0
    assert "Aborted" in result.output
    assert list(tmp_path.iterdir())


def test_run_reports_invalid_master_without_traceback(cli: Any, tmp_path: Path) -> None:
    """Malformed master endpoints use the standard invalid-input exit code."""
    result = CliRunner().invoke(
        cli,
        [
            "managed-client",
            "run",
            "--master",
            "://",
            "--minion-id",
            "slcli-invalid-master",
            "--state-dir",
            str(tmp_path),
        ],
    )

    assert result.exit_code == ExitCodes.INVALID_INPUT
    assert "✗" in result.output
    assert "Traceback" not in result.output


def test_run_reports_invalid_configuration_without_traceback(cli: Any, tmp_path: Path) -> None:
    """Invalid configuration values are handled as normal CLI errors."""
    result = CliRunner().invoke(
        cli,
        [
            "managed-client",
            "run",
            "--master",
            "localhost",
            "--minion-id",
            "",
            "--state-dir",
            str(tmp_path),
        ],
    )

    assert result.exit_code == ExitCodes.INVALID_INPUT
    assert "✗" in result.output
    assert "Traceback" not in result.output


def test_run_reports_transport_failure_as_network_error(
    cli: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Runtime transport failures use the standard network exit code."""

    def fail_to_start(*args: Any, **kwargs: Any) -> None:
        del args, kwargs
        raise TransportError("network unavailable")

    monkeypatch.setattr("slcli.managed_client.TestMinion", fail_to_start)
    result = CliRunner().invoke(
        cli,
        [
            "managed-client",
            "run",
            "--master",
            "localhost",
            "--minion-id",
            "slcli-network-error",
            "--state-dir",
            str(tmp_path),
        ],
    )

    assert result.exit_code == ExitCodes.NETWORK_ERROR
    assert "network unavailable" in result.output
