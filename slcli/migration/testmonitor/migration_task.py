"""Persisted Prefect tasks that migrate Test Monitor batches."""

from typing import List
from urllib.parse import urlparse

from prefect import task
from prefect.cache_policies import INPUTS

from slcli.migration.connection import resolve_migration_connection
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
