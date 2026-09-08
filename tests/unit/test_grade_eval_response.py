"""Unit tests for slcli eval response grading."""

from __future__ import annotations

import json
from pathlib import Path

from slcli.skills.slcli.scripts.grade_eval_response import (
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


def test_gather_response_text_replaces_invalid_utf8_bytes(tmp_path: Path) -> None:
    response_path = tmp_path / "response.txt"
    response_path.write_bytes(b"before\xffafter")

    response_text, sources = gather_response_text(response_path)

    assert response_text == "before\ufffdafter"
    assert sources == [str(response_path)]


def test_grade_response_reads_directory_artifacts_with_invalid_utf8(tmp_path: Path) -> None:
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
    (response_dir / "response.log").write_bytes(b"slcli testmonitor\xff result list\n")

    output = grade_response(manifest_path, 1, response_dir)

    assert output["summary"] == {"passed": 1, "failed": 0, "total": 1, "pass_rate": 1.0}
    assert output["eval_feedback"]["sources"] == [str(response_dir / "response.log")]


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
