"""Build a Chocolatey package for slcli (nupkg) using remote artifact download model.

Steps:
1. Ensure dist/slcli.zip (Windows binary zip) exists or has been uploaded to release.
2. Read version from pyproject.toml.
3. Copy nuspec & tools scripts to a temp build dir (or pack in place) and run `choco pack`.
4. Output .nupkg to dist/.

This script expects to run on Windows with Chocolatey available in PATH.
"""

from __future__ import annotations

import hashlib
import shutil
import subprocess
import sys
from pathlib import Path

import toml

ROOT = Path(__file__).parent.parent.resolve()
DIST = ROOT / "dist"
PYPROJECT = ROOT / "pyproject.toml"
CHOCO_DIR = ROOT / "packaging" / "choco"
NUSPEC = CHOCO_DIR / "slcli.nuspec"


def get_version() -> str:
    """Return project version from pyproject.toml."""
    data = toml.load(PYPROJECT)
    return data["tool"]["poetry"]["version"]


def ensure_dist() -> None:
    """Ensure dist directory exists."""
    DIST.mkdir(parents=True, exist_ok=True)


def prepare_nuspec(version: str, work_dir: Path) -> Path:
    """Copy nuspec and replace $version$ token.

    Args:
        version: semantic version string
        work_dir: working temp directory
    Returns:
        Path to prepared nuspec
    """
    target = work_dir / "slcli.nuspec"
    content = NUSPEC.read_text(encoding="utf-8").replace("$version$", version)
    target.write_text(content, encoding="utf-8")
    return target


def copy_tools(work_dir: Path) -> Path:
    """Copy Chocolatey tools scripts into working directory and return install script path.

    Args:
        work_dir: Temporary working directory
    Returns:
        Path to chocolateyinstall.ps1 inside work_dir
    """
    tools_src = CHOCO_DIR / "tools"
    tools_dest = work_dir / "tools"
    shutil.copytree(tools_src, tools_dest)
    return tools_dest / "chocolateyinstall.ps1"


def compute_sha256(file_path: Path) -> str:
    """Compute SHA256 hex digest for given file.

    Args:
        file_path: Path to file
    Returns:
        Lowercase hex digest string
    """
    h = hashlib.sha256()
    with file_path.open("rb") as f:  # pragma: no cover - simple IO
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def inject_checksum(install_script: Path, checksum: str) -> None:
    """Replace $checksum$ token in install script with actual checksum.

    Args:
        install_script: Path to chocolateyinstall.ps1 in temp work dir
        checksum: SHA256 digest for slcli.zip
    """
    content = install_script.read_text(encoding="utf-8")
    if "$checksum$" not in content:
        print("Warning: checksum token not found in install script", file=sys.stderr)
        return
    content = content.replace("$checksum$", checksum)
    install_script.write_text(content, encoding="utf-8")


def run_choco_pack(work_dir: Path) -> Path:
    """Run `choco pack` and return path to generated nupkg or exit on failure."""
    result = subprocess.run(["choco", "pack"], cwd=work_dir, text=True, stdout=sys.stdout, stderr=sys.stderr)
    if result.returncode != 0:
        print("choco pack failed", file=sys.stderr)
        sys.exit(result.returncode)
    pkgs = list(work_dir.glob("*.nupkg"))
    if not pkgs:
        print("No nupkg produced", file=sys.stderr)
        sys.exit(1)
    return pkgs[0]


def main() -> None:
    """Entry point: prepare temp build area, pack nupkg, move to dist."""
    version = get_version()
    ensure_dist()
    work_dir = DIST / f"choco-build-{version}"
    if work_dir.exists():
        shutil.rmtree(work_dir)
    work_dir.mkdir(parents=True)

    prepare_nuspec(version, work_dir)
    install_script = copy_tools(work_dir)

    # Compute checksum of pre-built Windows zip (expected in dist/) and inject
    zip_path = DIST / "slcli.zip"
    if not zip_path.exists():
        print("Expected dist/slcli.zip to exist before Chocolatey packaging", file=sys.stderr)
        sys.exit(1)
    checksum = compute_sha256(zip_path)
    inject_checksum(install_script, checksum)

    print(f"Injected SHA256 checksum {checksum} into install script")

    print(f"Packing Chocolatey package for version {version}")
    nupkg = run_choco_pack(work_dir)
    final = DIST / nupkg.name
    shutil.move(str(nupkg), final)
    print(f"Created {final}")

    print(
        "To publish (CI): choco push",
        final.name,
        "--source https://push.chocolatey.org/ --api-key ****",
    )


if __name__ == "__main__":  # pragma: no cover
    main()
