"""Source and destination profiles for migration E2E tests.

Fixtures, not migration, create the destination workspace. Fixtures may only
create the fixed names in ``tests.e2e.workspaces``.
"""

import os
from dataclasses import dataclass

import pytest

from slcli.migration.connection import MigrationConnection, resolve_migration_connection
from slcli.ssl_trust import inject_os_trust
from tests.e2e.workspaces import E2EWorkspace

SOURCE_PROFILE_ENV = "SLCLI_E2E_SOURCE_PROFILE"
DESTINATION_PROFILE_ENV = "SLCLI_E2E_DESTINATION_PROFILE"


@dataclass(frozen=True)
class MigrationEndpoints:
    """Resolved source and destination connections and the destination workspace."""

    source: MigrationConnection
    destination: MigrationConnection
    destination_workspace: str
    destination_workspace_id: str


def _required_env(name: str) -> str:
    value = os.getenv(name)
    if not value:
        pytest.skip(f"{name} is not configured")
    return value


def resolve_endpoints() -> MigrationEndpoints:
    """Resolve configured profiles and get or create the destination workspace."""
    source_profile = _required_env(SOURCE_PROFILE_ENV)
    destination_profile = _required_env(DESTINATION_PROFILE_ENV)
    inject_os_trust()
    destination = resolve_migration_connection(destination_profile)
    return MigrationEndpoints(
        source=resolve_migration_connection(source_profile),
        destination=destination,
        destination_workspace=E2EWorkspace.DESTINATION.value,
        destination_workspace_id=get_or_create_workspace(destination, E2EWorkspace.DESTINATION),
    )


def get_or_create_workspace(connection: MigrationConnection, workspace: E2EWorkspace) -> str:
    """Return the ID of a fixture-owned workspace, creating or re-enabling it if necessary.

    Workspaces cannot be deleted on shared servers, so fixtures reuse fixed names.
    A reused workspace may have been disabled, which rejects every write.
    """
    name = workspace.value
    session = connection.create_session()
    url = f"{connection.base_url}/niuser/v1/workspaces"
    response = session.get(url, params={"name": name}, timeout=30)
    response.raise_for_status()
    matches = [w for w in response.json().get("workspaces", []) if w.get("name") == name]
    if not matches:
        created = session.post(url, json={"name": name, "enabled": True}, timeout=30)
        created.raise_for_status()
        return str(created.json()["id"])
    existing = matches[0]
    if not existing.get("enabled", True):
        enabled = session.put(
            f"{url}/{existing['id']}", json={"name": name, "enabled": True}, timeout=30
        )
        enabled.raise_for_status()
    return str(existing["id"])


def get_or_create_disabled_workspace(
    connection: MigrationConnection, workspace: E2EWorkspace
) -> str:
    """Return the ID of a fixture-owned workspace, leaving it disabled.

    Disabled workspaces are never deleted, so the workspace persists for later runs.
    """
    workspace_id = get_or_create_workspace(connection, workspace)
    session = connection.create_session()
    response = session.put(
        f"{connection.base_url}/niuser/v1/workspaces/{workspace_id}",
        json={"name": workspace.value, "enabled": False},
        timeout=30,
    )
    response.raise_for_status()
    return workspace_id
