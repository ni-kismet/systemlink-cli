"""Script to build the slcli binary using PyInstaller."""

import os
import subprocess
import sys
from pathlib import Path

import tomllib

# This script is intended to be run as a Poetry script:
# > poetry run build-pyinstaller


def generate_version_file():
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

    with open(version_file_path, "w") as f:
        f.write(version_content)

    print(f"Generated _version.py with version {version}")
    return version


def main():
    """Build the slcli binary using PyInstaller."""
    # Generate version file first
    version = generate_version_file()

    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    entry_point = os.path.join(project_root, "slcli", "__main__.py")
    examples_dir = os.path.join(project_root, "slcli", "examples")
    editor_assets_dir = os.path.join(project_root, "dff-editor")

    if not os.path.isdir(examples_dir):
        print(f"Examples directory not found at {examples_dir}")
        sys.exit(1)

    if not os.path.isdir(editor_assets_dir):
        print(f"Editor assets directory not found at {editor_assets_dir}")
        sys.exit(1)

    examples_data_arg = f"{examples_dir}{os.pathsep}slcli/examples"
    editor_data_arg = f"{editor_assets_dir}{os.pathsep}dff-editor"
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name=slcli",
        "--noconfirm",
        "--collect-submodules=shellingham",
        "--collect-data=rfc3987_syntax",
        "--add-data",
        examples_data_arg,
        "--add-data",
        editor_data_arg,
        entry_point,
    ]
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print("PyInstaller build failed.")
        sys.exit(result.returncode)
    print(f"PyInstaller build completed for version {version}.")


if __name__ == "__main__":
    main()
