"""Tests for the persisted SLS file discovery task."""

import click
import pytest

from slcli.migration.files.discovery_task import discover_files_task
from slcli.migration.files.models import FileDiscovery
from slcli.migration.testmonitor.models import WorkspaceFailure
from slcli.migration.workspaces import DiscoveredWorkspaces


def test_incomplete_migration_discovery_raises_instead_of_returning_partial_map(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A failed workspace cannot produce a cacheable partial map for migration."""
    discovery = FileDiscovery(
        workspaces=("Broken", "Lab"),
        source_to_destination_id_map={"known-file": "destination-file"},
        failures=(WorkspaceFailure(workspace="Broken", error_type="HTTPError"),),
    )
    monkeypatch.setattr(
        "slcli.migration.files.discovery_task.resolve_migration_connection",
        lambda _profile: object(),
    )
    monkeypatch.setattr(
        "slcli.migration.files.discovery_task.FilesClient",
        lambda _connection: object(),
    )
    monkeypatch.setattr(
        "slcli.migration.files.discovery_task.discover_files",
        lambda _client, _workspaces: discovery,
    )

    with pytest.raises(click.ClickException, match="Broken.*Retry the migration"):
        discover_files_task.fn(
            "migration-id", "source", DiscoveredWorkspaces(), require_complete=True
        )


def test_incomplete_discovery_can_still_be_returned_when_completeness_is_not_required(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The discovery-only flow retains its existing partial-results behavior."""
    discovery = FileDiscovery(
        failures=(WorkspaceFailure(workspace="Broken", error_type="HTTPError"),),
    )
    monkeypatch.setattr(
        "slcli.migration.files.discovery_task.resolve_migration_connection",
        lambda _profile: object(),
    )
    monkeypatch.setattr(
        "slcli.migration.files.discovery_task.FilesClient",
        lambda _connection: object(),
    )
    monkeypatch.setattr(
        "slcli.migration.files.discovery_task.discover_files",
        lambda _client, _workspaces: discovery,
    )

    assert discover_files_task.fn("migration-id", "source", DiscoveredWorkspaces()) == discovery
