"""Discovery-only migration flow."""

from typing import List, Optional

from prefect import flow
from pydantic import ConfigDict

from slcli.migration.schema import VersionedModel
from slcli.migration.testmonitor.discovery_task import discover_test_monitor_task
from slcli.migration.testmonitor.models import TestMonitorDiscovery
from slcli.migration.workspace_task import discover_workspaces_task
from slcli.migration.workspaces import DiscoveredWorkspaces


class MigrationDiscovery(VersionedModel):
    """Discovery results for every supported resource type."""

    model_config = ConfigDict(frozen=True)

    workspaces: DiscoveredWorkspaces
    test_monitor: TestMonitorDiscovery


@flow(
    name="systemlink-migration-discovery",
    flow_run_name="migration-discovery-{migration_id}",
    persist_result=True,
    result_serializer="json",
)
def discover_flow(
    migration_id: str,
    source_profile: str,
    workspaces: Optional[List[str]],
) -> MigrationDiscovery:
    """Discover source workspaces, then each supported resource type within them.

    Args:
        migration_id: Migration that scopes task cache keys.
        source_profile: Name of the source profile.
        workspaces: Source workspace names to discover; all workspaces when None.

    Raises:
        WorkspaceMappingError: If a requested workspace does not exist on the source.
    """
    discovered = discover_workspaces_task(migration_id, source_profile, workspaces)
    return MigrationDiscovery(
        workspaces=discovered,
        test_monitor=discover_test_monitor_task(migration_id, source_profile, discovered),
    )
