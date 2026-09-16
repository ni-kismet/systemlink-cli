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
from slcli.skills.slcli.scripts.execution_records import load_execution_records
from slcli.skills.slcli.scripts.fixture_snapshot import (
    _extract_items,
    _lookup,
    _matches_expected,
    canonical_hash,
)

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


def _select_execution_records(
    records: list[dict[str, Any]], config: dict[str, Any]
) -> list[dict[str, Any]]:
    """Select records whose command matches an optional configured pattern."""
    command_pattern = config.get("command_pattern")
    if command_pattern is None:
        return records
    pattern = re.compile(command_pattern, re.IGNORECASE)
    return [record for record in records if pattern.search(record["command"])]


def _successful_payloads(
    records: list[dict[str, Any]], config: dict[str, Any]
) -> tuple[list[Any], str | None]:
    """Return parsed successful command payloads or an inconclusive reason."""
    selected = _select_execution_records(records, config)
    if not selected:
        return [], "no execution record matched the configured command"
    if any(record["exit_code"] is None for record in selected):
        return [], "execution records do not contain command exit codes"
    failed = [record for record in selected if record["exit_code"] != 0]
    if failed:
        return [], "configured command returned a nonzero exit code"
    if any(record["stdout_json"] is None for record in selected):
        return [], "configured command did not provide parsed JSON output"
    return [record["stdout_json"] for record in selected], None


def _all_resource_items(payloads: list[Any]) -> list[dict[str, Any]]:
    """Flatten common command response payloads into resource dictionaries."""
    items: list[dict[str, Any]] = []
    for payload in payloads:
        items.extend(_extract_items(payload))
    return items


def _read_json_artifact(directory: Path, name: str) -> dict[str, Any] | None:
    """Read a JSON artifact within the response directory."""
    path = (directory / name).resolve()
    if not path.is_relative_to(directory.resolve()) or not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return payload if isinstance(payload, dict) else None


def _load_fixture_readiness(
    eval_entry: dict[str, Any], artifact_directory: Path
) -> tuple[str, dict[str, Any] | None]:
    """Load live fixture readiness from the standard run artifact when required."""
    execution_mode = eval_entry.get("execution_mode", "offline")
    if execution_mode == "offline" or eval_entry.get("fixture_scope") == "local":
        return "not_applicable", None
    snapshot = _read_json_artifact(artifact_directory, "fixture_snapshot.json")
    if snapshot is None:
        return "inconclusive", None
    status = snapshot.get("status")
    if status not in {"ready", "fixture_drift", "unsupported", "inconclusive"}:
        return "inconclusive", snapshot
    return status, snapshot


