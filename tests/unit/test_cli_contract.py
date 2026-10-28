"""Contract checks shared by registered CLI commands."""

from typing import Any, Iterator, Tuple

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

_DESTRUCTIVE_COMMANDS = [
    (path, command)
    for path, command in _commands(cli)
    if path[-1] in {"delete", "remove", "reset", "force-clear", "revert", "logout"}
]


@pytest.mark.parametrize(
    "path,command", _DESTRUCTIVE_COMMANDS, ids=[" ".join(path) for path, _ in _DESTRUCTIVE_COMMANDS]
)
def test_destructive_confirmation_aliases_and_noninteractive_guard(
    path: Tuple[str, ...], command: click.Command, monkeypatch: Any
) -> None:
    """Destructive commands preserve explicit consent and fail clearly without a TTY."""
    monkeypatch.setenv("SLCLI_NON_INTERACTIVE", "true")
    option = next(
        param
        for param in command.params
        if isinstance(param, click.Option) and "--yes" in param.opts
    )
    assert "-y" in option.opts
    if path == ("example", "delete"):
        return  # Dry-run is checked in the callback before consent is required.
    assert option.callback is not None
    context = click.Context(command)
    with pytest.raises(click.BadParameter, match="pass --yes"):
        option.callback(context, option, False)
    option.callback(context, option, True)


def test_registered_list_output_contract() -> None:
    """List commands share formats and aliases, with explicit legacy exceptions."""
    unpaginated = set()
    legacy_format_aliases = {("feed", "package", "list"), ("function", "execute", "list")}
    for path, command in _commands(cli):
        options = {
            flag: param
            for param in command.params
            if isinstance(param, click.Option)
            for flag in param.opts
        }
        if "--take" in options:
            assert "-t" in options["--take"].opts, path
        if path[-1] != "list":
            continue
        output_format = options["--format"]
        assert isinstance(output_format.type, click.Choice)
        assert {"table", "json"} <= set(output_format.type.choices), path
        assert "-f" in output_format.opts or path in legacy_format_aliases, path
        if "--take" not in options:
            unpaginated.add(path)
    assert unpaginated == {("comment", "list"), ("config", "trust", "list"), ("example", "list")}


@pytest.mark.parametrize("path", _TAKE_COMMANDS, ids=lambda path: " ".join(path))
@pytest.mark.parametrize("count", ["0", "-1"])
def test_take_rejects_nonpositive_counts(path: Tuple[str, ...], count: str) -> None:
    """Every result count rejects invalid input before running a command callback."""
    result = CliRunner().invoke(cli, [*path, "--take", count], prog_name="slcli")
    assert result.exit_code == 2, result.output
    assert "not in the range" in result.output, result.output
