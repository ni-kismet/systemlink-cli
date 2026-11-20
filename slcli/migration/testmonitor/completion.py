"""Mark migrated test results complete once every migration step has succeeded."""

from datetime import datetime, timezone
from typing import List, Sequence

from slcli.migration.annotations import COMPLETE, COMPLETED_AT, STATUS
from slcli.migration.testmonitor.models import TestMonitorMigration
from slcli.migration.testmonitor.writer import DestinationWriter, Record

_CHUNK_SIZE = 100


def _update_results(writer: DestinationWriter, updates: Sequence[Record], *, replace: bool) -> None:
    response = writer.update_results(updates, replace=replace)
    expected = {record["id"] for record in updates}
    returned = {record.get("id") for record in response.created}
    if response.failed or response.error or not expected.issubset(returned):
        raise ValueError(f"Failed to update results: {', '.join(sorted(expected))}")


def complete_results(writer: DestinationWriter, migration: TestMonitorMigration) -> None:
    """Mark migrated results COMPLETE.

    Partial result migrations remain incomplete. Updates merge only completion
    properties, preserving unresolved-file annotations and all other fields.

    Raises:
        ValueError: If any completion update is rejected or not acknowledged.
    """
    result_ids = [item.destination_id for batch in migration.results for item in batch.migrated]
    for offset in range(0, len(result_ids), _CHUNK_SIZE):
        completed_at = datetime.now(timezone.utc).isoformat()
        updates: List[Record] = [
            {"id": result_id, "properties": {STATUS: COMPLETE, COMPLETED_AT: completed_at}}
            for result_id in result_ids[offset : offset + _CHUNK_SIZE]
        ]
        _update_results(writer, updates, replace=False)
