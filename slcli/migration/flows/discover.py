"""Discovery-only migration flow."""

from typing import List, Optional

from prefect import flow
from pydantic import ConfigDict

from slcli.migration.schema import VersionedModel
from slcli.migration.testmonitor.discovery_task import discover_test_monitor_task
from slcli.migration.testmonitor.models import TestMonitorDiscovery


class MigrationDiscovery(VersionedModel):
    """Discovery results for every supported resource type."""

    model_config = ConfigDict(frozen=True)

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
    """Run one persisted discovery task per supported resource type.

    Args:
        migration_id: Migration that scopes task cache keys.
        source_profile: Name of the source profile.
        workspaces: Source workspace names to discover; all workspaces when None.
    """
    return MigrationDiscovery(
        test_monitor=discover_test_monitor_task(migration_id, source_profile, workspaces)
    )
