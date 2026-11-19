"""Run migration flows against a Prefect server."""

from collections.abc import Generator
from contextlib import contextmanager
from typing import List, Optional

import click
from prefect.events.worker import EventsWorker
from prefect.settings import (
    PREFECT_API_URL,
    PREFECT_HOME,
    PREFECT_LOGGING_TO_API_ENABLED,
    temporary_settings,
)
from pydantic import ValidationError

from slcli.migration.flows.discover import discover_flow
from slcli.migration.flows.migrate import MigrationOutcome, migrate_flow
from slcli.migration.prefect_server import ManagedPrefectServer
from slcli.migration.state import MigrationDiscovery, MigrationPlan, MigrationRun, RunMetadata


@contextmanager
def prefect_server(run: MigrationRun, api_url: Optional[str] = None) -> Generator[str, None, None]:
    """Yield a Prefect API URL for a run.

    Args:
        run: Migration run whose ``server_home`` can host a managed server.
        api_url: An externally managed server to use instead; the caller owns its
            lifecycle and database.
    """
    if api_url is not None:
        yield api_url
        return
    with ManagedPrefectServer(run.server_home) as managed_api_url:
        yield managed_api_url


@contextmanager
def _run_settings(run: MigrationRun, api_url: str) -> Generator[None, None, None]:
    with temporary_settings(
        updates={
            PREFECT_HOME: run.client_home,
            PREFECT_API_URL: api_url,
            PREFECT_LOGGING_TO_API_ENABLED: False,
            "results.local_storage_path": run.results_path,
        }
    ):
        try:
            yield
        finally:
            # Deliver queued task-state events before the server may be stopped.
            EventsWorker.drain_all()


def run_discovery(
    run: MigrationRun,
    source_profile: str,
    workspaces: Optional[List[str]],
    api_url: str,
) -> MigrationDiscovery:
    """Run the discovery flow for a migration run on a Prefect server.

    Args:
        run: Migration run that provides the client home and result storage.
        source_profile: Name of the source profile.
        workspaces: Source workspace names to discover; all workspaces when None.
        api_url: Prefect API URL from :func:`prefect_server`.
    """
    with _run_settings(run, api_url):
        return discover_flow(run.migration_id, source_profile, workspaces)


def run_migration(
    run: MigrationRun,
    metadata: RunMetadata,
    api_url: str,
) -> MigrationOutcome:
    """Apply a saved plan, finishing discovery first if the run has no plan yet.

    Args:
        run: Migration run that provides the client home and result storage.
        metadata: Persisted run inputs, including profiles and batch sizes.
        api_url: Prefect API URL from :func:`prefect_server`.
    """
    try:
        plan = _read_plan(run)
    except FileNotFoundError:
        plan = run_plan(run, metadata, api_url)
    return _execute_plan(run, metadata, api_url, plan)


def apply_saved_plan(run: MigrationRun, metadata: RunMetadata, api_url: str) -> MigrationOutcome:
    """Apply a completed plan from disk, never running discovery."""
    try:
        plan = _read_plan(run)
    except FileNotFoundError as exc:
        raise click.ClickException(
            f"Migration '{run.migration_id}' has no completed plan."
        ) from exc
    return _execute_plan(run, metadata, api_url, plan)


def _execute_plan(
    run: MigrationRun, metadata: RunMetadata, api_url: str, plan: MigrationPlan
) -> MigrationOutcome:
    with _run_settings(run, api_url):
        return migrate_flow(
            run.migration_id,
            metadata.source_profile,
            metadata.destination_profile,
            metadata.workspace_mappings,
            metadata.product_batch_size,
            metadata.result_batch_size,
            plan.discovery,
        )


def _read_plan(run: MigrationRun) -> MigrationPlan:
    try:
        return run.read_plan()
    except FileNotFoundError:
        raise
    except (OSError, ValidationError) as exc:
        raise click.ClickException(
            f"Cannot load the completed plan for migration '{run.migration_id}'. "
            "The plan is unreadable, incomplete, or incompatible."
        ) from exc
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc


def run_plan(run: MigrationRun, metadata: RunMetadata, api_url: str) -> MigrationPlan:
    """Discover all selected resources and atomically save the completed plan."""
    mappings = metadata.workspace_mappings
    workspaces = list(mappings) if mappings is not None else None
    discovery = run_discovery(run, metadata.source_profile, workspaces, api_url)
    try:
        plan = MigrationPlan(migration_id=run.migration_id, discovery=discovery)
    except ValidationError as exc:
        raise click.ClickException("Discovery did not produce a complete migration plan.") from exc

    try:
        run.write_plan(plan)
    except OSError as exc:
        raise click.ClickException(f"Cannot save the migration plan: {exc}") from exc
    return plan
