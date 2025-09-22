"""Decorators and helpers for Dynamic Form Fields (DFF) testing and CLI behavior.

This module provides lightweight decorator utilities used by the CLI tests and
command implementations. Keep implementations minimal and well-typed.
"""

from typing import Callable, TypeVar

F = TypeVar("F", bound=Callable[..., object])


def passthrough_decorator(func: F) -> F:
    """A no-op decorator used in testing to preserve function metadata.

    Returns the original function unchanged. Useful as a placeholder when a
    decorator is required by test scaffolding but implements no behavior.

    Args:
        func: The callable to return.

    Returns:
        The original callable ``func``.
    """
    return func
