"""Tests for transferring discovered files to destination workspaces."""

import re
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any, Dict, List, Mapping, Optional

import click
import pytest

from slcli.migration.connection import MigrationConnection
from slcli.migration.files import transfer as transfer_module
from slcli.migration.files.client import FileContent, SourceFile
from slcli.migration.files.models import DiscoveredFile, FileDiscovery, FileFailure, FileTransfer
from slcli.migration.files.transfer import MIGRATED_SOURCE_ID, transfer_files
from slcli.migration.files.transfer_task import transfer_files_task
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
            existing: Destination properties by file ID, per destination workspace.
            download_failures: Number of times each source file fails to download.
            assigned_ids: IDs the destination assigns instead of the requested ones.
        """
        self.existing = existing or {}
        self.download_failures = download_failures or {}
        self.assigned_ids = assigned_ids or {}
        self.queried: List[str] = []
        self.downloads: List[str] = []
        self.uploads: List[Dict[str, Any]] = []

    @contextmanager
    def download_file(self, file_id: str) -> Iterator[FileContent]:
        self.downloads.append(file_id)
        if self.download_failures.get(file_id, 0) > 0:
            self.download_failures[file_id] -= 1
            raise RuntimeError("download failed")
        yield FileContent(chunks=[file_id.encode()], length=len(file_id))

    def query_files(self, workspace_id: str) -> Iterator[SourceFile]:
        self.queried.append(workspace_id)
        return iter(
            SourceFile(id=file_id, properties=properties)
            for file_id, properties in self.existing.get(workspace_id, {}).items()
        )

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


def test_files_are_uploaded_with_mapped_ids_to_mapped_workspaces() -> None:
    """Each file keeps its bytes and properties under its pre-allocated destination ID."""
    files = FakeFiles()
    discovery = _discovery(
        DiscoveredFile(id="f1", workspace="Lab", name="a.txt", properties={"Name": "a.txt"}),
        DiscoveredFile(id="f2", workspace="Default"),
    )

    transfer = transfer_files(files, files, discovery, MAPPING)

    assert transfer == FileTransfer(transferred=2)
    assert files.uploads == [
        {
            "id": "new-f1",
            "workspace": "sh-id",
            "filename": "a.txt",
            "properties": {"Name": "a.txt", MIGRATED_SOURCE_ID: "f1"},
            "data": b"f1",
        },
        {
            "id": "new-f2",
            "workspace": "d-id",
            "filename": "f2",
            "properties": {MIGRATED_SOURCE_ID: "f2"},
            "data": b"f2",
        },
    ]


def test_files_already_on_the_destination_are_skipped() -> None:
    """An annotation identifies an earlier upload, regardless of its current name."""
    files = FakeFiles(
        existing={
            "sh-id": {
                "new-f1": {"Name": "renamed.txt", MIGRATED_SOURCE_ID: "f1"},
                "unrelated": {"Name": "b.txt"},
            }
        }
    )
    discovery = _discovery(
        DiscoveredFile(id="f1", workspace="Lab", name="a.txt"),
        DiscoveredFile(id="f2", workspace="Other"),
    )

    transfer = transfer_files(files, files, discovery, MAPPING)

    assert transfer == FileTransfer(transferred=1, already_present=1)
    assert [upload["id"] for upload in files.uploads] == ["new-f2"]
    assert files.queried == ["sh-id"]


def test_mapped_id_taken_by_another_file_uploads_under_a_reassigned_id() -> None:
    """A mapped ID used by a differently named file is replaced and recorded."""
    files = FakeFiles(existing={"sh-id": {"new-f1": {"Name": "a.txt"}}})
    discovery = _discovery(DiscoveredFile(id="f1", workspace="Lab", name="a.txt"))

    transfer = transfer_files(files, files, discovery, MAPPING)

    replacement = files.uploads[0]["id"]
    assert transfer == FileTransfer(transferred=1, reassigned_ids={"new-f1": replacement})
    assert [upload["id"] for upload in files.uploads] == [replacement]
    assert re.fullmatch(r"[0-9a-f]{24}", replacement)


def test_replacements_skip_ids_taken_by_other_files(monkeypatch: pytest.MonkeyPatch) -> None:
    """Replacement IDs that are also taken by another file move on to the next one."""
    candidates = iter(["occupied", "ab" * 12])
    monkeypatch.setattr(
        "slcli.migration.files.transfer.secrets.token_hex", lambda _size: next(candidates)
    )
    files = FakeFiles(
        existing={"sh-id": {"new-f1": {"Name": "other.txt"}, "occupied": {"Name": "other2.txt"}}}
    )
    discovery = _discovery(DiscoveredFile(id="f1", workspace="Lab", name="a.txt"))

    transfer = transfer_files(files, files, discovery, MAPPING)

    assert transfer.reassigned_ids == {"new-f1": "ab" * 12}


def test_replacement_avoids_the_mapped_id_of_another_file(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A replacement never takes an ID pre-allocated to another discovered file."""
    candidates = iter(["new-f2", "free-id"])
    monkeypatch.setattr(
        "slcli.migration.files.transfer.secrets.token_hex",
        lambda _size: next(candidates),
    )
    files = FakeFiles(existing={"sh-id": {"new-f1": {"Name": "other.txt"}}})
    discovery = _discovery(
        DiscoveredFile(id="f1", workspace="Lab", name="a.txt"),
        DiscoveredFile(id="f2", workspace="Default"),
    )

    transfer = transfer_files(files, files, discovery, MAPPING)

    assert transfer.reassigned_ids == {"new-f1": "free-id"}
    assert [upload["id"] for upload in files.uploads] == ["free-id", "new-f2"]


