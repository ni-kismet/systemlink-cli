"""Unit tests for grading complete skill eval runs."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from slcli.skills.slcli.scripts.grade_iteration import grade_run


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write a JSON test fixture."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload), encoding="utf-8")


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
    outputs = run_dir / "outputs"
    outputs.mkdir(parents=True)
    (outputs / "response.txt").write_text("I could not determine the command.\n", encoding="utf-8")
    (outputs / "notes.txt").write_text("Expected: slcli system list\n", encoding="utf-8")
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
    iteration_metadata = {
        "skill_name": "test",
        "candidate_sha": "candidate",
        "baseline_sha": "baseline",
        "candidate_skill_hash": "candidate-hash",
        "baseline_skill_hash": "baseline-hash",
        "eval_manifest_hash": "manifest-hash",
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
    assert {item["path"] for item in record["outputs"]} == {
        "notes.txt",
        "response.txt",
        "run_metadata.json",
    }
