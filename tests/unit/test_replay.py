"""Tests for the E2E record/replay fake."""

import json
import socket
import threading
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, Generator, List

import pytest
import requests

from slcli.migration.annotations import STARTED_AT
from tests.replay import server as replay_server
from tests.replay.server import REPLAY_MISS_STATUS, Deck, FakeServer, Upstream
from tests.replay.tape import Exchange, FileData, Tape, parse_request_body

# Unit tests stub requests.get/post; sessions still reach the local servers.
http = requests.Session()

# An ar archive header followed by bytes that are not valid UTF-8, like a real package.
PACKAGE = b"!<arch>\n" + bytes(range(256)) * 4


def _summarize(body: bytes, content_type: str) -> Any:
    if not body:
        return None
    if "json" in content_type:
        return json.loads(body)
    return {"bytes": len(body)}


class _Upstream:
    """Echoes each request with a per-path call count, and records received headers."""

    def __init__(self) -> None:
        self.headers: List[Dict[str, str]] = []
        self.counts: Dict[str, int] = {}
        upstream = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def _echo(self) -> None:
                upstream.headers.append({k.lower(): v for k, v in self.headers.items()})
                upstream.counts[self.path] = upstream.counts.get(self.path, 0) + 1
                length = int(self.headers.get("Content-Length") or 0)
                received = self.rfile.read(length) if length else b""
                content_type = "application/json"
                if self.path.startswith("/files/"):
                    body, content_type = PACKAGE, "application/octet-stream"
                else:
                    body = json.dumps(
                        {
                            "call": upstream.counts[self.path],
                            "received": _summarize(received, self.headers["Content-Type"]),
                            "self": f"{upstream.url}/item",
                        }
                    ).encode()
                status = 201 if self.command == "POST" else 200
                if self.path.startswith("/status/"):
                    status = int(self.path.rsplit("/", 1)[-1])
                self.send_response(status)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            do_GET = do_POST = _echo  # noqa: N815 - names required by BaseHTTPRequestHandler

            def log_message(self, format: str, *args: Any) -> None:
                pass

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()


@pytest.fixture
def upstream() -> Generator[_Upstream, None, None]:
    server = _Upstream()
    yield server
    server.server.shutdown()
    server.server.server_close()


def _serve(deck: Deck, calls: Callable[[str], Any]) -> Any:
    fake = FakeServer(deck).start()
    try:
        return calls(fake.base_url)
    finally:
        fake.stop()
        deck.save()


def _record(upstream: _Upstream, path: Path, calls: Callable[[str], Any]) -> str:
    session = requests.Session()
    session.headers["x-ni-api-key"] = "real-secret"
    _serve(Deck(path, Upstream(upstream.url, session)), calls)
    return path.read_text(encoding="utf-8")


def test_recording_injects_credentials_but_never_stores_them(
    upstream: _Upstream, tmp_path: Path
) -> None:
    tape = _record(
        upstream,
        tmp_path / "t.yaml",
        lambda url: http.get(f"{url}/svc/items", headers={"x-ni-api-key": "dummy"}),
    )

    assert upstream.headers[0]["x-ni-api-key"] == "real-secret"
    assert "real-secret" not in tape and "dummy" not in tape
    assert upstream.url not in tape and "{{base_url}}/item" in tape


def test_replay_serves_recorded_responses_addressed_to_the_fake(
    upstream: _Upstream, tmp_path: Path
) -> None:
    path = tmp_path / "t.yaml"
    _record(upstream, path, lambda url: http.get(f"{url}/svc/items?b=2&a=1"))

    response, base_url = _serve(Deck(path), lambda url: (http.get(f"{url}/svc/items?a=1&b=2"), url))

    assert response.status_code == 200
    assert response.json() == {"call": 1, "received": None, "self": f"{base_url}/item"}


def test_repeated_requests_replay_in_recorded_order(upstream: _Upstream, tmp_path: Path) -> None:
    path = tmp_path / "t.yaml"
    _record(upstream, path, lambda url: [http.get(f"{url}/svc/items") for _ in "ab"])

    calls = _serve(Deck(path), lambda url: [http.get(f"{url}/svc/items") for _ in "abc"])

    assert [c.status_code for c in calls] == [200, 200, REPLAY_MISS_STATUS]
    assert [c.json().get("call") for c in calls[:2]] == [1, 2]


