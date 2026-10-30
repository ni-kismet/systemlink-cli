"""Compose a migration run for the ``migrate`` command."""

import logging
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, Optional
from urllib.parse import urlparse

import click
import requests

from slcli._version import __version__
from slcli.migration.connection import MigrationConnection, resolve_migration_connection
from slcli.migration.orchestration import prefect_server, run_migration
from slcli.migration.state import (
    DEFAULT_PRODUCT_BATCH_SIZE,
    DEFAULT_RESULT_BATCH_SIZE,
    MigrationRun,
    RunMetadata,
    create_migration_run,
    open_migration_run,
)
from slcli.migration.summary import (
    failed_items,
    format_migration_summary,
    format_summary,
    format_workspace_mapping,
)
from slcli.migration.testmonitor.models import TestMonitorDiscovery
from slcli.migration.workspaces import WorkspaceMappingError
from slcli.utils import handle_api_error

_logger = logging.getLogger("slcli.migration")
MIGRATION_LOG = "migration.log"


def start_migration(
    source_profile: str,
    destination_profile: str,
    workspace_mappings: Optional[Dict[str, str]],
    prefect_api_url: Optional[str],
    product_batch_size: int = DEFAULT_PRODUCT_BATCH_SIZE,
    result_batch_size: int = DEFAULT_RESULT_BATCH_SIZE,
) -> None:
    """Create a new migration run, then migrate resources."""
    source = resolve_migration_connection(source_profile)
    destination = resolve_migration_connection(destination_profile)
    _echo_connections(source, destination)
    run = create_migration_run(
        source_profile,
        destination_profile,
        workspace_mappings,
        product_batch_size=product_batch_size,
        result_batch_size=result_batch_size,
    )
    _, metadata = open_migration_run(run.migration_id, run.directory.parent)
    _migrate(run, metadata, source, destination, prefect_api_url)


def resume_migration(migration_id: str, prefect_api_url: Optional[str]) -> None:
    """Resume migration run with the original inputs and cached state."""
    try:
        run, metadata = open_migration_run(migration_id)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    source = resolve_migration_connection(metadata.source_profile)
    destination = resolve_migration_connection(metadata.destination_profile)
    _echo_connections(source, destination)
    _migrate(run, metadata, source, destination, prefect_api_url)


def _all_workspaces_failed(discovery: TestMonitorDiscovery) -> bool:
    return bool(discovery.workspaces) and len(discovery.failures) == len(discovery.workspaces)


def _echo_connections(source: MigrationConnection, destination: MigrationConnection) -> None:
    for role, connection in (("Source", source), ("Destination", destination)):
        click.echo(f"{role}: {connection.profile_name} ({connection.base_url})")
        if urlparse(connection.base_url).scheme.lower() != "https":
            click.echo(f"Warning: {role.lower()} connection does not use HTTPS.", err=True)
        if connection.ssl_verify is False:
            click.echo(
                f"Warning: {role.lower()} TLS certificate verification is disabled.", err=True
            )


def _mapping_error(
    exc: WorkspaceMappingError, workspace_mappings: Optional[Dict[str, str]]
) -> click.ClickException:
    # TODO(AB#4088608): Synchronize workspaces will create missing destination workspaces.
    hint = (
        "Destination workspaces are not created by migration."
        if workspace_mappings is not None
        else "Create the destination workspaces or select workspaces with "
        "--workspace-mappings. Destination workspaces are not created by migration."
    )
    return click.ClickException(f"{exc}. {hint}")


@contextmanager
def _run_log(log_path: Path) -> Generator[None, None, None]:
    """Write migration logs to the run directory for the duration of the run."""
    handler = logging.FileHandler(log_path, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s %(message)s"))
    previous_level = _logger.level
    _logger.addHandler(handler)
    _logger.setLevel(logging.INFO)
    try:
        yield
    finally:
        _logger.removeHandler(handler)
        _logger.setLevel(previous_level)
        handler.close()


def _migrate(
    run: MigrationRun,
    metadata: RunMetadata,
    source: MigrationConnection,
    destination: MigrationConnection,
    prefect_api_url: Optional[str],
) -> None:
    click.echo(f"Migration ID: {run.migration_id}")
    log_path = run.directory / MIGRATION_LOG
    workspace_mappings = metadata.workspace_mappings
    workspaces = list(workspace_mappings) if workspace_mappings is not None else None
    server_mode = "managed" if prefect_api_url is None else "external"
    with _run_log(log_path):
        _logger.info(
            "Migration started: migration=%s cli=%s profile=%s endpoint=%s workspaces=%s "
            "destination_profile=%s destination_endpoint=%s prefect_server=%s "
            "product_batch_size=%d result_batch_size=%d",
            run.migration_id,
            __version__,
            source.profile_name,
            source.base_url,
            workspaces if workspaces is not None else "all",
            destination.profile_name,
            destination.base_url,
            server_mode,
            metadata.product_batch_size,
            metadata.result_batch_size,
        )
        try:
            with prefect_server(run, prefect_api_url) as api_url:
                outcome = run_migration(run, metadata, api_url)
        except WorkspaceMappingError as exc:
            _log_failure(exc, log_path)
            raise _mapping_error(exc, workspace_mappings) from exc
        except requests.RequestException as exc:
            _log_failure(exc, log_path)
            handle_api_error(exc)
            raise
        except BaseException as exc:
            _log_failure(exc, log_path)
            raise
        _logger.info(
            "Workspace mapping: %s",
            [
                f"{w.source_name}({w.source_id}) -> {w.destination_name}({w.destination_id})"
                for w in outcome.mapping.workspaces
            ],
        )
        test_monitor = outcome.discovery.test_monitor
        migration = outcome.test_monitor
        failed = len(failed_items(migration.products)) + len(failed_items(migration.results))
        _logger.info(
            "Migration completed: products=%d results=%d failed_workspaces=%s failed_items=%d",
            len(test_monitor.products),
            len(test_monitor.results),
            [failure.workspace for failure in test_monitor.failures],
            failed,
        )
    click.echo(format_workspace_mapping(outcome.mapping))
    click.echo(format_summary(test_monitor))
    click.echo(format_migration_summary(migration))
    click.echo(f"Log: {log_path}")
    if _all_workspaces_failed(test_monitor):
        raise click.ClickException("Discovery failed for every workspace.")
    if failed:
        raise click.ClickException(f"{failed} items failed to migrate.")


def _log_failure(exc: BaseException, log_path: Path) -> None:
    _logger.error("Migration failed: %s: %s", type(exc).__name__, exc)
    click.echo(f"Log: {log_path}", err=True)
