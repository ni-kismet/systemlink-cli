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


def _exit_with_managed_client_error(error: ManagedClientError) -> NoReturn:
    """Print a managed-client error and exit with the appropriate CLI code."""
    from .managed_client.models import ConfigurationError, TransportError

    click.echo(f"✗ {error}", err=True)
    if isinstance(error, ConfigurationError):
        sys.exit(ExitCodes.INVALID_INPUT)
    if isinstance(error, TransportError):
        sys.exit(ExitCodes.NETWORK_ERROR)
    sys.exit(ExitCodes.GENERAL_ERROR)


def register_managed_client_commands(cli: Any) -> None:
    """Register the foreground managed-client test commands."""

    @cli.group(name="managed-client")
    def managed_client() -> None:
        """Run and reset an isolated SystemLink managed-client test minion."""

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
                details = ", ".join(f"{key}={value}" for key, value in event.details.items())
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
                    click.echo(
                        f"✗ {minion.last_error or 'The test minion failed.'}",
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
