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
from tests.replay.server import REPLAY_MISS_STATUS, Deck, FakeServer, Upstream
from tests.replay.tape import Exchange, Tape

# Unit tests stub requests.get/post; sessions still reach the local servers.
http = requests.Session()


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
                body = json.dumps(
                    {
                        "call": upstream.counts[self.path],
                        "received": json.loads(self.rfile.read(length)) if length else None,
                        "self": f"{upstream.url}/item",
                    }
                ).encode()
                status = 201 if self.command == "POST" else 200
                if self.path.startswith("/status/"):
                    status = int(self.path.rsplit("/", 1)[-1])
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
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


def test_replay_handler_failure_is_reported_as_a_miss(tmp_path: Path) -> None:
    deck = Deck(tmp_path / "missing.yaml")

    response = _serve(deck, lambda url: http.post(f"{url}/svc/items", data=b"not json"))

    assert response.status_code == REPLAY_MISS_STATUS
    assert len(deck.misses) == 1 and "JSONDecodeError" in deck.misses[0]


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
