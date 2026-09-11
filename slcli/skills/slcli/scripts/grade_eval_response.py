"""Grade a skill response against rule-based expectations from evals.json."""

from __future__ import annotations

import argparse
import json
import re
import shlex
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from slcli.skills.slcli.scripts.eval_manifest import load_manifest

UNQUOTED_WINDOWS_PATH = re.compile(r"(?<![\w\"'])([A-Za-z]:\\[^\s;&|]+)")
INLINE_COMMAND = re.compile(r"`(?P<command>slcli(?:\s+[^`]*)?)`", re.IGNORECASE)
WARNING_COMMAND_PREFIX = re.compile(
    r"\b(?:do not|don't|never|avoid)(?:\s+(?:use|run|execute))?" r"(?:\s+the following)?\s*:?\s*$",
    re.IGNORECASE,
)


def previous_calendar_month_bounds(reference_date: date) -> tuple[str, str]:
    """Return ISO date bounds for the calendar month before the reference date."""
    current_month = reference_date.replace(day=1)
    previous_month = (current_month - timedelta(days=1)).replace(day=1)
    return previous_month.isoformat(), current_month.isoformat()


def validate_candidate(candidate: str, rule: dict[str, Any], reference_date: date) -> bool:
    """Apply an optional semantic validator to one response candidate."""
    validator = rule.get("validator")
    if validator is None:
        return True
    if validator == "previous_calendar_month":
        lower_bound, upper_bound = previous_calendar_month_bounds(reference_date)
        lower_match = re.search(r"startedAt\s*>=\s*@(\d+)", candidate, re.IGNORECASE)
        upper_match = re.search(r"startedAt\s*<\s*@(\d+)", candidate, re.IGNORECASE)
        substitutions = re.findall(r"--substitution(?:=|\s+)(\S+)", candidate)
        if lower_match is None or upper_match is None:
            return False
        lower_index = int(lower_match.group(1))
        upper_index = int(upper_match.group(1))
        if lower_index >= len(substitutions) or upper_index >= len(substitutions):
            return False
        return (
            substitutions[lower_index].removesuffix("T00:00:00Z") == lower_bound
            and substitutions[upper_index].removesuffix("T00:00:00Z") == upper_bound
        )
    raise ValueError(f"Unsupported grading rule validator: {validator}")


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
    parser.add_argument(
        "--transcript",
        type=Path,
        help="Optional transcript artifact used for execution metrics.",
    )
    return parser.parse_args()


def load_eval(manifest_path: Path, eval_id: int) -> dict[str, Any]:
    """Load one eval entry from the manifest."""
    payload = load_manifest(manifest_path)
    for entry in payload.get("evals", []):
        if entry.get("id") == eval_id:
            return entry
    raise ValueError(f"Eval id {eval_id} not found in {manifest_path}")


def gather_response_text(response_path: Path) -> tuple[str, list[str]]:
    """Read a final response file or the designated response in an output directory."""
    if response_path.is_file():
        return read_text_artifact(response_path), [str(response_path)]

    final_response = response_path / "response.txt"
    if not final_response.is_file():
        raise ValueError(f"Final response artifact not found: {final_response}")
    return read_text_artifact(final_response), [str(final_response)]


def extract_slcli_commands(text: str) -> list[str]:
    """Extract complete slcli command invocations from a response."""
    commands: list[str] = []
    pending = ""
    warning_context = False
    ignored_warning_fence = False
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if ignored_warning_fence:
            if line.startswith("```"):
                ignored_warning_fence = False
            continue
        if warning_context and line.startswith("```"):
            warning_context = False
            ignored_warning_fence = True
            continue
        if pending:
            continuation = line.endswith("\\") or (line.endswith("`") and not line.endswith("```"))
            pending += " " + line.removesuffix("\\").removesuffix("`").strip()
            if not continuation:
                commands.extend(extract_slcli_commands(pending))
                pending = ""
            continue
        powershell_continuation = (
            line.endswith("`")
            and not line.startswith("```")
            and re.match(r"^(?:[-*+]\s+|\d+\.\s+|\$\s+)?slcli\b", line, re.IGNORECASE) is not None
        )
        if line.endswith("\\") or powershell_continuation:
            pending = line.removesuffix("\\").removesuffix("`").strip()
            continue
        if WARNING_COMMAND_PREFIX.search(line):
            warning_context = True
        inline_matches = list(INLINE_COMMAND.finditer(line))
        if inline_matches:
            for match in inline_matches:
                prefix = line[: match.start()].strip()
                if warning_context or WARNING_COMMAND_PREFIX.search(prefix):
                    continue
                commands.extend(extract_slcli_commands(match.group("command")))
            warning_context = False
            continue
        if warning_context and line.startswith(("slcli ", "slcli\t", "- `slcli")):
            warning_context = False
            continue
        command_line = re.sub(r"^(?:[-*+]\s+|\d+\.\s+|\$\s+)", "", line).strip("`")
        command_line = UNQUOTED_WINDOWS_PATH.sub(
            lambda match: match.group(1).replace("\\", "/"), command_line
        )
        lexer = shlex.shlex(command_line, posix=True, punctuation_chars=";&|")
        lexer.whitespace_split = True
        lexer.commenters = ""
        try:
            tokens = list(lexer)
        except ValueError:
            continue
        segment: list[str] = []
        for token in [*tokens, ";"]:
            if token in {";", "&&", "||", "|", "&"}:
                if segment and segment[0] == "slcli":
                    command_tokens = segment.copy()
                    if len(command_tokens) > 2 and command_tokens[1] in {"--profile", "-p"}:
                        del command_tokens[1:3]
                    elif len(command_tokens) > 1 and command_tokens[1].startswith("--profile="):
                        del command_tokens[1]
                    commands.append(" ".join(command_tokens))
                segment = []
            else:
                segment.append(token)
    if pending:
        commands.extend(extract_slcli_commands(pending))
    return commands


