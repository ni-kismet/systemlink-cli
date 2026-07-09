"""Generate executor prompts for each run in an slcli eval iteration workspace."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    script_dir = Path(__file__).resolve().parent
    skill_dir = script_dir.parent
    parser = argparse.ArgumentParser(
        description="Write executor prompts for every prepared run directory."
    )
    parser.add_argument(
        "iteration_dir",
        type=Path,
        help="Path to an iteration-N directory created by prepare_eval_workspace.py.",
    )
    parser.add_argument(
        "--skill-path",
        type=Path,
        default=skill_dir,
        help="Path to the slcli skill directory used for with_skill runs.",
    )
    parser.add_argument(
        "--artifact-name",
        default="response.txt",
        help="Primary output artifact name to request and optionally stub.",
    )
    parser.add_argument(
        "--max-tool-calls",
        type=int,
        default=8,
        help="Fail-fast budget for one eval run before the orchestrator should stop it.",
    )
    parser.add_argument(
        "--max-minutes",
        type=float,
        default=3.0,
        help="Fail-fast wall-clock budget in minutes for one eval run.",
    )
    parser.add_argument(
        "--max-parallel",
        type=int,
        default=3,
        help="Maximum number of independent runs to schedule in parallel batches.",
    )
    parser.add_argument(
        "--stub-output",
        action="store_true",
        help="Create placeholder output files in empty outputs directories.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Overwrite existing executor prompt files and placeholder output files.",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    """Load a JSON file."""
    return json.loads(path.read_text(encoding="utf-8"))


def relative_or_absolute(path_str: str) -> str:
    """Return a normalized display string for a path."""
    return str(Path(path_str))


def build_prompt(
    skill_path: Path,
    prompt_text: str,
    input_files: list[dict[str, str]],
    output_dir: Path,
    artifact_name: str,
    configuration: str,
    max_tool_calls: int,
    max_minutes: float,
) -> str:
    """Build the executor prompt text for one run."""
    lines = ["Execute this task.", ""]

    if configuration == "with_skill":
        lines.extend(
            [
                f"Skill path: {skill_path}",
                "Use the skill guidance from that path while solving the task.",
                "",
            ]
        )
    else:
        lines.extend(
            [
                "Baseline run: do not load the slcli skill for this execution.",
                "Solve the task without relying on the skill instructions.",
                "",
            ]
        )

    lines.extend([f"Task: {prompt_text}", ""])

    if input_files:
        lines.append("Input files:")
        for input_file in input_files:
            lines.append(f"- {relative_or_absolute(input_file['absolute_path'])}")
    else:
        lines.append("Input files: none")
    lines.append("")

    lines.extend(
        [
            "Execution budget:",
            f"- maximum of {max_tool_calls} tool calls for this run",
            f"- maximum of {max_minutes:g} minutes of active work for this run",
            "- if you do not converge inside that budget, stop early, save the best grounded response you have, and write notes.txt with a brief failure reason",
            "",
            "Save outputs to:",
            f"- {output_dir.resolve()}",
            "",
            "Required output artifacts:",
            f"- {artifact_name} containing the final user-facing answer",
            "- optional notes.txt if you had to make assumptions or explain tradeoffs",
            "",
            "Requirements:",
            "- Keep the answer grounded in supported slcli commands and workflows",
            "- Reference attached files when relevant",
            "- Do not write outside the specified outputs directory",
            "- Prefer a concise answer, but include enough detail for the grader to inspect command choices",
        ]
    )

    return "\n".join(lines) + "\n"


def iter_run_dirs(iteration_dir: Path) -> list[tuple[Path, Path, Path]]:
    """Yield eval metadata, inputs manifest, and run directory paths."""
    triples: list[tuple[Path, Path, Path]] = []
    for eval_dir in sorted(iteration_dir.glob("eval-*")):
        metadata_path = eval_dir / "eval_metadata.json"
        inputs_path = eval_dir / "inputs_manifest.json"
        if not metadata_path.exists() or not inputs_path.exists():
            continue
        for config_dir in sorted(eval_dir.iterdir()):
            if not config_dir.is_dir():
                continue
            for run_dir in sorted(config_dir.glob("run-*")):
                triples.append((metadata_path, inputs_path, run_dir))
    return triples


def chunked_runs(run_dirs: list[Path], batch_size: int) -> list[list[Path]]:
    """Group run directories into modest parallel batches."""
    return [run_dirs[index : index + batch_size] for index in range(0, len(run_dirs), batch_size)]


def build_orchestration_manifest(
    iteration_dir: Path,
    run_records: list[dict[str, Any]],
    max_parallel: int,
    max_tool_calls: int,
    max_minutes: float,
) -> dict[str, Any]:
    """Build a machine-readable run plan for the parent orchestrator."""
    run_dirs = [Path(record["run_dir"]) for record in run_records]
    batches = []
    for batch_index, batch in enumerate(chunked_runs(run_dirs, max_parallel), start=1):
        batch_records = [record for record in run_records if Path(record["run_dir"]) in batch]
        batches.append(
            {
                "batch": batch_index,
                "max_parallel": max_parallel,
                "runs": batch_records,
            }
        )

    return {
        "iteration_dir": str(iteration_dir.resolve()),
        "max_parallel": max_parallel,
        "max_tool_calls": max_tool_calls,
        "max_minutes": max_minutes,
        "total_runs": len(run_records),
        "batches": batches,
    }


def maybe_write(path: Path, content: str, force: bool) -> bool:
    """Write content when allowed and report whether a write happened."""
    if path.exists() and not force:
        return False
    path.write_text(content, encoding="utf-8")
    return True


def build_placeholder(configuration: str, artifact_name: str) -> str:
    """Build placeholder output content."""
    return (
        f"TODO: replace this placeholder with the saved model response for {configuration}.\n"
        f"Expected artifact name: {artifact_name}\n"
    )


def main() -> None:
    """Entry point."""
    args = parse_args()
    if args.max_tool_calls <= 0:
        raise SystemExit("--max-tool-calls must be greater than 0")
    if args.max_minutes <= 0:
        raise SystemExit("--max-minutes must be greater than 0")
    if args.max_parallel <= 0:
        raise SystemExit("--max-parallel must be greater than 0")

    written = 0
    placeholders = 0
    run_records: list[dict[str, Any]] = []

    for metadata_path, inputs_path, run_dir in iter_run_dirs(args.iteration_dir):
        metadata = load_json(metadata_path)
        inputs = load_json(inputs_path)
        configuration = run_dir.parent.name
        output_dir = run_dir / "outputs"
        prompt_text = build_prompt(
            args.skill_path,
            metadata["prompt"],
            inputs.get("files", []),
            output_dir,
            args.artifact_name,
            configuration,
            args.max_tool_calls,
            args.max_minutes,
        )
        prompt_path = run_dir / "executor_prompt.txt"
        if maybe_write(prompt_path, prompt_text, args.force):
            written += 1

        run_records.append(
            {
                "eval_id": metadata.get("eval_id"),
                "title": (
                    metadata.get("slug") or metadata.get("prompt") or run_dir.parent.parent.name
                ),
                "configuration": configuration,
                "run_dir": str(run_dir.resolve()),
                "prompt_path": str(prompt_path.resolve()),
                "output_dir": str(output_dir.resolve()),
                "artifact_name": args.artifact_name,
                "max_tool_calls": args.max_tool_calls,
                "max_minutes": args.max_minutes,
            }
        )

        if args.stub_output:
            placeholder_path = output_dir / args.artifact_name
            if maybe_write(
                placeholder_path,
                build_placeholder(configuration, args.artifact_name),
                args.force,
            ):
                placeholders += 1

    orchestration_manifest = build_orchestration_manifest(
        args.iteration_dir,
        run_records,
        args.max_parallel,
        args.max_tool_calls,
        args.max_minutes,
    )
    manifest_path = args.iteration_dir / "orchestration_manifest.json"
    manifest_path.write_text(
        json.dumps(orchestration_manifest, indent=2) + "\n",
        encoding="utf-8",
    )

    print(f"prompts_written={written}")
    if args.stub_output:
        print(f"placeholders_written={placeholders}")
    print(f"orchestration_manifest={manifest_path}")


if __name__ == "__main__":
    main()
