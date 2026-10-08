"""Contract tests for migration API clients."""

from contextlib import contextmanager
from typing import Any, Dict, Iterator, List, Union
from unittest.mock import MagicMock

import pytest
import requests

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


@pytest.mark.parametrize("verify", [False, True, "managed.pem"])
@pytest.mark.parametrize("fails", [False, True])
def test_workspace_requests_use_connection_ssl_context(
    monkeypatch: pytest.MonkeyPatch, verify: Union[bool, str], fails: bool
) -> None:
    """Each page request uses and restores the connection's TLS context, even on failure."""
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

    def get_page(*args: Any, **kwargs: Any) -> FakeResponse:
        assert active
        assert kwargs["verify"] == verify
        if fails:
            raise requests.ConnectionError("offline")
        page = (
            [{"id": str(index), "name": "workspace"} for index in range(WORKSPACE_PAGE_SIZE)]
            if kwargs["params"]["skip"] == 0
            else []
        )
        return FakeResponse({"workspaces": page})

    monkeypatch.setattr("slcli.migration.workspace_client.use_standard_ssl_context", ssl_context)
    session = MagicMock()
    session.get.side_effect = get_page
    connection = MigrationConnection("source", "https://source", {}, verify)
    client = WorkspaceClient(connection, session)

    if fails:
        with pytest.raises(requests.ConnectionError, match="offline"):
            list(client.query_workspaces())
    else:
        assert len(list(client.query_workspaces())) == WORKSPACE_PAGE_SIZE
    assert context_values == [verify] * (1 if fails else 2)
    assert not active
