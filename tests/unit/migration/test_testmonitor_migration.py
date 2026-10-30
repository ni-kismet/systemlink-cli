"""Unit tests for Test Monitor batch migration logic."""

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Dict, Iterable, List, Optional, Sequence, Set

import pytest
import requests

from slcli.migration.annotations import (
    COMPLETE,
    INCOMPLETE,
    MIGRATION_ID,
    SOURCE_HOSTNAME,
    SOURCE_ID,
    STATUS,
)
from slcli.migration.testmonitor import client, migration
from slcli.migration.testmonitor.migration import (
    DUPLICATE_PART_NUMBER,
    MigrationContext,
    migrate_products,
    migrate_results,
    literal_id_filter,
)
from slcli.migration.testmonitor.models import DiscoveredProduct, DiscoveredResult
from slcli.migration.testmonitor.records import Result
from slcli.migration.testmonitor.writer import ApiError, Record, WriteResponse
from slcli.migration.workspaces import MappedWorkspace, WorkspaceMapping

CONTEXT = MigrationContext(
    migration_id="mig-1",
    source_hostname="source.example",
    mapping=WorkspaceMapping(
        workspaces=(
            MappedWorkspace(
                source_name="Lab", source_id="lab", destination_name="Dest", destination_id="dest"
            ),
        )
    ),
)
NOW = datetime(2024, 1, 1, tzinfo=timezone.utc)


def _product(product_id: str, workspace: str = "Lab") -> DiscoveredProduct:
    return DiscoveredProduct(id=product_id, workspace=workspace)


def _result(result_id: str, workspace: str = "Lab") -> DiscoveredResult:
    return DiscoveredResult(
        id=result_id, product_id=None, workspace=workspace, status="PASSED", updated_at=NOW
    )


def _http_error(status: int) -> requests.HTTPError:
    response = requests.Response()
    response.status_code = status
    return requests.HTTPError(f"{status} Error", response=response)


@dataclass
class FakeSource:
    """Serves source records by collection and records each query."""

    records: Dict[str, List[Record]] = field(default_factory=dict)
    steps_error: Optional[requests.RequestException] = None

    def query_products(self) -> Iterable[client.Product]:
        """Migration never queries modeled products."""
        raise NotImplementedError

    def query_results(
        self, filter_expr: Optional[str] = None, substitutions: Optional[Sequence[str]] = None
    ) -> Iterable[client.Result]:
        """Migration never queries modeled results."""
        raise NotImplementedError

    def query_records(
        self, collection: str, filter_expr: str, substitutions: Sequence[object]
    ) -> Iterable[Record]:
        if collection == "steps":
            if self.steps_error is not None:
                raise self.steps_error
            [result_id] = substitutions
            return [s for s in self.records.get("steps", []) if s["resultId"] == result_id]
        assert not substitutions
        ids = re.findall(r'id == "([^"]+)"', filter_expr)
        return [r for r in self.records.get(collection, []) if r["id"] in ids]


@dataclass
class FakeDestination:
    """Creates records with generated IDs, optionally rejecting some by source ID."""

    existing_part_numbers: Set[str] = field(default_factory=set)
    reject: Set[str] = field(default_factory=set)
    raise_on: Dict[str, requests.RequestException] = field(default_factory=dict)
    products: List[Record] = field(default_factory=list)
    results: List[Record] = field(default_factory=list)
    step_calls: List[List[Record]] = field(default_factory=list)
    updates: List[Record] = field(default_factory=list)

    def _create(self, kind: str, records: Sequence[Record], store: List[Record]) -> WriteResponse:
        if kind in self.raise_on:
            raise self.raise_on[kind]
        created: List[Record] = []
        failed: List[Record] = []
        inner: List[ApiError] = []
        for record in records:
            if record.get("partNumber") in self.existing_part_numbers and kind == "products":
                failed.append(record)
                inner.append(ApiError(name=DUPLICATE_PART_NUMBER, args=[record["partNumber"]]))
            elif record["properties"][SOURCE_ID] in self.reject:
                failed.append(record)
                inner.append(ApiError(name="Rejected"))
            else:
                new = {**record, "id": f"new-{record['properties'][SOURCE_ID]}"}
                store.append(new)
                created.append(new)
        return WriteResponse(created, failed, ApiError(inner_errors=inner) if inner else None)

    def create_products(self, products: Sequence[Record]) -> WriteResponse:
        return self._create("products", products, self.products)

    def create_results(self, results: Sequence[Record]) -> WriteResponse:
        return self._create("results", results, self.results)

    def create_steps(self, steps: Sequence[Record]) -> WriteResponse:
        self.step_calls.append(list(steps))
        if "steps" in self.raise_on:
            raise self.raise_on["steps"]
        created: List[Record] = []
        failed: List[Record] = []
        for step in steps:
            source_id = step["properties"][SOURCE_ID]
            if source_id in self.reject:
                failed.append(step)
                continue
            created.append(step)
        error = ApiError(inner_errors=[ApiError(name="StepRejected")]) if failed else None
        return WriteResponse(created, failed, error)

    def update_results(self, results: Sequence[Record]) -> WriteResponse:
        if "update" in self.raise_on:
            raise self.raise_on["update"]
        self.updates.extend(results)
        return WriteResponse(list(results))


