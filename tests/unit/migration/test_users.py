"""Tests for migration user discovery and writes."""

from types import SimpleNamespace
from typing import List, Optional, Tuple
from unittest.mock import MagicMock

import click
import pytest
import requests

from slcli.migration.connection import MigrationConnection
from slcli.migration.files.models import FileDiscovery, FileTransfer
from slcli.migration.flows.migrate import migrate_flow as migration_flow
from slcli.migration.state import MigrationDiscovery
from slcli.migration.testmonitor.models import (
    TestMonitorDiscovery,
    TestMonitorMigration,
)
from slcli.migration.users import (
    MigrationUser,
    UserMigrationClient,
    _AuthMapping,
    _AuthMappingSelector,
    _Policy,
    discover_user_candidates,
    migrate_users,
)
from slcli.migration.workspaces import (
    DiscoveredWorkspaces,
    MappedWorkspace,
    WorkspaceMapping,
)


def _mapping() -> WorkspaceMapping:
    return WorkspaceMapping(
        workspaces=(
            MappedWorkspace(
                source_name="Lab1",
                source_id="source-lab1",
                destination_name="Lab1",
                destination_id="destination-lab1",
            ),
            MappedWorkspace(
                source_name="Lab2",
                source_id="source-lab2",
                destination_name="New Lab2",
                destination_id="destination-lab2",
            ),
        )
    )


def test_user_query_follows_continuation_tokens() -> None:
    """Every active user is returned across User Service pages."""
    first = MagicMock()
    first.json.return_value = {
        "users": [
            {
                "id": "user-1",
                "type": "user",
                "firstName": "Alex",
                "policies": ["policy-1"],
            }
        ],
        "continuationToken": "next",
    }
    second = MagicMock()
    second.json.return_value = {
        "users": [{"id": "user-2", "type": "user", "firstName": "Blair"}],
        "continuationToken": None,
    }
    session = MagicMock()
    session.post.side_effect = [first, second]
    client = UserMigrationClient(
        MigrationConnection("source", "https://source", {}),
        session=session,
        write_session=MagicMock(),
    )

    users = client.query_users()

    assert [user.id for user in users] == ["user-1", "user-2"]
    assert users[0].first_name == "Alex"
    assert session.post.call_args_list[0].kwargs["json"] == {
        "filter": 'status = "active"',
        "take": 100,
    }
    assert session.post.call_args_list[1].kwargs["json"]["continuationToken"] == "next"


def test_policy_query_follows_offset_pages() -> None:
    """All policy pages are read to find memberships beyond the first page."""
    first = MagicMock()
    first.json.return_value = {
        "policies": [{"id": f"policy-{index}", "name": "Policy"} for index in range(100)]
    }
    second = MagicMock()
    second.json.return_value = {"policies": [{"id": "last-policy", "name": "Last"}]}
    session = MagicMock()
    session.get.side_effect = [first, second]
    client = UserMigrationClient(
        MigrationConnection("source", "https://source", {}),
        session=session,
        write_session=MagicMock(),
    )

    policies = client.query_policies()

    assert len(policies) == 101
    assert session.get.call_args_list[1].kwargs["params"]["skip"] == 100


def test_auth_mapping_query_reads_user_id_mappings() -> None:
    """Auth-mapping results are parsed and filtered by user-ID type."""
    response = MagicMock()
    response.json.return_value = {
        "authMappings": [
            {
                "type": "user-id",
                "selector": {"key": "user-id", "value": "user-1"},
                "workspace": "workspace-1",
            }
        ]
    }
    session = MagicMock()
    session.get.return_value = response
    client = UserMigrationClient(
        MigrationConnection("source", "https://source", {}),
        session=session,
        write_session=MagicMock(),
    )

    mappings = client.query_auth_mappings()

    assert len(mappings) == 1
    assert mappings[0].selector.value == "user-1"
    assert session.get.call_args.kwargs["params"] == {
        "type": "user-id",
        "take": 100,
        "skip": 0,
    }


