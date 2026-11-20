"""Transfer discovered files to their mapped destination workspaces in batches."""

import logging
from contextlib import AbstractContextManager
from typing import Any, List, Mapping, Protocol, Sequence, Set

from slcli.migration.files.client import FileContent
from slcli.migration.files.models import DiscoveredFile, FileDiscovery, FileFailure, FileTransfer
from slcli.migration.flows.batching import partition_by_weight
from slcli.migration.workspaces import WorkspaceMapping

_logger = logging.getLogger(__name__)
MIGRATED_SOURCE_ID = "MigratedSourceId"
UPLOAD_ATTEMPTS = 2
DEFAULT_FILE_BATCH_BYTES = 256 * 1024 * 1024  # 256 MB


class FileSource(Protocol):
    """Downloads required by file transfer."""

    def download_file(self, file_id: str) -> AbstractContextManager[FileContent]:
        """Stream one source file."""
        ...


class FileDestination(Protocol):
    """ID lookups and uploads required by file transfer."""

    def query_existing_ids(self, ids: Sequence[str]) -> Set[str]:
        """Return which of the given file IDs exist on the server."""
        ...

    def upload_file(
        self,
        file_id: str,
        workspace_id: str,
        filename: str,
        properties: Mapping[str, Any],
        content: FileContent,
    ) -> str:
        """Upload one file requesting an ID, and return the ID the server assigned."""
        ...


def split_into_batches(
    discovery: FileDiscovery,
    max_bytes: int = DEFAULT_FILE_BATCH_BYTES,
) -> List[List[DiscoveredFile]]:
    """Split files into batches of at most ``max_bytes``.

    A file larger than ``max_bytes`` forms a batch of its own.
    """
    return partition_by_weight(
        discovery.files,
        max_bytes,
        lambda file: file.size_bytes or 0,
    )


def transfer_batch(
    source: FileSource,
    destination: FileDestination,
    batch: Sequence[DiscoveredFile],
    source_to_destination_id_map: Mapping[str, str],
    workspace_mapping: WorkspaceMapping,
) -> FileTransfer:
    """Upload one batch of files, each to the workspace mapped from its source workspace.

    All target IDs are looked up in one batched query. Files whose ID exists are skipped.
    The rest are uploaded under their allocated IDs.
    A failed upload is retried once. A file that still fails is recorded without
    stopping the others.

    Args:
        source: Downloads from the source server.
        destination: ID lookups and uploads on the destination server.
        batch: Files to transfer.
        source_to_destination_id_map: Pre-allocated destination IDs keyed by source file ID.
        workspace_mapping: Maps each file's source workspace to its destination workspace.
    """
    existing = destination.query_existing_ids(
        [source_to_destination_id_map[file.id] for file in batch]
    )
    transferred = 0
    already_present = 0
    failures: List[FileFailure] = []
    for file in batch:
        file_id = source_to_destination_id_map[file.id]
        if file_id in existing:
            already_present += 1
            continue
        try:
            destination_workspace_id = workspace_mapping.workspace(file.workspace).destination_id
            actual_id = _upload_with_retry(
                source, destination, file, file_id, destination_workspace_id
            )
            if actual_id != file_id:
                raise ValueError(f"Server assigned {actual_id} instead of {file_id}")
            transferred += 1
            _logger.info("File %s transferred as %s", file.id, actual_id)
        except Exception as exc:
            _logger.warning(
                "File %s in workspace %s could not be transferred: %s: %s",
                file.id,
                file.workspace,
                type(exc).__name__,
                exc,
            )
            failures.append(
                FileFailure(id=file.id, workspace=file.workspace, error_type=type(exc).__name__)
            )
    return FileTransfer(
        transferred=transferred,
        already_present=already_present,
        failures=tuple(failures),
    )


def _upload_with_retry(
    source: FileSource,
    destination: FileDestination,
    file: DiscoveredFile,
    requested_id: str,
    workspace_id: str,
) -> str:
    """Retry once with a fresh download, reconciling a potentially lost response first."""
    upload_attempted = False
    for attempt in range(1, UPLOAD_ATTEMPTS + 1):
        if (
            attempt > 1
            and upload_attempted
            and requested_id in destination.query_existing_ids([requested_id])
        ):
            return requested_id
        try:
            with source.download_file(file.id) as content:
                upload_attempted = True
                return destination.upload_file(
                    requested_id,
                    workspace_id,
                    file.name or file.id,
                    {**file.properties, MIGRATED_SOURCE_ID: file.id},
                    content,
                )
        except Exception as exc:
            _logger.warning(
                "File %s in workspace %s failed to transfer (attempt %d of %d): %s: %s",
                file.id,
                file.workspace,
                attempt,
                UPLOAD_ATTEMPTS,
                type(exc).__name__,
                exc,
            )
            if attempt == UPLOAD_ATTEMPTS:
                raise
    raise AssertionError("unreachable")
