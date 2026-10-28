"""Contract checks shared by registered CLI commands."""

from typing import Iterator, Tuple

import click
import pytest
from click.testing import CliRunner

from slcli.main import cli


def _commands(
    group: click.Group, path: Tuple[str, ...] = ()
) -> Iterator[Tuple[Tuple[str, ...], click.Command]]:
    for name, command in group.commands.items():
        command_path = (*path, name)
        yield command_path, command
        if isinstance(command, click.Group):
            yield from _commands(command, command_path)


_TAKE_COMMANDS = [
    path
    for path, command in _commands(cli)
    if any(isinstance(param, click.Option) and "--take" in param.opts for param in command.params)
]


@pytest.mark.parametrize("path", _TAKE_COMMANDS, ids=lambda path: " ".join(path))
@pytest.mark.parametrize("count", ["0", "-1"])
def test_take_rejects_nonpositive_counts(path: Tuple[str, ...], count: str) -> None:
    """Every result count rejects invalid input before running a command callback."""
    result = CliRunner().invoke(cli, [*path, "--take", count], prog_name="slcli")
    assert result.exit_code == 2, result.output
    assert "not in the range" in result.output, result.output
