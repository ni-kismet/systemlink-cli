"""Prepare an eval workspace for the slcli skill.

Creates the directory layout expected by the upstream skill-creator benchmark
and viewer flow so runs can be saved and graded consistently.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tarfile
from datetime import date
from io import BytesIO
from pathlib import Path
from typing import Any

from slcli.skills.slcli.scripts.eval_manifest import load_manifest, resolve_fixture_path

EVAL_WORKFLOW_SCRIPTS = frozenset(
    {
        "benchmark_iteration.py",
        "compare_iteration.py",
        "eval_manifest.py",
        "grade_eval_response.py",
        "grade_iteration.py",
        "prepare_eval_prompts.py",
        "prepare_eval_workspace.py",
        "render_eval_review.py",
    }
)


def positive_int(value: str) -> int:
    """Parse a positive integer argument."""
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be greater than zero")
    return parsed


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    script_dir = Path(__file__).resolve().parent
    skill_dir = script_dir.parent
    default_evals = skill_dir / "evals" / "evals.json"
    default_workspace = skill_dir.parent / f"{skill_dir.name}-workspace"

    parser = argparse.ArgumentParser(description="Scaffold an eval workspace for the slcli skill.")
    parser.add_argument(
        "--evals",
        type=Path,
        default=default_evals,
        help="Path to evals.json.",
    )
    parser.add_argument(
        "--workspace-root",
        type=Path,
        default=default_workspace,
        help="Root directory for iteration artifacts.",
    )
    parser.add_argument(
        "--iteration",
        type=int,
        help="Iteration number to create. Defaults to the next available number.",
    )
    parser.add_argument(
        "--suite",
        choices=["gating", "regression"],
        default="gating",
        help="Recommended suite to scaffold.",
    )
    parser.add_argument(
        "--eval-id",
        type=int,
        action="append",
        dest="eval_ids",
        help="Specific eval ID to include. Repeat to include multiple evals.",
    )
    parser.add_argument(
        "--runs-per-config",
        type=positive_int,
        default=3,
        help="Number of run directories to create for each configuration.",
    )
    parser.add_argument(
        "--baseline",
        choices=["without_skill", "old_skill"],
        default="old_skill",
        help="Baseline configuration directory name.",
    )
    parser.add_argument(
        "--baseline-ref",
        default="origin/main",
        help="Git ref used to find the merge-base skill snapshot.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow scaffolding into an existing iteration directory.",
    )
    parser.add_argument(
        "--isolate-baseline",
        action="store_true",
        help="Deprecated compatibility option; baselines are always isolated.",
    )
    return parser.parse_args()


def slugify(text: str) -> str:
    """Convert free text to a filesystem-safe slug."""
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower())
    return cleaned.strip("-") or "eval"


def select_evals(
    manifest: dict[str, Any], suite: str, explicit_ids: list[int] | None
) -> list[dict[str, Any]]:
    """Select evals from the manifest by suite or explicit ID list."""
    evals = manifest.get("evals", [])
    by_id = {entry["id"]: entry for entry in evals}

    if explicit_ids:
        explicit_ids = list(dict.fromkeys(explicit_ids))
        missing = [eval_id for eval_id in explicit_ids if eval_id not in by_id]
        if missing:
            raise ValueError(f"Unknown eval IDs: {missing}")
        return [by_id[eval_id] for eval_id in explicit_ids]

    suite_ids = manifest.get("recommended_suites", {}).get(suite, [])
    if not suite_ids:
        raise ValueError(f"Suite '{suite}' is not defined in the manifest")
    return [by_id[eval_id] for eval_id in suite_ids]


def next_iteration_number(workspace_root: Path) -> int:
    """Find the next available iteration number."""
    existing = []
    for path in workspace_root.glob("iteration-*"):
        try:
            existing.append(int(path.name.split("-")[1]))
        except (IndexError, ValueError):
            continue
    return (max(existing) + 1) if existing else 1


def build_eval_name(entry: dict[str, Any]) -> str:
    """Build a human-readable eval name."""
    tags = entry.get("tags", [])
    prefix = tags[0] if tags else "eval"
    return f"{prefix}-{entry['id']}-{slugify(entry['prompt'])[:48]}"


def write_json(path: Path, payload: dict[str, Any]) -> None:
    """Write JSON with stable formatting."""
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def find_repo_root(skill_dir: Path) -> Path:
    """Find the repository root that contains the skill."""
    for candidate in [skill_dir, *skill_dir.parents]:
        if (candidate / "pyproject.toml").exists():
            return candidate
    raise ValueError(f"Could not determine repository root from {skill_dir}")


def run_git(repo_root: Path, *args: str) -> str:
    """Run Git and return stripped standard output."""
    result = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def git_file_paths(repo_root: Path, *args: str) -> list[Path]:
    """Return repository file paths from Git as relative paths."""
    result = subprocess.run(
        ["git", "ls-files", "-z", *args],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    return [Path(path) for path in result.stdout.decode("utf-8").split("\0") if path]


def copy_worktree_file(source: Path, destination: Path) -> None:
    """Copy one worktree file while preserving symbolic links."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    if source.is_symlink():
        destination.symlink_to(source.readlink())
    elif source.is_file():
        shutil.copy2(source, destination)


