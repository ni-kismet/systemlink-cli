"""Profile-bound workspace queries for migration discovery."""

from collections.abc import Iterator
from typing import List, Optional

import requests

from slcli.migration.api import REQUEST_TIMEOUT_SECONDS, ApiModel
from slcli.migration.connection import MigrationConnection
from slcli.ssl_trust import use_standard_ssl_context

PAGE_SIZE = 100


class Workspace(ApiModel):
    """A SystemLink workspace."""

    id: str
    name: str


class _WorkspacePage(ApiModel):
    workspaces: List[Workspace]


class WorkspaceClient:
    """Query workspaces using one profile-bound migration connection."""

    def __init__(
        self,
        connection: MigrationConnection,
        session: Optional[requests.Session] = None,
    ) -> None:
        """Initialize a workspace query client."""
        self._url = f"{connection.base_url}/niuser/v1/workspaces"
        self._session = session or connection.create_session()
        self._ssl_verify = connection.ssl_verify

    def query_workspaces(self) -> Iterator[Workspace]:
        """Yield every accessible workspace."""
        skip = 0
        while True:
            with use_standard_ssl_context(self._ssl_verify):
                response = self._session.get(
                    self._url,
                    params={"take": PAGE_SIZE, "skip": skip},
                    timeout=REQUEST_TIMEOUT_SECONDS,
                    verify=self._ssl_verify,
                )
            response.raise_for_status()
            page = _WorkspacePage.model_validate(response.json())
            yield from page.workspaces
            if len(page.workspaces) < PAGE_SIZE:
                return
            skip += PAGE_SIZE
