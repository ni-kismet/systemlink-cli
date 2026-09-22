"""CLI commands for the opt-in managed-client test minion."""

from __future__ import annotations

import sys
import threading
import time
from pathlib import Path
from typing import TYPE_CHECKING, Any, NoReturn, TextIO

import click

from .utils import ExitCodes

if TYPE_CHECKING:
    from .managed_client.minion import TestMinion as TestMinionType
    from .managed_client.models import ManagedClientError


_MAX_EVENT_DETAIL_LENGTH = 256


class _PendingApprovalIndicator:
    """Render pending approval without adding repeated terminal log lines."""

    _FRAMES = ("|", "/", "-", "\\")

    def __init__(self, stream: TextIO | None = None) -> None:
        """Initialize an indicator for the selected output stream."""
        self._stream = stream if stream is not None else sys.stdout
        self._interactive = self._stream.isatty()
        self._lock = threading.Lock()
        self._active = False
        self._reported_noninteractive = False
        self._frame = 0
        self._last_line = ""
        self._message = ""

    @property
    def active(self) -> bool:
        """Return whether the minion is waiting for key approval."""
        with self._lock:
            return self._active

    def start(self, message: str) -> None:
        """Start or update the pending approval indicator."""
        with self._lock:
            self._active = True
            self._message = message
            if not self._interactive and not self._reported_noninteractive:
                click.echo(f"PENDING_APPROVAL: {message}", file=self._stream)
                self._reported_noninteractive = True

    def tick(self) -> None:
        """Advance the interactive indicator by one frame."""
        with self._lock:
            if not self._active or not self._interactive:
                return
            line = f"{self._FRAMES[self._frame]} {self._message}"
            padding = max(0, len(self._last_line) - len(line))
            self._stream.write(f"\r{line}{' ' * padding}")
            self._stream.flush()
            self._last_line = line
            self._frame = (self._frame + 1) % len(self._FRAMES)

    def stop(self) -> None:
        """Clear the interactive indicator before normal output resumes."""
        with self._lock:
            if self._interactive and self._last_line:
                self._stream.write(f"\r{' ' * len(self._last_line)}\r")
                self._stream.flush()
            self._active = False
            self._last_line = ""
            self._reported_noninteractive = False


def _exit_with_managed_client_error(error: ManagedClientError) -> NoReturn:
    """Print a managed-client error and exit with the appropriate CLI code."""
    from .managed_client.models import (
        ConfigurationError,
        ReconnectLimitExceededError,
        TransportError,
    )

    click.echo(f"✗ {error}", err=True)
    if isinstance(error, ConfigurationError):
        sys.exit(ExitCodes.INVALID_INPUT)
    if isinstance(error, (TransportError, ReconnectLimitExceededError)):
        sys.exit(ExitCodes.NETWORK_ERROR)
    sys.exit(ExitCodes.GENERAL_ERROR)


def _safe_event_detail(value: object) -> str:
    """Escape terminal controls and cap remote lifecycle detail values."""
    escaped = "".join(
        (
            f"\\x{ord(character):02x}"
            if (
                ord(character) < 0x20
                or 0x7F <= ord(character) <= 0x9F
                or 0xD800 <= ord(character) <= 0xDFFF
            )
            else character
        )
        for character in str(value)
    )
    if len(escaped) > _MAX_EVENT_DETAIL_LENGTH:
        return escaped[: _MAX_EVENT_DETAIL_LENGTH - 3] + "..."
    return escaped


