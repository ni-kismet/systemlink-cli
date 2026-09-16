"""Unit tests for slcli eval response grading."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import pytest

from slcli.skills.slcli.scripts.grade_eval_response import (
    evaluate_rule,
    evaluate_structured_rule,
    extract_slcli_commands,
    gather_response_text,
    grade_response,
)


def test_extract_slcli_commands_handles_fences_prefixes_and_continuations() -> None:
    response = """Run:
```bash
slcli testmonitor result list \\
  --status FAILED
```
Then: echo ready && slcli system list --format json
"""

    assert extract_slcli_commands(response) == [
        "slcli testmonitor result list --status FAILED",
        "slcli system list --format json",
    ]


def test_extract_slcli_commands_ignores_prose_and_malformed_quotes() -> None:
    response = """Don't forget to verify the output.
Do not use slcli query results.
- `slcli system list --format json`
slcli system get 'unterminated
"""

    assert extract_slcli_commands(response) == ["slcli system list --format json"]


def test_extract_slcli_commands_handles_inline_commands_but_not_warning_examples() -> None:
    response = (
        "Run `slcli system list --format json`.\n"
        "Do not use `slcli asset list`; use the system command instead."
    )

    assert extract_slcli_commands(response) == ["slcli system list --format json"]


def test_extract_slcli_commands_ignores_warning_fenced_commands() -> None:
    response = """Do not use:
