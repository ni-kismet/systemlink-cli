"""Hosted Angular webapp bootstrap commands and template generation helpers."""

import re
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import click

from .utils import (
    ExitCodes,
    format_success,
    handle_api_error,
    load_json_file,
    sanitize_filename,
    save_json_file,
)

_WEBAPP_FRAMEWORK_CHOICES = ("angular",)
_WEBAPP_TEMPLATE_CHOICES = ("blank", "dashboard", "list-detail", "admin")
_WEBAPP_PHASE1_SUPPORTED_TEMPLATES = frozenset({"blank"})
_WEBAPP_FEATURE_PACK_CHOICES = ("nimble", "spright", "clients")
_WEBAPP_ROUTING_CHOICES = ("hash", "path")
_WEBAPP_AUTH_CHOICES = ("same-origin", "api-key")
_WEBAPP_THEME_SYNC_CHOICES = ("auto", "off")
_WEBAPP_DEFAULT_FEATURE_PACKS = "nimble,clients"
_WEBAPP_SUPPORTED_ANGULAR_MAJOR = "20"
_WEBAPP_VERSION_MANIFEST: Dict[str, Dict[str, str]] = {
    "20": {
        "angular": "^20.3.0",
        "typescript": "~5.9.2",
        "zoneJs": "~0.15.0",
        "rxjs": "~7.8.0",
        "tslib": "^2.3.0",
        "angularBuilder": "^20.3.29",
        "jasmineCore": "~5.9.0",
        "karma": "~6.4.0",
        "karmaChromeLauncher": "~3.2.0",
        "karmaCoverage": "~2.2.0",
        "karmaJasmine": "~5.1.0",
        "karmaJasmineHtmlReporter": "~2.1.0",
        "nimbleAngular": "~33.2.0",
        "nimbleComponents": "~35.8.0",
        "okComponents": "1.6.0",
        "unitFormat": "^1.0.4",
        "systemlinkClients": "2.2.0",
        "sprightAngular": "latest",
    }
}


def _webapp_templates_dir_candidates() -> List[Path]:
    """Return candidate bundled template roots for source and frozen layouts."""
    candidates: List[Path] = []

    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "slcli" / "webapp_templates")

    if getattr(sys, "frozen", False):
        candidates.append(Path(sys.executable).resolve().parent / "slcli" / "webapp_templates")

    candidates.append(Path(__file__).resolve().parent / "webapp_templates")
    return candidates


def _resolve_webapp_template_directory(framework: str, template: str) -> Path:
    """Resolve a bundled webapp template directory from the current install layout."""
    for candidate_root in _webapp_templates_dir_candidates():
        candidate = candidate_root / framework / template
        if candidate.exists() and (candidate / "package.json").exists():
            return candidate

    raise FileNotFoundError(
        f"Bundled webapp template not found for framework '{framework}' and template '{template}'."
    )


def _slugify_webapp_name(value: str) -> str:
    """Return a safe package and project slug for a generated webapp."""
    slug = sanitize_filename(value)
    return slug or "systemlink-webapp"


def _default_publish_name(app_name: str) -> str:
    """Return a human-friendly publish name derived from the app name."""
    words = re.split(r"[._\s-]+", app_name.strip())
    rendered = " ".join(word.capitalize() for word in words if word)
    return rendered or "SystemLink WebApp"


def _parse_feature_pack_selection(selection: str) -> List[str]:
    """Parse and validate the requested feature packs."""
    requested = [item.strip().lower() for item in selection.split(",") if item.strip()]
    if not requested:
        click.echo("✗ --with must include at least one feature pack.", err=True)
        sys.exit(ExitCodes.INVALID_INPUT)

    invalid = [item for item in requested if item not in _WEBAPP_FEATURE_PACK_CHOICES]
    if invalid:
        click.echo(
            f"✗ Unsupported feature pack(s): {', '.join(sorted(set(invalid)))}. "
            f"Choose from: {', '.join(_WEBAPP_FEATURE_PACK_CHOICES)}.",
            err=True,
        )
        sys.exit(ExitCodes.INVALID_INPUT)

    unique_requested = list(dict.fromkeys(requested))
    if "nimble" not in unique_requested:
        click.echo(
            "✗ Angular webapp templates require the 'nimble' feature pack in --with.",
            err=True,
        )
        sys.exit(ExitCodes.INVALID_INPUT)

    return unique_requested


def _ensure_supported_webapp_template(template: str) -> None:
    """Reject templates that are planned but not yet shipped."""
    if template not in _WEBAPP_PHASE1_SUPPORTED_TEMPLATES:
        click.echo(
            "✗ Phase 1 currently supports only --template blank. "
            "Dashboard, list-detail, and admin templates are planned follow-on work.",
            err=True,
        )
        sys.exit(ExitCodes.INVALID_INPUT)


