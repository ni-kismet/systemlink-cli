"""Prefect-backed tests for persisted migration discovery."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional

import click
import pytest

from slcli.migration.connection import MigrationConnection
from slcli.migration.files.client import FileContent, SourceFile
from slcli.migration.files.discovery_task import discover_files_task
from slcli.migration.files.models import DiscoveredFile, FileDiscovery
from slcli.migration.files.transfer import MIGRATED_SOURCE_ID
from slcli.migration.orchestration import prefect_server, run_discovery, run_migration
from slcli.migration.state import create_migration_run
from slcli.migration.testmonitor.discovery_task import discover_test_monitor_task
from slcli.migration.testmonitor.migration_task import migrate_test_monitor_task
from slcli.migration.testmonitor.models import (
    DiscoveredProduct,
    TestMonitorDiscovery,
    TestMonitorMigration,
)
from slcli.migration.workspace_client import Workspace
from slcli.migration.workspace_task import discover_workspaces_task, synchronize_workspaces_task
from slcli.migration.workspaces import (
    DiscoveredWorkspaces,
    MappedWorkspace,
    WorkspaceMapping,
    discover_workspaces,
)

# Uses a real Prefect server, so too slow for unit tests.
pytestmark = pytest.mark.e2e_migration

DISCOVERY = TestMonitorDiscovery(products=(DiscoveredProduct(id="p", workspace="Lab"),))
FILES_DISCOVERY = FileDiscovery(workspaces=("Lab",))


@dataclass
class FakeSource:
    """Records task executions in place of querying a source server."""

    fail: bool = False
    calls: List[Dict[str, object]] = field(default_factory=list)


@pytest.fixture
def fake_source(monkeypatch: pytest.MonkeyPatch) -> FakeSource:
    """Replace the discovery task bodies; Prefect still persists and caches them."""
    fake = FakeSource()

    def workspaces_discovery(
        migration_id: str, source_profile: str, names: Optional[List[str]]
    ) -> DiscoveredWorkspaces:
        source = [Workspace(id=f"{name}-id", name=name) for name in ("Default", "Lab", "Other")]
        return discover_workspaces(source, names)

    monkeypatch.setattr(discover_workspaces_task, "fn", workspaces_discovery)

    def test_monitor_discovery(
        migration_id: str, source_profile: str, workspaces: DiscoveredWorkspaces
    ) -> TestMonitorDiscovery:
        fake.calls.append(
            {
                "migration_id": migration_id,
                "profile": source_profile,
                "workspaces": list(workspaces.selected),
            }
        )
        if fake.fail:
            raise RuntimeError("source unavailable")
        return DISCOVERY

    monkeypatch.setattr(discover_test_monitor_task, "fn", test_monitor_discovery)

    def files_discovery(
        migration_id: str, source_profile: str, workspaces: DiscoveredWorkspaces
    ) -> FileDiscovery:
        return FILES_DISCOVERY

    monkeypatch.setattr(discover_files_task, "fn", files_discovery)

    return fake


def test_discovery_persists_typed_task_result(
    fake_source: FakeSource, test_prefect_server: str, tmp_path: Path
) -> None:
    """The flow returns typed results and persists them in the run's storage."""
    run = create_migration_run("source", "destination", {"Lab": "Lab"}, tmp_path)

    discovery = run_discovery(run, "source", ["Lab"], test_prefect_server)

    assert discovery.test_monitor == DISCOVERY
    assert discovery.files == FILES_DISCOVERY
    assert fake_source.calls == [
        {"migration_id": run.migration_id, "profile": "source", "workspaces": ["Lab"]}
    ]
    assert len(list(run.results_path.iterdir())) == 4
    assert not run.server_home.exists()


def test_discovery_is_cached_per_input(
    fake_source: FakeSource, test_prefect_server: str, tmp_path: Path
) -> None:
    """Repeating the same inputs reuses the persisted task; new inputs recompute."""
    run = create_migration_run("source", "destination", None, tmp_path)

    first = run_discovery(run, "source", ["Lab"], test_prefect_server)
    second = run_discovery(run, "source", ["Lab"], test_prefect_server)
    run_discovery(run, "source", ["Other"], test_prefect_server)

    assert second == first
    assert [call["workspaces"] for call in fake_source.calls] == [["Lab"], ["Other"]]


def test_failed_run_does_not_affect_later_runs(
    fake_source: FakeSource, test_prefect_server: str, tmp_path: Path
) -> None:
    """A run-level failure surfaces and leaves the shared server usable."""
    fake_source.fail = True
    with pytest.raises(RuntimeError, match="source unavailable"):
        run_discovery(
            create_migration_run("source", "destination", None, tmp_path),
            "source",
            None,
            test_prefect_server,
        )

    fake_source.fail = False
    run = create_migration_run("source", "destination", None, tmp_path)

    assert run_discovery(run, "source", None, test_prefect_server).test_monitor == DISCOVERY


