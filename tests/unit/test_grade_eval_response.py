"""Unit tests for slcli eval response grading."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from slcli.skills.slcli.scripts.grade_eval_response import (
    evaluate_rule,
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


def test_extract_slcli_commands_normalizes_global_profile_options() -> None:
    assert extract_slcli_commands(
        "slcli --profile prod system list\n"
        "slcli -p test asset list\n"
        "slcli --profile=dev tag list"
    ) == ["slcli system list", "slcli asset list", "slcli tag list"]


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
    rule = {
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
