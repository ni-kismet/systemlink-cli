"""Unit tests for the checked-in skill eval manifest."""

import json
from datetime import date
from pathlib import Path

import pytest

from slcli.skills.slcli.scripts.eval_manifest import load_manifest, validate_manifest
from slcli.skills.slcli.scripts.grade_eval_response import evaluate_rule
from slcli.webapp_click import _validate_plugin_manager_metadata


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
                "expectations": ["test"],
                "grading_rules": [{"text": "rule", "mode": "any_of", "patterns": ["expected"]}],
            }
        ],
    }

    with pytest.raises(ValueError, match="explicit critical flag"):
        validate_manifest(payload, tmp_path)


def test_manifest_requires_schema_entry_fields(tmp_path: Path) -> None:
    payload = {
        "manifest_version": 1,
        "skill_name": "test",
        "recommended_suites": {"gating": [1], "regression": [1]},
        "evals": [
            {
                "id": 1,
                "prompt": "test",
                "expected_output": "test",
                "grading_rules": [],
            }
        ],
    }

    with pytest.raises(ValueError, match="missing required fields"):
        validate_manifest(payload, tmp_path)


def test_all_checked_in_critical_graders_pass_their_controls() -> None:
    manifest = load_manifest(Path("slcli/skills/slcli/evals/evals.json"))

    for eval_entry in manifest["evals"]:
        for rule in eval_entry["grading_rules"]:
            if not rule["critical"]:
                continue
            reference_date = (
                date.fromisoformat(rule["control_reference_date"])
                if "control_reference_date" in rule
                else None
            )
            positive_passed, _ = evaluate_rule(
                rule["positive_control"], rule, reference_date=reference_date
            )
            negative_passed, _ = evaluate_rule(
                rule["negative_control"], rule, reference_date=reference_date
            )
            assert (
                positive_passed
            ), f"positive control failed: eval {eval_entry['id']} {rule['text']}"
            assert (
                not negative_passed
            ), f"negative control passed: eval {eval_entry['id']} {rule['text']}"


def test_webapp_packaging_fixture_is_valid() -> None:
    config_path = Path("slcli/skills/slcli/evals/files/webapp-package/nipkg.config.json")
    metadata = json.loads(config_path.read_text(encoding="utf-8"))

    validated = _validate_plugin_manager_metadata(
        metadata, require_build_dir=True, base_dir=config_path.parent
    )

    assert validated["package"] == "fleet-dashboard-webapp"
    assert validated["buildDir"] == "webapp-content"
    assert validated["iconFile"] == "icon.svg"
    assert (config_path.parent / validated["buildDir"]).is_dir()
