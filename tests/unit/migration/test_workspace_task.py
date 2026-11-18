"""Tests for destination workspace synchronization tasks."""

from typing import Dict, List, Optional

import pytest

from slcli.migration.workspace_client import Workspace
from slcli.migration.workspace_task import synchronize_workspaces_task
from slcli.migration.workspaces import WorkspaceMapping, WorkspaceMappingError, discover_workspaces


class _FakeWorkspaceClient:
    def __init__(self, workspaces: List[Workspace]) -> None:
        self.workspaces = workspaces
        self.created_names: List[str] = []

    def query_workspaces(self) -> List[Workspace]:
        return list(self.workspaces)

    def create_workspace(self, name: str) -> Workspace:
        self.created_names.append(name)
        workspace = Workspace(id=f"created-{name}", name=name)
        self.workspaces.append(workspace)
        return workspace


@pytest.fixture
def fake_destination_client(monkeypatch: pytest.MonkeyPatch) -> _FakeWorkspaceClient:
    client = _FakeWorkspaceClient([Workspace(id="existing-id", name="Existing")])
    monkeypatch.setattr(
        "slcli.migration.workspace_task.resolve_migration_connection", lambda _profile: object()
    )
    monkeypatch.setattr(
        "slcli.migration.workspace_task.WorkspaceClient", lambda _connection: client
    )
    return client


def test_creates_only_missing_mapped_destinations(
    fake_destination_client: _FakeWorkspaceClient,
) -> None:
    discovered = discover_workspaces(
        [Workspace(id="lab-id", name="Lab"), Workspace(id="default-id", name="Default")],
        ["Lab", "Default"],
    )

    mapping = synchronize_workspaces_task.fn(
        "migration-id", "destination", discovered, {"Lab": "New", "Default": "Existing"}
    )

    assert fake_destination_client.created_names == ["New"]
    assert [
        (workspace.destination_name, workspace.destination_id) for workspace in mapping.workspaces
    ] == [
        ("Existing", "existing-id"),
        ("New", "created-New"),
    ]


def test_creates_a_shared_destination_name_only_once(
    fake_destination_client: _FakeWorkspaceClient,
) -> None:
    discovered = discover_workspaces(
        [Workspace(id="lab-id", name="Lab"), Workspace(id="default-id", name="Default")],
        ["Lab", "Default"],
    )

    mapping = synchronize_workspaces_task.fn(
        "migration-id",
        "destination",
        discovered,
        {"Lab": "Shared", "Default": "Shared"},
    )

    assert fake_destination_client.created_names == ["Shared"]
    assert [workspace.destination_id for workspace in mapping.workspaces] == [
        "created-Shared",
        "created-Shared",
    ]


def test_creates_same_named_destination_when_mapping_is_omitted(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = _FakeWorkspaceClient([])
    monkeypatch.setattr(
        "slcli.migration.workspace_task.resolve_migration_connection", lambda _profile: object()
    )
    monkeypatch.setattr(
        "slcli.migration.workspace_task.WorkspaceClient", lambda _connection: client
    )
    discovered = discover_workspaces([Workspace(id="lab-id", name="Lab")], None)

    mapping: WorkspaceMapping = synchronize_workspaces_task.fn(
        "migration-id", "destination", discovered, None
    )

    assert client.created_names == ["Lab"]
    assert mapping.workspaces[0].destination_id == "created-Lab"


@pytest.mark.parametrize("name_mappings", [None, {"Lab": "Disabled", "Other": "New"}])
def test_rejects_disabled_destination_before_creating_missing_workspaces(
    fake_destination_client: _FakeWorkspaceClient,
    name_mappings: Optional[Dict[str, str]],
) -> None:
    disabled_name = "Disabled" if name_mappings else "Lab"
    fake_destination_client.workspaces.append(
        Workspace(id="disabled-id", name=disabled_name, enabled=False)
    )
    discovered = discover_workspaces(
        [Workspace(id="lab-id", name="Lab"), Workspace(id="other-id", name="Other")], None
    )

    with pytest.raises(WorkspaceMappingError, match="disabled destination workspace") as raised:
        synchronize_workspaces_task.fn("migration-id", "destination", discovered, name_mappings)

    assert raised.value.disabled_destination == [disabled_name]
    assert fake_destination_client.created_names == []


def test_ignores_unmapped_disabled_destination(
    fake_destination_client: _FakeWorkspaceClient,
) -> None:
    fake_destination_client.workspaces.append(
        Workspace(id="disabled-id", name="Disabled", enabled=False)
    )
    discovered = discover_workspaces([Workspace(id="lab-id", name="Lab")], None)

    mapping = synchronize_workspaces_task.fn(
        "migration-id", "destination", discovered, {"Lab": "Existing"}
    )

    assert mapping.workspaces[0].destination_id == "existing-id"
    assert fake_destination_client.created_names == []
