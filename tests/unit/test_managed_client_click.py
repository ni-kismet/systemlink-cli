"""Tests for the opt-in managed-client CLI commands."""

from pathlib import Path
from typing import Any

import click
import pytest
from click.testing import CliRunner

from slcli.managed_client.state import StateStore
from slcli.managed_client_click import register_managed_client_commands


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
