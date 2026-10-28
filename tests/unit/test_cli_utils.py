"""Tests for shared CLI utility behavior."""

from typing import Any, List
from unittest.mock import Mock

import click
import pytest

from slcli.cli_utils import (
    confirm_bulk_operation,
    confirmation_option,
    is_interactive_environment,
    paginate_list_output,
)


@pytest.mark.parametrize("answer", ["y", "n"])
def test_confirmation_option_preserves_interactive_consent(answer: str) -> None:
    """Interactive users can accept or decline without executing on refusal."""
    from click.testing import CliRunner

    invoked = Mock()

    @click.command()
    @confirmation_option("Delete this resource?")
    def command() -> None:
        invoked()

    result = CliRunner().invoke(command, input=f"{answer}\n")
    assert result.exit_code == (0 if answer == "y" else 1)
    assert invoked.call_count == (1 if answer == "y" else 0)


def test_bulk_confirmation_requires_explicit_noninteractive_consent(monkeypatch: Any) -> None:
    """The shared confirmation helper never prompts when automation lacks consent."""
    monkeypatch.setenv("SLCLI_NON_INTERACTIVE", "true")
    prompt = Mock(side_effect=AssertionError("Must not prompt"))
    monkeypatch.setattr("slcli.cli_utils.click.confirm", prompt)
    with pytest.raises(SystemExit) as result:
        confirm_bulk_operation("delete", "record", 2)
    assert result.value.code == 2
    assert confirm_bulk_operation("delete", "record", 2, force=True)
    assert not confirm_bulk_operation("delete", "record", 0, force=True)


def test_noninteractive_table_stops_after_one_page(monkeypatch: Any, capsys: Any) -> None:
    """Captured table output has one page and a remaining-results notice on stderr."""
    monkeypatch.setenv("SLCLI_NON_INTERACTIVE", "true")
    paginate_list_output([{"id": str(i)} for i in range(3)], page_size=1)
    output = capsys.readouterr()
    assert output.out.strip() == "{'id': '0'}"
    assert "Showing 1 of 3" in output.err


@pytest.mark.parametrize("items", [[], [{"id": "1"}, {"id": "2"}]])
def test_json_output_is_complete_and_prompt_free(
    monkeypatch: Any, capsys: Any, items: list
) -> None:
    """Machine output is a single array even when its size exceeds a display page."""
    import json

    monkeypatch.setenv("SLCLI_NON_INTERACTIVE", "true")
    paginate_list_output(items, page_size=1, format_output="json")
    output = capsys.readouterr()
    assert json.loads(output.out) == items
    assert not output.err


@pytest.mark.parametrize("page_size", [0, -1])
def test_paginate_list_output_rejects_nonpositive_page_size(page_size: int) -> None:
    """Direct helper callers cannot enter a non-advancing pagination loop."""
    with pytest.raises(SystemExit) as result:
        paginate_list_output([{"id": "1"}], page_size=page_size)
    assert result.value.code == 2


def test_is_interactive_environment_honors_explicit_override(monkeypatch: Any) -> None:
    """The explicit non-interactive flag takes precedence over other signals."""
    monkeypatch.setenv("SLCLI_NON_INTERACTIVE", "TRUE")
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "test_is_interactive_environment")

    assert is_interactive_environment() is False


def test_is_interactive_environment_allows_in_process_prompt_tests(monkeypatch: Any) -> None:
    """Pytest callers can exercise prompt paths with mocked prompt implementations."""
    monkeypatch.delenv("SLCLI_NON_INTERACTIVE", raising=False)
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.setenv("PYTEST_CURRENT_TEST", "test_is_interactive_environment")

    assert is_interactive_environment() is True


def test_is_interactive_environment_rejects_ci(monkeypatch: Any) -> None:
    """CI execution is non-interactive when no explicit test override is present."""
    monkeypatch.delenv("SLCLI_NON_INTERACTIVE", raising=False)
    monkeypatch.delenv("PYTEST_CURRENT_TEST", raising=False)
    monkeypatch.setenv("CI", "true")

    assert is_interactive_environment() is False


def test_paginate_list_output_uses_configured_page_size_in_prompt(monkeypatch: Any) -> None:
    """Pagination prompts should describe the actual page size being fetched."""
    monkeypatch.delenv("SLCLI_NON_INTERACTIVE", raising=False)
    prompt_messages: List[str] = []

    class Prompt:
        def ask(self) -> bool:
            return False

    def confirm(message: str, default: bool = True) -> Prompt:
        prompt_messages.append(message)
        return Prompt()

    monkeypatch.setattr("slcli.cli_utils.questionary.confirm", confirm)

    paginate_list_output([{"id": str(index)} for index in range(11)], page_size=10)

    assert prompt_messages == ["Show next 10 results?"]
