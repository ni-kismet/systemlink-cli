"""CLI commands for managing SystemLink WebApps via the WebApp Service.

Provides local scaffolding (init), packing helpers (pack), and remote
management (list, get, delete, publish, open).
"""

import hashlib
import io
import re
import shutil
import sys
import tarfile
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

import click
import questionary
import requests

from .cli_utils import validate_output_format
from .skill_click import install_skills_to_directory
from .universal_handlers import UniversalResponseHandler
from .utils import (
    ExitCodes,
    format_success,
    get_base_url,
    get_web_url,
    get_headers,
    load_json_file,
    get_ssl_verify,
    get_workspace_id_with_fallback,
    get_workspace_map,
    handle_api_error,
    sanitize_filename,
    save_json_file,
)
from .workspace_utils import get_effective_workspace, get_workspace_display_name

_PACKAGE_PATTERN = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_VERSION_PATTERN = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$")
_MAINTAINER_PATTERN = re.compile(r"^[^<>]+\s<[^<>@\s]+@[^<>@\s]+>$")
_XB_PLUGIN_VALUES = ("webapp", "notebook", "dashboard", "routine", "bundle")
_ALLOWED_ICON_EXTENSIONS = frozenset({".svg", ".png", ".jpg", ".jpeg", ".webp", ".gif", ".ico"})
_MAX_PACKAGE_LENGTH = 100
_MAX_DISPLAY_NAME_LENGTH = 200
_MAX_DESCRIPTION_LENGTH = 5000
_MAX_RELEASE_TAG_LENGTH = 200
_MAX_SCREENSHOT_COUNT = 3
_SOURCE_REPO_PATTERN = re.compile(r"^[A-Za-z0-9._-]+/[A-Za-z0-9._-]+$")
_SOURCE_COMMIT_PATTERN = re.compile(r"^[0-9a-f]{40}$")
_ALLOWED_PLUGIN_MANAGER_KEYS = {
    "buildCommand",
    "buildDir",
    "description",
    "displayName",
    "homepage",
    "iconFile",
    "license",
    "maintainer",
    "nipkgFile",
    "package",
    "releaseTag",
    "section",
    "screenshots",
    "sourceCommit",
    "sourceRepo",
    "slPluginManagerMinServerVersion",
    "slPluginManagerTags",
    "version",
    "xbPlugin",
}
_LEGACY_MANIFEST_KEY_MAP = {
    "appStoreCategory": "section",
    "appStoreType": "xbPlugin",
    "appStoreAuthor": "maintainer",
    "appStoreRepo": "homepage",
    "appStoreTags": "slPluginManagerTags",
    "appStoreMinServerVersion": "slPluginManagerMinServerVersion",
}


def _get_webapp_base_url() -> str:
    return f"{get_base_url()}/niapp/v1"


def _build_published_webapp_url(
    webapp_id: str,
    webapp_name: str = "",
    workspace_id: str = "",
    workspace_name_hint: str = "",
    properties: Optional[Dict[str, Any]] = None,
) -> str:
    """Return the best available published URL for a webapp.

    Prefers the friendly SystemLink web UI URL and falls back to any explicit
    URL-like property returned by the service, then the raw content endpoint.
    """
    from urllib.parse import quote

    resolved_name = webapp_name
    resolved_workspace_id = workspace_id
    resolved_properties = properties or {}

    if webapp_id and (not resolved_name or not resolved_workspace_id):
        try:
            resp = requests.get(
                f"{_get_webapp_base_url()}/webapps/{webapp_id}",
                headers=get_headers("application/json"),
                verify=get_ssl_verify(),
            )
            resp.raise_for_status()
            data = resp.json()
            resolved_name = resolved_name or str(data.get("name", ""))
            resolved_workspace_id = resolved_workspace_id or str(data.get("workspace", ""))
            maybe_properties = data.get("properties", {})
            if not resolved_properties and isinstance(maybe_properties, dict):
                resolved_properties = maybe_properties
        except Exception:
            pass

    workspace_name = workspace_name_hint.strip()
    if resolved_workspace_id:
        try:
            workspace_map = get_workspace_map()
        except Exception:
            workspace_map = {}

        mapped_workspace_name = str(workspace_map.get(resolved_workspace_id, "") or "").strip()
        if mapped_workspace_name:
            workspace_name = mapped_workspace_name

    if resolved_name and workspace_name:
        web_base = get_web_url().rstrip("/")
        return f"{web_base}/webapps/app/{quote(workspace_name)}/{quote(resolved_name)}"

    fallback_url = (
        resolved_properties.get("embedLocation")
        or resolved_properties.get("url")
        or resolved_properties.get("interface")
    )
    if fallback_url:
        return str(fallback_url)

    if webapp_id:
        return f"{_get_webapp_base_url()}/webapps/{webapp_id}/content"

    return ""


def _query_webapps_http(filter_str: str, max_items: int = 1000) -> List[Dict[str, Any]]:
    """Query webapps using continuation token pagination.

    Args:
        filter_str: Filter string for the query (server syntax)
        max_items: Maximum number of items to retrieve in total

    Returns:
        List of webapp dicts
    """
    base = _get_webapp_base_url()
    headers = get_headers("application/json")

    all_items: List[Dict[str, Any]] = []
    continuation_token: Optional[str] = None

    # Choose a reasonable page size for server-side paging
    page_size = 100
    if max_items and max_items < page_size:
        page_size = max_items

    while True:
        payload: Dict[str, Any] = {
            "take": page_size,
            "orderBy": "updated",
            "orderByDescending": True,
        }
        if filter_str:
            payload["filter"] = filter_str
        if continuation_token:
            payload["continuationToken"] = continuation_token

        # Request the server to include a total count when available
        resp = requests.post(
            f"{base}/webapps/query?includeTotalCount=true",
            headers=headers,
            json=payload,
            verify=get_ssl_verify(),
        )
        resp.raise_for_status()
        data = resp.json()
        page_items: List[Dict[str, Any]] = data.get("webapps", []) if isinstance(data, dict) else []

        for it in page_items:
            all_items.append(it)

        # Stop if we've reached max_items
        if max_items and len(all_items) >= max_items:
            return all_items[:max_items]

        continuation_token = data.get("continuationToken")
        if not continuation_token:
            break

    return all_items


def _fetch_webapps_page(
    filter_str: str, take: int = 100, continuation_token: Optional[str] = None
) -> tuple:
    """Fetch a single page of webapps from the server.

    Returns a tuple: (items, continuationToken, total)
    """
    base = _get_webapp_base_url()
    headers = get_headers("application/json")

    payload: Dict[str, Any] = {"take": take, "orderBy": "updated", "orderByDescending": True}
    if filter_str:
        payload["filter"] = filter_str
    if continuation_token:
        payload["continuationToken"] = continuation_token

    # Request the server to include a total count when available
    resp = requests.post(
        f"{base}/webapps/query?includeTotalCount=true",
        headers=headers,
        json=payload,
        verify=get_ssl_verify(),
    )
    resp.raise_for_status()
    data = resp.json()
    items = data.get("webapps", []) if isinstance(data, dict) else []
    cont = data.get("continuationToken")
    total = data.get("totalCount")

    return items, cont, total


