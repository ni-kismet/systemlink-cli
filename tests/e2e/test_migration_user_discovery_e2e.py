"""Read-only E2E coverage for migration user discovery."""

import os

import pytest

from slcli.migration.connection import resolve_migration_connection
from slcli.migration.users import UserMigrationClient, discover_user_candidates
from slcli.migration.workspace_client import WorkspaceClient
from slcli.migration.workspaces import (
    MappedWorkspace,
    WorkspaceMapping,
    discover_workspaces,
)

pytestmark = pytest.mark.e2e_migration


def test_user_discovery_queries_source_memberships() -> None:
    """Source users, policies, and direct mappings produce valid workspace candidates."""
    source_profile = os.getenv("SLCLI_E2E_SOURCE_PROFILE")
    if not source_profile:
        pytest.skip("SLCLI_E2E_SOURCE_PROFILE is not configured")

    connection = resolve_migration_connection(source_profile)
    discovered = discover_workspaces(WorkspaceClient(connection).query_workspaces(), None)
    mapping = WorkspaceMapping(
        workspaces=tuple(
            MappedWorkspace(
                source_name=workspace.name,
                source_id=workspace.id,
                destination_name=workspace.name,
                destination_id=workspace.id,
            )
            for workspace in discovered.source.values()
        )
    )
    client = UserMigrationClient(connection)
    candidates = discover_user_candidates(
        client.query_users(),
        client.query_policies(),
        mapping,
        client.query_auth_mappings(),
    )

    assert all(candidate.user.type == "user" for candidate in candidates)
    assert all(candidate.workspaces for candidate in candidates)
