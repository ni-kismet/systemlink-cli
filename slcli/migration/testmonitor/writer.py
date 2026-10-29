"""Destination Test Monitor writes for migration."""

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, List, Optional, Sequence

import requests

from slcli.migration.api import REQUEST_TIMEOUT_SECONDS
from slcli.migration.connection import MigrationConnection
from slcli.migration.testmonitor.client import TestMonitorClient

Record = Dict[str, Any]


@dataclass(frozen=True)
class WriteResponse:
    """Created records and echoed failed requests from one create call."""

    created: List[Record] = field(default_factory=list)
    failed: List[Record] = field(default_factory=list)
    error: Optional[Record] = None


_FILTER_CHUNK_SIZE = 100


class TestMonitorWriter:
    """Create and annotate Test Monitor resources on a destination."""

    __test__ = False

    def __init__(
        self,
        connection: MigrationConnection,
        session: Optional[requests.Session] = None,
        query_session: Optional[requests.Session] = None,
    ) -> None:
        """Initialize a writer with a non-replaying write session."""
        self._base_url = f"{connection.base_url}/nitestmonitor/v2"
        self._session = session or connection.create_write_session()
        self._reader = TestMonitorClient(connection, query_session)

    def query_products_by_part_number(self, part_numbers: Sequence[str]) -> List[Record]:
        """Return destination products with any of the given part numbers."""
        products: List[Record] = []
        for start in range(0, len(part_numbers), _FILTER_CHUNK_SIZE):
            chunk = part_numbers[start : start + _FILTER_CHUNK_SIZE]
            placeholders = ",".join(f"@{index}" for index in range(len(chunk)))
            products.extend(
                self._reader.query_records(
                    "products", f"new[]{{{placeholders}}}.Contains(partNumber)", list(chunk)
                )
            )
        return products

    def create_products(self, products: Sequence[Record]) -> WriteResponse:
        """Create products; partial failures are returned, not raised."""
        return self._create("products", "products", products)

    def create_results(self, results: Sequence[Record]) -> WriteResponse:
        """Create results; partial failures are returned, not raised."""
        return self._create("results", "results", results)

    def create_steps(self, steps: Sequence[Record]) -> WriteResponse:
        """Create steps; partial failures are returned, not raised."""
        return self._create("steps", "steps", steps)

    def update_results(self, results: Sequence[Record]) -> WriteResponse:
        """Merge fields into existing results; partial failures are returned."""
        return self._post("update-results", "results", {"results": list(results)})

    def _create(self, endpoint: str, collection: str, records: Sequence[Record]) -> WriteResponse:
        return self._post(endpoint, collection, {collection: list(records)})

    def _post(self, endpoint: str, collection: str, payload: Dict[str, object]) -> WriteResponse:
        response = self._session.post(
            f"{self._base_url}/{endpoint}", json=payload, timeout=REQUEST_TIMEOUT_SECONDS
        )
        response.raise_for_status()
        body: Record = response.json() if response.content else {}
        return WriteResponse(
            created=list(body.get(collection) or []),
            failed=list(body.get("failed") or []),
            error=body.get("error"),
        )


def error_names(error: Optional[Record]) -> List[str]:
    """Return the error and inner-error names reported by a partial-success response."""
    if not error:
        return []
    names: Iterable[Any] = [
        error.get("name"),
        *(inner.get("name") for inner in error.get("innerErrors") or []),
    ]
    return [str(name) for name in names if name]
