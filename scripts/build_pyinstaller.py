"""Script to build the slcli binary using PyInstaller."""

import os
import subprocess
import sys
import tomllib
from pathlib import Path

# This script is intended to be run as a Poetry script:
# > poetry run build-pyinstaller


def generate_version_file() -> str:
    """Generate _version.py file from pyproject.toml."""
    project_root = Path(__file__).parent.parent
    pyproject_path = project_root / "pyproject.toml"
    version_file_path = project_root / "slcli" / "_version.py"

    # Read version from pyproject.toml
    with open(pyproject_path, "rb") as f:
        pyproject_data = tomllib.load(f)

    version = pyproject_data["tool"]["poetry"]["version"]

    # Write _version.py file
    version_content = f'''"""Version information for slcli."""

# This file is auto-generated during build. Do not edit manually.
__version__ = "{version}"
'''

    with open(version_file_path, "w", encoding="utf-8") as f:
        f.write(version_content)

    print(f"Generated _version.py with version {version}")
    return version


def _required_data_args(source_dir: Path, target_dir: str) -> list[str]:
    """Return PyInstaller --add-data args for a required directory."""
    if not source_dir.is_dir():
        print(f"Required data directory not found at {source_dir}")
        sys.exit(1)

    return ["--add-data", f"{source_dir}{os.pathsep}{target_dir}"]


def _optional_data_args(source_dir: Path, target_dir: str) -> list[str]:
    """Return PyInstaller --add-data args for an optional directory."""
    if not source_dir.is_dir():
        print(f"Skipping optional data directory missing at {source_dir}")
        return []

    return ["--add-data", f"{source_dir}{os.pathsep}{target_dir}"]


def main() -> None:
    """Build the slcli binary using PyInstaller."""
    # Generate version file first
    version = generate_version_file()

    project_root = Path(__file__).resolve().parent.parent
    entry_point = project_root / "slcli" / "__main__.py"
    examples_dir = project_root / "slcli" / "examples"
    editor_assets_dir = project_root / "dff-editor"
    skills_dir = project_root / "slcli" / "skills"
    webapp_templates_dir = project_root / "slcli" / "webapp_templates"

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name=slcli",
        "--noconfirm",
        "--collect-submodules=shellingham",
        "--collect-data=rfc3987_syntax",
        *_required_data_args(examples_dir, "slcli/examples"),
        *_required_data_args(editor_assets_dir, "dff-editor"),
        *_required_data_args(webapp_templates_dir, "slcli/webapp_templates"),
        *_optional_data_args(skills_dir, "skills"),
        str(entry_point),
    ]
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print("PyInstaller build failed.")
        sys.exit(result.returncode)
    print(f"PyInstaller build completed for version {version}.")


if __name__ == "__main__":
    main()
