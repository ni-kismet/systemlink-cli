"""Contract tests for migration API clients."""

from contextlib import contextmanager
from datetime import datetime, timezone
from typing import Any, Dict, Iterator, List, Union

import pytest
import requests
from pydantic import ValidationError

from slcli.migration.connection import MigrationConnection
from slcli.migration.testmonitor.client import PAGE_SIZE, TestMonitorClient
from slcli.migration.workspace_client import PAGE_SIZE as WORKSPACE_PAGE_SIZE
from slcli.migration.workspace_client import WorkspaceClient


class FakeResponse:
    """A successful response with a JSON body."""

    def __init__(self, body: Any) -> None:
        """Store the body."""
        self._body = body

    def raise_for_status(self) -> None:
        """Succeed."""

    def json(self) -> Any:
        """Return the body."""
        return self._body


class FakeSession:
    """Record requests and answer each with the next configured page."""

    def __init__(self, pages: List[Any]) -> None:
        """Store pending pages."""
        self.pages = pages
        self.calls: List[Dict[str, Any]] = []

    def post(self, url: str, **kwargs: Any) -> FakeResponse:
        """Record a POST."""
        self.calls.append({"url": url, **kwargs})
        return FakeResponse(self.pages.pop(0))

    def get(self, url: str, **kwargs: Any) -> FakeResponse:
        """Record a GET."""
        return self.post(url, **kwargs)


CONNECTION = MigrationConnection("source", "https://source", {"x-ni-api-key": "secret"}, False)


def _result(result_id: str) -> Dict[str, object]:
    return {
        "id": result_id,
        "partNumber": "part",
        "status": {"statusType": "PASSED", "statusName": "Passed"},
        "updatedAt": "2026-01-01T00:00:00Z",
        "unusedField": True,
    }


def test_query_results_follows_every_continuation_token() -> None:
    """Results are typed and paged to completion with a parameterized filter."""
    session = FakeSession(
        [
            {"results": [_result("r1")], "continuationToken": "next"},
            {"results": [_result("r2")], "continuationToken": None},
        ]
    )
    client = TestMonitorClient(CONNECTION, session)  # type: ignore[arg-type]

    results = list(client.query_results("workspace == @0", ["workspace-id"]))

    assert [r.id for r in results] == ["r1", "r2"]
    assert results[0].status.status_type == "PASSED"
    assert results[0].updated_at == datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert session.calls[0]["url"] == "https://source/nitestmonitor/v2/query-results"
    assert session.calls[0]["json"] == {
        "filter": "workspace == @0",
        "substitutions": ["workspace-id"],
        "take": PAGE_SIZE,
        "descending": False,
    }
    assert session.calls[1]["json"]["continuationToken"] == "next"


def test_query_products_reads_product_endpoint() -> None:
    """Products are queried unfiltered from their own endpoint."""
    session = FakeSession([{"products": [{"id": "p1", "partNumber": "part"}]}])
    client = TestMonitorClient(CONNECTION, session)  # type: ignore[arg-type]

    assert [p.part_number for p in client.query_products()] == ["part"]
    assert session.calls[0]["url"].endswith("/query-products")
    assert "filter" not in session.calls[0]["json"]


def test_query_rejects_malformed_response() -> None:
    """Responses that do not match the API contract fail at the client boundary."""
    session = FakeSession([{"results": [{"id": "r1"}]}])
    client = TestMonitorClient(CONNECTION, session)  # type: ignore[arg-type]

    with pytest.raises(ValidationError):
        list(client.query_results())


def test_query_rejects_timestamp_without_timezone() -> None:
    """SLS sends UTC with a Z suffix; an unzoned timestamp is not silently guessed."""
    session = FakeSession([{"results": [{**_result("r1"), "updatedAt": "2026-01-01T00:00:00"}]}])
    client = TestMonitorClient(CONNECTION, session)  # type: ignore[arg-type]

    with pytest.raises(ValidationError, match="timezone"):
        list(client.query_results())


def test_query_workspaces_follows_offset_pages() -> None:
    """Workspace paging continues until a short page."""
    full_page = [{"id": f"id-{i}", "name": f"ws-{i}"} for i in range(WORKSPACE_PAGE_SIZE)]
    session = FakeSession(
        [{"workspaces": full_page}, {"workspaces": [{"id": "last", "name": "Last"}]}]
    )

    workspaces = list(WorkspaceClient(CONNECTION, session).query_workspaces())  # type: ignore[arg-type]

    assert len(workspaces) == WORKSPACE_PAGE_SIZE + 1
    assert workspaces[-1].name == "Last"
    assert [call["params"]["skip"] for call in session.calls] == [0, WORKSPACE_PAGE_SIZE]


@pytest.mark.parametrize("verify", [False, True, "managed.pem"])
@pytest.mark.parametrize("fails", [False, True])
def test_connection_requests_use_ssl_context(
    monkeypatch: pytest.MonkeyPatch, verify: Union[bool, str], fails: bool
) -> None:
    """Each request uses and restores the connection's TLS context, even on failure."""
    context_values: List[Union[bool, str]] = []
    active = False

    @contextmanager
    def ssl_context(value: Union[bool, str]) -> Iterator[None]:
        nonlocal active
        context_values.append(value)
        active = True
        try:
            yield
        finally:
            active = False

    def send(*args: Any, **kwargs: Any) -> FakeResponse:
        assert active
        if fails:
            raise requests.ConnectionError("offline")
        return FakeResponse({})

    monkeypatch.setattr("slcli.migration.connection.use_standard_ssl_context", ssl_context)
    monkeypatch.setattr(requests.Session, "request", send)
    session = MigrationConnection("source", "https://source", {}, verify).create_session()

    for _ in range(2):
        if fails:
            with pytest.raises(requests.ConnectionError, match="offline"):
                session.post("https://source/query")
        else:
            session.get("https://source/query")
    assert context_values == [verify, verify]
    assert not active