def test_resumed_transfer_finds_a_file_uploaded_under_a_replacement() -> None:
    """Annotations recover arbitrary replacement IDs without generating them again."""
    files = FakeFiles(
        existing={
            "sh-id": {
                "new-f1": {"Name": "other.txt"},
                "server-id": {"Name": "a.txt", MIGRATED_SOURCE_ID: "f1"},
            }
        }
    )
    discovery = _discovery(DiscoveredFile(id="f1", workspace="Lab", name="a.txt"))

    transfer = transfer_files(files, files, discovery, MAPPING)

    assert transfer == FileTransfer(already_present=1, reassigned_ids={"new-f1": "server-id"})
    assert files.uploads == []


def test_server_assigned_id_is_recorded_as_reassigned() -> None:
    """When the destination assigns a different ID, the intended ID maps to it."""
    files = FakeFiles(assigned_ids={"new-f1": "server-id"})
    discovery = _discovery(
        DiscoveredFile(id="f1", workspace="Lab"),
        DiscoveredFile(id="f2", workspace="Lab"),
    )

    transfer = transfer_files(files, files, discovery, MAPPING)

    assert transfer == FileTransfer(transferred=2, reassigned_ids={"new-f1": "server-id"})


def test_unnamed_files_are_matched_by_annotation() -> None:
    """Files without names are identified by their source IDs, too."""
    files = FakeFiles(existing={"sh-id": {"new-f1": {MIGRATED_SOURCE_ID: "f1"}}})
    discovery = _discovery(DiscoveredFile(id="f1", workspace="Lab"))

    assert transfer_files(files, files, discovery, MAPPING) == FileTransfer(already_present=1)


def test_failed_transfer_is_retried_once() -> None:
    """A transient failure is retried and the file still transfers."""
    files = FakeFiles(download_failures={"f1": 1})
    discovery = _discovery(DiscoveredFile(id="f1", workspace="Lab"))

    transfer = transfer_files(files, files, discovery, MAPPING)

    assert transfer == FileTransfer(transferred=1)
    assert files.downloads == ["f1", "f1"]
    assert files.queried == ["sh-id"]


def test_upload_annotation_overrides_source_metadata_without_mutating_it() -> None:
    """Source metadata cannot override the migration-owned source identity."""
    properties = {"Name": "a.txt", MIGRATED_SOURCE_ID: "old-source"}
    discovery = _discovery(DiscoveredFile(id="f1", workspace="Lab", properties=properties))
    files = FakeFiles()

    transfer_files(files, files, discovery, MAPPING)

    assert files.uploads[0]["properties"][MIGRATED_SOURCE_ID] == "f1"
    assert discovery.files[0].properties[MIGRATED_SOURCE_ID] == "old-source"


def test_retry_recovers_successful_upload_with_lost_response() -> None:
    """A lost response is reconciled by annotation without a second upload."""

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
            self.existing.setdefault(workspace_id, {})["server-id"] = dict(properties)
            raise RuntimeError("response lost")

    files = LostResponse()
    discovery = _discovery(DiscoveredFile(id="f1", workspace="Lab"))

    transfer = transfer_files(files, files, discovery, MAPPING)

    assert transfer == FileTransfer(transferred=1, reassigned_ids={"new-f1": "server-id"})
    assert len(files.uploads) == 1
    assert files.downloads == ["f1"]
    assert files.queried == ["sh-id", "sh-id"]


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

    assert transfer_files(
        files, files, _discovery(DiscoveredFile(id="f1", workspace="Lab")), MAPPING
    ) == FileTransfer(transferred=1)
    assert files.downloads == ["f1", "f1"]
    assert [upload["data"] for upload in files.uploads] == [b"f1", b"f1"]
    assert files.queried == ["sh-id", "sh-id"]


def test_annotation_matching_is_scoped_to_mapped_workspace() -> None:
    """A file annotated in another destination workspace does not satisfy this upload."""
    files = FakeFiles(existing={"d-id": {"other-id": {MIGRATED_SOURCE_ID: "f1"}}})

    assert transfer_files(
        files, files, _discovery(DiscoveredFile(id="f1", workspace="Lab")), MAPPING
    ) == FileTransfer(transferred=1)


