"""Tests for backpatching reassigned result file IDs."""

from typing import Dict, Iterable, List, Sequence, Tuple

import pytest

from slcli.migration.annotations import COMPLETE, COMPLETED_AT, STATUS
from slcli.migration.connection import MigrationConnection
from slcli.migration.files.models import FileTransfer
from slcli.migration.testmonitor.file_references import complete_results, repair_file_references
from slcli.migration.testmonitor.file_references_task import repair_file_references_task
from slcli.migration.testmonitor.models import (
    BatchResult,
    FailedItem,
    MigratedItem,
    TestMonitorMigration,
)
from slcli.migration.testmonitor.writer import ApiError, Record, WriteResponse


class Queries:
    """Fetch destination records by parameterized IDs."""

    def __init__(self, records: Sequence[Record]) -> None:
        """Store records for lookup."""
        self.records = {record["id"]: record for record in records}
        self.calls: List[Sequence[object]] = []

    def query_records(
        self, collection: str, filter_expr: str, substitutions: Sequence[object]
    ) -> Iterable[Record]:
        assert collection == "results"
        assert filter_expr == " || ".join(f"id == @{i}" for i in range(len(substitutions)))
        self.calls.append(substitutions)
        return [self.records[item] for item in substitutions if item in self.records]


class Writer:
    """Record updates and optionally reject them."""

    def __init__(self, response: WriteResponse | None = None) -> None:
        """Initialize captured writes and an optional response."""
        self.updates: List[Record] = []
        self.replace_values: List[bool] = []
        self.batch_sizes: List[int] = []
        self.response = response

    def create_products(self, products: Sequence[Record]) -> WriteResponse:
        raise AssertionError("not used")

    def create_results(self, results: Sequence[Record]) -> WriteResponse:
        raise AssertionError("not used")

    def create_steps(self, steps: Sequence[Record]) -> WriteResponse:
        raise AssertionError("not used")

    def update_results(self, results: Sequence[Record], *, replace: bool = False) -> WriteResponse:
        self.updates.extend(results)
        self.replace_values.append(replace)
        self.batch_sizes.append(len(results))
        return self.response if self.response is not None else WriteResponse(created=list(results))


def _migration(
    *items: MigratedItem, file_results: Dict[str, Tuple[str, ...]]
) -> TestMonitorMigration:
    return TestMonitorMigration(
        results=(
            BatchResult(resource="results", batch=0, migrated=items, file_results=file_results),
        )
    )


def test_backpatches_only_changed_references_and_preserves_others() -> None:
    destination = Queries(
        [
            {"id": "d1", "fileIds": ["intended-a", "unchanged", "unrelated"]},
            {"id": "d2", "fileIds": ["unchanged"]},
        ]
    )
    writer = Writer()
    migration = _migration(
        MigratedItem(source_id="s1", destination_id="d1", unresolved_file_ids=("missing",)),
        MigratedItem(source_id="s2", destination_id="d2"),
        file_results={"intended-a": ("d1",), "unchanged": ("d1", "d2")},
    )

    result = repair_file_references(
        destination, writer, FileTransfer(reassigned_ids={"intended-a": "actual-a"}), migration
    )

    assert writer.updates == [{"id": "d1", "fileIds": ["actual-a", "unchanged", "unrelated"]}]
    assert writer.replace_values == [True]
    assert result.updated == 1
    assert result.unresolved[0].file_ids == ("missing",)
    assert result.unresolved[0].source_result_id == "s1"
    assert destination.calls == [["d1"]]


def test_no_reassignments_performs_no_queries() -> None:
    destination, writer = Queries([]), Writer()
    result = repair_file_references(
        destination,
        writer,
        FileTransfer(),
        _migration(
            MigratedItem(source_id="s", destination_id="d", unresolved_file_ids=("x",)),
            file_results={"old": ("d",)},
        ),
    )
    assert result.updated == 0
    assert result.unresolved[0].file_ids == ("x",)
    assert destination.calls == writer.updates == []


def test_already_backpatched_result_is_not_written_again() -> None:
    destination = Queries([{"id": "d", "fileIds": ["actual"]}])
    writer = Writer()
    result = repair_file_references(
        destination,
        writer,
        FileTransfer(reassigned_ids={"intended": "actual"}),
        _migration(
            MigratedItem(source_id="s", destination_id="d"), file_results={"intended": ("d",)}
        ),
    )
    assert result.updated == 0
    assert writer.updates == []
    assert destination.calls == [["d"]]


