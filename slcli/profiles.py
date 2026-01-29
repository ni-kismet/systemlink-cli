"""Profile management for slcli multi-environment configuration.

This module provides AWS CLI-style profile management, allowing users to
configure multiple SystemLink environments (dev, test, prod) and switch
between them easily.

Configuration is stored in ~/.config/slcli/config.json with the following structure:
{
  "current-profile": "dev",
  "profiles": {
    "dev": {
      "server": "https://dev-api.example.com",
      "web-url": "https://dev.example.com",
      "api-key": "xxx",
      "platform": "SLE",
      "workspace": "Development"
    }
  }
}
"""

import json
import os
import stat
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import click


@dataclass
class Profile:
    """A SystemLink connection profile."""

    name: str
    server: str
    api_key: str
    web_url: Optional[str] = None
    platform: Optional[str] = None
    workspace: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert profile to dictionary for serialization."""
        result: Dict[str, Any] = {
            "server": self.server,
            "api-key": self.api_key,
        }
        if self.web_url:
            result["web-url"] = self.web_url
        if self.platform:
            result["platform"] = self.platform
        if self.workspace:
            result["workspace"] = self.workspace
        return result

    @classmethod
    def from_dict(cls, name: str, data: Dict[str, Any]) -> "Profile":
        """Create a Profile from a dictionary."""
        return cls(
            name=name,
            server=data.get("server", ""),
            api_key=data.get("api-key", ""),
            web_url=data.get("web-url"),
            platform=data.get("platform"),
            workspace=data.get("workspace"),
        )


@dataclass
class ProfileConfig:
    """Configuration file manager for profiles."""

    current_profile: Optional[str] = None
    profiles: Dict[str, Profile] = field(default_factory=dict)

    # Additional non-profile settings (e.g., function_service_url)
    settings: Dict[str, Any] = field(default_factory=dict)

    @classmethod
    def get_config_path(cls) -> Path:
        """Get the path to the configuration file."""
        # Support override via environment variable
        if "SLCLI_CONFIG" in os.environ:
            return Path(os.environ["SLCLI_CONFIG"])

        # Use XDG_CONFIG_HOME if set, otherwise use ~/.config
        if "XDG_CONFIG_HOME" in os.environ:
            config_dir = Path(os.environ["XDG_CONFIG_HOME"]) / "slcli"
        else:
            config_dir = Path.home() / ".config" / "slcli"

        config_dir.mkdir(parents=True, exist_ok=True)
        return config_dir / "config.json"

    @classmethod
    def load(cls) -> "ProfileConfig":
        """Load configuration from file."""
        config_path = cls.get_config_path()

        if not config_path.exists():
            return cls()

        try:
            with open(config_path, "r", encoding="utf-8") as f:
                data = json.load(f)
        except (json.JSONDecodeError, OSError):
            # If config file is corrupted or unreadable, return empty config
            return cls()

        # Parse profiles
        profiles: Dict[str, Profile] = {}
        profiles_data = data.get("profiles", {})
        for name, profile_data in profiles_data.items():
            profiles[name] = Profile.from_dict(name, profile_data)

        # Extract settings (non-profile data)
        settings: Dict[str, Any] = {}
        for key, value in data.items():
            if key not in ("current-profile", "profiles"):
                settings[key] = value

        return cls(
            current_profile=data.get("current-profile"),
            profiles=profiles,
            settings=settings,
        )

    def save(self) -> None:
        """Save configuration to file with secure permissions."""
        config_path = self.get_config_path()

        data: Dict[str, Any] = {}

        if self.current_profile:
            data["current-profile"] = self.current_profile

        if self.profiles:
            data["profiles"] = {name: profile.to_dict() for name, profile in self.profiles.items()}

        # Include additional settings
        data.update(self.settings)

        try:
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2)

            # Set restrictive permissions (600 - owner read/write only)
            # This is important because the file contains API keys
            try:
                config_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
            except OSError:
                # On some systems (e.g., Windows), chmod may not work as expected
                pass

        except OSError as e:
            raise RuntimeError(f"Failed to save configuration: {e}")

    def get_profile(self, name: str) -> Optional[Profile]:
        """Get a profile by name."""
        return self.profiles.get(name)

    def get_current_profile(self) -> Optional[Profile]:
        """Get the currently active profile."""
        if not self.current_profile:
            return None
        return self.profiles.get(self.current_profile)

    def set_current_profile(self, name: str) -> None:
        """Set the current profile."""
        if name not in self.profiles:
            raise ValueError(f"Profile '{name}' does not exist")
        self.current_profile = name

    def add_profile(self, profile: Profile, set_current: bool = False) -> None:
        """Add or update a profile."""
        self.profiles[profile.name] = profile
        if set_current or not self.current_profile:
            self.current_profile = profile.name

    def delete_profile(self, name: str) -> bool:
        """Delete a profile. Returns True if deleted, False if not found."""
        if name not in self.profiles:
            return False

        del self.profiles[name]

        # If we deleted the current profile, clear it or set to another
        if self.current_profile == name:
            if self.profiles:
                self.current_profile = next(iter(self.profiles.keys()))
            else:
                self.current_profile = None

        return True

    def list_profiles(self) -> List[Profile]:
        """List all profiles."""
        return list(self.profiles.values())


# Global state for profile override (set via --profile CLI option)
_profile_override: Optional[str] = None


def set_profile_override(profile_name: Optional[str]) -> None:
    """Set a profile override for the current command."""
    global _profile_override
    _profile_override = profile_name


def get_profile_override() -> Optional[str]:
    """Get the current profile override."""
    return _profile_override


def get_active_profile() -> Optional[Profile]:
    """Get the currently active profile, considering overrides.

    Priority order:
    1. CLI --profile option (stored in _profile_override)
    2. SLCLI_PROFILE environment variable
    3. current-profile from config file
    """
    config = ProfileConfig.load()

    # Check for override from CLI option
    override = get_profile_override()
    if override:
        profile = config.get_profile(override)
        if not profile:
            raise click.ClickException(f"Profile '{override}' not found")
        return profile

    # Check for environment variable override
    env_profile = os.environ.get("SLCLI_PROFILE")
    if env_profile:
        profile = config.get_profile(env_profile)
        if not profile:
            raise click.ClickException(f"Profile '{env_profile}' not found (from SLCLI_PROFILE)")
        return profile

    # Use current profile from config
    return config.get_current_profile()


def get_active_profile_name() -> Optional[str]:
    """Get the name of the currently active profile."""
    profile = get_active_profile()
    return profile.name if profile else None


def get_default_workspace() -> Optional[str]:
    """Get the default workspace from the active profile."""
    profile = get_active_profile()
    return profile.workspace if profile else None


def has_profiles_configured() -> bool:
    """Check if any profiles are configured."""
    config = ProfileConfig.load()
    return bool(config.profiles)


def check_config_file_permissions() -> Optional[str]:
    """Check if config file has appropriate permissions.

    Returns a warning message if permissions are too open, None otherwise.
    """
    config_path = ProfileConfig.get_config_path()
    if not config_path.exists():
        return None

    try:
        mode = config_path.stat().st_mode
        # Check if group or others have any permissions
        if mode & (stat.S_IRWXG | stat.S_IRWXO):
            return (
                f"Warning: Config file {config_path} has overly permissive permissions. "
                "Consider running: chmod 600 " + str(config_path)
            )
    except OSError:
        pass

    return None
