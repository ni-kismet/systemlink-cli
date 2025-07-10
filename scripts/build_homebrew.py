"""Builds a Homebrew tarball for the slcli PyInstaller binary and updates the formula."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent.resolve()
DIST = ROOT / "dist"
SLCLI_DIR = DIST / "slcli"
TARBALL = DIST / "slcli.tar.gz"
FORMULA = ROOT / "homebrew-slcli.rb"
FORMULA_TEMPLATE = ROOT / "scripts" / "homebrew-slcli.rb.j2"
DIST_FORMULA = DIST / "homebrew-slcli.rb"


def run(cmd, **kwargs):
    """Run a shell command and print it."""
    print(f"$ {' '.join(cmd) if isinstance(cmd, list) else cmd}")
    subprocess.run(cmd, check=True, **kwargs)


def build_pyinstaller():
    """Build the PyInstaller binary using Poetry."""
    run(["poetry", "run", "python", str(ROOT / "scripts" / "build_pyinstaller.py")])


def create_tarball():
    """Create a tarball from the dist/slcli directory."""
    if not SLCLI_DIR.is_dir():
        print(f"Error: {SLCLI_DIR} not found. Run the PyInstaller build first.")
        sys.exit(1)
    print(f"Creating tarball {TARBALL} ...")
    if TARBALL.exists():
        TARBALL.unlink()
    run(["tar", "-czf", str(TARBALL), "-C", str(DIST), "slcli"])


def compute_sha256():
    """Compute the SHA256 checksum of the tarball."""
    result = subprocess.run(["shasum", "-a", "256", str(TARBALL)], capture_output=True, text=True)
    sha256 = result.stdout.split()[0]
    print(f"SHA256 for Homebrew formula: {sha256}")
    return sha256


def render_formula(sha256):
    """Render the Homebrew formula from the template and write to dist/homebrew-slcli.rb."""
    if not FORMULA_TEMPLATE.exists():
        print(f"Error: {FORMULA_TEMPLATE} not found.")
        sys.exit(1)
    template = FORMULA_TEMPLATE.read_text()
    rendered = template.replace("{{ sha256 }}", sha256)
    DIST_FORMULA.write_text(rendered)
    print(f"Wrote Homebrew formula to {DIST_FORMULA}")


def update_formula(sha256):
    """Update the Homebrew formula file with the new SHA256 checksum (legacy, root)."""
    if not FORMULA.exists():
        print(f"Warning: {FORMULA} not found, skipping update.")
        return
    lines = FORMULA.read_text().splitlines()
    new_lines = []
    for line in lines:
        if line.strip().startswith("sha256 "):
            new_lines.append(f'  sha256 "{sha256}"')
        else:
            new_lines.append(line)
    FORMULA.write_text("\n".join(new_lines) + "\n")
    print(f"Updated {FORMULA} with new sha256.")


def main():
    """Build, package, and update the Homebrew formula for slcli."""
    build_pyinstaller()
    create_tarball()
    sha256 = compute_sha256()
    render_formula(sha256)
    update_formula(sha256)
    print("Homebrew tarball build complete.")


if __name__ == "__main__":
    main()
