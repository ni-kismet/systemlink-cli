"""Unit tests for slcli webapp commands."""

import io
import tarfile
from hashlib import sha256
from json import dumps, loads
from pathlib import Path, PureWindowsPath
from typing import Any, Dict, List
from unittest.mock import patch

import pytest
from click.testing import CliRunner
from pytest import MonkeyPatch

from slcli import webapp_bootstrap
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

    assert "slcli webapp new <app-name>" in prompts
    assert "Bootstrap this directory into a maintainable Angular 20 SystemLink webapp" in prompts
    assert "Angular CLI remains the source of truth" in starter
    assert "Use `slcli webapp new <app-name>`" in starter
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
    assert "bundled `slcli` skill" in prompts
    assert "systemlink-clients-ts" in prompts
    assert "low-level manual path" in prompts
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
    assert "bundled `slcli` skill" in (target / "PROMPTS.md").read_text(encoding="utf-8")


def test_webapp_init_installs_project_skills(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    """Webapp init should install project-scoped skills for the manual starter path."""
    runner = CliRunner()
    patch_keyring(monkeypatch)

    target = tmp_path / "ng_skills"
    result = runner.invoke(cli, ["webapp", "init", str(target)])
    assert result.exit_code == 0
    assert "currently unavailable" not in result.output
    assert "currently unavailable" not in (target / "PROMPTS.md").read_text(encoding="utf-8")
    assert "currently unavailable" not in (target / "START_HERE.md").read_text(encoding="utf-8")
    assert (target / ".agents" / "skills" / "slcli" / "SKILL.md").exists()


def test_webapp_new_blank_creates_host_ready_workspace(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    runner = CliRunner()
    patch_keyring(monkeypatch)

    target = tmp_path / "coffee-roaster"
    result = runner.invoke(
        cli,
        [
            "webapp",
            "new",
            "coffee-roaster",
            "--directory",
            str(target),
            "--skip-install",
        ],
    )

    assert result.exit_code == 0
    assert (target / "package.json").exists()
    assert (target / "angular.json").exists()
    assert (target / "README.md").exists()
    assert (target / "src" / "app" / "app.module.ts").exists()
    assert (target / "src" / "app" / "app-routing.module.ts").exists()
    assert (target / "src" / "app" / "features" / "master-detail").exists()

    package_json = loads((target / "package.json").read_text(encoding="utf-8"))
    angular_json = loads((target / "angular.json").read_text(encoding="utf-8"))
    index_html = (target / "src" / "index.html").read_text(encoding="utf-8")
    main_ts = (target / "src" / "main.ts").read_text(encoding="utf-8")
    app_component = (target / "src" / "app" / "app.component.ts").read_text(encoding="utf-8")
    app_module = (target / "src" / "app" / "app.module.ts").read_text(encoding="utf-8")
    app_routing = (target / "src" / "app" / "app-routing.module.ts").read_text(encoding="utf-8")
    app_shell = (target / "src" / "app" / "core" / "layout" / "app-shell.component.ts").read_text(
        encoding="utf-8"
    )
    readme = (target / "README.md").read_text(encoding="utf-8")

    assert package_json["dependencies"]["@ni/nimble-angular"] == "~33.4.4"
    assert package_json["dependencies"]["@ni/ok-angular"] == "2.5.0"
    assert package_json["dependencies"]["@ni/systemlink-clients-ts"] == "3.0.2"
    assert "@angular/platform-browser-dynamic" not in package_json["dependencies"]
    assert "@angular/animations" not in package_json["dependencies"]
    assert package_json["engines"]["node"] == ">=24"
    assert package_json["devDependencies"]["@angular/localize"] == "^20.3.26"
    assert package_json["devDependencies"]["@angular/build"] == "^20.3.32"
    assert "@angular-devkit/build-angular" not in package_json["devDependencies"]
    assert "test" not in package_json["scripts"]
    assert "<base" not in index_html
    assert "bootstrapApplication(AppComponent" in main_ts
    assert "importProvidersFrom(AppModule)" in main_ts
    assert "platformBrowserDynamic" not in main_ts
    assert "standalone: true" in app_component
    assert "AppShellComponent" in app_component
    assert "APP_BASE_HREF" in app_module
    assert "bootstrap:" not in app_module
    assert "CUSTOM_ELEMENTS_SCHEMA" not in app_module
    assert "CommonModule" in app_module
    assert "BrowserModule" not in app_module
    assert "MasterDetailPageComponent" in app_module
    assert "standalone: true" in app_shell
    assert "RouterModule" in app_shell
    assert "AppRoutingModule" not in app_shell
    assert "useHash: true" in app_routing
    assert "path: 'master-detail'" in app_routing
    assert (
        angular_json["projects"]["coffee-roaster"]["architect"]["build"]["builder"]
        == "@angular/build:application"
    )
    assert (
        angular_json["projects"]["coffee-roaster"]["architect"]["build"]["options"]["browser"]
        == "src/main.ts"
    )
    assert "test" not in angular_json["projects"]["coffee-roaster"]["architect"]
    assert (
        angular_json["projects"]["coffee-roaster"]["architect"]["build"]["configurations"][
            "production"
        ]["optimization"]["styles"]["inlineCritical"]
        is False
    )
    assert (
        angular_json["projects"]["coffee-roaster"]["architect"]["build"]["configurations"][
            "production"
        ]["budgets"][0]["maximumWarning"]
        == "1.25MB"
    )
    assert "slcli webapp publish dist/coffee-roaster" in readme
    assert "six Nimble-based layout patterns" in readme
    assert "Node.js 24+ declared" in readme
    assert "standalone root bootstrap" in readme
    assert "warning budget tuned" in readme
    assert "omits a default test runner setup" in readme
    assert "Skipped npm install and npm run build" in result.output


def test_webapp_new_blank_uses_supported_nimble_api_shapes(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    runner = CliRunner()
    patch_keyring(monkeypatch)

    target = tmp_path / "nimble-api-check"
    result = runner.invoke(
        cli,
        [
            "webapp",
            "new",
            "nimble-api-check",
            "--directory",
            str(target),
            "--skip-install",
        ],
    )

    assert result.exit_code == 0

    assets_ts = (
        target / "src" / "app" / "features" / "assets" / "assets-page.component.ts"
    ).read_text(encoding="utf-8")
    app_module = (target / "src" / "app" / "app.module.ts").read_text(encoding="utf-8")
    datasets_ts = (
        target / "src" / "app" / "features" / "datasets" / "datasets-page.component.ts"
    ).read_text(encoding="utf-8")
    operations_ts = (
        target / "src" / "app" / "features" / "operations" / "operations-page.component.ts"
    ).read_text(encoding="utf-8")
    master_detail_ts = (
        target / "src" / "app" / "features" / "master-detail" / "master-detail-page.component.ts"
    ).read_text(encoding="utf-8")
    home_html = (
        target / "src" / "app" / "features" / "home" / "home-page.component.html"
    ).read_text(encoding="utf-8")
    datasets_html = (
        target / "src" / "app" / "features" / "datasets" / "datasets-page.component.html"
    ).read_text(encoding="utf-8")
    operations_html = (
        target / "src" / "app" / "features" / "operations" / "operations-page.component.html"
    ).read_text(encoding="utf-8")
    assets_html = (
        target / "src" / "app" / "features" / "assets" / "assets-page.component.html"
    ).read_text(encoding="utf-8")
    settings_html = (
        target / "src" / "app" / "features" / "settings" / "settings-page.component.html"
    ).read_text(encoding="utf-8")
    master_detail_html = (
        target / "src" / "app" / "features" / "master-detail" / "master-detail-page.component.html"
    ).read_text(encoding="utf-8")

    assert "TableFieldValue" in assets_ts
    assert "TableFieldValue" in datasets_ts
    assert "TableFieldValue" in operations_ts
    assert "queuePaneWidth" in operations_ts
    assert "startResize" in operations_ts
    assert "toggleDetailPane" in operations_ts
    assert "isDetailCollapsed" in operations_ts
    assert "MasterDetailChangeDetail" in master_detail_ts
    assert "filteredDevices" in master_detail_ts
    assert ".close();" in assets_ts
    assert ".hide();" not in assets_ts
    assert "selectedRecordIds[0]" in assets_ts
    assert "selectedRecordIds[0]" in operations_ts
    assert "TableRowSelectionEventDetail<" not in assets_ts
    assert "TableRowSelectionEventDetail<" not in operations_ts
    assert 'severity="information"' in home_html
    assert 'severity="information"' in datasets_html
    assert 'severity="information"' in operations_html
    assert 'severity="information"' in settings_html
    assert 'role="separator"' in operations_html
    assert "Show details" in operations_html
    assert "operations__splitter-toggle" in operations_html
    assert 'severity="info"' not in home_html
    assert 'severity="info"' not in datasets_html
    assert 'severity="success"' not in operations_html
    assert 'severity="success"' not in settings_html
    assert "NimbleChipModule" in app_module
    assert "nimble-checkbox" in settings_html
    assert "nimble-switch" in settings_html
    assert "nimble-text-area" in master_detail_html
    assert "ok-fv-master-detail-list" in master_detail_html
    assert "ok-fv-master-detail-list-item" in master_detail_html
    assert "nimble-text-field" in master_detail_html
    assert "Filter devices" in master_detail_html
    assert "nimble-chip" in assets_html
    assert "nimble-chip" in operations_html
    assert "nimble-chip" in master_detail_html
    assert "sl-pill" not in assets_html
    assert "sl-pill" not in operations_html
    assert "sl-pill" not in master_detail_html


def test_webapp_new_with_nimble_only_keeps_template_base_dependencies(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    runner = CliRunner()
    patch_keyring(monkeypatch)

    target = tmp_path / "nimble-only"
    result = runner.invoke(
        cli,
        [
            "webapp",
            "new",
            "nimble-only",
            "--directory",
            str(target),
            "--skip-install",
            "--with",
            "nimble",
        ],
    )

    assert result.exit_code == 0

    package_json = loads((target / "package.json").read_text(encoding="utf-8"))
    dependencies = package_json["dependencies"]

    assert dependencies["@ni/nimble-angular"] == "~33.4.4"
    assert "@ni/systemlink-clients-ts" not in dependencies
    assert "@ni/ok-angular" not in dependencies
    assert "@ni/ok-components" not in dependencies

    app_module = (target / "src" / "app" / "app.module.ts").read_text(encoding="utf-8")
    master_detail_html = (
        target / "src" / "app" / "features" / "master-detail" / "master-detail-page.component.html"
    ).read_text(encoding="utf-8")

    assert "@ni/ok-angular" not in app_module
    assert "OkFvMasterDetailListModule" not in app_module
    assert "ok-fv-master-detail-list" not in master_detail_html
    assert "nimble-select" in master_detail_html
    assert "nimble-list-option" in master_detail_html


def test_webapp_new_accepts_ok_feature_pack(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    runner = CliRunner()
    patch_keyring(monkeypatch)

    target = tmp_path / "ok-pack"
    result = runner.invoke(
        cli,
        [
            "webapp",
            "new",
            "ok-pack",
            "--directory",
            str(target),
            "--skip-install",
            "--with",
            "nimble,ok",
        ],
    )

    assert result.exit_code == 0
    package_json = loads((target / "package.json").read_text(encoding="utf-8"))

    assert package_json["dependencies"]["@ni/ok-angular"] == "2.5.0"
    assert "@ni/systemlink-clients-ts" not in package_json["dependencies"]


def test_webapp_new_dry_run_does_not_write_files(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    runner = CliRunner()
    patch_keyring(monkeypatch)

    target = tmp_path / "yield-dashboard"
    result = runner.invoke(
        cli,
        [
            "webapp",
            "new",
            "yield-dashboard",
            "--directory",
            str(target),
            "--dry-run",
        ],
    )

    assert result.exit_code == 0
    assert not target.exists()
    assert "Webapp generation dry run" in result.output
    assert "Package list:" in result.output
    assert "Config mutations:" in result.output
    assert "src/app/app.module.ts" in result.output


def test_template_relative_file_list_normalizes_windows_paths(monkeypatch: MonkeyPatch) -> None:
    class FakeWindowsFile:
        def __init__(self, raw_path: str) -> None:
            self._path = PureWindowsPath(raw_path)

        def is_file(self) -> bool:
            return True

        def relative_to(self, other: Path) -> PureWindowsPath:
            return self._path.relative_to(PureWindowsPath(str(other)))

    def fake_rglob(_self: Path, _pattern: str) -> list[FakeWindowsFile]:
        return [
            FakeWindowsFile("C:/template/src/app/app.module.ts"),
            FakeWindowsFile("C:/template/src/styles.scss"),
        ]

    monkeypatch.setattr(Path, "rglob", fake_rglob)

    assert webapp_bootstrap._template_relative_file_list(Path("C:/template")) == [
        "src/app/app.module.ts",
        "src/styles.scss",
    ]


def test_webapp_new_plugin_manager_writes_packaging_metadata(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    runner = CliRunner()
    patch_keyring(monkeypatch)

    target = tmp_path / "asset-browser"
    result = runner.invoke(
        cli,
        [
            "webapp",
            "new",
            "asset-browser",
            "--directory",
            str(target),
            "--skip-install",
            "--plugin-manager",
            "--publish-name",
            "Asset Browser",
            "--workspace",
            "Training - April 2026",
        ],
    )

    assert result.exit_code == 0
    assert (target / "icon.svg").exists()
    assert (target / "nipkg.config.json").exists()
    package_json = loads((target / "package.json").read_text(encoding="utf-8"))
    pack_config = loads((target / "nipkg.config.json").read_text(encoding="utf-8"))

    assert package_json["scripts"]["pack:webapp"] == "slcli webapp pack --config nipkg.config.json"
    assert pack_config["package"] == "asset-browser"
    assert pack_config["displayName"] == "Asset Browser"
    assert pack_config["buildDir"] == "dist/asset-browser"
    assert "npm run pack:webapp" in result.output


@pytest.mark.parametrize(
    ("template", "present_routes", "absent_routes", "expected_pattern"),
    [
        (
            "dashboard",
            ["path: ''", "path: 'datasets'", "path: 'assets'"],
            ["path: 'master-detail'", "path: 'operations'", "path: 'settings'"],
            "Search-first Nimble table toolbar",
        ),
        (
            "list-detail",
            ["path: ''", "path: 'assets'", "path: 'master-detail'"],
            ["path: 'datasets'", "path: 'operations'", "path: 'settings'"],
            "Master/detail split pane",
        ),
        (
            "admin",
            ["path: ''", "path: 'operations'", "path: 'settings'"],
            ["path: 'datasets'", "path: 'assets'", "path: 'master-detail'"],
            "Grouped settings form",
        ),
    ],
)
def test_webapp_new_named_templates_render_focused_navigation(
    tmp_path: Path,
    monkeypatch: MonkeyPatch,
    template: str,
    present_routes: List[str],
    absent_routes: List[str],
    expected_pattern: str,
) -> None:
    runner = CliRunner()
    patch_keyring(monkeypatch)

    target = tmp_path / template
    result = runner.invoke(
        cli,
        [
            "webapp",
            "new",
            template,
            "--directory",
            str(target),
            "--template",
            template,
            "--skip-install",
        ],
    )

    assert result.exit_code == 0

    routing = (target / "src" / "app" / "app-routing.module.ts").read_text(encoding="utf-8")
    shell = (target / "src" / "app" / "core" / "layout" / "app-shell.component.ts").read_text(
        encoding="utf-8"
    )
    home_data = (
        target / "src" / "app" / "core" / "systemlink" / "webapp-home-data.service.ts"
    ).read_text(encoding="utf-8")
    readme = (target / "README.md").read_text(encoding="utf-8")

    for route in present_routes:
        assert route in routing
    for route in absent_routes:
        assert route not in routing

    assert "readonly tabs: readonly ShellTab[]" in shell
    assert expected_pattern in home_data
    assert expected_pattern in readme


def test_resolve_webapp_template_directory_reports_selected_template_name(
    monkeypatch: MonkeyPatch,
) -> None:
    monkeypatch.setattr(webapp_bootstrap, "_webapp_templates_dir_candidates", lambda: [])

    with pytest.raises(FileNotFoundError) as exc_info:
        webapp_bootstrap._resolve_webapp_template_directory("angular", "dashboard")

    assert "selected template 'dashboard'" in str(exc_info.value)
    assert "source template 'blank'" in str(exc_info.value)


def test_webapp_new_runs_install_and_build(tmp_path: Path, monkeypatch: MonkeyPatch) -> None:
    runner = CliRunner()
    patch_keyring(monkeypatch)

    commands: List[List[str]] = []

    class Completed:
        def __init__(self) -> None:
            self.returncode = 0
            self.stdout = ""
            self.stderr = ""

    def fake_run(*args: Any, **kwargs: Any) -> Completed:
        commands.append(list(args[0]))
        assert kwargs["cwd"] == tmp_path / "build-check"
        return Completed()

    monkeypatch.setattr("slcli.webapp_bootstrap.subprocess.run", fake_run)

    result = runner.invoke(
        cli,
        ["webapp", "new", "build-check", "--directory", str(tmp_path / "build-check")],
    )

    assert result.exit_code == 0
    assert commands == [["npm", "install"], ["npm", "run", "build"]]
    assert "npm run build passed" in result.output


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
    import slcli.webapp_click

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
    monkeypatch.setattr(slcli.webapp_click, "get_workspace_id_with_fallback", lambda _: "ws1")
    monkeypatch.setattr(slcli.webapp_click, "get_workspace_map", lambda: {"ws1": "Default"})
    monkeypatch.setattr(slcli.webapp_click, "get_web_url", lambda: "https://web.example.test")

    result = runner.invoke(
        cli, ["webapp", "publish", str(folder), "--name", "NewApp", "--workspace", "Default"]
    )
    assert result.exit_code == 0
    assert "Published webapp content" in result.output or "Created webapp metadata" in result.output
    assert "Published URL" in result.output
    assert "https://web.example.test/webapps/app/Default/NewApp" in result.output


@pytest.mark.parametrize("source_kind", ["package", "folder"])
def test_webapp_publish_duplicate_name_shows_conflicting_webapp_details(
    tmp_path: Path, monkeypatch: MonkeyPatch, source_kind: str
) -> None:
    runner = CliRunner()
    patch_keyring(monkeypatch)
    import requests
    import slcli.webapp_click

    if source_kind == "package":
        source = tmp_path / "app.nipkg"
        source.write_bytes(b"test")
    else:
        source = tmp_path / "site"
        source.mkdir()
        (source / "index.html").write_text("hi")

    class MockPostResp:
        status_code = 409

        def json(self) -> Dict[str, Any]:
            return {
                "error": {
                    "message": "The webapp name is already in use.",
                }
            }

        def raise_for_status(self) -> None:
            return None

    class MockQueryResp:
        def json(self) -> Dict[str, Any]:
            return {
                "webapps": [
                    {
                        "id": "conflicting-webapp-id",
                        "name": "Existing App",
                        "workspace": "ws1",
                        "type": "WebVI",
                        "properties": {},
                    }
                ]
            }

        def raise_for_status(self) -> None:
            return None

    def mock_post(url: str, **kwargs: Any) -> Any:
        if url.endswith("/webapps"):
            return MockPostResp()
        return MockQueryResp()

    monkeypatch.setattr(requests, "post", mock_post)
    monkeypatch.setattr(slcli.webapp_click, "get_workspace_id_with_fallback", lambda _: "ws1")
    monkeypatch.setattr(slcli.webapp_click, "get_workspace_map", lambda: {"ws1": "Default"})
    monkeypatch.setattr(slcli.webapp_click, "get_web_url", lambda: "https://web.example.test")

    result = runner.invoke(
        cli, ["webapp", "publish", str(source), "--name", "Existing App", "--workspace", "Default"]
    )

    assert result.exit_code == ExitCodes.INVALID_INPUT
    assert "The webapp name is already in use." in result.output
    assert "Conflicting Webapp ID: conflicting-webapp-id" in result.output
    assert (
        "Conflicting Webapp URL: https://web.example.test/webapps/app/Default/Existing%20App"
        in result.output
    )


def test_webapp_publish_existing_id_includes_published_url(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    runner = CliRunner()
    patch_keyring(monkeypatch)
    import slcli.webapp_click

    package = tmp_path / "app.nipkg"
    package.write_bytes(b"test")

    import requests

    class MockGetResp:
        def json(self) -> Dict[str, Any]:
            return {
                "id": "existing-id",
                "name": "Existing App",
                "workspace": "ws1",
                "properties": {},
                "type": "WebVI",
            }

        def raise_for_status(self) -> None:
            return None

    class MockPutResp:
        text = ""

        @property
        def status_code(self) -> int:
            return 204

        def raise_for_status(self) -> None:
            return None

    monkeypatch.setattr(requests, "get", lambda *a, **k: MockGetResp())
    monkeypatch.setattr(requests, "put", lambda *a, **k: MockPutResp())
    monkeypatch.setattr(slcli.webapp_click, "get_workspace_map", lambda: {"ws1": "Default"})
    monkeypatch.setattr(slcli.webapp_click, "get_web_url", lambda: "https://web.example.test")

    result = runner.invoke(cli, ["webapp", "publish", str(package), "--id", "existing-id"])

    assert result.exit_code == 0
    assert "Published URL" in result.output
    assert "https://web.example.test/webapps/app/Default/Existing%20App" in result.output


def test_webapp_publish_existing_id_without_workspace_mapping_uses_content_url(
    tmp_path: Path, monkeypatch: MonkeyPatch
) -> None:
    runner = CliRunner()
    patch_keyring(monkeypatch)
    import slcli.webapp_click

    package = tmp_path / "app.nipkg"
    package.write_bytes(b"test")

    import requests

    class MockGetResp:
        def json(self) -> Dict[str, Any]:
            return {
                "id": "existing-id",
                "name": "Existing App",
                "workspace": "ws1",
                "properties": {},
                "type": "WebVI",
            }

        def raise_for_status(self) -> None:
            return None

    class MockPutResp:
        text = ""

        @property
        def status_code(self) -> int:
            return 204

        def raise_for_status(self) -> None:
            return None

    monkeypatch.setattr(requests, "get", lambda *a, **k: MockGetResp())
    monkeypatch.setattr(requests, "put", lambda *a, **k: MockPutResp())
    monkeypatch.setattr(slcli.webapp_click, "get_workspace_map", lambda: {})
    monkeypatch.setattr(
        slcli.webapp_click,
        "_get_webapp_base_url",
        lambda: "https://api.example.test/niapp/v1",
    )

    result = runner.invoke(cli, ["webapp", "publish", str(package), "--id", "existing-id"])

    assert result.exit_code == 0
    assert "Published URL" in result.output
    assert "https://api.example.test/niapp/v1/webapps/existing-id/content" in result.output
    assert "/webapps/app/Default/Existing%20App" not in result.output


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
