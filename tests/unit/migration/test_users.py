"""Tests for migration user discovery and writes."""

from pathlib import Path
from types import SimpleNamespace
from typing import Dict, Iterator, List, Optional, Tuple
from unittest.mock import MagicMock, call

import click
import pytest
import questionary
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
from slcli.migration.users.client import (
    AuthMapping,
    AuthMappingSelector,
    Policy,
    User,
    UserMigrationClient,
)
from slcli.migration.users.discovery import discover_user_candidates
from slcli.migration.users.migration import apply_user_migrations
from slcli.migration.users.models import UserMigrationSelections, UserToMigrate
from slcli.migration.users.select import select_users
from slcli.migration.users.select_task import select_users_task
from slcli.migration.workspaces import (
    DiscoveredWorkspaces,
    MappedWorkspace,
    WorkspaceMapping,
)
from tests.e2e import test_migration_users_e2e as users_e2e


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


def test_user_selection_aligns_columns_and_preserves_selection(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Names, emails, and workspaces align even for wide characters and missing values."""
    lab1, lab2 = _mapping().workspaces
    candidates = [
        UserToMigrate(
            user=User(id="a", type="user", first_name="Alice", email="a@x"),
            workspaces=(lab1,),
        ),
        UserToMigrate(
            user=User(id="b", type="user", first_name="\u674e", email="long@example.test"),
            workspaces=(lab2,),
        ),
        UserToMigrate(user=User(id="c", type="user"), workspaces=(lab1, lab2)),
        UserToMigrate(
            user=User(id="d", type="user", first_name="\U0001f469\u200d\U0001f4bb", email="d@x"),
            workspaces=(lab1,),
        ),
    ]
    checkbox = MagicMock(return_value=SimpleNamespace(ask=lambda: [candidates[0], candidates[2]]))
    monkeypatch.setattr("slcli.migration.users.select.questionary.checkbox", checkbox)

    selected = select_users(candidates)

    choices = checkbox.call_args.kwargs["choices"]
    assert isinstance(choices[0], questionary.Separator)
    assert choices[0].title == f"  NAME{' ' * 2}  EMAIL{' ' * 13}  WORKSPACES"
    assert [choice.title for choice in choices[1:]] == [
        f"Alice   a@x{' ' * 17}Lab1",
        f"\u674e{' ' * 6}long@example.test   New Lab2",
        f"{' ' * 28}Lab1, New Lab2",
        f"\U0001f469\u200d\U0001f4bb{' ' * 4}d@x{' ' * 17}Lab1",
    ]
    assert [choice.value for choice in choices[1:]] == candidates
    assert all(choice.checked for choice in choices[1:])
    assert selected == [candidates[0], candidates[2]]


def test_user_selection_aligns_headers_with_short_values(monkeypatch: pytest.MonkeyPatch) -> None:
    """Column headers do not overflow columns containing short or missing values."""
    candidate = UserToMigrate(
        user=User(id="a", type="user", first_name="A"), workspaces=_mapping().workspaces[:1]
    )
    checkbox = MagicMock(return_value=SimpleNamespace(ask=lambda: [candidate]))
    monkeypatch.setattr("slcli.migration.users.select.questionary.checkbox", checkbox)

    select_users([candidate])

    header, choice = checkbox.call_args.kwargs["choices"]
    assert header.title == "  NAME  EMAIL  WORKSPACES"
    assert choice.title == f"A{' ' * 12}Lab1"


def test_user_selection_returns_checked_candidates(monkeypatch: pytest.MonkeyPatch) -> None:
    """Selected checkbox values are returned, while unchecked users are excluded."""
    lab1 = _mapping().workspaces[0]
    candidates = [
        UserToMigrate(user=User(id="a", type="user", email="a@x"), workspaces=(lab1,)),
        UserToMigrate(user=User(id="b", type="user", email="b@x"), workspaces=(lab1,)),
    ]
    monkeypatch.setattr(
        "slcli.migration.users.select.questionary.checkbox",
        lambda *_args, **_kwargs: SimpleNamespace(ask=lambda: [candidates[1]]),
    )

    assert select_users(candidates) == [candidates[1]]


def test_user_selection_cancellation_aborts(monkeypatch: pytest.MonkeyPatch) -> None:
    """Cancelling the checkbox aborts rather than selecting no users."""
    candidate = UserToMigrate(user=_source_user(), workspaces=_mapping().workspaces)
    monkeypatch.setattr(
        "slcli.migration.users.select.questionary.checkbox",
        lambda *_args, **_kwargs: SimpleNamespace(ask=lambda: None),
    )

    with pytest.raises(click.Abort):
        select_users([candidate])


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


def test_user_query_discovers_untyped_users_but_not_service_accounts() -> None:
    """Users without a type are eligible, while typed service accounts are excluded."""
    response = MagicMock()
    response.json.return_value = {
        "users": [
            {"id": "untyped", "policies": ["super-user"]},
            {"id": "service", "type": "service", "policies": ["super-user"]},
        ]
    }
    session = MagicMock()
    session.post.return_value = response
    client = UserMigrationClient(
        MigrationConnection("source", "https://source", {}),
        session=session,
        write_session=MagicMock(),
    )

    candidates = discover_user_candidates(
        client.query_users(),
        [Policy(id="super-user", name="Super User", built_in=True)],
        _mapping(),
    )

    assert [candidate.user.id for candidate in candidates] == ["untyped"]


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
    """All pages of user-ID auth-mappings are requested and parsed."""
    first = MagicMock()
    first.json.return_value = {
        "authMappings": [
            {
                "type": "user-id",
                "selector": {"key": "user-id", "value": f"user-{index}"},
                "workspace": "workspace-1",
            }
            for index in range(100)
        ]
    }
    second = MagicMock()
    second.json.return_value = {
        "authMappings": [
            {
                "type": "user-id",
                "selector": {"key": "user-id", "value": "last-user"},
                "workspace": "workspace-2",
            }
        ]
    }
    session = MagicMock()
    session.get.side_effect = [first, second]
    client = UserMigrationClient(
        MigrationConnection("source", "https://source", {}),
        session=session,
        write_session=MagicMock(),
    )

    mappings = client.query_auth_mappings()

    assert len(mappings) == 101
    assert mappings[0].selector.value == "user-0"
    assert mappings[-1].selector.value == "last-user"
    assert session.get.call_args_list[0].kwargs["params"] == {
        "type": "user-id",
        "take": 100,
        "skip": 0,
    }
    assert session.get.call_args_list[1].kwargs["params"] == {
        "type": "user-id",
        "take": 100,
        "skip": 100,
    }


def test_user_discovery_maps_template_policies_and_super_user() -> None:
    """Only mapped template workspaces and all Super User workspaces are eligible."""
    mapping = _mapping()
    users = [
        User(id="mapped", type="user", first_name="Alex", policies=["policy-1"]),
        User(id="super", type="user", first_name="Blair", policies=["super-user"]),
        User(id="out-of-scope", type="user", policies=["outside"]),
        User(id="service", type="service", policies=["policy-1"]),
    ]
    policies = [
        Policy(
            id="policy-1",
            name="Lab1 Contributor",
            template_id="template",
            workspace="source-lab1",
        ),
        Policy(id="outside", name="Outside", template_id="template", workspace="not-mapped"),
        Policy(id="super-user", name="Super User", built_in=True),
    ]

    candidates = discover_user_candidates(users, policies, mapping)

    assert [
        (candidate.user.id, [w.destination_name for w in candidate.workspaces])
        for candidate in candidates
    ] == [
        ("mapped", ["Lab1"]),
        ("super", ["Lab1", "New Lab2"]),
    ]


def test_user_discovery_includes_multiple_super_users() -> None:
    """Every Super User is eligible for all selected workspaces."""
    users = [
        User(id="super-1", type="user", policies=["super-user"]),
        User(id="super-2", type="user", policies=["super-user"]),
        User(id="service", type="service", policies=["super-user"]),
    ]
    policies = [Policy(id="super-user", name="Super User", built_in=True)]
    mapping = _mapping()

    candidates = discover_user_candidates(users, policies, mapping)

    assert {candidate.user.id: candidate.workspaces for candidate in candidates} == {
        "super-1": mapping.workspaces,
        "super-2": mapping.workspaces,
    }
    assert users_e2e._verify_super_users_exist(users, policies) == {"super-1", "super-2"}


def test_user_discovery_excludes_special_email_but_keeps_missing_emails() -> None:
    """A '-' email excludes special users, not users needing an email prompt."""
    users = [
        User(id="special-super", type="user", email="-", policies=["super-user"]),
        User(id="special-mapped", type="user", email=" - "),
        User(id="missing", type="user", email=None, policies=["super-user"]),
        User(id="blank", type="user", email="  ", policies=["super-user"]),
        User(id="normal", type="user", email="user@example.com", policies=["super-user"]),
    ]
    policies = [Policy(id="super-user", name="Super User", built_in=True)]
    mappings = [
        AuthMapping(
            type="user-id",
            selector=AuthMappingSelector(key="user-id", value="special-mapped"),
            workspace="source-lab1",
        )
    ]

    candidates = discover_user_candidates(users, policies, _mapping(), mappings)

    assert {candidate.user.id for candidate in candidates} == {"missing", "blank", "normal"}


def test_user_discovery_includes_explicit_source_auth_mappings() -> None:
    """Direct user-ID workspace mappings grant membership without a policy snapshot."""
    user = User(id="direct", type="user", first_name="Casey")
    auth_mapping = AuthMapping(
        type="user-id",
        selector=AuthMappingSelector(key="user-id", value="direct"),
        workspace="source-lab2",
    )

    policies = [Policy(id="super-user", name="Super User", built_in=True)]
    candidates = discover_user_candidates([user], policies, _mapping(), [auth_mapping])

    assert [
        (candidate.user.id, candidate.workspaces[0].destination_id) for candidate in candidates
    ] == [("direct", "destination-lab2")]


@pytest.mark.parametrize(
    ("mapping_type", "selector_key", "workspace"),
    [
        ("user-id", "user-id", "out-of-scope"),
        ("user-id", "user-id", None),
        ("other", "user-id", "source-lab1"),
        ("user-id", "other", "source-lab1"),
    ],
)
def test_user_discovery_ignores_out_of_scope_auth_mappings(
    mapping_type: str, selector_key: str, workspace: Optional[str]
) -> None:
    """Only direct user-ID grants in selected workspaces make a user eligible."""
    users = [User(id="ignored", type="user"), User(id="included", type="user")]
    policies = [Policy(id="super-user", name="Super User", built_in=True)]
    mappings = [
        AuthMapping(
            type=mapping_type,
            selector=AuthMappingSelector(key=selector_key, value="ignored"),
            workspace=workspace,
        ),
        AuthMapping(
            type="user-id",
            selector=AuthMappingSelector(key="user-id", value="included"),
            workspace="source-lab2",
        ),
    ]

    candidates = discover_user_candidates(users, policies, _mapping(), mappings)

    assert [(candidate.user.id, candidate.workspaces) for candidate in candidates] == [
        ("included", (_mapping().workspaces[1],))
    ]


@pytest.mark.parametrize("count", [0, 2])
def test_user_discovery_requires_exactly_one_super_user_policy(count: int) -> None:
    """Discovery rejects missing or ambiguous built-in Super User policies."""
    policies = [
        Policy(id=f"super-{index}", name="Super User", built_in=True) for index in range(count)
    ]

    with pytest.raises(ValueError, match=f"Expected exactly one super user policy, found {count}"):
        discover_user_candidates([], policies, _mapping())


def test_user_discovery_handles_policy_iterators_and_preserves_workspace_order() -> None:
    """Mixed Super User policies and direct mappings retain the workspace mapping order."""
    mapping = _mapping()
    users = [
        User(id="super", type="user", policies=["super-user", "policy-1"]),
        User(id="mapped", type="user", policies=["policy-1"]),
    ]
    policies = iter(
        [
            Policy(id="super-user", name="Super User", built_in=True),
            Policy(
                id="policy-1",
                name="Lab1",
                template_id="template",
                workspace="source-lab1",
            ),
        ]
    )
    auth_mapping = AuthMapping(
        type="user-id",
        selector=AuthMappingSelector(key="user-id", value="mapped"),
        workspace="source-lab2",
    )

    candidates = discover_user_candidates(users, policies, mapping, [auth_mapping])

    assert {candidate.user.id: candidate.workspaces for candidate in candidates} == {
        "super": mapping.workspaces,
        "mapped": mapping.workspaces,
    }


class _FakeClient:
    def __init__(
        self,
        users: List[User],
        policies: Optional[List[Policy]] = None,
        mappings: Optional[List[AuthMapping]] = None,
        template_id: Optional[str] = "collaborator-template",
    ) -> None:
        self.users = users
        self.policies = policies or []
        self.mappings = mappings or []
        self.template_id = template_id
        self.readonly = False
        self.user_query_options: List[bool] = []
        self.created_users: List[User] = []
        self.created_mappings: List[Tuple[str, str, str]] = []

    def query_users(self, include_inactive: bool = False) -> List[User]:
        self.user_query_options.append(include_inactive)
        return self.users

    def query_policies(self) -> List[Policy]:
        return self.policies

    def query_auth_mappings(self) -> List[AuthMapping]:
        return self.mappings

    def collaborator_template_id(self) -> Optional[str]:
        return self.template_id

    def create_user(self, source_user: User) -> str:
        self.created_users.append(source_user)
        self.users.append(User(id="created-user", type="user", email=source_user.email))
        return "created-user"

    def create_auth_mapping(self, user_id: str, workspace_id: str, template_id: str) -> None:
        self.created_mappings.append((user_id, workspace_id, template_id))
        self.mappings.append(
            AuthMapping(
                type="user-id",
                selector=AuthMappingSelector(key="user-id", value=user_id),
                workspace=workspace_id,
            )
        )


def _source_user() -> User:
    return User(
        id="source-user",
        type="user",
        first_name="Alex",
        last_name="Johnson",
        email="Alex@example.com",
        keywords=["operator"],
        properties={"department": "test"},
        policies=["policy-1", "policy-2"],
    )


def _policies() -> List[Policy]:
    return [
        Policy(id="super-user", name="Super User", built_in=True),
        Policy(
            id="policy-1",
            name="Lab1",
            template_id="source-template",
            workspace="source-lab1",
        ),
        Policy(
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
    clients = {"source": source, "destination": destination}
    for module in ("select_task", "migration"):
        monkeypatch.setattr(
            f"slcli.migration.users.{module}.resolve_migration_connection",
            lambda profile: (source_connection if profile == "source" else destination_connection),
        )
        monkeypatch.setattr(
            f"slcli.migration.users.{module}.UserMigrationClient",
            lambda connection: clients[connection.profile_name],
        )

    def checkbox(
        _message: str, *, choices: List[questionary.Choice], instruction: str
    ) -> SimpleNamespace:
        return SimpleNamespace(
            ask=lambda: [
                choice.value
                for choice in choices
                if not isinstance(choice, questionary.Separator)
                and isinstance(choice.value, UserToMigrate)
                and choice.value.user.id in selected_ids
            ]
        )

    monkeypatch.setattr("slcli.migration.users.select.questionary.checkbox", checkbox)


def _review(
    monkeypatch: pytest.MonkeyPatch,
    source: _FakeClient,
    destination: _FakeClient,
    selected_ids: List[str],
    mapping: Optional[WorkspaceMapping] = None,
) -> UserMigrationSelections:
    _patch_clients(monkeypatch, source, destination, selected_ids)
    return select_users_task.fn("source", mapping if mapping is not None else _mapping())


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
            User(
                id="destination-user",
                type="user",
                email="alex@EXAMPLE.com",
                first_name="Keep",
            )
        ],
        mappings=[
            AuthMapping(
                type="user-id",
                selector=AuthMappingSelector(key="user-id", value="destination-user"),
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
    assert destination.created_users == [_source_user()]
    assert destination.created_mappings == [
        ("created-user", "destination-lab1", "collaborator-template"),
        ("created-user", "destination-lab2", "collaborator-template"),
    ]


def test_pending_destination_user_is_reused(monkeypatch: pytest.MonkeyPatch) -> None:
    """A pending email match must not be recreated or have its record changed."""
    source = _FakeClient([_source_user()], _policies())
    destination = _FakeClient(
        [
            User.model_validate(
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

    assert destination.created_users == [_source_user()]
    assert destination.created_mappings == [
        ("created-user", "destination-lab1", "collaborator-template"),
        ("created-user", "destination-lab2", "collaborator-template"),
    ]


def test_review_is_persisted_and_reused_across_flow_runs(
    monkeypatch: pytest.MonkeyPatch, prefect_results: None
) -> None:
    """The reviewed users are a Prefect result, so the same inputs never re-query or re-prompt."""
    source = _FakeClient([_source_user().model_copy(update={"email": None})], _policies())
    destination = _FakeClient([])
    prompt = MagicMock(return_value="supplied@example.com")
    monkeypatch.setattr(
        "slcli.migration.users.select.click.prompt",
        prompt,
    )
    _patch_clients(monkeypatch, source, destination, ["source-user"])

    first = select_users_task("source", _mapping())
    monkeypatch.setattr(
        "slcli.migration.users.select_task.select_users",
        lambda *_args: pytest.fail("A persisted review must not be repeated"),
    )
    second = select_users_task("source", _mapping())

    assert second == first
    assert [user.user.id for user in first.users] == ["source-user"]
    assert first.users[0].user.email == "supplied@example.com"
    prompt.assert_called_once()
    assert source.user_query_options == [False]


def test_user_review_rejects_duplicate_source_ids() -> None:
    """A persisted review cannot describe the same source user twice."""
    reviewed = UserToMigrate(user=_source_user(), workspaces=())

    with pytest.raises(ValueError, match="duplicate source IDs"):
        UserMigrationSelections(users=[reviewed, reviewed])


def test_resume_reconciles_user_created_before_lost_response(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A user created before a lost response is found by email rather than recreated."""
    source = _FakeClient([_source_user()], _policies())
    destination = _FakeClient([])
    create_user = destination.create_user

    def create_then_fail(user: User) -> str:
        create_user(user)
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
        ([User(id="existing-user", type="user", email="alex@example.com")] if existing else []),
        mappings=(
            [
                AuthMapping(
                    type="user-id",
                    selector=AuthMappingSelector(key="user-id", value="existing-user"),
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
    monkeypatch.setattr("slcli.migration.users.select.click.prompt", lambda *_args, **_kwargs: "")

    migrated = _run_migration(monkeypatch, source, destination, ["source-user"])

    assert migrated == 0
    assert destination.user_query_options == []
    assert destination.created_users == []
    assert destination.created_mappings == []


def test_selection_persists_only_users_with_resolved_emails(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Skipping one missing email retains the other selected user."""
    missing = _source_user().model_copy(update={"email": None})
    retained = _source_user().model_copy(update={"id": "retained"})
    source = _FakeClient([missing, retained], _policies())
    destination = _FakeClient([])
    _patch_clients(monkeypatch, source, destination, [])
    monkeypatch.setattr(
        "slcli.migration.users.select_task.select_users", lambda candidates: candidates
    )
    monkeypatch.setattr("slcli.migration.users.select.click.prompt", lambda *_args, **_kwargs: "")

    selections = select_users_task.fn("source", _mapping())

    assert [user.user.id for user in selections.users] == ["retained"]


def test_selection_drops_user_when_missing_email_is_skipped(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Skipping the only missing email persists an empty selection."""
    missing = _source_user().model_copy(update={"email": None})
    source = _FakeClient([missing], _policies())
    _patch_clients(monkeypatch, source, _FakeClient([]), [])
    monkeypatch.setattr(
        "slcli.migration.users.select_task.select_users", lambda candidates: candidates
    )
    monkeypatch.setattr("slcli.migration.users.select.click.prompt", lambda *_args, **_kwargs: "")

    assert select_users_task.fn("source", _mapping()).users == []


def test_selection_persists_supplied_email(monkeypatch: pytest.MonkeyPatch) -> None:
    """A supplied email is normalized and saved with the selected user."""
    missing = _source_user().model_copy(update={"email": None})
    source = _FakeClient([missing], _policies())
    _patch_clients(monkeypatch, source, _FakeClient([]), [])
    monkeypatch.setattr(
        "slcli.migration.users.select_task.select_users", lambda candidates: candidates
    )
    monkeypatch.setattr(
        "slcli.migration.users.select.click.prompt",
        lambda *_args, **_kwargs: " supplied@example.com ",
    )

    selections = select_users_task.fn("source", _mapping())

    assert len(selections.users) == 1
    assert selections.users[0].user.email == "supplied@example.com"
    assert missing.email is None


def test_existing_destination_grants_use_destination_user_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An existing destination grant is not recreated when user IDs differ."""
    source = _FakeClient([], _policies())
    destination = _FakeClient(
        [User(id="destination-user", type="user", email="Alex@example.com")],
        mappings=[
            AuthMapping(
                type="user-id",
                selector=AuthMappingSelector(key="user-id", value="destination-user"),
                workspace="destination-lab1",
            )
        ],
    )
    _patch_clients(monkeypatch, source, destination, [])
    selections = UserMigrationSelections(
        users=[UserToMigrate(user=_source_user(), workspaces=_mapping().workspaces)]
    )

    assert apply_user_migrations("destination", selections) == 1
    assert destination.created_users == []
    assert destination.created_mappings == [
        ("destination-user", "destination-lab2", "collaborator-template")
    ]


@pytest.mark.parametrize(
    ("source_email", "destination_email"),
    [
        ("Alex@example.com", " alex@EXAMPLE.com "),
        (" STRASSE@example.com ", "stra\u00dfe@example.com"),
    ],
)
def test_destination_email_match_ignores_case_and_whitespace(
    monkeypatch: pytest.MonkeyPatch, source_email: str, destination_email: str
) -> None:
    """A differently formatted destination email still identifies the existing user."""
    destination = _FakeClient([User(id="destination-user", type="user", email=destination_email)])
    _patch_clients(monkeypatch, _FakeClient([], _policies()), destination, [])
    selections = UserMigrationSelections(
        users=[
            UserToMigrate(
                user=_source_user().model_copy(update={"email": source_email}),
                workspaces=_mapping().workspaces,
            )
        ]
    )

    assert apply_user_migrations("destination", selections) == 1
    assert destination.created_users == []
    assert destination.created_mappings == [
        ("destination-user", "destination-lab1", "collaborator-template"),
        ("destination-user", "destination-lab2", "collaborator-template"),
    ]


@pytest.mark.parametrize("second_email", ["Alex@example.com", " alex@EXAMPLE.com "])
def test_ambiguous_destination_email_skips_only_matching_user(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], second_email: str
) -> None:
    """Ambiguous matches are skipped; uniquely matched and new users still migrate."""
    destination = _FakeClient(
        [
            User(id="duplicate-1", type="user", email="Alex@example.com"),
            User(id="duplicate-2", type="user", email=second_email),
            User(id="unique", type="user", email="unique@example.com"),
        ]
    )
    _patch_clients(monkeypatch, _FakeClient([]), destination, [])
    selections = UserMigrationSelections(
        users=[
            UserToMigrate(user=_source_user(), workspaces=_mapping().workspaces),
            UserToMigrate(
                user=_source_user().model_copy(
                    update={"id": "unique-source", "email": "unique@example.com"}
                ),
                workspaces=_mapping().workspaces[:1],
            ),
            UserToMigrate(
                user=_source_user().model_copy(
                    update={"id": "new-source", "email": "new@example.com"}
                ),
                workspaces=_mapping().workspaces[:1],
            ),
        ]
    )

    assert apply_user_migrations("destination", selections) == 2
    assert [user.email for user in destination.created_users] == ["new@example.com"]
    assert destination.created_mappings == [
        ("unique", "destination-lab1", "collaborator-template"),
        ("created-user", "destination-lab1", "collaborator-template"),
    ]
    assert "Skipping user 'Alex@example.com'" in capsys.readouterr().err


def test_unrelated_duplicate_destination_emails_do_not_block_migration(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """Duplicates unrelated to selected users neither block migration nor warn."""
    destination = _FakeClient(
        [
            User(id="duplicate-1", type="user", email="other@example.com"),
            User(id="duplicate-2", type="user", email=" OTHER@example.com "),
            User(id="existing", type="user", email="alex@example.com"),
        ]
    )
    _patch_clients(monkeypatch, _FakeClient([]), destination, [])
    selections = UserMigrationSelections(
        users=[UserToMigrate(user=_source_user(), workspaces=_mapping().workspaces[:1])]
    )

    assert apply_user_migrations("destination", selections) == 1
    assert destination.created_users == []
    assert destination.created_mappings == [
        ("existing", "destination-lab1", "collaborator-template")
    ]
    assert capsys.readouterr().err == ""


def test_all_ambiguous_users_are_skipped_without_writes(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """An entirely ambiguous selection requires no destination writes or template."""
    destination = _FakeClient(
        [
            User(id="duplicate-1", type="user", email="alex@example.com"),
            User(id="duplicate-2", type="user", email="alex@example.com"),
        ],
        template_id=None,
    )
    _patch_clients(monkeypatch, _FakeClient([]), destination, [])
    selections = UserMigrationSelections(
        users=[UserToMigrate(user=_source_user(), workspaces=_mapping().workspaces)]
    )

    assert apply_user_migrations("destination", selections) == 0
    assert destination.created_users == []
    assert destination.created_mappings == []
    assert "Skipping user 'Alex@example.com'" in capsys.readouterr().err


def test_deselected_user_is_not_migrated(monkeypatch: pytest.MonkeyPatch) -> None:
    """Unchecking an eligible source user excludes it from destination writes."""
    source = _FakeClient([_source_user()], _policies())
    destination = _FakeClient([])

    migrated = _run_migration(monkeypatch, source, destination, [])

    assert migrated == 0
    assert destination.created_users == []
    assert destination.created_mappings == []


def test_missing_collaborator_template_aborts_before_writes(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A missing Collaborator template leaves the destination unchanged."""
    source = _FakeClient([_source_user()], _policies())
    destination = _FakeClient([], template_id=None)

    with pytest.raises(click.Abort):
        _run_migration(monkeypatch, source, destination, ["source-user"])

    assert destination.created_users == []
    assert destination.created_mappings == []


def test_user_creation_uses_email_for_niua_id_and_preserves_metadata() -> None:
    """The User Service payload carries migration fields and uses email as niuaId."""
    connection = MigrationConnection("destination", "https://destination", {})
    write_session = MagicMock()
    write_session.post.return_value.json.return_value = {"id": "created-id"}
    client = UserMigrationClient(connection, MagicMock(), write_session)

    user_id = client.create_user(_source_user())

    assert user_id == "created-id"
    assert write_session.post.call_args.kwargs["json"] == {
        "type": "user",
        "firstName": "Alex",
        "lastName": "Johnson",
        "email": "Alex@example.com",
        "phone": "",
        "niuaId": "Alex@example.com",
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
        client.create_user(_source_user())

    write_session.post.assert_not_called()


@pytest.mark.parametrize("existing", [False, True])
def test_readonly_migration_preflight_rejects_writes(
    monkeypatch: pytest.MonkeyPatch, existing: bool
) -> None:
    """Read-only preflight rejects both user creation and missing grants before writes."""
    connection = MigrationConnection("destination", "https://destination", {}, readonly=True)
    write_session = MagicMock()
    client = UserMigrationClient(connection, MagicMock(), write_session)
    destination_users = (
        [User(id="destination-user", type="user", email="Alex@example.com")] if existing else []
    )
    monkeypatch.setattr(client, "query_users", lambda **_kwargs: destination_users)
    monkeypatch.setattr(client, "query_auth_mappings", lambda: [])
    template = MagicMock(return_value="collaborator-template")
    monkeypatch.setattr(client, "collaborator_template_id", template)
    monkeypatch.setattr(
        "slcli.migration.users.migration.resolve_migration_connection", lambda _profile: connection
    )
    monkeypatch.setattr("slcli.migration.users.migration.UserMigrationClient", lambda _conn: client)
    selections = UserMigrationSelections(
        users=[UserToMigrate(user=_source_user(), workspaces=_mapping().workspaces)]
    )

    with pytest.raises(click.ClickException, match="readonly mode"):
        apply_user_migrations("destination", selections)

    template.assert_not_called()
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


def test_e2e_cleanup_deletes_owned_grants_before_user() -> None:
    """Cleanup follows mapping pages and deletes only the fixture user's grants."""
    client = MagicMock()
    client.query_users.return_value = [
        User(
            id="fixture-user",
            type="user",
            email="fixture@example.invalid",
            properties={users_e2e.OWNER_PROPERTY: "fixture-owner"},
        )
    ]
    first = MagicMock()
    first.json.return_value = {
        "authMappings": [
            {
                "id": f"unrelated-{index}",
                "type": "user-id",
                "selector": {"key": "user-id", "value": "another-user"},
                "workspace": "workspace",
            }
            for index in range(100)
        ]
    }
    second = MagicMock()
    second.json.return_value = {
        "authMappings": [
            {
                "id": "fixture-grant",
                "type": "user-id",
                "selector": {"key": "user-id", "value": "fixture-user"},
                "workspace": "workspace",
            },
            {
                "id": "other-workspace",
                "type": "user-id",
                "selector": {"key": "user-id", "value": "fixture-user"},
                "workspace": "other",
            },
        ]
    }
    session = MagicMock()
    session.get.side_effect = [first, second]

    users_e2e._cleanup_user(
        client, session, "https://destination", "fixture@example.invalid", "fixture-owner"
    )

    assert session.get.call_args_list[1].kwargs["params"]["skip"] == 100
    assert session.delete.call_args_list == [
        call(
            "https://destination/niuser/v1/auth-mappings/fixture-grant",
            timeout=users_e2e.REQUEST_TIMEOUT_SECONDS,
        ),
        call(
            "https://destination/niuser/v1/auth-mappings/other-workspace",
            timeout=users_e2e.REQUEST_TIMEOUT_SECONDS,
        ),
        call(
            "https://destination/niuser/v1/users/fixture-user",
            timeout=users_e2e.REQUEST_TIMEOUT_SECONDS,
        ),
    ]


def test_e2e_cleanup_refuses_unowned_user() -> None:
    """An email match without the test's ownership marker is never deleted."""
    client = MagicMock()
    client.query_users.return_value = [
        User(id="unowned", type="user", email="fixture@example.invalid")
    ]
    session = MagicMock()

    with pytest.raises(RuntimeError, match="ownership marker"):
        users_e2e._cleanup_user(
            client,
            session,
            "https://destination",
            "fixture@example.invalid",
            "fixture-owner",
        )

    session.get.assert_not_called()
    session.delete.assert_not_called()


def test_e2e_cleanup_reports_missing_known_user() -> None:
    """Cleanup does not silently succeed if a previously observed fixture user disappears."""
    client = MagicMock()
    client.query_users.return_value = []
    session = MagicMock()

    with pytest.raises(RuntimeError, match="Cannot find fixture user fixture-user"):
        users_e2e._cleanup_user(
            client,
            session,
            "https://destination",
            "fixture@example.invalid",
            "fixture-owner",
            "fixture-user",
        )

    session.delete.assert_not_called()


def test_e2e_cleanup_surfaces_grant_deletion_failure() -> None:
    """A failed grant deletion leaves the user available for cleanup and reports the error."""
    client = MagicMock()
    client.query_users.return_value = [
        User(
            id="fixture-user",
            type="user",
            email="fixture@example.invalid",
            properties={users_e2e.OWNER_PROPERTY: "fixture-owner"},
        )
    ]
    session = MagicMock()
    session.get.return_value.json.return_value = {
        "authMappings": [
            {
                "id": "fixture-grant",
                "type": "user-id",
                "selector": {"key": "user-id", "value": "fixture-user"},
                "workspace": "workspace",
            }
        ]
    }
    session.delete.return_value.raise_for_status.side_effect = requests.HTTPError("delete failed")

    with pytest.raises(requests.HTTPError, match="delete failed"):
        users_e2e._cleanup_user(
            client,
            session,
            "https://destination",
            "fixture@example.invalid",
            "fixture-owner",
        )

    session.delete.assert_called_once_with(
        "https://destination/niuser/v1/auth-mappings/fixture-grant",
        timeout=users_e2e.REQUEST_TIMEOUT_SECONDS,
    )


def test_e2e_cleanup_runs_after_migration_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """A failed or ambiguous migration response still triggers ownership-scoped cleanup."""
    connection = MigrationConnection("destination", "https://destination", {})
    monkeypatch.setattr(
        users_e2e,
        "resolve_endpoints",
        lambda: SimpleNamespace(
            destination=connection,
            destination_workspace="Lab",
            destination_workspace_id="workspace",
        ),
    )
    client = MagicMock()
    client.query_users.return_value = []
    monkeypatch.setattr(users_e2e, "UserMigrationClient", lambda _connection: client)
    monkeypatch.setattr(
        users_e2e,
        "apply_user_migrations",
        MagicMock(side_effect=requests.ConnectionError("response lost")),
    )
    cleanup = MagicMock()
    monkeypatch.setattr(users_e2e, "_cleanup_user", cleanup)

    with pytest.raises(requests.ConnectionError, match="response lost"):
        users_e2e.test_migrate_user_and_create_auth_mapping()

    cleanup.assert_called_once()


def test_empty_mapping_discovers_no_users() -> None:
    """An empty workspace migration cannot select any users."""
    assert discover_user_candidates([_source_user()], _policies(), WorkspaceMapping()) == []


def test_flow_reviews_users_after_workspace_synchronization(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Workspace synchronization and review finish before any tasks are submitted."""
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
    users_future = MagicMock()

    def synchronize(*_args: object) -> WorkspaceMapping:
        events.append("workspaces")
        return WorkspaceMapping()

    def review_users(*_args: object) -> str:
        events.append("review")
        return "review"

    class _UsersTask:
        def submit(self, *_args: object) -> MagicMock:
            events.append("users")
            return users_future

    class _TestMonitorTask:
        def submit(self, *_args: object, **_kwargs: object) -> MagicMock:
            events.append("test monitor")
            return future

    class _FileTransferTask:
        def submit(self, *_args: object, **_kwargs: object) -> MagicMock:
            events.append("files")
            return file_future

    monkeypatch.setattr("slcli.migration.flows.migrate.synchronize_workspaces_task", synchronize)
    monkeypatch.setattr("slcli.migration.flows.migrate.select_users_task", review_users)
    monkeypatch.setattr("slcli.migration.flows.migrate.migrate_users_task", _UsersTask())
    monkeypatch.setattr("slcli.migration.flows.migrate.transfer_files_task", _FileTransferTask())
    monkeypatch.setattr(
        "slcli.migration.flows.migrate.migrate_test_monitor_task",
        _TestMonitorTask(),
    )

    outcome = migration_flow.fn("migration", "source", "destination", None, 10, 10, discovery)

    assert events == ["workspaces", "review", "users", "files", "test monitor"]
    users_future.result.assert_called_once()
    assert outcome.test_monitor == migration


def test_flow_does_not_start_migrations_if_review_aborts(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An aborted review leaves all three migrations unstarted."""
    monkeypatch.setattr(
        "slcli.migration.flows.migrate.synchronize_workspaces_task", lambda *_args: _mapping()
    )
    review = MagicMock(side_effect=click.Abort())
    users, files, test_monitor = MagicMock(), MagicMock(), MagicMock()
    monkeypatch.setattr("slcli.migration.flows.migrate.select_users_task", review)
    monkeypatch.setattr("slcli.migration.flows.migrate.migrate_users_task", users)
    monkeypatch.setattr("slcli.migration.flows.migrate.transfer_files_task", files)
    monkeypatch.setattr("slcli.migration.flows.migrate.migrate_test_monitor_task", test_monitor)
    discovery = MigrationDiscovery(
        workspaces=DiscoveredWorkspaces(),
        files=FileDiscovery(),
        test_monitor=TestMonitorDiscovery(),
    )

    with pytest.raises(click.Abort):
        migration_flow.fn("migration", "source", "destination", None, 10, 10, discovery)

    users.submit.assert_not_called()
    files.submit.assert_not_called()
    test_monitor.submit.assert_not_called()


def test_flow_reports_first_failure_without_joining_later_migrations(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A failure is reported and propagated without joining later futures."""
    monkeypatch.setattr(
        "slcli.migration.flows.migrate.synchronize_workspaces_task", lambda *_args: _mapping()
    )
    monkeypatch.setattr("slcli.migration.flows.migrate.select_users_task", lambda *_args: "review")
    users, files, test_monitor = MagicMock(), MagicMock(), MagicMock()
    users.state.is_completed.return_value = False
    users.state.message = "users failed"
    users.result.side_effect = RuntimeError("users failed")
    files.state.is_completed.return_value = False
    files.state.message = "files failed"
    monkeypatch.setattr(
        "slcli.migration.flows.migrate.migrate_users_task", SimpleNamespace(submit=lambda *_: users)
    )
    monkeypatch.setattr(
        "slcli.migration.flows.migrate.transfer_files_task",
        SimpleNamespace(submit=lambda *_: files),
    )
    monkeypatch.setattr(
        "slcli.migration.flows.migrate.migrate_test_monitor_task",
        SimpleNamespace(submit=lambda *_: test_monitor),
    )
    discovery = MigrationDiscovery(
        workspaces=DiscoveredWorkspaces(),
        files=FileDiscovery(),
        test_monitor=TestMonitorDiscovery(),
    )

    with pytest.raises(RuntimeError, match="users failed"):
        migration_flow.fn("migration", "source", "destination", None, 10, 10, discovery)

    users.wait.assert_called_once()
    files.wait.assert_not_called()
    test_monitor.wait.assert_not_called()
    assert "User migration failed: users failed" in caplog.text
    assert "File migration failed: files failed" not in caplog.text


@pytest.mark.parametrize("failed_resource", ["files", "test monitor"])
def test_flow_resume_after_resource_failure_keeps_user_review(
    monkeypatch: pytest.MonkeyPatch, failed_resource: str, prefect_results: None
) -> None:
    """A later resource failure reuses the persisted user review on resume."""
    selected = _source_user().model_copy(update={"email": None})
    excluded = _source_user().model_copy(update={"id": "excluded", "email": "other@example.com"})
    source = _FakeClient([selected, excluded], _policies())
    destination = _FakeClient([])
    _patch_clients(monkeypatch, source, destination, ["source-user"])
    monkeypatch.setattr(
        "slcli.migration.users.select.click.prompt",
        lambda *_args, **_kwargs: "supplied@example.com",
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
        migration_flow(
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

    monkeypatch.setattr("slcli.migration.users.select_task.select_users", unexpected)
    monkeypatch.setattr("slcli.migration.users.select.click.prompt", unexpected)
    apply()

    assert source.user_query_options == [False]
    assert destination.user_query_options == [True, True]
    assert destination.created_users == [
        selected.model_copy(update={"email": "supplied@example.com"})
    ]
    assert destination.created_mappings == [
        ("created-user", "destination-lab1", "collaborator-template"),
        ("created-user", "destination-lab2", "collaborator-template"),
    ]
