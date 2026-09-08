"""Unit tests for the skill regression gate."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

import pytest

from slcli.skills.slcli.scripts.compare_iteration import evaluate_iteration, regression_margin


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write a JSON fixture."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def grading(pass_rate: float, critical_pass: bool = True) -> dict[str, Any]:
    """Build a grading fixture."""
    return {
        "classification": "pass" if critical_pass else "fail",
        "summary": {"pass_rate": pass_rate},
        "expectations": [
            {"text": "critical", "critical": True, "passed": critical_pass, "evidence": "test"}
        ],
    }


def run_metadata(configuration: str, model: str = "test-model") -> dict[str, str]:
    """Build an executor metadata fixture."""
    return {
        "executor_provider": "test-provider",
        "executor_model": model,
        "harness": "test-harness-v1",
        "configuration": configuration,
        "status": "completed",
    }


def prepare_iteration(tmp_path: Path) -> Path:
    """Create a complete three-trial paired iteration."""
    write_json(
        tmp_path / "iteration_manifest.json",
        {
            "skill_name": "test",
            "baseline": "old_skill",
            "runs_per_config": 3,
            "eval_ids": [1],
            "candidate_sha": "candidate",
            "baseline_sha": "baseline",
            "candidate_skill_hash": "candidate-hash",
            "baseline_skill_hash": "baseline-hash",
            "eval_manifest_hash": "manifest-hash",
        },
    )
    eval_dir = tmp_path / "eval-1-example"
    write_json(eval_dir / "eval_metadata.json", {"eval_id": 1})
    for configuration in ("with_skill", "old_skill"):
        for run_number in range(1, 4):
            write_json(
                eval_dir / configuration / f"run-{run_number}" / "grading.json",
                grading(1.0),
            )
            write_json(
                eval_dir / configuration / f"run-{run_number}" / "run_record.json",
                {
                    "skill_name": "test",
                    "candidate_sha": "candidate",
                    "baseline_sha": "baseline",
                    "candidate_skill_hash": "candidate-hash",
                    "baseline_skill_hash": "baseline-hash",
                    "eval_manifest_hash": "manifest-hash",
                    "eval_id": 1,
                    "trial": run_number,
                    "configuration": configuration,
                    "classification": "pass",
                },
            )
            write_json(
                eval_dir / configuration / f"run-{run_number}" / "outputs" / "run_metadata.json",
                run_metadata(configuration),
            )
    return eval_dir


def test_evaluate_iteration_passes_non_regressing_candidate(tmp_path: Path) -> None:
    prepare_iteration(tmp_path)

    result = evaluate_iteration(tmp_path, margin=0.05)

    assert result["status"] == "pass"
    assert result["delta"] == 0.0


def test_evaluate_iteration_detects_critical_regression(tmp_path: Path) -> None:
    eval_dir = prepare_iteration(tmp_path)
    for run_number in (1, 2):
        write_json(
            eval_dir / "with_skill" / f"run-{run_number}" / "grading.json",
            grading(0.0, critical_pass=False),
        )
        record_path = eval_dir / "with_skill" / f"run-{run_number}" / "run_record.json"
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record["classification"] = "fail"
        write_json(record_path, record)

    result = evaluate_iteration(tmp_path, margin=0.05)

    assert result["status"] == "regression"
    assert result["critical_regressions"] == [1]
    assert result["candidate_only_critical_failures"] == [
        {"eval_id": 1, "run_number": 1},
        {"eval_id": 1, "run_number": 2},
    ]


def test_candidate_only_failure_regresses_even_with_candidate_majority(tmp_path: Path) -> None:
    eval_dir = prepare_iteration(tmp_path)
    write_json(
        eval_dir / "with_skill" / "run-1" / "grading.json",
        grading(0.9, critical_pass=False),
    )
    record_path = eval_dir / "with_skill" / "run-1" / "run_record.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["classification"] = "fail"
    write_json(record_path, record)

    result = evaluate_iteration(tmp_path, margin=0.05)

    assert result["status"] == "regression"
    assert result["critical_regressions"] == [1]


def test_evaluate_iteration_detects_aggregate_regression(tmp_path: Path) -> None:
    eval_dir = prepare_iteration(tmp_path)
    for run_number in range(1, 4):
        write_json(
            eval_dir / "with_skill" / f"run-{run_number}" / "grading.json",
            grading(0.9),
        )

    result = evaluate_iteration(tmp_path, margin=0.05)

    assert result["status"] == "regression"
    assert result["aggregate_regression"] is True


def test_evaluate_iteration_is_inconclusive_when_run_is_missing(tmp_path: Path) -> None:
    eval_dir = prepare_iteration(tmp_path)
    (eval_dir / "with_skill" / "run-3" / "grading.json").unlink()

    result = evaluate_iteration(tmp_path, margin=0.05)

    assert result["status"] == "inconclusive"
    assert result["missing_or_inconclusive_runs"]


def test_evaluate_iteration_is_inconclusive_for_different_models(tmp_path: Path) -> None:
    eval_dir = prepare_iteration(tmp_path)
    write_json(
        eval_dir / "old_skill" / "run-2" / "outputs" / "run_metadata.json",
        run_metadata("old_skill", model="other-model"),
    )

    result = evaluate_iteration(tmp_path, margin=0.05)

    assert result["status"] == "inconclusive"
    assert result["incompatible_run_metadata"] == ["eval 1 run 2"]


def test_evaluate_iteration_is_inconclusive_for_infrastructure_error(tmp_path: Path) -> None:
    eval_dir = prepare_iteration(tmp_path)
    metadata = run_metadata("with_skill")
    metadata["status"] = "infrastructure_error"
    write_json(
        eval_dir / "with_skill" / "run-1" / "outputs" / "run_metadata.json",
        metadata,
    )

    result = evaluate_iteration(tmp_path, margin=0.05)

    assert result["status"] == "inconclusive"


def test_evaluate_iteration_is_inconclusive_for_stale_provenance(tmp_path: Path) -> None:
    eval_dir = prepare_iteration(tmp_path)
    record_path = eval_dir / "with_skill" / "run-1" / "run_record.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["candidate_sha"] = "stale-candidate"
    write_json(record_path, record)

    result = evaluate_iteration(tmp_path, margin=0.05)

    assert result["status"] == "inconclusive"
    assert str(eval_dir / "with_skill" / "run-1") in result["missing_or_inconclusive_runs"]


@pytest.mark.parametrize("value", ["-0.1", "1.1", "nan", "inf"])
def test_regression_margin_rejects_invalid_values(value: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError, match="finite value between 0 and 1"):
        regression_margin(value)


@pytest.mark.parametrize("value", ["0", "0.05", "1"])
def test_regression_margin_accepts_unit_interval(value: str) -> None:
    assert regression_margin(value) == float(value)
