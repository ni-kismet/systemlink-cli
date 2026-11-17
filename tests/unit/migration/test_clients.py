"""Contract tests for migration API clients."""

import json
from contextlib import contextmanager
from datetime import datetime, timezone
from email.message import Message
from email.parser import BytesParser
from typing import Any, Dict, Iterator, List, Optional, Union

import click
import pytest
import requests
from pydantic import ValidationError
from requests.adapters import HTTPAdapter

from slcli.migration.connection import MigrationConnection
from slcli.migration.files.client import FileContent, FilesClient, _multipart_body
from slcli.migration.files.client import PAGE_SIZE as FILES_PAGE_SIZE
from slcli.migration.testmonitor.client import PAGE_SIZE, TestMonitorClient
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


def _result(result_id: str) -> Dict[str, object]:
    return {
        "id": result_id,
        "partNumber": "part",
        "status": {"statusType": "PASSED", "statusName": "Passed"},
        "updatedAt": "2026-01-01T00:00:00Z",
        "unusedField": True,
    }


def test_query_results_follows_every_continuation_token() -> None:
    """Results are typed and paged to completion with a parameterized filter."""
    session = FakeSession(
        [
            {"results": [_result("r1")], "continuationToken": "next"},
            {"results": [_result("r2")], "continuationToken": None},
        ]
    )
    client = TestMonitorClient(CONNECTION, session)  # type: ignore[arg-type]

    results = list(client.query_results("workspace == @0", ["workspace-id"]))

    assert [r.id for r in results] == ["r1", "r2"]
    assert results[0].status.status_type == "PASSED"
    assert results[0].updated_at == datetime(2026, 1, 1, tzinfo=timezone.utc)
    assert session.calls[0]["url"] == "https://source/nitestmonitor/v2/query-results"
    assert session.calls[0]["json"] == {
        "filter": "workspace == @0",
        "substitutions": ["workspace-id"],
        "take": PAGE_SIZE,
        "descending": False,
    }
    assert session.calls[1]["json"]["continuationToken"] == "next"


def test_query_products_reads_product_endpoint() -> None:
    """Products are queried unfiltered from their own endpoint."""
    session = FakeSession([{"products": [{"id": "p1", "partNumber": "part"}]}])
    client = TestMonitorClient(CONNECTION, session)  # type: ignore[arg-type]

    assert [p.part_number for p in client.query_products()] == ["part"]
    assert session.calls[0]["url"].endswith("/query-products")
    assert "filter" not in session.calls[0]["json"]


def test_query_results_accepts_null_property_values() -> None:
    """Null result properties do not prevent discovery of the entire workspace."""
    session = FakeSession(
        [{"results": [{**_result("r1"), "properties": {"TEST_STOP_TIME": None, "owner": "test"}}]}]
    )
    client = TestMonitorClient(CONNECTION, session)  # type: ignore[arg-type]

    [result] = client.query_results()
    assert result.properties == {"TEST_STOP_TIME": None, "owner": "test"}


def test_query_files_pages_with_skip_until_short_page() -> None:
    """Files page with skip/take per workspace and stop after a short page."""
    full_page = [{"id": f"f{i}", "properties": {"Name": f"n{i}"}} for i in range(FILES_PAGE_SIZE)]
    session = FakeSession(
        [
            {"availableFiles": full_page},
            {"availableFiles": [{"id": "last", "size64": 9}]},
        ]
    )
    client = FilesClient(CONNECTION, session)  # type: ignore[arg-type]

    files = list(client.query_files("lab-id"))

    assert len(files) == FILES_PAGE_SIZE + 1
    assert files[0].name == "n0"
    assert files[-1].id == "last"
    assert files[-1].size_bytes == 9
    assert session.calls[0]["url"] == (
        "https://source/nifile/v1/service-groups/Default/query-files"
    )
    assert session.calls[0]["params"] == {
        "skip": 0,
        "take": FILES_PAGE_SIZE,
        "workspace": "lab-id",
    }
    assert session.calls[1]["params"] == {
        "skip": FILES_PAGE_SIZE,
        "take": FILES_PAGE_SIZE,
        "workspace": "lab-id",
    }
    assert session.calls[0]["json"] == {}


def test_query_files_fetches_empty_page_after_exact_full_page() -> None:
    """An exact page-size result is followed by an empty page to finish paging."""
    full_page = [{"id": f"f{i}"} for i in range(FILES_PAGE_SIZE)]
    session = FakeSession([{"availableFiles": full_page}, {"availableFiles": []}])
    client = FilesClient(CONNECTION, session)  # type: ignore[arg-type]

    files = list(client.query_files("lab-id"))

    assert len(files) == FILES_PAGE_SIZE
    assert [call["params"]["skip"] for call in session.calls] == [0, FILES_PAGE_SIZE]


