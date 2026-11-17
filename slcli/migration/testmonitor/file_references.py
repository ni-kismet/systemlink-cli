"""Restore migrated test result file references after file transfer."""

from typing import Dict, Iterable, List, Mapping, Protocol, Sequence, Tuple

from pydantic import BaseModel, ConfigDict

from slcli.migration.files.models import FileTransfer
from slcli.migration.schema import VersionedModel
from slcli.migration.testmonitor.models import (
    BatchResult,
    FailedItem,
    MigratedItem,
    TestMonitorMigration,
)
from slcli.migration.testmonitor.writer import DestinationWriter, Record

_CHUNK_SIZE = 100


class UnresolvedFileReferences(BaseModel):
    """Source file IDs that could not be resolved for one migrated result."""

    model_config = ConfigDict(frozen=True)

    source_result_id: str
    destination_result_id: str
    file_ids: Tuple[str, ...]


class FileReferenceRepair(VersionedModel):
    """Outcome of attaching migrated files to migrated results."""

    model_config = ConfigDict(frozen=True)

    updated: int = 0
    unresolved: Tuple[UnresolvedFileReferences, ...] = ()


class ResultQueries(Protocol):
    """Queries needed to fetch source and destination result records."""

    def query_records(
        self, collection: str, filter_expr: str, substitutions: Sequence[object]
    ) -> Iterable[Record]:
        """Return full result records."""
        ...


def _records_by_id(client: ResultQueries, ids: Sequence[str]) -> Dict[str, Record]:
    records: Dict[str, Record] = {}
    expected = set(ids)
    query = " || ".join(f"id == @{i}" for i in range(len(ids)))
    for record in client.query_records("results", query, list(ids)):
        record_id = record.get("id")
        if not isinstance(record_id, str) or record_id not in expected or record_id in records:
            raise ValueError(f"Invalid or duplicate result ID: {record_id!r}")
        records[record_id] = record
    missing = set(ids) - records.keys()
    if missing:
        raise ValueError(
            f"Results not found during file reference repair: {', '.join(sorted(missing))}"
        )
    return records


def _affected_results(
    migration: TestMonitorMigration, reassignments: Mapping[str, str]
) -> Dict[str, List[str]]:
    affected = {
        result_id
        for batch in migration.results
        for file_id in batch.file_results.keys() & reassignments.keys()
        for result_id in batch.file_results[file_id]
    }
    original_ids: Dict[str, List[str]] = {}
    for batch in migration.results:
        for file_id, result_ids in batch.file_results.items():
            for result_id in result_ids:
                if result_id in affected:
                    original_ids.setdefault(result_id, []).append(file_id)
    return original_ids


def _file_ids(record: Record) -> List[str]:
    value = record.get("fileIds", [])
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise ValueError(f"Invalid fileIds on result {record.get('id')!r}")
    return list(value)


def _result_items(batch: BatchResult) -> Iterable[MigratedItem | FailedItem]:
    yield from batch.migrated
    yield from batch.failed


def unresolved_references(migration: TestMonitorMigration) -> Tuple[UnresolvedFileReferences, ...]:
    """Return unresolved IDs recorded when result migration created each result."""
    return tuple(
        UnresolvedFileReferences(
            source_result_id=item.source_id,
            destination_result_id=item.destination_id,
            file_ids=item.unresolved_file_ids,
        )
        for batch in migration.results
        for item in _result_items(batch)
        if item.unresolved_file_ids and item.destination_id is not None
    )


def repair_file_references(
    destination: ResultQueries,
    writer: DestinationWriter,
    transfer: FileTransfer,
    migration: TestMonitorMigration,
) -> FileReferenceRepair:
    """Repair only indexed results referencing reassigned intended file IDs.

    Final IDs are derived from original associations, not current IDs, so
    overlapping reassignments and interrupted repairs are safe to resume.
    Unrelated destination attachments are preserved. Reads and writes are batched.

    Raises:
        ValueError: If a result is missing or malformed, or an update is rejected.
    """
    unresolved = unresolved_references(migration)
    if not transfer.reassigned_ids:
        return FileReferenceRepair(unresolved=unresolved)
    original_ids = _affected_results(migration, transfer.reassigned_ids)
    result_ids = list(original_ids)
    updated = 0
    for offset in range(0, len(result_ids), _CHUNK_SIZE):
        chunk = result_ids[offset : offset + _CHUNK_SIZE]
        records = _records_by_id(destination, chunk)
        updates: List[Record] = []
        for result_id in chunk:
            existing_ids = _file_ids(records[result_id])
            intended = set(original_ids[result_id])
            final_ids = [
                transfer.reassigned_ids.get(file_id, file_id) for file_id in original_ids[result_id]
            ]
            corrected = list(
                dict.fromkeys([*final_ids, *(fid for fid in existing_ids if fid not in intended)])
            )
            if set(corrected) != set(existing_ids):
                updates.append({"id": result_id, "fileIds": corrected})
        if not updates:
            continue
        response = writer.update_results(updates, replace=True)
        expected = {record["id"] for record in updates}
        returned = {record.get("id") for record in response.created}
        if response.failed or response.error or not expected.issubset(returned):
            raise ValueError(
                f"Failed to update file references for results: {', '.join(sorted(expected))}"
            )
        updated += len(updates)
    return FileReferenceRepair(updated=updated, unresolved=unresolved)
