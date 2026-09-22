"""Tests for the opt-in managed-client CLI commands."""

import io
import subprocess
import sys
from pathlib import Path
from typing import Any

import click
import pytest
from click.testing import CliRunner

from slcli.managed_client.models import MinionEvent, MinionPhase, TransportError
from slcli.managed_client.state import StateStore
from slcli.managed_client_click import _PendingApprovalIndicator, register_managed_client_commands
from slcli.utils import ExitCodes


def test_importing_cli_does_not_load_managed_client_protocol() -> None:
    """Importing the base CLI keeps optional protocol modules unloaded."""
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import sys; import slcli.main; "
                "assert 'slcli.managed_client.protocol' not in sys.modules"
            ),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr


@pytest.fixture
def cli() -> Any:
    """Return a small command group with managed-client commands registered."""

    @click.group()
    def test_cli() -> None:
        pass

    register_managed_client_commands(test_cli)
    return test_cli


def test_managed_client_help_lists_commands(cli: Any) -> None:
    """The explicit group exposes only the supported foreground commands."""
    result = CliRunner().invoke(cli, ["managed-client", "--help"])

    assert result.exit_code == 0
    assert "run" in result.output
    assert "reset" in result.output

    result = CliRunner().invoke(cli, ["managed-client", "run", "--help"])

    assert result.exit_code == 0
    assert "--max-reconnect-attempts INTEGER" in result.output
    assert "[default: 5" in result.output


def test_managed_client_smoke_exercises_protocol_and_crypto(cli: Any) -> None:
    """The packaged smoke command loads the optional protocol dependencies."""
    result = CliRunner().invoke(cli, ["managed-client", "smoke"])

    assert result.exit_code == 0
    assert "smoke test passed" in result.output


class _InteractiveStringIO(io.StringIO):
    """String buffer that behaves like an interactive terminal."""

    def isatty(self) -> bool:
        """Report that the buffer represents a terminal."""
        return True


def test_pending_approval_indicator_updates_one_terminal_line() -> None:
    """Interactive pending approval output uses carriage returns, not log lines."""
    stream = _InteractiveStringIO()
    indicator = _PendingApprovalIndicator(stream)

    indicator.start("Waiting for SystemLink approval")
    indicator.tick()
    first_frame = stream.getvalue()
    indicator.tick()
    indicator.stop()

    assert "\n" not in stream.getvalue()
    assert first_frame.startswith("\r| Waiting for SystemLink approval")
    assert stream.getvalue().endswith("\r")


