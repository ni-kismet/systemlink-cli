"""Unit tests for migration write sessions, retry logging, and the writer."""

import logging
from typing import Any, Dict, List, Optional

import pytest
import requests
from urllib3.exceptions import MaxRetryError, ProtocolError
from urllib3.response import HTTPResponse

from slcli.migration.api import correlation_id
from slcli.migration.connection import LoggingRetry, MigrationConnection
from slcli.migration.flows.migrate import partition
from slcli.migration.testmonitor.writer import TestMonitorWriter, error_names

CONNECTION = MigrationConnection("destination", "https://dest", {"x-ni-api-key": "secret"})


def _retry_of(session: requests.Session) -> Any:
    return session.get_adapter("https://dest").max_retries  # type: ignore[attr-defined]


def test_write_session_never_replays_ambiguous_failures() -> None:
    """Writes retry refused connections and throttling only, never read errors or 5xx."""
    retry = _retry_of(CONNECTION.create_write_session())

    assert isinstance(retry, LoggingRetry)
    assert retry.read == 0
    assert retry.other == 0
    assert set(retry.status_forcelist) == {429, 503}
    assert retry.is_retry("POST", 429)
    assert not retry.is_retry("POST", 500)
    assert not retry.is_retry("POST", 502)


def test_query_session_logs_retries() -> None:
    """Query sessions use the logging retry policy."""
    assert isinstance(_retry_of(CONNECTION.create_session()), LoggingRetry)


def test_retry_logs_attempt_and_correlation(caplog: pytest.LogCaptureFixture) -> None:
    """Each retry decision and exhaustion is logged with the correlation ID."""
    retry = LoggingRetry(total=1, status_forcelist=(503,), allowed_methods=None, backoff_factor=0)
    response = HTTPResponse(status=503, headers={"x-correlation-id": "corr-1"})

    with caplog.at_level(logging.WARNING, logger="slcli.migration.connection"):
        retry = retry.increment("POST", "/nitestmonitor/v2/results", response=response)
        with pytest.raises(MaxRetryError):
            retry.increment("POST", "/nitestmonitor/v2/results", response=response)

    assert [r.getMessage() for r in caplog.records] == [
        "HTTP retry: POST /nitestmonitor/v2/results status=503 attempt=1 backoff=0.0s "
        "correlation_id=corr-1",
        "HTTP retry exhausted: POST /nitestmonitor/v2/results status=503 correlation_id=corr-1",
    ]


def test_write_read_error_is_not_retried() -> None:
    """A read error after sending a write is surfaced instead of replayed."""
    retry = _retry_of(CONNECTION.create_write_session())

    with pytest.raises(MaxRetryError) as raised:
        retry.increment("POST", "/results", error=ProtocolError("reset"))
    assert isinstance(raised.value.reason, ProtocolError)


@pytest.mark.parametrize(
    "headers, expected",
    [
        ({"x-ni-correlation-id": "a", "x-request-id": "b"}, "a"),
        ({"request-id": "c"}, "c"),
        ({"other": "d"}, None),
        (None, None),
    ],
)
def test_correlation_id_prefers_known_headers(
    headers: Optional[Dict[str, str]], expected: Optional[str]
) -> None:
    """Only allow-listed headers are reported, in priority order."""
    assert correlation_id(headers) == expected


class _FakeSession(requests.Session):
    def __init__(self, body: Dict[str, Any], status: int = 200) -> None:
        super().__init__()
        self.body = body
        self.status = status
        self.posts: List[Dict[str, Any]] = []

    def post(self, url: Any, data: Any = None, json: Any = None, **kwargs: Any) -> Any:
        self.posts.append({"url": url, "json": json})
        response = requests.Response()
        response.status_code = self.status
        response.headers["x-correlation-id"] = "corr"
        response._content = __import__("json").dumps(self.body).encode()
        return response


def test_writer_returns_partial_success() -> None:
    """Created, failed, and error details of a partial success are returned, not raised."""
    session = _FakeSession(
        {
            "results": [{"id": "r1"}],
            "failed": [{"programName": "bad"}],
            "error": {"name": "Skyline.OneOrMoreErrorsOccurred", "innerErrors": [{"name": "X"}]},
        }
    )
    writer = TestMonitorWriter(CONNECTION, session=session, query_session=session)

    response = writer.create_results([{"programName": "ok"}, {"programName": "bad"}])

    assert session.posts == [
        {
            "url": "https://dest/nitestmonitor/v2/results",
            "json": {"results": [{"programName": "ok"}, {"programName": "bad"}]},
        }
    ]
    assert response.created == [{"id": "r1"}]
    assert response.failed == [{"programName": "bad"}]
    assert response.correlation_id == "corr"
    assert error_names(response.error) == ["Skyline.OneOrMoreErrorsOccurred", "X"]


def test_writer_raises_http_errors() -> None:
    """A failed request raises so the caller can report its status and correlation."""
    session = _FakeSession({}, status=400)
    writer = TestMonitorWriter(CONNECTION, session=session, query_session=session)

    with pytest.raises(requests.HTTPError):
        writer.update_results([{"id": "r1"}])
    assert session.posts[0]["url"] == "https://dest/nitestmonitor/v2/update-results"


def test_partition_keeps_order() -> None:
    """Batches are stable and bounded."""
    assert partition([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]
    assert partition([], 3) == []
    with pytest.raises(ValueError):
        partition([1], 0)
