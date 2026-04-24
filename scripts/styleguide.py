"""Repository-local replacement for the ni-python-styleguide command."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import Sequence


REPO_ROOT = Path(__file__).resolve().parent.parent
FLAKE8_CONFIG = REPO_ROOT / ".flake8"
PYPROJECT = REPO_ROOT / "pyproject.toml"
DEFAULT_EXCLUDE = "__pycache__,.git,.venv"


def _run(cmd: Sequence[str]) -> int:
    """Run a subprocess and return its exit code."""
    proc = subprocess.run(list(cmd), stdout=sys.stdout, stderr=sys.stderr)  # noqa: S603,S607
    return proc.returncode


def _verbosity_args(verbose: int, quiet: int) -> list[str]:
    """Convert verbosity counters into a flake8-compatible flag."""
    level = verbose - quiet
    if level > 0:
        return [f"-{'v' * level}"]
    if level < 0:
        return [f"-{'q' * abs(level)}"]
    return []


def _targets(paths: Sequence[str]) -> list[str]:
    """Return the lint targets, defaulting to the repository root."""
    return list(paths) if paths else ["."]


def _exclude_args(exclude: str, extend_exclude: str) -> list[str]:
    """Merge default and extended exclude patterns."""
    merged = ",".join(part for part in [exclude.strip(","), extend_exclude.strip(",")] if part)
    return [f"--exclude={merged}"] if merged else []


def _run_lint(args: argparse.Namespace) -> int:
    """Execute flake8 with the repository's style configuration."""
    cmd = [
        sys.executable,
        "-m",
        "flake8",
        f"--config={FLAKE8_CONFIG}",
        f"--black-config={PYPROJECT}",
        *_verbosity_args(args.verbose, args.quiet),
        *_exclude_args(args.exclude, args.extend_exclude),
    ]
    if args.format:
        cmd.append(f"--format={args.format}")
    if args.extend_ignore:
        cmd.append(f"--extend-ignore={args.extend_ignore}")
    cmd.extend(_targets(args.paths))
    return _run(cmd)


def _run_fix(args: argparse.Namespace) -> int:
    """Format imports and code using isort and black."""
    targets = _targets(args.paths)
    exit_code = 0

    isort_cmd = [sys.executable, "-m", "isort", f"--settings-path={PYPROJECT}", *targets]
    if _run(isort_cmd) != 0:
        exit_code = 1

    black_cmd = [sys.executable, "-m", "black", f"--config={PYPROJECT}", *targets]
    if _run(black_cmd) != 0:
        exit_code = 1

    return exit_code


def _build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""
    parser = argparse.ArgumentParser(prog="ni-python-styleguide")
    parser.add_argument("-v", "--verbose", action="count", default=0)
    parser.add_argument("-q", "--quiet", action="count", default=0)
    parser.add_argument("--exclude", default=DEFAULT_EXCLUDE)
    parser.add_argument("--extend-exclude", default="")

    subparsers = parser.add_subparsers(dest="command", required=True)

    lint_parser = subparsers.add_parser("lint")
    lint_parser.add_argument("--format")
    lint_parser.add_argument("--extend-ignore")
    lint_parser.add_argument("paths", nargs="*")
    lint_parser.set_defaults(handler=_run_lint)

    fix_parser = subparsers.add_parser("fix")
    fix_parser.add_argument("--extend-ignore")
    fix_parser.add_argument("paths", nargs="*")
    fix_parser.set_defaults(handler=_run_fix)

    return parser


def main() -> None:
    """Run the repository-local styleguide command."""
    parser = _build_parser()
    args = parser.parse_args()
    sys.exit(args.handler(args))


if __name__ == "__main__":  # pragma: no cover
    main()
