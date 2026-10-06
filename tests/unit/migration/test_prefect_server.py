"""Unit tests for the locally managed Prefect server process."""

import subprocess
from pathlib import Path
from typing import List, Optional

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