def test_files_client_enables_post_retries_only_for_query_files_route() -> None:
    """The client's default session safely retries read-only query POSTs."""
    client = FilesClient(CONNECTION)

    query_adapter = client._session.get_adapter(
        "https://source/nifile/v1/service-groups/Default/query-files"
    )
    assert isinstance(query_adapter, HTTPAdapter)
    assert "POST" in (query_adapter.max_retries.allowed_methods or ())
    assert 429 in (query_adapter.max_retries.status_forcelist or ())
    assert 503 in (query_adapter.max_retries.status_forcelist or ())

    write_adapter = client._session.get_adapter(
        "https://source/nifile/v1/service-groups/Default/upload-files"
    )
    assert isinstance(write_adapter, HTTPAdapter)
    assert "POST" not in (write_adapter.max_retries.allowed_methods or ())


class FakeDownload:
    """A streamed download response."""

    def __init__(self, chunks: List[bytes], headers: Dict[str, str]) -> None:
        """Store the chunks and headers."""
        self.chunks = chunks
        self.headers = headers
        self.closed = False

    def raise_for_status(self) -> None:
        """Succeed."""

    def iter_content(self, chunk_size: int) -> Iterator[bytes]:
        """Yield the configured chunks."""
        return iter(self.chunks)

    def close(self) -> None:
        """Record that the download was released."""
        self.closed = True


class FakeFileSession(FakeSession):
    """Serve one download and answer one upload with a URI."""

    def __init__(self, download: Optional[FakeDownload] = None, uri: str = "") -> None:
        """Store the download and the upload response URI."""
        super().__init__([{"uri": uri}])
        self.download = download

    def get(self, url: str, **kwargs: Any) -> Any:
        """Record a GET and return the download."""
        self.calls.append({"url": url, **kwargs})
        return self.download


NEW_ID = "ab" * 12


def _parse_multipart(content_type: str, body: bytes) -> Dict[str, Message]:
    message = BytesParser().parsebytes(f"Content-Type: {content_type}\r\n\r\n".encode() + body)
    parts: List[Message] = message.get_payload()  # type: ignore[assignment]
    return {str(part.get_param("name", header="content-disposition")): part for part in parts}


def test_download_file_streams_by_id_and_closes() -> None:
    """Downloads stream raw bytes for the file and release the connection afterwards."""
    download = FakeDownload([b"ab", b"c"], {"Content-Length": "3"})
    session = FakeFileSession(download)
    client = FilesClient(CONNECTION, session)  # type: ignore[arg-type]

    with client.download_file("a/b") as content:
        assert b"".join(content.chunks) == b"abc"
        assert content.length == 3
        closed_while_streaming = download.closed

    assert not closed_while_streaming
    assert download.closed
    assert session.calls[0]["url"] == (
        "https://source/nifile/v1/service-groups/Default/files/a%2Fb/data"
    )
    assert session.calls[0]["stream"] is True
    assert session.calls[0]["headers"] == {"Accept-Encoding": "identity"}


@pytest.mark.parametrize(
    "headers",
    [{}, {"Content-Length": "3", "Content-Encoding": "gzip"}, {"Content-Length": "x"}],
)
def test_download_length_is_unknown_without_a_usable_content_length(
    headers: Dict[str, str],
) -> None:
    """Missing, invalid, or encoded lengths are not reported as the decoded length."""
    session = FakeFileSession(FakeDownload([b"abc"], headers))
    client = FilesClient(CONNECTION, session)  # type: ignore[arg-type]

    with client.download_file("f") as content:
        assert content.length is None


def test_upload_file_sends_mapped_id_metadata_and_streamed_file() -> None:
    """The upload is a multipart form with the requested ID, metadata, and file bytes."""
    session = FakeFileSession(uri=f"/nifile/v1/service-groups/Default/files/{NEW_ID}")
    client = FilesClient(CONNECTION, session)  # type: ignore[arg-type]
    properties = {"Name": 'q"uote é.txt', "Owner": "lab"}

    uploaded_id = client.upload_file(
        NEW_ID,
        "dest-ws",
        'q"uote é.txt',
        properties,
        FileContent(chunks=iter([b"ab", b"c"]), length=3),
    )

    assert uploaded_id == NEW_ID
    [call] = session.calls
    assert call["url"] == "https://source/nifile/v1/service-groups/Default/upload-files"
    assert call["params"] == {"workspace": "dest-ws"}
    declared_length = len(call["data"])
    body = b"".join(call["data"])
    assert declared_length == len(body)
    parts = _parse_multipart(call["headers"]["Content-Type"], body)
    assert parts["id"].get_payload() == NEW_ID
    assert json.loads(str(parts["metadata"].get_payload())) == properties
    assert parts["file"].get_payload(decode=True) == b"abc"
    assert 'name="file"; filename="q%22uote é.txt"'.encode() in body


