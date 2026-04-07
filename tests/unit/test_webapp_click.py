"""Unit tests for slcli webapp commands."""

import io
import tarfile
from hashlib import sha256
from json import dumps, loads
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import patch

import pytest
from click.testing import CliRunner
from pytest import MonkeyPatch
from slcli.main import cli
from slcli.utils import ExitCodes

from .test_utils import patch_keyring


def _read_control_file(pkg_path: Path) -> str:
    """Extract and decode the Debian control file from a .nipkg archive."""
    with open(pkg_path, "rb") as package_file:
        assert package_file.read(8) == b"!<arch>\n"

        while True:
            header = package_file.read(60)
            if not header:
                break
            member_name = header[:16].decode("utf-8").strip()
            member_size = int(header[48:58].decode("ascii").strip())
            member_data = package_file.read(member_size)
            if member_size % 2:
                package_file.read(1)

            if member_name == "control.tar.gz":
                with tarfile.open(fileobj=io.BytesIO(member_data), mode="r:gz") as archive:
                    control_member = archive.extractfile("control")
                    assert control_member is not None
                    return control_member.read().decode("utf-8")

    raise AssertionError("control.tar.gz not found in package")


def _read_data_member_names(pkg_path: Path) -> List[str]:
    """Return the member names stored in the data archive of a .nipkg."""
    with open(pkg_path, "rb") as package_file:
        assert package_file.read(8) == b"!<arch>\n"

        while True:
            header = package_file.read(60)
            if not header:
                break
            member_name = header[:16].decode("utf-8").strip()
            member_size = int(header[48:58].decode("ascii").strip())
            member_data = package_file.read(member_size)
            if member_size % 2:
                package_file.read(1)

            if member_name == "data.tar.gz":
                with tarfile.open(fileobj=io.BytesIO(member_data), mode="r:gz") as archive:
                    return [member.name for member in archive.getmembers()]

    raise AssertionError("data.tar.gz not found in package")


def _read_data_member_payloads(pkg_path: Path, member_name: str) -> List[bytes]:
    """Return all payloads for a given member name in the data archive of a .nipkg."""
    with open(pkg_path, "rb") as package_file:
        assert package_file.read(8) == b"!<arch>\n"

        while True:
            header = package_file.read(60)
            if not header:
                break
            archive_member_name = header[:16].decode("utf-8").strip()
            member_size = int(header[48:58].decode("ascii").strip())
            member_data = package_file.read(member_size)
            if member_size % 2:
                package_file.read(1)

            if archive_member_name == "data.tar.gz":
                payloads: List[bytes] = []
                with tarfile.open(fileobj=io.BytesIO(member_data), mode="r:gz") as archive:
                    for archive_member in archive.getmembers():
                        if archive_member.name == member_name:
                            extracted = archive.extractfile(archive_member)
                            assert extracted is not None
                            payloads.append(extracted.read())
                return payloads

    raise AssertionError("data.tar.gz not found in package")


@pytest.fixture(autouse=True)
def _no_profile_workspace() -> Any:
    """Prevent profile workspace default from interfering with tests."""
    with patch("slcli.workspace_utils.get_default_workspace", return_value=None):
        yield


