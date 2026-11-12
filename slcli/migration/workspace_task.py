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
    migration_id: str, source_profile: str, explicit_workspace_selection: Optional[List[str]]
) -> DiscoveredWorkspaces:
    """Discover the source workspaces in scope of a migration.

    ``migration_id`` is unused by the body but scopes the cache key to one migration.
    ``explicit_workspace_selection`` optionally contains a specific set of workspaces to find.
    If not given, all workspaces are discovered and returned.

    Raises:
        WorkspaceMappingError: If a requested source workspace does not exist.
    """
    source_workspace_iterator = WorkspaceClient(
        resolve_migration_connection(source_profile)
    ).query_workspaces()
    return discover_workspaces(source_workspace_iterator, explicit_workspace_selection)


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
    source_workspaces: DiscoveredWorkspaces,
    workspace_mappings: Optional[Dict[str, str]],
) -> WorkspaceMapping:
    """Map source workspaces to existing destination workspaces, or create if missing.

    ``migration_id`` is unused by the body but scopes the cache key to one migration.

    Raises:
        WorkspaceMappingError: If a mapped destination workspace is disabled.
    """
    destination_client = WorkspaceClient(resolve_migration_connection(destination_profile))
    return synchronize_workspaces(
        source_workspaces,
        destination_client.query_workspaces(),
        destination_client.create_workspace,
        workspace_mappings,
    )
