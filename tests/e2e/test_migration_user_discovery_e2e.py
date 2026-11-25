"""Read-only E2E coverage for migration user discovery."""

import os

import pytest

from slcli.migration.connection import resolve_migration_connection
from slcli.migration.users.client import UserMigrationClient
from slcli.migration.users.discovery import discover_user_candidates
from slcli.migration.workspace_client import WorkspaceClient
from slcli.migration.workspaces import (
    MappedWorkspace,
    WorkspaceMapping,
    discover_workspaces,
)

pytestmark = pytest.mark.e2e_migration


def test_user_discovery_finds_super_users() -> None:
    """Source Super Users are discovered with access to every selected workspace."""
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
    users = client.query_users()
    policies = client.query_policies()
    super_user_policy_ids = {
        policy.id
        for policy in policies
        if policy.built_in and policy.name.casefold() == "super user"
    }
    assert super_user_policy_ids, "Source must have a built-in Super User policy"
    super_user_ids = {
        user.id
        for user in users
        if user.type.casefold() == "user" and super_user_policy_ids.intersection(user.policies)
    }
    assert super_user_ids, "Source must have an active user with the Super User policy"
    assert mapping.workspaces, "Source must have at least one selected workspace"

    candidates = discover_user_candidates(
        users,
        policies,
        mapping,
        client.query_auth_mappings(),
    )

    assert all(candidate.user.type == "user" for candidate in candidates)
    assert all(candidate.workspaces for candidate in candidates)
    candidates_by_id = {candidate.user.id: candidate for candidate in candidates}
    assert super_user_ids <= candidates_by_id.keys()
    for user_id in super_user_ids:
        assert candidates_by_id[user_id].workspaces == mapping.workspaces
