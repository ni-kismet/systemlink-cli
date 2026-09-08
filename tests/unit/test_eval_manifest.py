"""Unit tests for the checked-in skill eval manifest."""

from pathlib import Path

import pytest

from slcli.skills.slcli.scripts.eval_manifest import load_manifest, validate_manifest
from slcli.skills.slcli.scripts.grade_eval_response import evaluate_rule


def test_checked_in_eval_manifest_is_valid() -> None:
    manifest = Path("slcli/skills/slcli/evals/evals.json")

    payload = load_manifest(manifest)

    assert payload["manifest_version"] == 1


def test_manifest_requires_explicit_critical_flags(tmp_path: Path) -> None:
    payload = {
        "manifest_version": 1,
        "skill_name": "test",
        "recommended_suites": {"gating": [1], "regression": [1]},
        "evals": [
            {
                "id": 1,
                "prompt": "test",
                "expected_output": "test",
                "files": [],
                "grading_rules": [{"text": "rule", "mode": "any_of", "patterns": ["expected"]}],
            }
        ],
    }

    with pytest.raises(ValueError, match="explicit critical flag"):
        validate_manifest(payload, tmp_path)


def test_all_checked_in_critical_graders_pass_their_controls() -> None:
    manifest = load_manifest(Path("slcli/skills/slcli/evals/evals.json"))

    for eval_entry in manifest["evals"]:
        for rule in eval_entry["grading_rules"]:
            if not rule["critical"]:
                continue
            positive_passed, _ = evaluate_rule(rule["positive_control"], rule)
            negative_passed, _ = evaluate_rule(rule["negative_control"], rule)
            assert (
                positive_passed
            ), f"positive control failed: eval {eval_entry['id']} {rule['text']}"
            assert (
                not negative_passed
            ), f"negative control passed: eval {eval_entry['id']} {rule['text']}"
