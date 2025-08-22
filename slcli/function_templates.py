"""Helpers for initializing local function templates (TypeScript / Python).

This module encapsulates downloading and extracting subfolders from the
SystemLink Enterprise examples repository, adding safety checks against
path traversal, symlinks, and unexpected archive contents.
"""

from __future__ import annotations

import io
import sys
import tarfile
from pathlib import Path
from typing import Dict

import click
import requests

from .utils import ExitCodes

TEMPLATE_REPO = "ni/systemlink-enterprise-examples"
TEMPLATE_BRANCH = "function-examples"  # Treated as stable per user direction
TEMPLATE_SUBFOLDERS: Dict[str, str] = {
    "typescript": "function-examples/typescript-hono-function",
    "python": "function-examples/python-http-function",
}

_DOWNLOAD_TIMEOUT_SECONDS = 60


def download_and_extract_template(language: str, destination: Path) -> None:
    """Download and extract the specified language template into destination.

    Args:
        language: Normalized language key ('typescript' or 'python').
        destination: Directory to populate (must already exist).
    """
    if language not in TEMPLATE_SUBFOLDERS:
        click.echo(f"✗ Unsupported template language: {language}", err=True)
        sys.exit(ExitCodes.INVALID_INPUT)

    subfolder = TEMPLATE_SUBFOLDERS[language]
    tarball_url = f"https://codeload.github.com/{TEMPLATE_REPO}/tar.gz/{TEMPLATE_BRANCH}"
    resp = None
    try:
        resp = requests.get(tarball_url, timeout=_DOWNLOAD_TIMEOUT_SECONDS)
    except requests.RequestException as exc:  # noqa: BLE001
        click.echo(f"✗ Network error downloading template: {exc}", err=True)
        sys.exit(ExitCodes.NETWORK_ERROR)
    if resp.status_code != 200:
        click.echo(
            f"✗ Failed to download template (HTTP {resp.status_code}) from {tarball_url}",
            err=True,
        )
        sys.exit(ExitCodes.NETWORK_ERROR)

    try:
        with tarfile.open(fileobj=io.BytesIO(resp.content), mode="r:gz") as tf:  # type: ignore[arg-type]
            for member in tf.getmembers():
                # Skip symlinks / hard links for safety
                if member.issym() or member.islnk():  # pragma: no cover - defensive
                    continue
                parts = member.name.split("/", 1)
                if len(parts) < 2:
                    continue
                remainder = parts[1]
                if not remainder.startswith(subfolder.rstrip("/")):
                    continue
                # Compute relative path inside desired subfolder
                relative_path = Path(remainder).relative_to(subfolder)
                if any(p == ".." for p in relative_path.parts):  # Path traversal guard
                    continue
                target_path = destination / relative_path
                if member.isdir():
                    target_path.mkdir(parents=True, exist_ok=True)
                    continue
                target_path.parent.mkdir(parents=True, exist_ok=True)
                extracted = tf.extractfile(member)
                if not extracted:
                    continue
                with open(target_path, "wb") as f_out:
                    f_out.write(extracted.read())
    except Exception as exc:  # noqa: BLE001
        click.echo(f"✗ Error extracting template: {exc}", err=True)
        sys.exit(ExitCodes.GENERAL_ERROR)
