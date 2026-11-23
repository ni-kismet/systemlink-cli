"""Tests for transferring discovered files to destination workspaces."""

from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, Dict, List, Mapping, Optional, Sequence, Set

import click
import pytest
from prefect import flow
from prefect.testing.utilities import prefect_test_harness

from slcli.migration.connection import MigrationConnection
from slcli.migration.files.client import FileContent
from slcli.migration.files.models import DiscoveredFile, FileDiscovery, FileFailure, FileTransfer
from slcli.migration.files.transfer import (
    MIGRATED_SOURCE_ID,
    split_into_batches,
    transfer_batch,
)
from slcli.migration.files.transfer_task import transfer_files_task
from slcli.migration.flows.service import migration_task_runner
from slcli.migration.workspaces import MappedWorkspace, WorkspaceMapping

MAPPING = WorkspaceMapping(
    workspaces=(
        MappedWorkspace(
            source_name="Default", source_id="s-d", destination_name="D", destination_id="d-id"
        ),
        MappedWorkspace(
            source_name="Lab", source_id="s-l", destination_name="Shared", destination_id="sh-id"
        ),
        MappedWorkspace(
            source_name="Other", source_id="s-o", destination_name="Shared", destination_id="sh-id"
        ),
    )
)


def _discovery(*files: DiscoveredFile) -> FileDiscovery:
    return FileDiscovery(
        workspaces=("Default", "Lab", "Other"),
        files=files,
        source_to_destination_id_map={file.id: f"new-{file.id}" for file in files},
    )


class FakeFiles:
    """Source downloads and destination queries/uploads, recorded in memory."""

    def __init__(
        self,
        existing: Optional[Dict[str, Dict[str, Dict[str, Any]]]] = None,
        download_failures: Optional[Dict[str, int]] = None,
        assigned_ids: Optional[Dict[str, str]] = None,
    ) -> None:
        """Arrange the destination and the faults to inject.

        Args:
            existing: Destination file properties by file ID, per destination workspace.
            download_failures: Number of times each source file fails to download.
            assigned_ids: IDs the destination assigns instead of the requested ones.
        """
        self.existing = existing or {}
        self.download_failures = download_failures or {}
        self.assigned_ids = assigned_ids or {}
        self.queried: List[List[str]] = []
        self.downloads: List[str] = []
        self.uploads: List[Dict[str, Any]] = []

    @contextmanager
    def download_file(self, file_id: str) -> Iterator[FileContent]:
        self.downloads.append(file_id)
        if self.download_failures.get(file_id, 0) > 0:
            self.download_failures[file_id] -= 1
            raise RuntimeError("download failed")
        yield FileContent(chunks=[file_id.encode()], length=len(file_id))

    def query_existing_ids(self, ids: Sequence[str]) -> Set[str]:
        self.queried.append(list(ids))
        known: Set[str] = set()
        for files in self.existing.values():
            known.update(files)
        return {file_id for file_id in ids if file_id in known}

    def upload_file(
        self,
        file_id: str,
        workspace_id: str,
        filename: str,
        properties: Mapping[str, Any],
        content: FileContent,
    ) -> str:
        self.uploads.append(
            {
                "id": file_id,
                "workspace": workspace_id,
                "filename": filename,
                "properties": dict(properties),
                "data": b"".join(content.chunks),
            }
        )
        return self.assigned_ids.get(file_id, file_id)


def test_batch_uploads_files_under_intended_ids() -> None:
    """Each file keeps its bytes and properties under its pre-allocated destination ID."""
    files = FakeFiles()
    batch = [DiscoveredFile(id="f1", workspace="Lab", name="a.txt", properties={"Name": "a.txt"})]

    transfer = transfer_batch(files, files, batch, {"f1": "new-f1"}, MAPPING)

    assert transfer == FileTransfer(transferred=1)
    assert files.uploads == [
        {
            "id": "new-f1",
            "workspace": "sh-id",
            "filename": "a.txt",
            "properties": {"Name": "a.txt", MIGRATED_SOURCE_ID: "f1"},
            "data": b"f1",
        }
    ]
    assert files.queried == [["new-f1"]]


