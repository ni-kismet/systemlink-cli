"""Profile-bound System Management queries for migration discovery."""

from collections.abc import Iterable, Iterator
from typing import Optional, Protocol

import requests
from pydantic import Field

from slcli.migration.api import REQUEST_TIMEOUT_SECONDS, ApiModel
from slcli.migration.connection import MigrationConnection

PAGE_SIZE = 100
_SYSTEM_PROJECTION = "new(id, workspace)"


class System(ApiModel):
    """Source system identity and workspace assignment."""

    id: str
    workspace: str


class SystemQuery(Protocol):
    """System Management queries needed by migration discovery."""

    def query_systems(self) -> Iterable[System]:
        """Return every source system needed for discovery."""
        ...


class _SystemPage(ApiModel):
    """One offset-paginated System Management response."""

    data: list[System] = Field(default_factory=list)


class SystemClient:
    """Query System Management using one profile-bound migration connection."""

    __test__ = False

    def __init__(
        self,
        connection: MigrationConnection,
        session: Optional[requests.Session] = None,
    ) -> None:
        """Initialize a System Management query client."""
        self._url = f"{connection.base_url}/nisysmgmt/v1/query-systems"
        self._session = session or connection.create_session()

    def query_systems(self) -> Iterator[System]:
        """Yield every source system using System Management offset pagination."""
        skip = 0
        while True:
            response = self._session.post(
                self._url,
                json={"skip": skip, "take": PAGE_SIZE, "projection": _SYSTEM_PROJECTION},
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            systems = _SystemPage.model_validate(response.json()).data
            yield from systems
            if len(systems) < PAGE_SIZE:
                return
            skip += len(systems)
