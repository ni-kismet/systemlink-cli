"""Compose a discovery-only migration run for the ``migrate`` command."""

import logging
from collections.abc import Generator
from contextlib import contextmanager
from typing import Dict, Optional
from urllib.parse import urlparse

import click

from slcli._version import __version__
from slcli.migration.connection import MigrationConnection, resolve_migration_connection
from slcli.migration.orchestration import prefect_server, run_discovery
from slcli.migration.state import MigrationRun, create_migration_run, open_migration_run
from slcli.migration.testmonitor.models import TestMonitorDiscovery
from slcli.migration.workspace_client import WorkspaceClient

_logger = logging.getLogger("slcli.migration")


def start_migration(
    source_profile: str,
    workspace_mappings: Optional[Dict[str, str]],
    prefect_api_url: Optional[str],
) -> None:
    """Create a new migration run and discover its source resources."""
    connection = resolve_migration_connection(source_profile)
    _echo_source(connection)
    if workspace_mappings is not None:
        _require_source_workspaces(connection, workspace_mappings)
    run = create_migration_run(source_profile, workspace_mappings)
    _discover(run, connection, workspace_mappings, prefect_api_url)


def resume_migration(migration_id: str, prefect_api_url: Optional[str]) -> None:
    """Resume migration run with the original inputs and cached state."""
    try:
        run, metadata = open_migration_run(migration_id)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    connection = resolve_migration_connection(metadata.source_profile)
    _echo_source(connection)
    _discover(run, connection, metadata.workspace_mappings, prefect_api_url)


def format_summary(discovery: TestMonitorDiscovery) -> str:
    """Return deterministic Test Monitor discovery counts and failures."""
    lines = [
        "Test Monitor discovery:",
        f"  Products: {len(discovery.products)}",
        f"  Terminal results: {len(discovery.results)}",
        f"  Failed workspaces: {len(discovery.failures)}",
        *(f"    {failure.workspace}: {failure.error_type}" for failure in discovery.failures),
    ]
    return "\n".join(lines)


def _echo_source(connection: MigrationConnection) -> None:
    click.echo(f"Source: {connection.profile_name} ({connection.base_url})")
    if urlparse(connection.base_url).scheme.lower() != "https":
        click.echo("Warning: source connection does not use HTTPS.", err=True)
    if connection.ssl_verify is False:
        click.echo("Warning: source TLS certificate verification is disabled.", err=True)


def _require_source_workspaces(
    connection: MigrationConnection, workspace_mappings: Dict[str, str]
) -> None:
    existing = {workspace.name for workspace in WorkspaceClient(connection).query_workspaces()}
    unknown = sorted(set(workspace_mappings).difference(existing))
    if unknown:
        raise click.BadParameter(
            f"unknown source workspace: {', '.join(unknown)}",
            param_hint="--workspace-mappings",
        )


@contextmanager
def _run_log(run: MigrationRun) -> Generator[None, None, None]:
    """Write migration logs to the run directory for the duration of the run."""
    handler = logging.FileHandler(run.directory / "migration.log", encoding="utf-8")
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


def _discover(
    run: MigrationRun,
    connection: MigrationConnection,
    workspace_mappings: Optional[Dict[str, str]],
    prefect_api_url: Optional[str],
) -> None:
    click.echo(f"Migration ID: {run.migration_id}")
    workspaces = list(workspace_mappings) if workspace_mappings is not None else None
    server_mode = "managed" if prefect_api_url is None else "external"
    with _run_log(run):
        _logger.info(
            "Discovery started: migration=%s cli=%s profile=%s endpoint=%s workspaces=%s "
            "prefect_server=%s",
            run.migration_id,
            __version__,
            connection.profile_name,
            connection.base_url,
            workspaces if workspaces is not None else "all",
            server_mode,
        )
        try:
            with prefect_server(run, prefect_api_url) as api_url:
                discovery = run_discovery(run, connection.profile_name, workspaces, api_url)
        except BaseException as exc:
            _logger.error("Discovery failed: %s", type(exc).__name__)
            raise
        test_monitor = discovery.test_monitor
        _logger.info(
            "Discovery completed: products=%d results=%d failed_workspaces=%s",
            len(test_monitor.products),
            len(test_monitor.results),
            [failure.workspace for failure in test_monitor.failures],
        )
    click.echo(format_summary(test_monitor))
