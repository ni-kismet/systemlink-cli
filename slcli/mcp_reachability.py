"""Helpers for classifying local MCP client connectivity failures."""

from typing import Iterator, List


def iter_exceptions(exc: BaseException) -> Iterator[BaseException]:
    """Yield an exception plus any nested causes, contexts, or exception-group members."""
    stack: List[BaseException] = [exc]
    seen: set[int] = set()

    while stack:
        current = stack.pop()
        marker = id(current)
        if marker in seen:
            continue
        seen.add(marker)
        yield current

        cause = getattr(current, "__cause__", None)
        if isinstance(cause, BaseException):
            stack.append(cause)

        context = getattr(current, "__context__", None)
        if isinstance(context, BaseException):
            stack.append(context)

        if isinstance(current, BaseExceptionGroup):
            stack.extend(current.exceptions)


def is_reachability_failure(exc: BaseException) -> bool:
    """Return True when an exception indicates the local MCP server is unreachable."""
    for candidate in iter_exceptions(exc):
        if isinstance(candidate, (OSError, TimeoutError)):
            return True

        message = str(candidate).lower()
        if any(
            token in message
            for token in (
                "connection refused",
                "connect error",
                "all connection attempts failed",
                "timed out",
                "timeout",
                "name or service not known",
                "nodename nor servname provided",
                "server disconnected",
            )
        ):
            return True

    return False