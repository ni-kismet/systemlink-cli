"""Compose a discovery-only migration run for the ``migrate`` command."""

import logging
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path
from typing import Dict, List, Optional
from urllib.parse import urlparse

import click
import requests

from slcli._version import __version__
from slcli.migration.connection import MigrationConnection, resolve_migration_connection
from slcli.migration.orchestration import prefect_server, run_discovery
from slcli.migration.state import MigrationRun, create_migration_run, open_migration_run
from slcli.migration.testmonitor.models import TestMonitorDiscovery
from slcli.migration.workspace_client import Workspace, WorkspaceClient
from slcli.migration.workspaces import (
    WorkspaceMapping,
    WorkspaceMappingError,
    map_workspaces,
)
from slcli.utils import handle_api_error

_logger = logging.getLogger("slcli.migration")
MIGRATION_LOG = "migration.log"


def start_migration(
    source_profile: str,
    destination_profile: str,
    workspace_mappings: Optional[Dict[str, str]],
    prefect_api_url: Optional[str],
) -> None:
    """Create a new migration run after mapping its workspaces, then discover resources."""
    source = resolve_migration_connection(source_profile)
    destination = resolve_migration_connection(destination_profile)
    _echo_connections(source, destination)
    mapping = _map_workspaces(source, destination, workspace_mappings)
    run = create_migration_run(source_profile, destination_profile, workspace_mappings)
    _discover(run, source, destination, mapping, workspace_mappings, prefect_api_url)


def resume_migration(migration_id: str, prefect_api_url: Optional[str]) -> None:
    """Resume migration run with the original inputs and cached state."""
    try:
        run, metadata = open_migration_run(migration_id)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    source = resolve_migration_connection(metadata.source_profile)
    destination = resolve_migration_connection(metadata.destination_profile)
    _echo_connections(source, destination)
    mapping = _map_workspaces(source, destination, metadata.workspace_mappings)
    _discover(run, source, destination, mapping, metadata.workspace_mappings, prefect_api_url)


def format_summary(discovery: TestMonitorDiscovery) -> str:
    """Return deterministic Test Monitor discovery counts and failures."""
    lines = [
        "Test Monitor discovery:",
        f"  Products: {len(discovery.products)}",
        f"  Terminal results: {len(discovery.results)}",
        f"  Failed workspaces: {len(discovery.failures)}",
        *(f"    {failure.workspace}: {failure.error_type}" for failure in discovery.failures),
    ]
    if discovery.failures:
        lines.append("  Product workspaces were inferred without the failed workspaces.")
    return "\n".join(lines)


def _all_workspaces_failed(discovery: TestMonitorDiscovery) -> bool:
    return bool(discovery.workspaces) and len(discovery.failures) == len(discovery.workspaces)


def format_workspace_mapping(mapping: WorkspaceMapping) -> str:
    """Return each source workspace and the destination workspace it migrates to."""
    return "\n".join(
        [
            "Workspace mapping:",
            *(
                f"  {workspace.source_name} -> {workspace.destination_name}"
                for workspace in mapping.workspaces
            ),
        ]
    )


def _echo_connections(source: MigrationConnection, destination: MigrationConnection) -> None:
    for role, connection in (("Source", source), ("Destination", destination)):
        click.echo(f"{role}: {connection.profile_name} ({connection.base_url})")
        if urlparse(connection.base_url).scheme.lower() != "https":
            click.echo(f"Warning: {role.lower()} connection does not use HTTPS.", err=True)
        if connection.ssl_verify is False:
            click.echo(
                f"Warning: {role.lower()} TLS certificate verification is disabled.", err=True
            )


def _map_workspaces(
    source: MigrationConnection,
    destination: MigrationConnection,
    workspace_mappings: Optional[Dict[str, str]],
) -> WorkspaceMapping:
    """Discover workspaces on both sides and fail before any migration work if unmapped."""
    workspaces: List[List[Workspace]] = []
    for role, connection in (("source", source), ("destination", destination)):
        try:
            workspaces.append(list(WorkspaceClient(connection).query_workspaces()))
        except requests.RequestException as exc:
            click.echo(
                f"Failed to query {role} workspaces with profile '{connection.profile_name}'.",
                err=True,
            )
            handle_api_error(exc)
    try:
        return map_workspaces(workspaces[0], workspaces[1], workspace_mappings)
    except WorkspaceMappingError as exc:
        # TODO(AB#4088608): Synchronize workspaces will create missing destination workspaces.
        hint = (
            "Destination workspaces are not created by migration."
            if workspace_mappings is not None
            else "Create the destination workspaces or select workspaces with "
            "--workspace-mappings. Destination workspaces are not created by migration."
        )
        raise click.ClickException(f"{exc}. {hint}") from exc


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


def _discover(
    run: MigrationRun,
    source: MigrationConnection,
    destination: MigrationConnection,
    mapping: WorkspaceMapping,
    workspace_mappings: Optional[Dict[str, str]],
    prefect_api_url: Optional[str],
) -> None:
    click.echo(f"Migration ID: {run.migration_id}")
    click.echo(format_workspace_mapping(mapping))
    log_path = run.directory / MIGRATION_LOG
    workspaces = list(workspace_mappings) if workspace_mappings is not None else None
    server_mode = "managed" if prefect_api_url is None else "external"
    with _run_log(log_path):
        _logger.info(
            "Discovery started: migration=%s cli=%s profile=%s endpoint=%s workspaces=%s "
            "destination_profile=%s destination_endpoint=%s prefect_server=%s",
            run.migration_id,
            __version__,
            source.profile_name,
            source.base_url,
            workspaces if workspaces is not None else "all",
            destination.profile_name,
            destination.base_url,
            server_mode,
        )
        _logger.info(
            "Workspace mapping: %s",
            [
                f"{w.source_name}({w.source_id}) -> {w.destination_name}({w.destination_id})"
                for w in mapping.workspaces
            ],
        )
        try:
            with prefect_server(run, prefect_api_url) as api_url:
                discovery = run_discovery(run, source.profile_name, workspaces, api_url)
        except BaseException as exc:
            _logger.error("Discovery failed: %s: %s", type(exc).__name__, exc)
            click.echo(f"Log: {log_path}", err=True)
            raise
        test_monitor = discovery.test_monitor
        _logger.info(
            "Discovery completed: products=%d results=%d failed_workspaces=%s",
            len(test_monitor.products),
            len(test_monitor.results),
            [failure.workspace for failure in test_monitor.failures],
        )
    click.echo(format_summary(test_monitor))
    click.echo(f"Log: {log_path}")
    if _all_workspaces_failed(test_monitor):
        raise click.ClickException("Discovery failed for every workspace.")