def _source_product(product_id: str, part_number: str) -> Record:
    return {
        "id": product_id,
        "partNumber": part_number,
        "name": f"Name {part_number}",
        "workspace": "lab",
        "fileIds": ["f1"],
        "properties": {"custom": "kept", MIGRATION_ID: "stale"},
    }


def _source_result(result_id: str) -> Record:
    return {
        "id": result_id,
        "partNumber": "PN-1",
        "status": {"statusType": "PASSED", "statusName": "Passed"},
        "programName": "Program",
        "workspace": "lab",
        "fileIds": ["f1"],
        "dataTableIds": ["t1"],
        "properties": {"custom": "kept"},
    }


def _step(step_id: str, result_id: str, *ancestors: str) -> Record:
    """Return a source step under ``ancestors``, which default to the ``root`` pseudo-parent."""
    path = ancestors or ("root",)
    return {
        "stepId": step_id,
        "resultId": result_id,
        "name": step_id,
        "parentId": path[-1],
        "pathIds": [*path, step_id],
    }


def test_products_are_copied_annotated_and_mapped() -> None:
    """Products land in the mapped workspace with source identity, without other fields."""
    source = FakeSource({"products": [_source_product("p1", "PN-1")]})
    destination = FakeDestination()

    result = migrate_products(source, destination, CONTEXT, 0, [_product("p1")])

    assert [(m.source_id, m.destination_id) for m in result.migrated] == [("p1", "new-p1")]
    [created] = destination.products
    assert created["workspace"] == "dest"
    assert created["partNumber"] == "PN-1"
    assert "fileIds" not in created
    assert created["properties"]["custom"] == "kept"
    assert created["properties"][MIGRATION_ID] == "mig-1"
    assert created["properties"][SOURCE_HOSTNAME] == "source.example"


def test_product_part_number_conflict_is_skipped_and_reported() -> None:
    """A duplicate part number rejected by the destination is reported as a conflict."""
    source = FakeSource(
        {"products": [_source_product("p1", "PN-1"), _source_product("p2", "PN-2")]}
    )
    destination = FakeDestination(existing_part_numbers={"PN-1"})

    result = migrate_products(source, destination, CONTEXT, 0, [_product("p1"), _product("p2")])

    assert [m.source_id for m in result.migrated] == ["p2"]
    assert not result.failed
    [conflict] = result.conflicts
    assert conflict.model_dump() == {
        "source_id": "p1",
        "part_number": "PN-1",
        "expected_workspace": "Dest",
    }


def test_product_partial_failure_and_missing_records_are_reported() -> None:
    """Rejected and vanished products fail individually."""
    source = FakeSource({"products": [_source_product("p1", "PN-1")]})
    destination = FakeDestination(reject={"p1"})

    result = migrate_products(source, destination, CONTEXT, 2, [_product("p1"), _product("gone")])

    assert result.batch == 2
    assert not result.migrated
    failures = {f.source_id: (f.stage, f.error_type, f.detail) for f in result.failed}
    assert failures == {
        "gone": ("fetch", "SourceRecordNotFound", "gone"),
        "p1": ("create", "NotCreated", "Rejected"),
    }


def test_unmapped_product_workspace_fails_the_batch() -> None:
    """Discovery only yields mapped workspaces, so an unmapped one is a bug."""
    source = FakeSource({"products": [_source_product("p1", "PN-1")]})

    with pytest.raises(KeyError):
        migrate_products(
            source, FakeDestination(), CONTEXT, 0, [_product("p1", workspace="Unmapped")]
        )


def test_product_request_error_fails_the_batch() -> None:
    """A create request that fails as a whole fails the batch."""
    source = FakeSource({"products": [_source_product("p1", "PN-1")]})
    destination = FakeDestination(raise_on={"products": _http_error(500)})

    with pytest.raises(requests.HTTPError):
        migrate_products(source, destination, CONTEXT, 0, [_product("p1")])


def test_result_with_steps_is_completed() -> None:
    """A result is created incomplete, its step tree is remapped, then it is completed."""
    source = FakeSource(
        {
            "results": [_source_result("r1")],
            "steps": [
                _step("grandchild", "r1", "root", "parent", "child"),
                _step("child", "r1", "root", "parent"),
                _step("parent", "r1"),
            ],
        }
    )
    destination = FakeDestination()

    batch = migrate_results(source, destination, CONTEXT, 0, [_result("r1")])

    assert not batch.failed
    [migrated] = batch.migrated
    assert (migrated.destination_id, migrated.steps) == ("new-r1", 3)
    [created] = destination.results
    assert created["properties"][STATUS] == INCOMPLETE
    assert "fileIds" not in created and "dataTableIds" not in created
    [call] = destination.step_calls
    source_ids = {s["stepId"]: s["properties"][SOURCE_ID] for s in call}
    assert [
        (source_ids[s["stepId"]], source_ids.get(s["parentId"], s["parentId"])) for s in call
    ] == [
        ("parent", "root"),
        ("child", "parent"),
        ("grandchild", "child"),
    ]
    assert not {"parent", "child", "grandchild"} & set(source_ids)
    assert all("pathIds" not in s and s["resultId"] == "new-r1" for s in call)
    [update] = destination.updates
    assert update["id"] == "new-r1"
    assert update["properties"][STATUS] == COMPLETE


