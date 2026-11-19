"""Persisted Prefect task for Test Monitor discovery."""

import click
from prefect import task
from prefect.cache_policies import INPUTS, TASK_SOURCE

from slcli.migration.connection import resolve_migration_connection
from slcli.migration.testmonitor.client import TestMonitorClient
from slcli.migration.testmonitor.discovery import discover_test_monitor
from slcli.migration.testmonitor.models import TestMonitorDiscovery
from slcli.migration.workspaces import DiscoveredWorkspaces


@task(
    name="discover-test-monitor",
    persist_result=True,
    result_serializer="json",
    cache_result_in_memory=False,
    cache_policy=TASK_SOURCE + INPUTS,
)
def discover_test_monitor_task(
    migration_id: str,
    source_profile: str,
    workspaces: DiscoveredWorkspaces,
) -> TestMonitorDiscovery:
    """Discover Test Monitor resources in the discovered source workspaces.

    Inputs are references, never credentials. ``migration_id`` is unused by the
    body but scopes the cache key to one migration. Partial discovery is not cached.
    """
    connection = resolve_migration_connection(source_profile)
    discovery = discover_test_monitor(
        TestMonitorClient(connection),
        workspaces,
    )
    if discovery.failures:
        failed_workspaces = ", ".join(failure.workspace for failure in discovery.failures)
        raise click.ClickException(
            f"Test Monitor discovery failed for workspace(s): {failed_workspaces}. "
            "Retry the migration before results are created."
        )
    return discovery