@pytest.mark.parametrize(
    "reassignments",
    [{"a": "b", "b": "c"}, {"a": "b", "b": "a"}],
)
def test_overlapping_reassignments_resume_after_partial_update(
    reassignments: Dict[str, str],
) -> None:
    """Original associations disambiguate both chains and cycles after a lost response."""
    destination = Queries(
        [
            {"id": "d1", "fileIds": ["a", "extra"]},
            {"id": "d2", "fileIds": ["b"]},
            {"id": "d3", "fileIds": ["a", "b"]},
        ]
    )
    migration = _migration(file_results={"a": ("d1", "d3"), "b": ("d2", "d3")})
    transfer = FileTransfer(reassigned_ids=reassignments)

    class InterruptedWriter(Writer):
        def update_results(
            self, results: Sequence[Record], *, replace: bool = False
        ) -> WriteResponse:
            super().update_results(results, replace=replace)
            destination.records["d1"].update(results[0])
            raise RuntimeError("response lost after partial update")

    with pytest.raises(RuntimeError, match="response lost"):
        repair_file_references(destination, InterruptedWriter(), transfer, migration)
    assert destination.records["d1"]["fileIds"] == [reassignments["a"], "extra"]

    writer = Writer()
    repair_file_references(destination, writer, transfer, migration)

    assert all(record["id"] != "d1" for record in writer.updates)
    expected = {"d2": [reassignments["b"]], "d3": list(reassignments.values())}
    for update in writer.updates:
        assert set(update["fileIds"]) == set(expected[update["id"]])
        destination.records[update["id"]].update(update)
    assert destination.records["d2"]["fileIds"] == [reassignments["b"]]
    assert set(destination.records["d3"]["fileIds"]) == set(reassignments.values())
    assert repair_file_references(destination, writer, transfer, migration).updated == 0


def test_partially_migrated_results_with_destination_ids_are_backpatched() -> None:
    migration = TestMonitorMigration(
        results=(
            BatchResult(
                resource="results",
                batch=0,
                file_results={"old": ("d",)},
                failed=(
                    FailedItem(
                        source_id="s",
                        stage="complete",
                        error_type="RuntimeError",
                        destination_id="d",
                        unresolved_file_ids=("missing",),
                    ),
                    FailedItem(source_id="missing", stage="create", error_type="RuntimeError"),
                ),
            ),
        )
    )
    writer = Writer()
    result = repair_file_references(
        Queries([{"id": "d", "fileIds": ["old"]}]),
        writer,
        FileTransfer(reassigned_ids={"old": "new"}),
        migration,
    )
    assert result.updated == 1
    assert result.unresolved[0].file_ids == ("missing",)
    assert writer.updates == [{"id": "d", "fileIds": ["new"]}]


@pytest.mark.parametrize(
    "response",
    [
        WriteResponse(failed=[{"id": "d"}]),
        WriteResponse(error=ApiError(name="rejected")),
        WriteResponse(),
    ],
)
def test_rejected_updates_fail_task(response: WriteResponse) -> None:
    with pytest.raises(ValueError, match="Failed to update"):
        repair_file_references(
            Queries([{"id": "d", "fileIds": ["old"]}]),
            Writer(response),
            FileTransfer(reassigned_ids={"old": "new"}),
            _migration(
                MigratedItem(source_id="s", destination_id="d"), file_results={"old": ("d",)}
            ),
        )


def test_missing_result_fails() -> None:
    with pytest.raises(ValueError, match="Results not found.*d"):
        repair_file_references(
            Queries([]),
            Writer(),
            FileTransfer(reassigned_ids={"old": "new"}),
            _migration(
                MigratedItem(source_id="s", destination_id="d"), file_results={"old": ("d",)}
            ),
        )


def test_malformed_file_ids_fail() -> None:
    with pytest.raises(ValueError, match="Invalid fileIds"):
        repair_file_references(
            Queries([{"id": "d", "fileIds": "old"}]),
            Writer(),
            FileTransfer(reassigned_ids={"old": "new"}),
            _migration(
                MigratedItem(source_id="s", destination_id="d"), file_results={"old": ("d",)}
            ),
        )


