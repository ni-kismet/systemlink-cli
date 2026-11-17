"""Profile-bound file queries, downloads, and uploads for migration."""

import json
import re
import uuid
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Dict, List, Mapping, Optional, Union
from urllib.parse import quote, urlsplit

import click
import requests
from urllib3.fields import RequestField

from slcli.migration.api import REQUEST_TIMEOUT_SECONDS, ApiModel
from slcli.migration.connection import MigrationConnection

PAGE_SIZE = 1000
CHUNK_SIZE = 1024 * 1024


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


class _UploadResponse(ApiModel):
    uri: str


@dataclass(frozen=True)
class FileContent:
    """Streamed file bytes and their length, when the server reported it."""

    chunks: Iterable[bytes]
    length: Optional[int] = None


class _SizedBody:
    """An iterable request body whose length lets requests send Content-Length."""

    def __init__(self, parts: Iterable[bytes], length: int) -> None:
        self._parts = parts
        self._length = length

    def __iter__(self) -> Iterator[bytes]:
        return iter(self._parts)

    def __len__(self) -> int:
        return self._length


def _multipart_body(
    boundary: str, fields: Mapping[str, str], filename: str, content: FileContent
) -> Union[_SizedBody, Iterator[bytes]]:
    """Stream form fields followed by the file part, without buffering the file."""
    preamble = b""
    for name, value in fields.items():
        field = RequestField(name=name, data=value)
        field.make_multipart()
        preamble += f"--{boundary}\r\n{field.render_headers()}{value}\r\n".encode("utf-8")
    file_field = RequestField(name="file", data=b"", filename=filename)
    file_field.make_multipart(content_type="application/octet-stream")
    preamble += f"--{boundary}\r\n{file_field.render_headers()}".encode("utf-8")
    epilogue = f"\r\n--{boundary}--\r\n".encode("utf-8")

    def parts() -> Iterator[bytes]:
        yield preamble
        yield from content.chunks
        yield epilogue

    if content.length is None:
        return parts()
    return _SizedBody(parts(), len(preamble) + content.length + len(epilogue))


class FilesClient:
    """Query, download, and upload files using one profile-bound migration connection."""

    def __init__(
        self,
        connection: MigrationConnection,
        session: Optional[requests.Session] = None,
    ) -> None:
        """Initialize a file client.

        Args:
            connection: Profile-bound connection to the file service.
            session: Session for every request; a profile-bound session when None.
        """
        self._connection = connection
        self._base_url = f"{connection.base_url}/nifile/v1/service-groups/Default"
        self._session = session or connection.create_session(
            ("nifile/v1/service-groups/Default/query-files",)
        )

    @contextmanager
    def download_file(self, file_id: str) -> Iterator[FileContent]:
        """Stream one file's bytes; the download is closed when the context exits."""
        response = self._session.get(
            f"{self._base_url}/files/{quote(file_id, safe='')}/data",
            headers={"Accept-Encoding": "identity"},
            stream=True,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        try:
            response.raise_for_status()
            yield FileContent(
                chunks=response.iter_content(CHUNK_SIZE),
                length=_content_length(response),
            )
        finally:
            response.close()

    def upload_file(
        self,
        file_id: str,
        workspace_id: str,
        filename: str,
        properties: Mapping[str, Any],
        content: FileContent,
    ) -> str:
        """Upload a file into a workspace, requesting a caller-assigned ID.

        Args:
            file_id: 24-character hex ID requested for the uploaded file.
            workspace_id: Workspace that will own the file.
            filename: Name of the uploaded file part.
            properties: File properties to store as metadata.
            content: The file bytes to upload.

        Returns:
            The ID the server assigned, which may differ from ``file_id``.

        Raises:
            click.ClickException: If the profile is readonly.
            ValueError: If the response URI is not a file resource with a 24-hex ID.
        """
        if self._connection.readonly:
            raise click.ClickException(
                f"Cannot upload a file: profile '{self._connection.profile_name}' "
                "is in readonly mode"
            )
        boundary = uuid.uuid4().hex
        fields = {"id": file_id, "metadata": json.dumps(dict(properties))}
        # Only the query-files route permits replaying POST requests; streamed uploads do not.
        response = self._session.post(
            f"{self._base_url}/upload-files",
            params={"workspace": workspace_id},
            data=_multipart_body(boundary, fields, filename, content),
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
        response.raise_for_status()
        uri = _UploadResponse.model_validate(response.json()).uri
        path = urlsplit(uri).path
        match = re.fullmatch(r"/nifile/v1/service-groups/Default/files/([0-9a-fA-F]{24})/?", path)
        if match is None:
            raise ValueError(f"Upload response URI '{uri}' does not contain a valid file ID")
        return match.group(1)

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


def _content_length(response: requests.Response) -> Optional[int]:
    """Return the length of the bytes iter_content yields, when known."""
    # iter_content decodes compressed bodies, so an encoded Content-Length would be wrong.
    if response.headers.get("Content-Encoding", "identity").lower() != "identity":
        return None
    value = response.headers.get("Content-Length", "")
    return int(value) if value.isdigit() else None
