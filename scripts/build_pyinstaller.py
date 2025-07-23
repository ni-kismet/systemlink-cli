"""Script to build the slcli binary using PyInstaller."""

import os
import subprocess
import sys

# This script is intended to be run as a Poetry script:
# > poetry run build-pyinstaller


def main():
    """Build the slcli binary using PyInstaller."""
    project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    entry_point = os.path.join(project_root, "slcli", "__main__.py")
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name=slcli",
        "--noconfirm",
        "--collect-submodules=shellingham",
        entry_point,
    ]
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print("PyInstaller build failed.")
        sys.exit(result.returncode)
    print("PyInstaller build completed.")


if __name__ == "__main__":
    main()
