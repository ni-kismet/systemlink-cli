"""Test Monitor service task: migrate products, then results, in batches."""

from typing import Any, List, Tuple

from prefect import allow_failure
from pydantic import ConfigDict

from slcli.migration.flows.batching import gather_batches, partition, shared_task_args
from slcli.migration.flows.service import service_task
from slcli.migration.schema import VersionedModel
from slcli.migration.testmonitor.migration_task import (
    migrate_products_task,
    migrate_results_task,
)
from slcli.migration.testmonitor.models import BatchResult, TestMonitorDiscovery
from slcli.migration.workspaces import WorkspaceMapping


class TestMonitorMigration(VersionedModel):
    """Batch outcomes for Test Monitor resources."""

    __test__ = False
    model_config = ConfigDict(frozen=True)

    products: Tuple[BatchResult, ...] = ()
    results: Tuple[BatchResult, ...] = ()


@service_task("migrate-test-monitor")
def migrate_test_monitor_task(
    migration_id: str,
    source_profile: str,
    destination_profile: str,
    mapping: WorkspaceMapping,
    discovery: TestMonitorDiscovery,
    product_batch_size: int,
    result_batch_size: int,
) -> TestMonitorMigration:
    """Migrate products, then results with their steps, in batch tasks.

    Results reference products by part number, so result batches wait for every
    product batch to finish, including batches that failed.

    Args:
        migration_id: Migration that scopes task cache keys.
        source_profile: Name of the source profile.
        destination_profile: Name of the destination profile.
        mapping: Resolved source-to-destination workspaces.
        discovery: Discovered Test Monitor resources.
        product_batch_size: Products per migration task.
        result_batch_size: Results, with their steps, per migration task.
    """
    common = shared_task_args(migration_id, source_profile, destination_profile, mapping)
    product_batches = partition(discovery.products, product_batch_size)
    products = migrate_products_task.map(
        *common, list(range(len(product_batches))), product_batches
    )
    result_batches = partition(discovery.results, result_batch_size)
    # Prefect accepts allow_failure in wait_for but does not annotate it.
    after_products: List[Any] = [allow_failure(future) for future in products]
    results = migrate_results_task.map(
        *common,
        list(range(len(result_batches))),
        result_batches,
        wait_for=after_products,
    )
    return TestMonitorMigration(
        products=tuple(gather_batches("products", product_batches, products)),
        results=tuple(gather_batches("results", result_batches, results)),
    )
