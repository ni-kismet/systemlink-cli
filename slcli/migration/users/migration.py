"""Reconcile destination users and their workspace permissions."""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

import click

from slcli.migration.connection import resolve_migration_connection
from slcli.migration.users.client import AuthMapping, User, UserMigrationClient
from slcli.migration.users.discovery import is_workspace_auth_mapping
from slcli.migration.users.models import UserMigrationSelections, UserToMigrate
from slcli.migration.workspaces import MappedWorkspace

_logger = logging.getLogger("slcli.migration")


@dataclass(frozen=True)
class _UserMigrationTask:
    """One user record and its missing workspace auth-mappings."""

    source_user: User
    existing_user_id: Optional[str]
    workspaces: Tuple[MappedWorkspace, ...]


def _plan_user_migrations(
    users_to_migrate: List[UserToMigrate],
    existing_users: List[User],
    existing_auth_mappings: List[AuthMapping],
) -> List[_UserMigrationTask]:
    existing_users_by_email = _map_users_by_email(existing_users)
    existing_user_authorized_workspaces = _get_authorized_workspaces_by_user(existing_auth_mappings)

    tasks: List[_UserMigrationTask] = []
    for to_migrate in users_to_migrate:
        assert to_migrate.user.email is not None
        matches = existing_users_by_email.get(to_migrate.user.email.strip().casefold(), [])
        if len(matches) > 1:
            click.echo(
                f"Warning: Skipping user '{to_migrate.user.email}': "
                "multiple destination users have this email.",
                err=True,
            )
            continue
        existing_user = matches[0] if matches else None
        existing_authorizations = (
            existing_user_authorized_workspaces.get(existing_user.id, set())
            if existing_user is not None
            else set()
        )
        workspaces = _get_not_yet_authorized_workspaces(to_migrate, existing_authorizations)
        tasks.append(
            _UserMigrationTask(
                source_user=to_migrate.user,
                existing_user_id=existing_user.id if existing_user else None,
                workspaces=tuple(workspaces),
            )
        )
    return tasks


def _map_users_by_email(users: List[User]) -> Dict[str, List[User]]:
    by_email: Dict[str, List[User]] = {}
    for user in users:
        assert user.email is not None
        normalized_email = user.email.strip().casefold()
        by_email.setdefault(normalized_email, []).append(user)
    return by_email


def _get_authorized_workspaces_by_user(auth_mappings: List[AuthMapping]) -> Dict[str, Set[str]]:
    authorized_workspaces: Dict[str, Set[str]] = {}
    for auth_mapping in auth_mappings:
        if is_workspace_auth_mapping(auth_mapping):
            assert auth_mapping.workspace is not None
            authorized_workspaces.setdefault(auth_mapping.selector.value, set()).add(
                auth_mapping.workspace
            )
    return authorized_workspaces


def _get_not_yet_authorized_workspaces(
    to_migrate: UserToMigrate, existing_authorizations: set[str]
) -> List[MappedWorkspace]:
    workspaces: List[MappedWorkspace] = []
    do_not_recreate = existing_authorizations
    for workspace in to_migrate.workspaces:
        if workspace.destination_id not in do_not_recreate:
            workspaces.append(workspace)
            do_not_recreate.add(workspace.destination_id)
    return workspaces


def apply_user_migrations(destination_profile: str, selections: UserMigrationSelections) -> int:
    """Create or reuse destination users and grant their workspace access.

    The destination is queried on every call, so re-running with the same selections reuses
    users and grants that already exist and writes only what is missing. Users matching
    multiple destination accounts are skipped with a warning.
    """
    if not selections.users:
        click.echo("Successfully migrated 0 users.")
        return 0

    destination_client = UserMigrationClient(resolve_migration_connection(destination_profile))
    existing_users = destination_client.query_users(include_inactive=True)
    existing_auth_mappings = destination_client.query_auth_mappings()
    tasks = _plan_user_migrations(
        selections.users,
        existing_users,
        existing_auth_mappings,
    )

    if not tasks:
        click.echo("Successfully migrated 0 users.")
        return 0

    if destination_client.readonly and any(
        task.existing_user_id is None or task.workspaces for task in tasks
    ):
        destination_client._ensure_writable("migrate users")

    collaborator_template_id = destination_client.collaborator_template_id()
    if collaborator_template_id is None:
        click.echo(
            "Error: the built-in Collaborator template was not found. Aborting.",
            err=True,
        )
        raise click.Abort()

    created_users = 0
    created_mappings = 0
    for task in tasks:
        user_id = task.existing_user_id
        if user_id is None:
            user_id = destination_client.create_user(task.source_user)
            created_users += 1
        for workspace in task.workspaces:
            destination_client.create_auth_mapping(
                user_id, workspace.destination_id, collaborator_template_id
            )
            created_mappings += 1

    _logger.info(
        "Users migrated: users=%d created=%d auth_mappings=%d",
        len(tasks),
        created_users,
        created_mappings,
    )
    click.echo(f"Successfully migrated {len(tasks)} users.")
    return len(tasks)
