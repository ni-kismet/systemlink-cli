"""Migrate Test Monitor products, results, and steps one batch at a time.

Records pass through unchanged apart from server-owned fields, destination
routing, and source identity annotations. File and data table references are
not migrated yet.
"""

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import (
    Callable,
    Dict,
    Iterator,
    List,
    Optional,
    Sequence,
    Tuple,
    Type,
    TypeVar,
)

from slcli.migration.annotations import (
    COMPLETE,
    COMPLETED_AT,
    INCOMPLETE,
    MIGRATION_ID,
    SOURCE_HOSTNAME,
    SOURCE_ID,
    STARTED_AT,
    STATUS,
)
from slcli.migration.testmonitor.client import TestMonitorSource
from slcli.migration.testmonitor.models import (
    BatchResult,
    DiscoveredProduct,
    DiscoveredResult,
    FailedItem,
    MigratedItem,
    ProductConflict,
)
from slcli.migration.testmonitor.records import Product, Result, Step, TestMonitorRecord
from slcli.migration.testmonitor.writer import DestinationWriter, Record, WriteResponse, error_names
from slcli.migration.workspaces import WorkspaceMapping

_logger = logging.getLogger(__name__)

STEP_CHUNK_SIZE = 500
FILTER_CHUNK_SIZE = 100
_SERVER_ID = re.compile(r"^[A-Za-z0-9-]+$")


class SourceRecordNotFound(LookupError):
    """A discovered source record no longer exists."""


class NotCreated(RuntimeError):
    """The destination did not create or update an item it was sent."""


class InvalidStepHierarchy(ValueError):
    """Source steps whose parents form a cycle."""


class ProductConflictError(Exception):
    """A product whose part number already exists on the destination."""

    def __init__(self, conflict: ProductConflict) -> None:
        """Record the conflicting destination product."""
        super().__init__(conflict.part_number)
        self.conflict = conflict


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class MigrationContext:
    """Identity and workspace routing shared by every batch of one migration."""

    migration_id: str
    source_hostname: str
    mapping: WorkspaceMapping

    def annotate(self, record: TestMonitorRecord, **extra: str) -> Dict[str, str]:
        """Return a record's properties with its source identity added."""
        return {
            **record.properties,
            SOURCE_ID: record.key,
            SOURCE_HOSTNAME: self.source_hostname,
            MIGRATION_ID: self.migration_id,
            STARTED_AT: _now(),
            **extra,
        }


_T = TypeVar("_T")
_R = TypeVar("_R", bound=TestMonitorRecord)


