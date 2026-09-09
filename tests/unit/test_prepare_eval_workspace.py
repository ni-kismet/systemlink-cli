"""Unit tests for skill eval workspace preparation."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
from pathlib import Path

import pytest

from slcli.skills.slcli.scripts.eval_manifest import load_manifest
from slcli.skills.slcli.scripts.prepare_eval_prompts import build_prompt
from slcli.skills.slcli.scripts.prepare_eval_workspace import (
    create_old_skill_snapshot,
    create_repository_snapshots,
    create_without_skill_snapshots,
    hash_directory,
    positive_int,
    prepare_iteration_directory,
    scaffold_eval_dir,
    select_evals,
)
from slcli.webapp_click import _validate_plugin_manager_metadata


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

    candidate_root, snapshot_root, merge_base = create_old_skill_snapshot(
        skill_dir, tmp_path / "iteration", "main"
    )

    assert merge_base
    assert (candidate_root / "slcli" / "skills" / "slcli" / "SKILL.md").read_text(
        encoding="utf-8"
    ) == "candidate skill\n"
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
        configuration="old_skill",
        max_tool_calls=8,
        max_minutes=3,
        repository_root=str(baseline_repo),
    )

    assert f"Skill path: {baseline_repo / 'slcli' / 'skills' / 'slcli'}" in prompt
    assert "Use the merge-base version of the skill" in prompt


def test_with_skill_prompt_loads_isolated_candidate_skill(tmp_path: Path) -> None:
    candidate_repo = tmp_path / "candidate_repo"

    prompt = build_prompt(
        skill_path=tmp_path / "working-skill",
        prompt_text="Do the task",
        input_files=[],
        output_dir=tmp_path / "outputs",
        configuration="with_skill",
        max_tool_calls=8,
        max_minutes=3,
        repository_root=str(candidate_repo),
    )

    assert f"Skill path: {candidate_repo / 'slcli' / 'skills' / 'slcli'}" in prompt
    assert f"Use this isolated candidate repo root: {candidate_repo}" in prompt
    assert "transcript.jsonl containing the complete executor trace" in prompt
    assert f"{tmp_path / 'timing.json'} containing duration_ms and total_tokens" in prompt
    assert "Write timing.json only to the run-root path specified above" in prompt


def test_scaffold_eval_uses_independent_run_repos_and_neutral_inputs(tmp_path: Path) -> None:
    skill_dir = tmp_path / "working" / "slcli" / "skills" / "slcli"
    fixture = skill_dir / "evals" / "files" / "input.txt"
    fixture.parent.mkdir(parents=True)
    fixture.write_text("fixture\n", encoding="utf-8")
    candidate_template = tmp_path / "candidate-template"
    baseline_template = tmp_path / "baseline-template"
    for template, content in (
        (candidate_template, "candidate\n"),
        (baseline_template, "baseline\n"),
    ):
        template_skill = template / "slcli" / "skills" / "slcli"
        template_skill.mkdir(parents=True)
        (template_skill / "SKILL.md").write_text(content, encoding="utf-8")

    iteration_dir = tmp_path / "iteration"
    iteration_dir.mkdir()
    scaffold_eval_dir(
        skill_dir,
        iteration_dir,
        {
            "id": 1,
            "prompt": "Use the fixture",
            "expectations": [],
            "tags": ["gating"],
            "files": ["evals/files/input.txt"],
        },
        "old_skill",
        2,
        candidate_template,
        baseline_template,
    )

    eval_dir = next(iteration_dir.glob("eval-*"))
    candidate_roots = [
        Path(
            json.loads(
                (eval_dir / "with_skill" / f"run-{run}" / "run_config.json").read_text(
                    encoding="utf-8"
                )
            )["repository_root"]
        )
        for run in (1, 2)
    ]
    baseline_root = Path(
        json.loads(
            (eval_dir / "old_skill" / "run-1" / "run_config.json").read_text(encoding="utf-8")
        )["repository_root"]
    )
    input_record = json.loads((eval_dir / "inputs_manifest.json").read_text(encoding="utf-8"))[
        "files"
    ][0]
    input_path = Path(input_record["absolute_path"])

    assert candidate_roots[0] != candidate_roots[1]
    assert candidate_roots[0].is_relative_to(eval_dir)
    assert baseline_root.is_relative_to(eval_dir)
    assert input_path.is_relative_to(eval_dir / "inputs")
    assert not input_path.is_relative_to(skill_dir)
    assert input_record["sha256"] == hashlib.sha256(input_path.read_bytes()).hexdigest()
    (candidate_roots[0] / "changed.txt").write_text("changed\n", encoding="utf-8")
    assert not (candidate_roots[1] / "changed.txt").exists()


def test_scaffold_eval_rejects_fixture_path_traversal(tmp_path: Path) -> None:
    skill_dir = tmp_path / "skill"
    skill_dir.mkdir()
    (tmp_path / "outside.txt").write_text("outside\n", encoding="utf-8")
    iteration_dir = tmp_path / "iteration"
    iteration_dir.mkdir()

    with pytest.raises(ValueError, match="must stay within the skill directory"):
        scaffold_eval_dir(
            skill_dir,
            iteration_dir,
            {
                "id": 1,
                "prompt": "Use the fixture",
                "expectations": [],
                "tags": ["gating"],
                "files": ["../outside.txt"],
            },
            "without_skill",
            1,
            None,
            None,
        )


def test_scaffold_eval_copies_complete_webapp_fixture(tmp_path: Path) -> None:
    skill_dir = Path("slcli/skills/slcli").resolve()
    manifest = load_manifest(skill_dir / "evals" / "evals.json")
    entry = next(item for item in manifest["evals"] if item["id"] == 11)
    iteration_dir = tmp_path / "iteration"
    iteration_dir.mkdir()

    scaffold_eval_dir(
        skill_dir,
        iteration_dir,
        entry,
        "without_skill",
        1,
        None,
        None,
    )

    eval_dir = next(iteration_dir.glob("eval-*"))
    config_path = eval_dir / "inputs" / "evals/files/webapp-package/nipkg.config.json"
    metadata = json.loads(config_path.read_text(encoding="utf-8"))
    validated = _validate_plugin_manager_metadata(
        metadata, require_build_dir=True, base_dir=config_path.parent
    )

    assert (config_path.parent / validated["buildDir"]).is_dir()


def test_select_evals_deduplicates_explicit_ids() -> None:
    manifest = {
        "evals": [{"id": 1}, {"id": 2}],
        "recommended_suites": {"gating": [1], "regression": [1, 2]},
    }

    selected = select_evals(manifest, "gating", [2, 1, 2])

    assert [entry["id"] for entry in selected] == [2, 1]


def test_positive_int_rejects_non_positive_values() -> None:
    with pytest.raises(argparse.ArgumentTypeError, match="greater than zero"):
        positive_int("0")


def test_without_skill_snapshots_isolate_candidate_and_baseline(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    skill_dir = repo / "slcli" / "skills" / "slcli"
    workspace = repo / "slcli" / "skills" / "slcli-workspace"
    iteration = workspace / "iteration-1"
    skill_dir.mkdir(parents=True)
    iteration.mkdir(parents=True)
    (repo / "pyproject.toml").write_text("[tool.poetry]\nname = 'test'\n", encoding="utf-8")
    (skill_dir / "SKILL.md").write_text("skill\n", encoding="utf-8")
    (iteration / "stale.txt").write_text("stale\n", encoding="utf-8")

    candidate, baseline = create_without_skill_snapshots(skill_dir, iteration, False)

    assert (candidate / "slcli" / "skills" / "slcli" / "SKILL.md").is_file()
    assert not (candidate / "slcli" / "skills" / "slcli-workspace").exists()
    assert not (baseline / "slcli" / "skills" / "slcli-workspace").exists()
    assert not (baseline / "slcli" / "skills" / "slcli").exists()


def test_without_skill_baseline_always_creates_repository_snapshots(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    skill_dir = repo / "slcli" / "skills" / "slcli"
    iteration = repo / "slcli" / "skills" / "slcli-workspace" / "iteration-1"
    skill_dir.mkdir(parents=True)
    iteration.mkdir(parents=True)
    (repo / "pyproject.toml").write_text("[tool.poetry]\nname = 'test'\n", encoding="utf-8")
    (skill_dir / "SKILL.md").write_text("skill\n", encoding="utf-8")

    candidate, baseline, baseline_sha = create_repository_snapshots(
        skill_dir, iteration, "without_skill", "origin/main", False
    )

    assert (candidate / "slcli" / "skills" / "slcli" / "SKILL.md").is_file()
    assert not (baseline / "slcli" / "skills" / "slcli").exists()
    assert baseline_sha is None


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