def _template_relative_file_list(template_dir: Path) -> List[str]:
    """Return the relative file list for a bundled template."""
    return sorted(
        str(path.relative_to(template_dir)) for path in template_dir.rglob("*") if path.is_file()
    )


def _render_template_tokens(template_text: str, replacements: Dict[str, str]) -> str:
    """Replace all template tokens in a text file."""
    rendered = template_text
    for key, value in replacements.items():
        rendered = rendered.replace(f"{{{{{key}}}}}", value)
    return rendered


def _ensure_generation_directory(directory: Path, force: bool) -> None:
    """Validate the target directory for webapp generation."""
    if directory.exists() and not directory.is_dir():
        click.echo(f"✗ Target path is not a directory: {directory}", err=True)
        sys.exit(ExitCodes.INVALID_INPUT)

    if directory.exists() and any(directory.iterdir()) and not force:
        click.echo(
            f"✗ Target directory is not empty: {directory}. Use --force to continue.",
            err=True,
        )
        sys.exit(ExitCodes.INVALID_INPUT)

    directory.mkdir(parents=True, exist_ok=True)


def _publish_command_for_directory(
    project_name: str, publish_name: str, workspace_name: str
) -> str:
    """Return the default publish command for a generated webapp."""
    command = f'slcli webapp publish dist/{project_name} --name "{publish_name}"'
    if workspace_name:
        command += f' --workspace "{workspace_name}"'
    return command


def _build_webapp_template_replacements(
    app_name: str,
    project_name: str,
    publish_name: str,
    workspace_name: str,
    routing_mode: str,
    auth_mode: str,
    theme_sync: str,
) -> Dict[str, str]:
    """Build the token replacement map for the bundled template files."""
    return {
        "APP_NAME": app_name,
        "PROJECT_NAME": project_name,
        "PUBLISH_NAME": publish_name,
        "WORKSPACE_NAME": workspace_name or "Default",
        "WORKSPACE_NOTE": workspace_name or "Set a workspace when you publish the app.",
        "ROUTER_USE_HASH": "true" if routing_mode == "hash" else "false",
        "AUTH_MODE": auth_mode,
        "THEME_SYNC_ENABLED": "true" if theme_sync == "auto" else "false",
        "PUBLISH_COMMAND": _publish_command_for_directory(
            project_name, publish_name, workspace_name
        ),
    }


def _write_rendered_template_tree(
    template_dir: Path, target_dir: Path, replacements: Dict[str, str]
) -> None:
    """Copy a bundled template into the target directory with token replacement."""
    for source_path in template_dir.rglob("*"):
        if source_path.is_dir():
            continue

        relative_path = source_path.relative_to(template_dir)
        target_path = target_dir / relative_path
        target_path.parent.mkdir(parents=True, exist_ok=True)

        rendered_text = _render_template_tokens(
            source_path.read_text(encoding="utf-8"), replacements
        )
        target_path.write_text(rendered_text, encoding="utf-8")


def _base_angular_dependencies(angular_major: str) -> Dict[str, str]:
    """Return the Angular runtime dependency set for a generated app."""
    manifest = _WEBAPP_VERSION_MANIFEST[angular_major]
    angular_version = manifest["angular"]
    return {
        "@angular/animations": angular_version,
        "@angular/common": angular_version,
        "@angular/compiler": angular_version,
        "@angular/core": angular_version,
        "@angular/forms": angular_version,
        "@angular/platform-browser": angular_version,
        "@angular/platform-browser-dynamic": angular_version,
        "@angular/router": angular_version,
        "@ni/ok-components": manifest["okComponents"],
        "rxjs": manifest["rxjs"],
        "tslib": manifest["tslib"],
        "zone.js": manifest["zoneJs"],
    }


def _base_angular_dev_dependencies(angular_major: str) -> Dict[str, str]:
    """Return the Angular dev dependency set for a generated app."""
    manifest = _WEBAPP_VERSION_MANIFEST[angular_major]
    angular_version = manifest["angular"]
    return {
        "@angular-devkit/build-angular": manifest["angularBuilder"],
        "@angular/cli": angular_version,
        "@angular/compiler-cli": angular_version,
        "@angular/localize": angular_version,
        "@types/jasmine": "~5.1.0",
        "jasmine-core": manifest["jasmineCore"],
        "karma": manifest["karma"],
        "karma-chrome-launcher": manifest["karmaChromeLauncher"],
        "karma-coverage": manifest["karmaCoverage"],
        "karma-jasmine": manifest["karmaJasmine"],
        "karma-jasmine-html-reporter": manifest["karmaJasmineHtmlReporter"],
        "typescript": manifest["typescript"],
    }