def test_pending_approval_indicator_preserves_control_characters_with_rich(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Rich output must not convert spinner control characters into log output."""
    from slcli import rich_output

    stream = _InteractiveStringIO()
    monkeypatch.setattr(sys, "stdout", stream)
    monkeypatch.setattr(click, "echo", rich_output._rich_echo)
    monkeypatch.setattr(click, "secho", rich_output._rich_secho)
    monkeypatch.setattr(click.utils, "echo", rich_output._rich_echo)
    monkeypatch.setattr(rich_output, "_STDOUT_CONSOLE", None)

    indicator = _PendingApprovalIndicator()
    indicator.start("Waiting for SystemLink approval")
    indicator.tick()
    indicator.stop()

    assert "\r" in stream.getvalue()
    assert "\n" not in stream.getvalue()


def test_pending_approval_indicator_logs_once_when_not_interactive() -> None:
    """Redirected output remains readable without terminal control characters."""
    stream = io.StringIO()
    indicator = _PendingApprovalIndicator(stream)

    indicator.start("Waiting for SystemLink approval")
    indicator.start("Waiting for SystemLink approval")
    indicator.tick()

    assert stream.getvalue() == "PENDING_APPROVAL: Waiting for SystemLink approval\n"


def test_pending_approval_indicator_reports_each_noninteractive_episode() -> None:
    """A later approval episode emits a fresh redirected-output status line."""
    stream = io.StringIO()
    indicator = _PendingApprovalIndicator(stream)

    indicator.start("Waiting for SystemLink approval")
    indicator.stop()
    indicator.start("Waiting for SystemLink approval")

    assert stream.getvalue() == (
        "PENDING_APPROVAL: Waiting for SystemLink approval\n"
        "PENDING_APPROVAL: Waiting for SystemLink approval\n"
    )


def test_run_keeps_only_pending_indicator_during_approval_retries(
    cli: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Approval retry phases do not become repeated console log lines."""

    class FakeMinion:
        def __init__(self, *args: Any, on_event: Any, **kwargs: Any) -> None:
            del args, kwargs
            self.phase = MinionPhase.INITIALIZING
            self.last_error = "test complete"
            self._on_event = on_event

        def start(self) -> None:
            for phase, message in (
                (MinionPhase.PENDING_APPROVAL, "Waiting for SystemLink approval"),
                (
                    MinionPhase.APPROVED_RECONNECTING,
                    "Retrying authentication after approval",
                ),
                (MinionPhase.AUTHENTICATING, "Authenticating with Salt master"),
            ):
                self._on_event(MinionEvent(phase=phase, message=message))
            self.phase = MinionPhase.FAILED

        def stop(self) -> None:
            pass

    monkeypatch.setattr("slcli.managed_client.TestMinion", FakeMinion)
    result = CliRunner().invoke(
        cli,
        [
            "managed-client",
            "run",
            "--master",
            "localhost",
            "--minion-id",
            "slcli-approval-output",
            "--state-dir",
            str(tmp_path),
        ],
    )

    assert result.exit_code == ExitCodes.GENERAL_ERROR
    assert "PENDING_APPROVAL: Waiting for SystemLink approval" in result.output
    assert "APPROVED_RECONNECTING" not in result.output
    assert "AUTHENTICATING" not in result.output


def test_reset_removes_only_identity_state(cli: Any, tmp_path: Path) -> None:
    """Reset removes identity files while preserving the state directory."""
    StateStore(tmp_path).load_or_create_identity("slcli-test")

    result = CliRunner().invoke(
        cli,
        ["managed-client", "reset", "--state-dir", str(tmp_path), "--yes"],
    )

    assert result.exit_code == 0
    assert "Reset managed-client identity state" in result.output
    assert tmp_path.is_dir()
    assert not list(tmp_path.iterdir())


def test_reset_requires_confirmation(cli: Any, tmp_path: Path) -> None:
    """Reset aborts without confirmation for destructive cleanup."""
    StateStore(tmp_path).load_or_create_identity("slcli-test")

    result = CliRunner().invoke(
        cli,
        ["managed-client", "reset", "--state-dir", str(tmp_path)],
        input="n\n",
    )

    assert result.exit_code != 0
    assert "Aborted" in result.output
    assert list(tmp_path.iterdir())


def test_run_reports_invalid_master_without_traceback(cli: Any, tmp_path: Path) -> None:
    """Malformed master endpoints use the standard invalid-input exit code."""
    result = CliRunner().invoke(
        cli,
        [
            "managed-client",
            "run",
            "--master",
            "://",
            "--minion-id",
            "slcli-invalid-master",
            "--state-dir",
            str(tmp_path),
        ],
    )

    assert result.exit_code == ExitCodes.INVALID_INPUT
    assert "✗" in result.output
    assert "Traceback" not in result.output


def test_run_reports_invalid_configuration_without_traceback(cli: Any, tmp_path: Path) -> None:
    """Invalid configuration values are handled as normal CLI errors."""
    result = CliRunner().invoke(
        cli,
        [
            "managed-client",
            "run",
            "--master",
            "localhost",
            "--minion-id",
            "",
            "--state-dir",
            str(tmp_path),
        ],
    )

    assert result.exit_code == ExitCodes.INVALID_INPUT
    assert "✗" in result.output
    assert "Traceback" not in result.output


def test_run_reports_transport_failure_as_network_error(
    cli: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Runtime transport failures use the standard network exit code."""

    def fail_to_start(*args: Any, **kwargs: Any) -> None:
        del args, kwargs
        raise TransportError("network unavailable")

    monkeypatch.setattr("slcli.managed_client.TestMinion", fail_to_start)
    result = CliRunner().invoke(
        cli,
        [
            "managed-client",
            "run",
            "--master",
            "localhost",
            "--minion-id",
            "slcli-network-error",
            "--state-dir",
            str(tmp_path),
        ],
    )

    assert result.exit_code == ExitCodes.NETWORK_ERROR
    assert "network unavailable" in result.output


def test_run_reports_background_transport_failure_as_network_error(
    cli: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Transport failures from the lifecycle thread use the network exit code."""

    class FailedMinion:
        phase = MinionPhase.FAILED
        last_error = "network unavailable"
        failure = TransportError("network unavailable")

        def __init__(self, *args: Any, **kwargs: Any) -> None:
            del args, kwargs

        def start(self) -> None:
            return None

        def stop(self) -> None:
            return None

    monkeypatch.setattr("slcli.managed_client.TestMinion", FailedMinion)
    result = CliRunner().invoke(
        cli,
        [
            "managed-client",
            "run",
            "--master",
            "localhost",
            "--minion-id",
            "slcli-background-network-error",
            "--state-dir",
            str(tmp_path),
        ],
    )

    assert result.exit_code == ExitCodes.NETWORK_ERROR
    assert "network unavailable" in result.output


def test_run_sanitizes_remote_job_details(
    cli: Any, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Remote job details cannot inject terminal controls or unbounded output."""

    class FailedMinion:
        phase = MinionPhase.FAILED
        last_error = "test complete"
        failure = None

        def __init__(self, *args: Any, on_event: Any, **kwargs: Any) -> None:
            del args, kwargs
            self._on_event = on_event

        def start(self) -> None:
            self._on_event(
                MinionEvent(
                    phase=MinionPhase.RUNNING_JOB,
                    message="Received Salt job",
                    details={
                        "jid": "job\n\x1b[31m" + "x" * 300,
                        "function": "ni_asset.add_asset",
                    },
                )
            )

        def stop(self) -> None:
            return None

    monkeypatch.setattr("slcli.managed_client.TestMinion", FailedMinion)
    result = CliRunner().invoke(
        cli,
        [
            "managed-client",
            "run",
            "--master",
            "localhost",
            "--minion-id",
            "slcli-output-safety",
            "--state-dir",
            str(tmp_path),
        ],
    )

    assert result.exit_code == ExitCodes.GENERAL_ERROR
    assert "\x1b" not in result.output
    assert "\\x0a" in result.output
    assert "x" * 257 not in result.output
