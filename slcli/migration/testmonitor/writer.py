"""Destination Test Monitor writes for migration."""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Protocol, Sequence

import requests

from slcli.migration.api import REQUEST_TIMEOUT_SECONDS, ApiModel
from slcli.migration.connection import MigrationConnection

Record = Dict[str, Any]


class ApiError(ApiModel):
    """A SystemLink error and the per-item errors it contains."""

    name: Optional[str] = None
    message: Optional[str] = None
    args: List[Any] = []
    inner_errors: List["ApiError"] = []

    def names(self) -> List[str]:
        """Return this error's name and the names of its inner errors."""
        return [n for n in (self.name, *(e.name for e in self.inner_errors)) if n]


@dataclass(frozen=True)
class WriteResponse:
    """Created records and echoed failed requests from one create call."""

    created: List[Record] = field(default_factory=list)
    failed: List[Record] = field(default_factory=list)
    error: Optional[ApiError] = None


class DestinationWriter(Protocol):
    """Destination writes needed by migration."""

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


class TestMonitorWriter:
    """Create and annotate Test Monitor resources on a destination."""

    __test__ = False

    def __init__(
        self,
        connection: MigrationConnection,
        session: Optional[requests.Session] = None,
    ) -> None:
        """Initialize a writer with a non-replaying write session."""
        self._base_url = f"{connection.base_url}/nitestmonitor/v2"
        self._session = session or connection.create_write_session()

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
        if not records:
            return WriteResponse()
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
            error=ApiError.model_validate(body["error"]) if body.get("error") else None,
        )
