"""Grade all available runs in an slcli eval iteration workspace."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from slcli.skills.slcli.scripts.grade_eval_response import gather_response_text, grade_response


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    skill_dir = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(
        description="Grade every populated run directory in an slcli eval iteration."
    )
    parser.add_argument(
        "iteration_dir",
        type=Path,
        help="Path to an iteration-N directory created by prepare_eval_workspace.py.",
    )
    parser.add_argument(
        "--evals",
        type=Path,
        default=skill_dir / "evals" / "evals.json",
        help="Path to evals.json.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Recompute grading.json even if it already exists.",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict:
    """Load a JSON file into a dict."""
    return json.loads(path.read_text(encoding="utf-8"))


def iter_run_dirs(iteration_dir: Path) -> list[tuple[int, Path]]:
    """Yield eval_id and run directory pairs for all prepared runs."""
    run_pairs: list[tuple[int, Path]] = []
    for eval_dir in sorted(iteration_dir.glob("eval-*")):
        metadata_path = eval_dir / "eval_metadata.json"
        if not metadata_path.exists():
            continue
        eval_id = int(load_json(metadata_path)["eval_id"])
        for config_dir in sorted(eval_dir.iterdir()):
            if not config_dir.is_dir():
                continue
            for run_dir in sorted(config_dir.glob("run-*")):
                run_pairs.append((eval_id, run_dir))
    return run_pairs


def grade_run(manifest_path: Path, eval_id: int, run_dir: Path, force: bool) -> str:
    """Grade one run directory if response artifacts exist."""
    output_path = run_dir / "grading.json"
    if output_path.exists() and not force:
        return f"skip {run_dir}: grading.json exists"

    response_dir = run_dir / "outputs"
    if not response_dir.exists():
        return f"skip {run_dir}: outputs directory missing"

    try:
        gather_response_text(response_dir)
    except ValueError:
        return f"skip {run_dir}: no readable response artifacts"

    timing_path = run_dir / "timing.json"
    graded = grade_response(manifest_path, eval_id, response_dir, timing_path)
    output_path.write_text(json.dumps(graded, indent=2) + "\n", encoding="utf-8")
    return f"graded {run_dir}"


def main() -> None:
    """Entry point."""
    args = parse_args()
    messages: list[str] = []
    graded_count = 0
    skipped_count = 0

    for eval_id, run_dir in iter_run_dirs(args.iteration_dir):
        message = grade_run(args.evals, eval_id, run_dir, args.force)
        messages.append(message)
        if message.startswith("graded "):
            graded_count += 1
        else:
            skipped_count += 1

    for message in messages:
        print(message)
    print(f"summary: graded={graded_count} skipped={skipped_count}")


if __name__ == "__main__":
    main()