def _feature_pack_dependencies(feature_packs: List[str], angular_major: str) -> Dict[str, str]:
    """Return dependency versions for the selected feature packs."""
    manifest = _WEBAPP_VERSION_MANIFEST[angular_major]
    dependencies: Dict[str, str] = {}
    if "nimble" in feature_packs:
        dependencies.update(
            {
                "@ni/nimble-angular": manifest["nimbleAngular"],
                "@ni/nimble-components": manifest["nimbleComponents"],
                "@ni/unit-format": manifest["unitFormat"],
            }
        )
    if "clients" in feature_packs:
        dependencies["@ni/systemlink-clients-ts"] = manifest["systemlinkClients"]
    if "spright" in feature_packs:
        dependencies["@ni/spright-angular"] = manifest["sprightAngular"]
    return dependencies


def _customize_generated_package_json(
    package_json_path: Path,
    feature_packs: List[str],
    angular_major: str,
    project_name: str,
    publish_name: str,
    workspace_name: str,
    plugin_manager: bool,
) -> Dict[str, Any]:
    """Apply package versions and scripts to the generated package.json."""
    package_json = load_json_file(str(package_json_path))
    dependencies = _base_angular_dependencies(angular_major)
    dependencies.update(_feature_pack_dependencies(feature_packs, angular_major))
    dev_dependencies = _base_angular_dev_dependencies(angular_major)

    package_json["name"] = project_name
    package_json["description"] = f"{publish_name} hosted Angular webapp for SystemLink."
    package_json["dependencies"] = dependencies
    package_json["devDependencies"] = dev_dependencies
    package_json["scripts"] = {
        "start": "ng serve --host 0.0.0.0",
        "build": "ng build",
        "test": "ng test --watch=false --browsers=ChromeHeadless",
        "publish:webapp": _publish_command_for_directory(
            project_name, publish_name, workspace_name
        ),
    }
    if plugin_manager:
        package_json["scripts"]["pack:webapp"] = "slcli webapp pack --config nipkg.config.json"

    save_json_file(package_json, str(package_json_path))
    return package_json


def _render_plugin_manager_icon(publish_name: str) -> str:
    """Return a simple SVG placeholder for Plugin Manager packaging."""
    safe_label = publish_name.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 128 128" role="img" aria-label="{safe_label}">\n'
        '  <rect width="128" height="128" rx="24" fill="#0f172a" />\n'
        '  <rect x="18" y="18" width="92" height="92" rx="18" fill="#2563eb" opacity="0.18" />\n'
        '  <path d="M40 44h48v8H40zm0 16h48v8H40zm0 16h30v8H40z" fill="#f8fafc" />\n'
        f'  <text x="64" y="108" text-anchor="middle" fill="#bfdbfe" font-size="10" font-family="Source Sans Pro, Arial, sans-serif">{safe_label}</text>\n'
        "</svg>\n"
    )


def _initialize_plugin_manager_files(directory: Path, project_name: str, publish_name: str) -> None:
    """Generate Plugin Manager starter files for a new webapp."""
    icon_path = directory / "icon.svg"
    icon_path.write_text(_render_plugin_manager_icon(publish_name), encoding="utf-8")

    config = {
        "package": project_name,
        "version": "0.1.0",
        "displayName": publish_name,
        "description": f"{publish_name} hosted Angular webapp for SystemLink.",
        "section": "Web Apps",
        "maintainer": "Your Team <team@example.com>",
        "homepage": "",
        "license": "MIT",
        "xbPlugin": "webapp",
        "slPluginManagerTags": "systemlink,webapp,angular",
        "slPluginManagerMinServerVersion": "",
        "iconFile": icon_path.name,
        "buildDir": f"dist/{project_name}",
        "buildCommand": "npm run build",
    }
    save_json_file(config, str(directory / "nipkg.config.json"))


def _run_webapp_local_command(directory: Path, command: List[str], label: str) -> None:
    """Run a local process for webapp generation and surface actionable failures."""
    click.echo(f"→ {label}")
    try:
        result = subprocess.run(
            command,
            cwd=directory,
            capture_output=True,
            text=True,
            check=False,
        )
    except FileNotFoundError as exc:
        click.echo(f"✗ {label} failed: {exc}", err=True)
        click.echo("Generated files were preserved for inspection.", err=True)
        sys.exit(ExitCodes.GENERAL_ERROR)

    if result.returncode != 0:
        click.echo(f"✗ {label} failed in {directory}", err=True)
        if result.stdout.strip():
            click.echo(result.stdout.rstrip(), err=True)
        if result.stderr.strip():
            click.echo(result.stderr.rstrip(), err=True)
        click.echo("Generated files were preserved for inspection.", err=True)
        sys.exit(ExitCodes.GENERAL_ERROR)


