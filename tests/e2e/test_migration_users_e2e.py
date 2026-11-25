"""Live destination user migration coverage."""

import uuid
from typing import Dict, List, NamedTuple, Optional, Union

import pytest
import requests

from slcli.migration.api import ApiModel, REQUEST_TIMEOUT_SECONDS
from slcli.migration.connection import MigrationConnection
from slcli.migration.users.client import PAGE_SIZE, AuthMapping, User, UserMigrationClient
from slcli.migration.users.migration import apply_user_migrations
from slcli.migration.users.models import UserMigrationSelections, UserToMigrate
from slcli.migration.workspaces import MappedWorkspace
from tests.e2e.migration_endpoints import resolve_endpoints
from tests.e2e.owned_resource_helpers import OWNER_PROPERTY, owner_properties

pytestmark = pytest.mark.e2e_migration


class TestContext(NamedTuple):
    connection: MigrationConnection
    client: UserMigrationClient
    email: str
    owner: str
    workspace: MappedWorkspace
    selections: UserMigrationSelections


class _MappingWithId(AuthMapping):
    id: str


class _MappingPage(ApiModel):
    auth_mappings: List[_MappingWithId]


def test_migrate_user_and_workspace_grant() -> None:
    """Create and reuse a destination user and grant, then remove both."""
    cxt = _setup()

    with cxt.connection.create_session() as session:
        created_user_id: Optional[str] = None
        try:
            assert apply_user_migrations(cxt.connection.profile_name, cxt.selections) == 1
            created_user_id = _query_and_verify_user(cxt)
            _query_and_verify_auth_mapping(cxt, created_user_id)

            # Re-apply the same migrations to ensure idempotency
            assert apply_user_migrations(cxt.connection.profile_name, cxt.selections) == 1
            assert _query_and_verify_user(cxt) == created_user_id
            _query_and_verify_auth_mapping(cxt, created_user_id)
        finally:
            _cleanup_user(cxt.client, session, cxt.connection.base_url, cxt.email, cxt.owner, created_user_id)


def _setup() -> TestContext:
    endpoints = resolve_endpoints()
    connection = endpoints.destination
    assert not connection.readonly, "Destination profile must permit writes"
    client = UserMigrationClient(connection)
    owner = uuid.uuid4().hex
    email = f"slcli-migration-e2e-{owner}@example.invalid"
    assert not [
        user
        for user in client.query_users(include_inactive=True)
        if user.email and user.email.strip().casefold() == email.casefold()
    ], "Test email already exists on the destination"

    workspace = MappedWorkspace(
        source_name="source",
        source_id="source",
        destination_name=endpoints.destination_workspace,
        destination_id=endpoints.destination_workspace_id,
    )
    selections = UserMigrationSelections(
        users=[
            UserToMigrate(
                user=User(
                    id="source-user",
                    type="user",
                    first_name="Migration E2E",
                    email=email,
                    properties=owner_properties(owner),
                ),
                workspaces=(workspace,),
            )
        ]
    )
    return TestContext(
        connection=connection,
        client=client,
        email=email,
        owner=owner,
        workspace=workspace,
        selections=selections,
    )


def _query_and_verify_user(cxt: TestContext) -> str:
    matches = [
        user
        for user in cxt.client.query_users(include_inactive=True)
        if user.email and user.email.strip().casefold() == cxt.email.casefold()
    ]
    assert len(matches) == 1
    assert matches[0].properties.get(OWNER_PROPERTY) == cxt.owner
    return matches[0].id


def _query_and_verify_auth_mapping(cxt: TestContext, user_id: str) -> None:
    num_grants = sum(
            1
            for mapping in cxt.client.query_auth_mappings()
            if mapping.type == "user-id"
            and mapping.selector.key == "user-id"
            and mapping.selector.value == user_id
            and mapping.workspace == cxt.workspace.destination_id
        )
    assert num_grants == 1


def _cleanup_user(
    client: UserMigrationClient,
    session: requests.Session,
    base_url: str,
    email: str,
    owner: str,
    known_user_id: Optional[str] = None,
) -> None:
    users = [
        user
        for user in client.query_users(include_inactive=True)
        if user.email and user.email.strip().casefold() == email.casefold()
    ]
    if any(user.properties.get(OWNER_PROPERTY) != owner for user in users):
        raise RuntimeError(
            "Refusing to delete a user without the expected fixture ownership marker"
        )
    if known_user_id is not None and not any(user.id == known_user_id for user in users):
        raise RuntimeError(f"Cannot find fixture user {known_user_id} for cleanup")

    mappings: List[_MappingWithId] = []
    skip = 0
    while users:
        params: Dict[str, Union[str, int]] = {"type": "user-id", "take": PAGE_SIZE, "skip": skip}
        response = session.get(
            f"{base_url}/niuser/v1/auth-mappings",
            params=params,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        page = _MappingPage.model_validate(response.json())
        mappings.extend(page.auth_mappings)
        if len(page.auth_mappings) < PAGE_SIZE:
            break
        skip += len(page.auth_mappings)

    user_ids = {user.id for user in users}
    for mapping in mappings:
        if (
            mapping.type == "user-id"
            and mapping.selector.key == "user-id"
            and mapping.selector.value in user_ids
        ):
            response = session.delete(
                f"{base_url}/niuser/v1/auth-mappings/{mapping.id}", timeout=REQUEST_TIMEOUT_SECONDS
            )
            response.raise_for_status()
    for user in users:
        response = session.delete(
            f"{base_url}/niuser/v1/users/{user.id}", timeout=REQUEST_TIMEOUT_SECONDS
        )
        response.raise_for_status()
