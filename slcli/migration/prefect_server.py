"""Owned local Prefect server process."""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from types import TracebackType
from typing import Dict, Optional, Set, TextIO, Type
from urllib.error import URLError
from urllib.request import urlopen

import psutil

_HOST = "127.0.0.1"
_LOOPBACK_ADDRESSES = (_HOST, "::1")
_STARTUP_TIMEOUT_SECONDS = 30.0
_POLL_INTERVAL_SECONDS = 0.1
_TERMINATE_TIMEOUT_SECONDS = 10
_KILL_TIMEOUT_SECONDS = 5


def _allocate_port() -> int:
    """Ask the OS for an available loopback port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind((_HOST, 0))
        return int(listener.getsockname()[1])


def loopback_listener_pids(port: int) -> Set[int]:
    """Return the IDs of processes listening on the loopback ``port``."""
    return {
        connection.pid
        for connection in psutil.net_connections(kind="tcp")
        if connection.pid is not None
        and connection.status == psutil.CONN_LISTEN
        and connection.laddr
        and connection.laddr.port == port
        and connection.laddr.ip in _LOOPBACK_ADDRESSES
    }


def _is_healthy(api_url: str) -> bool:
    try:
        with urlopen(f"{api_url}/health", timeout=1) as response:
            return bool(response.status == 200)
    except (OSError, URLError):
        return False


class ManagedPrefectServer:
    """Start and stop one Prefect server child process over a Prefect home.

    Entering the context returns the server's API URL once the listener on a
    dynamically allocated port is verified to belong to the spawned child. Only
    that child is ever terminated.
    """

    def __init__(self, home: Path) -> None:
        """Initialize a server controller whose database and logs live in ``home``."""
        self._home = home
        self._process: Optional["subprocess.Popen[str]"] = None
        self._log: Optional[TextIO] = None

    @property
    def database_path(self) -> Path:
        """Return the Prefect SQLite database path."""
        return self._home / "prefect.db"

    @property
    def process_id(self) -> Optional[int]:
        """Return the PID of the running child, if any."""
        return self._process.pid if self._process is not None else None

    def __enter__(self) -> str:
        """Start Prefect and return its API URL after PID-verified readiness."""
        port = _allocate_port()
        api_url = f"http://{_HOST}:{port}/api"
        self._home.mkdir(parents=True, exist_ok=True)
        self._log = (self._home / "server.log").open("a", encoding="utf-8")
        self._process = subprocess.Popen(
            [sys.executable, "-m", "prefect", "server", "start"]
            + ["--host", _HOST, "--port", str(port)],
            env=self._environment(api_url),
            stdout=self._log,
            stderr=subprocess.STDOUT,
            text=True,
        )
        try:
            self._wait_until_ready(self._process, port, api_url)
        except BaseException:
            self.stop()
            raise
        return api_url

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[TracebackType],
    ) -> None:
        """Terminate the child process created by this manager."""
        self.stop()

    def _environment(self, api_url: str) -> Dict[str, str]:
        return {
            **os.environ,
            "PREFECT_HOME": str(self._home),
            "PREFECT_API_URL": api_url,
            "PREFECT_API_DATABASE_CONNECTION_URL": (
                f"sqlite+aiosqlite:///{self.database_path.as_posix()}"
            ),
            "PREFECT_SERVER_ANALYTICS_ENABLED": "false",
            "PREFECT_UI_ENABLED": "false",
        }

    @staticmethod
    def _wait_until_ready(process: "subprocess.Popen[str]", port: int, api_url: str) -> None:
        deadline = time.monotonic() + _STARTUP_TIMEOUT_SECONDS
        while time.monotonic() < deadline:
            if process.poll() is not None:
                raise RuntimeError("Prefect server exited before becoming ready")
            # A healthy response alone could come from another process on the port.
            if loopback_listener_pids(port) == {process.pid} and _is_healthy(api_url):
                return
            time.sleep(_POLL_INTERVAL_SECONDS)
        raise RuntimeError("Prefect server did not become ready on its owned listener")

    def stop(self) -> None:
        """Terminate the owned child, escalating to kill, and close its log."""
        if self._process is not None and self._process.poll() is None:
            self._process.terminate()
            try:
                self._process.wait(timeout=_TERMINATE_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=_KILL_TIMEOUT_SECONDS)
        if self._log is not None:
            self._log.close()
        self._process = None
        self._log = None
