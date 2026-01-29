"""Unit tests for the profiles module."""

import json
from pathlib import Path
from typing import Any, Dict

from slcli.profiles import (
    Profile,
    ProfileConfig,
    check_config_file_permissions,
    get_active_profile,
    get_default_workspace,
    set_profile_override,
)


class TestProfile:
    """Tests for the Profile dataclass."""

    def test_profile_creation(self) -> None:
        """Test basic profile creation."""
        profile = Profile(
            name="test",
            server="https://example.com",
            api_key="secret123",
        )
        assert profile.name == "test"
        assert profile.server == "https://example.com"
        assert profile.api_key == "secret123"
        assert profile.web_url is None
        assert profile.platform is None
        assert profile.workspace is None

    def test_profile_with_all_fields(self) -> None:
        """Test profile creation with all fields."""
        profile = Profile(
            name="full",
            server="https://api.example.com",
            api_key="key123",
            web_url="https://web.example.com",
            platform="SLE",
            workspace="MyWorkspace",
        )
        assert profile.name == "full"
        assert profile.web_url == "https://web.example.com"
        assert profile.platform == "SLE"
        assert profile.workspace == "MyWorkspace"

    def test_profile_to_dict_minimal(self) -> None:
        """Test converting minimal profile to dict."""
        profile = Profile(
            name="test",
            server="https://example.com",
            api_key="secret",
        )
        result = profile.to_dict()
        assert result == {
            "server": "https://example.com",
            "api-key": "secret",
        }

    def test_profile_to_dict_full(self) -> None:
        """Test converting full profile to dict."""
        profile = Profile(
            name="test",
            server="https://api.example.com",
            api_key="secret",
            web_url="https://web.example.com",
            platform="SLS",
            workspace="Test Workspace",
        )
        result = profile.to_dict()
        assert result == {
            "server": "https://api.example.com",
            "api-key": "secret",
            "web-url": "https://web.example.com",
            "platform": "SLS",
            "workspace": "Test Workspace",
        }

    def test_profile_from_dict_minimal(self) -> None:
        """Test creating profile from minimal dict."""
        data: Dict[str, Any] = {
            "server": "https://example.com",
            "api-key": "secret",
        }
        profile = Profile.from_dict("test", data)
        assert profile.name == "test"
        assert profile.server == "https://example.com"
        assert profile.api_key == "secret"
        assert profile.web_url is None
        assert profile.platform is None
        assert profile.workspace is None

    def test_profile_from_dict_full(self) -> None:
        """Test creating profile from full dict."""
        data: Dict[str, Any] = {
            "server": "https://api.example.com",
            "api-key": "key123",
            "web-url": "https://web.example.com",
            "platform": "SLE",
            "workspace": "Production",
        }
        profile = Profile.from_dict("prod", data)
        assert profile.name == "prod"
        assert profile.server == "https://api.example.com"
        assert profile.api_key == "key123"
        assert profile.web_url == "https://web.example.com"
        assert profile.platform == "SLE"
        assert profile.workspace == "Production"


