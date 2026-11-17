"""Prefect-backed tests for persisted migration discovery."""

from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from threading import Barrier, Event
from time import sleep
from typing import Any, Dict, List, Mapping, Optional

import click
import pytest

from slcli.migration.connection import MigrationConnection
from slcli.migration.files.client import FileContent, SourceFile
from slcli.migration.files.discovery_task import discover_files_task
from slcli.migration.files.models import DiscoveredFile, FileDiscovery, FileTransfer
from slcli.migration.files.transfer import MIGRATED_SOURCE_ID
from slcli.migration.files.transfer_task import transfer_files_task
from slcli.migration.orchestration import prefect_server, run_discovery, run_migration
from slcli.migration.state import create_migration_run
from slcli.migration.testmonitor.discovery_task import discover_test_monitor_task
from slcli.migration.testmonitor.file_references import FileReferenceRepair
from slcli.migration.testmonitor.file_references_task import repair_file_references_task
from slcli.migration.testmonitor.migration_task import (
    migrate_results_task,
    migrate_test_monitor_task,
)
from slcli.migration.testmonitor.models import (
    BatchResult,
    DiscoveredProduct,
    DiscoveredResult,
    MigratedItem,
    TestMonitorDiscovery,
    TestMonitorMigration,
)
from slcli.migration.testmonitor.writer import Record, WriteResponse
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


@pytest.mark.parametrize("failing_task", [None, "files", "test-monitor"])
def test_file_and_test_monitor_migrations_run_concurrently(
    fake_source: FakeSource,
    test_prefect_server: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    failing_task: Optional[str],
) -> None:
    """Both tasks overlap, and either failure waits for the other task to finish."""
    barrier = Barrier(2, timeout=30)
    completed = Event()
    repair_calls: List[tuple[FileTransfer, TestMonitorMigration]] = []
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
    monkeypatch.setattr(synchronize_workspaces_task, "fn", lambda *args: mapping)

    def transfer(*args: Any) -> FileTransfer:
        barrier.wait()
        if failing_task == "files":
            raise RuntimeError("files failed")
        if failing_task == "test-monitor":
            sleep(0.5)
        completed.set()
        return FileTransfer(transferred=1)

    def migrate_monitor(*args: Any) -> TestMonitorMigration:
        barrier.wait()
        if failing_task == "test-monitor":
            raise RuntimeError("test-monitor failed")
        if failing_task == "files":
            sleep(0.5)
        completed.set()
        return TestMonitorMigration()

    monkeypatch.setattr(transfer_files_task, "fn", transfer)
    monkeypatch.setattr(migrate_test_monitor_task, "fn", migrate_monitor)

    def repair(
        migration_id: str,
        source_profile: str,
        destination_profile: str,
        files: FileTransfer,
        monitor: TestMonitorMigration,
    ) -> FileReferenceRepair:
        repair_calls.append((files, monitor))
        return FileReferenceRepair()

    monkeypatch.setattr(repair_file_references_task, "fn", repair)
    run = create_migration_run("source", "destination", {"Lab": "Destination"}, tmp_path)
    metadata = run.read_metadata()

    if failing_task is None:
        outcome = run_migration(run, metadata, test_prefect_server)
        assert outcome.files == FileTransfer(transferred=1)
        assert outcome.test_monitor == TestMonitorMigration()
        assert repair_calls == [(outcome.files, outcome.test_monitor)]
    else:
        with pytest.raises(RuntimeError, match=f"{failing_task} failed"):
            run_migration(run, metadata, test_prefect_server)
        assert repair_calls == []
    assert completed.is_set()


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
        source_to_destination_id_map={"good": intended_good, "bad": intended_bad},
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


