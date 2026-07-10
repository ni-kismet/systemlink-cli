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
_WEBAPP_FEATURE_PACK_CHOICES = ("nimble", "spright", "clients", "ok")
_WEBAPP_ROUTING_CHOICES = ("hash", "path")
_WEBAPP_AUTH_CHOICES = ("same-origin", "api-key")
_WEBAPP_THEME_SYNC_CHOICES = ("auto", "off")
_WEBAPP_DEFAULT_FEATURE_PACKS = "nimble,clients,ok"
_WEBAPP_SUPPORTED_ANGULAR_MAJOR = "20"
_WEBAPP_VERSION_MANIFEST: Dict[str, Dict[str, str]] = {
    "20": {
        "angular": "^20.3.26",
        "typescript": "~5.9.3",
        "zoneJs": "~0.15.1",
        "rxjs": "~7.8.2",
        "tslib": "^2.8.1",
        "angularBuild": "^20.3.32",
        "nimbleAngular": "~33.4.4",
        "nimbleComponents": "~35.12.3",
        "okAngular": "2.5.0",
        "unitFormat": "^1.0.5",
        "systemlinkClients": "3.0.2",
        "sprightAngular": "9.5.5",
        "nodeEngine": ">=24",
    }
}
_WEBAPP_TEMPLATE_PROFILES: Dict[str, Dict[str, Any]] = {
    "blank": {
        "source_template": "blank",
        "tabs": [
            {"id": "overview", "label": "Overview", "route": "/"},
            {"id": "datasets", "label": "Data Table", "route": "/datasets"},
            {"id": "assets", "label": "Drawer Detail", "route": "/assets"},
            {"id": "master-detail", "label": "Master Detail", "route": "/master-detail"},
            {"id": "operations", "label": "Operations", "route": "/operations"},
            {"id": "settings", "label": "Settings", "route": "/settings"},
        ],
        "pattern_summary": "six Nimble-based layout patterns ready to replace with real SystemLink resource calls",
        "patterns": [
            "Route-level navigation with Nimble anchor tabs",
            "Search-first Nimble table toolbar with concise Search <items> copy",
            "Drawer-based detail inspection from a primary dataset",
            "Master/detail split pane with read-only detail fields until edit mode",
            "Split operations workspace with manual refresh and a confirm dialog",
            "Grouped settings form with theme-aware sections and readonly hosted facts",
        ],
        "readme_patterns": [
            "Route-level navigation with Nimble anchor tabs",
            "Search-first Nimble table toolbar with concise Search <items> copy",
            "Drawer-based detail inspection from a primary dataset",
            "Master/detail split pane with read-only detail fields until edit mode",
            "Split operations workspace with manual refresh and a confirm dialog",
            "Grouped settings form with theme-aware sections and readonly hosted facts",
        ],
        "readiness_message": "This starter keeps hosted routing, Nimble tokens, and sample control text aligned to current Stratus guidance.",
    },
    "dashboard": {
        "source_template": "blank",
        "tabs": [
            {"id": "overview", "label": "Overview", "route": "/"},
            {"id": "datasets", "label": "Data Table", "route": "/datasets"},
            {"id": "assets", "label": "Drawer Detail", "route": "/assets"},
        ],
        "pattern_summary": "three dashboard-oriented starter routes ready for metrics, tables, and record drill-down",
        "patterns": [
            "Route-level navigation with Nimble anchor tabs",
            "Search-first Nimble table toolbar with concise Search <items> copy",
            "Drawer-based detail inspection from a primary dataset",
        ],
        "readme_patterns": [
            "Route-level navigation with Nimble anchor tabs",
            "Search-first Nimble table toolbar with concise Search <items> copy",
            "Drawer-based detail inspection from a primary dataset",
        ],
        "readiness_message": "This dashboard starter keeps hosted routing, Nimble tokens, and table-first control text aligned to current Stratus guidance.",
    },
    "list-detail": {
        "source_template": "blank",
        "tabs": [
            {"id": "overview", "label": "Overview", "route": "/"},
            {"id": "assets", "label": "Drawer Detail", "route": "/assets"},
            {"id": "master-detail", "label": "Master Detail", "route": "/master-detail"},
        ],
        "pattern_summary": "three list-and-detail starter routes ready for inspection, selection, and edit workflows",
        "patterns": [
            "Route-level navigation with Nimble anchor tabs",
            "Drawer-based detail inspection from a primary dataset",
            "Master/detail split pane with read-only detail fields until edit mode",
        ],
        "readme_patterns": [
            "Route-level navigation with Nimble anchor tabs",
            "Drawer-based detail inspection from a primary dataset",
            "Master/detail split pane with read-only detail fields until edit mode",
        ],
        "readiness_message": "This list-detail starter keeps hosted routing, Nimble tokens, and record-inspection flows aligned to current Stratus guidance.",
    },
    "admin": {
        "source_template": "blank",
        "tabs": [
            {"id": "overview", "label": "Overview", "route": "/"},
            {"id": "operations", "label": "Operations", "route": "/operations"},
            {"id": "settings", "label": "Settings", "route": "/settings"},
        ],
        "pattern_summary": "three admin-focused starter routes ready for queue management and configuration workflows",
        "patterns": [
            "Route-level navigation with Nimble anchor tabs",
            "Split operations workspace with manual refresh and a confirm dialog",
            "Grouped settings form with theme-aware sections and readonly hosted facts",
        ],
        "readme_patterns": [
            "Route-level navigation with Nimble anchor tabs",
            "Split operations workspace with manual refresh and a confirm dialog",
            "Grouped settings form with theme-aware sections and readonly hosted facts",
        ],
        "readiness_message": "This admin starter keeps hosted routing, Nimble tokens, and configuration-first workflows aligned to current Stratus guidance.",
    },
}


