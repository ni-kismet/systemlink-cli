"""Tests for migration workspace API operations."""

from unittest.mock import MagicMock

import pytest
import requests
from pydantic import ValidationError

from slcli.migration.workspace_client import Workspace, WorkspaceClient


def test_create_workspace_posts_enabled_workspace() -> None:
    """Workspace creation sends the expected request and returns its identity."""
    session = MagicMock()
    response = MagicMock()
    response.json.return_value = {"id": "created-id"}
    session.post.return_value = response
    connection = MagicMock()
    connection.base_url = "https://destination.example.com"
    connection.create_session.return_value = session

    workspace = WorkspaceClient(connection).create_workspace("New workspace")

    assert workspace == Workspace(id="created-id", name="New workspace")
    connection.create_session.assert_called_once_with(retry_post_queries=False)
    session.post.assert_called_once_with(
        "https://destination.example.com/niuser/v1/workspaces",
        json={"name": "New workspace", "enabled": True},
        timeout=30,
    )
    response.raise_for_status.assert_called_once_with()


@pytest.mark.parametrize("enabled", [False, True])
def test_query_preserves_workspace_enabled_state(enabled: bool) -> None:
    """Workspace queries retain the enabled state used by synchronization."""
    session = MagicMock()
    response = MagicMock()
    response.json.return_value = {
        "workspaces": [{"id": "workspace-id", "name": "Lab", "enabled": enabled}]
    }
    session.get.return_value = response
    connection = MagicMock()
    connection.base_url = "https://destination.example.com"

    workspaces = list(WorkspaceClient(connection, session).query_workspaces())

    assert workspaces == [Workspace(id="workspace-id", name="Lab", enabled=enabled)]


@pytest.mark.parametrize("operation", ["create", "query"])
@pytest.mark.parametrize("status_code", [401, 403, 500, 503])
def test_workspace_http_errors_propagate_before_parsing(
    operation: str,
    status_code: int,
) -> None:
    """Permission and server errors are not mistaken for workspace data."""
    response = requests.Response()
    response.status_code = status_code
    session = MagicMock()
    session.get.return_value = session.post.return_value = response
    connection = MagicMock()
    connection.base_url = "https://destination.example.com"
    client = WorkspaceClient(connection, session)

    with pytest.raises(requests.HTTPError) as raised:
        if operation == "create":
            client.create_workspace("Lab")
        else:
            list(client.query_workspaces())

    assert raised.value.response is response
    assert session.get.call_count + session.post.call_count == 1


@pytest.mark.parametrize("operation", ["create", "query"])
def test_workspace_invalid_json_propagates(operation: str) -> None:
    """Successful HTTP responses with invalid JSON cannot produce workspace mappings."""
    response = requests.Response()
    response.status_code = 200
    response._content = b"not json"
    session = MagicMock()
    session.get.return_value = session.post.return_value = response
    connection = MagicMock()
    connection.base_url = "https://destination.example.com"
    client = WorkspaceClient(connection, session)

    with pytest.raises(requests.exceptions.JSONDecodeError):
        if operation == "create":
            client.create_workspace("Lab")
        else:
            list(client.query_workspaces())


@pytest.mark.parametrize(
    "payload",
    [{}, {"workspaces": None}, {"workspaces": [{"id": "workspace-id"}]}],
)
def test_workspace_query_rejects_malformed_payload(payload: object) -> None:
    """Query responses must contain a workspace list with required workspace fields."""
    session = MagicMock()
    session.get.return_value.json.return_value = payload
    connection = MagicMock()
    connection.base_url = "https://destination.example.com"

    with pytest.raises(ValidationError):
        list(WorkspaceClient(connection, session).query_workspaces())


def test_workspace_creation_rejects_missing_id() -> None:
    """A creation response without a server-assigned ID cannot produce a workspace."""
    session = MagicMock()
    session.post.return_value.json.return_value = {}
    connection = MagicMock()
    connection.base_url = "https://destination.example.com"

    with pytest.raises(KeyError, match="id"):
        WorkspaceClient(connection, session).create_workspace("Lab")