def _emit_webapp_new_dry_run(
    framework: str,
    template: str,
    directory: Path,
    feature_packs: List[str],
    package_json: Dict[str, Any],
    plugin_manager: bool,
) -> None:
    """Print the generation plan without writing files."""
    click.echo("Webapp generation dry run")
    click.echo(f"  Framework: {framework}")
    click.echo(f"  Template: {template}")
    click.echo(f"  Directory: {directory}")
    click.echo("  File plan:")
    template_dir = _resolve_webapp_template_directory(framework, template)
    for relative_path in _template_relative_file_list(template_dir):
        click.echo(f"    - {relative_path}")
    if plugin_manager:
        click.echo("    - icon.svg")
        click.echo("    - nipkg.config.json")
    click.echo("  Package list:")
    for package_name, version in sorted(package_json["dependencies"].items()):
        click.echo(f"    - {package_name}@{version}")
    click.echo("  Config mutations:")
    click.echo(f"    - feature packs: {', '.join(feature_packs)}")
    click.echo("    - APP_BASE_HREF provider with no <base> tag")
    click.echo("    - Angular localize polyfills for build and test")
    click.echo("    - Nimble fonts in src/styles.scss")
    click.echo("    - legacy Angular builder with inlineCritical disabled")
    click.echo("    - hash routing enabled unless --routing path is requested")


def _generate_new_webapp(
    app_name: str,
    framework: str,
    template: str,
    directory: Path,
    workspace_name: str,
    publish_name: str,
    feature_pack_selection: str,
    plugin_manager: bool,
    skip_install: bool,
    dry_run: bool,
    angular_version: str,
    routing_mode: str,
    auth_mode: str,
    theme_sync: str,
    force: bool,
) -> None:
    """Generate a hosted, buildable SystemLink Angular app from a bundled template."""
    if framework != "angular":
        click.echo("✗ Phase 1 currently supports only --framework angular.", err=True)
        sys.exit(ExitCodes.INVALID_INPUT)

    if angular_version != _WEBAPP_SUPPORTED_ANGULAR_MAJOR:
        click.echo(
            f"✗ Phase 1 currently supports only --angular-version {_WEBAPP_SUPPORTED_ANGULAR_MAJOR}.",
            err=True,
        )
        sys.exit(ExitCodes.INVALID_INPUT)

    _ensure_supported_webapp_template(template)
    feature_packs = _parse_feature_pack_selection(feature_pack_selection)

    project_name = _slugify_webapp_name(app_name)
    target_dir = directory.resolve()
    publish_display_name = publish_name or _default_publish_name(app_name)
    template_dir = _resolve_webapp_template_directory(framework, template)
    replacements = _build_webapp_template_replacements(
        app_name=app_name,
        project_name=project_name,
        publish_name=publish_display_name,
        workspace_name=workspace_name,
        routing_mode=routing_mode,
        auth_mode=auth_mode,
        theme_sync=theme_sync,
    )

    package_json_preview = load_json_file(str(template_dir / "package.json"))
    package_json_preview["dependencies"] = _base_angular_dependencies(angular_version)
    package_json_preview["dependencies"].update(
        _feature_pack_dependencies(feature_packs, angular_version)
    )

    if dry_run:
        _emit_webapp_new_dry_run(
            framework=framework,
            template=template,
            directory=target_dir,
            feature_packs=feature_packs,
            package_json=package_json_preview,
            plugin_manager=plugin_manager,
        )
        return

    _ensure_generation_directory(target_dir, force)
    _write_rendered_template_tree(template_dir, target_dir, replacements)
    _customize_generated_package_json(
        package_json_path=target_dir / "package.json",
        feature_packs=feature_packs,
        angular_major=angular_version,
        project_name=project_name,
        publish_name=publish_display_name,
        workspace_name=workspace_name,
        plugin_manager=plugin_manager,
    )
    if plugin_manager:
        _initialize_plugin_manager_files(target_dir, project_name, publish_display_name)

    if not skip_install:
        _run_webapp_local_command(target_dir, ["npm", "install"], "npm install")
        _run_webapp_local_command(target_dir, ["npm", "run", "build"], "npm run build")

    result_data: Dict[str, Any] = {
        "Directory": str(target_dir),
        "Framework": framework,
        "Template": template,
        "Publish command": _publish_command_for_directory(
            project_name, publish_display_name, workspace_name
        ),
    }
    if skip_install:
        result_data["Validation"] = "Skipped npm install and npm run build"
    else:
        result_data["Validation"] = "npm run build passed"
    if plugin_manager:
        result_data["Pack command"] = "npm run pack:webapp"

    format_success("Created SystemLink Angular webapp", result_data)


