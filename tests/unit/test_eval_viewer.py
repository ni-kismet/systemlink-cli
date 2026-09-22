"""Unit tests for the bundled skill eval viewer."""

from __future__ import annotations

import runpy
from pathlib import Path


def test_build_run_finds_metadata_at_eval_ancestor(tmp_path: Path) -> None:
    module = runpy.run_path(
        ".github/skills/skill-creator/eval-viewer/generate_review.py",
        run_name="eval_viewer_test",
    )
    build_run = module["build_run"]
    eval_dir = tmp_path / "eval-7-workitem"
    run_dir = eval_dir / "with_skill" / "run-1"
    (run_dir / "outputs").mkdir(parents=True)
    (eval_dir / "eval_metadata.json").write_text(
        '{"eval_id": 7, "prompt": "Create a work item template"}\n',
        encoding="utf-8",
    )

    result = build_run(tmp_path, run_dir)

    assert result["eval_id"] == 7
    assert result["prompt"] == "Create a work item template"
