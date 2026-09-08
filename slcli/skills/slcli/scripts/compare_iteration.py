"""Compare candidate and baseline skill eval runs and enforce a regression gate."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

REGRESSION_EXIT_CODE = 1
INCONCLUSIVE_EXIT_CODE = 2


def regression_margin(value: str) -> float:
    """Parse a finite regression margin between zero and one."""
    parsed = float(value)
    if not math.isfinite(parsed) or not 0 <= parsed <= 1:
        raise argparse.ArgumentTypeError("margin must be a finite value between 0 and 1")
    return parsed


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Apply the paired skill regression gate.")
    parser.add_argument("iteration_dir", type=Path, help="Prepared and graded iteration directory.")
    parser.add_argument(
        "--margin",
        type=regression_margin,
        default=0.05,
        help="Maximum allowed candidate pass-rate decrease.",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    """Load one JSON object."""
    return json.loads(path.read_text(encoding="utf-8"))


def load_run(
    run_dir: Path,
    iteration: dict[str, Any],
    eval_id: int,
    run_number: int,
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Load grading output when a run completed successfully."""
    grading_path = run_dir / "grading.json"
    metadata_path = run_dir / "outputs" / "run_metadata.json"
    record_path = run_dir / "run_record.json"
    if not grading_path.exists() or not metadata_path.exists() or not record_path.exists():
        return None
    metadata = load_json(metadata_path)
    required_metadata = {
        "executor_provider",
        "executor_model",
        "harness",
        "configuration",
        "status",
    }
    if (
        not required_metadata.issubset(metadata)
        or metadata["configuration"] != run_dir.parent.name
        or metadata["status"] != "completed"
    ):
        return None
    grading = load_json(grading_path)
    if grading.get("classification") == "inconclusive":
        return None
    record = load_json(record_path)
    expected_provenance = {
        "skill_name": iteration.get("skill_name"),
        "candidate_sha": iteration.get("candidate_sha"),
        "baseline_sha": iteration.get("baseline_sha"),
        "candidate_skill_hash": iteration.get("candidate_skill_hash"),
        "baseline_skill_hash": iteration.get("baseline_skill_hash"),
        "eval_manifest_hash": iteration.get("eval_manifest_hash"),
        "eval_id": eval_id,
        "trial": run_number,
        "configuration": run_dir.parent.name,
    }
    if any(record.get(field) != value for field, value in expected_provenance.items()):
        return None
    if record.get("classification") != grading.get("classification"):
        return None
    return grading, metadata


def critical_passed(grading: dict[str, Any]) -> bool:
    """Return whether all critical expectations passed."""
    critical = [item for item in grading.get("expectations", []) if item.get("critical", True)]
    return bool(critical) and all(item.get("passed", False) for item in critical)


