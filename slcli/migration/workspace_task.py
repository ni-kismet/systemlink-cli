"""Persisted Prefect task that resolves the run's workspace mapping."""

from typing import Dict, Optional

from prefect import task
from prefect.cache_policies import INPUTS

from slcli.migration.connection import resolve_migration_connection
from slcli.migration.workspace_client import WorkspaceClient
from slcli.migration.workspaces import WorkspaceMapping, map_workspaces


# Batch task cache keys include the mapping, so a resumed run must reuse the
# mapping it resolved first: re-resolving could pick up a newly created workspace
# and re-migrate completed batches. A resolution that raised is not cached.
@task(
    name="resolve-workspaces",
    persist_result=True,
    result_serializer="json",
    cache_result_in_memory=False,
    cache_policy=INPUTS,
)
def resolve_workspaces_task(
    migration_id: str,
    source_profile: str,
    destination_profile: str,
    workspace_mappings: Optional[Dict[str, str]],
) -> WorkspaceMapping:
    """Map source workspaces to existing destination workspaces.

    ``migration_id`` is unused by the body but scopes the cache key to one migration.

    Raises:
        WorkspaceMappingError: If a requested workspace is missing on either side.
    """
    source = WorkspaceClient(resolve_migration_connection(source_profile)).query_workspaces()
    destination = WorkspaceClient(
        resolve_migration_connection(destination_profile)
    ).query_workspaces()
    return map_workspaces(source, destination, workspace_mappings)
