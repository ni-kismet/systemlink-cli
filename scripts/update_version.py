"""Script for semantic release to update _version.py after version bump."""

import sys
from pathlib import Path

import tomllib


def main():
    """Update _version.py file after semantic release version bump."""
    project_root = Path(__file__).parent.parent
    pyproject_path = project_root / "pyproject.toml"
    version_file_path = project_root / "slcli" / "_version.py"

    # Read version from pyproject.toml
    try:
        with open(pyproject_path, "rb") as f:
            pyproject_data = tomllib.load(f)

        version = pyproject_data["tool"]["poetry"]["version"]
        print(f"Updating _version.py with version {version}")

        # Write _version.py file
        version_content = f'''"""Version information for slcli."""

# This file is auto-generated. Do not edit manually.
__version__ = "{version}"
'''

        with open(version_file_path, "w") as f:
            f.write(version_content)

        print(f"Successfully updated _version.py with version {version}")

    except Exception as e:
        print(f"Error updating _version.py: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
