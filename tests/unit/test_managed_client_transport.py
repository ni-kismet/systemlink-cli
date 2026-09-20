"""Unit tests for raw Salt transport."""

import socket
import threading

import pytest

from slcli.managed_client.models import ConfigurationError, TransportError
from slcli.managed_client.protocol import SaltMessage
from slcli.managed_client.transport import MasterEndpoint, SaltChannel


def test_master_endpoint_parses_host_and_port() -> None:
    """The transport accepts the endpoint forms used by test environments."""
    assert MasterEndpoint.parse("salt.example.com").request_port == 4506
    assert MasterEndpoint.parse("tcp://salt.example.com:4510").request_port == 4510
    assert MasterEndpoint.parse("[::1]:4511").host == "::1"


def test_master_endpoint_rejects_invalid_explicit_ports() -> None:
    """Explicit zero and non-numeric ports fail instead of using a fallback."""
    with pytest.raises(ConfigurationError, match="between 1 and 65535"):
        MasterEndpoint.parse("tcp://salt.example.com:0")
    with pytest.raises(ConfigurationError, match="invalid port"):
        MasterEndpoint.parse("tcp://salt.example.com:not-a-port")


def test_salt_channel_receives_partial_message() -> None:
    """The channel delegates partial TCP reads to the stream decoder."""
    client_socket, server_socket = socket.socketpair()
    channel = SaltChannel(client_socket)
    message = SaltMessage(
        body={"enc": "clear", "load": {"cmd": "_auth"}},
        head={"mid": 1},
    )

    def send_fragments() -> None:
        packed = message.pack()
        server_socket.sendall(packed[:2])
        server_socket.sendall(packed[2:])
        server_socket.close()

    sender = threading.Thread(target=send_fragments)
    sender.start()
    try:
        assert channel.receive() == message
    finally:
        channel.close()
        sender.join()


def test_salt_channel_retains_coalesced_messages() -> None:
    """A single TCP read can supply multiple messages without loss."""
    client_socket, server_socket = socket.socketpair()
    channel = SaltChannel(client_socket)
    messages = [
        SaltMessage(body={"enc": "clear", "load": {}}, head={"mid": 1}),
        SaltMessage(body={"enc": "clear", "load": {}}, head={"mid": 2}),
    ]
    server_socket.sendall(b"".join(message.pack() for message in messages))
    try:
        assert channel.receive() == messages[0]
        assert channel.receive() == messages[1]
    finally:
        channel.close()
        server_socket.close()


def test_salt_channel_rejects_closed_socket() -> None:
    """A closed channel produces a typed transport error."""
    client_socket, server_socket = socket.socketpair()
    server_socket.close()
    channel = SaltChannel(client_socket)

    with pytest.raises(TransportError, match="closed unexpectedly"):
        channel.receive()

    channel.close()


def test_salt_channel_raises_auth_socket_timeout() -> None:
    """An authentication channel timeout becomes a bounded transport error."""

    class TimeoutSocket:
        def recv(self, _: int) -> bytes:
            raise socket.timeout()

        def shutdown(self, _: socket.SocketKind) -> None:
            return None

        def close(self) -> None:
            return None

    channel = SaltChannel(TimeoutSocket())  # type: ignore[arg-type]

    with pytest.raises(TransportError, match="Timed out"):
        channel.receive()
    channel.close()


def test_salt_channel_ignores_idle_socket_timeout() -> None:
    """An idle publish channel remains available for a later job."""
    message = SaltMessage(body={"enc": "clear", "load": {}}, head={"mid": 1})

    class TimeoutThenMessageSocket:
        def __init__(self) -> None:
            self._attempts = 0

        def recv(self, _: int) -> bytes:
            self._attempts += 1
            if self._attempts == 1:
                raise socket.timeout()
            return message.pack()

        def shutdown(self, _: int) -> None:
            return None

        def close(self) -> None:
            return None

    channel = SaltChannel(TimeoutThenMessageSocket())  # type: ignore[arg-type]

    try:
        assert channel.receive(ignore_timeout=True) == message
    finally:
        channel.close()