def _chunks(items: Sequence[_T], size: int) -> Iterator[Sequence[_T]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


def literal_id_filter(ids: Sequence[str]) -> str:
    """Return a filter matching server-generated IDs without substitutions.

    SystemLink Server ``query-products`` does not accept substitutions, so IDs
    are validated and inlined for every collection.

    Raises:
        ValueError: If an ID is not a server-generated identifier.
    """
    for item in ids:
        if not _SERVER_ID.match(item):
            raise ValueError(f"Unexpected resource ID format: {item!r}")
    return " || ".join(f'id == "{item}"' for item in ids)


def _fetch_by_id(
    source: TestMonitorSource, collection: str, model: Type[_R], ids: Sequence[str]
) -> Dict[str, _R]:
    records = (
        model.model_validate(record)
        for chunk in _chunks(ids, FILTER_CHUNK_SIZE)
        for record in source.query_records(collection, literal_id_filter(chunk), [])
    )
    return {record.key: record for record in records}


def _lookup(records: Dict[str, _R], source_id: str) -> _R:
    if source_id not in records:
        raise SourceRecordNotFound(source_id)
    return records[source_id]


def _failed(
    source_id: str, stage: str, exc: Exception, destination_id: Optional[str] = None
) -> FailedItem:
    return FailedItem(
        source_id=source_id,
        stage=stage,
        error_type=type(exc).__name__,
        detail=str(exc) or None,
        destination_id=destination_id,
    )


def _created_ids(model: Type[TestMonitorRecord], response: WriteResponse) -> Dict[str, str]:
    """Map each created record's source ID annotation to its destination ID."""
    created = (model.model_validate(record) for record in response.created)
    return {record.properties[SOURCE_ID]: record.key for record in created}


def _create(
    create: Callable[[Sequence[Record]], WriteResponse],
    model: Type[TestMonitorRecord],
    requests_by_source_id: Dict[str, Record],
) -> Tuple[Dict[str, str], List[FailedItem]]:
    """Create records in one request and split the response by source ID.

    Raises:
        requests.RequestException: If the request fails as a whole.
    """
    if not requests_by_source_id:
        return {}, []
    response = create(list(requests_by_source_id.values()))
    created = _created_ids(model, response)
    error = NotCreated(", ".join(error_names(response.error)))
    failed = [
        _failed(source_id, "create", error)
        for source_id in requests_by_source_id
        if source_id not in created
    ]
    return created, failed


def _product_request(
    discovered: DiscoveredProduct,
    records: Dict[str, Product],
    existing: Dict[str, Product],
    context: MigrationContext,
) -> Record:
    product = _lookup(records, discovered.id)
    workspace = context.mapping.workspace(discovered.workspace)
    match = existing.get(product.part_number)
    if match is not None:
        raise ProductConflictError(
            ProductConflict(
                source_id=product.id,
                part_number=product.part_number,
                expected_workspace=workspace.destination_name,
                existing_id=match.id,
                existing_workspace_id=match.workspace,
                existing_migration_id=match.properties.get(MIGRATION_ID),
                existing_source_id=match.properties.get(SOURCE_ID),
            )
        )
    return product.create_request(
        {"workspace": workspace.destination_id, "properties": context.annotate(product)}
    )


def migrate_products(
    source: TestMonitorSource,
    destination: DestinationWriter,
    context: MigrationContext,
    batch: int,
    products: Sequence[DiscoveredProduct],
) -> BatchResult:
    """Migrate a batch of products into their mapped destination workspaces.

    A product whose part number already exists on the destination is not changed
    and is reported as a conflict. Other per-product errors are reported as
    failures.

    Raises:
        requests.RequestException: If a batch-wide read or create fails.
    """
    records = _fetch_by_id(source, "products", Product, [p.id for p in products])
    part_numbers = sorted({product.part_number for product in records.values()})
    existing = {
        product.part_number: product
        for product in map(
            Product.model_validate, destination.query_products_by_part_number(part_numbers)
        )
    }
    failed: List[FailedItem] = []
    conflicts: List[ProductConflict] = []
    to_create: Dict[str, Record] = {}
    for product in products:
        try:
            to_create[product.id] = _product_request(product, records, existing, context)
        except ProductConflictError as exc:
            conflicts.append(exc.conflict)
        except Exception as exc:
            failed.append(_failed(product.id, "prepare", exc))
    created, create_failed = _create(destination.create_products, Product, to_create)
    return BatchResult(
        resource="products",
        batch=batch,
        migrated=tuple(MigratedItem(source_id=s, destination_id=d) for s, d in created.items()),
        failed=tuple(failed + create_failed),
        conflicts=tuple(conflicts),
    )


def _result_request(
    discovered: DiscoveredResult, records: Dict[str, Result], context: MigrationContext
) -> Record:
    result = _lookup(records, discovered.id)
    return result.create_request(
        {
            "workspace": context.mapping.workspace(discovered.workspace).destination_id,
            "properties": context.annotate(result, **{STATUS: INCOMPLETE}),
        }
    )


def migrate_results(
    source: TestMonitorSource,
    destination: DestinationWriter,
    context: MigrationContext,
    batch: int,
    results: Sequence[DiscoveredResult],
) -> BatchResult:
    """Migrate a batch of results, each with all of its steps.

    A result is created ``INCOMPLETE`` and marked ``COMPLETE`` only after all of
    its steps migrate. A result whose steps fail stays ``INCOMPLETE`` and is
    reported as failed with its destination ID.

    Raises:
        requests.RequestException: If a batch-wide read or create fails.
    """
    records = _fetch_by_id(source, "results", Result, [r.id for r in results])
    failed: List[FailedItem] = []
    to_create: Dict[str, Record] = {}
    for result in results:
        try:
            to_create[result.id] = _result_request(result, records, context)
        except Exception as exc:
            failed.append(_failed(result.id, "prepare", exc))
    created, create_failed = _create(destination.create_results, Result, to_create)
    failed.extend(create_failed)
    migrated: List[MigratedItem] = []
    for source_id, destination_id in created.items():
        try:
            steps = _complete_result(source, destination, context, source_id, destination_id)
        except Exception as exc:
            failed.append(_failed(source_id, "complete", exc, destination_id))
        else:
            migrated.append(
                MigratedItem(source_id=source_id, destination_id=destination_id, steps=steps)
            )
    return BatchResult(
        resource="results", batch=batch, migrated=tuple(migrated), failed=tuple(failed)
    )


def _complete_result(
    source: TestMonitorSource,
    destination: DestinationWriter,
    context: MigrationContext,
    source_id: str,
    destination_id: str,
) -> int:
    """Migrate a created result's steps, then mark the result complete.

    Returns:
        The number of steps migrated.
    """
    steps = [
        Step.model_validate(record)
        for record in source.query_records("steps", "resultId == @0", [source_id])
    ]
    _migrate_steps(destination, context, destination_id, steps)
    response = destination.update_results(
        [{"id": destination_id, "properties": {STATUS: COMPLETE, COMPLETED_AT: _now()}}]
    )
    if response.failed or response.error:
        raise NotCreated(", ".join(error_names(response.error)))
    return len(steps)


def order_steps(steps: Sequence[Step]) -> List[List[Step]]:
    """Group steps into levels so every parent precedes its children.

    Parents outside ``steps``, such as the ``root`` pseudo-parent, are level 0.

    Raises:
        InvalidStepHierarchy: If the source step hierarchy has a cycle.
    """
    by_id = {step.step_id: step for step in steps}
    depths: Dict[str, int] = {}

    def depth(step_id: str) -> int:
        chain: List[str] = []
        current: Optional[str] = step_id
        while current is not None and current in by_id and current not in depths:
            if current in chain:
                raise InvalidStepHierarchy(f"Step hierarchy has a cycle at '{current}'")
            chain.append(current)
            current = by_id[current].parent_id
        base = depths.get(current, -1) if current is not None else -1
        for offset, item in enumerate(reversed(chain), start=1):
            depths[item] = base + offset
        return depths[step_id]

    levels: Dict[int, List[Step]] = {}
    for step_id, step in by_id.items():
        levels.setdefault(depth(step_id), []).append(step)
    return [levels[level] for level in sorted(levels)]


def _step_request(
    step: Step,
    context: MigrationContext,
    destination_result_id: str,
    destination_step_ids: Dict[str, str],
) -> Record:
    """Return a create request for a step whose parent, if migrated, is already created."""
    overrides: Record = {"resultId": destination_result_id, "properties": context.annotate(step)}
    if step.parent_id is not None:
        # Parents outside the result, such as ``root``, keep their ID.
        overrides["parentId"] = destination_step_ids.get(step.parent_id, step.parent_id)
    return step.create_request(overrides)


def _migrate_steps(
    destination: DestinationWriter,
    context: MigrationContext,
    destination_result_id: str,
    steps: Sequence[Step],
) -> None:
    """Create every step parent-first, remapping parent IDs to destination step IDs.

    Raises:
        NotCreated: If the destination did not create every step.
    """
    destination_step_ids: Dict[str, str] = {}
    for level in order_steps(steps):
        for chunk in _chunks(level, STEP_CHUNK_SIZE):
            response = destination.create_steps(
                [
                    _step_request(step, context, destination_result_id, destination_step_ids)
                    for step in chunk
                ]
            )
            destination_step_ids.update(_created_ids(Step, response))
            if any(step.step_id not in destination_step_ids for step in chunk):
                errors = ", ".join(error_names(response.error))
                raise NotCreated(
                    f"{len(destination_step_ids)} of {len(steps)} steps created; {errors}"
                )


def log_batch(result: BatchResult) -> None:
    """Log a batch outcome with the IDs needed to follow up."""
    level = logging.WARNING if result.failed or result.conflicts else logging.INFO
    _logger.log(
        level,
        "Batch %s[%d] completed: migrated=%d failed=%d conflicts=%d",
        result.resource,
        result.batch,
        len(result.migrated),
        len(result.failed),
        len(result.conflicts),
    )
    for item in result.failed:
        _logger.warning(
            "Failed %s %s: stage=%s error=%s detail=%s destination_id=%s",
            result.resource,
            item.source_id,
            item.stage,
            item.error_type,
            item.detail,
            item.destination_id,
        )
    for conflict in result.conflicts:
        _logger.warning(
            "Product conflict %s: part_number=%s expected_workspace=%s existing_id=%s "
            "existing_workspace=%s existing_migration_id=%s existing_source_id=%s",
            conflict.source_id,
            conflict.part_number,
            conflict.expected_workspace,
            conflict.existing_id,
            conflict.existing_workspace_id,
            conflict.existing_migration_id,
            conflict.existing_source_id,
        )