@pytest.mark.parametrize("status", [404, 500])
def test_recorded_error_status_is_replayed_not_reported_as_a_miss(
    upstream: _Upstream, tmp_path: Path, status: int
) -> None:
    path = tmp_path / "t.yaml"
    _record(upstream, path, lambda url: http.get(f"{url}/status/{status}"))
    deck = Deck(path)

    response = _serve(deck, lambda url: http.get(f"{url}/status/{status}"))

    assert response.status_code == status
    assert response.json()["call"] == 1
    assert deck.misses == []


def test_timestamps_are_ignored_but_other_body_changes_miss(
    upstream: _Upstream, tmp_path: Path
) -> None:
    path = tmp_path / "t.yaml"
    recorded = {"name": "a", "properties": {STARTED_AT: "2026-01-01T00:00:00+00:00"}}
    _record(upstream, path, lambda url: http.post(f"{url}/svc/items", json=recorded))
    deck = Deck(path)

    later = {"name": "a", "properties": {STARTED_AT: "2026-11-19T12:00:00+00:00"}}
    matched, missed = _serve(
        deck,
        lambda url: (
            http.post(f"{url}/svc/items", json=later),
            http.post(f"{url}/svc/items", json={**later, "name": "b"}),
        ),
    )

    assert (matched.status_code, missed.status_code) == (201, REPLAY_MISS_STATUS)
    assert len(deck.misses) == 1


def test_hand_written_tape_is_served(tmp_path: Path) -> None:
    path = tmp_path / "t.yaml"
    path.write_text(
        """\
exchanges:
- request: POST /svc/query
  note: Second page added by hand to exercise pagination.
  body:
    take: 1
  response:
    status: 200
    contentType: application/json
    body:
      items: [{id: a}]
      next: "{{base_url}}/svc/query?page=2"
""",
        encoding="utf-8",
    )

    response, base_url = _serve(
        Deck(path), lambda url: (http.post(f"{url}/svc/query", json={"take": 1}), url)
    )

    assert response.json() == {"items": [{"id": "a"}], "next": f"{base_url}/svc/query?page=2"}


def test_generated_values_are_recorded_and_replayed_in_order(
    upstream: _Upstream, tmp_path: Path
) -> None:
    path = tmp_path / "t.yaml"
    fresh = iter(["first", "second"])
    recording = Deck(path, Upstream(upstream.url, requests.Session()))
    recorded = [recording.generated("migrationId", lambda: next(fresh)) for _ in "ab"]
    recording.save()

    replaying = Deck(path)
    replayed = [replaying.generated("migrationId", lambda: "invented") for _ in "ab"]

    assert recorded == replayed == ["first", "second"]
    with pytest.raises(LookupError, match="migrationId"):
        replaying.generated("migrationId", lambda: "invented")


