"""Profile-bound Asset Service queries for migration discovery."""

from collections.abc import Iterator
from typing import Any, Dict, Iterable, Optional, Protocol

import requests
from pydantic import Field

from slcli.migration.api import REQUEST_TIMEOUT_SECONDS, ApiModel
from slcli.migration.connection import MigrationConnection

PAGE_SIZE = 1000
AssetRecord = Dict[str, Any]


class AssetQuery(Protocol):
    """Asset Service queries needed by migration discovery."""

    def query_assets(self) -> Iterable[AssetRecord]:
        """Return every source asset needed for discovery."""
        ...


class _AssetPage(ApiModel):
    """One offset-paginated Asset Service response."""

    assets: list[AssetRecord] = Field(default_factory=list)


class AssetClient:
    """Query Asset Service using one profile-bound migration connection."""

    __test__ = False

    def __init__(
        self,
        connection: MigrationConnection,
        session: Optional[requests.Session] = None,
    ) -> None:
        """Initialize an Asset Service query client."""
        self._url = f"{connection.base_url}/niapm/v1/query-assets"
        self._session = session or connection.create_session()

    def query_assets(self) -> Iterator[AssetRecord]:
        """Yield every source asset using Asset Service offset pagination."""
        skip = 0
        while True:
            response = self._session.post(
                self._url,
                json={"skip": skip, "take": PAGE_SIZE, "descending": False},
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            assets = _AssetPage.model_validate(response.json()).assets
            yield from assets
            if len(assets) < PAGE_SIZE:
                return
            skip += len(assets)