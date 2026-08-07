"""Unit tests for slcli eval response grading."""

from __future__ import annotations

import json
from pathlib import Path

from slcli.skills.slcli.scripts.grade_eval_response import gather_response_text, grade_response


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
                "evals": [
                    {
                        "id": 1,
                        "tags": ["gating"],
                        "grading_rules": [
                            {
                                "text": "Matches command",
                                "mode": "any_of",
                                "patterns": [r"slcli\s+testmonitor"],
                            }
                        ],
                    }
                ]
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