def test_intended_ids_already_on_the_destination_are_skipped() -> None:
    """A file whose intended ID already exists on the destination is not downloaded or uploaded."""
    files = FakeFiles(existing={"sh-id": {"new-f1": {"Name": "renamed.txt"}}})
    batch = [DiscoveredFile(id="f1", workspace="Lab"), DiscoveredFile(id="f2", workspace="Lab")]

    transfer = transfer_batch(files, files, batch, {"f1": "new-f1", "f2": "new-f2"}, MAPPING)

    assert transfer == FileTransfer(transferred=1, already_present=1)
    assert files.downloads == ["f2"]
    assert [upload["id"] for upload in files.uploads] == ["new-f2"]
    assert files.queried == [["new-f1", "new-f2"]]


def test_batch_routes_each_file_to_its_own_destination_workspace() -> None:
    """A batch may mix source workspaces, and each file uploads to its own mapped destination."""
    files = FakeFiles()
    batch = [DiscoveredFile(id="f1", workspace="Lab"), DiscoveredFile(id="f2", workspace="Default")]

    transfer = transfer_batch(files, files, batch, {"f1": "new-f1", "f2": "new-f2"}, MAPPING)

    assert transfer == FileTransfer(transferred=2)
    assert {upload["id"]: upload["workspace"] for upload in files.uploads} == {
        "new-f1": "sh-id",
        "new-f2": "d-id",
    }
    assert files.queried == [["new-f1", "new-f2"]]


def test_batches_split_by_bytes_regardless_of_workspace() -> None:
    """Batches stay under the byte limit, and a batch may hold files from several workspaces."""
    discovery = _discovery(
        DiscoveredFile(id="a", workspace="Lab", size_bytes=60),
        DiscoveredFile(id="b", workspace="Lab", size_bytes=30),
        DiscoveredFile(id="c", workspace="Default", size_bytes=30),
        DiscoveredFile(id="d", workspace="Lab", size_bytes=30),
    )

    batches = split_into_batches(discovery, max_bytes=100)

    assert [[file.id for file in batch] for batch in batches] == [["a", "b"], ["c", "d"]]


def test_oversized_file_forms_its_own_batch() -> None:
    discovery = _discovery(
        DiscoveredFile(id="big", workspace="Lab", size_bytes=500),
        DiscoveredFile(id="small", workspace="Lab", size_bytes=10),
    )

    batches = split_into_batches(discovery, max_bytes=100)

    assert [[file.id for file in batch] for batch in batches] == [["big"], ["small"]]


def test_failed_transfer_is_retried_once() -> None:
    """A transient download failure is retried and the file still transfers."""
    files = FakeFiles(download_failures={"f1": 1})
    batch = [DiscoveredFile(id="f1", workspace="Lab")]

    transfer = transfer_batch(files, files, batch, {"f1": "new-f1"}, MAPPING)

    assert transfer == FileTransfer(transferred=1)
    assert files.downloads == ["f1", "f1"]


def test_retry_recovers_successful_upload_with_lost_response() -> None:
    """A lost response is reconciled by checking the intended ID, without a second upload."""

    class LostResponse(FakeFiles):
        def upload_file(
            self,
            file_id: str,
            workspace_id: str,
            filename: str,
            properties: Mapping[str, Any],
            content: FileContent,
        ) -> str:
            super().upload_file(file_id, workspace_id, filename, properties, content)
            self.existing.setdefault(workspace_id, {})[file_id] = dict(properties)
            raise RuntimeError("response lost")

    files = LostResponse()
    batch = [DiscoveredFile(id="f1", workspace="Lab")]

    transfer = transfer_batch(files, files, batch, {"f1": "new-f1"}, MAPPING)

    assert transfer == FileTransfer(transferred=1)
    assert len(files.uploads) == 1
    assert files.downloads == ["f1"]


def test_failed_upload_reopens_download_for_retry() -> None:
    """A failed streamed upload gets fresh bytes on its second attempt."""

    class FailOnce(FakeFiles):
        def upload_file(
            self,
            file_id: str,
            workspace_id: str,
            filename: str,
            properties: Mapping[str, Any],
            content: FileContent,
        ) -> str:
            actual_id = super().upload_file(file_id, workspace_id, filename, properties, content)
            if len(self.uploads) == 1:
                raise RuntimeError("upload failed")
            return actual_id

    files = FailOnce()
    batch = [DiscoveredFile(id="f1", workspace="Lab")]

    transfer = transfer_batch(files, files, batch, {"f1": "new-f1"}, MAPPING)

    assert transfer == FileTransfer(transferred=1)
    assert files.downloads == ["f1", "f1"]
    assert [upload["data"] for upload in files.uploads] == [b"f1", b"f1"]


