"""Persisted Prefect task for SLS file discovery."""

import click
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
    destination_profile: str,
    workspaces: DiscoveredWorkspaces,
) -> FileDiscovery:
    """Discover SLS files in the discovered source workspaces.

    Inputs are references, never credentials. ``migration_id`` is unused by the
    body but scopes the cache key to one migration. Partial discovery raises
    rather than caching an incomplete file map. Planned destination IDs are checked
    against ``destination_profile`` so none is already in use there.
    """
    discovery = discover_files(
        FilesClient(resolve_migration_connection(source_profile)),
        FilesClient(resolve_migration_connection(destination_profile)),
        workspaces,
    )
    if discovery.failures:
        failed_workspaces = ", ".join(failure.workspace for failure in discovery.failures)
        raise click.ClickException(
            f"File discovery failed for workspace(s): {failed_workspaces}. "
            "Retry the migration before results are created."
        )
    return discovery
