"""Builds a Scoop manifest for the slcli Windows binary and writes it to dist/scoop-slcli.json."""

import subprocess
import sys
from pathlib import Path

import toml

ROOT = Path(__file__).parent.parent.resolve()
DIST = ROOT / "dist"
SLCLI_EXE = DIST / "slcli.exe"
MANIFEST_TEMPLATE = ROOT / "scripts" / "scoop-slcli.json.j2"
DIST_MANIFEST = DIST / "scoop-slcli.json"
PYPROJECT = ROOT / "pyproject.toml"


def run(cmd, **kwargs):
    """Run a shell command and print it."""
    print(f"$ {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    subprocess.run(cmd, check=True, **kwargs)


def compute_sha256():
    """Compute the SHA256 checksum of the slcli.exe binary."""
    result = subprocess.run(
        [
            "powershell",
            "-Command",
            f"Get-FileHash -Algorithm SHA256 '{SLCLI_EXE}' | Select-Object -ExpandProperty Hash",
        ],
        capture_output=True,
        text=True,
    )
    sha256 = result.stdout.strip()
    print(f"SHA256 for Scoop manifest: {sha256}")
    return sha256


def get_version():
    """Extract the version from pyproject.toml."""
    data = toml.load(PYPROJECT)
    return data["tool"]["poetry"]["version"]


def render_manifest(version, url, sha256):
    """Render the Scoop manifest from the template and write to dist/scoop-slcli.json."""
    if not MANIFEST_TEMPLATE.exists():
        print(f"Error: {MANIFEST_TEMPLATE} not found.")
        sys.exit(1)
    template = MANIFEST_TEMPLATE.read_text()
    rendered = (
        template.replace("{{ version }}", version)
        .replace("{{ url }}", url)
        .replace("{{ sha256 }}", sha256)
    )
    DIST_MANIFEST.write_text(rendered)
    print(f"Wrote Scoop manifest to {DIST_MANIFEST}")


def main():
    """Build and render the Scoop manifest for slcli."""
    version = get_version()
    url = f"https://github.com/ni/systemlink-cli/releases/download/v{version}/slcli.exe"
    sha256 = compute_sha256()
    render_manifest(version, url, sha256)
    print("Scoop manifest build complete.")


if __name__ == "__main__":
    main()
