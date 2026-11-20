"""Profile-bound workspace queries for migration discovery."""

from collections.abc import Iterable, Iterator
from typing import Dict, List, Optional, Union

import click
import requests

from slcli.migration.api import REQUEST_TIMEOUT_SECONDS, ApiModel
from slcli.migration.connection import MigrationConnection

PAGE_SIZE = 100


class Workspace(ApiModel):
    """A SystemLink workspace."""

    id: str
    name: str
    enabled: bool = True


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
        self._connection = connection
        self._url = f"{connection.base_url}/niuser/v1/workspaces"
        self._session = session or connection.create_session()

    def query_workspaces(self) -> Iterator[Workspace]:
        """Yield every accessible workspace."""
        return self._query({})

    def find_workspaces(self, names: Iterable[str]) -> Iterator[Workspace]:
        """Yield the accessible workspaces with exactly these names.

        Each name is a separate filtered query, so a large tenant is never listed.
        """
        for name in sorted(set(names)):
            yield from (w for w in self._query({"name": name}) if w.name == name)

    def _query(self, params: Dict[str, str]) -> Iterator[Workspace]:
        skip = 0
        while True:
            page_params: Dict[str, Union[str, int]] = {**params, "take": PAGE_SIZE, "skip": skip}
            response = self._session.get(
                self._url,
                params=page_params,
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            page = _WorkspacePage.model_validate(response.json())
            yield from page.workspaces
            if len(page.workspaces) < PAGE_SIZE:
                return
            skip += PAGE_SIZE

    def create_workspace(self, name: str) -> Workspace:
        """Create an enabled workspace and return its server-assigned identity."""
        if self._connection.readonly:
            raise click.ClickException(
                f"Cannot create a workspace: profile '{self._connection.profile_name}' "
                "is in readonly mode"
            )
        response = self._session.post(
            self._url,
            json={"name": name, "enabled": True},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        return Workspace(id=str(response.json()["id"]), name=name)
