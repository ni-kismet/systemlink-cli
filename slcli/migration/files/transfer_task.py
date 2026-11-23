"""Persisted Prefect tasks that transfer files to the destination in batches."""

from typing import Dict, List, Tuple

import click
from prefect import task
from prefect.cache_policies import INPUTS

from slcli.migration.connection import resolve_migration_connection
from slcli.migration.files.client import FilesClient
from slcli.migration.files.models import (
    DiscoveredFile,
    FileDiscovery,
    FileFailure,
    FileTransfer,
)
from slcli.migration.files.transfer import split_into_batches, transfer_batch
from slcli.migration.flows.batching import shared_task_args
from slcli.migration.flows.service import service_task
from slcli.migration.workspaces import WorkspaceMapping


class BatchTransferError(click.ClickException):
    """A batch in which some files failed; carries only those files."""

    def __init__(self, batch: int, failures: Tuple[FileFailure, ...]) -> None:
        """Record the failed files of one batch.

        Args:
            batch: Index of the batch that failed.
            failures: Files in the batch that did not transfer.
        """
        super().__init__(f"Batch {batch} had {len(failures)} failed file(s).")
        self.failures = failures


# A batch with failed files raises, so it is not cached and a resumed run retries
# its files. A batch that completes is cached and is not transferred again.
@task(
    name="transfer-file-batch",
    task_run_name="files-{batch}",
    persist_result=True,
    result_serializer="json",
    cache_result_in_memory=False,
    cache_policy=INPUTS,
)
def transfer_file_batch_task(
    migration_id: str,
    source_profile: str,
    destination_profile: str,
    mapping: WorkspaceMapping,
    batch: int,
    files: List[DiscoveredFile],
    source_to_destination_id_map: Dict[str, str],
) -> FileTransfer:
    """Transfer one batch of files, possibly from several source workspaces.

    Inputs are references, never credentials. ``migration_id`` scopes the cache key
    to one migration.

    Raises:
        BatchTransferError: If any file in the batch failed to transfer.
    """
    source = FilesClient(resolve_migration_connection(source_profile))
    destination = FilesClient(resolve_migration_connection(destination_profile))
    transfer = transfer_batch(source, destination, files, source_to_destination_id_map, mapping)
    if transfer.failures:
        raise BatchTransferError(batch, transfer.failures)
    return transfer


@service_task("transfer-files")
def transfer_files_task(
    migration_id: str,
    source_profile: str,
    destination_profile: str,
    files: FileDiscovery,
    mapping: WorkspaceMapping,
) -> FileTransfer:
    """Transfer files in batches, skipping files already present on the destination.

    Every batch runs even when another batch fails. Failed files are reported after
    all batches finish, so a resumed run retries only them.

    Args:
        migration_id: Migration that scopes task cache keys.
        source_profile: Name of the source profile.
        destination_profile: Name of the destination profile.
        files: Discovered files and their pre-allocated destination IDs.
        mapping: Resolved source-to-destination workspaces.

    Raises:
       ValueError: If the destination is readonly.
       click.ClickException: If any file failed to transfer.
    """
    destination = resolve_migration_connection(destination_profile)
    if files.files and destination.readonly:
        raise ValueError(
            f"Cannot transfer files: profile '{destination.profile_name}' is in readonly mode"
        )
    batches = split_into_batches(files)
    if not batches:
        return FileTransfer()

    common = shared_task_args(migration_id, source_profile, destination_profile, mapping)
    intended_ids = [
        {file.id: files.source_to_destination_id_map[file.id] for file in batch}
        for batch in batches
    ]
    futures = transfer_file_batch_task.map(
        *common,
        list(range(len(batches))),
        batches,
        intended_ids,
    )
    transferred = 0
    already_present = 0
    failures: List[FileFailure] = []
    for batch, future in zip(batches, futures):
        future.wait()
        if future.state.is_completed():
            outcome = future.result()
            transferred += outcome.transferred
            already_present += outcome.already_present
            continue
        error = future.state.result(raise_on_failure=False)
        if isinstance(error, BatchTransferError):
            failures.extend(error.failures)
            continue
        error_type = type(error).__name__ if isinstance(error, BaseException) else "Failed"
        failures.extend(
            FileFailure(id=file.id, workspace=file.workspace, error_type=error_type)
            for file in batch
        )
    if failures:
        raise click.ClickException(
            f"{len(failures)} of {len(files.files)} files failed to transfer. "
            f"Resume with --migration-id {migration_id} to retry them."
        )
    return FileTransfer(transferred=transferred, already_present=already_present)