def evaluate_structured_rule(
    rule: dict[str, Any], records: list[dict[str, Any]], artifact_directory: Path
) -> tuple[bool, str, str]:
    """Evaluate one non-regex rule against records and state artifacts."""
    grader_type = rule["grader_type"]
    config = rule["grader_config"]
    if grader_type in {"resource_query", "resource_set", "relationship", "negative_query"}:
        payloads, unavailable_reason = _successful_payloads(records, config)
        if unavailable_reason:
            return False, unavailable_reason, "inconclusive"
        items = _all_resource_items(payloads)
        resource_match = config.get("match", {})
        matched = [item for item in items if _matches_expected(item, resource_match)]
        if grader_type == "resource_query":
            minimum = config.get("minimum_count", 1)
            maximum = config.get("maximum_count")
            passed = len(matched) >= minimum and (maximum is None or len(matched) <= maximum)
            return (
                passed,
                f"matched {len(matched)} {config.get('resource_type', 'resource')} resources",
                "complete",
            )
        if grader_type == "resource_set":
            expected_resources = config.get("expected", config.get("resources", []))
            if not isinstance(expected_resources, list):
                return False, "resource_set expected resources must be a list", "inconclusive"
            missing = [
                expected
                for expected in expected_resources
                if not any(
                    _matches_expected(item, expected.get("match", expected)) for item in items
                )
            ]
            return not missing, f"missing resources: {missing!r}", "complete"
        if grader_type == "negative_query":
            return not items, f"returned {len(items)} resources", "complete"
        relationship_path = config.get("path") or config.get("relationship_path")
        if not isinstance(relationship_path, str) or not relationship_path:
            return False, "relationship grader requires path", "inconclusive"
        expected_value = config.get("expected")
        related = [_lookup(item, relationship_path) for item in matched]
        passed = bool(matched) and all(value == expected_value for value in related)
        return passed, f"relationship values: {related!r}", "complete"

    if grader_type == "snapshot":
        before = _read_json_artifact(
            artifact_directory, config.get("before", "fixture_snapshot_before.json")
        )
        after = _read_json_artifact(
            artifact_directory, config.get("after", "fixture_snapshot_after.json")
        )
        if before is None or after is None:
            return False, "snapshot artifacts are missing or invalid", "inconclusive"
        expected_status = config.get("expected_status")
        if expected_status and after.get("status") != expected_status:
            return False, f"snapshot status was {after.get('status')!r}", "complete"
        if config.get("comparison", "unchanged") == "unchanged":
            before_hash = before.get("snapshot_hash") or canonical_hash(before)
            after_hash = after.get("snapshot_hash") or canonical_hash(after)
            return before_hash == after_hash, "before and after snapshot hashes match", "complete"
        return False, "unsupported snapshot comparison", "inconclusive"

    if grader_type == "mutation_safety":
        if any(record["exit_code"] is None for record in records):
            return False, "execution records do not contain command exit codes", "inconclusive"
        forbidden_patterns = config.get(
            "forbidden_patterns",
            [r"\b(?:create|update|delete|upload|publish|install|remove|set|write|schedule)\b"],
        )
        forbidden = [
            record["command"]
            for record in records
            if any(
                re.search(pattern, record["command"], re.IGNORECASE)
                for pattern in forbidden_patterns
            )
        ]
        return not forbidden, f"forbidden commands: {forbidden!r}", "complete"

    if grader_type == "cleanup":
        report_name = config.get("report", "cleanup_report.json")
        report = _read_json_artifact(artifact_directory, report_name)
        if report is None:
            return False, "cleanup report is missing or invalid", "inconclusive"
        expected_status = config.get("expected_status", "clean")
        return (
            report.get("status") == expected_status,
            f"cleanup status: {report.get('status')!r}",
            "complete",
        )

    return False, f"unsupported structured grader: {grader_type}", "inconclusive"


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
    eval_entry_override: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Grade one response artifact path against one eval entry."""
    eval_entry = {**load_eval(manifest_path, eval_id), **(eval_entry_override or {})}
    response_text, sources = gather_response_text(response_path)
    artifact_directory = response_path if response_path.is_dir() else response_path.parent
    fixture_readiness, fixture_snapshot = _load_fixture_readiness(eval_entry, artifact_directory)
    timing = load_timing(timing_path)
    transcript_text = read_text_artifact(transcript_path) if transcript_path else None
    reference_date = reference_date or date.today()
    fallback_commands = extract_slcli_commands(response_text)
    record_error: str | None
    try:
        execution_records, execution_sources = load_execution_records(
            response_path, fallback_commands
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as error:
        execution_records = []
        execution_sources = []
        record_error = str(error)
    else:
        record_error = None

    results: list[dict[str, Any]] = []
    for rule in eval_entry.get("grading_rules", []):
        required_in_modes = rule.get("required_in_modes")
        if (
            required_in_modes
            and eval_entry.get("execution_mode", "offline") not in required_in_modes
        ):
            results.append(
                {
                    "text": rule["text"],
                    "passed": True,
                    "evidence": "not applicable to this execution mode",
                    "critical": rule["critical"],
                    "grader_type": rule.get("grader_type", "regex"),
                    "scope": rule.get("scope", "response"),
                    "status": "not_applicable",
                }
            )
            continue
        grader_type = rule.get("grader_type", "regex")
        if grader_type == "regex":
            passed, evidence = evaluate_rule(response_text, rule, reference_date=reference_date)
            result_status = "complete"
        elif record_error:
            passed, evidence, result_status = False, record_error, "inconclusive"
        else:
            passed, evidence, result_status = evaluate_structured_rule(
                rule, execution_records, artifact_directory
            )
        results.append(
            {
                "text": rule["text"],
                "passed": passed,
                "evidence": evidence,
                "critical": rule["critical"],
                "grader_type": grader_type,
                "scope": rule.get("scope", "response"),
                "status": result_status,
            }
        )
    sources.extend(execution_sources)

    return build_output(
        eval_entry,
        results,
        sources,
        response_text,
        timing,
        transcript_text,
        reference_date,
        execution_records,
        fixture_readiness,
        fixture_snapshot,
    )


def build_output(
    eval_entry: dict[str, Any],
    results: list[dict[str, Any]],
    sources: list[str],
    response_text: str,
    timing: dict[str, Any],
    transcript_text: str | None,
    reference_date: date,
    execution_records: list[dict[str, Any]] | None = None,
    fixture_readiness: str = "not_applicable",
    fixture_snapshot: dict[str, Any] | None = None,
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
            "total_tool_calls": len(execution_records or []),
            "total_steps": 0,
            "errors_encountered": sum(
                1 for record in execution_records or [] if record.get("exit_code") not in (None, 0)
            ),
            "total_tokens": timing.get("total_tokens") if timing else None,
            "output_chars": len(response_text),
            "transcript_chars": len(transcript_text) if transcript_text is not None else None,
            "api_latency_seconds": sum(
                record["duration_seconds"]
                for record in execution_records or []
                if isinstance(record.get("duration_seconds"), (int, float))
            ),
            "json_parse_successes": sum(
                1 for record in execution_records or [] if record.get("stdout_json") is not None
            ),
        },
        "execution_records": execution_records or [],
        "timing": timing_block,
        "claims": [],
        "user_notes_summary": {"uncertainties": [], "needs_review": [], "workarounds": []},
        "eval_feedback": {
            "eval_id": eval_entry["id"],
            "tags": eval_entry.get("tags", []),
            "sources": sources,
        },
        "evaluation": {
            "execution_mode": eval_entry.get("execution_mode", "offline"),
            "fixture": eval_entry.get("fixture"),
            "fixture_scope": eval_entry.get("fixture_scope", "local"),
            "mutation_policy": eval_entry.get("mutation_policy", "forbidden"),
            "cleanup": eval_entry.get("cleanup"),
            "fixture_readiness": fixture_readiness,
            "fixture_snapshot_hash": (
                fixture_snapshot.get("snapshot_hash") if fixture_snapshot else None
            ),
        },
    }


def main() -> None:
    """Entry point."""
    args = parse_args()
    output = grade_response(args.evals, args.eval_id, args.response, args.timing, args.transcript)
    args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
