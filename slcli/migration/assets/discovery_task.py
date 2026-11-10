"""Persisted Prefect task for Asset Service discovery."""

from prefect import task
from prefect.cache_policies import INPUTS

from slcli.migration.assets.client import AssetClient
from slcli.migration.assets.discovery import discover_assets, source_system_workspaces
from slcli.migration.assets.models import AssetDiscovery
from slcli.migration.connection import resolve_migration_connection
from slcli.migration.system_client import SystemClient
from slcli.migration.workspaces import WorkspaceMapping


@task(
    name="discover-assets",
    persist_result=True,
    result_serializer="json",
    cache_result_in_memory=False,
    cache_policy=INPUTS,
)
def discover_assets_task(
    migration_id: str,
    source_profile: str,
    destination_profile: str,
    workspace_mapping: WorkspaceMapping,
) -> AssetDiscovery:
    """Discover source assets and validate destination system dependencies.

    Inputs are references, never credentials. ``migration_id`` is unused by the
    body but scopes the cache key to one migration. File migration does not yet
    provide a durable source-to-destination file map, so linked assets remain
    blocked until that map is available.
    """
    source = resolve_migration_connection(source_profile)
    destination = resolve_migration_connection(destination_profile)
    source_systems = SystemClient(source).query_systems()
    destination_minion_ids = {system.id for system in SystemClient(destination).query_systems()}
    return discover_assets(
        AssetClient(source).query_assets(),
        source_system_workspaces(
            source_systems,
            {
                workspace.source_id: workspace.source_name
                for workspace in workspace_mapping.workspaces
            },
        ),
        destination_minion_ids,
        destination_file_ids=(),
        workspace_mappings={
            workspace.source_name: workspace.destination_name
            for workspace in workspace_mapping.workspaces
        },
    )
