"""Run migration flows against a Prefect server."""

from collections.abc import Generator
from contextlib import contextmanager
from typing import List, Optional

from prefect.events.worker import EventsWorker
from prefect.settings import (
    PREFECT_API_URL,
    PREFECT_HOME,
    PREFECT_LOGGING_TO_API_ENABLED,
    temporary_settings,
)

from slcli.migration.flows.discover import MigrationDiscovery, discover_flow
from slcli.migration.prefect_server import ManagedPrefectServer
from slcli.migration.state import MigrationRun


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
    with temporary_settings(
        updates={
            PREFECT_HOME: run.client_home,
            PREFECT_API_URL: api_url,
            PREFECT_LOGGING_TO_API_ENABLED: False,
            "results.local_storage_path": run.results_path,
        }
    ):
        try:
            return discover_flow(run.migration_id, source_profile, workspaces)
        finally:
            # Deliver queued task-state events before the server may be stopped.
            EventsWorker.drain_all()
