"""Tests for migration user discovery and writes."""

from pathlib import Path
from types import SimpleNamespace
from typing import Dict, Iterator, List, Optional, Tuple
from unittest.mock import MagicMock

import click
import pytest
import requests
from prefect.settings import temporary_settings
from prefect.testing.utilities import prefect_test_harness

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
    _ReviewedUser,
    _UserReview,
    apply_user_migrations,
    discover_user_candidates,
    review_users_task,
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


@pytest.mark.parametrize("include_inactive", [False, True])
def test_user_query_follows_continuation_tokens(include_inactive: bool) -> None:
    """Source and destination queries return all requested users across pages."""
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

    users = client.query_users(include_inactive=include_inactive)

    assert [user.id for user in users] == ["user-1", "user-2"]
    assert users[0].first_name == "Alex"
    expected: Dict[str, object] = {"take": 100}
    if not include_inactive:
        expected["filter"] = 'status = "active"'
    assert session.post.call_args_list[0].kwargs["json"] == expected
    assert session.post.call_args_list[1].kwargs["json"]["continuationToken"] == "next"
    assert ("filter" in session.post.call_args_list[1].kwargs["json"]) is not include_inactive


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
        self.user_query_options: List[bool] = []
        self.created_users: List[Tuple[MigrationUser, str]] = []
        self.created_mappings: List[Tuple[str, str, str]] = []

    def query_users(self, include_inactive: bool = False) -> List[MigrationUser]:
        self.user_query_options.append(include_inactive)
        return self.users

    def query_policies(self) -> List[_Policy]:
        return self.policies

    def query_auth_mappings(self) -> List[_AuthMapping]:
        return self.mappings

    def collaborator_template_id(self) -> Optional[str]:
        return self.template_id

    def create_user(self, source_user: MigrationUser, email: str) -> str:
        self.created_users.append((source_user, email))
        self.users.append(MigrationUser(id="created-user", type="user", email=email))
        return "created-user"

    def create_auth_mapping(self, user_id: str, workspace_id: str, template_id: str) -> None:
        self.created_mappings.append((user_id, workspace_id, template_id))
        self.mappings.append(
            _AuthMapping(
                type="user-id",
                selector=_AuthMappingSelector(key="user-id", value=user_id),
                workspace=workspace_id,
            )
        )


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


def _patch_clients(
    monkeypatch: pytest.MonkeyPatch,
    source: _FakeClient,
    destination: _FakeClient,
    selected_ids: List[str],
) -> None:
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


def _review(
    monkeypatch: pytest.MonkeyPatch,
    source: _FakeClient,
    destination: _FakeClient,
    selected_ids: List[str],
    mapping: Optional[WorkspaceMapping] = None,
) -> _UserReview:
    _patch_clients(monkeypatch, source, destination, selected_ids)
    return review_users_task.fn("source", mapping if mapping is not None else _mapping())


def _run_migration(
    monkeypatch: pytest.MonkeyPatch,
    source: _FakeClient,
    destination: _FakeClient,
    selected_ids: List[str],
    mapping: Optional[WorkspaceMapping] = None,
) -> int:
    review = _review(monkeypatch, source, destination, selected_ids, mapping)
    return apply_user_migrations("destination", review)


@pytest.fixture
def prefect_results(tmp_path: Path) -> Iterator[None]:
    """Run Prefect with a per-test result store so cached reviews never leak between tests."""
    with (
        prefect_test_harness(),
        temporary_settings(updates={"results.local_storage_path": str(tmp_path / "results")}),
    ):
        yield


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
    assert source.user_query_options == [False]
    assert destination.user_query_options == [True]
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


def test_pending_destination_user_is_reused(monkeypatch: pytest.MonkeyPatch) -> None:
    """A pending email match must not be recreated or have its record changed."""
    source = _FakeClient([_source_user()], _policies())
    destination = _FakeClient(
        [
            MigrationUser.model_validate(
                {
                    "id": "pending-user",
                    "type": "user",
                    "email": "alex@example.com",
                    "status": "pending",
                }
            )
        ]
    )

    migrated = _run_migration(monkeypatch, source, destination, ["source-user"])

    assert migrated == 1
    assert destination.user_query_options == [True]
    assert destination.created_users == []
    assert destination.created_mappings == [
        ("pending-user", "destination-lab1", "collaborator-template"),
        ("pending-user", "destination-lab2", "collaborator-template"),
    ]