def evaluate_iteration(iteration_dir: Path, margin: float) -> dict[str, Any]:
    """Evaluate paired candidate and baseline results."""
    manifest = load_json(iteration_dir / "iteration_manifest.json")
    baseline = manifest["baseline"]
    runs_per_config = int(manifest["runs_per_config"])
    majority = math.floor(runs_per_config / 2) + 1
    eval_results: list[dict[str, Any]] = []
    all_candidate_rates: list[float] = []
    all_baseline_rates: list[float] = []
    missing_runs: list[str] = []
    incompatible_runs: list[str] = []
    critical_regressions: list[int] = []
    candidate_only_failures: list[dict[str, int]] = []

    eval_dirs = {
        int(load_json(path / "eval_metadata.json")["eval_id"]): path
        for path in iteration_dir.glob("eval-*")
        if (path / "eval_metadata.json").exists()
    }
    for eval_id in manifest["eval_ids"]:
        eval_dir = eval_dirs.get(int(eval_id))
        if eval_dir is None:
            missing_runs.append(f"eval {eval_id}: directory missing")
            continue

        candidate_gradings: list[dict[str, Any]] = []
        baseline_gradings: list[dict[str, Any]] = []
        for run_number in range(1, runs_per_config + 1):
            for configuration, destination in (
                ("with_skill", candidate_gradings),
                (baseline, baseline_gradings),
            ):
                run_dir = eval_dir / configuration / f"run-{run_number}"
                run = load_run(run_dir, manifest, int(eval_id), run_number)
                if run is None:
                    missing_runs.append(str(run_dir))
                else:
                    destination.append(run[0])

            candidate_run = load_run(
                eval_dir / "with_skill" / f"run-{run_number}",
                manifest,
                int(eval_id),
                run_number,
            )
            baseline_run = load_run(
                eval_dir / baseline / f"run-{run_number}",
                manifest,
                int(eval_id),
                run_number,
            )
            if candidate_run and baseline_run:
                candidate_metadata = candidate_run[1]
                baseline_metadata = baseline_run[1]
                comparable_fields = ("executor_provider", "executor_model", "harness")
                if any(
                    candidate_metadata[field] != baseline_metadata[field]
                    for field in comparable_fields
                ):
                    incompatible_runs.append(f"eval {eval_id} run {run_number}")
                if critical_passed(baseline_run[0]) and not critical_passed(candidate_run[0]):
                    candidate_only_failures.append(
                        {"eval_id": int(eval_id), "run_number": run_number}
                    )

        candidate_critical = sum(critical_passed(item) for item in candidate_gradings)
        baseline_critical = sum(critical_passed(item) for item in baseline_gradings)
        is_critical_regression = (
            len(candidate_gradings) == runs_per_config
            and len(baseline_gradings) == runs_per_config
            and baseline_critical >= majority
            and any(item["eval_id"] == int(eval_id) for item in candidate_only_failures)
        )
        if is_critical_regression:
            critical_regressions.append(int(eval_id))

        candidate_rates = [item["summary"]["pass_rate"] for item in candidate_gradings]
        baseline_rates = [item["summary"]["pass_rate"] for item in baseline_gradings]
        all_candidate_rates.extend(candidate_rates)
        all_baseline_rates.extend(baseline_rates)
        eval_results.append(
            {
                "eval_id": eval_id,
                "candidate_critical_passes": candidate_critical,
                "baseline_critical_passes": baseline_critical,
                "critical_regression": is_critical_regression,
            }
        )

    candidate_mean = (
        sum(all_candidate_rates) / len(all_candidate_rates) if all_candidate_rates else 0.0
    )
    baseline_mean = sum(all_baseline_rates) / len(all_baseline_rates) if all_baseline_rates else 0.0
    delta = candidate_mean - baseline_mean
    aggregate_regression = not missing_runs and not incompatible_runs and delta < -margin
    if missing_runs or incompatible_runs:
        status = "inconclusive"
    elif critical_regressions or aggregate_regression:
        status = "regression"
    else:
        status = "pass"

    return {
        "status": status,
        "margin": margin,
        "candidate_mean_pass_rate": round(candidate_mean, 4),
        "baseline_mean_pass_rate": round(baseline_mean, 4),
        "delta": round(delta, 4),
        "critical_regressions": critical_regressions,
        "candidate_only_critical_failures": candidate_only_failures,
        "aggregate_regression": aggregate_regression,
        "missing_or_inconclusive_runs": missing_runs,
        "incompatible_run_metadata": incompatible_runs,
        "evals": eval_results,
    }


def render_markdown(result: dict[str, Any]) -> str:
    """Render a concise regression report."""
    lines = [
        "# Skill Regression Gate",
        "",
        f"**Status**: {result['status']}",
        f"**Candidate pass rate**: {result['candidate_mean_pass_rate']:.1%}",
        f"**Baseline pass rate**: {result['baseline_mean_pass_rate']:.1%}",
        f"**Delta**: {result['delta']:+.1%}",
        f"**Allowed decrease**: {result['margin']:.1%}",
        "",
    ]
    if result["critical_regressions"]:
        lines.append(
            "Critical regressions: "
            + ", ".join(str(eval_id) for eval_id in result["critical_regressions"])
        )
    if result["candidate_only_critical_failures"]:
        lines.extend(["Candidate-only critical failures:", ""])
        lines.extend(
            f"- eval {item['eval_id']} run {item['run_number']}"
            for item in result["candidate_only_critical_failures"]
        )
    if result["missing_or_inconclusive_runs"]:
        lines.extend(["Missing or inconclusive runs:", ""])
        lines.extend(f"- {run}" for run in result["missing_or_inconclusive_runs"])
    if result["incompatible_run_metadata"]:
        lines.extend(["Incompatible paired run metadata:", ""])
        lines.extend(f"- {run}" for run in result["incompatible_run_metadata"])
    return "\n".join(lines) + "\n"


def main() -> None:
    """Apply the gate and return a CI-friendly exit code."""
    args = parse_args()
    result = evaluate_iteration(args.iteration_dir, args.margin)
    (args.iteration_dir / "regression.json").write_text(
        json.dumps(result, indent=2) + "\n", encoding="utf-8"
    )
    (args.iteration_dir / "regression.md").write_text(render_markdown(result), encoding="utf-8")
    print(render_markdown(result), end="")
    if result["status"] == "regression":
        sys.exit(REGRESSION_EXIT_CODE)
    if result["status"] == "inconclusive":
        sys.exit(INCONCLUSIVE_EXIT_CODE)


if __name__ == "__main__":
    main()
