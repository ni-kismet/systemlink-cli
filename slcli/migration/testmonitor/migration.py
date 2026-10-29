"""Migrate Test Monitor products, results, and steps one batch at a time.

Records are copied field-by-field from the source and annotated with their
source identity. File and data table references are not migrated yet.
"""

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import (
    Callable,
    Dict,
    Iterable,
    List,
    Optional,
    Protocol,
    Sequence,
    Tuple,
    Union,
)

import requests

from slcli.migration.testmonitor.models import (
    BatchResult,
    DiscoveredProduct,
    DiscoveredResult,
    FailedItem,
    MigratedItem,
    ProductConflict,
)
from slcli.migration.testmonitor.writer import Record, WriteResponse, error_names
from slcli.migration.workspaces import WorkspaceMapping

_logger = logging.getLogger(__name__)

SOURCE_ID = "Migration.SourceId"
SOURCE_HOSTNAME = "Migration.SourceHostname"
MIGRATION_ID = "Migration.Id"
STATUS = "Migration.Status"
STARTED_AT = "Migration.StartedAt"
COMPLETED_AT = "Migration.CompletedAt"
INCOMPLETE = "INCOMPLETE"
COMPLETE = "COMPLETE"

PRODUCT_FIELDS = ("partNumber", "name", "family", "keywords")
RESULT_FIELDS = (
    "programName",
    "status",
    "systemId",
    "hostName",
    "keywords",
    "serialNumber",
    "operator",
    "partNumber",
    "startedAt",
    "totalTimeInSeconds",
)
STEP_FIELDS = (
    "stepId",
    "name",
    "stepType",
    "status",
    "startedAt",
    "totalTimeInSeconds",
    "dataModel",
    "data",
    "inputs",
    "outputs",
    "keywords",
)
STEP_CHUNK_SIZE = 500


class SourceRecords(Protocol):
    """Complete source records by parameterized filter."""

    def query_records(
        self, collection: str, filter_expr: str, substitutions: Sequence[object]
    ) -> Iterable[Record]:
        """Return records of a collection matching a filter."""
        ...


class DestinationWriter(Protocol):
    """Destination reads and writes needed by migration."""

    def query_products_by_part_number(self, part_numbers: Sequence[str]) -> List[Record]:
        """Return destination products with any of the given part numbers."""
        ...

    def create_products(self, products: Sequence[Record]) -> WriteResponse:
        """Create products."""
        ...

    def create_results(self, results: Sequence[Record]) -> WriteResponse:
        """Create results."""
        ...

    def create_steps(self, steps: Sequence[Record]) -> WriteResponse:
        """Create steps."""
        ...

    def update_results(self, results: Sequence[Record]) -> WriteResponse:
        """Merge fields into results."""
        ...


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass(frozen=True)
class MigrationContext:
    """Identity and workspace routing shared by every batch of one migration."""

    migration_id: str
    source_hostname: str
    mapping: WorkspaceMapping

    def annotate(self, record: Record, source_id: str, **extra: str) -> Dict[str, str]:
        """Return a record's properties with its source identity added."""
        # Servers may hold null property values, which writes reject.
        properties = {
            key: value
            for key, value in (record.get("properties") or {}).items()
            if value is not None
        }
        properties.update(
            {
                SOURCE_ID: source_id,
                SOURCE_HOSTNAME: self.source_hostname,
                MIGRATION_ID: self.migration_id,
                STARTED_AT: _now(),
                **extra,
            }
        )
        return properties

    def workspace_name(self, destination_id: str) -> str:
        """Return the destination workspace name for an ID."""
        for workspace in self.mapping.workspaces:
            if workspace.destination_id == destination_id:
                return workspace.destination_name
        return destination_id


def _copy(record: Record, fields: Sequence[str]) -> Record:
    return {name: record[name] for name in fields if record.get(name) is not None}


def _request_failure(exc: requests.RequestException) -> Tuple[str, Optional[str]]:
    response = exc.response
    return type(exc).__name__, f"HTTP {response.status_code}" if response is not None else None


FILTER_CHUNK_SIZE = 100
_SERVER_ID = re.compile(r"^[A-Za-z0-9-]+$")


def contains_filter(field: str, values: Sequence[str]) -> Tuple[str, List[str]]:
    """Return a parameterized filter matching any of ``values`` in ``field``.

    Test Monitor rejects a list substitution such as ``@0.Contains(id)``.
    """
    placeholders = ",".join(f"@{index}" for index in range(len(values)))
    return f"new[]{{{placeholders}}}.Contains({field})", list(values)


def literal_id_filter(ids: Sequence[str]) -> str:
    """Return a filter matching server-generated IDs without substitutions.

    SystemLink Server ``query-products`` does not accept substitutions, so IDs
    are validated and inlined.

    Raises:
        ValueError: If an ID is not a server-generated identifier.
    """
    for item in ids:
        if not _SERVER_ID.match(item):
            raise ValueError(f"Unexpected resource ID format: {item!r}")
    return " || ".join(f'id == "{item}"' for item in ids)