def test_server_assigned_different_id_fails_the_file() -> None:
    """A destination that ignores the requested ID cannot be matched later, so it is a failure."""
    files = FakeFiles(assigned_ids={"new-f1": "server-id"})
    batch = [DiscoveredFile(id="f1", workspace="Lab")]

    transfer = transfer_batch(files, files, batch, {"f1": "new-f1"}, MAPPING)

    assert transfer.transferred == 0
    assert transfer.failures == (FileFailure(id="f1", workspace="Lab", error_type="ValueError"),)
    assert len(files.uploads) == 1


def test_failed_file_is_isolated_from_the_others() -> None:
    """A file failing both attempts is recorded while the remaining files still transfer."""
    files = FakeFiles(download_failures={"f1": 2})
    batch = [DiscoveredFile(id="f1", workspace="Lab"), DiscoveredFile(id="f2", workspace="Lab")]

    transfer = transfer_batch(files, files, batch, {"f1": "new-f1", "f2": "new-f2"}, MAPPING)

    assert transfer.transferred == 1
    assert transfer.failures == (FileFailure(id="f1", workspace="Lab", error_type="RuntimeError"),)
    assert files.downloads == ["f1", "f1", "f2"]
    assert [upload["id"] for upload in files.uploads] == ["new-f2"]


def test_transfer_result_survives_a_json_round_trip() -> None:
    """The result is persisted as JSON by Prefect, so it must load back unchanged."""
    transfer = FileTransfer(
        transferred=1,
        already_present=2,
        failures=(FileFailure(id="f", workspace="Lab", error_type="HTTPError"),),
    )

    assert FileTransfer.model_validate_json(transfer.model_dump_json()) == transfer


@pytest.fixture
def task_files(monkeypatch: pytest.MonkeyPatch) -> FakeFiles:
    files = FakeFiles(download_failures={"bad": 2})
    monkeypatch.setattr(
        "slcli.migration.files.transfer_task.resolve_migration_connection",
        lambda profile: MigrationConnection(
            profile, f"https://{profile}", {}, readonly=profile == "readonly"
        ),
    )
    monkeypatch.setattr(
        "slcli.migration.files.transfer_task.FilesClient", lambda _connection: files
    )
    return files


@pytest.fixture(scope="module", autouse=True)
def isolated_prefect() -> Iterator[None]:
    """Keep task results in a temporary Prefect store so cached batches never leak between runs."""
    with prefect_test_harness():
        yield


def _run_transfer(*args: Any) -> FileTransfer:
    """Run the transfer task in a flow so its batches can be mapped."""

    @flow(task_runner=migration_task_runner())
    def transfer_flow() -> FileTransfer:
        return transfer_files_task.fn(*args)

    return transfer_flow()


def test_task_raises_when_any_file_fails_so_resume_retries(task_files: FakeFiles) -> None:
    """Failed files fail the task, which leaves its batch uncached for a resumed run."""
    discovery = _discovery(
        DiscoveredFile(id="bad", workspace="Lab"),
        DiscoveredFile(id="good", workspace="Lab"),
    )

    with pytest.raises(click.ClickException, match="1 of 2 files failed") as raised:
        _run_transfer("run-id", "source", "destination", discovery, MAPPING)

    assert "--migration-id run-id" in raised.value.message
    assert [upload["id"] for upload in task_files.uploads] == ["new-good"]


def test_task_returns_transfer_when_every_file_succeeds(task_files: FakeFiles) -> None:
    discovery = _discovery(DiscoveredFile(id="good", workspace="Lab"))

    transfer = _run_transfer("run-id", "source", "destination", discovery, MAPPING)

    assert transfer == FileTransfer(transferred=1)


def test_task_rejects_readonly_destination_before_transferring(task_files: FakeFiles) -> None:
    discovery = _discovery(DiscoveredFile(id="good", workspace="Lab"))

    with pytest.raises(ValueError, match="profile 'readonly' is in readonly mode"):
        transfer_files_task.fn("run-id", "source", "readonly", discovery, MAPPING)

    assert task_files.queried == []
    assert task_files.uploads == []


def test_task_allows_readonly_destination_without_files(task_files: FakeFiles) -> None:
    """A readonly destination is only a problem when there is something to upload."""
    assert transfer_files_task.fn("run-id", "source", "readonly", _discovery(), MAPPING) == (
        FileTransfer()
    )
