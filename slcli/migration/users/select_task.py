"""Persist the interactive user review as a Prefect task result."""

from typing import List

from prefect import task
from prefect.cache_policies import INPUTS, TASK_SOURCE

from slcli.migration.connection import resolve_migration_connection
from slcli.migration.users.client import UserMigrationClient
from slcli.migration.users.discovery import discover_user_candidates
from slcli.migration.users.models import UserToMigrate, UserMigrationSelections
from slcli.migration.users.select import resolve_emails, select_users
from slcli.migration.workspaces import WorkspaceMapping


@task(
    name="select-users",
    persist_result=True,
    result_serializer="json",
    cache_result_in_memory=False,
    cache_policy=TASK_SOURCE + INPUTS,
)
def select_users_task(source_profile: str, mapping: WorkspaceMapping) -> UserMigrationSelections:
    """Ask which eligible source users to migrate and prompt for any missing emails.

    The result is persisted, so a resumed run does not re-prompt.
    """
    candidates: List[UserToMigrate] = []
    if mapping.workspaces:
        source_client = UserMigrationClient(resolve_migration_connection(source_profile))
        candidates = discover_user_candidates(
            source_client.query_users(),
            source_client.query_policies(),
            mapping,
            source_client.query_auth_mappings(),
        )
    selected = select_users(candidates) if candidates else []
    return UserMigrationSelections(users=resolve_emails(selected))