def _fetch_by_id(source: SourceRecords, collection: str, ids: Sequence[str]) -> Dict[str, Record]:
    records: Dict[str, Record] = {}
    for start in range(0, len(ids), FILTER_CHUNK_SIZE):
        chunk = ids[start : start + FILTER_CHUNK_SIZE]
        if collection == "products":
            filter_expr, substitutions = literal_id_filter(chunk), list[str]()
        else:
            filter_expr, substitutions = contains_filter("id", chunk)
        for record in source.query_records(collection, filter_expr, substitutions):
            records[str(record["id"])] = record
    return records


def _create(
    create: Callable[[Sequence[Record]], WriteResponse],
    requests_by_source_id: Dict[str, Record],
) -> Tuple[Dict[str, str], List[FailedItem]]:
    """Create records and map each source ID to its destination ID or failure.

    Created and echoed failed records are matched by their source ID annotation.
    """
    if not requests_by_source_id:
        return {}, []
    try:
        response = create(list(requests_by_source_id.values()))
    except requests.RequestException as exc:
        error_type, detail = _request_failure(exc)
        return {}, [
            FailedItem(source_id=source_id, stage="create", error_type=error_type, detail=detail)
            for source_id in requests_by_source_id
        ]
    created = {
        str(record.get("properties", {}).get(SOURCE_ID)): str(record["id"])
        for record in response.created
    }
    errors = ", ".join(error_names(response.error)) or None
    failed = [
        FailedItem(
            source_id=source_id,
            stage="create",
            error_type="PartialFailure" if errors else "NotCreated",
            detail=errors,
        )
        for source_id in requests_by_source_id
        if source_id not in created
    ]
    return created, failed


def migrate_products(
    source: SourceRecords,
    destination: DestinationWriter,
    context: MigrationContext,
    batch: int,
    products: Sequence[DiscoveredProduct],
) -> BatchResult:
    """Migrate a batch of products into their mapped destination workspaces.

    A product whose part number already exists on the destination is not changed
    and is reported as a conflict; results that reference it still migrate.

    Raises:
        requests.RequestException: If reading before any write fails, so the batch
            can be retried without duplicating destination resources.
    """
    records = _fetch_by_id(source, "products", [p.id for p in products])
    existing = {
        str(record.get("partNumber")): record
        for record in destination.query_products_by_part_number(
            sorted({str(r["partNumber"]) for r in records.values()})
        )
    }
    failed: List[FailedItem] = []
    conflicts: List[ProductConflict] = []
    to_create: Dict[str, Record] = {}
    for product in products:
        record = records.get(product.id)
        if record is None:
            failed.append(FailedItem(source_id=product.id, stage="fetch", error_type="NotFound"))
            continue
        try:
            workspace_id = context.mapping.destination_id(product.workspace)
        except KeyError:
            failed.append(
                FailedItem(
                    source_id=product.id,
                    stage="map",
                    error_type="UnmappedWorkspace",
                    detail=product.workspace,
                )
            )
            continue
        match = existing.get(str(record["partNumber"]))
        if match is not None:
            match_properties = match.get("properties") or {}
            conflicts.append(
                ProductConflict(
                    source_id=product.id,
                    part_number=str(record["partNumber"]),
                    expected_workspace=context.workspace_name(workspace_id),
                    existing_id=str(match.get("id")),
                    existing_workspace_id=match.get("workspace"),
                    existing_migration_id=match_properties.get(MIGRATION_ID),
                    existing_source_id=match_properties.get(SOURCE_ID),
                )
            )
            continue
        to_create[product.id] = {
            **_copy(record, PRODUCT_FIELDS),
            "workspace": workspace_id,
            "properties": context.annotate(record, product.id),
        }
    created, create_failed = _create(destination.create_products, to_create)
    return BatchResult(
        resource="products",
        batch=batch,
        migrated=tuple(MigratedItem(source_id=s, destination_id=d) for s, d in created.items()),
        failed=tuple(failed + create_failed),
        conflicts=tuple(conflicts),
    )


def migrate_results(
    source: SourceRecords,
    destination: DestinationWriter,
    context: MigrationContext,
    batch: int,
    results: Sequence[DiscoveredResult],
) -> BatchResult:
    """Migrate a batch of results, each with all of its steps.

    A result is created ``INCOMPLETE`` and marked ``COMPLETE`` only after all of
    its steps migrate. A result with any failed step stays ``INCOMPLETE`` and is
    reported as failed.

    Raises:
        requests.RequestException: If reading before any write fails.
    """
    records = _fetch_by_id(source, "results", [r.id for r in results])
    failed: List[FailedItem] = []
    to_create: Dict[str, Record] = {}
    for result in results:
        record = records.get(result.id)
        if record is None:
            failed.append(FailedItem(source_id=result.id, stage="fetch", error_type="NotFound"))
            continue
        try:
            workspace_id = context.mapping.destination_id(result.workspace)
        except KeyError:
            failed.append(
                FailedItem(
                    source_id=result.id,
                    stage="map",
                    error_type="UnmappedWorkspace",
                    detail=result.workspace,
                )
            )
            continue
        to_create[result.id] = {
            **_copy(record, RESULT_FIELDS),
            "workspace": workspace_id,
            "properties": context.annotate(record, result.id, **{STATUS: INCOMPLETE}),
        }
    created, create_failed = _create(destination.create_results, to_create)
    failed.extend(create_failed)
    migrated: List[MigratedItem] = []
    for source_id, destination_id in created.items():
        outcome = _complete_result(source, destination, context, source_id, destination_id)
        if isinstance(outcome, FailedItem):
            failed.append(outcome)
        else:
            migrated.append(outcome)
    return BatchResult(
        resource="results", batch=batch, migrated=tuple(migrated), failed=tuple(failed)
    )


