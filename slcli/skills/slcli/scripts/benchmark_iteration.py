"""Grade and aggregate an slcli eval iteration workspace."""

from __future__ import annotations

import argparse
import json
import runpy
import subprocess
import sys
from pathlib import Path
from typing import Any, Callable, cast


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
        "--skip-gate",
        action="store_true",
        help="Generate benchmark artifacts without applying the regression gate.",
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


def metric_delta(run_summary: dict[str, Any], candidate: str, baseline: str, metric: str) -> float:
    """Calculate a candidate-minus-baseline mean metric delta."""
    candidate_mean = run_summary.get(candidate, {}).get(metric, {}).get("mean", 0)
    baseline_mean = run_summary.get(baseline, {}).get(metric, {}).get("mean", 0)
    return float(candidate_mean) - float(baseline_mean)


def load_executor_metadata(path: Path) -> dict[str, str] | None:
    """Load usable executor identity metadata without aborting report generation."""
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(payload, dict):
        return None
    fields = ("executor_model", "executor_provider", "harness")
    if any(
        not isinstance(payload.get(field), str) or not payload[field].strip() for field in fields
    ):
        return None
    return {field: payload[field] for field in fields}


def enrich_benchmark(iteration_dir: Path, aggregate_script: Path) -> None:
    """Apply recorded metadata and regenerate both benchmark artifacts."""
    benchmark_path = iteration_dir / "benchmark.json"
    benchmark = json.loads(benchmark_path.read_text(encoding="utf-8"))
    iteration = json.loads((iteration_dir / "iteration_manifest.json").read_text(encoding="utf-8"))
    run_metadata = [
        metadata
        for path in iteration_dir.glob("eval-*/*/run-*/outputs/run_metadata.json")
        if (metadata := load_executor_metadata(path)) is not None
    ]
    models = sorted({item["executor_model"] for item in run_metadata if "executor_model" in item})
    providers = sorted(
        {item["executor_provider"] for item in run_metadata if "executor_provider" in item}
    )
    harnesses = sorted({item["harness"] for item in run_metadata if "harness" in item})
    benchmark["metadata"].update(
        {
            "executor_model": ", ".join(models) if models else "unknown",
            "executor_provider": ", ".join(providers) if providers else "unknown",
            "executor_harness": ", ".join(harnesses) if harnesses else "unknown",
            "runs_per_configuration": iteration["runs_per_config"],
            "candidate_sha": iteration.get("candidate_sha"),
            "baseline_sha": iteration.get("baseline_sha"),
            "candidate_skill_hash": iteration.get("candidate_skill_hash"),
            "baseline_skill_hash": iteration.get("baseline_skill_hash"),
            "eval_manifest_hash": iteration.get("eval_manifest_hash"),
        }
    )
    baseline = iteration["baseline"]
    run_summary = benchmark["run_summary"]
    run_summary["delta"] = {
        "pass_rate": f"{metric_delta(run_summary, 'with_skill', baseline, 'pass_rate'):+.2f}",
        "time_seconds": f"{metric_delta(run_summary, 'with_skill', baseline, 'time_seconds'):+.1f}",
        "tokens": f"{metric_delta(run_summary, 'with_skill', baseline, 'tokens'):+.0f}",
    }
    benchmark_path.write_text(json.dumps(benchmark, indent=2) + "\n", encoding="utf-8")
    aggregate_module = runpy.run_path(str(aggregate_script))
    generate_markdown = cast(Callable[[dict[str, Any]], str], aggregate_module["generate_markdown"])
    (iteration_dir / "benchmark.md").write_text(
        generate_markdown(benchmark) + "\n", encoding="utf-8"
    )


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
    enrich_benchmark(args.iteration_dir, args.aggregate_script)

    if not args.skip_gate:
        compare_script = script_dir / "compare_iteration.py"
        run_command([args.python, str(compare_script), str(args.iteration_dir)])


if __name__ == "__main__":
    main()