def test_user_discovery_maps_template_policies_and_super_user() -> None:
    """Only mapped template workspaces and all Super User workspaces are eligible."""
    mapping = _mapping()
    users = [
        MigrationUser(id="mapped", type="user", first_name="Alex", policies=["policy-1"]),
        MigrationUser(id="super", type="user", first_name="Blair", policies=["super-user"]),
        MigrationUser(id="out-of-scope", type="user", policies=["outside"]),
        MigrationUser(id="service", type="service", policies=["policy-1"]),
    ]
    policies = [
        _Policy(
            id="policy-1",
            name="Lab1 Contributor",
            template_id="template",
            workspace="source-lab1",
        ),
        _Policy(id="outside", name="Outside", template_id="template", workspace="not-mapped"),
        _Policy(id="super-user", name="Super User", built_in=True),
    ]

    candidates = discover_user_candidates(users, policies, mapping)

    assert [
        (candidate.user.id, [w.destination_name for w in candidate.workspaces])
        for candidate in candidates
    ] == [
        ("mapped", ["Lab1"]),
        ("super", ["Lab1", "New Lab2"]),
    ]


def test_user_discovery_includes_explicit_source_auth_mappings() -> None:
    """Direct user-ID workspace mappings grant membership without a policy snapshot."""
    user = MigrationUser(id="direct", type="user", first_name="Casey")
    auth_mapping = _AuthMapping(
        type="user-id",
        selector=_AuthMappingSelector(key="user-id", value="direct"),
        workspace="source-lab2",
    )

    candidates = discover_user_candidates([user], [], _mapping(), [auth_mapping])

    assert [
        (candidate.user.id, candidate.workspaces[0].destination_id) for candidate in candidates
    ] == [("direct", "destination-lab2")]


class _FakeClient:
    def __init__(
        self,
        users: List[MigrationUser],
        policies: Optional[List[_Policy]] = None,
        mappings: Optional[List[_AuthMapping]] = None,
        template_id: Optional[str] = "collaborator-template",
    ) -> None:
        self.users = users
        self.policies = policies or []
        self.mappings = mappings or []
        self.template_id = template_id
        self.readonly = False
        self.created_users: List[Tuple[MigrationUser, str]] = []
        self.created_mappings: List[Tuple[str, str, str]] = []

    def query_users(self) -> List[MigrationUser]:
        return self.users

    def query_policies(self) -> List[_Policy]:
        return self.policies

    def query_auth_mappings(self) -> List[_AuthMapping]:
        return self.mappings

    def collaborator_template_id(self) -> Optional[str]:
        return self.template_id

    def create_user(self, source_user: MigrationUser, email: str) -> str:
        self.created_users.append((source_user, email))
        return "created-user"

    def create_auth_mapping(self, user_id: str, workspace_id: str, template_id: str) -> None:
        self.created_mappings.append((user_id, workspace_id, template_id))


def _source_user() -> MigrationUser:
    return MigrationUser(
        id="source-user",
        type="user",
        first_name="Alex",
        last_name="Johnson",
        email="Alex@example.com",
        keywords=["operator"],
        properties={"department": "test"},
        policies=["policy-1", "policy-2"],
    )


def _policies() -> List[_Policy]:
    return [
        _Policy(
            id="policy-1",
            name="Lab1",
            template_id="source-template",
            workspace="source-lab1",
        ),
        _Policy(
            id="policy-2",
            name="Lab2",
            template_id="source-template",
            workspace="source-lab2",
        ),
    ]


def _run_migration(
    monkeypatch: pytest.MonkeyPatch,
    source: _FakeClient,
    destination: _FakeClient,
    selected_ids: List[str],
) -> int:
    source_connection = MigrationConnection("source", "https://source", {})
    destination_connection = MigrationConnection("destination", "https://destination", {})
    monkeypatch.setattr(
        "slcli.migration.users.resolve_migration_connection",
        lambda profile: (source_connection if profile == "source" else destination_connection),
    )
    clients = {"source": source, "destination": destination}
    monkeypatch.setattr(
        "slcli.migration.users.UserMigrationClient",
        lambda connection: clients[connection.profile_name],
    )
    monkeypatch.setattr(
        "slcli.migration.users.questionary.checkbox",
        lambda *_args, **_kwargs: SimpleNamespace(ask=lambda: selected_ids),
    )

    return migrate_users("source", "destination", _mapping())


