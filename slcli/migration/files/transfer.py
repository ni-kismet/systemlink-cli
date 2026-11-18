"""Transfer discovered files to their mapped destination workspaces."""

import logging
import secrets
from contextlib import AbstractContextManager
from typing import Any, Dict, Iterable, List, Mapping, Protocol, Set

from slcli.migration.files.client import FileContent, SourceFile
from slcli.migration.files.models import (
    DiscoveredFile,
    FileDiscovery,
    FileFailure,
    FileTransfer,
)
from slcli.migration.workspaces import WorkspaceMapping

_logger = logging.getLogger(__name__)
MIGRATED_SOURCE_ID = "MigratedSourceId"
UPLOAD_ATTEMPTS = 2


class FileSource(Protocol):
    """Downloads required by file transfer."""

    def download_file(self, file_id: str) -> AbstractContextManager[FileContent]:
        """Stream one source file."""
        ...


class FileDestination(Protocol):
    """Queries and uploads required by file transfer."""

    def query_files(self, workspace_id: str) -> Iterable[SourceFile]:
        """Return every file in one destination workspace."""
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


def transfer_files(
    source: FileSource,
    destination: FileDestination,
    discovery: FileDiscovery,
    mapping: WorkspaceMapping,
) -> FileTransfer:
    """Upload each discovered file to its mapped destination workspace under its mapped ID.

    Destination files are identified by their ``MigratedSourceId`` property within
    the mapped workspace. Occupied IDs belonging to other files are replaced with
    random IDs. Actual IDs differing from the intended IDs are recorded in
    ``reassigned_ids``, including files recovered after an interrupted run.
    Source annotations are indexed once per workspace for constant-time lookups.

    A failed upload is retried once. A file that still fails is logged and recorded
    without stopping the others.

    Args:
        source: Downloads from the source server.
        destination: Queries and uploads on the destination server.
        discovery: Discovered source files and their pre-allocated destination IDs.
        mapping: Source to destination workspaces.
    """
    destination_workspace_ids = {
        workspace.source_name: workspace.destination_id for workspace in mapping.workspaces
    }
    # A replacement must not take the intended ID of another file.
    reserved_ids: Set[str] = set(discovery.source_to_destination_id_map.values())
    files_by_workspace: Dict[str, Dict[str, SourceFile]] = {}
    migrated_by_workspace: Dict[str, Dict[str, List[SourceFile]]] = {}
    transferred = 0
    already_present = 0
    reassigned_ids: Dict[str, str] = {}
    failures: List[FileFailure] = []
    for file in discovery.files:
        intended_id = discovery.source_to_destination_id_map[file.id]
        workspace_id = destination_workspace_ids[file.workspace]
        try:
            if workspace_id not in files_by_workspace:
                files_by_workspace[workspace_id] = {
                    existing.id: existing for existing in destination.query_files(workspace_id)
                }
                migrated_by_workspace[workspace_id] = _index_migrated_files(
                    files_by_workspace[workspace_id].values()
                )
            existing_files = files_by_workspace[workspace_id]
            migrated_files = migrated_by_workspace[workspace_id]
            filename = file.name or file.id

            migrated = _find_migrated_file(file.id, migrated_files)
            if migrated is not None:
                actual_id = migrated.id
                already_present += 1
            else:
                requested_id = _choose_id(intended_id, existing_files, reserved_ids)
                actual_id = _upload_with_retry(
                    source,
                    destination,
                    file,
                    requested_id,
                    workspace_id,
                    filename,
                    reserved_ids,
                )
                existing_files[actual_id] = SourceFile(
                    id=actual_id,
                    properties={**file.properties, MIGRATED_SOURCE_ID: file.id},
                )
                migrated_files[file.id] = [existing_files[actual_id]]
                reserved_ids.add(actual_id)
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
            continue

        if actual_id != intended_id:
            _logger.info("File %s was reassigned from %s to %s", file.id, intended_id, actual_id)
            reassigned_ids[intended_id] = actual_id
    return FileTransfer(
        transferred=transferred,
        already_present=already_present,
        reassigned_ids=reassigned_ids,
        failures=tuple(failures),
    )


def _choose_id(
    intended_id: str,
    existing_files: Mapping[str, SourceFile],
    reserved_ids: Set[str],
) -> str:
    """Choose an unused ID without taking another file's pre-allocated ID."""
    candidate = intended_id
    while candidate in existing_files or (candidate != intended_id and candidate in reserved_ids):
        candidate = secrets.token_hex(12)
    reserved_ids.add(candidate)
    return candidate


def _index_migrated_files(files: Iterable[SourceFile]) -> Dict[str, List[SourceFile]]:
    """Index source annotations once, retaining duplicates for ambiguity checks."""
    indexed: Dict[str, List[SourceFile]] = {}
    for file in files:
        source_id = file.properties.get(MIGRATED_SOURCE_ID)
        if isinstance(source_id, str):
            indexed.setdefault(source_id, []).append(file)
    return indexed


def _find_migrated_file(
    source_id: str, indexed: Mapping[str, List[SourceFile]]
) -> SourceFile | None:
    """Find an annotated file, rejecting ambiguous duplicate annotations."""
    matches = indexed.get(source_id, [])
    if len(matches) > 1:
        raise ValueError(f"Multiple destination files have {MIGRATED_SOURCE_ID}={source_id}")
    return matches[0] if matches else None


def _upload_with_retry(
    source: FileSource,
    destination: FileDestination,
    file: DiscoveredFile,
    requested_id: str,
    workspace_id: str,
    filename: str,
    reserved_ids: Set[str],
) -> str:
    """Retry once with a fresh download, reconciling a potentially lost response first."""
    upload_attempted = False
    for attempt in range(1, UPLOAD_ATTEMPTS + 1):
        if attempt > 1 and upload_attempted:
            existing = {item.id: item for item in destination.query_files(workspace_id)}
            migrated = _find_migrated_file(file.id, _index_migrated_files(existing.values()))
            if migrated is not None:
                return migrated.id
            requested_id = _choose_id(requested_id, existing, reserved_ids)
        try:
            with source.download_file(file.id) as content:
                upload_attempted = True
                return destination.upload_file(
                    requested_id,
                    workspace_id,
                    filename,
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
