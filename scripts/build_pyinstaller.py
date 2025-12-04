"""Script to build the slcli binary using PyInstaller.

Includes macOS code signing support for keychain access.
"""

import os
import platform
import subprocess
import sys
from pathlib import Path

import tomllib

# This script is intended to be run as a Poetry script:
# > poetry run build-pyinstaller


def generate_version_file() -> str:
    """Generate _version.py file from pyproject.toml.

    Returns:
        The version string extracted from pyproject.toml.
    """
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


def sign_macos_binary(binary_path: Path, entitlements_path: Path) -> bool:
    """Sign a macOS binary with entitlements for keychain access.

    Uses the MACOS_SIGNING_IDENTITY environment variable for the signing identity.
    If not set, attempts ad-hoc signing (which allows local testing but won't
    work for distribution).

    Args:
        binary_path: Path to the binary to sign.
        entitlements_path: Path to the entitlements plist file.

    Returns:
        True if signing succeeded, False otherwise.
    """
    signing_identity = os.environ.get("MACOS_SIGNING_IDENTITY", "-")

    if signing_identity == "-":
        print("No MACOS_SIGNING_IDENTITY set, using ad-hoc signing.")
        print("Note: Ad-hoc signed binaries may have limited keychain access.")
    else:
        print(f"Signing with identity: {signing_identity}")

    # Sign the binary with entitlements
    cmd = [
        "codesign",
        "--force",
        "--options",
        "runtime",
        "--entitlements",
        str(entitlements_path),
        "--sign",
        signing_identity,
        "--deep",
        str(binary_path),
    ]

    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)

    if result.returncode != 0:
        print(f"Code signing failed: {result.stderr}")
        return False

    print(f"Successfully signed: {binary_path}")

    # Verify the signature
    verify_cmd = ["codesign", "--verify", "--verbose", str(binary_path)]
    verify_result = subprocess.run(verify_cmd, capture_output=True, text=True)

    if verify_result.returncode != 0:
        print(f"Signature verification failed: {verify_result.stderr}")
        return False

    print("Signature verified successfully.")
    return True


def sign_macos_app_bundle(dist_path: Path, entitlements_path: Path) -> bool:
    """Sign all binaries in the PyInstaller output directory.

    PyInstaller creates a directory with the main binary and supporting files.
    We need to sign the main binary and any embedded frameworks/dylibs.

    Args:
        dist_path: Path to the dist/slcli directory.
        entitlements_path: Path to the entitlements plist file.

    Returns:
        True if all signing succeeded, False otherwise.
    """
    slcli_dir = dist_path / "slcli"
    if not slcli_dir.exists():
        print(f"Error: {slcli_dir} does not exist.")
        return False

    # Find all binaries to sign (main executable and dylibs)
    main_binary = slcli_dir / "slcli"
    if not main_binary.exists():
        print(f"Error: Main binary {main_binary} not found.")
        return False

    # Sign embedded libraries first (if any), then the main binary
    # This is important because the main binary's signature includes hashes of embedded code
    dylibs = list(slcli_dir.rglob("*.dylib")) + list(slcli_dir.rglob("*.so"))
    frameworks = list(slcli_dir.rglob("*.framework"))

    signing_identity = os.environ.get("MACOS_SIGNING_IDENTITY", "-")

    # Sign dylibs and shared objects
    for lib in dylibs:
        cmd = [
            "codesign",
            "--force",
            "--sign",
            signing_identity,
            str(lib),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Warning: Failed to sign {lib}: {result.stderr}")
            # Continue anyway, some libraries may not need signing

    # Sign frameworks
    for framework in frameworks:
        cmd = [
            "codesign",
            "--force",
            "--sign",
            signing_identity,
            "--deep",
            str(framework),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            print(f"Warning: Failed to sign {framework}: {result.stderr}")

    # Sign the main binary with entitlements
    return sign_macos_binary(main_binary, entitlements_path)


def main() -> None:
    """Build the slcli binary using PyInstaller."""
    # Generate version file first
    version = generate_version_file()

    project_root = Path(__file__).parent.parent
    entry_point = project_root / "slcli" / "__main__.py"
    dist_path = project_root / "dist"

    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--name=slcli",
        "--noconfirm",
        "--collect-submodules=shellingham",
        str(entry_point),
    ]
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd)
    if result.returncode != 0:
        print("PyInstaller build failed.")
        sys.exit(result.returncode)
    print(f"PyInstaller build completed for version {version}.")

    # On macOS, sign the binary for keychain access
    if platform.system() == "Darwin":
        print("\nSigning macOS binary for keychain access...")
        entitlements_path = project_root / "scripts" / "entitlements.plist"

        if not entitlements_path.exists():
            print(f"Warning: Entitlements file not found at {entitlements_path}")
            print("Skipping code signing.")
        else:
            success = sign_macos_app_bundle(dist_path, entitlements_path)
            if not success:
                print("Warning: Code signing failed. Keychain access may not work.")
                # Don't fail the build, just warn
            else:
                print("macOS code signing completed successfully.")


if __name__ == "__main__":
    main()
