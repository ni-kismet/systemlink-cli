"""End-to-end tests for the locally managed Prefect server process."""

import subprocess
from pathlib import Path
from types import SimpleNamespace
from typing import Any, List, Optional

import psutil
import pytest

from slcli.migration.prefect_server import ManagedPrefectServer, loopback_listener_pids


# Tests that start a prefect server are slow (10-30s), so are included with e2e tests
# instead of unit tests.
@pytest.mark.e2e_migration
# Server management relies on a lot of OS interaction, so schedule on the CI's full os matrix.
@pytest.mark.full_os_client_matrix
def test_managed_server_lifecycle(tmp_path: Path) -> None:
    """A real child becomes ready on a dynamic port, persists its database, and stops."""
    server = ManagedPrefectServer(tmp_path)

    with server as api_url:
        process_id = server.process_id
        assert process_id is not None and psutil.pid_exists(process_id)
        assert api_url.startswith("http://127.0.0.1:")

    assert server.database_path.is_file()
    assert not psutil.pid_exists(process_id)


def _listener(pid: int, port: int = 1234, ip: str = "127.0.0.1", status: str = "") -> Any:
    return SimpleNamespace(
        pid=pid, status=status or psutil.CONN_LISTEN, laddr=SimpleNamespace(ip=ip, port=port)
    )


@pytest.mark.e2e_migration
@pytest.mark.full_os_client_matrix
def test_loopback_listener_pids_checks_only_the_requested_process(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Only loopback listeners owned by the requested process count."""
    connections = [
        _listener(pid=1),
        _listener(pid=2, ip="::1"),
        _listener(pid=3, port=4321),
        _listener(pid=4, ip="0.0.0.0"),
        _listener(pid=5, status=psutil.CONN_ESTABLISHED),
    ]
    process_ids: List[int] = []

    def process(process_id: int) -> Any:
        process_ids.append(process_id)
        return SimpleNamespace(net_connections=lambda kind: connections)

    monkeypatch.setattr(psutil, "Process", process)

    assert loopback_listener_pids(42, 1234) == {42}
    assert process_ids == [42]


class FakeProcess:
    """A child process that exits with ``exit_code`` or ignores termination."""

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


@pytest.mark.e2e_migration
@pytest.mark.full_os_client_matrix
def test_startup_fails_fast_when_child_exits() -> None:
    """An exited child fails readiness without waiting for the timeout."""
    with pytest.raises(RuntimeError, match="exited before becoming ready"):
        ManagedPrefectServer._wait_until_ready(
            FakeProcess(exit_code=1), 1234, "http://127.0.0.1:1234/api"  # type: ignore[arg-type]
        )


@pytest.mark.e2e_migration
@pytest.mark.full_os_client_matrix
def test_stop_escalates_to_kill_for_owned_child(tmp_path: Path) -> None:
    """A child that ignores termination is killed."""
    process = FakeProcess(ignores_terminate=True)
    server = ManagedPrefectServer(tmp_path)
    server._process = process  # type: ignore[assignment]

    server.stop()

    assert process.calls == ["terminate", "wait", "kill", "wait"]
    assert server.process_id is None