# Restarting over the same database exercises OS process and file-lock handling.
@pytest.mark.full_os_client_matrix
def test_managed_server_restart_reuses_persisted_discovery(
    fake_source: FakeSource, tmp_path: Path
) -> None:
    """A new managed server over the same run restores discovery without recomputing."""
    run = create_migration_run("source", "destination", None, tmp_path)

    with prefect_server(run) as api_url:
        first = run_discovery(run, "source", None, api_url)
    with prefect_server(run) as api_url:
        second = run_discovery(run, "source", None, api_url)

    assert second == first
    assert len(fake_source.calls) == 1
    assert (run.server_home / "prefect.db").is_file()


def test_cached_discovery_does_not_depend_on_server_history(
    fake_source: FakeSource, test_prefect_server: str, tmp_path: Path
) -> None:
    """Result storage alone restores a run; any server can serve the next flow."""
    run = create_migration_run("source", "destination", None, tmp_path)
    first = run_discovery(run, "source", None, test_prefect_server)

    with prefect_server(run) as fresh_server_url:
        second = run_discovery(run, "source", None, fresh_server_url)

    assert second == first
    assert len(fake_source.calls) == 1


def test_file_transfer_resume_persists_reassigned_ids(
    fake_source: FakeSource,
    test_prefect_server: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The real flow recovers partial uploads and persists the final reference map."""
    intended_good, intended_bad, actual_good = ("ab" * 12, "cd" * 12, "ef" * 12)
    discovery = FileDiscovery(
        files=(
            DiscoveredFile(id="good", workspace="Lab", name="good.txt"),
            DiscoveredFile(id="bad", workspace="Lab", name="bad.txt"),
        ),
        file_id_map={"good": intended_good, "bad": intended_bad},
        workspaces=("Lab",),
    )
    mapping = WorkspaceMapping(
        workspaces=(
            MappedWorkspace(
                source_name="Lab",
                source_id="Lab-id",
                destination_name="Destination",
                destination_id="dest-id",
            ),
        )
    )
    stored: Dict[str, SourceFile] = {}
    uploads: List[str] = []
    downloads: List[str] = []
    fail = True

    class Endpoint:
        """In-memory file API; Prefect flow and task persistence remain real."""

        @contextmanager
        def download_file(self, file_id: str) -> Iterator[FileContent]:
            """Record downloads, failing one source until the run resumes."""
            downloads.append(file_id)
            if fail and file_id == "bad":
                raise RuntimeError("source temporarily unavailable")
            yield FileContent([file_id.encode()], len(file_id))

        def query_files(self, workspace_id: str) -> Iterator[SourceFile]:
            """Expose uploads from prior attempts for reconciliation."""
            assert workspace_id == "dest-id"
            return iter(stored.values())

        def upload_file(
            self,
            file_id: str,
            workspace_id: str,
            filename: str,
            properties: Mapping[str, Any],
            content: FileContent,
        ) -> str:
            """Store the metadata and return the actual destination identity."""
            assert b"".join(content.chunks) == properties[MIGRATED_SOURCE_ID].encode()
            uploads.append(file_id)
            actual_id = actual_good if file_id == intended_good else file_id
            stored[actual_id] = SourceFile(id=actual_id, properties=dict(properties))
            return actual_id

    monkeypatch.setattr(discover_files_task, "fn", lambda *args: discovery)
    monkeypatch.setattr(synchronize_workspaces_task, "fn", lambda *args: mapping)
    monkeypatch.setattr(migrate_test_monitor_task, "fn", lambda *args: TestMonitorMigration())
    monkeypatch.setattr(
        "slcli.migration.files.transfer_task.resolve_migration_connection",
        lambda profile: MigrationConnection(profile, f"https://{profile}", {}),
    )
    monkeypatch.setattr(
        "slcli.migration.files.transfer_task.FilesClient", lambda connection: Endpoint()
    )
    run = create_migration_run("source", "destination", {"Lab": "Destination"}, tmp_path)
    metadata = run.read_metadata()

    with pytest.raises(click.ClickException, match="1 of 2 files failed"):
        run_migration(run, metadata, test_prefect_server)
    assert uploads == [intended_good]
    assert downloads == ["good", "bad", "bad"]

    fail = False
    resumed = run_migration(run, metadata, test_prefect_server)
    assert resumed.discovery.files == discovery
    assert resumed.mapping == mapping
    assert resumed.files.transferred == 1
    assert resumed.files.already_present == 1
    assert resumed.files.reassigned_ids == {intended_good: actual_good}
    assert uploads == [intended_good, intended_bad]
    assert downloads == ["good", "bad", "bad", "bad"]
    assert len(fake_source.calls) == 1

    def unexpected_client(connection: MigrationConnection) -> None:
        pytest.fail("A completed transfer must load its persisted result")

    monkeypatch.setattr("slcli.migration.files.transfer_task.FilesClient", unexpected_client)
    cached = run_migration(run, metadata, test_prefect_server)
    assert cached == resumed
