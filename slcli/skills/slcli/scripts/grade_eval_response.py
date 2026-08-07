"""Grade a skill response against rule-based expectations from evals.json."""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def read_text_artifact(path: Path) -> str:
    """Read a text artifact without failing on undecodable bytes."""
    return path.read_text(encoding="utf-8", errors="replace")


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Grade a saved response against slcli skill eval rules."
    )
    parser.add_argument(
        "--evals",
        type=Path,
        default=Path(__file__).resolve().parent.parent / "evals" / "evals.json",
        help="Path to the evals.json manifest.",
    )
    parser.add_argument("--eval-id", type=int, required=True, help="Eval identifier to grade.")
    parser.add_argument(
        "--response",
        type=Path,
        required=True,
        help="Path to a response file or a directory containing response artifacts.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="Path to write grading.json.",
    )
    parser.add_argument(
        "--timing",
        type=Path,
        help="Optional timing.json to merge into the grading output.",
    )
    return parser.parse_args()


def load_eval(manifest_path: Path, eval_id: int) -> dict[str, Any]:
    """Load one eval entry from the manifest."""
    payload = json.loads(read_text_artifact(manifest_path))
    for entry in payload.get("evals", []):
        if entry.get("id") == eval_id:
            return entry
    raise ValueError(f"Eval id {eval_id} not found in {manifest_path}")


def gather_response_text(response_path: Path) -> tuple[str, list[str]]:
    """Read response text from a file or a directory of artifacts."""
    if response_path.is_file():
        return read_text_artifact(response_path), [str(response_path)]

    text_parts: list[str] = []
    sources: list[str] = []
    for file_path in sorted(response_path.rglob("*")):
        if not file_path.is_file():
            continue
        if file_path.suffix.lower() not in {".txt", ".md", ".json", ".log", ".sh"}:
            continue
        text_parts.append(read_text_artifact(file_path))
        sources.append(str(file_path))

    if not text_parts:
        raise ValueError(f"No readable text artifacts found under {response_path}")

    return "\n\n".join(text_parts), sources


def evaluate_rule(text: str, rule: dict[str, Any]) -> tuple[bool, str]:
    """Evaluate one grading rule."""
    mode = rule["mode"]
    patterns = [re.compile(pattern, re.IGNORECASE | re.MULTILINE) for pattern in rule["patterns"]]
    matches = [pattern.search(text) for pattern in patterns]

    if mode == "all_of":
        passed = all(match is not None for match in matches)
    elif mode == "any_of":
        passed = any(match is not None for match in matches)
    elif mode == "none_of":
        passed = all(match is None for match in matches)
    else:
        raise ValueError(f"Unsupported grading rule mode: {mode}")

    if passed:
        if mode == "none_of":
            evidence = "None of the forbidden patterns were present in the response artifacts."
        else:
            found = [match.group(0) for match in matches if match is not None]
            evidence = f"Matched: {', '.join(found)}"
    else:
        if mode == "none_of":
            found = [match.group(0) for match in matches if match is not None]
            evidence = f"Found forbidden content: {', '.join(found)}"
        else:
            evidence = "Missing required patterns: " + ", ".join(rule["patterns"])

    return passed, evidence


def load_timing(timing_path: Path | None) -> dict[str, Any]:
    """Load optional timing metadata."""
    if timing_path is None or not timing_path.exists():
        return {}
    return json.loads(read_text_artifact(timing_path))


def grade_response(
    manifest_path: Path,
    eval_id: int,
    response_path: Path,
    timing_path: Path | None = None,
) -> dict[str, Any]:
    """Grade one response artifact path against one eval entry."""
    eval_entry = load_eval(manifest_path, eval_id)
    response_text, sources = gather_response_text(response_path)
    timing = load_timing(timing_path)

    results: list[dict[str, Any]] = []
    for rule in eval_entry.get("grading_rules", []):
        passed, evidence = evaluate_rule(response_text, rule)
        results.append({"text": rule["text"], "passed": passed, "evidence": evidence})

    return build_output(eval_entry, results, sources, response_text, timing)


def build_output(
    eval_entry: dict[str, Any],
    results: list[dict[str, Any]],
    sources: list[str],
    response_text: str,
    timing: dict[str, Any],
) -> dict[str, Any]:
    """Build grading.json payload."""
    passed_count = sum(1 for result in results if result["passed"])
    total = len(results)
    failed_count = total - passed_count
    timing_block = {}
    if timing:
        timing_block = {
            "executor_duration_seconds": timing.get("total_duration_seconds"),
            "grader_duration_seconds": 0.0,
            "total_duration_seconds": timing.get("total_duration_seconds"),
        }

    return {
        "expectations": results,
        "summary": {
            "passed": passed_count,
            "failed": failed_count,
            "total": total,
            "pass_rate": round((passed_count / total) if total else 0.0, 2),
        },
        "execution_metrics": {
            "tool_calls": {},
            "total_tool_calls": 0,
            "total_steps": 0,
            "errors_encountered": 0,
            "output_chars": len(response_text),
            "transcript_chars": len(response_text),
        },
        "timing": timing_block,
        "claims": [],
        "user_notes_summary": {"uncertainties": [], "needs_review": [], "workarounds": []},
        "eval_feedback": {
            "eval_id": eval_entry["id"],
            "tags": eval_entry.get("tags", []),
            "sources": sources,
        },
    }


def main() -> None:
    """Entry point."""
    args = parse_args()
    output = grade_response(args.evals, args.eval_id, args.response, args.timing)
    args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