def test_reapplied_review_reuses_created_user_and_adds_only_missing_grants(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Re-applying a persisted review reuses the created user and writes only missing grants."""
    source = _FakeClient([_source_user()], _policies())
    destination = _FakeClient([])
    create_mapping = destination.create_auth_mapping

    def fail_second_mapping(user_id: str, workspace_id: str, template_id: str) -> None:
        if workspace_id == "destination-lab2":
            raise requests.ConnectionError("interrupted")
        create_mapping(user_id, workspace_id, template_id)

    monkeypatch.setattr(destination, "create_auth_mapping", fail_second_mapping)
    review = _review(monkeypatch, source, destination, ["source-user"])
    with pytest.raises(requests.ConnectionError):
        apply_user_migrations("destination", review)

    monkeypatch.setattr(destination, "create_auth_mapping", create_mapping)
    apply_user_migrations("destination", review)

    assert destination.created_users == [(_source_user(), "Alex@example.com")]
    assert destination.created_mappings == [
        ("created-user", "destination-lab1", "collaborator-template"),
        ("created-user", "destination-lab2", "collaborator-template"),
    ]


def test_review_is_persisted_and_reused_across_flow_runs(
    monkeypatch: pytest.MonkeyPatch, prefect_results: None
) -> None:
    """The reviewed users are a Prefect result, so the same inputs never re-query or re-prompt."""
    source = _FakeClient([_source_user()], _policies())
    destination = _FakeClient([])
    monkeypatch.setattr(
        "slcli.migration.users.click.prompt", lambda *_args, **_kwargs: "supplied@example.com"
    )
    _patch_clients(monkeypatch, source, destination, ["source-user"])

    first = review_users_task("source", _mapping())
    monkeypatch.setattr(
        "slcli.migration.users._select_users",
        lambda *_args: pytest.fail("A persisted review must not be repeated"),
    )
    second = review_users_task("source", _mapping())

    assert second == first
    assert source.user_query_options == [False]


def test_user_review_rejects_duplicate_source_ids() -> None:
    """A persisted review cannot describe the same source user twice."""
    reviewed = _ReviewedUser(user=_source_user(), workspaces=(), email="alex@example.com")

    with pytest.raises(ValueError, match="duplicate source IDs"):
        _UserReview(users=[reviewed, reviewed])


def test_resume_reconciles_user_created_before_lost_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A user created before a lost response is found by email rather than recreated."""
    source = _FakeClient([_source_user()], _policies())
    destination = _FakeClient([])
    create_user = destination.create_user

    def create_then_fail(user: MigrationUser, email: str) -> str:
        create_user(user, email)
        raise requests.ConnectionError("response lost")

    monkeypatch.setattr(destination, "create_user", create_then_fail)
    review = _review(monkeypatch, source, destination, ["source-user"])
    with pytest.raises(requests.ConnectionError):
        apply_user_migrations("destination", review)
    monkeypatch.setattr(destination, "create_user", create_user)
    apply_user_migrations("destination", review)
    assert len(destination.created_users) == 1
    assert len(destination.created_mappings) == 2


def test_resume_reconciles_grant_created_before_lost_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A successful grant with a lost response is found even if user lookup lags."""
    source = _FakeClient([_source_user()], _policies())
    destination = _FakeClient([])
    create_mapping = destination.create_auth_mapping

    def create_then_fail(user_id: str, workspace_id: str, template_id: str) -> None:
        create_mapping(user_id, workspace_id, template_id)
        raise requests.ConnectionError("response lost")

    monkeypatch.setattr(destination, "create_auth_mapping", create_then_fail)
    review = _review(monkeypatch, source, destination, ["source-user"])
    with pytest.raises(requests.ConnectionError):
        apply_user_migrations("destination", review)
    monkeypatch.setattr(destination, "create_auth_mapping", create_mapping)
    apply_user_migrations("destination", review)
    assert destination.created_mappings == [
        ("created-user", "destination-lab1", "collaborator-template"),
        ("created-user", "destination-lab2", "collaborator-template"),
    ]


@pytest.mark.parametrize(
    ("existing", "already_mapped"), [(False, False), (True, False), (True, True)]
)
def test_shared_destination_gets_only_one_user_mapping(
    monkeypatch: pytest.MonkeyPatch, existing: bool, already_mapped: bool
) -> None:
    """Multiple source workspaces mapping to one destination produce one grant."""
    source = _FakeClient([_source_user()], _policies())
    destination = _FakeClient(
        (
            [MigrationUser(id="existing-user", type="user", email="alex@example.com")]
            if existing
            else []
        ),
        mappings=(
            [
                _AuthMapping(
                    type="user-id",
                    selector=_AuthMappingSelector(key="user-id", value="existing-user"),
                    workspace="shared",
                )
            ]
            if already_mapped
            else []
        ),
    )
    shared = _mapping().model_copy(
        update={
            "workspaces": tuple(
                workspace.model_copy(update={"destination_id": "shared"})
                for workspace in _mapping().workspaces
            )
        }
    )
    migrated = _run_migration(monkeypatch, source, destination, ["source-user"], mapping=shared)

    assert migrated == 1
    assert destination.created_mappings == (
        []
        if already_mapped
        else [("existing-user" if existing else "created-user", "shared", "collaborator-template")]
    )


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

    def review_users(*_args: object) -> str:
        return "review"

    def apply_users(*_args: object) -> int:
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
    monkeypatch.setattr("slcli.migration.flows.migrate.review_users_task", review_users)
    monkeypatch.setattr("slcli.migration.flows.migrate.apply_user_migrations", apply_users)
    monkeypatch.setattr("slcli.migration.flows.migrate.transfer_files_task", _FileTransferTask())
    monkeypatch.setattr(
        "slcli.migration.flows.migrate.migrate_test_monitor_task",
        _TestMonitorTask(),
    )

    outcome = migration_flow.fn("migration", "source", "destination", None, 10, 10, discovery)

    assert events == ["workspaces", "users", "files", "test monitor"]
    assert outcome.test_monitor == migration


@pytest.mark.parametrize("failed_resource", ["files", "test monitor"])
def test_flow_resume_after_resource_failure_keeps_user_review(
    monkeypatch: pytest.MonkeyPatch, failed_resource: str, prefect_results: None
) -> None:
    """A later resource failure reuses the persisted user review on resume."""
    selected = _source_user().model_copy(update={"email": None})
    excluded = _source_user().model_copy(update={"id": "excluded", "email": "other@example.com"})
    source = _FakeClient([selected, excluded], _policies())
    destination = _FakeClient([])
    clients = {"source": source, "destination": destination}
    monkeypatch.setattr(
        "slcli.migration.users.resolve_migration_connection",
        lambda profile: MigrationConnection(profile, "https://example.com", {}),
    )
    monkeypatch.setattr(
        "slcli.migration.users.UserMigrationClient",
        lambda connection: clients[connection.profile_name],
    )
    monkeypatch.setattr(
        "slcli.migration.users.questionary.checkbox",
        lambda *_args, **_kwargs: SimpleNamespace(ask=lambda: ["source-user"]),
    )
    monkeypatch.setattr(
        "slcli.migration.users.click.prompt", lambda *_args, **_kwargs: "supplied@example.com"
    )
    monkeypatch.setattr(
        "slcli.migration.flows.migrate.synchronize_workspaces_task", lambda *_args: _mapping()
    )
    discovery = MigrationDiscovery(
        workspaces=DiscoveredWorkspaces(),
        files=FileDiscovery(),
        test_monitor=TestMonitorDiscovery(),
    )
    file_future = MagicMock()
    file_future.result.return_value = FileTransfer()
    test_future = MagicMock()
    test_future.result.return_value = TestMonitorMigration()
    failing_future = file_future if failed_resource == "files" else test_future
    failing_future.result.side_effect = [
        RuntimeError("resource failure"),
        failing_future.result.return_value,
    ]
    monkeypatch.setattr(
        "slcli.migration.flows.migrate.transfer_files_task",
        SimpleNamespace(submit=lambda *_: file_future),
    )
    monkeypatch.setattr(
        "slcli.migration.flows.migrate.migrate_test_monitor_task",
        SimpleNamespace(submit=lambda *_: test_future),
    )

    def apply() -> None:
        migration_flow.fn(
            "migration",
            "source",
            "destination",
            None,
            10,
            10,
            discovery,
        )

    with pytest.raises(RuntimeError, match="resource failure"):
        apply()

    def unexpected(*_args: object, **_kwargs: object) -> None:
        pytest.fail("A completed user review must not be repeated")

    monkeypatch.setattr("slcli.migration.users._select_users", unexpected)
    monkeypatch.setattr("slcli.migration.users.click.prompt", unexpected)
    apply()

    assert source.user_query_options == [False]
    assert destination.created_users == [(selected, "supplied@example.com")]
    assert destination.created_mappings == [
        ("created-user", "destination-lab1", "collaborator-template"),
        ("created-user", "destination-lab2", "collaborator-template"),
    ]
