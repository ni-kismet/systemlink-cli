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
from slcli.migration.testmonitor import migration
from slcli.migration.testmonitor.migration import (
    MigrationContext,
    migrate_products,
    migrate_results,
    literal_id_filter,
    order_steps,
)
from slcli.migration.testmonitor.models import DiscoveredProduct, DiscoveredResult
from slcli.migration.testmonitor.writer import Record, WriteResponse
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

    existing_products: List[Record] = field(default_factory=list)
    reject: Set[str] = field(default_factory=set)
    raise_on: Dict[str, requests.RequestException] = field(default_factory=dict)
    honor_step_ids: bool = False
    products: List[Record] = field(default_factory=list)
    results: List[Record] = field(default_factory=list)
    step_calls: List[List[Record]] = field(default_factory=list)
    updates: List[Record] = field(default_factory=list)

    def query_products_by_part_number(self, part_numbers: Sequence[str]) -> List[Record]:
        return [p for p in self.existing_products if p["partNumber"] in part_numbers]

    def _create(self, kind: str, records: Sequence[Record], store: List[Record]) -> WriteResponse:
        if kind in self.raise_on:
            raise self.raise_on[kind]
        created: List[Record] = []
        failed: List[Record] = []
        for record in records:
            if record["properties"][SOURCE_ID] in self.reject:
                failed.append(record)
                continue
            new = {**record, "id": f"new-{record['properties'][SOURCE_ID]}"}
            store.append(new)
            created.append(new)
        error = {"innerErrors": [{"name": "Rejected"}]} if failed else None
        return WriteResponse(created, failed, error)

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
            step_id = step["stepId"] if self.honor_step_ids else f"dst-{source_id}"
            created.append({**step, "stepId": step_id})
        error = {"innerErrors": [{"name": "StepRejected"}]} if failed else None
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


def _step(step_id: str, result_id: str, parent: Optional[str] = "root") -> Record:
    step: Record = {"stepId": step_id, "resultId": result_id, "name": step_id}
    if parent is not None:
        step["parentId"] = parent
    return step


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
    """An existing destination part number is left unchanged and reported with context."""
    source = FakeSource(
        {"products": [_source_product("p1", "PN-1"), _source_product("p2", "PN-2")]}
    )
    destination = FakeDestination(
        existing_products=[
            {
                "id": "existing",
                "partNumber": "PN-1",
                "workspace": "other",
                "properties": {MIGRATION_ID: "older", SOURCE_ID: "p0"},
            }
        ]
    )

    result = migrate_products(source, destination, CONTEXT, 0, [_product("p1"), _product("p2")])

    assert [m.source_id for m in result.migrated] == ["p2"]
    assert not result.failed
    [conflict] = result.conflicts
    assert conflict.model_dump() == {
        "source_id": "p1",
        "part_number": "PN-1",
        "expected_workspace": "Dest",
        "existing_id": "existing",
        "existing_workspace_id": "other",
        "existing_migration_id": "older",
        "existing_source_id": "p0",
    }


def test_product_partial_failure_and_missing_records_are_reported() -> None:
    """Rejected, vanished, and unmapped products fail individually."""
    source = FakeSource(
        {"products": [_source_product("p1", "PN-1"), _source_product("p3", "PN-3")]}
    )
    destination = FakeDestination(reject={"p1"})

    result = migrate_products(
        source,
        destination,
        CONTEXT,
        2,
        [_product("p1"), _product("gone"), _product("p3", workspace="Unmapped")],
    )

    assert result.batch == 2
    assert not result.migrated
    failures = {f.source_id: (f.stage, f.error_type, f.detail) for f in result.failed}
    assert failures == {
        "gone": ("prepare", "SourceRecordNotFound", "gone"),
        "p3": ("prepare", "KeyError", "\"Workspace 'Unmapped' is not mapped\""),
        "p1": ("create", "NotCreated", "Rejected"),
    }


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
                _step("child", "r1", parent="parent"),
                _step("parent", "r1"),
                _step("grandchild", "r1", parent="child"),
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
    assert [[s["properties"][SOURCE_ID] for s in call] for call in destination.step_calls] == [
        ["parent"],
        ["child"],
        ["grandchild"],
    ]
    parents = [call[0]["parentId"] for call in destination.step_calls]
    assert parents == ["root", "dst-parent", "dst-child"]
    assert all(call[0]["resultId"] == "new-r1" for call in destination.step_calls)
    [update] = destination.updates
    assert update["id"] == "new-r1"
    assert update["properties"][STATUS] == COMPLETE


