"""Persisted Prefect task for SLS file discovery."""

from prefect import task
from prefect.cache_policies import INPUTS, TASK_SOURCE

from slcli.migration.connection import resolve_migration_connection
from slcli.migration.files.client import FilesClient
from slcli.migration.files.discovery import discover_files
from slcli.migration.files.models import FileDiscovery
from slcli.migration.workspaces import DiscoveredWorkspaces


@task(
    name="discover-files",
    persist_result=True,
    result_serializer="json",
    cache_result_in_memory=False,
    cache_policy=TASK_SOURCE + INPUTS,
)
def discover_files_task(
    migration_id: str,
    source_profile: str,
    workspaces: DiscoveredWorkspaces,
) -> FileDiscovery:
    """Discover SLS files in the discovered source workspaces.

    Inputs are references, never credentials. ``migration_id`` is unused by the
    body but scopes the cache key to one migration.
    """
    connection = resolve_migration_connection(source_profile)
    return discover_files(
        FilesClient(connection),
        workspaces,
    )
