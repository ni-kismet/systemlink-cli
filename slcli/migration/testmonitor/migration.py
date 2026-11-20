"""Migrate Test Monitor products, results, and steps one batch at a time.

Records pass through unchanged apart from server-owned fields, destination
routing, source identity annotations, and mapped file references. Data table
references are not migrated yet.
"""

import logging
import re
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import (
    Dict,
    Iterable,
    Iterator,
    List,
    Mapping,
    NamedTuple,
    Optional,
    Sequence,
    Set,
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
    UNRESOLVED_FILE_IDS,
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
from slcli.migration.testmonitor.writer import ApiError, DestinationWriter, WriteResponse
from slcli.migration.workspaces import WorkspaceMapping

_logger = logging.getLogger(__name__)

STEP_CHUNK_SIZE = 500
ROOT_STEP_ID = "root"
FILTER_CHUNK_SIZE = 100
_SERVER_ID = re.compile(r"^[A-Za-z0-9-]+$")


DUPLICATE_PART_NUMBER = "TestMonitor.DuplicatePartNumber"


class SourceRecordNotFound(LookupError):
    """A discovered source record no longer exists."""


class NotCreated(RuntimeError):
    """The destination did not create or update an item it was sent."""


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


def _missing(ids: Iterable[str], records: Dict[str, _R]) -> List[FailedItem]:
    """Report discovered items whose source record no longer exists."""
    return [
        _failed(source_id, "fetch", SourceRecordNotFound(source_id))
        for source_id in ids
        if source_id not in records
    ]


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


def _not_created(
    source_ids: Iterable[str], created: Dict[str, str], error: Optional[ApiError]
) -> List[FailedItem]:
    exc = NotCreated(", ".join(error.names() if error else []))
    return [
        _failed(source_id, "create", exc) for source_id in source_ids if source_id not in created
    ]


def _duplicate_part_numbers(error: Optional[ApiError]) -> Set[str]:
    inner = error.inner_errors if error else []
    return {str(arg) for e in inner if e.name == DUPLICATE_PART_NUMBER for arg in e.args}


def migrate_products(
    source: TestMonitorSource,
    destination: DestinationWriter,
    context: MigrationContext,
    batch: int,
    products: Sequence[DiscoveredProduct],
) -> BatchResult:
    """Migrate a batch of products into their mapped destination workspaces.

    A product whose part number already exists on the destination is not changed
    and is reported as a conflict.

    Raises:
        requests.RequestException: If a batch-wide read or create fails.
        KeyError: If a product's workspace is not mapped.
    """
    records = _fetch_by_id(source, "products", Product, [p.id for p in products])
    workspaces = {p.id: context.mapping.workspace(p.workspace) for p in products}
    product_id_to_creation_request_map = {
        record.id: _build_creation_request(record, workspaces, context)
        for record in records.values()
    }
    creation_requests = list(product_id_to_creation_request_map.values())

    response = destination.create_products(creation_requests)
    created = _created_ids(Product, response)
    duplicates = _duplicate_part_numbers(response.error)
    conflicts = [
        ProductConflict(
            source_id=product.id,
            part_number=product.part_number,
            expected_workspace=workspaces[product.id].destination_name,
        )
        for product in records.values()
        if product.id not in created and product.part_number in duplicates
    ]
    conflicted = {conflict.source_id for conflict in conflicts}
    return BatchResult(
        resource="products",
        batch=batch,
        migrated=tuple(MigratedItem(source_id=s, destination_id=d) for s, d in created.items()),
        failed=(
            *_missing(workspaces, records),
            *_not_created(
                set(product_id_to_creation_request_map) - conflicted, created, response.error
            ),
        ),
        conflicts=tuple(conflicts),
    )


def migrate_results(
    source: TestMonitorSource,
    destination: DestinationWriter,
    context: MigrationContext,
    batch: int,
    results: Sequence[DiscoveredResult],
    file_id_map: Mapping[str, str],
) -> BatchResult:
    """Migrate a batch of results, each with all of its steps.

    A result is created ``INCOMPLETE`` and marked ``COMPLETE`` only after all of
    its steps migrate. A result whose steps fail stays ``INCOMPLETE`` and is
    reported as failed with its destination ID.

    Raises:
        requests.RequestException: If a batch-wide read or create fails.
    """
    records = _fetch_by_id(source, "results", Result, [r.id for r in results])
    workspaces = {r.id: context.mapping.workspace(r.workspace) for r in results}
    unresolved_by_result: Dict[str, tuple[str, ...]] = {}
    creation_requests: Dict[str, Dict[str, object]] = {}
    for result in records.values():
        file_ids = _classify_file_ids(result, file_id_map)
        unresolved_by_result[result.id] = file_ids.unresolved_ids
        extra_annotations = _build_result_annotations(result, file_ids.unresolved_ids)
        extra_overrides = {"fileIds": file_ids.destination_ids} if file_ids.destination_ids else {}
        creation_requests[result.id] = _build_creation_request(
            result, workspaces, context, extra_annotations, extra_overrides
        )

    response = destination.create_results(list(creation_requests.values()))
    created = _created_ids(Result, response)
    completion_result = _mark_results_complete(
        source, destination, context, created, unresolved_by_result
    )
    failed = tuple(
        *_missing(workspaces, records),
        *_not_created(creation_requests, created, response.error),
        *completion_result.failed,
    )

    return BatchResult(
        resource="results",
        batch=batch,
        migrated=completion_result.migrated,
        failed=failed,
    )


def _build_creation_request(
    record: TestMonitorRecord, workspaces, context, extra_annotations={}, extra_overrides={}
):
    return record.create_request(
        {
            "workspace": workspaces[record.id].destination_id,
            "properties": context.annotate(record, **extra_annotations),
            **extra_overrides,
        }
    )


def _build_result_annotations(result, unresolved_file_ids):
    extra_annotations = {STATUS: INCOMPLETE}
    if unresolved_file_ids:
        extra_annotations[UNRESOLVED_FILE_IDS] = ",".join(unresolved_file_ids)
        _logger.warning(
            "Result %s has unresolved source file IDs: %s", result.id, ",".join(unresolved_file_ids)
        )
    elif UNRESOLVED_FILE_IDS in result.properties:
        extra_annotations[UNRESOLVED_FILE_IDS] = ""
    return extra_annotations


class FilteredFileIds(NamedTuple):
    """Source file IDs split into migrated destination IDs and unresolved source IDs."""

    destination_ids: tuple[str, ...]
    unresolved_ids: tuple[str, ...]


def _classify_file_ids(result, file_id_map) -> FilteredFileIds:
    file_ids = _get_file_ids(result)
    return FilteredFileIds(
        destination_ids=tuple(file_id_map[fid] for fid in file_ids if fid in file_id_map),
        unresolved_ids=tuple(fid for fid in file_ids if fid not in file_id_map),
    )


def _get_file_ids(result) -> list[str]:
    file_ids = result.model_extra.get("fileIds", []) if result.model_extra else []
    if not isinstance(file_ids, list) or not all(isinstance(fid, str) for fid in file_ids):
        raise ValueError(f"Invalid fileIds on source result {result.id!r}")
    return file_ids


class ResultCompletionOutput(NamedTuple):
    """Items migrated and failed while marking results complete."""

    migrated: tuple[MigratedItem, ...]
    failed: tuple[FailedItem, ...]


def _mark_results_complete(
    source, destination, context, created, unresolved_by_result
) -> ResultCompletionOutput:
    migrated: List[MigratedItem] = []
    failed: List[FailedItem] = []
    for source_id, destination_id in created.items():
        try:
            steps = _complete_result(source, destination, context, source_id, destination_id)
        except Exception as exc:
            failed.append(
                _failed(source_id, "complete", exc, destination_id).model_copy(
                    update={"unresolved_file_ids": unresolved_by_result[source_id]}
                )
            )
        else:
            migrated.append(
                MigratedItem(
                    source_id=source_id,
                    destination_id=destination_id,
                    steps=steps,
                    unresolved_file_ids=unresolved_by_result[source_id],
                )
            )
    return ResultCompletionOutput(migrated=tuple(migrated), failed=tuple(failed))


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
        raise NotCreated(", ".join(response.error.names() if response.error else []))
    return len(steps)


def _migrate_steps(
    destination: DestinationWriter,
    context: MigrationContext,
    destination_result_id: str,
    steps: Sequence[Step],
) -> None:
    """Create every step under the destination result with fresh step IDs.

    The destination accepts client-supplied step IDs and orders parents within a
    request, but a parent must exist before a later request references it. Sorting
    by path depth keeps each parent in the same or an earlier chunk than its children.
    Top-level steps keep the ``root`` pseudo-parent.

    Raises:
        KeyError: If a step's parent is not ``root`` or another step of the result.
        NotCreated: If the destination did not create every step.
    """
    step_ids = {ROOT_STEP_ID: ROOT_STEP_ID, **{step.step_id: str(uuid.uuid4()) for step in steps}}
    to_create = [
        step.create_request(
            {
                "stepId": step_ids[step.step_id],
                "parentId": step_ids[step.parent_id],
                "resultId": destination_result_id,
                "properties": context.annotate(step),
            }
        )
        for step in sorted(steps, key=lambda step: len(step.path_ids))
    ]
    created = 0
    for chunk in _chunks(to_create, STEP_CHUNK_SIZE):
        response = destination.create_steps(chunk)
        created += len(response.created)
        if response.failed or response.error:
            errors = ", ".join(response.error.names() if response.error else [])
            raise NotCreated(f"{created} of {len(steps)} steps created; {errors}")


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
            "Product conflict %s: part_number=%s expected_workspace=%s",
            conflict.source_id,
            conflict.part_number,
            conflict.expected_workspace,
        )
