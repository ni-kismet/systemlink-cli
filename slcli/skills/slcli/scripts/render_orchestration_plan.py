"""Render a parent-chat execution plan from an slcli orchestration manifest."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Render a batch-by-batch orchestration plan for prepared eval runs."
    )
    parser.add_argument(
        "iteration_dir",
        type=Path,
        help="Path to an iteration-N directory containing orchestration_manifest.json.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional file path to write the rendered plan. Defaults to stdout.",
    )
    parser.add_argument(
        "--format",
        choices=["markdown", "text"],
        default="markdown",
        help="Output format.",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    """Load a JSON file."""
    return json.loads(path.read_text(encoding="utf-8"))


def require_manifest(iteration_dir: Path) -> dict[str, Any]:
    """Load orchestration_manifest.json from an iteration directory."""
    manifest_path = iteration_dir / "orchestration_manifest.json"
    if not manifest_path.exists():
        raise FileNotFoundError(
            f"{manifest_path} does not exist. Run prepare_eval_prompts.py first."
        )
    return load_json(manifest_path)


def load_iteration_summary(iteration_dir: Path) -> dict[str, Any]:
    """Load iteration_manifest.json when present."""
    summary_path = iteration_dir / "iteration_manifest.json"
    if not summary_path.exists():
        return {}
    return load_json(summary_path)


def format_run_label(run: dict[str, Any]) -> str:
    """Build a concise run label."""
    configuration = run.get("configuration", "unknown")
    eval_id = run.get("eval_id", "?")
    title = str(run.get("title", "")).strip()
    return f"eval {eval_id} {configuration}: {title}"


def output_artifact_path(run: dict[str, Any]) -> str:
    """Return the full output artifact path for a run."""
    return f"{run.get('output_dir', '')}/{run.get('artifact_name', 'response.txt')}"


def render_markdown(iteration_dir: Path, manifest: dict[str, Any], summary: dict[str, Any]) -> str:
    """Render a markdown orchestration plan."""
    lines = [
        "# Eval Orchestration Plan",
        "",
        f"Iteration: `{iteration_dir.resolve()}`",
        f"Suite: `{summary.get('suite', 'unknown')}`",
        f"Runs: `{manifest.get('total_runs', 0)}`",
        f"Max parallel: `{manifest.get('max_parallel', '?')}`",
        f"Per-run budget: `{manifest.get('max_tool_calls', '?')}` tool calls or `{manifest.get('max_minutes', '?')}` minutes",
        "",
        "## Parent Chat Checklist",
        "",
        "1. Read `iteration_manifest.json`.",
        "2. Read `orchestration_manifest.json` and use its batches as the source of truth.",
        "3. Execute one batch at a time.",
        "4. Within a batch, run the listed evals in parallel subagents up to `max_parallel`.",
        "5. If a run exceeds its budget, persist the best grounded `response.txt`, add `notes.txt`, and continue.",
        "6. After all batches finish, run `benchmark_iteration.py` and `render_eval_review.py`.",
        "",
        "## Batches",
        "",
    ]

    for batch in manifest.get("batches", []):
        lines.extend(
            [
                f"### Batch {batch.get('batch', '?')}",
                "",
                f"Run up to `{batch.get('max_parallel', manifest.get('max_parallel', '?'))}` subagents in parallel for this batch.",
                "",
            ]
        )
        for run in batch.get("runs", []):
            lines.extend(
                [
                    f"- [ ] {format_run_label(run)}",
                    f"  prompt: `{run.get('prompt_path', '')}`",
                    f"  output: `{output_artifact_path(run)}`",
                    f"  budget: `{run.get('max_tool_calls', manifest.get('max_tool_calls', '?'))}` tool calls or `{run.get('max_minutes', manifest.get('max_minutes', '?'))}` minutes",
                ]
            )
        lines.append("")

    lines.extend(
        [
            "## Closing Commands",
            "",
            f"```bash\npython slcli/skills/slcli/scripts/benchmark_iteration.py --force {iteration_dir}\npython slcli/skills/slcli/scripts/render_eval_review.py {iteration_dir}\n```",
            "",
        ]
    )
    return "\n".join(lines)


def render_text(iteration_dir: Path, manifest: dict[str, Any], summary: dict[str, Any]) -> str:
    """Render a plain-text orchestration plan."""
    lines = [
        "Eval Orchestration Plan",
        f"iteration={iteration_dir.resolve()}",
        f"suite={summary.get('suite', 'unknown')}",
        f"runs={manifest.get('total_runs', 0)}",
        f"max_parallel={manifest.get('max_parallel', '?')}",
        f"budget={manifest.get('max_tool_calls', '?')} tool calls | {manifest.get('max_minutes', '?')} minutes",
        "",
        "Parent chat steps:",
        "1. Read iteration_manifest.json",
        "2. Read orchestration_manifest.json",
        "3. Execute one batch at a time",
        "4. Run listed subagents in parallel within each batch",
        "5. Persist partial outputs if a run hits its budget",
        "6. Run benchmark_iteration.py and render_eval_review.py",
        "",
    ]

    for batch in manifest.get("batches", []):
        lines.append(
            "Batch "
            f"{batch.get('batch', '?')} "
            "(max_parallel="
            f"{batch.get('max_parallel', manifest.get('max_parallel', '?'))})"
        )
        for run in batch.get("runs", []):
            lines.append(f"- {format_run_label(run)}")
            lines.append(f"  prompt={run.get('prompt_path', '')}")
            lines.append(f"  output={output_artifact_path(run)}")
        lines.append("")

    return "\n".join(lines)


def main() -> None:
    """Entry point."""
    args = parse_args()
    manifest = require_manifest(args.iteration_dir)
    summary = load_iteration_summary(args.iteration_dir)

    if args.format == "markdown":
        rendered = render_markdown(args.iteration_dir, manifest, summary)
    else:
        rendered = render_text(args.iteration_dir, manifest, summary)

    if args.output:
        args.output.write_text(rendered + "\n", encoding="utf-8")
        print(args.output)
        return

    sys.stdout.write(rendered)
    if not rendered.endswith("\n"):
        sys.stdout.write("\n")


if __name__ == "__main__":
    main()
