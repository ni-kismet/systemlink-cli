"""Render a static eval review page for an slcli iteration workspace."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parents[3]

    parser = argparse.ArgumentParser(
        description="Generate a static HTML review page for an iteration workspace."
    )
    parser.add_argument(
        "iteration_dir",
        type=Path,
        help="Path to an iteration-N directory.",
    )
    parser.add_argument(
        "--skill-name",
        default="slcli",
        help="Skill name shown in the review UI.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Output HTML path. Defaults to <iteration_dir>/review.html.",
    )
    parser.add_argument(
        "--previous-workspace",
        type=Path,
        help="Optional previous iteration workspace for side-by-side review context.",
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Python executable to use for the upstream viewer script.",
    )
    parser.add_argument(
        "--viewer-script",
        type=Path,
        default=repo_root
        / ".github"
        / "skills"
        / "skill-creator"
        / "eval-viewer"
        / "generate_review.py",
        help="Path to the upstream generate_review.py script.",
    )
    return parser.parse_args()


def main() -> None:
    """Entry point."""
    args = parse_args()
    output_path = args.output or (args.iteration_dir / "review.html")
    benchmark_path = args.iteration_dir / "benchmark.json"

    command = [
        args.python,
        str(args.viewer_script),
        str(args.iteration_dir),
        "--skill-name",
        args.skill_name,
        "--benchmark",
        str(benchmark_path),
        "--static",
        str(output_path),
    ]
    if args.previous_workspace:
        command.extend(["--previous-workspace", str(args.previous_workspace)])

    subprocess.run(command, check=True)


if __name__ == "__main__":
    main()
