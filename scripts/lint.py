"""Convenience script to run style linting and formatting.

Default (no flags):
    - Run style guide lint checks (non-modifying)
    - Run black in check mode (no file changes)

With --fix:
    - Run style guide lint checks (still non-modifying; separate fixer not provided)
    - Run black to auto-format the codebase

Equivalent commands:
    Check: ni-python-styleguide lint && black --check .
    Fix:   ni-python-styleguide lint && black .

Exposed as `poetry run lint` via pyproject.toml.
"""

from __future__ import annotations

import subprocess
import sys
from typing import List


def _run(cmd: List[str]) -> int:
    """Run a subprocess command and return its exit code."""
    proc = subprocess.run(cmd, stdout=sys.stdout, stderr=sys.stderr)  # noqa: S603,S607
    return proc.returncode


def main() -> None:
    """Execute lint steps; optionally format when --fix provided."""
    fix = "--fix" in sys.argv[1:]
    # Remove our flag so tools don't see it
    if fix:
        sys.argv = [sys.argv[0]] + [a for a in sys.argv[1:] if a != "--fix"]

    code = 0
    # Lint (non-modifying)
    if _run([sys.executable, "-m", "ni_python_styleguide", "lint"]) != 0:
        code = 1

    # Formatting
    black_cmd = [sys.executable, "-m", "black"]
    if fix:
        black_cmd.append(".")
    else:
        black_cmd.extend(["--check", "."])

    if _run(black_cmd) != 0:
        code = 1

    sys.exit(code)


if __name__ == "__main__":  # pragma: no cover
    main()