def evaluate_rule(
    text: str, rule: dict[str, Any], reference_date: date | None = None
) -> tuple[bool, str]:
    """Evaluate one grading rule."""
    mode = rule["mode"]
    patterns = [re.compile(pattern, re.IGNORECASE | re.MULTILINE) for pattern in rule["patterns"]]
    scope = rule.get("scope", "response")
    candidates = extract_slcli_commands(text) if scope == "command" else [text]
    candidate_matches = [
        [pattern.search(candidate) for pattern in patterns] for candidate in candidates
    ]
    reference_date = reference_date or date.today()
    valid_candidates = [
        validate_candidate(candidate, rule, reference_date) for candidate in candidates
    ]

    if mode == "all_of":
        passed = any(
            all(match is not None for match in matches) and valid
            for matches, valid in zip(candidate_matches, valid_candidates)
        )
    elif mode == "any_of":
        passed = any(
            any(match is not None for match in matches) and valid
            for matches, valid in zip(candidate_matches, valid_candidates)
        )
    elif mode == "none_of":
        passed = all(
            all(match is None for match in matches) and valid
            for matches, valid in zip(candidate_matches, valid_candidates)
        )
    else:
        raise ValueError(f"Unsupported grading rule mode: {mode}")

    if passed:
        if mode == "none_of":
            evidence = "None of the forbidden patterns were present in the response artifacts."
        else:
            found = [
                match.group(0)
                for matches in candidate_matches
                for match in matches
                if match is not None
            ]
            evidence = f"Matched: {', '.join(found)}"
    else:
        if mode == "none_of":
            found = [
                match.group(0)
                for matches in candidate_matches
                for match in matches
                if match is not None
            ]
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
    transcript_path: Path | None = None,
    reference_date: date | None = None,
) -> dict[str, Any]:
    """Grade one response artifact path against one eval entry."""
    eval_entry = load_eval(manifest_path, eval_id)
    response_text, sources = gather_response_text(response_path)
    timing = load_timing(timing_path)
    transcript_text = read_text_artifact(transcript_path) if transcript_path else None
    reference_date = reference_date or date.today()

    results: list[dict[str, Any]] = []
    for rule in eval_entry.get("grading_rules", []):
        passed, evidence = evaluate_rule(response_text, rule, reference_date=reference_date)
        results.append(
            {
                "text": rule["text"],
                "passed": passed,
                "evidence": evidence,
                "critical": rule["critical"],
                "grader_type": "regex",
                "scope": rule.get("scope", "response"),
            }
        )

    return build_output(
        eval_entry,
        results,
        sources,
        response_text,
        timing,
        transcript_text,
        reference_date,
    )


def build_output(
    eval_entry: dict[str, Any],
    results: list[dict[str, Any]],
    sources: list[str],
    response_text: str,
    timing: dict[str, Any],
    transcript_text: str | None,
    reference_date: date,
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
        "reference_date": reference_date.isoformat(),
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
            "total_tokens": timing.get("total_tokens") if timing else None,
            "output_chars": len(response_text),
            "transcript_chars": len(transcript_text) if transcript_text is not None else None,
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
    output = grade_response(args.evals, args.eval_id, args.response, args.timing, args.transcript)
    args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