```bash
slcli query results
```
Use this instead:
```bash
slcli system list
```
"""

    assert extract_slcli_commands(response) == ["slcli system list"]


@pytest.mark.parametrize("prefix", ["Avoid", "Never", "Do not use"])
def test_extract_slcli_commands_ignores_direct_warning_commands(prefix: str) -> None:
    response = f"{prefix} `slcli query results`; use `slcli system list` instead."

    assert extract_slcli_commands(response) == ["slcli system list"]


def test_extract_slcli_commands_handles_powershell_continuation() -> None:
    response = "slcli system `\n  list `\n  --format json\n"

    assert extract_slcli_commands(response) == ["slcli system list --format json"]


def test_extract_slcli_commands_normalizes_global_profile_options() -> None:
    assert extract_slcli_commands(
        "slcli --profile prod system list\n"
        "slcli -p test asset list\n"
        "slcli --profile=dev tag list"
    ) == ["slcli system list", "slcli asset list", "slcli tag list"]


def test_extract_slcli_commands_normalizes_unquoted_windows_paths() -> None:
    response = r"slcli webapp pack --config C:\repo\evals\files\nipkg.config.json"

    assert extract_slcli_commands(response) == [
        "slcli webapp pack --config C:/repo/evals/files/nipkg.config.json"
    ]


def test_gather_response_text_replaces_invalid_utf8_bytes(tmp_path: Path) -> None:
    response_path = tmp_path / "response.txt"
    response_path.write_bytes(b"before\xffafter")

    response_text, sources = gather_response_text(response_path)

    assert response_text == "before\ufffdafter"
    assert sources == [str(response_path)]


def test_grade_response_reads_final_directory_response_with_invalid_utf8(tmp_path: Path) -> None:
    manifest_path = tmp_path / "evals.json"
    manifest_path.write_text(
        json.dumps(
            {
                "manifest_version": 1,
                "skill_name": "test",
                "recommended_suites": {"gating": [1], "regression": [1]},
                "evals": [
                    {
                        "id": 1,
                        "tags": ["gating"],
                        "prompt": "Run a testmonitor command",
                        "expected_output": "Uses the testmonitor command group",
                        "files": [],
                        "expectations": ["Uses testmonitor"],
                        "grading_rules": [
                            {
                                "text": "Matches command",
                                "critical": True,
                                "positive_control": "slcli testmonitor result list",
                                "negative_control": "slcli system list",
                                "scope": "command",
                                "mode": "any_of",
                                "patterns": [r"slcli\s+testmonitor"],
                            }
                        ],
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )
    response_dir = tmp_path / "outputs"
    response_dir.mkdir()
    (response_dir / "response.txt").write_bytes(b"slcli testmonitor\xff result list\n")
    (response_dir / "notes.txt").write_text("slcli system list\n", encoding="utf-8")

    output = grade_response(manifest_path, 1, response_dir)

    assert output["summary"] == {"passed": 1, "failed": 0, "total": 1, "pass_rate": 1.0}
    assert output["eval_feedback"]["sources"] == [str(response_dir / "response.txt")]


def test_directory_grading_does_not_use_notes(tmp_path: Path) -> None:
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    (outputs / "response.txt").write_text("No command found.\n", encoding="utf-8")
    (outputs / "notes.txt").write_text("slcli system list\n", encoding="utf-8")

    text, sources = gather_response_text(outputs)

    assert text == "No command found.\n"
    assert sources == [str(outputs / "response.txt")]


def test_command_rule_requires_patterns_in_same_invocation(tmp_path: Path) -> None:
    manifest_path = tmp_path / "evals" / "evals.json"
    manifest_path.parent.mkdir()
    manifest_path.write_text(
        json.dumps(
            {
                "manifest_version": 1,
                "skill_name": "test",
                "recommended_suites": {"gating": [1], "regression": [1]},
                "evals": [
                    {
                        "id": 1,
                        "prompt": "test",
                        "expected_output": "test",
                        "files": [],
                        "expectations": ["same command"],
                        "grading_rules": [
                            {
                                "text": "same command",
                                "critical": True,
                                "positive_control": "slcli system list --part-number BATT --status FAILED",
                                "negative_control": "slcli system list --part-number BATT",
                                "scope": "command",
                                "mode": "all_of",
                                "patterns": ["--part-number BATT", "--status FAILED"],
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    response_path = tmp_path / "response.txt"
    response_path.write_text(
        "slcli testmonitor result list --part-number BATT\n"
        "slcli testmonitor result list --status FAILED\n",
        encoding="utf-8",
    )

    output = grade_response(manifest_path, 1, response_path)

    assert output["expectations"][0]["passed"] is False


def test_command_rule_splits_shell_command_lists(tmp_path: Path) -> None:
    rule: dict[str, Any] = {
        "mode": "all_of",
        "scope": "command",
        "patterns": ["--part-number BATT", "--status FAILED"],
    }

    commands = extract_slcli_commands(
        "slcli testmonitor result list --part-number BATT && "
        "slcli testmonitor result list --status FAILED"
    )

    assert commands == [
        "slcli testmonitor result list --part-number BATT",
        "slcli testmonitor result list --status FAILED",
    ]
    assert evaluate_rule(" && ".join(commands), rule)[0] is False


def test_previous_calendar_month_validator_checks_exact_bounds() -> None:
    rule = {
        "mode": "all_of",
        "scope": "command",
        "validator": "previous_calendar_month",
        "patterns": ["startedAt >=", "startedAt <", "--substitution"],
    }
    reference_date = date(2026, 9, 8)

    valid, _ = evaluate_rule(
        "slcli testmonitor result list --filter 'startedAt >= @0 && startedAt < @1' "
        "--substitution 2026-08-01 --substitution 2026-09-01",
        rule,
        reference_date,
    )
    stale, _ = evaluate_rule(
        "slcli testmonitor result list --filter 'startedAt >= @0 && startedAt < @1' "
        "--substitution 2025-01-01 --substitution 2025-02-01",
        rule,
        reference_date,
    )

    assert valid is True
    assert stale is False


def test_previous_calendar_month_validator_checks_referenced_substitution_positions() -> None:
    rule = {
        "mode": "all_of",
        "scope": "command",
        "validator": "previous_calendar_month",
        "patterns": ["startedAt >=", "startedAt <", "--substitution"],
    }
    response = (
        "slcli testmonitor result list --filter 'startedAt >= @0 && startedAt < @1' "
        "--substitution 2025-01-01 --substitution 2025-02-01 "
        "--substitution 2026-08-01 --substitution 2026-09-01"
    )

    assert evaluate_rule(response, rule, date(2026, 9, 8))[0] is False


def test_profile_normalization_applies_to_required_and_forbidden_rules() -> None:
    required = {"mode": "any_of", "scope": "command", "patterns": [r"slcli\s+system\s+list"]}
    forbidden = {"mode": "none_of", "scope": "command", "patterns": [r"slcli\s+asset\s+list"]}

    assert evaluate_rule("slcli --profile prod system list", required)[0] is True
    assert evaluate_rule("slcli -p prod asset list", forbidden)[0] is False


def test_resource_query_grader_checks_structured_results() -> None:
    records = [
        {
            "command": "slcli system list --format json",
            "exit_code": 0,
            "stdout_json": [{"name": "PXI-Rack-07"}],
        }
    ]
    rule: dict[str, Any] = {
        "grader_type": "resource_query",
        "grader_config": {
            "command_pattern": r"slcli\s+system\s+list",
            "resource_type": "system",
            "match": {"name": "PXI-Rack-07"},
            "minimum_count": 1,
        },
    }

    assert evaluate_structured_rule(rule, records, Path("."))[0] is True
    rule["grader_config"]["match"] = {"name": "missing"}
    assert evaluate_structured_rule(rule, records, Path("."))[0] is False


def test_resource_set_and_relationship_graders_check_expected_values() -> None:
    records = [
        {
            "command": "slcli testmonitor result list --format json",
            "exit_code": 0,
            "stdout_json": [
                {"name": "Result 1", "systemId": "system-1"},
                {"name": "Result 2", "systemId": "system-1"},
            ],
        }
    ]
    resource_set = {
        "grader_type": "resource_set",
        "grader_config": {
            "expected": [{"name": "Result 1"}, {"name": "Result 2"}],
        },
    }
    relationship: dict[str, Any] = {
        "grader_type": "relationship",
        "grader_config": {
            "match": {"name": "Result 1"},
            "path": "system_id",
            "expected": "system-1",
        },
    }

    assert evaluate_structured_rule(resource_set, records, Path("."))[0] is True
    assert evaluate_structured_rule(relationship, records, Path("."))[0] is True
    relationship["grader_config"]["expected"] = "wrong-system"
    assert evaluate_structured_rule(relationship, records, Path("."))[0] is False


def test_negative_query_and_mutation_safety_graders_reject_bad_controls() -> None:
    negative_records = [
        {"command": "slcli testmonitor product list", "exit_code": 0, "stdout_json": []}
    ]
    negative_rule = {
        "grader_type": "negative_query",
        "grader_config": {"command_pattern": r"product\s+list"},
    }
    safe_rule = {"grader_type": "mutation_safety", "grader_config": {}}
    unsafe_records = [
        {"command": "slcli asset create --name unexpected", "exit_code": 0, "stdout_json": {}}
    ]

    assert evaluate_structured_rule(negative_rule, negative_records, Path("."))[0] is True
    assert evaluate_structured_rule(safe_rule, negative_records, Path("."))[0] is True
    assert evaluate_structured_rule(safe_rule, unsafe_records, Path("."))[0] is False


def test_snapshot_and_cleanup_graders_check_artifacts(tmp_path: Path) -> None:
    before = {"status": "ready", "snapshot_hash": "same"}
    after = {"status": "ready", "snapshot_hash": "same"}
    (tmp_path / "fixture_snapshot_before.json").write_text(json.dumps(before), encoding="utf-8")
    (tmp_path / "fixture_snapshot_after.json").write_text(json.dumps(after), encoding="utf-8")
    (tmp_path / "cleanup_report.json").write_text(json.dumps({"status": "clean"}), encoding="utf-8")

    snapshot_rule = {
        "grader_type": "snapshot",
        "grader_config": {"expected_status": "ready"},
    }
    cleanup_rule = {"grader_type": "cleanup", "grader_config": {}}

    assert evaluate_structured_rule(snapshot_rule, [], tmp_path)[0] is True
    assert evaluate_structured_rule(cleanup_rule, [], tmp_path)[0] is True
    (tmp_path / "fixture_snapshot_after.json").write_text(
        json.dumps({"status": "ready", "snapshot_hash": "changed"}), encoding="utf-8"
    )
    assert evaluate_structured_rule(snapshot_rule, [], tmp_path)[0] is False


def test_structured_grader_marks_missing_execution_records_inconclusive() -> None:
    rule = {
        "grader_type": "resource_query",
        "grader_config": {"resource_type": "system"},
    }

    passed, _, status = evaluate_structured_rule(rule, [], Path("."))

    assert passed is False
    assert status == "inconclusive"


def test_grade_response_evaluates_complete_live_artifacts(tmp_path: Path) -> None:
    manifest_path = tmp_path / "skill" / "evals" / "evals.json"
    manifest = {
        "manifest_version": 1,
        "skill_name": "test",
        "recommended_suites": {"gating": [12], "regression": [12], "live_readonly": [12]},
        "evals": [
            {
                "id": 12,
                "execution_mode": "live_readonly",
                "fixture": {
                    "example": "demo-data-3",
                    "profile": "test",
                    "workspace": "fixture-workspace",
                },
                "mutation_policy": "forbidden",
                "resource_prerequisites": [{"type": "system", "match": {"name": "PXI-Rack-07"}}],
                "prompt": "List the fixture system.",
                "expected_output": "The fixture system.",
                "files": [],
                "expectations": ["Uses live structured output."],
                "grading_rules": [
                    {
                        "text": "Finds the fixture system",
                        "critical": True,
                        "grader_type": "resource_query",
                        "grader_config": {
                            "command_pattern": r"slcli\s+system\s+list",
                            "match": {"name": "PXI-Rack-07"},
                        },
                    },
                    {
                        "text": "Preserves the fixture",
                        "critical": True,
                        "grader_type": "snapshot",
                        "grader_config": {
                            "comparison": "unchanged",
                            "expected_status": "ready",
                        },
                    },
                ],
            }
        ],
    }
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    (outputs / "response.txt").write_text("The system is PXI-Rack-07.\n", encoding="utf-8")
    (outputs / "execution_records.json").write_text(
        json.dumps(
            [
                {
                    "command": "slcli system list --format json",
                    "exit_code": 0,
                    "stdout_json": [{"id": "system-id", "name": "PXI-Rack-07"}],
                }
            ]
        ),
        encoding="utf-8",
    )
    for name in (
        "fixture_snapshot.json",
        "fixture_snapshot_before.json",
        "fixture_snapshot_after.json",
    ):
        (outputs / name).write_text(
            json.dumps({"status": "ready", "snapshot_hash": "unchanged"}), encoding="utf-8"
        )

    grading = grade_response(manifest_path, 12, outputs)

    assert grading["evaluation"]["fixture_readiness"] == "ready"
    assert grading["summary"]["pass_rate"] == 1.0
    assert all(result["passed"] for result in grading["expectations"])


def test_grade_response_applies_online_override_and_cleanup_rule(tmp_path: Path) -> None:
    manifest_path = tmp_path / "evals.json"
    manifest_path.write_text(
        json.dumps(
            {
                "manifest_version": 1,
                "skill_name": "test",
                "recommended_suites": {"gating": [7], "regression": [7]},
                "evals": [
                    {
                        "id": 7,
                        "prompt": "Create a resource.",
                        "expected_output": "Creates a resource.",
                        "files": [],
                        "expectations": [],
                        "grading_rules": [
                            {
                                "text": "Cleans the fixture",
                                "critical": True,
                                "grader_type": "cleanup",
                                "grader_config": {},
                                "required_in_modes": ["online"],
                            }
                        ],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    outputs = tmp_path / "outputs"
    outputs.mkdir()
    (outputs / "response.txt").write_text("Done.\n", encoding="utf-8")

    grading = grade_response(
        manifest_path,
        7,
        outputs,
        eval_entry_override={
            "execution_mode": "online",
            "fixture_scope": "isolated",
            "mutation_policy": "allow_with_cleanup",
        },
    )

    assert grading["evaluation"]["execution_mode"] == "online"
    assert grading["expectations"][0]["status"] == "inconclusive"

    (outputs / "cleanup_report.json").write_text(json.dumps({"status": "clean"}), encoding="utf-8")
    grading = grade_response(
        manifest_path,
        7,
        outputs,
        eval_entry_override={
            "execution_mode": "online",
            "fixture_scope": "isolated",
            "mutation_policy": "allow_with_cleanup",
        },
    )

    assert grading["expectations"][0]["passed"] is True
