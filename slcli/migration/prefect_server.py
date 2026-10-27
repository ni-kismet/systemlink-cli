"""Owned local Prefect server process."""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path
from types import TracebackType
from typing import Dict, List, Optional, Set, TextIO, Type
from urllib.error import URLError
from urllib.request import urlopen

import psutil

_HOST = "127.0.0.1"
_LOOPBACK_ADDRESSES = (_HOST, "::1")
_STARTUP_TIMEOUT_SECONDS = 30.0
_POLL_INTERVAL_SECONDS = 0.1
_TERMINATE_TIMEOUT_SECONDS = 10
_KILL_TIMEOUT_SECONDS = 5
_MAX_START_ATTEMPTS = 5


class _ExitedBeforeReadyError(RuntimeError):
    """The Prefect child exited before it became ready."""


class _PortConflictError(RuntimeError):
    """Another process holds the port allocated for the Prefect child."""


def _accepts_connections(port: int) -> bool:
    """Return whether something accepts TCP connections on the loopback ``port``."""
    try:
        with socket.create_connection((_HOST, port), timeout=1):
            return True
    except OSError:
        return False


def _allocate_port() -> int:
    """Ask the OS for an available loopback port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as listener:
        listener.bind((_HOST, 0))
        return int(listener.getsockname()[1])


def _process_tree(process_id: int) -> List[psutil.Process]:
    """Return the process and its live descendants, or an empty list if it has exited."""
    try:
        root = psutil.Process(process_id)
        return [root] + root.children(recursive=True)
    except psutil.NoSuchProcess:
        return []


def _listens_on(process: psutil.Process, port: int) -> bool:
    try:
        connections = process.net_connections(kind="tcp")
    except (psutil.NoSuchProcess, psutil.AccessDenied):
        return False
    return any(
        connection.status == psutil.CONN_LISTEN
        and connection.laddr
        and connection.laddr.port == port
        and connection.laddr.ip in _LOOPBACK_ADDRESSES
        for connection in connections
    )


def loopback_listener_pids(process_id: int, port: int) -> Set[int]:
    """Return PIDs in the process tree rooted at ``process_id`` listening on loopback ``port``.

    Descendants are included because launchers such as the Windows venv
    ``python.exe`` start the real interpreter as a child that owns the socket.
    """
    return {process.pid for process in _process_tree(process_id) if _listens_on(process, port)}


def _stop_processes(processes: List[psutil.Process]) -> None:
    """Terminate processes that outlived their parent, escalating to kill."""
    for process in processes:
        try:
            process.terminate()
        except psutil.NoSuchProcess:
            pass
    _, alive = psutil.wait_procs(processes, timeout=_TERMINATE_TIMEOUT_SECONDS)
    for process in alive:
        try:
            process.kill()
        except psutil.NoSuchProcess:
            pass
    psutil.wait_procs(alive, timeout=_KILL_TIMEOUT_SECONDS)


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
        self._home.mkdir(parents=True, exist_ok=True)
        # The allocated port can be taken before Prefect binds it; a fresh port avoids that.
        for _ in range(_MAX_START_ATTEMPTS - 1):
            try:
                return self._start(_allocate_port())
            except (_ExitedBeforeReadyError, _PortConflictError):
                pass
        return self._start(_allocate_port())

    def _start(self, port: int) -> str:
        api_url = f"http://{_HOST}:{port}/api"
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
                raise _ExitedBeforeReadyError("Prefect server exited before becoming ready")
            # A healthy response alone could come from another process on the port.
            if loopback_listener_pids(process.pid, port) and _is_healthy(api_url):
                return
            time.sleep(_POLL_INTERVAL_SECONDS)
        if not loopback_listener_pids(process.pid, port) and _accepts_connections(port):
            raise _PortConflictError(
                f"Port {port} is in use by another process; Prefect server could not claim it"
            )
        raise RuntimeError("Prefect server did not become ready on its owned listener")

    def stop(self) -> None:
        """Terminate the owned child and its descendants, escalating to kill, and close its log."""
        if self._process is not None and self._process.poll() is None:
            descendants = _process_tree(self._process.pid)[1:]
            self._process.terminate()
            try:
                self._process.wait(timeout=_TERMINATE_TIMEOUT_SECONDS)
            except subprocess.TimeoutExpired:
                self._process.kill()
                self._process.wait(timeout=_KILL_TIMEOUT_SECONDS)
            _stop_processes(descendants)
        if self._log is not None:
            self._log.close()
        self._process = None
        self._log = None