def _default_nipkg_filename(package_name: str, version: str) -> str:
    """Return the canonical Plugin Manager package filename."""
    return f"{package_name}_{version}_all.nipkg"


def _default_display_name(package_name: str) -> str:
    """Return a display name derived from a package identifier."""
    words = re.split(r"[._-]+", package_name)
    return " ".join(word.capitalize() for word in words if word)


def _default_angular_build_dir(directory: Path) -> str:
    """Return the default Angular production output path for a starter directory."""
    return f"dist/{_default_angular_project_name(directory)}/browser"


def _resolve_local_path(path_value: str, base_dir: Optional[Path] = None) -> Path:
    """Resolve a local path against a base directory or the current working directory."""
    path = Path(path_value).expanduser()
    if not path.is_absolute():
        anchor = base_dir if base_dir is not None else Path.cwd()
        path = anchor / path
    return path.resolve()


def _validate_icon_file_value(icon_file: str, base_dir: Optional[Path] = None) -> Optional[str]:
    """Validate the icon asset referenced by Plugin Manager metadata."""
    if not icon_file:
        return "iconFile is required"

    resolved_icon = _resolve_local_path(icon_file, base_dir)
    if not resolved_icon.exists() or not resolved_icon.is_file():
        return f"iconFile does not exist or is not a file: {icon_file}"
    if resolved_icon.suffix.lower() not in _ALLOWED_ICON_EXTENSIONS:
        allowed_extensions = ", ".join(sorted(ext.lstrip(".") for ext in _ALLOWED_ICON_EXTENSIONS))
        return f"iconFile must be one of: {allowed_extensions}"
    return None


def _prepare_icon_file_for_directory(
    icon_file: str, directory: Path, force: bool
) -> tuple[Path, str]:
    """Validate an icon asset and return its source path plus stored manifest filename."""
    icon_error = _validate_icon_file_value(icon_file)
    if icon_error:
        click.echo(f"✗ {icon_error}", err=True)
        sys.exit(ExitCodes.INVALID_INPUT)

    source_icon = _resolve_local_path(icon_file)
    target_icon = directory / source_icon.name

    if target_icon.exists() and target_icon.resolve() != source_icon:
        if not force:
            click.echo(
                f"✗ {target_icon.name} already exists in {directory}. Use --force to overwrite it.",
                err=True,
            )
            sys.exit(ExitCodes.INVALID_INPUT)

    return source_icon, target_icon.name


def _copy_icon_file_to_directory(source_icon: Path, directory: Path) -> bool:
    """Copy an icon asset into the manifest directory when it is not already there."""
    target_icon = directory / source_icon.name
    if target_icon.resolve() == source_icon:
        return False

    shutil.copy2(source_icon, target_icon)
    return True


def _compute_sha256(file_path: Path) -> str:
    """Return the SHA-256 checksum for a file."""
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as input_file:
        for chunk in iter(lambda: input_file.read(1024 * 1024), b""):
            sha256_hash.update(chunk)
    return sha256_hash.hexdigest()


