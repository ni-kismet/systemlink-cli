"""Unit tests for the skill regression gate."""

from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from slcli.skills.slcli.scripts.compare_iteration import evaluate_iteration, regression_margin
from slcli.skills.slcli.scripts.grade_iteration import file_manifest
from slcli.skills.slcli.scripts.prepare_eval_workspace import hash_directory


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
    candidate_template = tmp_path / "candidate-skill"
    baseline_template = tmp_path / "baseline-skill"
    candidate_template.mkdir()
    baseline_template.mkdir()
    (candidate_template / "SKILL.md").write_text("candidate\n", encoding="utf-8")
    (baseline_template / "SKILL.md").write_text("baseline\n", encoding="utf-8")
    candidate_hash = hash_directory(candidate_template)
    baseline_hash = hash_directory(baseline_template)
    write_json(
        tmp_path / "iteration_manifest.json",
        {
            "skill_name": "test",
            "baseline": "old_skill",
            "runs_per_config": 3,
            "eval_ids": [1],
            "candidate_sha": "candidate",
            "baseline_sha": "baseline",
            "candidate_skill_hash": candidate_hash,
            "baseline_skill_hash": baseline_hash,
            "eval_manifest_hash": "manifest-hash",
        },
    )
    eval_dir = tmp_path / "eval-1-example"
    write_json(eval_dir / "eval_metadata.json", {"eval_id": 1})
    write_json(eval_dir / "inputs_manifest.json", {"files": []})
    for configuration in ("with_skill", "old_skill"):
        for run_number in range(1, 4):
            grading_payload = grading(1.0)
            run_dir = eval_dir / configuration / f"run-{run_number}"
            run_skill_dir = run_dir / "repo" / "slcli" / "skills" / "slcli"
            run_skill_dir.mkdir(parents=True)
            source_skill = (
                candidate_template if configuration == "with_skill" else baseline_template
            )
            (run_skill_dir / "SKILL.md").write_bytes((source_skill / "SKILL.md").read_bytes())
            write_json(
                run_dir / "run_config.json",
                {"configuration": configuration, "repository_root": str(run_dir / "repo")},
            )
            timing = {"duration_ms": 1000, "total_duration_seconds": 1.0, "total_tokens": 10}
            write_json(run_dir / "timing.json", timing)
            write_json(
                run_dir / "grading.json",
                grading_payload,
            )
            outputs_dir = run_dir / "outputs"
            (outputs_dir / "response.txt").parent.mkdir(parents=True, exist_ok=True)
            (outputs_dir / "response.txt").write_text("response\n", encoding="utf-8")
            (outputs_dir / "transcript.jsonl").write_text("{}\n", encoding="utf-8")
            metadata = run_metadata(configuration)
            write_json(outputs_dir / "run_metadata.json", metadata)
            write_json(
                run_dir / "run_record.json",
                {
                    "skill_name": "test",
                    "candidate_sha": "candidate",
                    "baseline_sha": "baseline",
                    "candidate_skill_hash": candidate_hash,
                    "baseline_skill_hash": baseline_hash,
                    "eval_manifest_hash": "manifest-hash",
                    "eval_id": 1,
                    "trial": run_number,
                    "configuration": configuration,
                    "run_skill_hash": (
                        candidate_hash if configuration == "with_skill" else baseline_hash
                    ),
                    "classification": "pass",
                    "executor": metadata,
                    "inputs": [],
                    "outputs": file_manifest(outputs_dir),
                    "timing": timing,
                    "grading": grading_payload,
                },
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
        grading_payload = grading(0.0, critical_pass=False)
        write_json(
            eval_dir / "with_skill" / f"run-{run_number}" / "grading.json",
            grading_payload,
        )
        record_path = eval_dir / "with_skill" / f"run-{run_number}" / "run_record.json"
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record["classification"] = "fail"
        record["grading"] = grading_payload
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
    grading_payload = grading(0.9, critical_pass=False)
    write_json(
        eval_dir / "with_skill" / "run-1" / "grading.json",
        grading_payload,
    )
    record_path = eval_dir / "with_skill" / "run-1" / "run_record.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["classification"] = "fail"
    record["grading"] = grading_payload
    write_json(record_path, record)

    result = evaluate_iteration(tmp_path, margin=0.05)

    assert result["status"] == "regression"
    assert result["critical_regressions"] == [1]


def test_evaluate_iteration_detects_aggregate_regression(tmp_path: Path) -> None:
    eval_dir = prepare_iteration(tmp_path)
    for run_number in range(1, 4):
        grading_payload = grading(0.9)
        write_json(
            eval_dir / "with_skill" / f"run-{run_number}" / "grading.json",
            grading_payload,
        )
        record_path = eval_dir / "with_skill" / f"run-{run_number}" / "run_record.json"
        record = json.loads(record_path.read_text(encoding="utf-8"))
        record["grading"] = grading_payload
        write_json(record_path, record)

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
    run_dir = eval_dir / "old_skill" / "run-2"
    metadata = run_metadata("old_skill", model="other-model")
    write_json(run_dir / "outputs" / "run_metadata.json", metadata)
    record_path = run_dir / "run_record.json"
    record = json.loads(record_path.read_text(encoding="utf-8"))
    record["executor"] = metadata
    record["outputs"] = file_manifest(run_dir / "outputs")
    write_json(record_path, record)

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


@pytest.mark.parametrize("field", ["executor_provider", "executor_model", "harness"])
@pytest.mark.parametrize("value", ["", None])
def test_evaluate_iteration_requires_non_empty_executor_metadata(
    tmp_path: Path, field: str, value: str | None
) -> None:
    eval_dir = prepare_iteration(tmp_path)
    metadata_path = eval_dir / "with_skill" / "run-1" / "outputs" / "run_metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata[field] = value
    write_json(metadata_path, metadata)

    result = evaluate_iteration(tmp_path, margin=0.05)

    assert result["status"] == "inconclusive"


@pytest.mark.parametrize("artifact", ["response.txt", "transcript.jsonl"])
def test_evaluate_iteration_is_inconclusive_for_modified_output(
    tmp_path: Path, artifact: str
) -> None:
    eval_dir = prepare_iteration(tmp_path)
    output_path = eval_dir / "with_skill" / "run-1" / "outputs" / artifact
    output_path.write_text("modified\n", encoding="utf-8")

    result = evaluate_iteration(tmp_path, margin=0.05)

    assert result["status"] == "inconclusive"


def test_evaluate_iteration_is_inconclusive_for_modified_executor_metadata(
    tmp_path: Path,
) -> None:
    eval_dir = prepare_iteration(tmp_path)
    metadata_path = eval_dir / "with_skill" / "run-1" / "outputs" / "run_metadata.json"
    metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    metadata["executor_model"] = "modified-model"
    write_json(metadata_path, metadata)

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


def test_evaluate_iteration_is_inconclusive_for_modified_run_skill(tmp_path: Path) -> None:
    eval_dir = prepare_iteration(tmp_path)
    skill_path = eval_dir / "with_skill" / "run-1" / "repo/slcli/skills/slcli/SKILL.md"
    skill_path.write_text("modified\n", encoding="utf-8")

    result = evaluate_iteration(tmp_path, margin=0.05)

    assert result["status"] == "inconclusive"


def test_evaluate_iteration_is_inconclusive_for_invalid_run_config(tmp_path: Path) -> None:
    eval_dir = prepare_iteration(tmp_path)
    run_config = eval_dir / "with_skill" / "run-1" / "run_config.json"
    run_config.write_text("{", encoding="utf-8")

    result = evaluate_iteration(tmp_path, margin=0.05)

    assert result["status"] == "inconclusive"


def test_evaluate_iteration_is_inconclusive_for_modified_grading(tmp_path: Path) -> None:
    eval_dir = prepare_iteration(tmp_path)
    grading_path = eval_dir / "with_skill" / "run-1" / "grading.json"
    modified = json.loads(grading_path.read_text(encoding="utf-8"))
    modified["summary"]["pass_rate"] = 0.25
    write_json(grading_path, modified)

    result = evaluate_iteration(tmp_path, margin=0.05)

    assert result["status"] == "inconclusive"
    assert str(eval_dir / "with_skill" / "run-1") in result["missing_or_inconclusive_runs"]


def test_evaluate_iteration_is_inconclusive_for_modified_input(tmp_path: Path) -> None:
    eval_dir = prepare_iteration(tmp_path)
    input_path = eval_dir / "inputs" / "fixture.txt"
    input_path.parent.mkdir()
    input_path.write_text("original\n", encoding="utf-8")
    input_record = {
        "relative_path": "fixture.txt",
        "absolute_path": str(input_path),
        "sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
    }
    write_json(eval_dir / "inputs_manifest.json", {"files": [input_record]})
    for configuration in ("with_skill", "old_skill"):
        for run_number in range(1, 4):
            record_path = eval_dir / configuration / f"run-{run_number}" / "run_record.json"
            record = json.loads(record_path.read_text(encoding="utf-8"))
            record["inputs"] = [input_record]
            write_json(record_path, record)
    input_path.write_text("modified\n", encoding="utf-8")

    result = evaluate_iteration(tmp_path, margin=0.05)

    assert result["status"] == "inconclusive"


@pytest.mark.parametrize("value", ["-0.1", "1.1", "nan", "inf"])
def test_regression_margin_rejects_invalid_values(value: str) -> None:
    with pytest.raises(argparse.ArgumentTypeError, match="finite value between 0 and 1"):
        regression_margin(value)


@pytest.mark.parametrize("value", ["0", "0.05", "1"])
def test_regression_margin_accepts_unit_interval(value: str) -> None:
    assert regression_margin(value) == float(value)
