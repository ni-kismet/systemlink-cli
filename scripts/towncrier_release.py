"""Helpers for Towncrier-based versioning and changelog releases."""

from __future__ import annotations

import argparse
import subprocess
import sys
import tomllib
from pathlib import Path
from typing import Iterable, Optional, Sequence

from packaging.version import Version

PATCH_BUMP_TYPES = {"patch", "doc", "misc"}
MINOR_BUMP_TYPES = {"minor"}
MAJOR_BUMP_TYPES = {"major"}


def read_poetry_version(pyproject_path: Path) -> str:
    """Return the current Poetry package version."""
    with pyproject_path.open("rb") as handle:
        pyproject_data = tomllib.load(handle)
    return str(pyproject_data["tool"]["poetry"]["version"])


def replace_poetry_version(pyproject_text: str, new_version: str) -> str:
    """Replace the version in the [tool.poetry] section of pyproject.toml."""
    lines = pyproject_text.splitlines(keepends=True)
    in_tool_poetry = False
    replaced = False
    updated_lines = []

    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            in_tool_poetry = stripped == "[tool.poetry]"

        if in_tool_poetry and stripped.startswith("version = "):
            newline = "\n" if line.endswith("\n") else ""
            updated_lines.append(f'version = "{new_version}"{newline}')
            replaced = True
        else:
            updated_lines.append(line)

    if not replaced:
        raise ValueError("Could not find tool.poetry.version in pyproject.toml")

    return "".join(updated_lines)


def write_poetry_version(pyproject_path: Path, new_version: str) -> None:
    """Persist the updated Poetry version to pyproject.toml."""
    updated = replace_poetry_version(pyproject_path.read_text(encoding="utf-8"), new_version)
    pyproject_path.write_text(updated, encoding="utf-8")


def write_version_file(version_file_path: Path, version: str) -> None:
    """Write the generated slcli/_version.py file."""
    version_content = f'''"""Version information for slcli."""

# This file is auto-generated. Do not edit manually.
__version__ = "{version}"
'''
    version_file_path.write_text(version_content, encoding="utf-8")


def get_fragment_type(fragment_path: Path) -> Optional[str]:
    """Extract the Towncrier fragment type from a fragment filename."""
    stem_parts = fragment_path.stem.split(".")
    if len(stem_parts) < 2:
        return None
    if stem_parts[-1].isdigit() and len(stem_parts) >= 3:
        return stem_parts[-2]
    return stem_parts[-1]


def iter_fragment_types(newsfragments_dir: Path) -> list[str]:
    """Return the configured fragment types present in the newsfragments directory."""
    if not newsfragments_dir.exists():
        return []

    fragment_types: list[str] = []
    ignored_names = {"readme", "readme.md", ".gitkeep", ".keep"}
    for fragment_path in sorted(newsfragments_dir.glob("*.md")):
        if fragment_path.name.lower() in ignored_names:
            continue
        fragment_type = get_fragment_type(fragment_path)
        if fragment_type:
            fragment_types.append(fragment_type)
    return fragment_types


def determine_version_bump(fragment_types: Iterable[str]) -> Optional[str]:
    """Determine the highest-priority version bump implied by fragment types."""
    seen = set(fragment_types)
    if seen & MAJOR_BUMP_TYPES:
        return "major"
    if seen & MINOR_BUMP_TYPES:
        return "minor"
    if seen & PATCH_BUMP_TYPES:
        return "patch"
    return None


def bump_version(current_version: str, bump: str) -> str:
    """Return the next semantic version for a major, minor, or patch bump."""
    version = Version(current_version)
    release = list(version.release)
    while len(release) < 3:
        release.append(0)

    major, minor, patch = release[:3]
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    if bump == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError(f"Unsupported bump type: {bump}")


def get_next_version(project_root: Path) -> Optional[str]:
    """Return the next version implied by the current Towncrier fragments, if any."""
    pyproject_path = project_root / "pyproject.toml"
    current_version = read_poetry_version(pyproject_path)
    fragment_types = iter_fragment_types(project_root / "newsfragments")
    bump = determine_version_bump(fragment_types)
    if bump is None:
        return None
    return bump_version(current_version, bump)


def build_changelog(project_root: Path, version: str) -> None:
    """Build CHANGELOG.md from Towncrier fragments for the specified version."""
    subprocess.run(
        [sys.executable, "-m", "towncrier", "build", "--yes", "--version", version],
        cwd=project_root,
        check=True,
    )


def apply_release(project_root: Path, version: Optional[str] = None) -> Optional[str]:
    """Apply a release: bump version files and build the changelog from Towncrier fragments."""
    next_version = version or get_next_version(project_root)
    if next_version is None:
        return None

    pyproject_path = project_root / "pyproject.toml"
    version_file_path = project_root / "slcli" / "_version.py"

    build_changelog(project_root, next_version)
    write_poetry_version(pyproject_path, next_version)
    write_version_file(version_file_path, next_version)
    return next_version


def parse_args(argv: Optional[Sequence[str]] = None) -> argparse.Namespace:
    """Parse command-line arguments for the Towncrier release helper."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-root",
        type=Path,
        default=Path(__file__).resolve().parent.parent,
        help="Project root containing pyproject.toml and newsfragments/.",
    )
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument(
        "--next-version",
        action="store_true",
        help="Print the next version implied by the current Towncrier fragments.",
    )
    mode.add_argument(
        "--apply",
        action="store_true",
        help="Apply the next release by bumping versions and building CHANGELOG.md.",
    )
    parser.add_argument(
        "--version",
        help="Explicit version to use with --apply. Defaults to the version implied by fragments.",
    )
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> None:
    """Run the Towncrier release helper."""
    args = parse_args(argv)
    project_root = args.project_root.resolve()

    if args.next_version:
        next_version = get_next_version(project_root)
        if next_version:
            print(next_version)
        return

    applied_version = apply_release(project_root, args.version)
    if applied_version:
        print(applied_version)


if __name__ == "__main__":
    main()
