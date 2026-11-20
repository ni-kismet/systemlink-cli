"""Local HTTP servers that stand in for SystemLink, backed by a tape.

One fake stands in for one server. When recording, each request is forwarded to
the real server with that server's credentials and appended to the tape. When
replaying, each request is answered with the first unserved exchange whose
request matches; a request with no match gets status 598 and is reported as a miss.
"""

import json
import threading
from dataclasses import dataclass, field
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

import requests

from tests.replay.tape import Exchange, Tape, request_key

# Not a real HTTP status, so a replay miss is never mistaken for server behavior.
REPLAY_MISS_STATUS = 598

# The fake injects the real profile's credentials; the client's are never forwarded.
_DROPPED_HEADERS = frozenset(
    {
        "authorization",
        "x-ni-api-key",
        "cookie",
        "host",
        "content-length",
        "connection",
        "accept-encoding",
        "transfer-encoding",
        "keep-alive",
    }
)

Reply = Tuple[int, Optional[str], bytes]


@dataclass(frozen=True)
class Upstream:
    """A real server to record from: base URL and an authenticated session."""

    base_url: str
    session: requests.Session


@dataclass
class Deck:
    """Plays or records one server's tape.

    Values the client generates, such as migration IDs, are recorded alongside the
    exchanges and returned in the same order on replay, so requests that contain
    them match without the client inventing stand-in values.
    """

    path: Path
    upstream: Optional[Upstream] = None
    tape: Tape = field(default_factory=Tape)
    served: List[bool] = field(default_factory=list)
    misses: List[str] = field(default_factory=list)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    def __post_init__(self) -> None:
        """Load the tape when replaying; a missing tape answers nothing."""
        if not self.recording and self.path.exists():
            self.tape = Tape.load(self.path)
        self.served = [False] * len(self.tape.exchanges)

    @property
    def recording(self) -> bool:
        """Return whether requests are forwarded to a real server and recorded."""
        return self.upstream is not None

    def generated(self, name: str, generate: Callable[[], str]) -> str:
        """Return a newly generated value when recording, or the next recorded one.

        Raises:
            LookupError: If replay asks for more values than were recorded.
        """
        with self._lock:
            values = self.tape.generated.setdefault(name, [])
            if self.recording:
                values.append(generate())
                return values[-1]
            if not values:
                raise LookupError(f"{self.path.name} has no more recorded {name!r} values")
            return values.pop(0)

    def handle(
        self, method: str, path_and_query: str, body: bytes, headers: Dict[str, str], base_url: str
    ) -> Reply:
        """Record or replay one request."""
        if self.upstream is not None:
            return self._record(self.upstream, method, path_and_query, body, headers, base_url)
        parsed = json.loads(body) if body else None
        key = request_key(method, path_and_query, parsed)
        with self._lock:
            for index, exchange in enumerate(self.tape.exchanges):
                if not self.served[index] and exchange.key() == key:
                    self.served[index] = True
                    return (
                        exchange.response_status,
                        exchange.content_type,
                        exchange.response_bytes(base_url),
                    )
            self.misses.append(f"{method} {path_and_query} {body.decode()}")
        return miss(f"No unserved exchange in {self.path} matches {method} {path_and_query}")

    def unserved(self) -> List[Exchange]:
        """Return recorded exchanges that were never replayed."""
        return [e for e, done in zip(self.tape.exchanges, self.served) if not done]

    def save(self) -> None:
        """Write the tape, when recording."""
        if self.recording and (self.tape.exchanges or self.tape.generated):
            self.tape.save(self.path)

    def _record(
        self,
        upstream: Upstream,
        method: str,
        path_and_query: str,
        body: bytes,
        headers: Dict[str, str],
        base_url: str,
    ) -> Reply:
        response = upstream.session.request(
            method,
            upstream.base_url + path_and_query,
            data=body or None,
            headers={k: v for k, v in headers.items() if k.lower() not in _DROPPED_HEADERS},
            allow_redirects=False,
            timeout=300,
        )
        exchange = Exchange.recorded(
            method,
            path_and_query,
            body,
            response.status_code,
            response.headers.get("Content-Type"),
            response.content,
            upstream.base_url,
        )
        with self._lock:
            self.tape.exchanges.append(exchange)
        return exchange.response_status, exchange.content_type, exchange.response_bytes(base_url)


def miss(message: str) -> Reply:
    """Return the reply for a request the fake cannot answer."""
    return REPLAY_MISS_STATUS, "application/json", json.dumps({"replayMiss": message}).encode()


class FakeServer:
    """A threaded local server that delegates to its current deck."""

    def __init__(self, deck: Optional[Deck] = None) -> None:
        """Bind to a free local port; call :meth:`start` to serve."""
        self.deck = deck
        self._server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler_class())
        self._server.daemon_threads = True
        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)

    @property
    def base_url(self) -> str:
        """Return the URL clients use in place of the real server."""
        return f"http://127.0.0.1:{self._server.server_address[1]}"

    def start(self) -> "FakeServer":
        """Serve on a background thread."""
        self._thread.start()
        return self

    def stop(self) -> None:
        """Stop serving and release the port."""
        self._server.shutdown()
        self._server.server_close()

    def _handler_class(self) -> Callable[..., BaseHTTPRequestHandler]:
        fake = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def _serve(self) -> None:
                length = int(self.headers.get("Content-Length") or 0)
                body = self.rfile.read(length) if length else b""
                try:
                    if fake.deck is None:
                        raise RuntimeError("No tape is loaded")
                    status, content_type, payload = fake.deck.handle(
                        self.command,
                        self.path,
                        body,
                        dict(self.headers.items()),
                        fake.base_url,
                    )
                except Exception as exc:  # noqa: BLE001 - every failure must reach the client
                    status, content_type, payload = miss(f"{type(exc).__name__}: {exc}")
                self.send_response(status)
                if content_type:
                    self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            # BaseHTTPRequestHandler dispatches to these names.
            do_GET = do_POST = do_PUT = do_PATCH = do_DELETE = _serve  # noqa: N815

            def log_message(self, format: str, *args: Any) -> None:
                pass

        return Handler
