"""Unit tests for the locally managed Prefect server process."""

import subprocess
from pathlib import Path
from typing import Any, List, Optional

import pytest

from slcli.migration import prefect_server
from slcli.migration.prefect_server import ManagedPrefectServer


class FakeProcess:
    """A child process that exits with `exit_code` or ignores termination."""

    def __init__(self, exit_code: Optional[int] = None, ignores_terminate: bool = False) -> None:
        """Configure process behavior."""
        self.pid = 42
        self.exit_code = exit_code
        self.ignores_terminate = ignores_terminate
        self.calls: List[str] = []

    def poll(self) -> Optional[int]:
        """Return the exit code, if exited."""
        return self.exit_code

    def terminate(self) -> None:
        """Request termination."""
        self.calls.append("terminate")

    def wait(self, timeout: float) -> int:
        """Wait for exit, timing out when termination is ignored."""
        self.calls.append("wait")
        if self.ignores_terminate and "kill" not in self.calls:
            raise subprocess.TimeoutExpired("prefect", timeout)
        return 0

    def kill(self) -> None:
        """Force exit."""
        self.calls.append("kill")


def test_stop_escalates_to_kill_for_owned_child(tmp_path: Path) -> None:
    """A child that ignores termination is killed."""
    process = FakeProcess(ignores_terminate=True)
    server = ManagedPrefectServer(tmp_path)
    server._process = process  # type: ignore[assignment]

    server.stop()

    assert process.calls == ["terminate", "wait", "kill", "wait"]
    assert server.process_id is None


def _patch_start(monkeypatch: pytest.MonkeyPatch, exit_codes: List[Optional[int]]) -> List[int]:
    ports = iter(range(5000, 5000 + len(exit_codes)))
    started: List[int] = []

    def fake_popen(args: List[str], **_: Any) -> FakeProcess:
        started.append(int(args[-1]))
        return FakeProcess(exit_code=exit_codes[len(started) - 1])

    monkeypatch.setattr(prefect_server, "_allocate_port", lambda: next(ports))
    monkeypatch.setattr(prefect_server, "loopback_listener_pids", lambda pid, port: {pid})
    monkeypatch.setattr(prefect_server, "_is_healthy", lambda url: True)
    monkeypatch.setattr(prefect_server.subprocess, "Popen", fake_popen)
    return started


def test_enter_retries_on_new_port_after_early_exit(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A child that exits before readiness is restarted on a freshly allocated port."""
    started = _patch_start(monkeypatch, [1, None])

    with ManagedPrefectServer(tmp_path) as api_url:
        assert api_url == "http://127.0.0.1:5001/api"

    assert started == [5000, 5001]


def test_enter_raises_after_max_attempts(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Repeated early exits stop after the attempt limit."""
    attempts = prefect_server._MAX_START_ATTEMPTS
    started = _patch_start(monkeypatch, [1] * attempts)

    with pytest.raises(RuntimeError, match="exited before becoming ready"):
        ManagedPrefectServer(tmp_path).__enter__()

    assert started == list(range(5000, 5000 + attempts))
