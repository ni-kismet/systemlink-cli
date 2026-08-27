"""Tests for shared CLI utility behavior."""

from typing import Any, List

from slcli.cli_utils import is_interactive_environment, paginate_list_output


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
