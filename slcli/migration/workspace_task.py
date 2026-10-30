"""Persisted Prefect tasks for migration workspaces."""

from typing import Dict, List, Optional

from prefect import task
from prefect.cache_policies import INPUTS

from slcli.migration.connection import resolve_migration_connection
from slcli.migration.workspace_client import WorkspaceClient
from slcli.migration.workspaces import (
    DiscoveredWorkspaces,
    WorkspaceMapping,
    discover_workspaces,
    synchronize_workspaces,
)


@task(
    name="discover-workspaces",
    persist_result=True,
    result_serializer="json",
    cache_result_in_memory=False,
    cache_policy=INPUTS,
)
def discover_workspaces_task(
    migration_id: str, source_profile: str, workspaces: Optional[List[str]]
) -> DiscoveredWorkspaces:
    """Discover the source workspaces in scope of a migration.

    ``migration_id`` is unused by the body but scopes the cache key to one migration.

    Raises:
        WorkspaceMappingError: If a requested workspace does not exist on the source.
    """
    source = WorkspaceClient(resolve_migration_connection(source_profile)).query_workspaces()
    return discover_workspaces(source, workspaces)


# Later migration tasks are cached by the mapping, so a resumed run must reuse
# the mapping it synchronized first. A synchronization that raised is not cached.
@task(
    name="synchronize-workspaces",
    persist_result=True,
    result_serializer="json",
    cache_result_in_memory=False,
    cache_policy=INPUTS,
)
def synchronize_workspaces_task(
    migration_id: str,
    destination_profile: str,
    discovered: DiscoveredWorkspaces,
    workspace_mappings: Optional[Dict[str, str]],
) -> WorkspaceMapping:
    """Map discovered source workspaces to destination workspaces.

    ``migration_id`` is unused by the body but scopes the cache key to one migration.

    Raises:
        WorkspaceMappingError: If a destination workspace does not exist.
    """
    # TODO(AB#4088608): Create missing destination workspaces.
    destination = WorkspaceClient(
        resolve_migration_connection(destination_profile)
    ).query_workspaces()
    return synchronize_workspaces(discovered, destination, workspace_mappings)
