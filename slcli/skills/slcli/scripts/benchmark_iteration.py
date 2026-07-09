"""Grade and aggregate an slcli eval iteration workspace."""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    script_dir = Path(__file__).resolve().parent
    repo_root = script_dir.parents[3]
    skill_dir = script_dir.parent

    parser = argparse.ArgumentParser(
        description="Grade an iteration and generate benchmark.json plus benchmark.md."
    )
    parser.add_argument(
        "iteration_dir",
        type=Path,
        help="Path to an iteration-N directory.",
    )
    parser.add_argument(
        "--evals",
        type=Path,
        default=skill_dir / "evals" / "evals.json",
        help="Path to evals.json.",
    )
    parser.add_argument(
        "--skill-name",
        default="slcli",
        help="Skill name recorded in benchmark metadata.",
    )
    parser.add_argument(
        "--skill-path",
        default=str(skill_dir / "SKILL.md"),
        help="Skill path recorded in benchmark metadata.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Recompute grading.json files before aggregation.",
    )
    parser.add_argument(
        "--python",
        default=sys.executable,
        help="Python executable to use for helper scripts.",
    )
    parser.add_argument(
        "--aggregate-script",
        type=Path,
        default=repo_root
        / ".github"
        / "skills"
        / "skill-creator"
        / "scripts"
        / "aggregate_benchmark.py",
        help="Path to the upstream aggregate_benchmark.py script.",
    )
    return parser.parse_args()


def run_command(command: list[str]) -> None:
    """Run a subprocess command and stream output."""
    subprocess.run(command, check=True)


def main() -> None:
    """Entry point."""
    args = parse_args()
    script_dir = Path(__file__).resolve().parent
    grade_script = script_dir / "grade_iteration.py"

    grade_command = [
        args.python,
        str(grade_script),
        str(args.iteration_dir),
        "--evals",
        str(args.evals),
    ]
    if args.force:
        grade_command.append("--force")
    run_command(grade_command)

    aggregate_command = [
        args.python,
        str(args.aggregate_script),
        str(args.iteration_dir),
        "--skill-name",
        args.skill_name,
        "--skill-path",
        args.skill_path,
    ]
    run_command(aggregate_command)


if __name__ == "__main__":
    main()