def test_replay_handler_failure_is_reported_as_a_miss(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def fail(*_: Any) -> str:
        raise ValueError("unmatchable")

    monkeypatch.setattr(replay_server, "request_key", fail)
    deck = Deck(tmp_path / "missing.yaml")

    response = _serve(deck, lambda url: http.post(f"{url}/svc/items", json={}))

    assert response.status_code == REPLAY_MISS_STATUS
    assert len(deck.misses) == 1 and "ValueError: unmatchable" in deck.misses[0]


def test_recording_upstream_failure_is_reported_as_a_miss(tmp_path: Path) -> None:
    with socket.socket() as closed:
        closed.bind(("127.0.0.1", 0))
        unreachable = f"http://127.0.0.1:{closed.getsockname()[1]}"
    deck = Deck(tmp_path / "t.yaml", Upstream(unreachable, requests.Session()))

    response = _serve(deck, lambda url: http.get(f"{url}/svc/items"))

    assert response.status_code == REPLAY_MISS_STATUS
    assert len(deck.misses) == 1 and "ConnectionError" in deck.misses[0]
    assert deck.tape.exchanges == []


def test_missing_tape_misses_every_request_and_is_not_created(tmp_path: Path) -> None:
    path = tmp_path / "missing.yaml"
    deck = Deck(path)

    calls = _serve(
        deck,
        lambda url: [http.get(f"{url}/svc/items"), http.post(f"{url}/svc/items", json={})],
    )

    assert [c.status_code for c in calls] == [REPLAY_MISS_STATUS, REPLAY_MISS_STATUS]
    assert len(deck.misses) == 2
    assert not path.exists()


def test_replay_never_rewrites_its_tape(upstream: _Upstream, tmp_path: Path) -> None:
    path = tmp_path / "t.yaml"
    original = _record(upstream, path, lambda url: http.get(f"{url}/svc/items"))

    _serve(Deck(path), lambda url: http.get(f"{url}/svc/other"))

    assert path.read_text(encoding="utf-8") == original


def test_recording_nothing_writes_no_tape(upstream: _Upstream, tmp_path: Path) -> None:
    path = tmp_path / "t.yaml"

    Deck(path, Upstream(upstream.url, requests.Session())).save()

    assert not path.exists()


def test_text_response_round_trips_with_base_url_replaced(tmp_path: Path) -> None:
    path = tmp_path / "t.yaml"
    exchange = Exchange.recorded(
        "GET",
        "/svc/readme",
        b"",
        200,
        "text/plain; charset=utf-8",
        b"See http://upstream/svc/item\nfor details.\n",
        "http://upstream",
    )
    Tape([exchange]).save(path)

    [loaded] = Tape.load(path).exchanges

    assert loaded.response_body == "See {{base_url}}/svc/item\nfor details.\n"
    assert loaded.response_bytes("http://fake") == b"See http://fake/svc/item\nfor details.\n"


def test_concurrent_identical_requests_get_distinct_exchanges(
    upstream: _Upstream, tmp_path: Path
) -> None:
    path = tmp_path / "t.yaml"
    count = 8
    _record(upstream, path, lambda url: [http.get(f"{url}/svc/items") for _ in range(count)])
    deck = Deck(path)

    def get_concurrently(url: str) -> List[requests.Response]:
        def get(_: int) -> requests.Response:
            with requests.Session() as session:
                return session.get(f"{url}/svc/items")

        with ThreadPoolExecutor(max_workers=count) as pool:
            return list(pool.map(get, range(count)))

    responses = _serve(deck, get_concurrently)

    assert sorted(r.json()["call"] for r in responses) == list(range(1, count + 1))
    assert deck.unserved() == [] and deck.misses == []


def _upload(url: str, content: bytes = PACKAGE) -> requests.Response:
    return http.post(
        f"{url}/nifeed/v1/feeds/f1/packages?shouldOverwrite=false",
        files={"package": ("foo_1.0_x64.nipkg", content, "application/octet-stream")},
    )


def test_downloaded_file_is_saved_beside_the_tape_and_replayed_byte_for_byte(
    upstream: _Upstream, tmp_path: Path
) -> None:
    path = tmp_path / "t.yaml"
    tape = _record(upstream, path, lambda url: http.get(f"{url}/files/packages/foo_1.0_x64.nipkg"))

    [saved] = (tmp_path / "t").iterdir()
    assert saved.name.endswith("-foo_1.0_x64.nipkg") and saved.read_bytes() == PACKAGE
    assert f"body: !file 't/{saved.name}'" in tape

    deck = Deck(path)
    response = _serve(deck, lambda url: http.get(f"{url}/files/packages/foo_1.0_x64.nipkg"))

    assert response.status_code == 200
    assert response.headers["Content-Type"] == "application/octet-stream"
    assert response.content == PACKAGE
    assert deck.misses == []


def test_multipart_upload_matches_despite_new_boundary_and_misses_other_content(
    upstream: _Upstream, tmp_path: Path
) -> None:
    path = tmp_path / "t.yaml"
    tape = _record(upstream, path, _upload)

    [saved] = (tmp_path / "t").iterdir()
    assert saved.read_bytes() == PACKAGE
    assert "name: package" in tape and "filename: foo_1.0_x64.nipkg" in tape

    deck = Deck(path)
    matched, missed = _serve(deck, lambda url: (_upload(url), _upload(url, PACKAGE + b"x")))

    assert (matched.status_code, missed.status_code) == (201, REPLAY_MISS_STATUS)
    assert matched.json()["call"] == 1
    assert len(deck.misses) == 1


def test_multipart_text_fields_are_stored_inline_and_matched(
    upstream: _Upstream, tmp_path: Path
) -> None:
    path = tmp_path / "t.yaml"

    def upload(url: str, workspace: str) -> requests.Response:
        return http.post(
            f"{url}/svc/upload",
            data={"metadata": json.dumps({"workspace": workspace})},
            files={"file": ("a.bin", PACKAGE)},
        )

    tape = _record(upstream, path, lambda url: upload(url, "ws1"))
    assert "workspace: ws1" in tape

    responses = _serve(Deck(path), lambda url: (upload(url, "ws2"), upload(url, "ws1")))

    assert [r.status_code for r in responses] == [REPLAY_MISS_STATUS, 201]


def test_multipart_non_ascii_filename_is_stored_readably(
    upstream: _Upstream, tmp_path: Path
) -> None:
    path = tmp_path / "t.yaml"

    def upload(url: str, filename: str) -> requests.Response:
        return http.post(f"{url}/svc/upload", files={"file": (filename, PACKAGE)})

    tape = _record(upstream, path, lambda url: upload(url, "résumé.bin"))
    assert "filename: résumé.bin" in tape

    # Same UTF-8 length, so the old parser garbled both names identically and matched them.
    responses = _serve(
        Deck(path), lambda url: (upload(url, "rèsumè.bin"), upload(url, "résumé.bin"))
    )

    assert [r.status_code for r in responses] == [REPLAY_MISS_STATUS, 201]


@pytest.mark.parametrize(
    "content", [b"before--BOUNDARYafter", b"line\r\n--BOUNDARY-ish\r\n", b"ends with crlf\r\n"]
)
def test_multipart_file_keeps_boundary_like_bytes_and_trailing_crlf(content: bytes) -> None:
    body = (
        b"--BOUNDARY\r\n"
        b'Content-Disposition: form-data; name="file"; filename="a.bin"\r\n\r\n'
        + content
        + b"\r\n--BOUNDARY--\r\n"
    )

    [part] = parse_request_body("/svc/upload", body, "multipart/form-data; boundary=BOUNDARY")[
        "multipart"
    ]

    assert part["body"] == FileData("a.bin", content)


def test_rerecording_removes_files_the_new_tape_no_longer_uses(
    upstream: _Upstream, tmp_path: Path
) -> None:
    path = tmp_path / "t.yaml"
    _record(upstream, path, lambda url: http.get(f"{url}/files/packages/old.nipkg"))
    _record(upstream, path, lambda url: http.get(f"{url}/svc/items"))

    assert not (tmp_path / "t").exists()


def test_hand_written_file_reference_is_served(tmp_path: Path) -> None:
    (tmp_path / "t").mkdir()
    (tmp_path / "t" / "pkg.ipk").write_bytes(PACKAGE)
    path = tmp_path / "t.yaml"
    path.write_text(
        """\
exchanges:
- request: GET /nirepo/v1/files/packages/pkg.ipk
  response:
    status: 200
    contentType: application/octet-stream
    body: !file t/pkg.ipk
""",
        encoding="utf-8",
    )

    response = _serve(Deck(path), lambda url: http.get(f"{url}/nirepo/v1/files/packages/pkg.ipk"))

    assert response.content == PACKAGE


@pytest.mark.parametrize("content_type", ["application/octet-stream", "text/plain"])
def test_recorded_binary_response_keeps_its_exact_bytes(content_type: str) -> None:
    upstream_url = "http://upstream:9090"
    received = PACKAGE + upstream_url.encode()

    exchange = Exchange.recorded(
        "GET", "/files/pkg.ipk", b"", 200, content_type, received, upstream_url
    )

    assert exchange.response_body == FileData("pkg.ipk", received)
    if content_type == "application/octet-stream":
        assert exchange.response_body.data is received


def test_recorded_download_path_error_stays_inline() -> None:
    exchange = Exchange.recorded(
        "GET",
        "/nifile/v1/service-groups/Default/files/f1/data",
        b"",
        404,
        "application/json",
        b'{"error": {"name": "Skyline.NotFound"}}',
        "http://upstream:9090",
    )

    assert exchange.response_body == {"error": {"name": "Skyline.NotFound"}}


def test_recorded_attachment_is_saved_as_a_file_even_when_text() -> None:
    upstream_url = "http://upstream:9090"
    received = f"link,{upstream_url}/x\n".encode()

    exchange = Exchange.recorded(
        "GET",
        "/nifile/v1/service-groups/Default/files/f1/data",
        b"",
        200,
        "text/csv",
        received,
        upstream_url,
        content_disposition='attachment; filename="report.csv"',
    )

    assert exchange.response_body == FileData("report.csv", received)
    assert exchange.response_body.data is received
