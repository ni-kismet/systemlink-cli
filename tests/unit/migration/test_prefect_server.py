"""Unit tests for the locally managed Prefect server process."""

import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Iterator, List, Optional, Tuple

import psutil
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


def test_stop_escalates_to_kill_for_owned_child(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A child that ignores termination is killed."""
    monkeypatch.setattr(prefect_server, "_process_tree", lambda pid: [])
    process = FakeProcess(ignores_terminate=True)
    server = ManagedPrefectServer(tmp_path)
    server._process = process  # type: ignore[assignment]

    server.stop()

    assert process.calls == ["terminate", "wait", "kill", "wait"]
    assert server.process_id is None


_LAUNCHER_SCRIPT = """
import subprocess, sys
child = subprocess.Popen([sys.executable, "-c", sys.argv[1]])
print(child.pid, flush=True)
child.wait()
"""

_LISTENER_SCRIPT = """
import socket, time
listener = socket.socket()
listener.bind(("127.0.0.1", int({port})))
listener.listen()
time.sleep(60)
"""


@pytest.fixture
def launcher_with_listening_child() -> Iterator[Tuple["subprocess.Popen[str]", int, int]]:
    """Start a launcher whose child, not the launcher itself, owns a loopback listener."""
    port = prefect_server._allocate_port()
    launcher = subprocess.Popen(
        [sys.executable, "-c", _LAUNCHER_SCRIPT, _LISTENER_SCRIPT.format(port=port)],
        stdout=subprocess.PIPE,
        text=True,
    )
    assert launcher.stdout is not None
    child_pid = int(launcher.stdout.readline())
    try:
        yield launcher, child_pid, port
    finally:
        for process in prefect_server._process_tree(launcher.pid):
            process.kill()
        launcher.wait(timeout=10)
        launcher.stdout.close()


def test_listener_owned_by_descendant_is_found(
    launcher_with_listening_child: Tuple["subprocess.Popen[str]", int, int],
) -> None:
    """A listener owned by a child of the spawned launcher counts as owned."""
    launcher, child_pid, port = launcher_with_listening_child
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if prefect_server.loopback_listener_pids(launcher.pid, port):
            break
        time.sleep(0.05)

    assert prefect_server.loopback_listener_pids(launcher.pid, port) == {child_pid}


def test_listener_check_returns_empty_for_exited_process() -> None:
    """A process that already exited owns no listeners."""
    process = subprocess.Popen([sys.executable, "-c", "pass"])
    process.wait(timeout=10)

    assert prefect_server.loopback_listener_pids(process.pid, 1) == set()


def test_stop_terminates_descendants_left_by_launcher(
    tmp_path: Path,
    launcher_with_listening_child: Tuple["subprocess.Popen[str]", int, int],
) -> None:
    """Stopping the launcher also stops the real server process it started."""
    launcher, child_pid, _ = launcher_with_listening_child
    server = ManagedPrefectServer(tmp_path)
    server._process = launcher

    server.stop()

    assert not psutil.pid_exists(child_pid) or (
        psutil.Process(child_pid).status() == psutil.STATUS_ZOMBIE
    )


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


def _patch_conflict(monkeypatch: pytest.MonkeyPatch, accepts: bool) -> None:
    clock = iter(range(0, 1000, 100))
    monkeypatch.setattr(prefect_server.time, "monotonic", lambda: float(next(clock)))
    monkeypatch.setattr(prefect_server.time, "sleep", lambda _: None)
    monkeypatch.setattr(prefect_server, "loopback_listener_pids", lambda pid, port: set())
    monkeypatch.setattr(prefect_server, "_is_healthy", lambda url: False)
    monkeypatch.setattr(prefect_server, "_accepts_connections", lambda port: accepts)


def test_wait_reports_port_conflict(monkeypatch: pytest.MonkeyPatch) -> None:
    """A port answered by another process is reported as a conflict."""
    _patch_conflict(monkeypatch, accepts=True)

    with pytest.raises(prefect_server._PortConflictError, match="Port 5000 is in use"):
        ManagedPrefectServer._wait_until_ready(
            FakeProcess(), 5000, "http://127.0.0.1:5000/api"  # type: ignore[arg-type]
        )


def test_wait_reports_generic_timeout_without_conflict(monkeypatch: pytest.MonkeyPatch) -> None:
    """A silent port times out with the generic readiness error."""
    _patch_conflict(monkeypatch, accepts=False)

    with pytest.raises(RuntimeError, match="did not become ready"):
        ManagedPrefectServer._wait_until_ready(
            FakeProcess(), 5000, "http://127.0.0.1:5000/api"  # type: ignore[arg-type]
        )
