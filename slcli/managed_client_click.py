"""CLI commands for the opt-in managed-client test minion."""

from __future__ import annotations

import time
from pathlib import Path
from typing import Any

import click


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
    def run(
        master: str,
        minion_id: str,
        state_dir: Path,
        request_port: int,
        request_timeout: float,
        reconnect_interval: float,
    ) -> None:
        """Run the test minion until interrupted or a lifecycle failure occurs."""
        from .managed_client import MinionConfiguration, TestMinion
        from .managed_client.models import ManagedClientError, MinionEvent, MinionPhase

        def report_event(event: MinionEvent) -> None:
            message = f"{event.phase.value}: {event.message}"
            if event.details:
                details = ", ".join(f"{key}={value}" for key, value in event.details.items())
                message = f"{message} ({details})"
            click.echo(message)

        minion = TestMinion(
            MinionConfiguration(
                master=master,
                minion_id=minion_id,
                state_dir=state_dir,
                request_port=request_port,
                request_timeout=request_timeout,
                reconnect_interval=reconnect_interval,
            ),
            on_event=report_event,
        )
        try:
            minion.start()
            click.echo(f"Running managed-client test minion {minion_id}.")
            while True:
                if minion.phase is MinionPhase.FAILED:
                    raise click.ClickException(minion.last_error or "The test minion failed.")
                time.sleep(0.25)
        except KeyboardInterrupt:
            click.echo("Stopping managed-client test minion.")
        except ManagedClientError as error:
            raise click.ClickException(str(error)) from error
        finally:
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
            raise click.ClickException(str(error)) from error
        click.echo(f"Reset managed-client identity state in {state_dir}.")
