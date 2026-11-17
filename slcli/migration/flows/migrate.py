"""Migration flow: discover, synchronize workspaces, then migrate each resource type."""

import logging
from typing import Dict, List, Optional

import click
from prefect import flow
from pydantic import ConfigDict

from slcli.migration.files.models import FileTransfer
from slcli.migration.files.transfer_task import transfer_files_task
from slcli.migration.flows.discover import MigrationDiscovery, discover_flow
from slcli.migration.flows.service import migration_task_runner
from slcli.migration.schema import VersionedModel
from slcli.migration.testmonitor.file_references import FileReferenceRepair
from slcli.migration.testmonitor.file_references_task import repair_file_references_task
from slcli.migration.testmonitor.migration_task import migrate_test_monitor_task
from slcli.migration.testmonitor.models import TestMonitorMigration
from slcli.migration.workspace_task import synchronize_workspaces_task
from slcli.migration.workspaces import WorkspaceMapping

_logger = logging.getLogger("slcli.migration")


class MigrationOutcome(VersionedModel):
    """Workspace mapping, discovery, and migration outcomes of one run."""

    model_config = ConfigDict(frozen=True)

    mapping: WorkspaceMapping
    discovery: MigrationDiscovery
    test_monitor: TestMonitorMigration
    files: FileTransfer
    file_references: FileReferenceRepair = FileReferenceRepair()


def format_file_transfer_summary(transfer: FileTransfer) -> str:
    """Returns a formatted summary of the file transfer results."""
    lines = [
        "File transfer:",
        f"  Transferred: {transfer.transferred}",
        f"  Already present: {transfer.already_present}",
        f"  Reassigned IDs: {len(transfer.reassigned_ids)}",
    ]
    return "\n".join(lines)


@flow(
    name="systemlink-migration",
    flow_run_name="migration-{migration_id}",
    persist_result=True,
    result_serializer="json",
    task_runner=migration_task_runner(),
)
def migrate_flow(
    migration_id: str,
    source_profile: str,
    destination_profile: str,
    workspace_mappings: Optional[Dict[str, str]],
    product_batch_size: int,
    result_batch_size: int,
) -> MigrationOutcome:
    """Discover source resources, synchronize workspaces, then migrate resources.

    File transfer and Test Monitor migration run in parallel after workspace
    synchronization. Result file references are repaired after both complete.

    Args:
        migration_id: Migration that scopes task cache keys.
        source_profile: Name of the source profile.
        destination_profile: Name of the destination profile.
        workspace_mappings: Source to destination workspace names; all by name when None.
        product_batch_size: Products per migration task.
        result_batch_size: Results, with their steps, per migration task.

    Raises:
        WorkspaceMappingError: If a source workspace does not exist.
        click.ClickException: If any file failed to transfer.
    """
    explicit_workspace_selection: Optional[List[str]] = (
        list(workspace_mappings) if workspace_mappings is not None else None
    )
    discovery = discover_flow(
        migration_id,
        source_profile,
        explicit_workspace_selection,
        require_complete_file_discovery=True,
    )
    mapping = synchronize_workspaces_task(
        migration_id, destination_profile, discovery.workspaces, workspace_mappings
    )
    files_future = transfer_files_task.submit(
        migration_id, source_profile, destination_profile, discovery.files, mapping
    )
    test_monitor = migrate_test_monitor_task.submit(
        migration_id,
        source_profile,
        destination_profile,
        mapping,
        discovery.test_monitor,
        product_batch_size,
        result_batch_size,
        discovery.files.source_to_destination_id_map,
    )
    references = repair_file_references_task.submit(
        migration_id,
        source_profile,
        destination_profile,
        files_future,
        test_monitor,
        return_state=False,
    )
    files_future.wait()
    test_monitor.wait()
    files = files_future.result()
    test_monitor_result = test_monitor.result()
    files_summary = format_file_transfer_summary(files)
    _logger.info(files_summary)
    click.echo(files_summary)
    repaired = references.result()
    summary = (
        f"Result file references: {repaired.updated} results updated, "
        f"{len(repaired.unresolved)} results with unresolved file IDs"
    )
    _logger.info(summary)
    click.echo(summary)
    return MigrationOutcome(
        mapping=mapping,
        discovery=discovery,
        test_monitor=test_monitor_result,
        files=files,
        file_references=repaired,
    )
