"""Prepare an eval workspace for the slcli skill.

Creates the directory layout expected by the upstream skill-creator benchmark
and viewer flow so runs can be saved and graded consistently.
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


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
        type=int,
        default=1,
        help="Number of run directories to create for each configuration.",
    )
    parser.add_argument(
        "--baseline",
        choices=["without_skill", "old_skill"],
        default="without_skill",
        help="Baseline configuration directory name.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Allow scaffolding into an existing iteration directory.",
    )
    return parser.parse_args()


def slugify(text: str) -> str:
    """Convert free text to a filesystem-safe slug."""
    cleaned = re.sub(r"[^a-zA-Z0-9]+", "-", text.strip().lower())
    return cleaned.strip("-") or "eval"


def load_manifest(manifest_path: Path) -> dict[str, Any]:
    """Load eval manifest JSON."""
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def select_evals(
    manifest: dict[str, Any], suite: str, explicit_ids: list[int] | None
) -> list[dict[str, Any]]:
    """Select evals from the manifest by suite or explicit ID list."""
    evals = manifest.get("evals", [])
    by_id = {entry["id"]: entry for entry in evals}

    if explicit_ids:
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


def make_run_dirs(eval_dir: Path, configurations: list[str], runs_per_config: int) -> None:
    """Create configuration and run directories."""
    for configuration in configurations:
        for run_number in range(1, runs_per_config + 1):
            outputs_dir = eval_dir / configuration / f"run-{run_number}" / "outputs"
            outputs_dir.mkdir(parents=True, exist_ok=True)


def scaffold_eval_dir(
    skill_dir: Path, iteration_dir: Path, entry: dict[str, Any], baseline: str, runs_per_config: int
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
        input_files.append(
            {
                "relative_path": relative_path,
                "absolute_path": str((skill_dir / relative_path).resolve()),
            }
        )
    write_json(eval_dir / "inputs_manifest.json", {"files": input_files})

    (eval_dir / "prompt.txt").write_text(entry["prompt"] + "\n", encoding="utf-8")
    make_run_dirs(eval_dir, ["with_skill", baseline], runs_per_config)


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
    if iteration_dir.exists() and not args.force:
        raise FileExistsError(
            f"{iteration_dir} already exists. Use --force or choose another iteration number."
        )
    iteration_dir.mkdir(parents=True, exist_ok=True)

    for entry in selected:
        scaffold_eval_dir(skill_dir, iteration_dir, entry, args.baseline, args.runs_per_config)

    summary = {
        "skill_name": manifest.get("skill_name"),
        "suite": args.suite,
        "baseline": args.baseline,
        "iteration": iteration_number,
        "runs_per_config": args.runs_per_config,
        "eval_ids": [entry["id"] for entry in selected],
    }
    write_json(iteration_dir / "iteration_manifest.json", summary)
    print(iteration_dir)


if __name__ == "__main__":
    main()
