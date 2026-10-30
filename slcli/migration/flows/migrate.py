"""Migration flow: resolve workspaces, discover, then migrate each resource type."""

from typing import Dict, Optional

from prefect import flow
from pydantic import ConfigDict

from slcli.migration.flows.discover import MigrationDiscovery, discover_flow
from slcli.migration.flows.service import migration_task_runner
from slcli.migration.schema import VersionedModel
from slcli.migration.testmonitor.pipeline import TestMonitorMigration, migrate_test_monitor_task
from slcli.migration.workspace_task import resolve_workspaces_task
from slcli.migration.workspaces import WorkspaceMapping


class MigrationOutcome(VersionedModel):
    """Workspace mapping, discovery, and migration outcomes of one run."""

    model_config = ConfigDict(frozen=True)

    mapping: WorkspaceMapping
    discovery: MigrationDiscovery
    test_monitor: TestMonitorMigration


@flow(
    name="systemlink-migration",
    flow_run_name="migration-{migration_id}",
    persist_result=True,
    result_serializer="json",
    task_runner=migration_task_runner(),
)
def migrate_flow(
    migration_id: str,
    source_profile: str,
    destination_profile: str,
    workspace_mappings: Optional[Dict[str, str]],
    product_batch_size: int,
    result_batch_size: int,
) -> MigrationOutcome:
    """Resolve workspaces, discover source resources, then migrate them.

    Each resource type is a service task (see :func:`service_task`). Submitted
    service tasks run in parallel; pass ``wait_for`` to sequence them.

    Args:
        migration_id: Migration that scopes task cache keys.
        source_profile: Name of the source profile.
        destination_profile: Name of the destination profile.
        workspace_mappings: Source to destination workspace names; all by name when None.
        product_batch_size: Products per migration task.
        result_batch_size: Results, with their steps, per migration task.
    """
    mapping = resolve_workspaces_task(
        migration_id, source_profile, destination_profile, workspace_mappings
    )
    workspaces = [workspace.source_name for workspace in mapping.workspaces]
    discovery = discover_flow(migration_id, source_profile, workspaces)
    test_monitor = migrate_test_monitor_task.submit(
        migration_id,
        source_profile,
        destination_profile,
        mapping,
        discovery.test_monitor,
        product_batch_size,
        result_batch_size,
    )
    return MigrationOutcome(
        mapping=mapping, discovery=discovery, test_monitor=test_monitor.result()
    )
