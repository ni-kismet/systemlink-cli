"""Builds Homebrew formula for slcli with platform-specific binaries."""

import subprocess
import sys
from pathlib import Path

import toml

ROOT = Path(__file__).parent.parent.resolve()
DIST = ROOT / "dist"
LINUX_TARBALL = DIST / "slcli-linux.tar.gz"
MACOS_TARBALL = DIST / "slcli-macos.tar.gz"
FORMULA_TEMPLATE = ROOT / "scripts" / "homebrew-slcli.rb.j2"
DIST_FORMULA = DIST / "homebrew-slcli.rb"
PYPROJECT = ROOT / "pyproject.toml"


def get_version():
    """Extract the version from pyproject.toml."""
    data = toml.load(PYPROJECT)
    return data["tool"]["poetry"]["version"]


def compute_sha256(tarball_path):
    """Compute the SHA256 checksum of a tarball."""
    if not tarball_path.exists():
        print(f"Error: {tarball_path} not found.")
        sys.exit(1)
    result = subprocess.run(
        ["shasum", "-a", "256", str(tarball_path)], capture_output=True, text=True
    )
    sha256 = result.stdout.split()[0]
    print(f"SHA256 for {tarball_path.name}: {sha256}")
    return sha256


def render_formula(sha256_linux, sha256_macos, version):
    """Render the Homebrew formula from the template and write to dist/homebrew-slcli.rb."""
    if not FORMULA_TEMPLATE.exists():
        print(f"Error: {FORMULA_TEMPLATE} not found.")
        sys.exit(1)
    template = FORMULA_TEMPLATE.read_text()
    rendered = (
        template.replace("{{ sha256_linux }}", sha256_linux)
        .replace("{{ sha256_macos }}", sha256_macos)
        .replace("{{ version }}", version)
    )
    DIST_FORMULA.write_text(rendered)
    print(f"Wrote Homebrew formula to {DIST_FORMULA}")


def main():
    """Build the Homebrew formula for slcli with platform-specific binaries."""
    version = get_version()

    # Compute SHA256 for both platform tarballs
    sha256_linux = compute_sha256(LINUX_TARBALL)
    sha256_macos = compute_sha256(MACOS_TARBALL)

    # Render the formula
    render_formula(sha256_linux, sha256_macos, version)
    print("Homebrew formula build complete.")


if __name__ == "__main__":
    main()
