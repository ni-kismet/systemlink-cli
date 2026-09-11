"""Unit tests for grading complete skill eval runs."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

import pytest

from slcli.skills.slcli.scripts.grade_iteration import grade_run


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write a JSON test fixture."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


def bind_executor_prompt(run_dir: Path) -> dict[str, Any]:
    """Create a prompt and return its iteration manifest binding."""
    prompt_path = run_dir / "executor_prompt.txt"
    prompt_path.write_text("Execute this task.\n", encoding="utf-8")
    return {
        "executor_prompt_hashes": {
            run_dir.relative_to(run_dir.parents[2])
            .as_posix(): hashlib.sha256(prompt_path.read_bytes())
            .hexdigest()
        }
    }


def test_grade_run_records_provenance_and_only_grades_response(tmp_path: Path) -> None:
    manifest_path = tmp_path / "skill" / "evals" / "evals.json"
    write_json(
        manifest_path,
        {
            "manifest_version": 1,
            "skill_name": "test",
            "recommended_suites": {"gating": [1], "regression": [1]},
            "evals": [
                {
                    "id": 1,
                    "prompt": "Use the supported command",
                    "expected_output": "A supported command",
                    "files": [],
                    "expectations": ["Uses the supported command"],
                    "grading_rules": [
                        {
                            "text": "supported command",
                            "critical": True,
                            "positive_control": "slcli system list",
                            "negative_control": "slcli asset list",
                            "scope": "command",
                            "mode": "any_of",
                            "patterns": [r"slcli\s+system\s+list"],
                        }
                    ],
                }
            ],
        },
    )
    run_dir = tmp_path / "iteration" / "eval-1" / "with_skill" / "run-1"
    skill_dir = run_dir / "repo" / "slcli" / "skills" / "slcli"
    skill_dir.mkdir(parents=True)
    (skill_dir / "SKILL.md").write_text("candidate skill\n", encoding="utf-8")
    write_json(
        run_dir / "run_config.json",
        {"configuration": "with_skill", "repository_root": str(run_dir / "repo")},
    )
    write_json(run_dir / "inputs_manifest.json", {"files": []})
    input_manifest_hash = hashlib.sha256(
        (run_dir / "inputs_manifest.json").read_bytes()
    ).hexdigest()
    outputs = run_dir / "outputs"
    outputs.mkdir(parents=True)
    (outputs / "response.txt").write_text("I could not determine the command.\n", encoding="utf-8")
    (outputs / "notes.txt").write_text("Expected: slcli system list\n", encoding="utf-8")
    (outputs / "transcript.jsonl").write_text('{"event":"completed"}\n', encoding="utf-8")
    prompt_path = run_dir / "executor_prompt.txt"
    prompt_path.write_text("Execute this task.\n", encoding="utf-8")
    prompt_hash = hashlib.sha256(prompt_path.read_bytes()).hexdigest()
    write_json(
        outputs / "run_metadata.json",
        {
            "executor_provider": "test",
            "executor_model": "test-model",
            "harness": "test-harness",
            "configuration": "with_skill",
            "status": "completed",
        },
    )
    write_json(
        run_dir / "timing.json",
        {"duration_ms": 2500, "total_duration_seconds": 2.5, "total_tokens": 42},
    )
    iteration_metadata = {
        "skill_name": "test",
        "candidate_sha": "candidate",
        "baseline_sha": "baseline",
        "candidate_skill_hash": "candidate-hash",
        "baseline_skill_hash": "baseline-hash",
        "eval_manifest_hash": "manifest-hash",
        "reference_date": "2026-09-08",
        "input_manifest_hashes": {"eval-1/with_skill/run-1": input_manifest_hash},
        "executor_prompt_hashes": {"eval-1/with_skill/run-1": prompt_hash},
    }

    message = grade_run(manifest_path, 1, run_dir, False, iteration_metadata)

    assert message.startswith("graded ")
    record = json.loads((run_dir / "run_record.json").read_text(encoding="utf-8"))
    assert record["classification"] == "fail"
    assert (
        json.loads((run_dir / "grading.json").read_text(encoding="utf-8"))["classification"]
        == "fail"
    )
    assert record["candidate_sha"] == "candidate"
    assert record["run_skill_hash"] == hashlib.sha256(b"SKILL.md\0candidate skill\n\0").hexdigest()
    assert record["executor_prompt_hash"] == prompt_hash
    assert record["eval_manifest_hash"] == hashlib.sha256(manifest_path.read_bytes()).hexdigest()
    assert record["reference_date"] == "2026-09-08"
    assert json.loads((run_dir / "grading.json").read_text(encoding="utf-8"))["reference_date"] == (
        "2026-09-08"
    )
    assert record["inputs"] == []
    assert record["input_manifest_hash"] == input_manifest_hash
    assert record["grading"]["execution_metrics"]["transcript_chars"] == len(
        '{"event":"completed"}\n'
    )
    assert record["grading"]["execution_metrics"]["total_tokens"] == 42
    assert record["grading"]["timing"]["total_duration_seconds"] == 2.5
    assert {item["path"] for item in record["outputs"]} == {
        "notes.txt",
        "response.txt",
        "run_metadata.json",
        "transcript.jsonl",
    }


def test_grade_run_skips_run_without_transcript(tmp_path: Path) -> None:
    outputs = tmp_path / "eval-1" / "with_skill" / "run-1" / "outputs"
    outputs.mkdir(parents=True)
    (outputs / "response.txt").write_text("A response\n", encoding="utf-8")
    write_json(outputs / "run_metadata.json", {"status": "completed"})
    write_json(
        outputs.parent / "timing.json",
        {"duration_ms": 1000, "total_duration_seconds": 1.0, "total_tokens": 1},
    )

    message = grade_run(
        tmp_path / "evals.json",
        1,
        outputs.parent,
        False,
        {},
    )

    assert message.endswith("required outputs missing: transcript.jsonl")


def test_grade_run_skips_invalid_input_manifest(tmp_path: Path) -> None:
    run_dir = tmp_path / "eval-1" / "with_skill" / "run-1"
    outputs = run_dir / "outputs"
    outputs.mkdir(parents=True)
    (outputs / "response.txt").write_text("A response\n", encoding="utf-8")
    (outputs / "transcript.jsonl").write_text("{}\n", encoding="utf-8")
    write_json(outputs / "run_metadata.json", {"status": "completed"})
    write_json(
        run_dir / "timing.json",
        {"duration_ms": 1000, "total_duration_seconds": 1.0, "total_tokens": 1},
    )
    write_json(run_dir / "inputs_manifest.json", {"files": {}})
    write_json(run_dir / "run_config.json", {"repository_root": None})
    iteration_metadata = bind_executor_prompt(run_dir)
    iteration_metadata["reference_date"] = "2026-09-08"

    message = grade_run(tmp_path / "evals.json", 1, run_dir, False, iteration_metadata)

    assert message.endswith("invalid input manifest")


@pytest.mark.parametrize("artifact_path", ["transcript.jsonl", "response.txt", "run_metadata.json"])
def test_grade_run_skips_directory_artifact(tmp_path: Path, artifact_path: str) -> None:
    run_dir = tmp_path / "eval-1" / "with_skill" / "run-1"
    outputs = run_dir / "outputs"
    outputs.mkdir(parents=True)
    for artifact in ("response.txt", "transcript.jsonl", "run_metadata.json"):
        path = outputs / artifact
        if artifact == artifact_path:
            path.mkdir()
        elif artifact == "run_metadata.json":
            write_json(path, {"status": "completed"})
        else:
            path.write_text("content\n", encoding="utf-8")
    write_json(
        run_dir / "timing.json",
        {"duration_ms": 1000, "total_duration_seconds": 1.0, "total_tokens": 1},
    )
    write_json(run_dir / "run_config.json", {"repository_root": None})

    message = grade_run(tmp_path / "evals.json", 1, run_dir, False, bind_executor_prompt(run_dir))

    assert message.endswith(f"required outputs missing: {artifact_path}")


def test_grade_run_skips_directory_timing_artifact(tmp_path: Path) -> None:
    run_dir = tmp_path / "eval-1" / "with_skill" / "run-1"
    outputs = run_dir / "outputs"
    outputs.mkdir(parents=True)
    (outputs / "response.txt").write_text("A response\n", encoding="utf-8")
    (outputs / "transcript.jsonl").write_text("{}\n", encoding="utf-8")
    write_json(outputs / "run_metadata.json", {"status": "completed"})
    (run_dir / "timing.json").mkdir()
    write_json(run_dir / "run_config.json", {"repository_root": None})

    message = grade_run(tmp_path / "evals.json", 1, run_dir, False, bind_executor_prompt(run_dir))

    assert message.endswith("required outputs missing: timing.json")


def test_grade_run_skips_invalid_executor_metadata(tmp_path: Path) -> None:
    run_dir = tmp_path / "eval-1" / "with_skill" / "run-1"
    outputs = run_dir / "outputs"
    outputs.mkdir(parents=True)
    (outputs / "response.txt").write_text("A response\n", encoding="utf-8")
    (outputs / "transcript.jsonl").write_text("{}\n", encoding="utf-8")
    (outputs / "run_metadata.json").write_text("{", encoding="utf-8")
    write_json(
        run_dir / "timing.json",
        {"duration_ms": 1000, "total_duration_seconds": 1.0, "total_tokens": 1},
    )
    write_json(run_dir / "run_config.json", {"repository_root": None})

    message = grade_run(tmp_path / "evals.json", 1, run_dir, False, bind_executor_prompt(run_dir))

    assert message.endswith("invalid run metadata or timing")


def test_grade_run_skips_inconsistent_timing(tmp_path: Path) -> None:
    run_dir = tmp_path / "eval-1" / "with_skill" / "run-1"
    outputs = run_dir / "outputs"
    outputs.mkdir(parents=True)
    (outputs / "response.txt").write_text("A response\n", encoding="utf-8")
    (outputs / "transcript.jsonl").write_text("{}\n", encoding="utf-8")
    write_json(outputs / "run_metadata.json", {"status": "completed"})
    write_json(
        run_dir / "timing.json",
        {"duration_ms": 1000, "total_duration_seconds": 99.0, "total_tokens": 1},
    )
    write_json(run_dir / "run_config.json", {"repository_root": None})

    message = grade_run(tmp_path / "evals.json", 1, run_dir, False, bind_executor_prompt(run_dir))

    assert message.endswith("invalid run metadata or timing")


@pytest.mark.parametrize("invalid_duration", [float("nan"), float("inf")])
def test_grade_run_skips_non_finite_timing(tmp_path: Path, invalid_duration: float) -> None:
    run_dir = tmp_path / "eval-1" / "with_skill" / "run-1"
    outputs = run_dir / "outputs"
    outputs.mkdir(parents=True)
    (outputs / "response.txt").write_text("A response\n", encoding="utf-8")
    (outputs / "transcript.jsonl").write_text("{}\n", encoding="utf-8")
    write_json(outputs / "run_metadata.json", {"status": "completed"})
    write_json(
        run_dir / "timing.json",
        {
            "duration_ms": invalid_duration,
            "total_duration_seconds": invalid_duration,
            "total_tokens": 1,
        },
    )
    write_json(run_dir / "run_config.json", {"repository_root": None})

    message = grade_run(tmp_path / "evals.json", 1, run_dir, False, bind_executor_prompt(run_dir))

    assert message.endswith("invalid run metadata or timing")
