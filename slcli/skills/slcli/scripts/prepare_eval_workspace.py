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
from io import BytesIO
from pathlib import Path
from typing import Any

from slcli.skills.slcli.scripts.eval_manifest import load_manifest


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
        help="Create an isolated repo for without_skill runs; old_skill is always isolated.",
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

    def ignore_entries(directory: str, names: list[str]) -> set[str]:
        ignored = {".git", ".venv", "__pycache__", ".mypy_cache", ".pytest_cache"}
        return {
            name
            for name in names
            if name in ignored or (Path(directory) / name).resolve() == workspace_root
        }

    shutil.copytree(repo_root, candidate_root, ignore=ignore_entries)
    shutil.copytree(candidate_root, snapshot_root)

    skill_relative_path = skill_dir.relative_to(repo_root)
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

    if not (old_skill_dir / "SKILL.md").exists():
        raise ValueError(f"Skill does not exist at merge base {merge_base}: {old_skill_dir}")
    return candidate_root, snapshot_root, merge_base


def create_isolated_baseline_repo(
    skill_dir: Path,
    iteration_dir: Path,
    baseline: str,
    force: bool,
) -> Path | None:
    """Create a baseline repo snapshot with the skill directory removed."""
    if baseline != "without_skill":
        return None

    repo_root = find_repo_root(skill_dir)
    snapshot_root = iteration_dir / "baseline_repo"
    if snapshot_root.exists():
        if not force:
            raise FileExistsError(
                f"{snapshot_root} already exists. Use --force to recreate the baseline snapshot."
            )
        shutil.rmtree(snapshot_root)

    workspace_root = iteration_dir.parent.resolve()

    def ignore_entries(directory: str, names: list[str]) -> set[str]:
        ignored = {".git", ".venv", "__pycache__", ".mypy_cache", ".pytest_cache"}
        return {
            name
            for name in names
            if name in ignored or (Path(directory) / name).resolve() == workspace_root
        }

    shutil.copytree(repo_root, snapshot_root, ignore=ignore_entries)

    skill_relative_path = skill_dir.relative_to(repo_root)
    isolated_skill_dir = snapshot_root / skill_relative_path
    if isolated_skill_dir.exists():
        shutil.rmtree(isolated_skill_dir)

    return snapshot_root


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

    input_files = []
    for relative_path in entry.get("files", []):
        source_path = skill_dir / relative_path
        input_path = eval_dir / "inputs" / relative_path
        input_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, input_path)
        input_files.append(
            {
                "relative_path": relative_path,
                "absolute_path": str(input_path.resolve()),
                "sha256": hashlib.sha256(input_path.read_bytes()).hexdigest(),
            }
        )
    write_json(eval_dir / "inputs_manifest.json", {"files": input_files})

    (eval_dir / "prompt.txt").write_text(entry["prompt"] + "\n", encoding="utf-8")
    make_run_dirs(
        eval_dir,
        ["with_skill", baseline],
        runs_per_config,
        {"with_skill": candidate_repo_root, baseline: baseline_repo_root},
    )


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

    candidate_repo_root = None
    baseline_repo_root = None
    baseline_sha = None
    if args.baseline == "old_skill":
        candidate_repo_root, baseline_repo_root, baseline_sha = create_old_skill_snapshot(
            skill_dir, iteration_dir, args.baseline_ref
        )
    elif args.isolate_baseline:
        baseline_repo_root = create_isolated_baseline_repo(
            skill_dir,
            iteration_dir,
            args.baseline,
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
        "iteration": iteration_number,
        "runs_per_config": args.runs_per_config,
        "eval_ids": [entry["id"] for entry in selected],
    }
    write_json(iteration_dir / "iteration_manifest.json", summary)
    print(iteration_dir)


if __name__ == "__main__":
    main()
