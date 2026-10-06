"""Contract tests for migration API clients."""

from typing import Any, Dict, List

from slcli.migration.connection import MigrationConnection
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