def test_webapp_init_creates_starter_files(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    runner = CliRunner()
    patch_keyring(monkeypatch)

    target = tmp_path / "webapp_skel"
    result = runner.invoke(cli, ["webapp", "init", str(target)])
    assert result.exit_code == 0
    assert (target / "PROMPTS.md").exists()
    assert (target / "START_HERE.md").exists()
    assert not (target / "README.md").exists()

    prompts = (target / "PROMPTS.md").read_text(encoding="utf-8")
    starter = (target / "START_HERE.md").read_text(encoding="utf-8")

    assert "Bootstrap this directory into a maintainable Angular 20 SystemLink webapp" in prompts
    assert "Angular CLI remains the source of truth" in starter
    assert "@ni/nimble-angular" in starter


def test_webapp_init_starter_creates_prompts(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    runner = CliRunner()
    patch_keyring(monkeypatch)

    target = tmp_path / "ng_app"
    result = runner.invoke(cli, ["webapp", "init", str(target)])
    assert result.exit_code == 0
    assert (target / "PROMPTS.md").exists()
    assert (target / "START_HERE.md").exists()
    prompts = (target / "PROMPTS.md").read_text(encoding="utf-8")
    assert "systemlink-webapp" in prompts
    assert "systemlink-clients-ts" in prompts
    starter = (target / "START_HERE.md").read_text(encoding="utf-8")
    assert "slcli webapp publish" in starter
    assert "Angular CLI remains the source of truth" in starter


def test_webapp_init_no_overwrite(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    runner = CliRunner()
    patch_keyring(monkeypatch)

    target = tmp_path / "ng_app"
    target.mkdir()
    (target / "PROMPTS.md").write_text("existing")

    result = runner.invoke(cli, ["webapp", "init", str(target)])
    assert result.exit_code != 0
    assert "already exist" in result.output


def test_webapp_init_requires_directory(monkeypatch: MonkeyPatch) -> None:
    runner = CliRunner()
    patch_keyring(monkeypatch)

    result = runner.invoke(cli, ["webapp", "init"])
    assert result.exit_code != 0
    assert "Missing argument 'DIRECTORY'" in result.output


def test_webapp_init_force_overwrite(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    runner = CliRunner()
    patch_keyring(monkeypatch)

    target = tmp_path / "ng_app"
    target.mkdir()
    (target / "PROMPTS.md").write_text("old")
    (target / "START_HERE.md").write_text("old")

    result = runner.invoke(cli, ["webapp", "init", str(target), "--force"])
    assert result.exit_code == 0
    assert "systemlink-webapp" in (target / "PROMPTS.md").read_text(encoding="utf-8")


def test_webapp_init_installs_skills(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    """Webapp init should auto-install skills into the project."""
    runner = CliRunner()
    patch_keyring(monkeypatch)

    target = tmp_path / "ng_skills"
    result = runner.invoke(cli, ["webapp", "init", str(target)])
    assert result.exit_code == 0

    # Skills should be installed in the universal .agents/skills/ convention
    skills_dir = target / ".agents" / "skills"
    assert skills_dir.exists()
    assert (skills_dir / "systemlink-webapp" / "SKILL.md").exists()
    assert (skills_dir / "slcli" / "SKILL.md").exists()


def test_webapp_manifest_init_writes_pack_config_only(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    runner = CliRunner()
    patch_keyring(monkeypatch)

    target = tmp_path / "my-dashboard"
    icon_source = tmp_path / "shared-icon.svg"
    icon_source.write_text("<svg></svg>", encoding="utf-8")
    result = runner.invoke(
        cli,
        [
            "webapp",
            "manifest",
            "init",
            str(target),
            "--description",
            "A dashboard for monitoring fleet status and calibration trends.",
            "--section",
            "Dashboard",
            "--maintainer",
            "Test User <test@example.com>",
            "--license",
            "MIT",
            "--icon-file",
            str(icon_source),
            "--homepage",
            "https://example.com/my-dashboard",
            "--tags",
            "dashboard,monitoring,assets",
            "--min-server-version",
            "2024 Q4",
        ],
    )

    assert result.exit_code == 0

    config = loads((target / "nipkg.config.json").read_text(encoding="utf-8"))

    assert config["package"] == "my-dashboard"
    assert config["version"] == "0.1.0"
    assert config["displayName"] == "My Dashboard"
    assert config["section"] == "Dashboard"
    assert config["maintainer"] == "Test User <test@example.com>"
    assert config["xbPlugin"] == "webapp"
    assert config["slPluginManagerTags"] == "dashboard,monitoring,assets"
    assert config["slPluginManagerMinServerVersion"] == "2024 Q4"
    assert config["buildDir"] == "dist/my-dashboard/browser"
    assert config["buildCommand"] == "npm run build"
    assert config["iconFile"] == "shared-icon.svg"
    assert "nipkgFile" not in config
    assert not (target / "manifest.json").exists()
    assert (target / "shared-icon.svg").exists()


def test_webapp_manifest_init_defaults_build_dir_from_directory_not_package(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    runner = CliRunner()
    patch_keyring(monkeypatch)

    target = tmp_path / "angular-app"
    icon_source = tmp_path / "dashboard-icon.svg"
    icon_source.write_text("<svg></svg>", encoding="utf-8")
    result = runner.invoke(
        cli,
        [
            "webapp",
            "manifest",
            "init",
            str(target),
            "--package",
            "plugin-catalog-entry",
            "--description",
            "A dashboard for monitoring fleet status and calibration trends.",
            "--section",
            "Dashboard",
            "--maintainer",
            "Test User <test@example.com>",
            "--license",
            "MIT",
            "--icon-file",
            str(icon_source),
        ],
    )

    assert result.exit_code == 0

    config = loads((target / "nipkg.config.json").read_text(encoding="utf-8"))

    assert config["package"] == "plugin-catalog-entry"
    assert config["buildDir"] == "dist/angular-app/browser"


def test_webapp_manifest_init_rejects_invalid_metadata(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    runner = CliRunner()
    patch_keyring(monkeypatch)

    target = tmp_path / "bad-dashboard"
    icon_source = tmp_path / "bad-dashboard.svg"
    icon_source.write_text("<svg></svg>", encoding="utf-8")
    result = runner.invoke(
        cli,
        [
            "webapp",
            "manifest",
            "init",
            str(target),
            "--version",
            "1.0",
            "--description",
            "too short",
            "--section",
            "D",
            "--maintainer",
            "not-an-email",
            "--license",
            "M",
            "--icon-file",
            str(icon_source),
        ],
    )

    assert result.exit_code == ExitCodes.INVALID_INPUT
    assert "version must be strict semver" in result.output
    assert "description must be at least 20 characters" in result.output
    assert "maintainer must be in the format" in result.output
    assert not (target / "bad-dashboard.svg").exists()


def test_webapp_manifest_init_does_not_copy_icon_when_config_exists(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    runner = CliRunner()
    patch_keyring(monkeypatch)

    target = tmp_path / "existing-manifest"
    target.mkdir()
    (target / "nipkg.config.json").write_text("{}", encoding="utf-8")
    icon_source = tmp_path / "existing-icon.svg"
    icon_source.write_text("<svg></svg>", encoding="utf-8")

    result = runner.invoke(
        cli,
        [
            "webapp",
            "manifest",
            "init",
            str(target),
            "--description",
            "A dashboard for monitoring fleet status and calibration trends.",
            "--section",
            "Dashboard",
            "--maintainer",
            "Test User <test@example.com>",
            "--license",
            "MIT",
            "--icon-file",
            str(icon_source),
        ],
    )

    assert result.exit_code == ExitCodes.INVALID_INPUT
    assert "nipkg.config.json already exist" in result.output
    assert not (target / "existing-icon.svg").exists()


def test_webapp_manifest_init_rejects_schema_length_limits_and_unknown_fields(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    runner = CliRunner()
    patch_keyring(monkeypatch)

    target = tmp_path / "too-long"
    config_path = target / "invalid.json"
    target.mkdir()
    (target / "icon.svg").write_text("<svg></svg>", encoding="utf-8")
    invalid_config = {
        "package": "p" * 101,
        "version": "1.2.3",
        "displayName": "D" * 201,
        "description": "A" * 5001,
        "section": "Dashboard",
        "maintainer": "Test User <test@example.com>",
        "license": "MIT",
        "xbPlugin": "webapp",
        "iconFile": "icon.svg",
        "unexpected": "value",
    }
    config_path.write_text(
        dumps(invalid_config),
        encoding="utf-8",
    )

    result = runner.invoke(
        cli,
        [
            "webapp",
            "pack",
            str(target),
            "--config",
            str(config_path),
        ],
    )

    assert result.exit_code == ExitCodes.INVALID_INPUT
    assert "package must be at most 100 characters" in result.output
    assert "displayName must be at most 200 characters" in result.output
    assert "description must be at most 5000 characters" in result.output
    assert "unexpected field(s): unexpected" in result.output


def test_webapp_pack_creates_nipkg(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    runner = CliRunner()
    patch_keyring(monkeypatch)

    folder = tmp_path / "site"
    folder.mkdir()
    (folder / "index.html").write_text("hello")

    out = tmp_path / "site_out.nipkg"
    result = runner.invoke(cli, ["webapp", "pack", str(folder), "--output", str(out)])
    assert result.exit_code == 0
    assert out.exists()
    # verify it's a Debian-style ar archive (.nipkg)
    with open(out, "rb") as f:
        magic = f.read(8)
    assert magic == b"!<arch>\n"

    # Simple check that the archive contains the standard members by searching bytes
    data = out.read_bytes()
    assert b"debian-binary" in data
    assert b"control.tar.gz" in data
    assert b"data.tar.gz" in data


def test_webapp_pack_uses_plugin_manager_metadata_from_config(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    runner = CliRunner()
    patch_keyring(monkeypatch)

    project_dir = tmp_path / "plugin-project"
    build_dir = project_dir / "dist" / "plugin-project" / "browser"
    build_dir.mkdir(parents=True)
    (build_dir / "index.html").write_text("hello", encoding="utf-8")
    (project_dir / "icon.svg").write_text("<svg></svg>", encoding="utf-8")

    config_path = project_dir / "nipkg.config.json"
    config_path.write_text(
        """
{
  "package": "plugin-project",
  "version": "1.2.3",
  "displayName": "Plugin Project",
  "description": "A plugin for monitoring assets and publishing fleet dashboards.",
  "section": "Monitoring",
  "maintainer": "Plugin Team <plugins@example.com>",
  "homepage": "https://example.com/plugin-project",
  "license": "MIT",
  "xbPlugin": "webapp",
  "slPluginManagerTags": "monitoring,assets,webapp",
  "slPluginManagerMinServerVersion": "2024 Q4",
    "iconFile": "icon.svg",
  "buildDir": "dist/plugin-project/browser",
  "buildCommand": "npm run build"
}
""".strip(),
        encoding="utf-8",
    )

    output_path = tmp_path / "plugin-project_1.2.3_all.nipkg"
    result = runner.invoke(
        cli,
        [
            "webapp",
            "pack",
            "--config",
            str(config_path),
            "--output",
            str(output_path),
        ],
    )

    assert result.exit_code == 0
    manifest_path = project_dir / "manifest.json"
    manifest = loads(manifest_path.read_text(encoding="utf-8"))
    control_file = _read_control_file(output_path)
    assert manifest["schemaVersion"] == 2
    assert manifest["nipkgFile"] == "plugin-project_1.2.3_all.nipkg"
    assert manifest["sha256"] == sha256(output_path.read_bytes()).hexdigest()
    assert "Package: plugin-project" in control_file
    assert "Version: 1.2.3" in control_file
    assert "Section: Monitoring" in control_file
    assert "Maintainer: Plugin Team <plugins@example.com>" in control_file
    assert "Homepage: https://example.com/plugin-project" in control_file
    assert "XB-DisplayName: Plugin Project" in control_file
    assert "XB-Plugin: webapp" in control_file
    assert "XB-SlPluginManagerLicense: MIT" in control_file
    assert "XB-SlPluginManagerTags: monitoring,assets,webapp" in control_file
    assert "XB-SlPluginManagerMinServerVersion: 2024 Q4" in control_file
    assert "XB-SlPluginManagerIcon: icon.svg" in control_file

    data_members = _read_data_member_names(output_path)
    assert any(member.endswith("icon.svg") for member in data_members)


def test_webapp_pack_replaces_existing_build_icon_without_duplicates(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    runner = CliRunner()
    patch_keyring(monkeypatch)

    project_dir = tmp_path / "pack-icon-override"
    build_dir = project_dir / "dist" / "pack-icon-override" / "browser"
    build_dir.mkdir(parents=True)
    (build_dir / "index.html").write_text("hello", encoding="utf-8")
    (build_dir / "icon.svg").write_text("<svg>build</svg>", encoding="utf-8")

    icon_source_dir = project_dir / "assets"
    icon_source_dir.mkdir()
    (icon_source_dir / "icon.svg").write_text("<svg>source</svg>", encoding="utf-8")

    config_path = project_dir / "nipkg.config.json"
    config_path.write_text(
        dumps(
            {
                "package": "pack-icon-override",
                "version": "1.2.3",
                "displayName": "Pack Icon Override",
                "description": "A plugin package should keep only one icon entry in the payload.",
                "section": "Monitoring",
                "maintainer": "Plugin Team <plugins@example.com>",
                "license": "MIT",
                "xbPlugin": "webapp",
                "iconFile": "assets/icon.svg",
                "buildDir": "dist/pack-icon-override/browser",
                "buildCommand": "npm run build",
            }
        ),
        encoding="utf-8",
    )

    output_path = tmp_path / "pack-icon-override_1.2.3_all.nipkg"
    result = runner.invoke(
        cli,
        [
            "webapp",
            "pack",
            "--config",
            str(config_path),
            "--output",
            str(output_path),
        ],
    )

    assert result.exit_code == 0
    icon_payloads = _read_data_member_payloads(output_path, "./icon.svg")
    assert len(icon_payloads) == 1
    assert icon_payloads[0] == b"<svg>source</svg>"


def test_webapp_pack_generates_manifest_with_provenance(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    runner = CliRunner()
    patch_keyring(monkeypatch)

    project_dir = tmp_path / "provenance-plugin"
    build_dir = project_dir / "dist" / "provenance-plugin" / "browser"
    build_dir.mkdir(parents=True)
    (build_dir / "index.html").write_text("hello", encoding="utf-8")
    (project_dir / "icon.svg").write_text("<svg></svg>", encoding="utf-8")

    config_path = project_dir / "nipkg.config.json"
    config_path.write_text(
        dumps(
            {
                "package": "provenance-plugin",
                "version": "1.2.3",
                "displayName": "Provenance Plugin",
                "description": "A plugin package with provenance for reviewed release artifacts.",
                "section": "Monitoring",
                "maintainer": "Plugin Team <plugins@example.com>",
                "license": "MIT",
                "xbPlugin": "webapp",
                "iconFile": "icon.svg",
                "buildDir": "dist/provenance-plugin/browser",
                "buildCommand": "npm run build",
                "sourceRepo": "ni-kismet/systemlink-plugin-manager",
                "releaseTag": "v1.2.3",
                "sourceCommit": "0123456789abcdef0123456789abcdef01234567",
                "screenshots": ["catalog.png"],
            }
        ),
        encoding="utf-8",
    )

    output_path = tmp_path / "provenance-plugin_1.2.3_all.nipkg"
    result = runner.invoke(
        cli,
        [
            "webapp",
            "pack",
            "--config",
            str(config_path),
            "--output",
            str(output_path),
        ],
    )

    assert result.exit_code == 0
    manifest = loads((project_dir / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["sourceRepo"] == "ni-kismet/systemlink-plugin-manager"
    assert manifest["releaseTag"] == "v1.2.3"
    assert manifest["sourceCommit"] == "0123456789abcdef0123456789abcdef01234567"
    assert manifest["screenshots"] == ["catalog.png"]


def test_webapp_pack_rejects_missing_icon_file(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    runner = CliRunner()
    patch_keyring(monkeypatch)

    project_dir = tmp_path / "missing-icon"
    build_dir = project_dir / "dist" / "missing-icon" / "browser"
    build_dir.mkdir(parents=True)
    (build_dir / "index.html").write_text("hello", encoding="utf-8")

    config_path = project_dir / "nipkg.config.json"
    config_path.write_text(
        dumps(
            {
                "package": "missing-icon",
                "version": "1.2.3",
                "displayName": "Missing Icon",
                "description": "A plugin config without an icon should now be rejected.",
                "section": "Monitoring",
                "maintainer": "Plugin Team <plugins@example.com>",
                "license": "MIT",
                "xbPlugin": "webapp",
                "buildDir": "dist/missing-icon/browser",
                "buildCommand": "npm run build",
            }
        ),
        encoding="utf-8",
    )

    result = runner.invoke(cli, ["webapp", "pack", "--config", str(config_path)])

    assert result.exit_code == ExitCodes.INVALID_INPUT
    assert "iconFile is required" in result.output


def test_webapp_pack_accepts_legacy_appstore_keys(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    runner = CliRunner()
    patch_keyring(monkeypatch)

    project_dir = tmp_path / "legacy-plugin"
    build_dir = project_dir / "dist" / "legacy-plugin" / "browser"
    build_dir.mkdir(parents=True)
    (build_dir / "index.html").write_text("hello", encoding="utf-8")
    (project_dir / "legacy-icon.svg").write_text("<svg></svg>", encoding="utf-8")

    config_path = project_dir / "legacy.json"
    config_path.write_text(
        dumps(
            {
                "package": "legacy-plugin",
                "version": "1.2.3",
                "displayName": "Legacy Plugin",
                "description": "A legacy App Store config should normalize to Plugin Manager fields.",
                "appStoreCategory": "Monitoring",
                "appStoreAuthor": "Plugin Team <plugins@example.com>",
                "appStoreRepo": "https://example.com/legacy-plugin",
                "license": "MIT",
                "appStoreType": "webapp",
                "appStoreTags": "legacy,monitoring",
                "appStoreMinServerVersion": "2024 Q4",
                "iconFile": "legacy-icon.svg",
                "buildDir": "dist/legacy-plugin/browser",
                "buildCommand": "npm run build",
            }
        ),
        encoding="utf-8",
    )

    output_path = tmp_path / "legacy-plugin_1.2.3_all.nipkg"
    result = runner.invoke(
        cli,
        [
            "webapp",
            "pack",
            "--config",
            str(config_path),
            "--output",
            str(output_path),
        ],
    )

    assert result.exit_code == 0
    control_file = _read_control_file(output_path)
    assert "Section: Monitoring" in control_file
    assert "Maintainer: Plugin Team <plugins@example.com>" in control_file
    assert "Homepage: https://example.com/legacy-plugin" in control_file
    assert "XB-Plugin: webapp" in control_file
    assert "XB-SlPluginManagerTags: legacy,monitoring" in control_file
    assert "XB-SlPluginManagerMinServerVersion: 2024 Q4" in control_file
    assert "XB-SlPluginManagerIcon: legacy-icon.svg" in control_file


def test_webapp_list_shows_items(monkeypatch: MonkeyPatch) -> None:
    runner = CliRunner()
    patch_keyring(monkeypatch)

    import requests

    class MockResp:
        def __init__(self, data: Dict[str, Any]):
            self._data = data

        def json(self) -> Dict[str, Any]:
            return self._data

        @property
        def status_code(self) -> int:
            return 200

        def raise_for_status(self) -> None:
            return None

    def mock_post(url: str, **kwargs: Any) -> MockResp:
        return MockResp(
            {"webapps": [{"id": "a1", "name": "AppOne", "workspace": "ws1", "type": "WebVI"}]}
        )

    monkeypatch.setattr(requests, "post", mock_post)
    # patch workspace map
    import slcli.utils

    monkeypatch.setattr(slcli.utils, "get_workspace_map", lambda: {})

    result = runner.invoke(cli, ["webapp", "list"])
    assert result.exit_code == 0
    assert "AppOne" in result.output


def test_webapp_list_with_filter(monkeypatch: MonkeyPatch) -> None:
    """Ensure user filter is combined with base filter."""
    runner = CliRunner()
    patch_keyring(monkeypatch)

    import requests

    class MockResp:
        def __init__(self, data: Dict[str, Any]):
            self._data = data

        def json(self) -> Dict[str, Any]:
            return self._data

        @property
        def status_code(self) -> int:
            return 200

        def raise_for_status(self) -> None:
            return None

    def mock_post(url: str, **kwargs: Any) -> MockResp:
        payload = kwargs.get("json", {})
        filt = payload.get("filter", "")
        assert '(type == "WebVI")' in filt
        # New implementation avoids ToLower(); ensure one of the variants is present
        assert 'name.Contains("appone")' in filt or 'name.Contains("Appone")' in filt
        return MockResp({"webapps": []})

    monkeypatch.setattr(requests, "post", mock_post)
    import slcli.utils

    monkeypatch.setattr(slcli.utils, "get_workspace_map", lambda: {})

    result = runner.invoke(
        cli,
        ["webapp", "list", "--filter", "AppOne", "--format", "json"],
    )
    assert result.exit_code == 0


def test_webapp_list_paging_default(monkeypatch: MonkeyPatch) -> None:
    """Default take should be 25 and the CLI should offer to show the next 25."""
    runner = CliRunner()
    patch_keyring(monkeypatch)

    import requests

    class MockResp:
        def __init__(self, data: Dict[str, Any]):
            self._data = data

        def json(self) -> Dict[str, Any]:
            return self._data

        @property
        def status_code(self) -> int:
            return 200

        def raise_for_status(self) -> None:
            return None

    def make_items(start: int, count: int) -> list:
        return [
            {"id": f"id{n}", "name": f"App{n}", "workspace": "ws1", "type": "WebVI"}
            for n in range(start, start + count)
        ]

    # Create two pages: 25 items, then 5 items
    pages = [make_items(1, 25), make_items(26, 5)]
    call = {"i": 0}

    def mock_post(url: str, **kwargs: Any) -> Any:
        i = call["i"]
        call["i"] += 1
        data: Dict[str, Any] = {"webapps": pages[i]}
        # Add continuation token on first page
        if i == 0:
            data["continuationToken"] = "tok1"
        return MockResp(data)

    monkeypatch.setattr(requests, "post", mock_post)
    # patch workspace map
    import slcli.utils

    monkeypatch.setattr(slcli.utils, "get_workspace_map", lambda: {})

    # Simulate user answering 'n' to the "Show next set of results?" prompt
    with patch("slcli.webapp_click.questionary.confirm") as mock_confirm:
        mock_confirm.return_value.ask.return_value = False
        result = runner.invoke(cli, ["webapp", "list"])
    assert result.exit_code == 0
    # Should contain first page item but not an item from the second page
    assert "App1" in result.output
    assert "App26" not in result.output


def test_webapp_list_paging_custom_take(monkeypatch: MonkeyPatch) -> None:
    """When the user specifies --take 10 the CLI should page by 10 and offer next 10."""
    runner = CliRunner()
    patch_keyring(monkeypatch)

    import requests

    class MockResp:
        def __init__(self, data: Dict[str, Any]):
            self._data = data

        def json(self) -> Dict[str, Any]:
            return self._data

        @property
        def status_code(self) -> int:
            return 200

        def raise_for_status(self) -> None:
            return None

    def make_items(start: int, count: int) -> list:
        return [
            {"id": f"id{n}", "name": f"App{n}", "workspace": "ws1", "type": "WebVI"}
            for n in range(start, start + count)
        ]

    # Pages of 10, 10, 5
    pages = [make_items(1, 10), make_items(11, 10), make_items(21, 5)]
    call = {"i": 0}

    def mock_post(url: str, **kwargs: Any) -> Any:
        i = call["i"]
        call["i"] += 1
        data: Dict[str, Any] = {"webapps": pages[i]}
        if i < 2:
            data["continuationToken"] = f"tok{i+1}"
        return MockResp(data)

    monkeypatch.setattr(requests, "post", mock_post)
    import slcli.utils

    monkeypatch.setattr(slcli.utils, "get_workspace_map", lambda: {})

    # Simulate user answering 'y' to fetch second page, then 'n' to stop before third
    with patch("slcli.webapp_click.questionary.confirm") as mock_confirm:
        mock_confirm.return_value.ask.side_effect = [True, False]
        result = runner.invoke(cli, ["webapp", "list", "--take", "10"])
    assert result.exit_code == 0
    # First and second page items should be present, third page should not
    assert "App1" in result.output
    assert "App20" in result.output
    assert "App21" not in result.output


def test_webapp_get_shows_metadata(monkeypatch: MonkeyPatch) -> None:
    runner = CliRunner()
    patch_keyring(monkeypatch)

    import requests

    class MockResp:
        def __init__(self, data: Dict[str, Any]):
            self._data = data

        def json(self) -> Dict[str, Any]:
            return self._data

        @property
        def status_code(self) -> int:
            return 200

        def raise_for_status(self) -> None:
            return None

    def mock_get(url: str, **kwargs: Any) -> Any:
        return MockResp({"id": "abc", "name": "MyApp", "properties": {}, "type": "WebVI"})

    monkeypatch.setattr(requests, "get", mock_get)
    result = runner.invoke(cli, ["webapp", "get", "--id", "abc"])
    assert result.exit_code == 0
    assert "MyApp" in result.output


def test_webapp_publish_creates_and_uploads(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    runner = CliRunner()
    patch_keyring(monkeypatch)

    # create a source folder to publish
    folder = tmp_path / "site"
    folder.mkdir()
    (folder / "index.html").write_text("hi")

    import requests

    class MockPostResp:
        def __init__(self, data: Dict[str, Any]):
            self._data = data

        def json(self) -> Dict[str, Any]:
            return self._data

        @property
        def status_code(self) -> int:
            return 201

        def raise_for_status(self) -> None:
            return None

    class MockPutResp:
        text = ""

        @property
        def status_code(self) -> int:
            return 204

        def raise_for_status(self) -> None:
            return None

    def mock_post(url: str, **kwargs: Any) -> Any:
        return MockPostResp({"id": "new-webapp-id"})

    def mock_put(url: str, **kwargs: Any) -> Any:
        return MockPutResp()

    monkeypatch.setattr(requests, "post", mock_post)
    monkeypatch.setattr(requests, "put", mock_put)

    result = runner.invoke(
        cli, ["webapp", "publish", str(folder), "--name", "NewApp", "--workspace", "Default"]
    )
    assert result.exit_code == 0
    assert "Published webapp content" in result.output or "Created webapp metadata" in result.output


def test_webapp_open_uses_workspace_url(monkeypatch: MonkeyPatch) -> None:
    """Ensure open builds friendly URL when workspace name is available."""
    runner = CliRunner()
    patch_keyring(monkeypatch)

    import requests
    import slcli.webapp_click

    class MockResp:
        def json(self) -> Dict[str, Any]:
            return {
                "id": "app1",
                "name": "AppOne",
                "workspace": "ws1",
                "properties": {},
                "type": "WebVI",
            }

        def raise_for_status(self) -> None:
            return None

    opened: list[str] = []

    import webbrowser

    monkeypatch.setattr(requests, "get", lambda *a, **k: MockResp())
    monkeypatch.setattr(slcli.webapp_click, "get_web_url", lambda: "https://web.example.test")
    monkeypatch.setattr(slcli.webapp_click, "get_workspace_map", lambda: {"ws1": "Workspace One"})
    monkeypatch.setattr(webbrowser, "open", lambda url: opened.append(url))

    result = runner.invoke(cli, ["webapp", "open", "--id", "app1"])

    assert result.exit_code == 0
    assert opened[0] == "https://web.example.test/webapps/app/Workspace%20One/AppOne"
    assert "Opening" in result.output
