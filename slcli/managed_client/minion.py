"""Foreground test-minion lifecycle and reconnect state machine."""

from __future__ import annotations

import threading
import time
import uuid
from collections.abc import Callable, Mapping
from typing import Any

from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

from .crypto import (
    CryptoError,
    load_rsa_public_key,
    rsa_x931_decrypt,
    rsa_x931_sign,
    serialize_public_key,
)
from .handlers import FixtureHandlerRegistry
from .models import (
    LifecycleTimeoutError,
    MasterIdentityChangedError,
    MinionConfiguration,
    MinionEvent,
    MinionPhase,
    ProtocolError,
    StateError,
    TransportError,
    UnsupportedCryptoError,
)
from .protocol import (
    AuthRequest,
    AuthResponse,
    AuthState,
    build_job_return,
    build_publish_registration,
    decrypt_message_load,
    parse_auth_response,
)
from .state import MinionIdentity, StateStore
from .transport import MasterEndpoint, SaltChannel

TokenSigner = Callable[[bytes, RSAPrivateKey], bytes]
LoadSignatureVerifier = Callable[[bytes, bytes], bool]
SessionSignatureVerifier = Callable[[bytes, bytes, str], bool]
EventCallback = Callable[[MinionEvent], None]


class TestMinion:
    """Run one isolated, deterministic Salt test minion in the foreground."""

    def __init__(
        self,
        configuration: MinionConfiguration,
        *,
        handlers: FixtureHandlerRegistry | None = None,
        on_event: EventCallback | None = None,
        token_signer: TokenSigner = rsa_x931_sign,
        verify_load_signature: LoadSignatureVerifier | None = None,
        verify_session_signature: SessionSignatureVerifier | None = None,
        verify_auth_signatures: bool = True,
    ) -> None:
        """Initialize a minion without opening sockets or storing credentials."""
        self.configuration = configuration
        self._endpoint = MasterEndpoint.parse(
            configuration.master, request_port=configuration.request_port
        )
        self._state_store = StateStore(configuration.state_dir)
        self._handlers = handlers or FixtureHandlerRegistry()
        self._on_event = on_event
        self._token_signer = token_signer
        self._verify_load_signature = verify_load_signature
        self._session_signature_verifier: SessionSignatureVerifier = (
            verify_session_signature or self._verify_session_signature
        )
        self._verify_auth_signatures = verify_auth_signatures
        self._condition = threading.Condition()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._identity: MinionIdentity | None = None
        self._phase = MinionPhase.INITIALIZING
        self._events: list[MinionEvent] = []
        self._channels: set[SaltChannel] = set()
        self._last_error: str | None = None

    @property
    def minion_id(self) -> str:
        """Return the configured stable minion ID."""
        return self.configuration.minion_id

    @property
    def phase(self) -> MinionPhase:
        """Return the current lifecycle phase."""
        with self._condition:
            return self._phase

    @property
    def connected(self) -> bool:
        """Return whether the publish channel is currently active."""
        return self.phase is MinionPhase.CONNECTED or self.phase is MinionPhase.RUNNING_JOB

    @property
    def events(self) -> tuple[MinionEvent, ...]:
        """Return a snapshot of structured lifecycle events."""
        with self._condition:
            return tuple(self._events)

    @property
    def last_error(self) -> str | None:
        """Return the latest safe error description, if one occurred."""
        with self._condition:
            return self._last_error

    def start(self) -> None:
        """Create or load identity and start the lifecycle thread."""
        with self._condition:
            if self._thread is not None and self._thread.is_alive():
                raise StateError("The test minion is already running.")
        identity = self._state_store.load_or_create_identity(self.minion_id)
        with self._condition:
            self._identity = identity
            self._stop_event.clear()
            self._last_error = None
            self._set_phase_locked(MinionPhase.INITIALIZING, "Minion initialized")
            self._thread = threading.Thread(
                target=self._run,
                name=f"slcli-test-minion-{self.minion_id}",
                daemon=True,
            )
            self._thread.start()

    def stop(self, timeout: float | None = None) -> None:
        """Stop sockets and the lifecycle thread deterministically."""
        self._stop_event.set()
        self._close_channels()
        thread = self._thread
        if thread is not None and thread is not threading.current_thread():
            thread.join(timeout=timeout or self.configuration.request_timeout)
            if thread.is_alive():
                raise LifecycleTimeoutError("The test minion did not stop in time.")
        with self._condition:
            self._set_phase_locked(MinionPhase.STOPPING, "Minion stopped")

    def wait_for_state(self, state: MinionPhase | str, timeout: float = 30.0) -> None:
        """Wait until a phase is reached or raise a typed timeout."""
        if timeout <= 0:
            raise ValueError("The state timeout must be positive.")
        expected = self._normalize_phase(state)
        deadline = time.monotonic() + timeout
        with self._condition:
            while self._phase is not expected:
                if any(event.phase is expected for event in self._events):
                    return
                if self._phase is MinionPhase.FAILED:
                    raise StateError(self._last_error or "The test minion failed.")
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise LifecycleTimeoutError(
                        f"The test minion did not reach {expected.value}; current phase is "
                        f"{self._phase.value}."
                    )
                self._condition.wait(timeout=remaining)

    def __enter__(self) -> "TestMinion":
        """Return the configured minion for an explicit start call."""
        return self

    def __exit__(self, exception_type: Any, exception: Any, traceback: Any) -> None:
        """Always stop the lifecycle thread when leaving a context."""
        self.stop()

    def _run(self) -> None:
        request_channel: SaltChannel | None = None
        publish_channel: SaltChannel | None = None
        try:
            while not self._stop_event.is_set():
                try:
                    self._set_phase(MinionPhase.AUTHENTICATING, "Authenticating with Salt master")
                    request_channel = self._open_channel(self._endpoint.request_port)
                    auth_response = self._authenticate(request_channel)
                    if auth_response.state is AuthState.PENDING:
                        self._close_channel(request_channel)
                        request_channel = None
                        self._set_phase(
                            MinionPhase.PENDING_APPROVAL,
                            "Waiting for Salt key approval",
                        )
                        self._stop_event.wait(self.configuration.reconnect_interval)
                        if not self._stop_event.is_set():
                            self._set_phase(
                                MinionPhase.APPROVED_RECONNECTING,
                                "Retrying authentication after approval",
                            )
                        continue

                    if auth_response.shared_secret is None or auth_response.publish_port is None:
                        raise ProtocolError("Accepted authentication has incomplete session data.")
                    if auth_response.master_public_key is None:
                        raise ProtocolError("Accepted authentication has no master identity.")
                    self._state_store.record_master_identity(auth_response.master_public_key)
                    self._set_phase(
                        MinionPhase.CONNECTING_PUBLISH,
                        "Connecting to the Salt publish channel",
                    )
                    publish_channel = self._open_channel(auth_response.publish_port)
                    publish_channel.send(
                        build_publish_registration(
                            minion_id=self.minion_id,
                            shared_secret=auth_response.shared_secret,
                            private_key=self._require_identity().key_pair.private_key,
                            api_key=self.configuration.api_key,
                            signer=self._token_signer,
                        )
                    )
                    self._set_phase(MinionPhase.CONNECTED, "Publish channel connected")
                    self._run_connected(
                        request_channel,
                        publish_channel,
                        auth_response,
                    )
                    request_channel = None
                    publish_channel = None
                except UnsupportedCryptoError:
                    raise
                except MasterIdentityChangedError:
                    raise
                except (CryptoError, OSError, ProtocolError, TransportError) as error:
                    if self._stop_event.is_set():
                        break
                    self._record_reconnect(error)
                finally:
                    if request_channel is not None:
                        self._close_channel(request_channel)
                        request_channel = None
                    if publish_channel is not None:
                        self._close_channel(publish_channel)
                        publish_channel = None
        except UnsupportedCryptoError as error:
            self._fail(error)
        except MasterIdentityChangedError as error:
            self._fail(error)
        except Exception as error:
            self._fail(error)
        finally:
            self._close_channels()
            if self._stop_event.is_set():
                self._set_phase(MinionPhase.STOPPING, "Minion stopped")

    def _authenticate(self, request_channel: SaltChannel) -> AuthResponse:
        """Send one auth request and parse its pending or accepted response."""
        identity = self._require_identity()
        nonce = str(uuid.uuid4())
        request_channel.send(
            AuthRequest(
                minion_id=self.minion_id,
                public_key=serialize_public_key(identity.public_key).decode("utf-8"),
                nonce=nonce,
                api_key=self.configuration.api_key,
            ).to_message()
        )
        response = parse_auth_response(
            request_channel.receive(),
            minion_private_key=identity.key_pair.private_key,
            verify_master_signature=self._verify_auth_signatures,
            verify_load_signature=self._verify_load_signature,
            verify_session_signature=self._session_signature_verifier,
        )
        if response.nonce != nonce:
            raise ProtocolError("The Salt auth response nonce does not match the request.")
        return response

    @staticmethod
    def _verify_session_signature(digest: bytes, signature: bytes, public_key: str) -> bool:
        """Verify Salt's X9.31 signature over the encoded session key."""
        try:
            recovered = rsa_x931_decrypt(
                signature,
                load_rsa_public_key(public_key.encode("utf-8")),
            )
        except CryptoError:
            return False
        return recovered == digest

    def _run_connected(
        self,
        request_channel: SaltChannel,
        publish_channel: SaltChannel,
        auth_response: AuthResponse,
    ) -> None:
        """Receive, dispatch, and return deterministic jobs until disconnected."""
        if auth_response.shared_secret is None:
            raise ProtocolError("Connected authentication has no shared secret.")
        while not self._stop_event.is_set():
            self._set_phase(MinionPhase.RUNNING_JOB, "Waiting for a Salt job")
            job_message = publish_channel.receive()
            job = decrypt_message_load(job_message, auth_response.shared_secret)
            self._set_phase(
                MinionPhase.RUNNING_JOB,
                "Received Salt job",
                details=self._job_details(job),
            )
            result = self._handlers.dispatch(job, self.minion_id)
            request_channel.send(
                build_job_return(
                    job=job,
                    result=result,
                    minion_id=self.minion_id,
                    shared_secret=auth_response.shared_secret,
                    private_key=self._require_identity().key_pair.private_key,
                    api_key=self.configuration.api_key,
                    signer=self._token_signer,
                )
            )
            self._set_phase(
                MinionPhase.CONNECTED,
                "Sent Salt job return",
                details=self._job_details(job, result),
            )

    @staticmethod
    def _job_details(
        job: Mapping[str, Any], result: Mapping[str, Any] | None = None
    ) -> dict[str, str]:
        """Return safe display details for one received job and its return."""
        details: dict[str, str] = {}
        if job.get("jid") is not None:
            details["jid"] = str(job["jid"])

        functions = job.get("fun", job.get("function"))
        if isinstance(functions, list):
            details["functions"] = ", ".join(str(function) for function in functions)
        elif functions is not None:
            details["function"] = str(functions)

        target = job.get("tgt", job.get("target"))
        if isinstance(target, list):
            details["target"] = ", ".join(str(item) for item in target)
        elif target is not None:
            details["target"] = str(target)

        if result is not None:
            if result.get("retcode") is not None:
                details["retcode"] = str(result["retcode"])
            if result.get("success") is not None:
                details["success"] = str(result["success"])
        return details

    def _open_channel(self, port: int) -> SaltChannel:
        """Open and track one Salt channel."""
        channel = SaltChannel.connect(
            self._endpoint.host,
            port,
            timeout=self.configuration.request_timeout,
        )
        with self._condition:
            self._channels.add(channel)
        return channel

    def _close_channels(self) -> None:
        """Close all channels currently owned by the lifecycle thread."""
        with self._condition:
            channels = tuple(self._channels)
            self._channels.clear()
        for channel in channels:
            channel.close()

    def _close_channel(self, channel: SaltChannel) -> None:
        """Close one channel and remove it from lifecycle ownership."""
        channel.close()
        with self._condition:
            self._channels.discard(channel)

    def _record_reconnect(self, error: Exception) -> None:
        """Record a safe reconnect event and wait for the next attempt."""
        self._close_channels()
        with self._condition:
            self._last_error = type(error).__name__
        self._set_phase(
            MinionPhase.RECONNECTING,
            "Salt channel interrupted; retrying",
            details={"error_type": type(error).__name__},
        )
        self._stop_event.wait(self.configuration.reconnect_interval)

    def _fail(self, error: Exception) -> None:
        """Stop on a non-retryable lifecycle error without exposing secrets."""
        with self._condition:
            self._last_error = str(error) or type(error).__name__
        self._set_phase(
            MinionPhase.FAILED,
            "Managed-client lifecycle failed",
            details={"error_type": type(error).__name__},
        )

    def _set_phase(
        self,
        phase: MinionPhase,
        message: str,
        details: dict[str, str] | None = None,
    ) -> None:
        """Publish a phase transition and notify state waiters."""
        with self._condition:
            self._set_phase_locked(phase, message, details)

    def _set_phase_locked(
        self,
        phase: MinionPhase,
        message: str,
        details: dict[str, str] | None = None,
    ) -> None:
        """Set phase while the condition lock is held."""
        self._phase = phase
        event = MinionEvent(
            phase=phase,
            message=message,
            endpoint=self._endpoint.host,
            details=details or {},
        )
        self._events.append(event)
        self._condition.notify_all()
        if self._on_event is not None:
            try:
                self._on_event(event)
            except Exception:
                pass

    def _require_identity(self) -> MinionIdentity:
        """Return the initialized identity or fail closed."""
        if self._identity is None:
            raise StateError("The test minion identity is not initialized.")
        return self._identity

    @staticmethod
    def _normalize_phase(state: MinionPhase | str) -> MinionPhase:
        """Accept enum values and the short names used by test callers."""
        if isinstance(state, MinionPhase):
            return state
        aliases = {
            "initializing": MinionPhase.INITIALIZING,
            "authenticating": MinionPhase.AUTHENTICATING,
            "pending": MinionPhase.PENDING_APPROVAL,
            "pending_approval": MinionPhase.PENDING_APPROVAL,
            "approved_reconnecting": MinionPhase.APPROVED_RECONNECTING,
            "connecting_publish": MinionPhase.CONNECTING_PUBLISH,
            "connected": MinionPhase.CONNECTED,
            "running_job": MinionPhase.RUNNING_JOB,
            "reconnecting": MinionPhase.RECONNECTING,
            "stopping": MinionPhase.STOPPING,
            "failed": MinionPhase.FAILED,
        }
        try:
            return aliases[state.lower()]
        except KeyError as error:
            raise ValueError(f"Unknown minion phase: {state}") from error
