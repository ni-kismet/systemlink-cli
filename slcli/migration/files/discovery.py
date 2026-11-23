"""File discovery and workspace assignment policy."""

import logging
import secrets
from collections import Counter
from typing import Dict, Iterable, List, Protocol, Sequence, Set

from slcli.migration.files.client import SourceFile
from slcli.migration.files.models import DiscoveredFile, FileDiscovery
from slcli.migration.testmonitor.models import WorkspaceFailure
from slcli.migration.workspaces import DiscoveredWorkspaces

_logger = logging.getLogger(__name__)
_OBJECT_ID_BYTES = 12
_ID_CHECK_ATTEMPTS = 5


class FilesQuery(Protocol):
    """Queries required by file discovery."""

    def query_files(self, workspace_id: str) -> Iterable[SourceFile]:
        """Return every file in one workspace."""
        ...


class IdAvailabilityLookup(Protocol):
    """Destination lookup used to avoid generated IDs that are already in use."""

    def query_existing_ids(self, ids: Sequence[str]) -> Set[str]:
        """Return which of the given file IDs exist on the server."""
        ...


def discover_files(
    client: FilesQuery,
    destination: IdAvailabilityLookup,
    workspaces: DiscoveredWorkspaces,
) -> FileDiscovery:
    """Discover files in the selected workspaces and plan their destination IDs.

    A workspace that fails discovery is logged and contributes no files. Generated
    destination IDs are checked for existence on the destination so that no planned
    ID is already in use there.

    Args:
        client: File queries for the source server.
        destination: Lookups on the destination server for planned ID conflicts.
        workspaces: Discovered source workspaces.
    """
    sorted_selected = tuple(sorted(workspaces.selected))

    files: List[DiscoveredFile] = []
    failures: List[WorkspaceFailure] = []
    for workspace_name in sorted_selected:
        try:
            source_files = list(client.query_files(workspaces.source[workspace_name].id))
            files.extend(
                DiscoveredFile(
                    id=file.id,
                    workspace=workspace_name,
                    name=file.name,
                    size_bytes=file.size_bytes,
                    properties=file.properties,
                )
                for file in source_files
            )
        except Exception as exc:
            _logger.warning(
                "Workspace %s file discovery failed: %s: %s",
                workspace_name,
                type(exc).__name__,
                exc,
            )
            failures.append(
                WorkspaceFailure(workspace=workspace_name, error_type=type(exc).__name__)
            )
            continue

    _throw_if_duplicate_ids(files)
    return FileDiscovery(
        workspaces=sorted_selected,
        files=tuple(sorted(files, key=lambda item: (item.workspace, item.id))),
        source_to_destination_id_map=_generate_file_id_mappings(
            (file.id for file in files), destination
        ),
        failures=tuple(sorted(failures, key=lambda item: item.workspace)),
    )


def _throw_if_duplicate_ids(file_ids: Iterable[DiscoveredFile]) -> None:
    counts = Counter(file.id for file in file_ids)
    duplicates = [fid for fid, count in counts.items() if count > 1]
    if duplicates:
        raise ValueError(f"Duplicate SLS file IDs found: {', '.join(duplicates)}")


def _generate_file_id_mappings(
    source_ids: Iterable[str], destination: IdAvailabilityLookup
) -> Dict[str, str]:
    """Map each SLS file ID to a new, unique ID suitable for the destination file ingestion service.

    Generated IDs are unique, 24-character hex strings (Mongo ObjectIds are 12-byte BSON).
    Generated IDs that already exist on the destination are regenerated.
    """
    taken: Set[str] = set(source_ids)
    mapping: Dict[str, str] = {}
    for source_id in sorted(taken):
        mapping[source_id] = _new_id(taken)
    for _ in range(_ID_CHECK_ATTEMPTS):
        in_use = destination.query_existing_ids(list(mapping.values()))
        conflicts = [source_id for source_id, new_id in mapping.items() if new_id in in_use]
        if not conflicts:
            return mapping
        for source_id in conflicts:
            mapping[source_id] = _new_id(taken)
    raise ValueError("Could not generate destination file IDs that are unused on the destination")


def _new_id(taken: Set[str]) -> str:
    while True:
        new_id = secrets.token_hex(_OBJECT_ID_BYTES)
        # Since file IDs are 12 bytes rather than 16 (like typical GUIDs), collisions are
        # more likely. To be safe, we check for collisions and retry generation as needed.
        if new_id not in taken:
            break
    taken.add(new_id)
    return new_id
