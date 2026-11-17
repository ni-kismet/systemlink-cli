"""Persisted Prefect task for transferring files to the destination."""

import click
from prefect import task
from prefect.cache_policies import INPUTS, TASK_SOURCE

from slcli.migration.connection import resolve_migration_connection
from slcli.migration.files.client import FilesClient
from slcli.migration.files.models import FileDiscovery, FileTransfer
from slcli.migration.files.transfer import transfer_files
from slcli.migration.workspaces import WorkspaceMapping


# A transfer with failed files raises, so it is not cached and a resumed run retries
# only files whose MigratedSourceId annotation is not present on the destination.
@task(
    name="transfer-files",
    persist_result=True,
    result_serializer="json",
    cache_result_in_memory=False,
    cache_policy=TASK_SOURCE + INPUTS,
)
def transfer_files_task(
    migration_id: str,
    source_profile: str,
    destination_profile: str,
    files: FileDiscovery,
    mapping: WorkspaceMapping,
) -> FileTransfer:
    """Transfer files, recovering prior uploads by their MigratedSourceId annotation.

    Inputs are references, never credentials. ``migration_id`` scopes the cache key
    to one migration.

    Raises:
        click.ClickException: If the destination is readonly or any file failed to transfer.
    """
    destination = resolve_migration_connection(destination_profile)
    if files.files and destination.readonly:
        raise click.ClickException(
            f"Cannot transfer files: profile '{destination.profile_name}' is in readonly mode"
        )
    transfer = transfer_files(
        FilesClient(resolve_migration_connection(source_profile)),
        FilesClient(destination),
        files,
        mapping,
    )
    if transfer.failures:
        raise click.ClickException(
            f"{len(transfer.failures)} of {len(files.files)} files failed to transfer. "
            f"Resume with --migration-id {migration_id} to retry them."
        )
    return transfer
