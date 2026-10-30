"""Profile-bound Test Monitor queries for migration discovery."""

from collections.abc import Iterator
from typing import Any, Dict, Iterable, List, Optional, Protocol, Sequence, Type, TypeVar

import requests
from pydantic import AwareDatetime

from slcli.migration.api import REQUEST_TIMEOUT_SECONDS, ApiModel
from slcli.migration.connection import MigrationConnection

PAGE_SIZE = 1000


class Product(ApiModel):
    """A Test Monitor product. SLS products have no workspace of their own."""

    id: str
    part_number: str
    workspace: Optional[str] = None
    properties: Dict[str, Optional[str]] = {}


class ResultStatus(ApiModel):
    """The status of a Test Monitor result."""

    status_type: str


class Result(ApiModel):
    """A Test Monitor result, associated with a product by part number."""

    id: str
    part_number: Optional[str] = None
    workspace: Optional[str] = None
    status: ResultStatus
    updated_at: AwareDatetime
    properties: Dict[str, Optional[str]] = {}


class _Page(ApiModel):
    continuation_token: Optional[str] = None


class _ProductPage(_Page):
    products: List[Product] = []


class _ResultPage(_Page):
    results: List[Result] = []


class _RecordPage(_Page):
    """Unmodeled records; a response populates only its own collection."""

    products: List[Dict[str, Any]] = []
    results: List[Dict[str, Any]] = []
    steps: List[Dict[str, Any]] = []


_PageT = TypeVar("_PageT", bound=_Page)


class TestMonitorSource(Protocol):
    """Source Test Monitor queries used by discovery and migration."""

    def query_products(self) -> Iterable[Product]:
        """Return all Test Monitor products."""
        ...

    def query_results(
        self,
        filter_expr: Optional[str] = None,
        substitutions: Optional[Sequence[str]] = None,
    ) -> Iterable[Result]:
        """Return Test Monitor results matching a parameterized filter."""
        ...

    def query_records(
        self, collection: str, filter_expr: str, substitutions: Sequence[object]
    ) -> Iterable[Dict[str, Any]]:
        """Return complete records of a collection matching a filter."""
        ...


class TestMonitorClient:
    """Query Test Monitor using one profile-bound migration connection."""

    __test__ = False

    def __init__(
        self,
        connection: MigrationConnection,
        session: Optional[requests.Session] = None,
    ) -> None:
        """Initialize a Test Monitor query client."""
        self._base_url = f"{connection.base_url}/nitestmonitor/v2"
        self._session = session or connection.create_session()

    def query_products(self) -> Iterator[Product]:
        """Yield every product."""
        for page in self._query_pages("products", _ProductPage, {}):
            yield from page.products

    def query_results(
        self,
        filter_expr: Optional[str] = None,
        substitutions: Optional[Sequence[str]] = None,
    ) -> Iterator[Result]:
        """Yield every result matching a parameterized filter."""
        query: Dict[str, object] = {}
        if filter_expr:
            query["filter"] = filter_expr
            query["substitutions"] = list(substitutions or [])
        for page in self._query_pages("results", _ResultPage, query):
            yield from page.results

    def query_records(
        self,
        collection: str,
        filter_expr: str,
        substitutions: Sequence[object],
    ) -> Iterator[Dict[str, Any]]:
        """Yield complete records of a collection matching a parameterized filter.

        Records are returned as received so fields that migration does not model
        are preserved.

        Args:
            collection: ``products``, ``results``, or ``steps``.
            filter_expr: Dynamic LINQ filter.
            substitutions: Values for ``@0``, ``@1``, and so on in ``filter_expr``.
        """
        query: Dict[str, object] = {"filter": filter_expr, "substitutions": list(substitutions)}
        for page in self._query_pages(collection, _RecordPage, query):
            yield from (*page.products, *page.results, *page.steps)

    def _query_pages(
        self, collection: str, page_type: Type[_PageT], query: Dict[str, object]
    ) -> Iterator[_PageT]:
        """Yield every record of a continuation-token query on ``query-<collection>``."""
        payload: Dict[str, object] = {**query, "take": PAGE_SIZE, "descending": False}
        while True:
            response = self._session.post(
                f"{self._base_url}/query-{collection}",
                json=payload,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            page = page_type.model_validate(response.json())
            yield page

            token = page.continuation_token
            if not token:
                return
            payload = {**payload, "continuationToken": token}
