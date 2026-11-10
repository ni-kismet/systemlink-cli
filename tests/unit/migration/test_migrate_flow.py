"""Tests for the migration flow composition."""

from typing import Dict, List, Optional, Tuple

import pytest

from slcli.migration.assets.models import AssetDiscovery
from slcli.migration.flows.discover import MigrationDiscovery
from slcli.migration.flows.migrate import MigrationOutcome, migrate_flow
from slcli.migration.testmonitor.models import TestMonitorDiscovery
from slcli.migration.workspace_client import Workspace
from slcli.migration.workspaces import DiscoveredWorkspaces, MappedWorkspace, WorkspaceMapping


def test_discovers_assets_after_synchronizing_workspaces(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Asset discovery receives the resolved source-to-destination workspace mapping."""
    discovered = DiscoveredWorkspaces(
        source=(Workspace(id="source-id", name="Source"),), selected=("Source",)
    )
    discovery = MigrationDiscovery(workspaces=discovered, test_monitor=TestMonitorDiscovery())
    mapping = WorkspaceMapping(
        workspaces=(
            MappedWorkspace(
                source_name="Source",
                source_id="source-id",
                destination_name="Destination",
                destination_id="destination-id",
            ),
        )
    )
    assets = AssetDiscovery()
    calls: List[str] = []

    def discover_flow(
        migration_id: str, source_profile: str, workspaces: Optional[List[str]]
    ) -> MigrationDiscovery:
        assert (migration_id, source_profile, workspaces) == ("migration-id", "source", ["Source"])
        calls.append("source")
        return discovery

    def synchronize_workspaces_task(
        migration_id: str,
        destination_profile: str,
        task_discovered: DiscoveredWorkspaces,
        workspace_mappings: Optional[Dict[str, str]],
    ) -> WorkspaceMapping:
        assert (migration_id, destination_profile, task_discovered, workspace_mappings) == (
            "migration-id",
            "destination",
            discovered,
            {"Source": "Destination"},
        )
        calls.append("mapping")
        return mapping

    def discover_assets_task(
        migration_id: str,
        source_profile: str,
        destination_profile: str,
        task_mapping: WorkspaceMapping,
    ) -> AssetDiscovery:
        assert (migration_id, source_profile, destination_profile, task_mapping) == (
            "migration-id",
            "source",
            "destination",
            mapping,
        )
        calls.append("assets")
        return assets

    monkeypatch.setattr("slcli.migration.flows.migrate.discover_flow", discover_flow)
    monkeypatch.setattr(
        "slcli.migration.flows.migrate.synchronize_workspaces_task", synchronize_workspaces_task
    )
    monkeypatch.setattr("slcli.migration.flows.migrate.discover_assets_task", discover_assets_task)

    outcome = migrate_flow.fn("migration-id", "source", "destination", {"Source": "Destination"})

    assert outcome == MigrationOutcome(discovery=discovery, mapping=mapping, assets=assets)
    assert calls == ["source", "mapping", "assets"]
