"""Migration flow: discover, then migrate batches of each resource type."""

import logging
from typing import Any, List, Optional, Protocol, Sequence, Tuple, TypeVar

from prefect import flow, unmapped
from prefect.futures import PrefectFutureList
from pydantic import ConfigDict

from slcli.migration.flows.discover import MigrationDiscovery, discover_flow
from slcli.migration.schema import VersionedModel
from slcli.migration.testmonitor.migration_task import (
    migrate_products_task,
    migrate_results_task,
)
from slcli.migration.testmonitor.models import BatchResult, FailedItem
from slcli.migration.workspaces import WorkspaceMapping

_T = TypeVar("_T")
_logger = logging.getLogger(__name__)


class _Identified(Protocol):
    @property
    def id(self) -> str: ...


class TestMonitorMigration(VersionedModel):
    """Batch outcomes for Test Monitor resources."""

    __test__ = False
    model_config = ConfigDict(frozen=True)

    products: Tuple[BatchResult, ...] = ()
    results: Tuple[BatchResult, ...] = ()


class MigrationOutcome(VersionedModel):
    """Discovery and migration outcomes of one run."""

    model_config = ConfigDict(frozen=True)

    discovery: MigrationDiscovery
    test_monitor: TestMonitorMigration


def partition(items: Sequence[_T], size: int) -> List[List[_T]]:
    """Split items into stable, ordered batches of at most ``size``."""
    if size < 1:
        raise ValueError("batch size must be at least 1")
    return [list(items[start : start + size]) for start in range(0, len(items), size)]


def _gather(
    resource: str,
    batches: Sequence[Sequence[_Identified]],
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


def _shared_task_args(
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


@flow(
    name="systemlink-migration",
    flow_run_name="migration-{migration_id}",
    persist_result=True,
    result_serializer="json",
)
def migrate_flow(
    migration_id: str,
    source_profile: str,
    destination_profile: str,
    workspaces: Optional[List[str]],
    mapping: WorkspaceMapping,
    product_batch_size: int,
    result_batch_size: int,
) -> MigrationOutcome:
    """Discover source resources, then migrate products before results.

    Args:
        migration_id: Migration that scopes task cache keys.
        source_profile: Name of the source profile.
        destination_profile: Name of the destination profile.
        workspaces: Source workspace names to discover; all workspaces when None.
        mapping: Resolved source-to-destination workspaces.
        product_batch_size: Products per migration task.
        result_batch_size: Results, with their steps, per migration task.
    """
    discovery = discover_flow(migration_id, source_profile, workspaces)
    test_monitor = discovery.test_monitor
    common = _shared_task_args(migration_id, source_profile, destination_profile, mapping)
    product_batches = partition(test_monitor.products, product_batch_size)
    products = _gather(
        "products",
        product_batches,
        migrate_products_task.map(*common, list(range(len(product_batches))), product_batches),
    )
    # Results reference products by part number, so all products are attempted first.
    result_batches = partition(test_monitor.results, result_batch_size)
    results = _gather(
        "results",
        result_batches,
        migrate_results_task.map(*common, list(range(len(result_batches))), result_batches),
    )
    return MigrationOutcome(
        discovery=discovery,
        test_monitor=TestMonitorMigration(products=tuple(products), results=tuple(results)),
    )
