"""Contract tests for the Asset Service migration client."""

from typing import Any, Dict, List

import pytest
from pydantic import ValidationError

from slcli.migration.assets.client import PAGE_SIZE, AssetClient
from slcli.migration.connection import MigrationConnection


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
    """Record Asset Service requests and return configured response pages."""

    def __init__(self, pages: List[Any]) -> None:
        """Store the pending response pages."""
        self._pages = pages
        self.calls: List[Dict[str, Any]] = []

    def post(self, url: str, **kwargs: Any) -> FakeResponse:
        """Record a request and return the next response page."""
        self.calls.append({"url": url, **kwargs})
        return FakeResponse(self._pages.pop(0))


CONNECTION = MigrationConnection("source", "https://source", {"x-ni-api-key": "secret"})


def test_query_assets_follows_offset_pages() -> None:
    """Asset discovery reads every offset page with the migration page size."""
    first_page = [{"id": f"asset-{index}"} for index in range(PAGE_SIZE)]
    session = FakeSession([{"assets": first_page}, {"assets": [{"id": "last"}]}])
    client = AssetClient(CONNECTION, session)  # type: ignore[arg-type]

    assets = list(client.query_assets())

    assert len(assets) == PAGE_SIZE + 1
    assert assets[-1] == {"id": "last"}
    assert [call["json"] for call in session.calls] == [
        {"skip": 0, "take": PAGE_SIZE, "descending": False},
        {"skip": PAGE_SIZE, "take": PAGE_SIZE, "descending": False},
    ]
    assert session.calls[0]["url"] == "https://source/niapm/v1/query-assets"


def test_query_assets_rejects_malformed_response() -> None:
    """Asset discovery rejects a response whose assets field is not a collection."""
    client = AssetClient(CONNECTION, FakeSession([{"assets": "not a list"}]))  # type: ignore[arg-type]

    with pytest.raises(ValidationError):
        list(client.query_assets())