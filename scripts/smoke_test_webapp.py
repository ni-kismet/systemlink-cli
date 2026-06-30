"""Generate and build a temporary hosted Angular webapp as a smoke test."""

import argparse
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Sequence


def _run_command(command: Sequence[str], cwd: Path | None = None) -> None:
    """Run a command and exit immediately if it fails."""
    result = subprocess.run(list(command), cwd=cwd, check=False)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def smoke_test_webapp(workspace_dir: Path, app_name: str) -> None:
    """Generate a hosted Angular webapp and verify it installs and builds."""
    _run_command(
        [
            sys.executable,
            "-m",
            "slcli",
            "webapp",
            "new",
            app_name,
            "--directory",
            str(workspace_dir),
            "--skip-install",
        ]
    )
    _run_command(["npm", "install"], cwd=workspace_dir)
    _run_command(["npm", "run", "build"], cwd=workspace_dir)


def _parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments for the webapp smoke test."""
    parser = argparse.ArgumentParser(
        description="Generate a hosted Angular webapp and verify npm install/build.",
    )
    parser.add_argument(
        "--app-name",
        default="smoke-check",
        help="App name to pass to `slcli webapp new`.",
    )
    parser.add_argument(
        "--directory",
        type=Path,
        default=None,
        help="Optional output directory to keep after the smoke test completes.",
    )
    return parser.parse_args(list(argv) if argv is not None else None)


def main(argv: Sequence[str] | None = None) -> None:
    """Run the hosted webapp smoke-build flow."""
    args = _parse_args(argv)

    if args.directory is not None:
        smoke_test_webapp(args.directory.resolve(), args.app_name)
        return

    with tempfile.TemporaryDirectory(prefix="slcli-webapp-smoke-") as temp_dir:
        smoke_test_webapp(Path(temp_dir) / args.app_name, args.app_name)


if __name__ == "__main__":
    main()