class TestProfileConfig:
    """Tests for the ProfileConfig class."""

    def test_empty_config(self) -> None:
        """Test creating empty config."""
        config = ProfileConfig()
        assert config.current_profile is None
        assert config.profiles == {}
        assert config.settings == {}

    def test_load_missing_file(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Test loading returns empty config when file doesn't exist."""
        config_file = tmp_path / "config.json"
        monkeypatch.setattr(
            "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
        )

        config = ProfileConfig.load()
        assert config.current_profile is None
        assert config.profiles == {}

    def test_load_valid_config(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Test loading valid config file."""
        config_file = tmp_path / "config.json"
        config_data: Dict[str, Any] = {
            "current-profile": "dev",
            "profiles": {
                "dev": {
                    "server": "https://dev.example.com",
                    "api-key": "dev-key",
                },
                "prod": {
                    "server": "https://prod.example.com",
                    "api-key": "prod-key",
                    "web-url": "https://prod-web.example.com",
                },
            },
        }
        config_file.write_text(json.dumps(config_data))
        config_file.chmod(0o600)
        monkeypatch.setattr(
            "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
        )

        config = ProfileConfig.load()
        assert config.current_profile == "dev"
        assert len(config.profiles) == 2
        assert "dev" in config.profiles
        assert "prod" in config.profiles
        assert config.profiles["dev"].server == "https://dev.example.com"
        assert config.profiles["prod"].web_url == "https://prod-web.example.com"

    def test_load_corrupted_file(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Test loading returns empty config for corrupted file."""
        config_file = tmp_path / "config.json"
        config_file.write_text("not valid json {{{")
        config_file.chmod(0o600)
        monkeypatch.setattr(
            "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
        )

        config = ProfileConfig.load()
        assert config.current_profile is None
        assert config.profiles == {}

    def test_save_config(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Test saving config file."""
        config_file = tmp_path / "config.json"
        monkeypatch.setattr(
            "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
        )

        config = ProfileConfig()
        config.add_profile(
            Profile(
                name="test",
                server="https://test.example.com",
                api_key="test-key",
            ),
            set_current=True,
        )
        config.save()

        assert config_file.exists()
        saved = json.loads(config_file.read_text())
        assert saved["current-profile"] == "test"
        assert "test" in saved["profiles"]

    def test_add_profile(self) -> None:
        """Test adding a profile."""
        config = ProfileConfig()
        profile = Profile(
            name="new",
            server="https://new.example.com",
            api_key="new-key",
        )
        config.add_profile(profile, set_current=True)

        assert "new" in config.profiles
        assert config.current_profile == "new"

    def test_add_profile_without_setting_current(self) -> None:
        """Test adding profile without making it current."""
        config = ProfileConfig()
        config.current_profile = "existing"

        profile = Profile(
            name="new",
            server="https://new.example.com",
            api_key="new-key",
        )
        config.add_profile(profile, set_current=False)

        assert "new" in config.profiles
        assert config.current_profile == "existing"

    def test_delete_profile(self) -> None:
        """Test deleting a profile."""
        config = ProfileConfig()
        config.profiles["test"] = Profile(
            name="test", server="https://test.example.com", api_key="key"
        )
        config.current_profile = "test"

        config.delete_profile("test")

        assert "test" not in config.profiles
        assert config.current_profile is None

    def test_delete_profile_sets_first_as_current(self) -> None:
        """Test that deleting current profile sets first remaining as current."""
        config = ProfileConfig()
        config.profiles["first"] = Profile(name="first", server="https://1.com", api_key="key1")
        config.profiles["second"] = Profile(name="second", server="https://2.com", api_key="key2")
        config.current_profile = "first"

        config.delete_profile("first")

        assert "first" not in config.profiles
        assert config.current_profile == "second"

    def test_get_profile(self) -> None:
        """Test getting a profile by name."""
        config = ProfileConfig()
        profile = Profile(name="test", server="https://test.example.com", api_key="key")
        config.profiles["test"] = profile

        result = config.get_profile("test")
        assert result is profile

        result = config.get_profile("nonexistent")
        assert result is None


class TestHelperFunctions:
    """Tests for module-level helper functions."""

    def test_get_active_profile_with_override(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Test that profile override takes precedence."""
        config_file = tmp_path / "config.json"
        config_data: Dict[str, Any] = {
            "current-profile": "default",
            "profiles": {
                "default": {"server": "https://default.com", "api-key": "default-key"},
                "override": {"server": "https://override.com", "api-key": "override-key"},
            },
        }
        config_file.write_text(json.dumps(config_data))
        config_file.chmod(0o600)
        monkeypatch.setattr(
            "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
        )

        # Clear any existing override
        set_profile_override(None)

        # Without override, get default
        profile = get_active_profile()
        assert profile is not None
        assert profile.name == "default"

        # With override, get the override profile
        set_profile_override("override")
        profile = get_active_profile()
        assert profile is not None
        assert profile.name == "override"
        assert profile.server == "https://override.com"

        # Clean up
        set_profile_override(None)

    def test_get_active_profile_no_profiles(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Test get_active_profile returns None when no profiles exist."""
        config_file = tmp_path / "config.json"
        monkeypatch.setattr(
            "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
        )
        set_profile_override(None)

        profile = get_active_profile()
        assert profile is None

    def test_get_default_workspace(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Test getting default workspace from active profile."""
        config_file = tmp_path / "config.json"
        config_data: Dict[str, Any] = {
            "current-profile": "test",
            "profiles": {
                "test": {
                    "server": "https://test.com",
                    "api-key": "key",
                    "workspace": "MyWorkspace",
                },
            },
        }
        config_file.write_text(json.dumps(config_data))
        config_file.chmod(0o600)
        monkeypatch.setattr(
            "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
        )
        set_profile_override(None)

        workspace = get_default_workspace()
        assert workspace == "MyWorkspace"

    def test_get_default_workspace_no_workspace(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Test get_default_workspace returns None when profile has no workspace."""
        config_file = tmp_path / "config.json"
        config_data: Dict[str, Any] = {
            "current-profile": "test",
            "profiles": {
                "test": {"server": "https://test.com", "api-key": "key"},
            },
        }
        config_file.write_text(json.dumps(config_data))
        config_file.chmod(0o600)
        monkeypatch.setattr(
            "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
        )
        set_profile_override(None)

        workspace = get_default_workspace()
        assert workspace is None


class TestPermissions:
    """Tests for file permission handling."""

    def test_check_permissions_good(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Test that proper permissions are accepted."""
        config_file = tmp_path / "config.json"
        config_file.write_text("{}")
        config_file.chmod(0o600)
        monkeypatch.setattr(
            "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
        )

        result = check_config_file_permissions()
        assert result is None  # No warning for good permissions

    def test_check_permissions_too_permissive(self, tmp_path: Path, monkeypatch: Any) -> None:
        """Test that world-readable permissions are flagged."""
        config_file = tmp_path / "config.json"
        config_file.write_text("{}")
        config_file.chmod(0o644)
        monkeypatch.setattr(
            "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
        )

        result = check_config_file_permissions()
        assert result is not None
        assert "permissive" in result.lower() or "permission" in result.lower()