def _complete_result(
    source: SourceRecords,
    destination: DestinationWriter,
    context: MigrationContext,
    source_id: str,
    destination_id: str,
) -> Union[MigratedItem, FailedItem]:
    def failure(stage: str, error_type: str, detail: Optional[str]) -> FailedItem:
        return FailedItem(
            source_id=source_id,
            stage=stage,
            error_type=error_type,
            detail=detail,
            destination_id=destination_id,
        )

    try:
        steps = list(source.query_records("steps", "resultId == @0", [source_id]))
    except requests.RequestException as exc:
        return failure("steps", *_request_failure(exc))
    step_failure = _migrate_steps(destination, context, destination_id, steps)
    if step_failure is not None:
        return failure("steps", *step_failure)
    try:
        response = destination.update_results(
            [{"id": destination_id, "properties": {STATUS: COMPLETE, COMPLETED_AT: _now()}}]
        )
    except requests.RequestException as exc:
        return failure("complete", *_request_failure(exc))
    if response.failed or response.error:
        return failure("complete", "PartialFailure", ", ".join(error_names(response.error)) or None)
    return MigratedItem(source_id=source_id, destination_id=destination_id, steps=len(steps))


def order_steps(steps: Sequence[Record]) -> List[List[Record]]:
    """Group steps into levels so every parent precedes its children.

    Parents outside ``steps``, such as the ``root`` pseudo-parent, are level 0.
    """
    by_id = {str(step["stepId"]): step for step in steps}
    depths: Dict[str, int] = {}

    def depth(step_id: str) -> int:
        chain: List[str] = []
        current: Optional[str] = step_id
        while current in by_id and current not in depths:
            if current in chain:
                raise ValueError(f"Step hierarchy has a cycle at '{current}'")
            chain.append(current)
            parent = by_id[current].get("parentId")
            current = str(parent) if parent is not None else None
        base = depths.get(current, -1) if current is not None else -1
        for offset, item in enumerate(reversed(chain), start=1):
            depths[item] = base + offset
        return depths[step_id]

    levels: Dict[int, List[Record]] = {}
    for step_id, step in by_id.items():
        levels.setdefault(depth(step_id), []).append(step)
    return [levels[level] for level in sorted(levels)]


def _migrate_steps(
    destination: DestinationWriter,
    context: MigrationContext,
    destination_result_id: str,
    steps: Sequence[Record],
) -> Optional[Tuple[str, Optional[str]]]:
    """Create every step parent-first, remapping parent IDs to destination step IDs.

    Returns:
        None when every step migrated, otherwise the error type and detail of
        the first failure.
    """
    try:
        levels = order_steps(steps)
    except ValueError as exc:
        return ("InvalidStepHierarchy", str(exc))
    destination_step_ids: Dict[str, str] = {}
    migrated = 0
    for level in levels:
        requests_by_source_id: Dict[str, Record] = {}
        for step in level:
            step_id = str(step["stepId"])
            parent = step.get("parentId")
            if parent is not None and str(parent) in destination_step_ids:
                parent = destination_step_ids[str(parent)]
            request = {
                **_copy(step, STEP_FIELDS),
                "resultId": destination_result_id,
                "properties": context.annotate(step, step_id),
            }
            if parent is not None:
                request["parentId"] = parent
            requests_by_source_id[step_id] = request
        chunks = list(requests_by_source_id.items())
        for start in range(0, len(chunks), STEP_CHUNK_SIZE):
            chunk = chunks[start : start + STEP_CHUNK_SIZE]
            try:
                response = destination.create_steps([request for _, request in chunk])
            except requests.RequestException as exc:
                error_type, detail = _request_failure(exc)
                return (error_type, f"{migrated} of {len(steps)} steps; {detail}")
            for created in response.created:
                source_step_id = (created.get("properties") or {}).get(SOURCE_ID)
                if source_step_id is not None:
                    destination_step_ids[str(source_step_id)] = str(created["stepId"])
            missing = [step_id for step_id, _ in chunk if step_id not in destination_step_ids]
            migrated += len(chunk) - len(missing)
            if missing:
                errors = ", ".join(error_names(response.error))
                return (
                    "PartialFailure",
                    f"{migrated} of {len(steps)} steps; {errors or 'not created'}",
                )
    return None


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