def register_webapp_bootstrap_commands(webapp: Any) -> None:
    """Register high-level hosted webapp bootstrap commands."""

    @webapp.command(name="new")
    @click.argument("app_name", type=str)
    @click.option(
        "--framework",
        type=click.Choice(list(_WEBAPP_FRAMEWORK_CHOICES)),
        default="angular",
        show_default=True,
        help="Framework starter to generate.",
    )
    @click.option(
        "--template",
        type=click.Choice(list(_WEBAPP_TEMPLATE_CHOICES)),
        default="blank",
        show_default=True,
        help="Starter template contract.",
    )
    @click.option(
        "--directory",
        type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
        default=None,
        help="Target directory. Defaults to <app-name>.",
    )
    @click.option("--workspace", "workspace_name", default="", help="Default workspace name.")
    @click.option(
        "--publish-name",
        "publish_name",
        default="",
        help="Friendly publish name for scripts and defaults.",
    )
    @click.option(
        "--with",
        "feature_pack_selection",
        default=_WEBAPP_DEFAULT_FEATURE_PACKS,
        show_default=True,
        help="Comma-separated feature packs.",
    )
    @click.option(
        "--plugin-manager",
        is_flag=True,
        help="Generate Plugin Manager packaging metadata and icon placeholder.",
    )
    @click.option(
        "--skip-install", is_flag=True, help="Generate files without running npm install."
    )
    @click.option(
        "--skip-git", is_flag=True, help="Reserved for future git initialization support."
    )
    @click.option("--dry-run", is_flag=True, help="Show the file and package plan without writing.")
    @click.option("--defaults", is_flag=True, help="Use opinionated non-interactive defaults.")
    @click.option("--force", is_flag=True, help="Allow generation into a non-empty directory.")
    @click.option(
        "--angular-version",
        default=_WEBAPP_SUPPORTED_ANGULAR_MAJOR,
        show_default=False,
        hidden=True,
        help="Advanced: Angular major version for scaffold testing.",
    )
    @click.option(
        "--routing",
        "routing_mode",
        type=click.Choice(list(_WEBAPP_ROUTING_CHOICES)),
        default="hash",
        show_default=True,
        help="Router mode for hosted navigation.",
    )
    @click.option(
        "--style",
        type=click.Choice(["scss"]),
        default="scss",
        show_default=True,
        help="Stylesheet format for the generated app.",
    )
    @click.option(
        "--auth",
        "auth_mode",
        type=click.Choice(list(_WEBAPP_AUTH_CHOICES)),
        default="same-origin",
        show_default=True,
        help="Sample auth wiring for generated services.",
    )
    @click.option(
        "--theme-sync",
        type=click.Choice(list(_WEBAPP_THEME_SYNC_CHOICES)),
        default="auto",
        show_default=True,
        help="Theme synchronization with the host shell.",
    )
    def new_webapp(
        app_name: str,
        framework: str,
        template: str,
        directory: Optional[Path],
        workspace_name: str,
        publish_name: str,
        feature_pack_selection: str,
        plugin_manager: bool,
        skip_install: bool,
        skip_git: bool,
        dry_run: bool,
        defaults: bool,
        force: bool,
        angular_version: str,
        routing_mode: str,
        style: str,
        auth_mode: str,
        theme_sync: str,
    ) -> None:
        """Generate a host-ready SystemLink Angular webapp in one pass."""
        del skip_git
        del defaults
        if style != "scss":
            click.echo("✗ Phase 1 currently supports only --style scss.", err=True)
            sys.exit(ExitCodes.INVALID_INPUT)

        target_directory = directory if directory is not None else Path(app_name)

        try:
            _generate_new_webapp(
                app_name=app_name,
                framework=framework,
                template=template,
                directory=target_directory,
                workspace_name=workspace_name,
                publish_name=publish_name,
                feature_pack_selection=feature_pack_selection,
                plugin_manager=plugin_manager,
                skip_install=skip_install,
                dry_run=dry_run,
                angular_version=angular_version,
                routing_mode=routing_mode,
                auth_mode=auth_mode,
                theme_sync=theme_sync,
                force=force,
            )
        except SystemExit:
            raise
        except Exception as exc:
            handle_api_error(exc)