def test_step_failure_leaves_result_incomplete() -> None:
    """A rejected step stops its result, which is reported failed and never completed."""
    source = FakeSource(
        {
            "results": [_source_result("r1")],
            "steps": [_step("parent", "r1"), _step("child", "r1", parent="parent")],
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
    assert failure.detail == "0 of 2 steps created; StepRejected"
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


def test_client_supplied_step_ids_are_used_when_honored() -> None:
    """Parent remapping uses whatever step IDs the destination returns."""
    source = FakeSource(
        {
            "results": [_source_result("r1")],
            "steps": [_step("parent", "r1"), _step("child", "r1", parent="parent")],
        }
    )
    destination = FakeDestination(honor_step_ids=True)

    migrate_results(source, destination, CONTEXT, 0, [_result("r1")])

    assert destination.step_calls[1][0]["parentId"] == "parent"


def test_steps_are_created_in_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    """Large levels are split into bounded requests."""
    monkeypatch.setattr(migration, "STEP_CHUNK_SIZE", 2)
    source = FakeSource(
        {
            "results": [_source_result("r1")],
            "steps": [_step(f"s{i}", "r1") for i in range(5)],
        }
    )
    destination = FakeDestination()

    batch = migrate_results(source, destination, CONTEXT, 0, [_result("r1")])

    assert [len(call) for call in destination.step_calls] == [2, 2, 1]
    assert batch.migrated[0].steps == 5


def test_order_steps_groups_levels_parent_first() -> None:
    """Steps with external parents form level zero; children follow their parents."""
    steps = [
        _step("c", "r", parent="b"),
        _step("b", "r", parent="a"),
        _step("a", "r"),
        _step("x", "r", parent=None),
    ]

    levels = order_steps(steps)

    assert [[s["stepId"] for s in level] for level in levels] == [["a", "x"], ["b"], ["c"]]


def test_order_steps_rejects_cycles() -> None:
    """A cyclic hierarchy cannot be created parent-first."""
    with pytest.raises(ValueError, match="cycle"):
        order_steps([_step("a", "r", parent="b"), _step("b", "r", parent="a")])


def test_cyclic_steps_fail_the_result() -> None:
    """An invalid step hierarchy is reported without writing steps."""
    source = FakeSource(
        {
            "results": [_source_result("r1")],
            "steps": [_step("a", "r1", parent="b"), _step("b", "r1", parent="a")],
        }
    )
    destination = FakeDestination()

    batch = migrate_results(source, destination, CONTEXT, 0, [_result("r1")])

    assert batch.failed[0].error_type == "InvalidStepHierarchy"
    assert not destination.step_calls


def test_literal_id_filter_rejects_non_server_ids() -> None:
    """Only server-generated ID characters can be inlined."""
    assert literal_id_filter(["a-1", "B2"]) == 'id == "a-1" || id == "B2"'
    with pytest.raises(ValueError):
        literal_id_filter(['x" || true || id == "y'])


def test_null_source_properties_are_dropped() -> None:
    """Null property values, which destinations reject, are not copied."""
    record = {"properties": {"kept": "v", "empty": None}}

    properties = CONTEXT.annotate(record, "p1")

    assert properties["kept"] == "v"
    assert "empty" not in properties


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
