"""Prefect tasks that migrate Test Monitor resources in batches."""

from typing import List
from urllib.parse import urlparse

from prefect import task
from prefect.cache_policies import INPUTS

from slcli.migration.connection import resolve_migration_connection
from slcli.migration.flows.batching import after_all, gather_batches, partition, shared_task_args
from slcli.migration.flows.service import service_task
from slcli.migration.testmonitor.client import TestMonitorClient
from slcli.migration.testmonitor.migration import (
    MigrationContext,
    log_batch,
    migrate_products,
    migrate_results,
)
from slcli.migration.testmonitor.models import (
    BatchResult,
    DiscoveredProduct,
    DiscoveredResult,
    TestMonitorDiscovery,
    TestMonitorMigration,
)
from slcli.migration.testmonitor.writer import TestMonitorWriter
from slcli.migration.workspaces import WorkspaceMapping


def _context(migration_id: str, source_profile: str, mapping: WorkspaceMapping) -> MigrationContext:
    source = resolve_migration_connection(source_profile)
    return MigrationContext(
        migration_id=migration_id,
        source_hostname=urlparse(source.base_url).hostname or source.base_url,
        mapping=mapping,
    )


# A completed batch is cached even when some items failed: without reconciliation,
# re-running it would duplicate the items that did migrate. A batch that raises
# before writing is not cached and runs again on the next attempt.
@task(
    name="migrate-test-monitor-products",
    task_run_name="products-{batch}",
    persist_result=True,
    result_serializer="json",
    cache_result_in_memory=False,
    cache_policy=INPUTS,
)
def migrate_products_task(
    migration_id: str,
    source_profile: str,
    destination_profile: str,
    mapping: WorkspaceMapping,
    batch: int,
    products: List[DiscoveredProduct],
) -> BatchResult:
    """Migrate one batch of products. Inputs are references, never credentials."""
    context = _context(migration_id, source_profile, mapping)
    source = TestMonitorClient(resolve_migration_connection(source_profile))
    destination = TestMonitorWriter(resolve_migration_connection(destination_profile))
    result = migrate_products(source, destination, context, batch, products)
    log_batch(result)
    return result


# A completed batch is cached even when some items failed: without reconciliation,
# re-running it would duplicate the items that did migrate. A batch that raises
# before writing is not cached and runs again on the next attempt.
@task(
    name="migrate-test-monitor-results",
    task_run_name="results-{batch}",
    persist_result=True,
    result_serializer="json",
    cache_result_in_memory=False,
    cache_policy=INPUTS,
)
def migrate_results_task(
    migration_id: str,
    source_profile: str,
    destination_profile: str,
    mapping: WorkspaceMapping,
    batch: int,
    results: List[DiscoveredResult],
) -> BatchResult:
    """Migrate one batch of results with their steps."""
    context = _context(migration_id, source_profile, mapping)
    source = TestMonitorClient(resolve_migration_connection(source_profile))
    destination = TestMonitorWriter(resolve_migration_connection(destination_profile))
    result = migrate_results(source, destination, context, batch, results)
    log_batch(result)
    return result


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
    product batch to finish. They run even when products failed: those results
    still migrate, but their source-to-destination product mapping is ambiguous
    and will need review. This will eventually be reported as a warning.

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
    results = migrate_results_task.map(
        *common,
        list(range(len(result_batches))),
        result_batches,
        wait_for=after_all(products),
    )
    return TestMonitorMigration(
        products=tuple(gather_batches("products", product_batches, products)),
        results=tuple(gather_batches("results", result_batches, results)),
    )
