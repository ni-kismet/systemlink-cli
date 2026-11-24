"""Contract tests for the System Management migration client."""

from typing import Any, Dict, List

import pytest
from pydantic import ValidationError

from slcli.migration.connection import MigrationConnection
from slcli.migration.system_client import PAGE_SIZE, SystemClient


class FakeResponse:
    """A successful response with a JSON body."""

    def __init__(self, body: Any) -> None:
        """Store the response body."""
        self._body = body

    def raise_for_status(self) -> None:
        """Succeed."""

    def json(self) -> Any:
        """Return the response body."""
        return self._body


class FakeSession:
    """Record System Management requests and return configured response pages."""

    def __init__(self, pages: List[Any]) -> None:
        """Store the pending response pages."""
        self._pages = pages
        self.calls: List[Dict[str, Any]] = []

    def post(self, url: str, **kwargs: Any) -> FakeResponse:
        """Record a request and return the next response page."""
        self.calls.append({"url": url, **kwargs})
        return FakeResponse(self._pages.pop(0))


CONNECTION = MigrationConnection("source", "https://source", {"x-ni-api-key": "secret"})


def test_query_systems_follows_offset_pages() -> None:
    """System discovery reads every offset page with the migration page size."""
    first_page = [
        {"id": f"minion-{index}", "workspace": "workspace-1"} for index in range(PAGE_SIZE)
    ]
    session = FakeSession(
        [{"data": first_page}, {"data": [{"id": "last", "workspace": "workspace-2"}]}]
    )
    client = SystemClient(CONNECTION, session)  # type: ignore[arg-type]

    systems = list(client.query_systems())

    assert len(systems) == PAGE_SIZE + 1
    assert systems[-1].id == "last"
    assert [call["json"] for call in session.calls] == [
        {"skip": 0, "take": PAGE_SIZE, "projection": "new(id, workspace)"},
        {"skip": PAGE_SIZE, "take": PAGE_SIZE, "projection": "new(id, workspace)"},
    ]
    assert session.calls[0]["url"] == "https://source/nisysmgmt/v1/query-systems"


def test_query_systems_rejects_malformed_response() -> None:
    """System discovery rejects a response whose data field is not a collection."""
    client = SystemClient(CONNECTION, FakeSession([{"data": "not a list"}]))  # type: ignore[arg-type]

    with pytest.raises(ValidationError):
        list(client.query_systems())