def test_step_failure_leaves_result_incomplete() -> None:
    """A rejected step stops its result, which is reported failed and never completed."""
    source = FakeSource(
        {
            "results": [_source_result("r1")],
            "steps": [_step("parent", "r1"), _step("child", "r1", "root", "parent")],
        }
    )
    destination = FakeDestination(reject={"parent"})

    batch = migrate_results(source, destination, CONTEXT, 0, [_result("r1")])

    assert not batch.migrated
    [failure] = batch.failed
    assert (failure.stage, failure.error_type, failure.destination_id) == (
        "complete",
        "NotCreated",
        "new-r1",
    )
    assert failure.detail == "1 of 2 steps created; StepRejected"
    assert len(destination.step_calls) == 1
    assert not destination.updates


def test_step_query_and_completion_errors_are_reported() -> None:
    """Errors after the result is created report its destination ID."""
    source = FakeSource({"results": [_source_result("r1")]}, steps_error=_http_error(503))
    batch = migrate_results(source, FakeDestination(), CONTEXT, 0, [_result("r1")])
    [failure] = batch.failed
    assert (failure.stage, failure.detail, failure.destination_id) == (
        "complete",
        "503 Error",
        "new-r1",
    )

    destination = FakeDestination(raise_on={"update": _http_error(500)})
    source = FakeSource({"results": [_source_result("r1")]})
    batch = migrate_results(source, destination, CONTEXT, 0, [_result("r1")])
    [failure] = batch.failed
    assert (failure.stage, failure.detail) == ("complete", "500 Error")


def test_step_with_unknown_parent_fails_the_result() -> None:
    """A parent outside the result other than ``root`` is a programming error."""
    source = FakeSource(
        {"results": [_source_result("r1")], "steps": [_step("c", "r1", "root", "gone")]}
    )
    destination = FakeDestination()

    batch = migrate_results(source, destination, CONTEXT, 0, [_result("r1")])

    assert batch.failed[0].error_type == "KeyError"
    assert not destination.step_calls


def test_steps_are_created_in_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    """Steps are split into bounded requests with parents in earlier chunks."""
    monkeypatch.setattr(migration, "STEP_CHUNK_SIZE", 2)
    source = FakeSource(
        {
            "results": [_source_result("r1")],
            "steps": [
                _step("c", "r1", "root", "p0"),
                *(_step(f"p{i}", "r1") for i in range(4)),
            ],
        }
    )
    destination = FakeDestination()

    batch = migrate_results(source, destination, CONTEXT, 0, [_result("r1")])

    assert [[s["properties"][SOURCE_ID] for s in call] for call in destination.step_calls] == [
        ["p0", "p1"],
        ["p2", "p3"],
        ["c"],
    ]
    assert batch.migrated[0].steps == 5


def test_literal_id_filter_rejects_non_server_ids() -> None:
    """Only server-generated ID characters can be inlined."""
    assert literal_id_filter(["a-1", "B2"]) == 'id == "a-1" || id == "B2"'
    with pytest.raises(ValueError):
        literal_id_filter(['x" || true || id == "y'])


def test_null_source_properties_become_empty_strings() -> None:
    """Null property values, which destinations reject, keep their key with an empty value."""
    record = Result.model_validate({"id": "r1", "properties": {"kept": "v", "empty": None}})

    assert record.properties == {"kept": "v", "empty": ""}


def test_create_request_passes_unknown_fields_and_nulls_through() -> None:
    """Undeclared fields and nulls round-trip; server-owned fields are dropped."""
    record = Result.model_validate(
        {"id": "r1", "updatedAt": "t", "fileIds": ["f"], "custom": {"x": 1}, "partNumber": None}
    )

    assert record.create_request({"workspace": "w"}) == {
        "custom": {"x": 1},
        "partNumber": None,
        "workspace": "w",
    }


def test_large_batches_are_fetched_in_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    """Source lookups are split to bound filter size."""
    monkeypatch.setattr(migration, "FILTER_CHUNK_SIZE", 2)
    products = [_source_product(f"p{i}", f"PN-{i}") for i in range(5)]
    destination = FakeDestination()

    result = migrate_products(
        FakeSource({"products": products}),
        destination,
        CONTEXT,
        0,
        [_product(f"p{i}") for i in range(5)],
    )

    assert len(result.migrated) == 5
