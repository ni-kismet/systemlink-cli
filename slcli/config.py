"""Configuration management for slcli."""

import json
import os
from pathlib import Path
from typing import Dict, Optional


def get_config_file_path() -> Path:
    """Get the path to the slcli configuration file."""
    # Use XDG_CONFIG_HOME if set, otherwise use ~/.config
    if "XDG_CONFIG_HOME" in os.environ:
        config_dir = Path(os.environ["XDG_CONFIG_HOME"]) / "slcli"
    else:
        config_dir = Path.home() / ".config" / "slcli"

    config_dir.mkdir(parents=True, exist_ok=True)
    return config_dir / "config.json"


def load_config() -> Dict[str, str]:
    """Load configuration from the config file.

    Returns:
        Dictionary containing configuration values
    """
    config_file = get_config_file_path()

    if not config_file.exists():
        return {}

    try:
        with open(config_file, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        # If config file is corrupted or unreadable, return empty config
        return {}


def save_config(config: Dict[str, str]) -> None:
    """Save configuration to the config file.

    Args:
        config: Dictionary containing configuration values to save
    """
    config_file = get_config_file_path()

    try:
        with open(config_file, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2)
    except OSError as e:
        raise RuntimeError(f"Failed to save configuration: {e}")


def get_function_service_url() -> Optional[str]:
    """Get the configured URL for the Function Service.

    Returns:
        The configured function service URL, or None if not configured
    """
    config = load_config()
    return config.get("function_service_url")


def set_function_service_url(url: str) -> None:
    """Set the URL for the Function Service.

    Args:
        url: The URL to use for function commands
    """
    config = load_config()
    config["function_service_url"] = url
    save_config(config)


def remove_function_service_url() -> None:
    """Remove the configured Function Service URL."""
    config = load_config()
    if "function_service_url" in config:
        del config["function_service_url"]
        save_config(config)
