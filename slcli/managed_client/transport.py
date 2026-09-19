"""Raw TCP transport for the observed Salt MessagePack protocol."""

from __future__ import annotations

import socket
from collections import deque
from dataclasses import dataclass
from urllib.parse import urlsplit

from .models import TransportError
from .protocol import MAX_FRAME_SIZE, MessagePackStream, SaltMessage

DEFAULT_REQUEST_PORT = 4506
DEFAULT_PUBLISH_PORT = 4505


@dataclass(frozen=True)
class MasterEndpoint:
    """A parsed Salt master hostname and request-channel port."""

    host: str
    request_port: int = DEFAULT_REQUEST_PORT

    @classmethod
    def parse(cls, value: str, request_port: int = DEFAULT_REQUEST_PORT) -> "MasterEndpoint":
        """Parse a hostname, host:port, or tcp://host:port endpoint."""
        if not value.strip():
            raise TransportError("The Salt master endpoint is required.")
        candidate = value if "://" in value else f"//{value}"
        parsed = urlsplit(candidate)
        if not parsed.hostname:
            raise TransportError("The Salt master endpoint has no hostname.")
        selected_port = parsed.port or request_port
        if not 1 <= selected_port <= 65535:
            raise TransportError("The Salt master port must be between 1 and 65535.")
        return cls(host=parsed.hostname, request_port=selected_port)


class SaltChannel:
    """A connected raw TCP Salt channel carrying MessagePack maps."""

    def __init__(self, connection: socket.socket, max_frame_size: int = MAX_FRAME_SIZE) -> None:
        """Wrap an already connected socket."""
        self._connection = connection
        self._decoder = MessagePackStream(max_frame_size=max_frame_size)
        self._pending: deque[SaltMessage] = deque()
        self._closed = False

    @classmethod
    def connect(
        cls,
        host: str,
        port: int,
        timeout: float,
        max_frame_size: int = MAX_FRAME_SIZE,
    ) -> "SaltChannel":
        """Open a TCP channel with a bounded connection timeout."""
        try:
            connection = socket.create_connection((host, port), timeout=timeout)
            connection.settimeout(timeout)
        except OSError as error:
            raise TransportError(f"Unable to connect to Salt channel {host}:{port}.") from error
        return cls(connection, max_frame_size=max_frame_size)

    def send(self, message: SaltMessage) -> None:
        """Write one unprefixed MessagePack Salt message."""
        if self._closed:
            raise TransportError("The Salt channel is closed.")
        try:
            self._connection.sendall(message.pack())
        except OSError as error:
            raise TransportError("Unable to send a Salt message.") from error

    def receive(self) -> SaltMessage:
        """Read until one complete Salt MessagePack message is available."""
        if self._closed:
            raise TransportError("The Salt channel is closed.")
        if self._pending:
            return self._pending.popleft()
        while True:
            try:
                data = self._connection.recv(65536)
            except socket.timeout:
                continue
            except OSError as error:
                raise TransportError("Unable to receive a Salt message.") from error
            if not data:
                raise TransportError("The Salt channel closed unexpectedly.")
            self._pending.extend(
                SaltMessage.from_mapping(frame) for frame in self._decoder.feed(data)
            )
            if self._pending:
                return self._pending.popleft()

    def close(self) -> None:
        """Close the socket and release its file descriptor."""
        if self._closed:
            return
        self._closed = True
        try:
            self._connection.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        try:
            self._connection.close()
        except OSError:
            pass