def create_candidate_snapshot(
    repo_root: Path,
    skill_dir: Path,
    destination: Path,
    workspace_root: Path,
) -> None:
    """Copy tracked worktree files and non-ignored untracked candidate-skill files."""
    repo_root = repo_root.resolve()
    skill_relative_path = skill_dir.resolve().relative_to(repo_root)
    destination.mkdir(parents=True, exist_ok=True)
    exclude_workspace = repo_root in workspace_root.parents

    for relative_path in git_file_paths(repo_root):
        source = repo_root / relative_path
        if exclude_workspace and (workspace_root in source.parents or source == workspace_root):
            continue
        if source.exists() or source.is_symlink():
            copy_worktree_file(source, destination / relative_path)

    for relative_path in git_file_paths(
        repo_root, "--others", "--exclude-standard", "--", skill_relative_path.as_posix()
    ):
        source = repo_root / relative_path
        if source.exists() or source.is_symlink():
            copy_worktree_file(source, destination / relative_path)


def hash_directory(directory: Path) -> str:
    """Return a stable SHA-256 hash for a directory tree."""
    digest = hashlib.sha256()
    for file_path in sorted(
        path
        for path in directory.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts and path.suffix != ".pyc"
    ):
        digest.update(file_path.relative_to(directory).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(file_path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def hash_file(path: Path) -> str:
    """Return a SHA-256 hash for one file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_input_manifest_hashes(iteration_dir: Path) -> dict[str, str]:
    """Map each run directory to its prepared input manifest hash."""
    return {
        path.parent.relative_to(iteration_dir).as_posix(): hash_file(path)
        for path in sorted(iteration_dir.rglob("inputs_manifest.json"))
    }


def remove_eval_workflow_files(repository_root: Path, skill_relative_path: Path) -> None:
    """Remove the eval corpus and harness from a runtime skill snapshot."""
    skill_snapshot = repository_root / skill_relative_path
    shutil.rmtree(skill_snapshot / "evals", ignore_errors=True)
    for script_name in EVAL_WORKFLOW_SCRIPTS:
        (skill_snapshot / "scripts" / script_name).unlink(missing_ok=True)


def create_old_skill_snapshot(
    skill_dir: Path,
    iteration_dir: Path,
    baseline_ref: str,
) -> tuple[Path, Path, str]:
    """Create paired candidate and old-skill sandboxes from the candidate state."""
    repo_root = find_repo_root(skill_dir)
    merge_base = run_git(repo_root, "merge-base", baseline_ref, "HEAD")
    candidate_root = iteration_dir / "candidate_repo"
    snapshot_root = iteration_dir / "baseline_repo"
    workspace_root = iteration_dir.parent.resolve()
    if workspace_root == repo_root.resolve():
        raise ValueError(
            "Iteration directory must be inside a workspace directory within the repository; "
            "using the repository root as its workspace would recursively copy the destination."
        )

    create_candidate_snapshot(repo_root, skill_dir, candidate_root, workspace_root)
    shutil.copytree(candidate_root, snapshot_root)

    skill_relative_path = skill_dir.relative_to(repo_root)
    remove_eval_workflow_files(candidate_root, skill_relative_path)
    remove_eval_workflow_files(snapshot_root, skill_relative_path)
    old_skill_dir = snapshot_root / skill_relative_path
    shutil.rmtree(old_skill_dir)

    archive = subprocess.run(
        ["git", "archive", "--format=tar", merge_base, "--", skill_relative_path.as_posix()],
        cwd=repo_root,
        check=True,
        capture_output=True,
    ).stdout
    with tarfile.open(fileobj=BytesIO(archive), mode="r:") as tar:
        tar.extractall(snapshot_root)
    remove_eval_workflow_files(snapshot_root, skill_relative_path)

    if not (old_skill_dir / "SKILL.md").exists():
        raise ValueError(f"Skill does not exist at merge base {merge_base}: {old_skill_dir}")
    return candidate_root, snapshot_root, merge_base


def create_without_skill_snapshots(
    skill_dir: Path,
    iteration_dir: Path,
    force: bool,
) -> tuple[Path, Path]:
    """Create paired candidate and skill-free repository snapshots."""
    repo_root = find_repo_root(skill_dir)
    candidate_root = iteration_dir / "candidate_repo"
    baseline_root = iteration_dir / "baseline_repo"
    existing = [path for path in (candidate_root, baseline_root) if path.exists()]
    if existing:
        if not force:
            raise FileExistsError(
                f"{existing[0]} already exists. Use --force to recreate repository snapshots."
            )
        for path in existing:
            shutil.rmtree(path)

    workspace_root = iteration_dir.parent.resolve()
    if workspace_root == repo_root.resolve():
        raise ValueError(
            "Iteration directory must be inside a workspace directory within the repository; "
            "using the repository root as its workspace would recursively copy the destination."
        )

    create_candidate_snapshot(repo_root, skill_dir, candidate_root, workspace_root)
    shutil.copytree(candidate_root, baseline_root)

    skill_relative_path = skill_dir.relative_to(repo_root)
    remove_eval_workflow_files(candidate_root, skill_relative_path)
    remove_eval_workflow_files(baseline_root, skill_relative_path)
    isolated_skill_dir = baseline_root / skill_relative_path
    if isolated_skill_dir.exists():
        shutil.rmtree(isolated_skill_dir)

    return candidate_root, baseline_root


def create_repository_snapshots(
    skill_dir: Path,
    iteration_dir: Path,
    baseline: str,
    baseline_ref: str,
    force: bool,
) -> tuple[Path, Path, str | None]:
    """Create paired repository snapshots for the selected baseline."""
    if baseline == "old_skill":
        return create_old_skill_snapshot(skill_dir, iteration_dir, baseline_ref)
    candidate_root, baseline_root = create_without_skill_snapshots(skill_dir, iteration_dir, force)
    return candidate_root, baseline_root, None


def make_run_dirs(
    eval_dir: Path,
    configurations: list[str],
    runs_per_config: int,
    repo_templates: dict[str, Path | None],
) -> None:
    """Create run directories with independent repository sandboxes."""
    for configuration in configurations:
        for run_number in range(1, runs_per_config + 1):
            run_dir = eval_dir / configuration / f"run-{run_number}"
            outputs_dir = run_dir / "outputs"
            outputs_dir.mkdir(parents=True, exist_ok=True)
            repository_root = None
            repo_template = repo_templates.get(configuration)
            if repo_template is not None:
                repository_root = run_dir / "repo"
                shutil.copytree(repo_template, repository_root)
            write_json(
                run_dir / "run_config.json",
                {
                    "configuration": configuration,
                    "repository_root": (
                        str(repository_root.resolve()) if repository_root else None
                    ),
                },
            )


def prepare_iteration_directory(iteration_dir: Path, force: bool) -> None:
    """Create an empty iteration directory, replacing it only when requested."""
    if iteration_dir.exists():
        if not force:
            raise FileExistsError(
                f"{iteration_dir} already exists. Use --force or choose another iteration number."
            )
        shutil.rmtree(iteration_dir)
    iteration_dir.mkdir(parents=True)


def scaffold_eval_dir(
    skill_dir: Path,
    iteration_dir: Path,
    entry: dict[str, Any],
    baseline: str,
    runs_per_config: int,
    candidate_repo_root: Path | None,
    baseline_repo_root: Path | None,
) -> None:
    """Create one eval directory and its metadata."""
    eval_name = build_eval_name(entry)
    eval_dir = iteration_dir / f"eval-{entry['id']}-{slugify(eval_name)}"
    eval_dir.mkdir(parents=True, exist_ok=True)

    metadata = {
        "eval_id": entry["id"],
        "eval_name": eval_name,
        "prompt": entry["prompt"],
        "assertions": entry.get("expectations", []),
        "tags": entry.get("tags", []),
    }
    write_json(eval_dir / "eval_metadata.json", metadata)

    (eval_dir / "prompt.txt").write_text(entry["prompt"] + "\n", encoding="utf-8")
    make_run_dirs(
        eval_dir,
        ["with_skill", baseline],
        runs_per_config,
        {"with_skill": candidate_repo_root, baseline: baseline_repo_root},
    )

    for configuration in ["with_skill", baseline]:
        for run_number in range(1, runs_per_config + 1):
            run_dir = eval_dir / configuration / f"run-{run_number}"
            input_files = []
            input_root = (run_dir / "inputs").resolve()
            for relative_path in entry.get("files", []):
                source_path = resolve_fixture_path(skill_dir, relative_path)
                input_path = (input_root / relative_path).resolve()
                if not input_path.is_relative_to(input_root):
                    raise ValueError(
                        f"fixture destination must stay within inputs: {relative_path}"
                    )
                input_path.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source_path, input_path)
                input_files.append(
                    {
                        "relative_path": relative_path,
                        "absolute_path": str(input_path.resolve()),
                        "sha256": hash_file(input_path),
                    }
                )
            write_json(run_dir / "inputs_manifest.json", {"files": input_files})


def main() -> None:
    """Entry point."""
    args = parse_args()
    manifest = load_manifest(args.evals)
    selected = select_evals(manifest, args.suite, args.eval_ids)
    skill_dir = args.evals.parent.parent

    workspace_root = args.workspace_root
    workspace_root.mkdir(parents=True, exist_ok=True)
    iteration_number = args.iteration or next_iteration_number(workspace_root)
    iteration_dir = workspace_root / f"iteration-{iteration_number}"
    prepare_iteration_directory(iteration_dir, args.force)

    candidate_repo_root, baseline_repo_root, baseline_sha = create_repository_snapshots(
        skill_dir,
        iteration_dir,
        args.baseline,
        args.baseline_ref,
        args.force,
    )

    repo_root = find_repo_root(skill_dir)
    candidate_sha = run_git(repo_root, "rev-parse", "HEAD")

    for entry in selected:
        scaffold_eval_dir(
            skill_dir,
            iteration_dir,
            entry,
            args.baseline,
            args.runs_per_config,
            candidate_repo_root,
            baseline_repo_root,
        )

    summary = {
        "skill_name": manifest.get("skill_name"),
        "suite": args.suite,
        "baseline": args.baseline,
        "baseline_isolated": bool(baseline_repo_root),
        "candidate_repo_template": (
            str(candidate_repo_root.resolve()) if candidate_repo_root else None
        ),
        "baseline_repo_template": (
            str(baseline_repo_root.resolve()) if baseline_repo_root else None
        ),
        "baseline_ref": args.baseline_ref if args.baseline == "old_skill" else None,
        "baseline_sha": baseline_sha,
        "candidate_sha": candidate_sha,
        "candidate_skill_hash": hash_directory(
            candidate_repo_root / skill_dir.relative_to(repo_root)
            if candidate_repo_root
            else skill_dir
        ),
        "eval_manifest_hash": hashlib.sha256(args.evals.read_bytes()).hexdigest(),
        "baseline_skill_hash": (
            hash_directory(baseline_repo_root / skill_dir.relative_to(repo_root))
            if baseline_repo_root and args.baseline == "old_skill"
            else None
        ),
        "reference_date": date.today().isoformat(),
        "iteration": iteration_number,
        "runs_per_config": args.runs_per_config,
        "eval_ids": [entry["id"] for entry in selected],
        "input_manifest_hashes": build_input_manifest_hashes(iteration_dir),
    }
    write_json(iteration_dir / "iteration_manifest.json", summary)
    print(iteration_dir)


if __name__ == "__main__":
    main()
