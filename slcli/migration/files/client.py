"""Profile-bound SLS file queries for migration discovery."""

from collections.abc import Iterator
from typing import Any, Dict, List, Optional

import requests

from slcli.migration.api import REQUEST_TIMEOUT_SECONDS, ApiModel
from slcli.migration.connection import MigrationConnection

PAGE_SIZE = 1000


class SourceFile(ApiModel):
    """An SLS file. Its name is stored in the ``Name`` property."""

    id: str
    properties: Dict[str, Any] = {}
    size: Optional[int] = None
    size64: Optional[int] = None

    @property
    def name(self) -> Optional[str]:
        """The file name, or None when the server did not provide one."""
        value = self.properties.get("Name")
        return value if isinstance(value, str) and value else None

    @property
    def size_bytes(self) -> Optional[int]:
        """The file size in bytes, preferring the 64-bit field."""
        # size == -1 means the file is larger than a 32-bit value can hold.
        if self.size64 is not None and self.size64 >= 0:
            return self.size64
        if self.size is not None and self.size >= 0:
            return self.size
        return None


class _FilePage(ApiModel):
    available_files: List[SourceFile] = []


class FilesClient:
    """Query SLS files using one profile-bound migration connection."""

    def __init__(
        self,
        connection: MigrationConnection,
        session: Optional[requests.Session] = None,
    ) -> None:
        """Initialize a file query client."""
        self._base_url = f"{connection.base_url}/nifile/v1/service-groups/Default"
        self._session = session or connection.create_session()

    def query_files(self, workspace_id: str) -> Iterator[SourceFile]:
        """Yield every file in one workspace, paging with skip/take.

        The server caps ``take`` at ``PAGE_SIZE`` and returns no continuation
        token, so a page shorter than ``PAGE_SIZE`` marks the last page.
        """
        skip = 0
        while True:
            params: Dict[str, Any] = {
                "skip": skip,
                "take": PAGE_SIZE,
                "workspace": workspace_id,
            }
            response = self._session.post(
                f"{self._base_url}/query-files",
                params=params,
                json={},
                timeout=REQUEST_TIMEOUT_SECONDS,
            )
            response.raise_for_status()
            page = _FilePage.model_validate(response.json())
            yield from page.available_files

            if len(page.available_files) < PAGE_SIZE:
                return
            skip += PAGE_SIZE
