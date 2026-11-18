"""Helpers shared by every resource type that migrates in batches."""

import logging
from typing import Any, Iterable, List, Protocol, Sequence, Tuple, TypeVar

from prefect import allow_failure, unmapped
from prefect.futures import PrefectFuture, PrefectFutureList

from slcli.migration.testmonitor.models import BatchResult, FailedItem
from slcli.migration.workspaces import WorkspaceMapping

_T = TypeVar("_T")
_logger = logging.getLogger(__name__)


class Identified(Protocol):
    """An item that reports failures by its source ID."""

    @property
    def id(self) -> str:
        """Return the source ID."""
        ...


def partition(items: Sequence[_T], size: int) -> List[List[_T]]:
    """Split items into stable, ordered batches of at most ``size``."""
    if size < 1:
        raise ValueError("batch size must be at least 1")
    return [list(items[start : start + size]) for start in range(0, len(items), size)]


def gather_batches(
    resource: str,
    batches: Sequence[Sequence[Identified]],
    futures: PrefectFutureList[BatchResult],
) -> List[BatchResult]:
    """Wait for every batch; a batch that raised reports all of its items as failed."""
    outcomes: List[BatchResult] = []
    for index, (batch, future) in enumerate(zip(batches, futures)):
        future.wait()
        if future.state.is_completed():
            outcomes.append(future.result())
            continue
        error = future.state.result(raise_on_failure=False)
        error_type = type(error).__name__ if isinstance(error, BaseException) else "Failed"
        _logger.error("Batch %s[%d] failed before migrating: %s", resource, index, error_type)
        outcomes.append(
            BatchResult(
                resource=resource,
                batch=index,
                failed=tuple(
                    FailedItem(source_id=item.id, stage="batch", error_type=error_type)
                    for item in batch
                ),
            )
        )
    return outcomes


def after_all(futures: Iterable[PrefectFuture[Any]]) -> List[Any]:
    """Return ``wait_for`` dependencies that are met once every future finishes.

    Unlike plain futures, these are met by failed and crashed futures too.
    """
    # Prefect accepts allow_failure in wait_for but does not annotate it.
    return [allow_failure(future) for future in futures]


def shared_task_args(
    migration_id: str, source_profile: str, destination_profile: str, mapping: WorkspaceMapping
) -> Tuple[Any, ...]:
    """Return the leading arguments every batch task receives.

    ``Task.map`` iterates sequence arguments; ``unmapped`` passes these unchanged
    to every batch instead.
    """
    return (
        unmapped(migration_id),
        unmapped(source_profile),
        unmapped(destination_profile),
        unmapped(mapping),
    )
