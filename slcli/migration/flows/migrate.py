"""Migration flow: discover, then synchronize workspaces."""

from typing import Dict, List, Optional

from prefect import flow
from pydantic import ConfigDict

from slcli.migration.flows.discover import MigrationDiscovery, discover_flow
from slcli.migration.schema import VersionedModel
from slcli.migration.workspace_task import synchronize_workspaces_task
from slcli.migration.workspaces import WorkspaceMapping


class MigrationOutcome(VersionedModel):
    """Discovery and workspace mapping of one run."""

    model_config = ConfigDict(frozen=True)

    discovery: MigrationDiscovery
    mapping: WorkspaceMapping


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
    workspace_mappings: Optional[Dict[str, str]],
) -> MigrationOutcome:
    """Discover source resources, then synchronize workspaces to the destination.

    Args:
        migration_id: Migration that scopes task cache keys.
        source_profile: Name of the source profile.
        destination_profile: Name of the destination profile.
        workspace_mappings: Source to destination workspace names; all by name when None.

    Raises:
        WorkspaceMappingError: If a source or destination workspace does not exist.
    """
    workspaces: Optional[List[str]] = (
        list(workspace_mappings) if workspace_mappings is not None else None
    )
    discovery = discover_flow(migration_id, source_profile, workspaces)
    mapping = synchronize_workspaces_task(
        migration_id, destination_profile, discovery.workspaces, workspace_mappings
    )
    return MigrationOutcome(discovery=discovery, mapping=mapping)