def test_upload_body_sets_content_length_only_when_known() -> None:
    """A known length avoids chunked encoding; an unknown length streams chunked."""
    sized = FileContent(chunks=iter([b"abc"]), length=3)
    unsized = FileContent(chunks=iter([b"abc"]))

    sized_request = requests.Request(
        "POST", "https://x", data=_multipart_body("b", {"id": NEW_ID}, "a", sized)
    ).prepare()
    unsized_request = requests.Request(
        "POST", "https://x", data=_multipart_body("b", {"id": NEW_ID}, "a", unsized)
    ).prepare()

    assert "Transfer-Encoding" not in sized_request.headers
    assert int(sized_request.headers["Content-Length"]) == len(
        b"".join(sized_request.body)  # type: ignore[arg-type]
    )
    assert unsized_request.headers["Transfer-Encoding"] == "chunked"


def test_upload_file_returns_the_server_assigned_id() -> None:
    """A destination that ignores the requested ID reports the ID it assigned."""
    actual_id = "cd" * 12
    session = FakeFileSession(uri=f"/nifile/v1/service-groups/Default/files/{actual_id}/")
    client = FilesClient(CONNECTION, session)  # type: ignore[arg-type]

    assert client.upload_file(NEW_ID, "ws", "a", {}, FileContent(chunks=[b""], length=0)) == (
        actual_id
    )


@pytest.mark.parametrize(
    "uri",
    [
        "",
        "/nifile/v1/service-groups/Default/files/",
        "not-a-file-uri",
        "/nifile/v1/service-groups/Default/files/other",
        "/nifile/v1/service-groups/Default/files/" + "ab" * 11,
        "/nifile/v1/service-groups/Default/files/" + "gh" * 12,
        "/wrong/files/" + NEW_ID,
    ],
)
def test_upload_file_rejects_malformed_response_uri(uri: str) -> None:
    """Invalid destination identities cannot be persisted for reference repair."""
    session = FakeFileSession(uri=uri)
    client = FilesClient(CONNECTION, session)  # type: ignore[arg-type]

    with pytest.raises(ValueError, match="valid file ID"):
        client.upload_file(NEW_ID, "ws", "a", {}, FileContent(chunks=[], length=0))


def test_upload_file_accepts_absolute_response_uri() -> None:
    """Absolute resource URIs are validated using their path."""
    session = FakeFileSession(
        uri=f"https://destination/nifile/v1/service-groups/Default/files/{NEW_ID}"
    )
    client = FilesClient(CONNECTION, session)  # type: ignore[arg-type]

    assert client.upload_file(NEW_ID, "ws", "a", {}, FileContent([], 0)) == NEW_ID


def test_upload_file_is_rejected_for_a_readonly_profile() -> None:
    """Readonly destination profiles never receive uploads."""
    session = FakeFileSession()
    connection = MigrationConnection("dest", "https://dest", {}, True, readonly=True)
    client = FilesClient(connection, session)  # type: ignore[arg-type]

    with pytest.raises(click.ClickException, match="readonly mode"):
        client.upload_file(NEW_ID, "ws", "a", {}, FileContent(chunks=[b""], length=0))
    assert session.calls == []


def test_query_rejects_malformed_response() -> None:
    """Responses that do not match the API contract fail at the client boundary."""
    session = FakeSession([{"results": [{"id": "r1"}]}])
    client = TestMonitorClient(CONNECTION, session)  # type: ignore[arg-type]

    with pytest.raises(ValidationError):
        list(client.query_results())


def test_query_rejects_timestamp_without_timezone() -> None:
    """SLS sends UTC with a Z suffix; an unzoned timestamp is not silently guessed."""
    session = FakeSession([{"results": [{**_result("r1"), "updatedAt": "2026-01-01T00:00:00"}]}])
    client = TestMonitorClient(CONNECTION, session)  # type: ignore[arg-type]

    with pytest.raises(ValidationError, match="timezone"):
        list(client.query_results())


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
def test_connection_requests_use_ssl_context(
    monkeypatch: pytest.MonkeyPatch, verify: Union[bool, str], fails: bool
) -> None:
    """Each request uses and restores the connection's TLS context, even on failure."""
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

    def send(*args: Any, **kwargs: Any) -> FakeResponse:
        assert active
        if fails:
            raise requests.ConnectionError("offline")
        return FakeResponse({})

    monkeypatch.setattr("slcli.migration.connection.use_standard_ssl_context", ssl_context)
    monkeypatch.setattr(requests.Session, "request", send)
    session = MigrationConnection("source", "https://source", {}, verify).create_session()

    for _ in range(2):
        if fails:
            with pytest.raises(requests.ConnectionError, match="offline"):
                session.post("https://source/query")
        else:
            session.get("https://source/query")
    assert context_values == [verify, verify]
    assert not active