def test_existing_destination_user_is_reused_and_only_missing_mappings_added(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Case-insensitive email matches preserve the user and add only missing access."""
    source = _FakeClient([_source_user()], _policies())
    destination = _FakeClient(
        [
            MigrationUser(
                id="destination-user",
                type="user",
                email="alex@EXAMPLE.com",
                first_name="Keep",
            )
        ],
        mappings=[
            _AuthMapping(
                type="user-id",
                selector=_AuthMappingSelector(key="user-id", value="destination-user"),
                workspace="destination-lab1",
            )
        ],
    )

    migrated = _run_migration(monkeypatch, source, destination, ["source-user"])

    assert migrated == 1
    assert destination.created_users == []
    assert destination.created_mappings == [
        ("destination-user", "destination-lab2", "collaborator-template")
    ]


def test_new_destination_user_gets_source_metadata_and_all_workspace_mappings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """New users receive source metadata and an auth-mapping for every workspace."""
    source = _FakeClient([_source_user()], _policies())
    destination = _FakeClient([])

    migrated = _run_migration(monkeypatch, source, destination, ["source-user"])

    assert migrated == 1
    assert destination.created_users == [(_source_user(), "Alex@example.com")]
    assert destination.created_mappings == [
        ("created-user", "destination-lab1", "collaborator-template"),
        ("created-user", "destination-lab2", "collaborator-template"),
    ]


def test_blank_missing_email_skips_user_without_destination_queries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing email left blank omits that user from execution."""
    source = _FakeClient([_source_user().model_copy(update={"email": None})], _policies())
    destination = _FakeClient([])
    monkeypatch.setattr("slcli.migration.users.click.prompt", lambda *_args, **_kwargs: "")

    migrated = _run_migration(monkeypatch, source, destination, ["source-user"])

    assert migrated == 0
    assert destination.created_users == []
    assert destination.created_mappings == []


def test_deselected_user_is_not_migrated(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unchecking an eligible source user excludes it from destination writes."""
    source = _FakeClient([_source_user()], _policies())
    destination = _FakeClient([])

    migrated = _run_migration(monkeypatch, source, destination, [])

    assert migrated == 0
    assert destination.created_users == []
    assert destination.created_mappings == []


def test_missing_collaborator_template_can_continue_without_mappings(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Continuing without the built-in template creates users but no permissions."""
    source = _FakeClient([_source_user()], _policies())
    destination = _FakeClient([], template_id=None)
    monkeypatch.setattr(
        "slcli.migration.users.questionary.confirm",
        lambda *_args, **_kwargs: SimpleNamespace(ask=lambda: True),
    )

    migrated = _run_migration(monkeypatch, source, destination, ["source-user"])

    assert migrated == 1
    assert destination.created_users == [(_source_user(), "Alex@example.com")]
    assert destination.created_mappings == []


def test_missing_collaborator_template_can_abort_before_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Declining to continue leaves the destination unchanged."""
    source = _FakeClient([_source_user()], _policies())
    destination = _FakeClient([], template_id=None)
    monkeypatch.setattr(
        "slcli.migration.users.questionary.confirm",
        lambda *_args, **_kwargs: SimpleNamespace(ask=lambda: False),
    )

    with pytest.raises(click.Abort):
        _run_migration(monkeypatch, source, destination, ["source-user"])

    assert destination.created_users == []
    assert destination.created_mappings == []


def test_ambiguous_destination_email_is_skipped_without_aborting_other_users(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Multiple destination matches are not overwritten or allowed to stop the migration."""
    first = _source_user()
    second = _source_user().model_copy(update={"id": "source-user-2", "email": "blair@example.com"})
    source = _FakeClient([first, second], _policies())
    destination = _FakeClient(
        [
            MigrationUser(id="destination-1", type="user", email="alex@example.com"),
            MigrationUser(id="destination-2", type="user", email="ALEX@example.com"),
        ]
    )
    monkeypatch.setattr(
        "slcli.migration.users.questionary.checkbox",
        lambda *_args, **_kwargs: SimpleNamespace(ask=lambda: ["source-user", "source-user-2"]),
    )

    migrated = _run_migration(monkeypatch, source, destination, ["source-user", "source-user-2"])

    assert migrated == 1
    assert destination.created_users == [(second, "blair@example.com")]


def test_user_creation_uses_email_for_niua_id_and_preserves_metadata() -> None:
    """The User Service payload carries migration fields and uses email as niuaId."""
    connection = MigrationConnection("destination", "https://destination", {})
    write_session = MagicMock()
    write_session.post.return_value.json.return_value = {"id": "created-id"}
    client = UserMigrationClient(connection, MagicMock(), write_session)

    user_id = client.create_user(_source_user(), "alex@example.com")

    assert user_id == "created-id"
    assert write_session.post.call_args.kwargs["json"] == {
        "type": "user",
        "firstName": "Alex",
        "lastName": "Johnson",
        "email": "alex@example.com",
        "phone": "",
        "niuaId": "alex@example.com",
        "login": "",
        "policies": [],
        "keywords": ["operator"],
        "properties": {"department": "test"},
    }


def test_auth_mapping_payload_targets_user_and_workspace() -> None:
    """Collaborator access is created as a user-ID mapping for the mapped workspace."""
    connection = MigrationConnection("destination", "https://destination", {})
    write_session = MagicMock()
    client = UserMigrationClient(connection, MagicMock(), write_session)

    client.create_auth_mapping("user-id", "workspace-id", "collaborator-template")

    assert write_session.post.call_args.args[0] == ("https://destination/niuser/v1/auth-mappings")
    assert write_session.post.call_args.kwargs["json"] == {
        "type": "user-id",
        "selector": {"key": "user-id", "value": "user-id"},
        "policyTemplateId": "collaborator-template",
        "workspace": "workspace-id",
    }


def test_readonly_destination_rejects_user_creation() -> None:
    """A read-only destination cannot create a user."""
    connection = MigrationConnection("destination", "https://destination", {}, readonly=True)
    write_session = MagicMock()
    client = UserMigrationClient(connection, MagicMock(), write_session)

    with pytest.raises(click.ClickException, match="readonly mode"):
        client.create_user(_source_user(), "alex@example.com")

    write_session.post.assert_not_called()


def test_query_http_errors_are_not_treated_as_empty_results() -> None:
    """API failures propagate rather than being interpreted as no users."""
    response = requests.Response()
    response.status_code = 403
    session = MagicMock()
    session.post.return_value = response
    client = UserMigrationClient(
        MigrationConnection("source", "https://source", {}),
        session=session,
        write_session=MagicMock(),
    )

    with pytest.raises(requests.HTTPError):
        client.query_users()


def test_empty_mapping_discovers_no_users() -> None:
    """An empty workspace migration cannot select any users."""
    assert discover_user_candidates([_source_user()], _policies(), WorkspaceMapping()) == []


def test_flow_reviews_users_after_workspace_synchronization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """User migration runs after workspace synchronization and before resource writes."""
    events: List[str] = []
    discovery = MigrationDiscovery(
        workspaces=DiscoveredWorkspaces(),
        files=FileDiscovery(),
        test_monitor=TestMonitorDiscovery(),
    )
    migration = TestMonitorMigration()
    future = MagicMock()
    future.result.return_value = migration
    file_future = MagicMock()
    file_future.result.return_value = FileTransfer()

    def synchronize(*_args: object) -> WorkspaceMapping:
        events.append("workspaces")
        return WorkspaceMapping()

    def review_users(*_args: object) -> int:
        events.append("users")
        return 0

    class _TestMonitorTask:
        def submit(self, *_args: object, **_kwargs: object) -> MagicMock:
            events.append("test monitor")
            return future

    class _FileTransferTask:
        def submit(self, *_args: object, **_kwargs: object) -> MagicMock:
            events.append("files")
            return file_future

    monkeypatch.setattr("slcli.migration.flows.migrate.synchronize_workspaces_task", synchronize)
    monkeypatch.setattr("slcli.migration.flows.migrate.migrate_users", review_users)
    monkeypatch.setattr("slcli.migration.flows.migrate.transfer_files_task", _FileTransferTask())
    monkeypatch.setattr(
        "slcli.migration.flows.migrate.migrate_test_monitor_task",
        _TestMonitorTask(),
    )

    outcome = migration_flow.fn("migration", "source", "destination", None, 10, 10, discovery)

    assert events == ["workspaces", "users", "files", "test monitor"]
    assert outcome.test_monitor == migration
