"""Tests for the persisted Asset Service discovery task."""

import pytest

from slcli.migration.assets.discovery_task import discover_assets_task
from slcli.migration.system_client import System
from slcli.migration.workspaces import MappedWorkspace, WorkspaceMapping


class _FakeAssetClient:
    def query_assets(self) -> list[dict[str, object]]:
        return [
            {
                "id": "asset-1",
                "fileIds": ["file-1"],
                "location": {"minionId": "minion-1"},
            }
        ]


class _FakeSystemClient:
    def __init__(self, systems: list[System]) -> None:
        self._systems = systems

    def query_systems(self) -> list[System]:
        return self._systems


def test_discovers_assets_with_resolved_workspace_and_destination_systems(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The task resolves each profile and blocks files until a file map exists."""
    source_connection = object()
    destination_connection = object()
    connections = {"source": source_connection, "destination": destination_connection}
    monkeypatch.setattr(
        "slcli.migration.assets.discovery_task.resolve_migration_connection",
        lambda profile: connections[profile],
    )
    monkeypatch.setattr(
        "slcli.migration.assets.discovery_task.AssetClient", lambda connection: _FakeAssetClient()
    )
    monkeypatch.setattr(
        "slcli.migration.assets.discovery_task.SystemClient",
        lambda connection: _FakeSystemClient(
            [System(id="minion-1", workspace="source-workspace")]
            if connection is source_connection
            else [System(id="minion-1", workspace="destination-workspace")]
        ),
    )
    mapping = WorkspaceMapping(
        workspaces=(
            MappedWorkspace(
                source_name="Source",
                source_id="source-workspace",
                destination_name="Destination",
                destination_id="destination-workspace",
            ),
        )
    )

    discovery = discover_assets_task.fn("migration-id", "source", "destination", mapping)

    assert len(discovery.assets) == 1
    asset = discovery.assets[0]
    assert (asset.workspace, asset.destination_workspace) == ("Source", "Destination")
    assert asset.decision == "block"
    assert asset.block_reason == "missing destination files: file-1"