def register_managed_client_commands(cli: Any) -> None:
    """Register the foreground managed-client test commands."""

    @cli.group(name="managed-client")
    def managed_client() -> None:
        """Run and reset an isolated SystemLink managed-client test minion."""

    @managed_client.command(name="smoke", hidden=True)
    def smoke() -> None:
        """Exercise packaged MessagePack and RSA X9.31 support without a network."""
        from .managed_client.crypto import generate_rsa_key_pair, rsa_x931_decrypt, rsa_x931_sign
        from .managed_client.protocol import pack_frame, unpack_frame

        payload = {"smoke": "managed-client"}
        if unpack_frame(pack_frame(payload)) != payload:
            raise click.ClickException("Managed-client MessagePack smoke test failed.")
        key_pair = generate_rsa_key_pair()
        message = b"slcli-managed-client-smoke"
        signature = rsa_x931_sign(message, key_pair.private_key)
        if rsa_x931_decrypt(signature, key_pair.public_key) != message:
            raise click.ClickException("Managed-client RSA X9.31 smoke test failed.")
        click.echo("Managed-client smoke test passed.")

    @managed_client.command(name="run")
    @click.option("--master", required=True, help="Salt master hostname or endpoint.")
    @click.option("--minion-id", required=True, help="Stable test-minion identity.")
    @click.option(
        "--state-dir",
        required=True,
        type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
        help="Directory for this minion's isolated identity state.",
    )
    @click.option(
        "--request-port",
        default=4506,
        show_default=True,
        type=click.IntRange(1, 65535),
        help="Salt request-channel TCP port.",
    )
    @click.option(
        "--request-timeout",
        default=10.0,
        show_default=True,
        type=click.FloatRange(min=0.001),
        help="Socket operation timeout in seconds.",
    )
    @click.option(
        "--reconnect-interval",
        default=1.0,
        show_default=True,
        type=click.FloatRange(min=0.001),
        help="Delay between authentication and reconnect attempts.",
    )
    @click.option(
        "--max-reconnect-attempts",
        default=5,
        show_default=True,
        type=click.IntRange(min=1),
        help="Maximum reconnect attempts before the minion fails.",
    )
    def run(
        master: str,
        minion_id: str,
        state_dir: Path,
        request_port: int,
        request_timeout: float,
        reconnect_interval: float,
        max_reconnect_attempts: int,
    ) -> None:
        """Run the test minion until interrupted or a lifecycle failure occurs."""
        from .managed_client import MinionConfiguration, TestMinion
        from .managed_client.models import ManagedClientError, MinionEvent, MinionPhase

        pending_indicator = _PendingApprovalIndicator()

        def report_event(event: MinionEvent) -> None:
            if event.phase is MinionPhase.PENDING_APPROVAL:
                pending_indicator.start(event.message)
                return
            if pending_indicator.active and event.phase in {
                MinionPhase.APPROVED_RECONNECTING,
                MinionPhase.AUTHENTICATING,
            }:
                return
            pending_indicator.stop()
            message = f"{event.phase.value}: {event.message}"
            if event.details:
                details = ", ".join(
                    f"{key}={_safe_event_detail(value)}" for key, value in event.details.items()
                )
                message = f"{message} ({details})"
            click.echo(message)

        minion: TestMinionType | None = None
        try:
            minion = TestMinion(
                MinionConfiguration(
                    master=master,
                    minion_id=minion_id,
                    state_dir=state_dir,
                    request_port=request_port,
                    request_timeout=request_timeout,
                    reconnect_interval=reconnect_interval,
                    max_reconnect_attempts=max_reconnect_attempts,
                ),
                on_event=report_event,
            )
            minion.start()
            click.echo(f"Running managed-client test minion {minion_id}.")
            while True:
                if minion.phase is MinionPhase.FAILED:
                    pending_indicator.stop()
                    failure = getattr(minion, "failure", None)
                    if isinstance(failure, ManagedClientError):
                        _exit_with_managed_client_error(failure)
                    click.echo(
                        f"✗ {_safe_event_detail(minion.last_error or 'The test minion failed.')}",
                        err=True,
                    )
                    sys.exit(ExitCodes.GENERAL_ERROR)
                pending_indicator.tick()
                time.sleep(0.1)
        except KeyboardInterrupt:
            pending_indicator.stop()
            click.echo("Stopping managed-client test minion.")
        except ManagedClientError as error:
            pending_indicator.stop()
            _exit_with_managed_client_error(error)
        finally:
            pending_indicator.stop()
            if minion is not None:
                minion.stop()

    @managed_client.command(name="reset")
    @click.option(
        "--state-dir",
        required=True,
        type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
        help="Directory containing this minion's isolated identity state.",
    )
    @click.option("--yes", is_flag=True, help="Skip the destructive-operation confirmation.")
    def reset(state_dir: Path, yes: bool) -> None:
        """Remove only the identity files in an isolated state directory."""
        if not yes:
            click.confirm(f"Delete managed-client identity state in {state_dir}?", abort=True)

        from .managed_client import StateStore
        from .managed_client.models import ManagedClientError

        try:
            StateStore(state_dir).reset()
        except ManagedClientError as error:
            _exit_with_managed_client_error(error)
        click.echo(f"Reset managed-client identity state in {state_dir}.")
