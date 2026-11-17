"""Prefect task for repairing migrated result file references."""

from prefect import task
from prefect.cache_policies import INPUTS, TASK_SOURCE

from slcli.migration.connection import resolve_migration_connection
from slcli.migration.files.models import FileTransfer
from slcli.migration.testmonitor.client import TestMonitorClient
from slcli.migration.testmonitor.file_references import (
    FileReferenceRepair,
    complete_results,
    repair_file_references,
    unresolved_references,
)
from slcli.migration.testmonitor.models import TestMonitorMigration
from slcli.migration.testmonitor.writer import TestMonitorWriter


@task(
    name="repair-result-file-references",
    persist_result=True,
    result_serializer="json",
    cache_result_in_memory=False,
    cache_policy=TASK_SOURCE + INPUTS,
)
def repair_file_references_task(
    migration_id: str,
    source_profile: str,
    destination_profile: str,
    transfer: FileTransfer,
    migration: TestMonitorMigration,
) -> FileReferenceRepair:
    """Repair references, then mark results complete after both migrations succeed.

    ``migration_id`` scopes the cache to one migration; inputs contain no credentials.
    """
    has_affected_results = any(
        result_ids
        for batch in migration.results
        for file_id, result_ids in batch.file_results.items()
        if file_id in transfer.reassigned_ids
    )
    has_successful_results = any(batch.migrated for batch in migration.results)
    if not has_affected_results and not has_successful_results:
        return FileReferenceRepair(unresolved=unresolved_references(migration))
    destination_connection = resolve_migration_connection(destination_profile)
    if destination_connection.readonly:
        raise ValueError(f"Profile '{destination_profile}' is in readonly mode")
    writer = TestMonitorWriter(destination_connection)
    repaired = repair_file_references(
        TestMonitorClient(destination_connection),
        writer,
        transfer,
        migration,
    )
    complete_results(writer, migration)
    return repaired