@pytest.mark.parametrize("interrupt_stage", [None, "transfer", "repair", "completion"])
def test_result_file_reference_task_receives_both_migration_outcomes(
    fake_source: FakeSource,
    test_prefect_server: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    interrupt_stage: Optional[str],
) -> None:
    """Prefect resolves both futures and reuses completed batch and repair results."""
    from slcli.migration.annotations import COMPLETE, INCOMPLETE, STATUS, UNRESOLVED_FILE_IDS

    intended, second, actual = "ab" * 12, "cd" * 12, "ef" * 12
    discovery = FileDiscovery(
        source_to_destination_id_map={"source-file": intended, "second-file": second}
    )
    mapping = WorkspaceMapping()
    migration = TestMonitorMigration(
        results=(
            BatchResult(
                resource="results",
                batch=0,
                file_results={intended: ("dest-result",), second: ("second-result",)},
                migrated=(
                    MigratedItem(
                        source_id="source-result",
                        destination_id="dest-result",
                        unresolved_file_ids=("unresolved",),
                    ),
                    MigratedItem(source_id="second-source", destination_id="second-result"),
                ),
            ),
        )
    )
    updates: List[Record] = []
    completions: List[Record] = []
    batch_calls: List[int] = []
    records: Dict[str, Record] = {
        "dest-result": {
            "id": "dest-result",
            "fileIds": [intended],
            "properties": {UNRESOLVED_FILE_IDS: "unresolved", STATUS: INCOMPLETE},
        },
        "second-result": {
            "id": "second-result",
            "fileIds": [second],
            "properties": {STATUS: INCOMPLETE},
        },
    }
    interrupted = False

    class Client:
        """Return source or destination result records for the repair task."""

        def __init__(self, connection: MigrationConnection) -> None:
            self.profile = connection.profile_name

        def query_records(
            self, collection: str, filter_expr: str, substitutions: List[object]
        ) -> Iterator[Record]:
            assert self.profile == "destination"
            for result_id in substitutions:
                assert isinstance(result_id, str)
                yield records[result_id]

    class Writer:
        """Capture the destination update."""

        def __init__(self, connection: MigrationConnection) -> None:
            assert connection.profile_name == "destination"

        def update_results(self, results: List[Record], *, replace: bool = False) -> WriteResponse:
            nonlocal interrupted
            if not replace:
                assert records["dest-result"]["fileIds"] == [second]
                assert records["second-result"]["fileIds"] == [actual]
                for result in results:
                    records[result["id"]]["properties"].update(result["properties"])
                    completions.append(result)
                    if interrupt_stage == "completion" and not interrupted:
                        interrupted = True
                        raise RuntimeError("response lost during completion")
                return WriteResponse(created=results)
            assert all(record["properties"][STATUS] == INCOMPLETE for record in records.values())
            if interrupt_stage == "repair" and not interrupted:
                records[results[0]["id"]].update(results[0])
                updates.append(results[0])
                interrupted = True
                raise RuntimeError("response lost after partial repair")
            for result in results:
                records[result["id"]].update(result)
            updates.extend(results)
            return WriteResponse(created=results)

    monkeypatch.setattr(discover_files_task, "fn", lambda *args: discovery)
    monkeypatch.setattr(
        discover_test_monitor_task,
        "fn",
        lambda *args: TestMonitorDiscovery(
            results=(
                DiscoveredResult(
                    id="source-result",
                    product_id=None,
                    workspace="Lab",
                    status="PASSED",
                    updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                ),
                DiscoveredResult(
                    id="second-source",
                    product_id=None,
                    workspace="Lab",
                    status="PASSED",
                    updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
                ),
            )
        ),
    )
    monkeypatch.setattr(synchronize_workspaces_task, "fn", lambda *args: mapping)

    def transfer(*args: Any) -> FileTransfer:
        nonlocal interrupted
        if interrupt_stage == "transfer" and not interrupted:
            interrupted = True
            raise RuntimeError("file transfer failed")
        return FileTransfer(reassigned_ids={intended: second, second: actual})

    monkeypatch.setattr(transfer_files_task, "fn", transfer)

    def migrate_result_batch(
        migration_id: str,
        source_profile: str,
        destination_profile: str,
        mapping: WorkspaceMapping,
        batch: int,
        results: List[DiscoveredResult],
        file_id_map: Dict[str, str],
        file_id_map_digest: str,
    ) -> BatchResult:
        assert file_id_map == {"source-file": intended, "second-file": second}
        assert [result.id for result in results] == ["source-result", "second-source"]
        batch_calls.append(batch)
        return migration.results[0]

    monkeypatch.setattr(migrate_results_task, "fn", migrate_result_batch)
    monkeypatch.setattr(
        "slcli.migration.testmonitor.file_references_task.resolve_migration_connection",
        lambda profile: MigrationConnection(profile, f"https://{profile}", {}),
    )
    monkeypatch.setattr(
        "slcli.migration.testmonitor.file_references_task.TestMonitorClient", Client
    )
    monkeypatch.setattr(
        "slcli.migration.testmonitor.file_references_task.TestMonitorWriter", Writer
    )
    run = create_migration_run("source", "destination", {"Lab": "Destination"}, tmp_path)

    if interrupt_stage is not None:
        with pytest.raises(RuntimeError, match="response lost|file transfer failed"):
            run_migration(run, run.read_metadata(), test_prefect_server)
        if interrupt_stage != "completion":
            assert completions == []
            assert all(record["properties"][STATUS] == INCOMPLETE for record in records.values())
    outcome = run_migration(run, run.read_metadata(), test_prefect_server)

    assert updates == [
        {
            "id": "dest-result",
            "fileIds": [second],
        },
        {"id": "second-result", "fileIds": [actual]},
    ]
    assert records["dest-result"]["fileIds"] == [second]
    assert records["second-result"]["fileIds"] == [actual]
    expected_updates = {"repair": 1, "completion": 0}
    assert outcome.file_references.updated == expected_updates.get(interrupt_stage or "", 2)
    assert outcome.file_references.unresolved[0].file_ids == ("unresolved",)
    assert all(record["properties"][STATUS] == COMPLETE for record in records.values())
    assert records["dest-result"]["properties"][UNRESOLVED_FILE_IDS] == "unresolved"
    completion_count = len(completions)
    resumed = run_migration(run, run.read_metadata(), test_prefect_server)
    assert resumed == outcome
    assert batch_calls == [0]
    assert len(updates) == 2
    assert len(completions) == completion_count
