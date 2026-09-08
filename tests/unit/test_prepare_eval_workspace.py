"""Unit tests for skill eval workspace preparation."""

from __future__ import annotations

import subprocess
from pathlib import Path

from slcli.skills.slcli.scripts.prepare_eval_prompts import build_prompt
from slcli.skills.slcli.scripts.prepare_eval_workspace import create_old_skill_snapshot


def run_git(repo: Path, *args: str) -> None:
    """Run a Git command in a test repository."""
    subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True, text=True)


def test_create_old_skill_snapshot_exports_merge_base(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    skill_dir = repo / "slcli" / "skills" / "slcli"
    skill_dir.mkdir(parents=True)
    (repo / "pyproject.toml").write_text("[tool.poetry]\nname = 'test'\n", encoding="utf-8")
    (skill_dir / "SKILL.md").write_text("old skill\n", encoding="utf-8")
    run_git(repo, "init", "-b", "main")
    run_git(repo, "config", "user.email", "eval@example.invalid")
    run_git(repo, "config", "user.name", "Eval Test")
    run_git(repo, "add", ".")
    run_git(repo, "commit", "-m", "baseline")
    run_git(repo, "checkout", "-b", "feature")
    (skill_dir / "SKILL.md").write_text("candidate skill\n", encoding="utf-8")
    run_git(repo, "add", ".")
    run_git(repo, "commit", "-m", "candidate")

    snapshot_root, merge_base = create_old_skill_snapshot(
        skill_dir, tmp_path / "iteration", "main", force=False
    )

    assert merge_base
    assert (snapshot_root / "slcli" / "skills" / "slcli" / "SKILL.md").read_text(
        encoding="utf-8"
    ) == "old skill\n"


def test_old_skill_prompt_loads_snapshot_skill(tmp_path: Path) -> None:
    baseline_repo = tmp_path / "baseline_repo"

    prompt = build_prompt(
        skill_path=tmp_path / "candidate",
        prompt_text="Do the task",
        input_files=[],
        output_dir=tmp_path / "outputs",
        artifact_name="response.txt",
        configuration="old_skill",
        max_tool_calls=8,
        max_minutes=3,
        baseline_repo_root=str(baseline_repo),
    )

    assert f"Skill path: {baseline_repo / 'slcli' / 'skills' / 'slcli'}" in prompt
    assert "Use the merge-base version of the skill" in prompt
