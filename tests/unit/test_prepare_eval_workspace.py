"""Unit tests for skill eval workspace preparation."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

import pytest

from slcli.skills.slcli.scripts.prepare_eval_prompts import build_prompt
from slcli.skills.slcli.scripts.prepare_eval_workspace import (
    create_isolated_baseline_repo,
    create_old_skill_snapshot,
    hash_directory,
    positive_int,
    prepare_iteration_directory,
)


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


def test_positive_int_rejects_non_positive_values() -> None:
    with pytest.raises(argparse.ArgumentTypeError, match="greater than zero"):
        positive_int("0")


def test_isolated_baseline_excludes_workspace_root(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    skill_dir = repo / "slcli" / "skills" / "slcli"
    workspace = repo / "slcli" / "skills" / "slcli-workspace"
    iteration = workspace / "iteration-1"
    skill_dir.mkdir(parents=True)
    iteration.mkdir(parents=True)
    (repo / "pyproject.toml").write_text("[tool.poetry]\nname = 'test'\n", encoding="utf-8")
    (skill_dir / "SKILL.md").write_text("skill\n", encoding="utf-8")
    (iteration / "stale.txt").write_text("stale\n", encoding="utf-8")

    snapshot = create_isolated_baseline_repo(skill_dir, iteration, "without_skill", False)

    assert snapshot is not None
    assert not (snapshot / "slcli" / "skills" / "slcli-workspace").exists()
    assert not (snapshot / "slcli" / "skills" / "slcli").exists()


def test_hash_directory_ignores_python_cache_files(tmp_path: Path) -> None:
    (tmp_path / "SKILL.md").write_text("skill\n", encoding="utf-8")
    expected = hash_directory(tmp_path)
    cache_dir = tmp_path / "scripts" / "__pycache__"
    cache_dir.mkdir(parents=True)
    (cache_dir / "module.cpython-311.pyc").write_bytes(b"generated")

    assert hash_directory(tmp_path) == expected


def test_force_recreates_iteration_without_stale_outputs(tmp_path: Path) -> None:
    iteration = tmp_path / "iteration-1"
    stale_output = iteration / "eval-old" / "with_skill" / "run-1" / "outputs" / "response.txt"
    stale_output.parent.mkdir(parents=True)
    stale_output.write_text("stale\n", encoding="utf-8")

    prepare_iteration_directory(iteration, force=True)

    assert iteration.is_dir()
    assert not stale_output.exists()
