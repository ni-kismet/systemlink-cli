"""File discovery and workspace assignment policy."""

import logging
import secrets
from collections import Counter
from typing import Dict, Iterable, List, Protocol, Set

from slcli.migration.files.client import SourceFile
from slcli.migration.files.models import DiscoveredFile, FileDiscovery
from slcli.migration.testmonitor.models import WorkspaceFailure
from slcli.migration.workspaces import DiscoveredWorkspaces

_logger = logging.getLogger(__name__)
_OBJECT_ID_BYTES = 12


class FilesQuery(Protocol):
    """Queries required by file discovery."""

    def query_files(self, workspace_id: str) -> Iterable[SourceFile]:
        """Return every file in one workspace."""
        ...


def discover_files(
    client: FilesQuery,
    workspaces: DiscoveredWorkspaces,
) -> FileDiscovery:
    """Discover files in the selected workspaces.

    A workspace that fails discovery is logged and contributes no files.

    Args:
        client: File queries for the source server.
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
        file_id_map=_generate_file_id_mappings(file.id for file in files),
        failures=tuple(sorted(failures, key=lambda item: item.workspace)),
    )


def _throw_if_duplicate_ids(file_ids: Iterable[DiscoveredFile]) -> None:
    counts = Counter(file.id for file in file_ids)
    duplicates = [fid for fid, count in counts.items() if count > 1]
    if duplicates:
        raise ValueError(f"Duplicate SLS file IDs found: {', '.join(duplicates)}")


def _generate_file_id_mappings(source_ids: Iterable[str]) -> Dict[str, str]:
    """Map each SLS file ID to a new, unique ID suitable for the destination file ingestion service.

    Generated IDs are unique, 24-character hex strings (Mongo ObjectIds are 12-byte BSON).
    """
    taken: Set[str] = set(source_ids)
    mapping: Dict[str, str] = {}
    for source_id in sorted(taken):
        new_id = secrets.token_hex(_OBJECT_ID_BYTES)
        while new_id in taken:
            new_id = secrets.token_hex(_OBJECT_ID_BYTES)
        taken.add(new_id)
        mapping[source_id] = new_id
    return mapping
