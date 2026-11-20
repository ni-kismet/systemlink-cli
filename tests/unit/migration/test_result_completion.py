"""Tests for marking migrated test results complete."""

from typing import List, Sequence

import pytest

from slcli.migration.annotations import COMPLETE, COMPLETED_AT, STATUS
from slcli.migration.testmonitor.completion import complete_results
from slcli.migration.testmonitor.models import (
    BatchResult,
    FailedItem,
    MigratedItem,
    TestMonitorMigration,
)
from slcli.migration.testmonitor.writer import ApiError, Record, WriteResponse


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


def _migration(*items: MigratedItem) -> TestMonitorMigration:
    return TestMonitorMigration(results=(BatchResult(resource="results", batch=0, migrated=items),))


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
            Writer(response), _migration(MigratedItem(source_id="s", destination_id="d"))
        )
