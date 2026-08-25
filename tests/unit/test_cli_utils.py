"""Tests for shared CLI utility behavior."""

from typing import Any

from slcli.cli_utils import is_interactive_environment


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