def test_duplicate_annotations_fail_only_the_ambiguous_file(
    caplog: pytest.LogCaptureFixture,
) -> None:
    """Reject ambiguous identity without stopping independent file transfers."""
    files = FakeFiles(
        existing={
            "sh-id": {
                "first": {MIGRATED_SOURCE_ID: "f1"},
                "second": {MIGRATED_SOURCE_ID: "f1"},
            }
        }
    )

    discovery = _discovery(
        DiscoveredFile(id="f1", workspace="Lab"),
        DiscoveredFile(id="f2", workspace="Lab"),
    )
    result = transfer_files(files, files, discovery, MAPPING)
    assert result.failures == (FileFailure(id="f1", workspace="Lab", error_type="ValueError"),)
    assert result.transferred == 1
    assert [upload["id"] for upload in files.uploads] == ["new-f2"]
    assert files.downloads == ["f2"]
    assert "Multiple destination files" in caplog.text


def test_failed_file_is_isolated_from_the_others() -> None:
    """A file failing both attempts is recorded while the remaining files still transfer."""
    files = FakeFiles(download_failures={"f1": 2})
    discovery = _discovery(
        DiscoveredFile(id="f1", workspace="Lab"),
        DiscoveredFile(id="f2", workspace="Lab"),
    )

    transfer = transfer_files(files, files, discovery, MAPPING)

    assert transfer.transferred == 1
    assert transfer.failures == (FileFailure(id="f1", workspace="Lab", error_type="RuntimeError"),)
    assert files.downloads == ["f1", "f1", "f2"]
    assert [upload["id"] for upload in files.uploads] == ["new-f2"]


def test_no_files_queries_nothing() -> None:
    """Without discovered files the destination is not touched."""
    files = FakeFiles()

    assert transfer_files(files, files, _discovery(), MAPPING) == FileTransfer()
    assert files.queried == []


def test_destination_annotations_are_indexed_once_per_workspace(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Large transfers must not rescan all annotations for each source file."""
    indexed_sizes: List[int] = []
    original = transfer_module._index_migrated_files

    def index(files: Iterator[SourceFile]) -> Dict[str, List[SourceFile]]:
        items = list(files)
        indexed_sizes.append(len(items))
        return original(items)

    monkeypatch.setattr(transfer_module, "_index_migrated_files", index)
    count = 1000
    files = FakeFiles(
        existing={"sh-id": {f"existing-{i}": {MIGRATED_SOURCE_ID: f"f{i}"} for i in range(count)}}
    )
    discovery = _discovery(*(DiscoveredFile(id=f"f{i}", workspace="Lab") for i in range(count * 2)))

    result = transfer_files(files, files, discovery, MAPPING)

    assert result.already_present == count
    assert result.transferred == count
    assert indexed_sizes == [count]
    assert files.queried == ["sh-id"]


def test_transfer_result_survives_a_json_round_trip() -> None:
    """The result is persisted as JSON by Prefect, so it must load back unchanged."""
    transfer = FileTransfer(
        transferred=1,
        already_present=2,
        reassigned_ids={"intended": "actual"},
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


def test_task_raises_when_any_file_fails_so_resume_retries(task_files: FakeFiles) -> None:
    """Failed files fail the task, which leaves it uncached for a resumed run."""
    discovery = _discovery(
        DiscoveredFile(id="bad", workspace="Lab"),
        DiscoveredFile(id="good", workspace="Lab"),
    )

    with pytest.raises(click.ClickException, match="1 of 2 files failed") as raised:
        transfer_files_task.fn("run-id", "source", "destination", discovery, MAPPING)

    assert "--migration-id run-id" in raised.value.message
    assert [upload["id"] for upload in task_files.uploads] == ["new-good"]


def test_task_returns_transfer_when_every_file_succeeds(task_files: FakeFiles) -> None:
    discovery = _discovery(DiscoveredFile(id="good", workspace="Lab"))

    transfer = transfer_files_task.fn("run-id", "source", "destination", discovery, MAPPING)

    assert transfer == FileTransfer(transferred=1)


def test_task_rejects_readonly_destination_before_transferring(task_files: FakeFiles) -> None:
    discovery = _discovery(DiscoveredFile(id="good", workspace="Lab"))

    with pytest.raises(click.ClickException, match="profile 'readonly' is in readonly mode"):
        transfer_files_task.fn("run-id", "source", "readonly", discovery, MAPPING)

    assert task_files.queried == []
    assert task_files.uploads == []


def test_task_allows_readonly_destination_without_files(task_files: FakeFiles) -> None:
    """A readonly destination is only a problem when there is something to upload."""
    assert transfer_files_task.fn("run-id", "source", "readonly", _discovery(), MAPPING) == (
        FileTransfer()
    )
