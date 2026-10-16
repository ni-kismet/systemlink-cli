"""Profile-bound Test Monitor queries for migration discovery."""

from collections.abc import Iterator
from typing import Dict, List, Optional, Sequence, Type, TypeVar

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
    properties: Dict[str, str] = {}


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
    properties: Dict[str, str] = {}


class _Page(ApiModel):
    continuation_token: Optional[str] = None


class _ProductPage(_Page):
    products: List[Product] = []


class _ResultPage(_Page):
    results: List[Result] = []


_PageT = TypeVar("_PageT", bound=_Page)


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
        for page in self._query_pages("query-products", _ProductPage, {}):
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
        for page in self._query_pages("query-results", _ResultPage, query):
            yield from page.results

    def _query_pages(
        self, endpoint: str, page_type: Type[_PageT], query: Dict[str, object]
    ) -> Iterator[_PageT]:
        """Yield every page of a continuation-token query."""
        payload: Dict[str, object] = {**query, "take": PAGE_SIZE, "descending": False}
        while True:
            response = self._session.post(
                f"{self._base_url}/{endpoint}", json=payload, timeout=REQUEST_TIMEOUT_SECONDS
            )
            response.raise_for_status()
            page = page_type.model_validate(response.json())
            yield page

            token = page.continuation_token
            if not token:
                return
            payload = {**payload, "continuationToken": token}