def _webapp_template_profile(template: str) -> Dict[str, Any]:
    """Return the generation profile for a named template."""
    return _WEBAPP_TEMPLATE_PROFILES[template]


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
    source_template = _webapp_template_profile(template)["source_template"]
    for candidate_root in _webapp_templates_dir_candidates():
        candidate = candidate_root / framework / source_template
        if candidate.exists() and (candidate / "package.json").exists():
            return candidate

    raise FileNotFoundError(
        "Bundled webapp template not found for framework "
        f"'{framework}', selected template '{template}', and source template "
        f"'{source_template}'."
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


def _template_relative_file_list(template_dir: Path) -> List[str]:
    """Return the relative file list for a bundled template."""
    return sorted(
        path.relative_to(template_dir).as_posix()
        for path in template_dir.rglob("*")
        if path.is_file()
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


def _build_webapp_routing_module(template: str, routing_mode: str) -> str:
    """Render app-routing.module.ts for the selected template."""
    tabs = _webapp_template_profile(template)["tabs"]
    import_map = {
        "/": "HomePageComponent",
        "/datasets": "DatasetsPageComponent",
        "/assets": "AssetsPageComponent",
        "/master-detail": "MasterDetailPageComponent",
        "/operations": "OperationsPageComponent",
        "/settings": "SettingsPageComponent",
    }
    file_map = {
        "/": "./features/home/home-page.component",
        "/datasets": "./features/datasets/datasets-page.component",
        "/assets": "./features/assets/assets-page.component",
        "/master-detail": "./features/master-detail/master-detail-page.component",
        "/operations": "./features/operations/operations-page.component",
        "/settings": "./features/settings/settings-page.component",
    }

    imports = [
        "import { NgModule } from '@angular/core';",
        "import { RouterModule, Routes } from '@angular/router';",
        "",
    ]
    for tab in tabs:
        route = tab["route"]
        component_name = import_map[route]
        imports.append(f"import {{ {component_name} }} from '{file_map[route]}';")

    route_entries: List[str] = []
    for tab in tabs:
        path_value = "" if tab["route"] == "/" else tab["route"].lstrip("/")
        component_name = import_map[tab["route"]]
        route_entries.extend(
            [
                "  {",
                f"    path: '{path_value}',",
                f"    component: {component_name},",
                "  },",
            ]
        )

    lines = imports + [
        "",
        "const routes: Routes = [",
        *route_entries,
        "];",
        "",
        "@NgModule({",
        f"  imports: [RouterModule.forRoot(routes, {{ useHash: {'true' if routing_mode == 'hash' else 'false'} }})],",
        "  exports: [RouterModule],",
        "})",
        "export class AppRoutingModule {}",
        "",
    ]
    return "\n".join(lines)


def _build_webapp_shell_component(template: str) -> str:
    """Render the app shell tabs for the selected template."""
    tab_lines = [
        f"    {{ id: '{tab['id']}', label: '{tab['label']}', route: '{tab['route']}' }},"
        for tab in _webapp_template_profile(template)["tabs"]
    ]

    return "\n".join(
        [
            "import { CommonModule } from '@angular/common';",
            "import { Component } from '@angular/core';",
            "import { NavigationEnd, Router, RouterModule } from '@angular/router';",
            "",
            "import { NimbleAnchorTabModule, NimbleAnchorTabsModule } from '@ni/nimble-angular';",
            "import { filter } from 'rxjs';",
            "",
            "import { SystemLinkContextService } from '../systemlink/systemlink-context.service';",
            "",
            "interface ShellTab {",
            "  id: string;",
            "  label: string;",
            "  route: string;",
            "}",
            "",
            "@Component({",
            "  selector: 'sl-app-shell',",
            "  standalone: true,",
            "  imports: [",
            "    CommonModule,",
            "    RouterModule,",
            "    NimbleAnchorTabsModule,",
            "    NimbleAnchorTabModule,",
            "  ],",
            "  templateUrl: './app-shell.component.html',",
            "  styleUrl: './app-shell.component.scss',",
            "})",
            "export class AppShellComponent {",
            "  readonly tabs: readonly ShellTab[] = [",
            *tab_lines,
            "  ];",
            "",
            "  activeTabId = 'overview';",
            "",
            "  constructor(",
            "    public readonly context: SystemLinkContextService,",
            "    router: Router,",
            "  ) {",
            "    this.updateActiveTab(router.url);",
            "    router.events",
            "      .pipe(filter((event): event is NavigationEnd => event instanceof NavigationEnd))",
            "      .subscribe((event: NavigationEnd) => {",
            "        this.updateActiveTab(event.urlAfterRedirects);",
            "      });",
            "  }",
            "",
            "  private updateActiveTab(url: string): void {",
            "    const path = url.split('?')[0] || '/';",
            "    const active = this.tabs.find((tab: ShellTab) => {",
            "      if (tab.route === '/') {",
            "        return path === '/';",
            "      }",
            "",
            "      return path === tab.route || path.startsWith(`${tab.route}/`);",
            "    });",
            "",
            "    this.activeTabId = active?.id ?? 'overview';",
            "  }",
            "}",
            "",
        ]
    )


def _quoted_typescript_list(values: List[str]) -> str:
    """Return a comma-separated TypeScript string literal list."""
    return ",\n        ".join(f"'{value}'" for value in values)


def _build_webapp_home_data_service(template: str) -> str:
    """Render the home data service for the selected template."""
    profile = _webapp_template_profile(template)
    patterns = _quoted_typescript_list(profile["patterns"])
    return "\n".join(
        [
            "import { Injectable } from '@angular/core';",
            "",
            "import { SystemLinkContextService } from './systemlink-context.service';",
            "",
            "export interface HomeMetric {",
            "  label: string;",
            "  value: string;",
            "  detail: string;",
            "  tone: 'info' | 'success' | 'warning';",
            "}",
            "",
            "export interface HomePageModel {",
            "  metrics: HomeMetric[];",
            "  patterns: string[];",
            "  nextSteps: string[];",
            "  readinessMessage: string;",
            "}",
            "",
            "@Injectable({ providedIn: 'root' })",
            "export class WebappHomeDataService {",
            "  constructor(private readonly context: SystemLinkContextService) {}",
            "",
            "  async load(): Promise<HomePageModel> {",
            "    return {",
            "      metrics: [",
            "        {",
            "          label: 'Hosted origin',",
            "          value: this.context.origin,",
            "          detail: 'Root future SDK clients and direct fetch calls here.',",
            "          tone: 'info',",
            "        },",
            "        {",
            "          label: 'Auth mode',",
            "          value: this.context.authMode,",
            "          detail: 'Swap with --auth when you need API-key-driven development flows.',",
            "          tone: 'warning',",
            "        },",
            "        {",
            "          label: 'Workspace',",
            "          value: this.context.workspaceName,",
            "          detail: 'Publishing help text and starter docs are already aligned to this workspace.',",
            "          tone: 'success',",
            "        },",
            "      ],",
            "      patterns: [",
            f"        {patterns},",
            "      ],",
            "      nextSteps: [",
            "        'Replace one sample page with a real SystemLink query before adding more routes.',",
            "        'Use Nimble buttons for actions and Nimble anchors or route tabs for navigation.',",
            "        'Preserve hosted query parameters if you later add cross-app breadcrumbs.',",
            "      ],",
            f"      readinessMessage: '{profile['readiness_message']}',",
            "    };",
            "  }",
            "}",
            "",
        ]
    )


def _build_webapp_readme(
    template: str,
    publish_name: str,
    app_name: str,
    routing_mode: str,
    publish_command: str,
    workspace_name: str,
    auth_mode: str,
) -> str:
    """Render README.md for the selected template."""
    profile = _webapp_template_profile(template)
    routed_features = [tab["route"].lstrip("/") or "home" for tab in profile["tabs"]]
    readme_patterns = "\n".join(f"- {item}" for item in profile["readme_patterns"])
    return f"""# {publish_name}

This app was generated by `slcli webapp new {app_name}` as a hosted Angular 20 starter for SystemLink.

## What You Start With

- Node.js 24+ declared in `package.json#engines`
- Angular 20 with standalone root bootstrap and NgModule-managed feature declarations
- `@ni/nimble-angular` wired into the standalone root plus `AppModule`
- `nimble-theme-provider` at the application root
- `APP_BASE_HREF` provided without a `<base>` tag in `src/index.html`
- `useHash: {'true' if routing_mode == 'hash' else 'false'}` routing for hosted navigation
- `@angular/localize/init` configured for the build polyfill path
- Nimble fonts imported in `src/styles.scss`
- modern Angular application builders configured for the hosted scaffold
- initial bundle warning budget tuned for the included starter shell
- shared loading, error, and empty states
- SystemLink context and theme sync services under `src/app/core/systemlink/`
- {profile['pattern_summary']}

## Enabled Starter Routes

{', '.join(routed_features)}

## Local Development

```bash
npm install
npm run build
```

The generated scaffold intentionally omits a default test runner setup so `npm install`
does not pull in the deprecated Karma/Jasmine stack. Add your preferred test tooling when
you start writing app-specific tests.

## Publish To SystemLink

```bash
{publish_command}
```

Current workspace default: `{workspace_name or 'Default'}`

## Hosted Validation Notes

- Keep `APP_BASE_HREF` in `src/app/app.module.ts`
- Keep `useHash: {'true' if routing_mode == 'hash' else 'false'}` in `src/app/app-routing.module.ts`
- Do not add a `<base>` tag to `src/index.html`
- Keep `inlineCritical: false` in `angular.json`
- Use `window.location.origin` when adding more SystemLink service clients

## Sample Service Wiring

The generated `SystemLinkContextService` centralizes:

- the hosted origin (`window.location.origin`)
- auth mode (`{auth_mode}`)
- request defaults for same-origin cookies or API-key headers

## Included Patterns

{readme_patterns}

## Pattern Guardrails

- Use Nimble tokens for custom fonts and colors. Import Nimble fonts once in `src/styles.scss`, then derive any custom styling from token-backed CSS variables.
- Use `nimble-button` for actions and Nimble anchors or route tabs for navigation. Do not style regular buttons to imitate Nimble buttons.
- Use concise `Search <items>` placeholders for toolbar text filters, and prefer `readonly` over `disabled` for non-editable text content.
- Add refresh controls only to views with data that changes outside the current session. Static overview and settings routes should stay manual.
- If you add breadcrumbs for cross-app navigation, preserve their hierarchy through query parameters instead of rewriting breadcrumb state during same-app tab switches.

Use these routes as starting points and replace one of them with a real SystemLink resource flow before broadening the app shell.
"""


def _apply_selected_webapp_template(
    target_dir: Path,
    template: str,
    app_name: str,
    publish_name: str,
    workspace_name: str,
    routing_mode: str,
    auth_mode: str,
) -> None:
    """Rewrite the generated starter entrypoints for the selected template."""
    app_dir = target_dir / "src" / "app"
    (app_dir / "app-routing.module.ts").write_text(
        _build_webapp_routing_module(template, routing_mode),
        encoding="utf-8",
    )
    (app_dir / "core" / "layout" / "app-shell.component.ts").write_text(
        _build_webapp_shell_component(template),
        encoding="utf-8",
    )
    (app_dir / "core" / "systemlink" / "webapp-home-data.service.ts").write_text(
        _build_webapp_home_data_service(template),
        encoding="utf-8",
    )
    (target_dir / "README.md").write_text(
        _build_webapp_readme(
            template=template,
            publish_name=publish_name,
            app_name=app_name,
            routing_mode=routing_mode,
            publish_command=_publish_command_for_directory(
                _slugify_webapp_name(app_name), publish_name, workspace_name
            ),
            workspace_name=workspace_name,
            auth_mode=auth_mode,
        ),
        encoding="utf-8",
    )


def _base_angular_dependencies(angular_major: str) -> Dict[str, str]:
    """Return the Angular runtime dependency set for a generated app."""
    manifest = _WEBAPP_VERSION_MANIFEST[angular_major]
    angular_version = manifest["angular"]
    return {
        "@angular/common": angular_version,
        "@angular/compiler": angular_version,
        "@angular/core": angular_version,
        "@angular/forms": angular_version,
        "@angular/platform-browser": angular_version,
        "@angular/router": angular_version,
        "rxjs": manifest["rxjs"],
        "tslib": manifest["tslib"],
        "zone.js": manifest["zoneJs"],
    }


def _base_angular_dev_dependencies(angular_major: str) -> Dict[str, str]:
    """Return the Angular dev dependency set for a generated app."""
    manifest = _WEBAPP_VERSION_MANIFEST[angular_major]
    angular_version = manifest["angular"]
    return {
        "@angular/build": manifest["angularBuild"],
        "@angular/cli": angular_version,
        "@angular/compiler-cli": angular_version,
        "@angular/localize": angular_version,
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
    if "ok" in feature_packs:
        dependencies["@ni/ok-angular"] = manifest["okAngular"]
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
    manifest = _WEBAPP_VERSION_MANIFEST[angular_major]
    dependencies = _base_angular_dependencies(angular_major)
    dependencies.update(_feature_pack_dependencies(feature_packs, angular_major))
    dev_dependencies = _base_angular_dev_dependencies(angular_major)

    package_json["name"] = project_name
    package_json["description"] = f"{publish_name} hosted Angular webapp for SystemLink."
    package_json["engines"] = {"node": manifest["nodeEngine"]}
    package_json["dependencies"] = dependencies
    package_json["devDependencies"] = dev_dependencies
    package_json["scripts"] = {
        "start": "ng serve --host 0.0.0.0",
        "build": "ng build",
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
    profile = _webapp_template_profile(template)
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
    click.echo(
        "    - enabled routes: "
        + ", ".join(tab["route"].lstrip("/") or "home" for tab in profile["tabs"])
    )
    click.echo("    - APP_BASE_HREF provider with no <base> tag")
    click.echo("    - Angular localize polyfills for build")
    click.echo("    - Nimble fonts in src/styles.scss")
    click.echo("    - @angular/build application builder with inlineCritical disabled")
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
    _apply_selected_webapp_template(
        target_dir=target_dir,
        template=template,
        app_name=app_name,
        publish_name=publish_display_name,
        workspace_name=workspace_name,
        routing_mode=routing_mode,
        auth_mode=auth_mode,
    )
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
