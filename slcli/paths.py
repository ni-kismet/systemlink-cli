"""Per-user application directories for slcli."""

import os
from pathlib import Path

from platformdirs import user_state_path

APP_NAME = "slcli"


def get_config_dir() -> Path:
    """Return the slcli configuration directory, creating it if needed.

    Configuration keeps its established XDG-style location on every platform so
    existing profiles remain discoverable.
    """
    if "XDG_CONFIG_HOME" in os.environ:
        config_dir = Path(os.environ["XDG_CONFIG_HOME"]) / APP_NAME
    else:
        config_dir = Path.home() / ".config" / APP_NAME
    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir


def get_state_dir() -> Path:
    """Return the OS-standard per-user state directory for slcli.

    Uses ``%LOCALAPPDATA%`` on Windows, ``~/Library/Application Support`` on macOS,
    and ``$XDG_STATE_HOME`` (default ``~/.local/state``) on Linux.
    """
    return user_state_path(APP_NAME, appauthor=False)