def _normalize_plugin_manager_metadata(raw_metadata: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize legacy App Store keys to Plugin Manager keys."""
    metadata = dict(raw_metadata)
    for old_key, new_key in _LEGACY_MANIFEST_KEY_MAP.items():
        if old_key in metadata and new_key not in metadata:
            metadata[new_key] = metadata[old_key]
    for old_key in _LEGACY_MANIFEST_KEY_MAP:
        metadata.pop(old_key, None)
    return metadata


def _validate_plugin_manager_metadata(
    raw_metadata: Dict[str, Any],
    require_build_dir: bool = False,
    base_dir: Optional[Path] = None,
) -> Dict[str, Any]:
    """Validate and normalize Plugin Manager packaging metadata."""
    from urllib.parse import urlparse

    metadata = _normalize_plugin_manager_metadata(raw_metadata)
    unexpected_keys = sorted(set(metadata) - _ALLOWED_PLUGIN_MANAGER_KEYS)

    package_name = str(metadata.get("package", "")).strip()
    version = str(metadata.get("version", "")).strip()
    display_name = str(metadata.get("displayName", "")).strip()
    description = str(metadata.get("description", "")).strip()
    section = str(metadata.get("section", "")).strip()
    maintainer = str(metadata.get("maintainer", "")).strip()
    homepage = str(metadata.get("homepage", "")).strip()
    license_name = str(metadata.get("license", "")).strip()
    xb_plugin = str(metadata.get("xbPlugin", "")).strip()
    tags = str(metadata.get("slPluginManagerTags", "")).strip()
    min_server_version = str(metadata.get("slPluginManagerMinServerVersion", "")).strip()
    nipkg_file = str(metadata.get("nipkgFile", "")).strip()
    build_dir = str(metadata.get("buildDir", "")).strip()
    build_command = str(metadata.get("buildCommand", "")).strip()
    icon_file = str(metadata.get("iconFile", "")).strip()
    source_repo = str(metadata.get("sourceRepo", "")).strip()
    release_tag = str(metadata.get("releaseTag", "")).strip()
    source_commit = str(metadata.get("sourceCommit", "")).strip()
    screenshots_raw = metadata.get("screenshots")

    errors: List[str] = []
    screenshots: List[str] = []

    if unexpected_keys:
        errors.append("unexpected field(s): " + ", ".join(unexpected_keys))

    if not package_name or not _PACKAGE_PATTERN.match(package_name) or len(package_name) < 3:
        errors.append("package must match ^[a-z0-9][a-z0-9._-]*$ and be at least 3 characters")
    elif len(package_name) > _MAX_PACKAGE_LENGTH:
        errors.append(f"package must be at most {_MAX_PACKAGE_LENGTH} characters")
    if not version or not _VERSION_PATTERN.match(version):
        errors.append("version must be strict semver in MAJOR.MINOR.PATCH format")
    if not display_name or len(display_name) < 3:
        errors.append("displayName must be at least 3 characters")
    elif len(display_name) > _MAX_DISPLAY_NAME_LENGTH:
        errors.append(f"displayName must be at most {_MAX_DISPLAY_NAME_LENGTH} characters")
    if not description or len(description) < 20:
        errors.append("description must be at least 20 characters")
    elif len(description) > _MAX_DESCRIPTION_LENGTH:
        errors.append(f"description must be at most {_MAX_DESCRIPTION_LENGTH} characters")
    if not section or len(section) < 2:
        errors.append("section must be at least 2 characters")
    if not maintainer or not _MAINTAINER_PATTERN.match(maintainer):
        errors.append("maintainer must be in the format 'Name <email@example.com>'")
    if homepage:
        parsed_homepage = urlparse(homepage)
        if not parsed_homepage.scheme or not parsed_homepage.netloc:
            errors.append("homepage must be a valid absolute URI")
    if not license_name or len(license_name) < 2:
        errors.append("license must be at least 2 characters")
    if xb_plugin not in _XB_PLUGIN_VALUES:
        errors.append(f"xbPlugin must be one of: {', '.join(_XB_PLUGIN_VALUES)}")
    if nipkg_file and not nipkg_file.endswith(".nipkg"):
        errors.append("nipkgFile must end with .nipkg")
    if source_repo and not _SOURCE_REPO_PATTERN.match(source_repo):
        errors.append("sourceRepo must be in owner/name format")
    if release_tag and len(release_tag) > _MAX_RELEASE_TAG_LENGTH:
        errors.append(f"releaseTag must be at most {_MAX_RELEASE_TAG_LENGTH} characters")
    if source_commit and not _SOURCE_COMMIT_PATTERN.match(source_commit):
        errors.append("sourceCommit must be a 40-character lowercase git SHA")
    if bool(source_repo) != bool(release_tag):
        errors.append("sourceRepo and releaseTag must be provided together")
    if screenshots_raw not in (None, ""):
        if not isinstance(screenshots_raw, list):
            errors.append("screenshots must be an array of filenames")
        else:
            screenshots = [str(item).strip() for item in screenshots_raw]
            if any(not item for item in screenshots):
                errors.append("screenshots entries must be non-empty strings")
            if len(screenshots) > _MAX_SCREENSHOT_COUNT:
                errors.append(f"screenshots must contain at most {_MAX_SCREENSHOT_COUNT} items")
            if len(set(screenshots)) != len(screenshots):
                errors.append("screenshots entries must be unique")
    if require_build_dir and not build_dir:
        errors.append("buildDir is required when packing from config without a folder argument")
    icon_error = _validate_icon_file_value(icon_file, base_dir)
    if icon_error:
        errors.append(icon_error)

    if errors:
        click.echo("✗ Invalid plugin manager metadata:", err=True)
        for error in errors:
            click.echo(f"  - {error}", err=True)
        sys.exit(ExitCodes.INVALID_INPUT)

    validated: Dict[str, Any] = {
        "package": package_name,
        "version": version,
        "displayName": display_name,
        "description": description,
        "section": section,
        "maintainer": maintainer,
        "license": license_name,
        "xbPlugin": xb_plugin,
        "nipkgFile": nipkg_file or _default_nipkg_filename(package_name, version),
    }
    if homepage:
        validated["homepage"] = homepage
    if tags:
        validated["slPluginManagerTags"] = tags
    if min_server_version:
        validated["slPluginManagerMinServerVersion"] = min_server_version
    if build_dir:
        validated["buildDir"] = build_dir
    if build_command:
        validated["buildCommand"] = build_command
    validated["iconFile"] = icon_file
    if source_repo:
        validated["sourceRepo"] = source_repo
    if release_tag:
        validated["releaseTag"] = release_tag
    if source_commit:
        validated["sourceCommit"] = source_commit
    if screenshots:
        validated["screenshots"] = screenshots

    return validated


def _pack_folder_to_nipkg(
    folder: Path,
    output: Optional[Path] = None,
    metadata: Optional[Dict[str, Any]] = None,
    icon_source: Optional[Path] = None,
) -> Path:
    """Pack a folder into a .nipkg (ar) file and return the output path.

    The .nipkg produced by this helper uses a Debian-style ar layout with
    three members: debian-binary, control.tar.gz and data.tar.gz. The
    implementation writes the ar archive directly; long member names are
    truncated to 16 bytes (simple strategy) which is acceptable for our
    use-case but could be extended to support GNU longname tables if
    needed.
    """
    if not folder.exists() or not folder.is_dir():
        raise click.ClickException(f"Folder not found: {folder}")

    if metadata is not None:
        package_name = metadata["package"]
        version = metadata["version"]
        architecture = "all"
    else:
        package_name = sanitize_filename(folder.name)
        version = "1.0.0"
        architecture = "all"
        if "_" in folder.name:
            first, rest = folder.name.split("_", 1)
            package_name = sanitize_filename(first)
            rest_parts = rest.split("_")
            if rest_parts:
                version = rest_parts[0]
            if len(rest_parts) > 1:
                architecture = "_".join(rest_parts[1:])

    if output is None:
        if metadata is not None:
            output = folder.parent / metadata["nipkgFile"]
        else:
            output = folder.with_suffix(".nipkg")

    # Ensure parent exists
    output.parent.mkdir(parents=True, exist_ok=True)
    # Debian-style package layout inside an ar archive:
    # - debian-binary (contains version string, e.g. "2.0\n")
    # - control.tar.gz (contains a control file with package metadata)
    # - data.tar.gz (contains the payload files)

    if metadata is not None:
        control_fields = {
            "Package": metadata["package"],
            "Version": metadata["version"],
            "Architecture": architecture,
            "Description": metadata["description"],
            "Section": metadata["section"],
            "Maintainer": metadata["maintainer"],
            "XB-DisplayName": metadata["displayName"],
            "XB-DisplayVersion": metadata["version"],
            "XB-Plugin": metadata["xbPlugin"],
            "XB-UserVisible": "yes",
            "XB-SlPluginManagerLicense": metadata["license"],
        }
        if metadata.get("homepage"):
            control_fields["Homepage"] = metadata["homepage"]
        if metadata.get("slPluginManagerTags"):
            control_fields["XB-SlPluginManagerTags"] = metadata["slPluginManagerTags"]
        if metadata.get("slPluginManagerMinServerVersion"):
            control_fields["XB-SlPluginManagerMinServerVersion"] = metadata[
                "slPluginManagerMinServerVersion"
            ]
        if metadata.get("iconFile"):
            control_fields["XB-SlPluginManagerIcon"] = Path(metadata["iconFile"]).name
    else:
        control_fields = {
            "Package": package_name,
            "Version": version,
            "Architecture": architecture,
            "Maintainer": "slcli <no-reply@example.com>",
            "Description": f"Package created by slcli for {package_name}",
        }

    control_lines = [f"{k}: {v}" for k, v in control_fields.items()]
    control_content = ("\n".join(control_lines) + "\n").encode("utf-8")

    # Create control.tar.gz in-memory containing a single file 'control'
    control_buf = io.BytesIO()
    with tarfile.open(fileobj=control_buf, mode="w:gz") as tf:
        ti = tarfile.TarInfo(name="control")
        ti.size = len(control_content)
        ti.mtime = int(time.time())
        tf.addfile(ti, io.BytesIO(control_content))
    control_bytes = control_buf.getvalue()

    # Create data.tar.gz in-memory containing the folder contents at the root
    data_buf = io.BytesIO()
    with tempfile.TemporaryDirectory() as temp_dir:
        payload_folder = folder
        if metadata is not None and icon_source is not None:
            icon_name = Path(metadata["iconFile"]).name
            folder_icon = folder.resolve() / icon_name
            resolved_icon_source = icon_source.resolve()
            if not folder_icon.exists() or folder_icon.resolve() != resolved_icon_source:
                payload_folder = Path(temp_dir) / folder.name
                shutil.copytree(folder, payload_folder)
                shutil.copy2(resolved_icon_source, payload_folder / icon_name)

        with tarfile.open(fileobj=data_buf, mode="w:gz") as dtf:
            # tarfile.add will handle directories and files; preserve relative paths
            dtf.add(str(payload_folder), arcname=".")
        data_bytes = data_buf.getvalue()

    # debian-binary content
    debian_bin = b"2.0\n"

    # Write an ar archive (the Debian .deb format) but use .nipkg extension
    def _ar_header(
        name: str,
        size: int,
        mtime: Optional[int] = None,
        uid: int = 0,
        gid: int = 0,
        mode: int = 0o100644,
    ) -> bytes:
        if mtime is None:
            mtime = int(time.time())
        # Header fields: name(16) mtime(12) uid(6) gid(6) mode(8) size(10) magic(2)
        name_field = name.encode("utf-8")
        if len(name_field) > 16:
            # use truncated name (simple strategy)
            name_field = name_field[:16]
        header = (
            name_field.ljust(16, b" ")
            + str(int(mtime)).encode("ascii").ljust(12, b" ")
            + str(int(uid)).encode("ascii").ljust(6, b" ")
            + str(int(gid)).encode("ascii").ljust(6, b" ")
            + oct(mode)[2:].encode("ascii").ljust(8, b" ")
            + str(int(size)).encode("ascii").ljust(10, b" ")
            + b"`\n"
        )
        return header

    with open(output, "wb") as out_f:
        # Global header
        out_f.write(b"!<arch>\n")

        # debian-binary
        out_f.write(_ar_header("debian-binary", len(debian_bin)))
        out_f.write(debian_bin)
        if len(debian_bin) % 2:
            out_f.write(b"\n")

        # control.tar.gz
        out_f.write(_ar_header("control.tar.gz", len(control_bytes)))
        out_f.write(control_bytes)
        if len(control_bytes) % 2:
            out_f.write(b"\n")

        # data.tar.gz
        out_f.write(_ar_header("data.tar.gz", len(data_bytes)))
        out_f.write(data_bytes)
        if len(data_bytes) % 2:
            out_f.write(b"\n")

    return output


# ── Template scaffolding helpers ──────────────────────────────────────────


def _default_angular_project_name(directory: Path) -> str:
    """Return a safe Angular project name derived from the target directory."""
    project_name = sanitize_filename(directory.name)
    return project_name or "systemlink-webapp"


def _build_angular_bootstrap_command(directory: Path) -> str:
    """Build the canonical Angular CLI command for this starter directory."""
    project_name = _default_angular_project_name(directory)
    return (
        f"npx -y @angular/cli@20 new {project_name} --directory . "
        "--routing --style=scss --skip-git --no-standalone --defaults --force"
    )


def _build_submission_manifest(
    nipkg_path: Path, metadata: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """Build the thin submission manifest from a packaged artifact."""
    manifest: Dict[str, Any] = {
        "schemaVersion": 2,
        "nipkgFile": nipkg_path.name,
        "sha256": _compute_sha256(nipkg_path),
    }
    if metadata is not None:
        for key in ("sourceRepo", "releaseTag", "sourceCommit"):
            value = metadata.get(key)
            if value:
                manifest[key] = value
        screenshots = metadata.get("screenshots")
        if screenshots:
            manifest["screenshots"] = screenshots
    return manifest


def _build_webapp_pack_config(
    package_name: str,
    version: str,
    display_name: str,
    description: str,
    section: str,
    maintainer: str,
    homepage: str,
    license_name: str,
    xb_plugin: str,
    tags: str,
    min_server_version: str,
    build_dir: str,
    build_command: str,
    icon_file: str,
    icon_validation_base_dir: Path,
    source_repo: str,
    release_tag: str,
    source_commit: str,
) -> Dict[str, Any]:
    """Build validated nipkg.config.json payloads."""
    pack_config = _validate_plugin_manager_metadata(
        {
            "package": package_name,
            "version": version,
            "displayName": display_name,
            "description": description,
            "section": section,
            "maintainer": maintainer,
            "homepage": homepage,
            "license": license_name,
            "xbPlugin": xb_plugin,
            "slPluginManagerTags": tags,
            "slPluginManagerMinServerVersion": min_server_version,
            "iconFile": icon_file,
            "sourceRepo": source_repo,
            "releaseTag": release_tag,
            "sourceCommit": source_commit,
        },
        base_dir=icon_validation_base_dir,
    )

    pack_config.pop("nipkgFile", None)
    pack_config["buildDir"] = build_dir
    pack_config["buildCommand"] = build_command

    return pack_config


def _render_angular_prompts_md(directory: Path) -> str:
    """Render the prompt file for the Angular starter."""
    bootstrap_command = _build_angular_bootstrap_command(directory)
    return f"""# SystemLink WebApp - AI Prompts

This project was initialized with `slcli webapp init`.
The bundled `systemlink-webapp` and `slcli` skills are already installed into
this project so your AI assistant can scaffold the Angular workspace and apply
the SystemLink-specific conventions immediately.

## Starter Prompt

Use this prompt first when the directory still only contains starter files:

> "Bootstrap this directory into a maintainable Angular 20 SystemLink webapp.
> Run `{bootstrap_command}` to generate the Angular workspace in place, then
> install `@ni/nimble-angular` and `@ni/systemlink-clients-ts`. Create a
> reusable app shell aligned with other SystemLink apps: `nimble-theme-provider`
> at the root, a responsive page header, content regions for summary cards and
> tables, and shared loading, error, and empty states. Keep the app NgModule-
> based, configure `APP_BASE_HREF`, remove the `<base>` tag, use hash routing,
> disable `inlineCritical` in production, import Nimble fonts, and sync the app
> theme with the host SystemLink shell."

## Manual Bootstrap

If you want to do the initial setup yourself before handing the project to AI:

```bash
{bootstrap_command}
npm install @ni/nimble-angular @ni/systemlink-clients-ts
```

The Angular workspace should be created in this directory, not inside a nested
subfolder.

## Example Feature Prompts

### Fleet monitoring

> "Build a dashboard that shows all connected systems with their status,
> operating system, and last check-in time. Highlight systems that have been
> offline for more than 24 hours."

### Test results review

> "Create a page where I can browse recent test results, filter by status,
> program name, and workspace, and see a summary of failure rates."

### Asset and calibration tracking

> "Show tracked assets grouped by calibration status. I want overdue and due-
> soon sections, plus an asset details page with key metadata and history."

### Production KPIs

> "Build a dashboard with first-pass yield, throughput per hour, and a trend
> chart of failures over the last 30 days."

### Build and deploy

> "Build the project for production and deploy it to SystemLink."

## Reference

- [Nimble Angular components](https://nimble.ni.dev/)
- [SystemLink TypeScript clients](https://www.npmjs.com/package/@ni/systemlink-clients-ts)
- [slcli webapp commands](https://ni-kismet.github.io/systemlink-cli/commands.html#webapp)
"""


def _render_angular_start_here_md(directory: Path) -> str:
    """Render the starter guide for the Angular workflow."""
    bootstrap_command = _build_angular_bootstrap_command(directory)
    return f"""# SystemLink Angular WebApp Starter

This directory was initialized with `slcli webapp init`.

`slcli` owns the SystemLink-specific starter layer for this workflow:

- bundled AI skills in `.agents/skills/`
- ready-made prompts in [PROMPTS.md](PROMPTS.md)
- deployment guidance for `slcli webapp publish`
- Plugin Manager packaging config scaffolding via `slcli webapp manifest init`

Angular CLI remains the source of truth for the Angular workspace itself. That
keeps the generated project aligned with current Angular defaults while the
skills and starter files enforce the SystemLink-specific best practices.

## Bootstrap the Angular workspace

```bash
{bootstrap_command}
npm install @ni/nimble-angular @ni/systemlink-clients-ts
```

If you use an AI assistant, ask it to follow the starter prompt in
[PROMPTS.md](PROMPTS.md). The Angular app should be created in this directory,
not inside a nested subfolder.

## Baseline conventions

- Angular 20 with an NgModule-based app (`--no-standalone`)
- `@ni/nimble-angular` for UI and design tokens
- `@ni/systemlink-clients-ts` as the default API integration path
- `APP_BASE_HREF` provided in DI and no `<base>` tag in `index.html`
- Hash routing for SystemLink sub-path hosting
- `inlineCritical: false` in the production build configuration
- A reusable SystemLink-aligned shell with theme sync, page header, content
  regions, and shared loading, error, and empty states

## Deploy to SystemLink

```bash
ng build --configuration production
slcli webapp publish dist/<project-name>/browser/ \\
  --name "My Dashboard" --workspace Default
```

## Plugin Manager packaging metadata

```bash
slcli webapp manifest init . \\
    --description "A dashboard for monitoring fleet health and calibration status." \\
    --section Dashboard \\
    --maintainer "Your Name <you@example.com>" \\
    --license MIT \\
    --icon-file ./icon.svg

slcli webapp pack --config nipkg.config.json
```
"""


def _init_angular_template(directory: Path, force: bool) -> None:
    """Scaffold the SystemLink Angular starter for a new webapp."""
    directory.mkdir(parents=True, exist_ok=True)

    prompts_file = directory / "PROMPTS.md"
    start_here_file = directory / "START_HERE.md"

    # Check for existing files
    existing = []
    if prompts_file.exists() and not force:
        existing.append("PROMPTS.md")
    if start_here_file.exists() and not force:
        existing.append("START_HERE.md")
    if existing:
        click.echo(
            f"✗ {', '.join(existing)} already exist(s). Use --force to overwrite.",
            err=True,
        )
        sys.exit(ExitCodes.INVALID_INPUT)

    prompts_file.write_text(_render_angular_prompts_md(directory), encoding="utf-8")
    start_here_file.write_text(_render_angular_start_here_md(directory), encoding="utf-8")

    # Auto-install AI skills into the project directory
    installed = install_skills_to_directory(directory)
    skill_msg = f"{installed} skill(s) installed" if installed else "skills not found"

    format_success(
        "Scaffolded SystemLink Angular starter",
        {
            "Directory": str(directory),
            "Skills": skill_msg,
            "Next steps": (
                "1. cd " + str(directory) + "\n"
                "   2. Open START_HERE.md and PROMPTS.md\n"
                "   3. Ask AI to bootstrap the Angular workspace in this directory"
            ),
        },
    )


def register_webapp_commands(cli: Any) -> None:
    """Register CLI commands for SystemLink webapps."""

    @cli.group()
    def webapp() -> None:  # pragma: no cover - Click wiring
        """Build, publish, and manage SystemLink web applications."""

    @webapp.command(name="init")
    @click.argument(
        "directory",
        type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    )
    @click.option("--force", is_flag=True, help="Overwrite existing starter files")
    def init_webapp(directory: Path, force: bool) -> None:
        """Scaffold the SystemLink Angular starter for a new webapp."""
        try:
            _init_angular_template(directory, force)
        except SystemExit:
            raise
        except Exception as exc:
            handle_api_error(exc)

    @webapp.group(name="manifest")
    def webapp_manifest() -> None:
        """Create Plugin Manager packaging config and submission manifest inputs."""

    @webapp_manifest.command(name="init")
    @click.argument(
        "directory",
        type=click.Path(file_okay=False, dir_okay=True, path_type=Path),
    )
    @click.option("--package", "package_name", default="", help="Package identifier")
    @click.option("--version", default="0.1.0", show_default=True, help="Semantic version")
    @click.option("--display-name", "display_name", default="", help="Human-readable name")
    @click.option("--description", required=True, help="Plugin description")
    @click.option("--section", required=True, help="Plugin Manager section/category")
    @click.option("--maintainer", required=True, help="Maintainer in 'Name <email>' format")
    @click.option("--homepage", default="", help="Project homepage or source repository URL")
    @click.option("--license", "license_name", required=True, help="License identifier")
    @click.option(
        "--plugin-type",
        "xb_plugin",
        type=click.Choice(list(_XB_PLUGIN_VALUES)),
        default="webapp",
        show_default=True,
        help="Plugin Manager top-level plugin type",
    )
    @click.option("--tags", default="", help="Comma-separated Plugin Manager search tags")
    @click.option(
        "--min-server-version",
        default="",
        help="Minimum supported SystemLink server version",
    )
    @click.option("--build-dir", default="", help="Build output directory for nipkg.config.json")
    @click.option(
        "--build-command",
        default="npm run build",
        show_default=True,
        help="Build command written to nipkg.config.json",
    )
    @click.option(
        "--source-repo",
        default="",
        help="Optional provenance repository in owner/name format for the generated manifest",
    )
    @click.option(
        "--release-tag",
        default="",
        help="Optional provenance release tag for the generated manifest",
    )
    @click.option(
        "--source-commit",
        default="",
        help="Optional source commit SHA for the generated manifest",
    )
    @click.option(
        "--icon-file",
        required=True,
        help="Path to the icon asset; copied into the manifest directory as iconFile",
    )
    @click.option("--force", is_flag=True, help="Overwrite existing packaging files")
    def init_manifest(
        directory: Path,
        package_name: str,
        version: str,
        display_name: str,
        description: str,
        section: str,
        maintainer: str,
        homepage: str,
        license_name: str,
        xb_plugin: str,
        tags: str,
        min_server_version: str,
        build_dir: str,
        build_command: str,
        source_repo: str,
        release_tag: str,
        source_commit: str,
        icon_file: str,
        force: bool,
    ) -> None:
        """Write nipkg.config.json for Plugin Manager packaging."""
        try:
            directory.mkdir(parents=True, exist_ok=True)

            package_name = package_name or sanitize_filename(directory.name, "webapp")
            display_name = display_name or _default_display_name(package_name)
            build_dir = build_dir or _default_angular_build_dir(directory)

            config_path = directory / "nipkg.config.json"
            existing = []
            if config_path.exists() and not force:
                existing.append("nipkg.config.json")
            if existing:
                click.echo(
                    f"✗ {', '.join(existing)} already exist(s). Use --force to overwrite.",
                    err=True,
                )
                sys.exit(ExitCodes.INVALID_INPUT)

            source_icon, manifest_icon_file = _prepare_icon_file_for_directory(
                icon_file, directory, force
            )

            pack_config = _build_webapp_pack_config(
                package_name=package_name,
                version=version,
                display_name=display_name,
                description=description,
                section=section,
                maintainer=maintainer,
                homepage=homepage,
                license_name=license_name,
                xb_plugin=xb_plugin,
                tags=tags,
                min_server_version=min_server_version,
                build_dir=build_dir,
                build_command=build_command,
                icon_file=manifest_icon_file,
                icon_validation_base_dir=source_icon.parent,
                source_repo=source_repo,
                release_tag=release_tag,
                source_commit=source_commit,
            )

            copied_icon = _copy_icon_file_to_directory(source_icon, directory)
            try:
                save_json_file(pack_config, str(config_path))
            except Exception:
                if copied_icon:
                    (directory / manifest_icon_file).unlink(missing_ok=True)
                raise

            format_success(
                "Created Plugin Manager pack config",
                {
                    "Pack config": str(config_path),
                    "Next step": "Run slcli webapp pack --config nipkg.config.json to generate the .nipkg and manifest.json",
                },
            )
        except SystemExit:
            raise
        except Exception as exc:
            handle_api_error(exc)

    @webapp.command(name="pack")
    @click.argument(
        "folder",
        required=False,
        type=click.Path(exists=True, file_okay=False, path_type=Path),
    )
    @click.option(
        "--config",
        "config_path",
        type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path),
        default=None,
        help=(
            "Path to nipkg.config.json or compatible metadata JSON. "
            "If it does not include buildDir, also pass FOLDER."
        ),
    )
    @click.option(
        "--output",
        "output",
        type=click.Path(file_okay=True, dir_okay=False, path_type=Path),
        default=None,
        help="Output .nipkg file path",
    )
    def pack_cmd(
        folder: Optional[Path], config_path: Optional[Path], output: Optional[Path]
    ) -> None:
        """Pack a folder into a .nipkg."""
        try:
            metadata: Optional[Dict[str, Any]] = None
            resolved_folder = folder

            if config_path is not None:
                raw_data = load_json_file(str(config_path))
                if not isinstance(raw_data, dict):
                    click.echo("✗ Config file must contain a JSON object.", err=True)
                    sys.exit(ExitCodes.INVALID_INPUT)
                metadata = _validate_plugin_manager_metadata(
                    raw_data,
                    require_build_dir=resolved_folder is None,
                    base_dir=config_path.parent,
                )

                if resolved_folder is None:
                    build_dir = metadata.get("buildDir", "")
                    base_dir = config_path.parent
                    resolved_folder = Path(build_dir)
                    if not resolved_folder.is_absolute():
                        resolved_folder = base_dir / resolved_folder
                    resolved_folder = resolved_folder.resolve()
                    if not resolved_folder.exists() or not resolved_folder.is_dir():
                        click.echo(
                            f"✗ buildDir does not exist or is not a directory: {resolved_folder}",
                            err=True,
                        )
                        sys.exit(ExitCodes.INVALID_INPUT)

                if output is None and metadata.get("nipkgFile"):
                    output = config_path.parent / metadata["nipkgFile"]

            if resolved_folder is None:
                click.echo("✗ Must provide a folder or --config with buildDir.", err=True)
                sys.exit(ExitCodes.INVALID_INPUT)

            out = Path(output) if output else None
            icon_source: Optional[Path] = None
            if metadata is not None and config_path is not None:
                icon_source = _resolve_local_path(metadata["iconFile"], config_path.parent)

            result = _pack_folder_to_nipkg(resolved_folder, out, metadata, icon_source)
            success_data: Dict[str, str] = {"Path": str(result)}
            if metadata is not None and config_path is not None:
                manifest_path = config_path.parent / "manifest.json"
                submission_manifest = _build_submission_manifest(result, metadata)
                save_json_file(submission_manifest, str(manifest_path))
                success_data["Manifest"] = str(manifest_path)

            format_success("Packed folder", success_data)
        except SystemExit:
            raise
        except Exception as exc:
            handle_api_error(exc)

    @webapp.command(name="list")
    @click.option(
        "--workspace", "-w", "workspace", default="", help="Filter by workspace name or ID"
    )
    @click.option(
        "--filter",
        "filter_text",
        default="",
        help="Case-insensitive substring match on name",
    )
    @click.option("--take", "take", type=int, default=25, show_default=True, help="Max rows/page")
    @click.option(
        "--format",
        "format_output",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    def list_webapps(workspace: str, filter_text: str, take: int, format_output: str) -> None:
        """List webapps."""
        try:

            # Validate and normalize format option
            format_output = validate_output_format(format_output)

            # Determine how many items to request from the API
            if format_output.lower() == "json":
                # For JSON output we want to return all matching items (no
                # interactive pagination). Use a falsy api_take (0) to indicate
                # "fetch all" to the helper.
                api_take = 0
            else:
                api_take = take if take != 25 else 1000
            # Use server-side query to only retrieve WebVI documents
            base_filter = 'type == "WebVI"'
            workspace = get_effective_workspace(workspace) or workspace
            if workspace:
                ws_id = get_workspace_id_with_fallback(workspace)
                # add workspace constraint to filter
                base_filter = f'{base_filter} and workspace == "{ws_id}"'

            if filter_text:
                # Avoid ToLower() due to backend limitations; match common case variants.
                # Apply case transformations first, then escape each variant.
                def _esc(s: str) -> str:
                    return s.replace("\\", "\\\\").replace('"', '\\"')

                original_raw = filter_text
                lower_raw = original_raw.lower()
                upper_raw = original_raw.upper()
                title_raw = original_raw.title()
                variants = [
                    f'name.Contains("{_esc(original_raw)}")',
                    f'name.Contains("{_esc(lower_raw)}")',
                    f'name.Contains("{_esc(upper_raw)}")',
                    f'name.Contains("{_esc(title_raw)}")',
                ]
                name_clause = f"({' or '.join(variants)})"
                base_filter = f"({base_filter}) and ({name_clause})"

            # If the user requested JSON output or did not request a specific take,
            # fetch all matching items (using server-side paging). Otherwise, if
            # the user specified a take and wants table output, perform interactive
            # server-side paging: fetch a page, show total (if available), and offer
            # to fetch the next page(s).
            webapps: List[Dict[str, Any]] = []
            if format_output.lower() == "json" or take == 0:
                webapps = _query_webapps_http(base_filter, max_items=api_take)
            else:
                # Interactive server-side paging: show each fetched page immediately
                # using the same display formatting so the user sees the first page
                # before being prompted to fetch the next one.
                cont: Optional[str] = None
                first_page = True

                # Prepare workspace map once for display name resolution
                try:
                    workspace_map = get_workspace_map()
                except Exception:
                    workspace_map = {}

                from .universal_handlers import FilteredResponse

                def _format_page_items(raw_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
                    page_items: List[Dict[str, Any]] = []
                    for wa in raw_items:
                        if wa.get("type", "") != "WebVI":
                            continue
                        ws_name = get_workspace_display_name(wa.get("workspace", ""), workspace_map)
                        page_items.append(
                            {
                                "id": wa.get("id", ""),
                                "name": wa.get("name", ""),
                                "workspace": ws_name,
                                "type": wa.get("type", ""),
                            }
                        )
                    return page_items

                while True:
                    raw_page, cont, total = _fetch_webapps_page(base_filter, take, cont)

                    # Format and display this page immediately
                    page_display_items = _format_page_items(raw_page)

                    # Track how many items we've displayed so far and, if the
                    # server provided a total, show a concise summary like:
                    # "Showing 25 of 556 webapp(s). 531 more available."
                    if "shown_count" not in locals():
                        shown_count = 0
                    shown_count += len(page_display_items)

                    # We now delegate printing the "Showing X of Y..." summary
                    # to the UniversalResponseHandler so behavior matches other
                    # list commands (e.g., notebooks). Supply total_count and
                    # shown_count to enable that summary.
                    first_page = False

                    # Use the UniversalResponseHandler to display this page (no internal pagination)
                    def formatter(item: Dict[str, Any]) -> List[str]:
                        return [
                            item.get("name", ""),
                            item.get("workspace", ""),
                            item.get("id", ""),
                            item.get("type", ""),
                        ]

                    UniversalResponseHandler.handle_list_response(
                        resp=FilteredResponse({"webapps": page_display_items}),
                        data_key="webapps",
                        item_name="webapp",
                        format_output=format_output,
                        formatter_func=formatter,
                        headers=["Name", "Workspace", "ID", "Type"],
                        column_widths=[40, 30, 36, 16],
                        empty_message="No webapps found.",
                        enable_pagination=False,
                        page_size=take,
                        total_count=total,
                        shown_count=shown_count,
                    )
                    # Flush stdout so that the rendered table is visible before prompting
                    try:
                        sys.stdout.flush()
                    except Exception:
                        pass

                    # Accumulate raw items so callers that expect an aggregated
                    # list (or further processing) can see all fetched pages.
                    webapps.extend(raw_page)

                    # If there's no continuation token, we're done
                    if not cont:
                        break

                    # Ask the user if they want to fetch the next set
                    if not questionary.confirm("Show next set of results?", default=True).ask():
                        break

                # We've already displayed each page interactively above; avoid
                # rendering a second, aggregated table below. Return early.
                return

            # Map workspace ids
            try:
                workspace_map = get_workspace_map()
            except Exception:
                workspace_map = {}

            items: List[Dict[str, Any]] = []
            for wa in webapps:
                # Only include WebVI documents
                if wa.get("type", "") != "WebVI":
                    continue
                ws_name = get_workspace_display_name(wa.get("workspace", ""), workspace_map)
                items.append(
                    {
                        "id": wa.get("id", ""),
                        "name": wa.get("name", ""),
                        "workspace": ws_name,
                        "type": wa.get("type", ""),
                    }
                )

            from .universal_handlers import FilteredResponse

            def formatter(item: Dict[str, Any]) -> List[str]:
                return [
                    item.get("name", ""),
                    item.get("workspace", ""),
                    item.get("id", ""),
                    item.get("type", ""),
                ]

            UniversalResponseHandler.handle_list_response(
                resp=FilteredResponse({"webapps": items}),
                data_key="webapps",
                item_name="webapp",
                format_output=format_output,
                formatter_func=formatter,
                headers=["Name", "Workspace", "ID", "Type"],
                column_widths=[40, 30, 36, 16],
                empty_message="No webapps found.",
                enable_pagination=True,
                page_size=take,
            )
        except Exception as exc:
            handle_api_error(exc)

    @webapp.command(name="get")
    @click.option("--id", "-i", "webapp_id", required=True, help="Webapp ID to retrieve")
    @click.option(
        "--format",
        "format_output",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
    )
    def get_webapp(webapp_id: str, format_output: str) -> None:
        """Show webapp metadata."""
        try:
            base = _get_webapp_base_url()
            resp = requests.get(
                f"{base}/webapps/{webapp_id}",
                headers=get_headers("application/json"),
                verify=get_ssl_verify(),
            )
            resp.raise_for_status()
            data = resp.json()
            if data.get("type", "") != "WebVI":
                click.echo("✗ Webapp is not a WebVI document.", err=True)
                sys.exit(ExitCodes.NOT_FOUND)
            UniversalResponseHandler.handle_get_response(resp, "webapp", format_output)
        except Exception as exc:
            handle_api_error(exc)

    @webapp.command(name="delete")
    @click.option("--id", "-i", "webapp_id", required=True, help="Webapp ID to delete")
    @click.confirmation_option(prompt="Are you sure you want to delete this webapp?")
    def delete_webapp(webapp_id: str) -> None:
        """Delete a webapp."""
        from .utils import check_readonly_mode

        check_readonly_mode("delete a webapp")

        try:
            base = _get_webapp_base_url()
            resp = requests.delete(
                f"{base}/webapps/{webapp_id}", headers=get_headers(), verify=get_ssl_verify()
            )
            # Validate response and type if possible
            try:
                data = resp.json()
                if data.get("type", "") != "WebVI":
                    click.echo("✗ Webapp is not a WebVI document.", err=True)
                    sys.exit(ExitCodes.NOT_FOUND)
            except Exception:
                # If no JSON, continue and let handler report success/failure
                pass

            # Use UniversalResponseHandler to print a friendly message
            UniversalResponseHandler.handle_delete_response(resp, "webapp", item_count=1)
        except Exception as exc:
            handle_api_error(exc)

    @webapp.command(name="open")
    @click.option("--id", "-i", "webapp_id", required=True, help="Webapp ID to open in browser")
    def open_webapp(webapp_id: str) -> None:
        """Open a webapp in the browser."""
        import webbrowser

        try:
            base = _get_webapp_base_url()
            resp = requests.get(
                f"{base}/webapps/{webapp_id}",
                headers=get_headers("application/json"),
                verify=get_ssl_verify(),
            )
            resp.raise_for_status()
            data = resp.json()
            app_url = _build_published_webapp_url(
                webapp_id,
                webapp_name=str(data.get("name", "")),
                workspace_id=str(data.get("workspace", "")),
                properties=data.get("properties", {}),
            )
            if app_url:
                webbrowser.open(app_url)
                click.echo(f"✓ Opening: {app_url}")
                return
        except Exception as exc:
            handle_api_error(exc)

    @webapp.command(name="publish")
    @click.argument(
        "source",
        type=click.Path(exists=True, path_type=Path),
    )
    @click.option(
        "--id",
        "-i",
        "webapp_id",
        default="",
        help="Existing webapp ID to upload content to",
    )
    @click.option(
        "--name",
        "-n",
        "name",
        default="",
        help="Create a new webapp with this name before publishing",
    )
    @click.option(
        "--workspace",
        "-w",
        "workspace",
        default="Default",
        help="Workspace name or ID for new webapp",
    )
    def publish(source: Path, webapp_id: str, name: str, workspace: str) -> None:
        """Publish a .nipkg (or folder) to the WebApp service.

        SOURCE may be a .nipkg file or a folder. If a folder is provided it will be
        packed into a .nipkg archive prior to upload.
        """
        from .utils import check_readonly_mode

        check_readonly_mode("publish a web application")

        tmp_file: Optional[Path] = None
        try:
            # If folder, pack it first using a context-managed TemporaryDirectory
            if source.is_dir():
                click.echo("Packing folder into .nipkg...")
                # Keep the TemporaryDirectory alive for the duration of the
                # metadata creation and upload so the packaged file remains
                # available. The context manager will ensure cleanup afterwards.
                with tempfile.TemporaryDirectory() as _tmp_dir:
                    tmp_dir = Path(_tmp_dir)
                    suggested = tmp_dir / (sanitize_filename(source.name) + ".nipkg")
                    packaged = _pack_folder_to_nipkg(source, suggested)
                    tmp_file = packaged
                    created_workspace_id = ""

                    # If no webapp id provided create webapp metadata using name
                    base = _get_webapp_base_url()
                    if not webapp_id:
                        if not name:
                            click.echo("✗ Must provide --id or --name to publish.", err=True)
                            sys.exit(ExitCodes.INVALID_INPUT)
                        ws_id = get_workspace_id_with_fallback(
                            get_effective_workspace(workspace) or workspace
                        )
                        created_workspace_id = ws_id
                        payload = {
                            "name": name,
                            "type": "WebVI",
                            "workspace": ws_id,
                            "policyIds": [],
                            "properties": {},
                        }
                        resp_create = requests.post(
                            f"{base}/webapps",
                            headers=get_headers("application/json"),
                            json=payload,
                            verify=get_ssl_verify(),
                        )
                        resp_create.raise_for_status()
                        created = resp_create.json()
                        webapp_id = created.get("id")
                        if not webapp_id:
                            click.echo("✗ Failed to create webapp metadata.", err=True)
                            sys.exit(ExitCodes.GENERAL_ERROR)
                        click.echo(f"✓ Created webapp metadata: {webapp_id}")

                    # Upload content (binary). Use requests.put because content may be binary.
                    with open(packaged, "rb") as f:  # type: ignore[arg-type]
                        data = f.read()

                    upload_headers = get_headers("application/octet-stream")
                    url = f"{base}/webapps/{webapp_id}/content"
                    resp = requests.put(
                        url, headers=upload_headers, data=data, verify=get_ssl_verify()
                    )
                    if resp.status_code in (200, 201, 204):
                        workspace_name_hint = (
                            get_effective_workspace(workspace) or workspace
                            if created_workspace_id
                            else ""
                        )
                        published_url = _build_published_webapp_url(
                            webapp_id,
                            webapp_name=name,
                            workspace_id=created_workspace_id,
                            workspace_name_hint=workspace_name_hint,
                        )
                        format_success(
                            "Published webapp content",
                            {
                                "Webapp ID": webapp_id,
                                "Source": str(packaged),
                                "Published URL": published_url,
                            },
                        )
                    else:
                        # Try to show body message
                        try:
                            click.echo(resp.text, err=True)
                        except Exception:
                            pass
                        click.echo("✗ Failed to upload content.", err=True)
                        sys.exit(ExitCodes.GENERAL_ERROR)
            else:
                packaged = source
                created_workspace_id = ""

                # If no webapp id provided create webapp metadata using name
                base = _get_webapp_base_url()
                if not webapp_id:
                    if not name:
                        click.echo("✗ Must provide --id or --name to publish.", err=True)
                        sys.exit(ExitCodes.INVALID_INPUT)
                    ws_id = get_workspace_id_with_fallback(
                        get_effective_workspace(workspace) or workspace
                    )
                    created_workspace_id = ws_id
                    payload = {
                        "name": name,
                        "type": "WebVI",
                        "workspace": ws_id,
                        "policyIds": [],
                        "properties": {},
                    }
                    resp_create = requests.post(
                        f"{base}/webapps",
                        headers=get_headers("application/json"),
                        json=payload,
                        verify=get_ssl_verify(),
                    )
                    resp_create.raise_for_status()
                    created = resp_create.json()
                    webapp_id = created.get("id")
                    if not webapp_id:
                        click.echo("✗ Failed to create webapp metadata.", err=True)
                        sys.exit(ExitCodes.GENERAL_ERROR)
                    click.echo(f"✓ Created webapp metadata: {webapp_id}")

                # Upload content (binary). Use requests.put because content may be binary.
                with open(packaged, "rb") as f:  # type: ignore[arg-type]
                    data = f.read()

                upload_headers = get_headers("application/octet-stream")
                url = f"{base}/webapps/{webapp_id}/content"
                resp = requests.put(url, headers=upload_headers, data=data, verify=get_ssl_verify())
                if resp.status_code in (200, 201, 204):
                    workspace_name_hint = (
                        (get_effective_workspace(workspace) or workspace)
                        if created_workspace_id
                        else ""
                    )
                    published_url = _build_published_webapp_url(
                        webapp_id,
                        webapp_name=name,
                        workspace_id=created_workspace_id,
                        workspace_name_hint=workspace_name_hint,
                    )
                    format_success(
                        "Published webapp content",
                        {
                            "Webapp ID": webapp_id,
                            "Source": str(packaged),
                            "Published URL": published_url,
                        },
                    )
                else:
                    # Try to show body message
                    try:
                        click.echo(resp.text, err=True)
                    except Exception:
                        pass
                    click.echo("✗ Failed to upload content.", err=True)
                    sys.exit(ExitCodes.GENERAL_ERROR)

            # No further action here; upload is handled in the branches above
            # (inside the TemporaryDirectory for folders, or in the file branch).

        except SystemExit:
            raise
        except Exception as exc:
            handle_api_error(exc)
        finally:
            # Cleanup temporary packaged file if we created one and it still exists.
            # In the common case the TemporaryDirectory context manager removes the
            # file for us when it exits; however, if something unusual happened and
            # the file remains, attempt to remove it here.
            try:
                if tmp_file and tmp_file.exists():
                    tmp_file.unlink()
            except Exception:
                pass
