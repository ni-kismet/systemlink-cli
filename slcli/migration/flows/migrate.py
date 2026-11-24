"""Apply a migration plan by synchronizing workspaces and migrating resources."""

import logging
from typing import Dict, Optional

import click
from prefect import flow
from pydantic import ConfigDict

from slcli.migration.files.models import FileTransfer
from slcli.migration.files.transfer_task import transfer_files_task
from slcli.migration.flows.service import migration_task_runner
from slcli.migration.schema import VersionedModel
from slcli.migration.state import MigrationDiscovery
from slcli.migration.testmonitor.migration_task import migrate_test_monitor_task
from slcli.migration.testmonitor.models import TestMonitorMigration
from slcli.migration.users import migrate_users_task, review_users_task
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


def format_file_transfer_summary(transfer: FileTransfer) -> str:
    """Returns a formatted summary of the file transfer results."""
    lines = [
        "File transfer:",
        f"  Transferred: {transfer.transferred}",
        f"  Already present: {transfer.already_present}",
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
    discovery: MigrationDiscovery,
) -> MigrationOutcome:
    """Apply previously discovered resources to the destination.

    User review follows workspace synchronization. User migration, file transfer,
    and Test Monitor migration then run in parallel. Results are marked COMPLETE once
    Test Monitor migration completes.

    Args:
        migration_id: Migration that scopes task cache keys.
        source_profile: Name of the source profile.
        destination_profile: Name of the destination profile.
        workspace_mappings: Source to destination workspace names; all by name when None.
        product_batch_size: Products per migration task.
        result_batch_size: Results, with their steps, per migration task.
        discovery: Completed discovery results, including the planned file IDs.

    Raises:
        click.ClickException: If any file failed to transfer.
    """
    mapping = synchronize_workspaces_task(
        migration_id, destination_profile, discovery.workspaces, workspace_mappings
    )
    reviewed_users = review_users_task(source_profile, mapping)
    users_future = migrate_users_task.submit(destination_profile, reviewed_users)
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
    for resource, future in (
        ("User", users_future),
        ("Test Monitor", test_monitor),
        ("File", files_future),
    ):
        future.wait()
        if not future.state.is_completed():
            _logger.error("%s migration failed: %s", resource, future.state.message)

    users_future.result()
    test_monitor_result = test_monitor.result()
    files = files_future.result()
    files_summary = format_file_transfer_summary(files)
    _logger.info(files_summary)
    click.echo(files_summary)
    return MigrationOutcome(
        mapping=mapping,
        discovery=discovery,
        test_monitor=test_monitor_result,
        files=files,
    )