def test_no_migrated_results_does_not_query_or_write() -> None:
    destination, writer = Queries([]), Writer()
    result = repair_file_references(
        destination,
        writer,
        FileTransfer(reassigned_ids={"old": "new"}),
        _migration(file_results={}),
    )
    assert result.updated == 0
    assert destination.calls == writer.updates == []


def test_queries_are_bounded_and_parameterized() -> None:
    count = 201
    destination = Queries([{"id": f"d{i}", "fileIds": ["old"]} for i in range(count)])
    writer = Writer()
    result = repair_file_references(
        destination,
        writer,
        FileTransfer(reassigned_ids={"old": "new"}),
        _migration(file_results={"old": tuple(f"d{i}" for i in range(count))}),
    )
    assert [len(call) for call in destination.calls] == [100, 100, 1]
    assert writer.batch_sizes == [100, 100, 1]
    assert result.updated == count


def test_one_affected_result_does_not_fetch_unaffected_results() -> None:
    destination, writer = Queries([{"id": "affected", "fileIds": ["old"]}]), Writer()
    migration = _migration(
        file_results={
            "old": ("affected",),
            "unchanged": tuple(f"missing-{i}" for i in range(1000)),
        }
    )
    assert (
        repair_file_references(
            destination, writer, FileTransfer(reassigned_ids={"old": "new"}), migration
        ).updated
        == 1
    )
    assert destination.calls == [["affected"]]


def test_no_affected_results_does_not_resolve_connection(monkeypatch: pytest.MonkeyPatch) -> None:
    def unexpected_connection(profile: str) -> None:
        pytest.fail("No destination queries are needed")

    monkeypatch.setattr(
        "slcli.migration.testmonitor.file_references_task.resolve_migration_connection",
        unexpected_connection,
    )
    result = repair_file_references_task.fn(
        "run",
        "source",
        "destination",
        FileTransfer(reassigned_ids={"other": "new"}),
        _migration(file_results={"unchanged": ("d",)}),
    )
    assert result.updated == 0


def test_completion_is_batched_and_excludes_partial_results() -> None:
    items = tuple(MigratedItem(source_id=f"s{i}", destination_id=f"d{i}") for i in range(201))
    migration = TestMonitorMigration(
        results=(
            BatchResult(
                resource="results",
                batch=0,
                migrated=items,
                failed=(
                    FailedItem(
                        source_id="partial",
                        destination_id="partial-destination",
                        stage="steps",
                        error_type="RuntimeError",
                    ),
                ),
            ),
        )
    )
    writer = Writer()

    complete_results(writer, migration)

    assert writer.batch_sizes == [100, 100, 1]
    assert writer.replace_values == [False, False, False]
    assert {update["id"] for update in writer.updates} == {item.destination_id for item in items}
    for update in writer.updates:
        assert set(update) == {"id", "properties"}
        assert update["properties"][STATUS] == COMPLETE
        assert update["properties"][COMPLETED_AT]


@pytest.mark.parametrize(
    "response",
    [
        WriteResponse(),
        WriteResponse(failed=[{"id": "d"}]),
        WriteResponse(error=ApiError(name="rejected")),
    ],
)
def test_completion_errors_are_not_silently_accepted(response: WriteResponse) -> None:
    with pytest.raises(ValueError, match="Failed to update results.*d"):
        complete_results(
            Writer(response),
            _migration(MigratedItem(source_id="s", destination_id="d"), file_results={}),
        )


def test_task_marks_results_complete_even_without_reassignments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    writer = Writer()
    monkeypatch.setattr(
        "slcli.migration.testmonitor.file_references_task.resolve_migration_connection",
        lambda profile: MigrationConnection(profile, "https://destination", {}),
    )
    monkeypatch.setattr(
        "slcli.migration.testmonitor.file_references_task.TestMonitorWriter",
        lambda connection: writer,
    )
    repair_file_references_task.fn(
        "run",
        "source",
        "destination",
        FileTransfer(),
        _migration(MigratedItem(source_id="s", destination_id="d"), file_results={}),
    )
    assert writer.updates[0]["id"] == "d"
    assert writer.updates[0]["properties"][STATUS] == COMPLETE
    assert writer.replace_values == [False]
