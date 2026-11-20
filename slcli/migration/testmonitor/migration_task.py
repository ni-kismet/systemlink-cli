"""Prefect tasks that migrate Test Monitor resources in batches."""

import hashlib
import json
from typing import Dict, List
from urllib.parse import urlparse

from prefect import task, unmapped
from prefect.cache_policies import INPUTS

from slcli.migration.connection import resolve_migration_connection
from slcli.migration.flows.batching import after_all, gather_batches, partition, shared_task_args
from slcli.migration.flows.service import service_task
from slcli.migration.testmonitor.client import TestMonitorClient
from slcli.migration.testmonitor.completion import complete_results
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
    cache_policy=INPUTS - "file_id_map",
)
def migrate_results_task(
    migration_id: str,
    source_profile: str,
    destination_profile: str,
    mapping: WorkspaceMapping,
    batch: int,
    results: List[DiscoveredResult],
    file_id_map: Dict[str, str],
    file_id_map_digest: str,
) -> BatchResult:
    """Migrate results; the shared file map's digest participates in the cache key."""
    context = _context(migration_id, source_profile, mapping)
    source = TestMonitorClient(resolve_migration_connection(source_profile))
    destination = TestMonitorWriter(resolve_migration_connection(destination_profile))
    result = migrate_results(source, destination, context, batch, results, file_id_map)
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
    file_id_map: Dict[str, str],
) -> TestMonitorMigration:
    """Migrate products, then results with their steps, in batch tasks.

    Results reference products by part number, so result batches wait for every
    product batch to finish. They run even when products failed: those results
    still migrate, but their source-to-destination product mapping is ambiguous
    and will need review. This will eventually be reported as a warning.
    Migrated results are then marked COMPLETE.

    Args:
        migration_id: Migration that scopes task cache keys.
        source_profile: Name of the source profile.
        destination_profile: Name of the destination profile.
        mapping: Resolved source-to-destination workspaces.
        discovery: Discovered Test Monitor resources.
        product_batch_size: Products per migration task.
        result_batch_size: Results, with their steps, per migration task.
        file_id_map: Pre-allocated destination IDs keyed by source file ID.

    Raises:
        ValueError: If the destination profile is readonly or a completion update fails.
    """
    common = shared_task_args(migration_id, source_profile, destination_profile, mapping)
    product_batches = partition(discovery.products, product_batch_size)
    products = migrate_products_task.map(
        *common, list(range(len(product_batches))), product_batches
    )
    result_batches = partition(discovery.results, result_batch_size)
    file_id_map_digest = hashlib.sha256(
        json.dumps(file_id_map, sort_keys=True).encode("utf-8")
    ).hexdigest()
    results = migrate_results_task.map(
        *common,
        list(range(len(result_batches))),
        result_batches,
        unmapped(file_id_map),
        unmapped(file_id_map_digest),
        wait_for=after_all(products),
    )
    migration = TestMonitorMigration(
        products=tuple(gather_batches("products", product_batches, products)),
        results=tuple(gather_batches("results", result_batches, results)),
    )
    destination = resolve_migration_connection(destination_profile)
    if destination.readonly:
        raise ValueError(f"Profile '{destination_profile}' is in readonly mode")
    complete_results(TestMonitorWriter(destination), migration)
    return migration
