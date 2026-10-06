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


def test_master_endpoint_rejects_malformed_ipv6_endpoint() -> None:
    """Malformed bracketed IPv6 endpoints use the typed configuration error."""
    with pytest.raises(ConfigurationError, match="invalid"):
        MasterEndpoint.parse("tcp://[::1")


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


@pytest.mark.parametrize("shutdown_wakes_receive", [True, False])
def test_salt_channel_close_interrupts_idle_receive(shutdown_wakes_receive: bool) -> None:
    """Close stops an idle TCP receive even when shutdown does not wake it."""
    listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    client_socket = socket.create_connection(listener.getsockname(), timeout=5)
    server_socket, _ = listener.accept()
    receiving = threading.Event()
    errors: list[TransportError] = []

    class ReceivingSocket:
        """Signal from inside the channel's locked read of a real TCP socket."""

        def gettimeout(self) -> float | None:
            return client_socket.gettimeout()

        def settimeout(self, timeout: float | None) -> None:
            client_socket.settimeout(timeout)

        def recv(self, size: int) -> bytes:
            receiving.set()
            return client_socket.recv(size)

        def shutdown(self, how: int) -> None:
            if shutdown_wakes_receive:
                client_socket.shutdown(how)

        def close(self) -> None:
            client_socket.close()

    channel = SaltChannel(ReceivingSocket())  # type: ignore[arg-type]

    def receive() -> None:
        try:
            channel.receive(ignore_timeout=True)
        except TransportError as error:
            errors.append(error)

    receiver = threading.Thread(target=receive, daemon=True)
    closer = threading.Thread(target=channel.close, daemon=True)
    receiver.start()
    try:
        assert receiving.wait(timeout=1)
        closer.start()
        closer.join(timeout=1)
        assert not closer.is_alive()
        receiver.join(timeout=1)
        assert not receiver.is_alive()
        assert len(errors) == 1
    finally:
        channel.close()
        server_socket.close()
        listener.close()
        receiver.join(timeout=6)
        if closer.ident is not None:
            closer.join(timeout=6)


@pytest.mark.parametrize("timeout", [None, 5.0, 0.05])
@pytest.mark.parametrize("peer_closed", [False, True])
def test_salt_channel_restores_timeout_after_idle_receive(
    timeout: float | None, peer_closed: bool
) -> None:
    """Idle reads preserve the socket timeout after success or a transport error."""
    client_socket, server_socket = socket.socketpair()
    client_socket.settimeout(timeout)
    channel = SaltChannel(client_socket)
    message = SaltMessage(body={"enc": "clear", "load": {}}, head={"mid": 1})
    if peer_closed:
        server_socket.close()
    else:
        server_socket.sendall(message.pack())
    try:
        if peer_closed:
            with pytest.raises(TransportError, match="closed unexpectedly"):
                channel.receive(ignore_timeout=True)
        else:
            assert channel.receive(ignore_timeout=True) == message
        assert client_socket.gettimeout() == timeout
    finally:
        channel.close()
        server_socket.close()


def test_salt_channel_close_waits_for_active_receive() -> None:
    """The descriptor remains open until an interrupted receive has returned."""
    receiving = threading.Event()
    shutdown_started = threading.Event()
    release_receive = threading.Event()
    descriptor_closed = threading.Event()

    class InterruptedSocket:
        def gettimeout(self) -> float | None:
            return 5.0

        def settimeout(self, timeout: float | None) -> None:
            return None

        def recv(self, _: int) -> bytes:
            receiving.set()
            assert release_receive.wait(timeout=2)
            raise OSError("Socket shut down")

        def shutdown(self, _: int) -> None:
            shutdown_started.set()

        def close(self) -> None:
            descriptor_closed.set()

    channel = SaltChannel(InterruptedSocket())  # type: ignore[arg-type]
    errors: list[TransportError] = []

    def receive() -> None:
        try:
            channel.receive(ignore_timeout=True)
        except TransportError as error:
            errors.append(error)

    receiver = threading.Thread(target=receive, daemon=True)
    closer = threading.Thread(target=channel.close, daemon=True)
    receiver.start()
    try:
        assert receiving.wait(timeout=1)
        closer.start()
        assert shutdown_started.wait(timeout=1)
        assert not descriptor_closed.wait(timeout=0.05)
    finally:
        release_receive.set()
        receiver.join(timeout=1)
        if closer.ident is not None:
            closer.join(timeout=1)
        channel.close()

    assert not receiver.is_alive()
    assert not closer.is_alive()
    assert descriptor_closed.is_set()
    assert len(errors) == 1


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


def test_salt_channel_stops_retrying_timeouts_after_close() -> None:
    """Closing during an idle receive timeout prevents another socket read."""

    class ClosingTimeoutSocket:
        def __init__(self) -> None:
            self._attempts = 0

        def gettimeout(self) -> float | None:
            return 5.0

        def settimeout(self, timeout: float | None) -> None:
            return None

        def recv(self, _: int) -> bytes:
            self._attempts += 1
            if self._attempts > 1:
                pytest.fail("A closed channel must not retry an idle receive timeout.")
            channel.close()
            raise socket.timeout()

        def shutdown(self, _: int) -> None:
            return None

        def close(self) -> None:
            return None

    channel = SaltChannel(ClosingTimeoutSocket())  # type: ignore[arg-type]

    with pytest.raises(TransportError, match="closed"):
        channel.receive(ignore_timeout=True)


def test_salt_channel_ignores_idle_socket_timeout() -> None:
    """An idle publish channel remains available for a later job."""
    message = SaltMessage(body={"enc": "clear", "load": {}}, head={"mid": 1})

    class TimeoutThenMessageSocket:
        def __init__(self) -> None:
            self._attempts = 0

        def gettimeout(self) -> float | None:
            return 5.0

        def settimeout(self, timeout: float | None) -> None:
            return None

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
