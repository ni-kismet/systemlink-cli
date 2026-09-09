"""Load and validate the slcli skill eval manifest."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

SUPPORTED_RULE_MODES = {"all_of", "any_of", "none_of"}
SUPPORTED_RULE_SCOPES = {"response", "command"}
SUPPORTED_RULE_VALIDATORS = {"previous_calendar_month"}


def resolve_fixture_path(skill_dir: Path, relative_path: str) -> Path:
    """Resolve a fixture path contained within the skill directory."""
    path = Path(relative_path)
    skill_root = skill_dir.resolve()
    resolved = (skill_root / path).resolve()
    if path.is_absolute() or ".." in path.parts or not resolved.is_relative_to(skill_root):
        raise ValueError(f"fixture path must stay within the skill directory: {relative_path}")
    return resolved


def validate_manifest(payload: dict[str, Any], skill_dir: Path) -> None:
    """Validate invariants needed by the eval harness."""
    if payload.get("manifest_version") != 1:
        raise ValueError("eval manifest_version must be 1")
    if not payload.get("skill_name"):
        raise ValueError("eval manifest requires skill_name")

    entries = payload.get("evals")
    if not isinstance(entries, list) or not entries:
        raise ValueError("eval manifest requires a non-empty evals list")
    ids = [entry.get("id") for entry in entries]
    if any(not isinstance(eval_id, int) for eval_id in ids) or len(ids) != len(set(ids)):
        raise ValueError("eval IDs must be unique integers")

    by_id = set(ids)
    suites = payload.get("recommended_suites", {})
    if set(suites) != {"gating", "regression"}:
        raise ValueError("recommended_suites must define gating and regression")
    for suite, suite_ids in suites.items():
        unknown = set(suite_ids) - by_id
        if unknown:
            raise ValueError(f"suite {suite} references unknown eval IDs: {sorted(unknown)}")

    for entry in entries:
        eval_id = entry["id"]
        required_entry_fields = {
            "prompt",
            "expected_output",
            "files",
            "expectations",
            "grading_rules",
        }
        missing_entry_fields = required_entry_fields - entry.keys()
        if missing_entry_fields:
            raise ValueError(
                f"eval {eval_id} is missing required fields: {sorted(missing_entry_fields)}"
            )
        if not entry["prompt"] or not entry["expected_output"]:
            raise ValueError(f"eval {eval_id} requires prompt and expected_output")
        if not isinstance(entry["files"], list) or not isinstance(entry["expectations"], list):
            raise ValueError(f"eval {eval_id} files and expectations must be lists")
        for relative_path in entry["files"]:
            if not isinstance(relative_path, str):
                raise ValueError(f"eval {eval_id} fixture paths must be strings")
            fixture_path = resolve_fixture_path(skill_dir, relative_path)
            if not fixture_path.is_file():
                raise ValueError(f"eval {eval_id} fixture does not exist: {relative_path}")
        rules = entry["grading_rules"]
        if not isinstance(rules, list):
            raise ValueError(f"eval {eval_id} grading_rules must be a list")
        if eval_id in suites["gating"] and not rules:
            raise ValueError(f"gating eval {eval_id} requires grading rules")
        for rule in rules:
            if not isinstance(rule.get("critical"), bool):
                raise ValueError(f"eval {eval_id} grading rules require an explicit critical flag")
            missing_rule_fields = {"text", "mode", "patterns"} - rule.keys()
            if missing_rule_fields:
                raise ValueError(
                    f"eval {eval_id} grading rule is missing fields: {sorted(missing_rule_fields)}"
                )
            if not isinstance(rule["text"], str) or not rule["text"]:
                raise ValueError(f"eval {eval_id} grading rule text must be non-empty")
            if rule.get("mode") not in SUPPORTED_RULE_MODES:
                raise ValueError(f"eval {eval_id} has unsupported rule mode: {rule.get('mode')}")
            if rule.get("scope", "response") not in SUPPORTED_RULE_SCOPES:
                raise ValueError(f"eval {eval_id} has unsupported rule scope: {rule.get('scope')}")
            validator = rule.get("validator")
            if validator is not None and validator not in SUPPORTED_RULE_VALIDATORS:
                raise ValueError(f"eval {eval_id} has unsupported rule validator: {validator}")
            patterns = rule.get("patterns")
            if (
                not isinstance(patterns, list)
                or not patterns
                or any(not isinstance(pattern, str) or not pattern for pattern in patterns)
            ):
                raise ValueError(
                    f"eval {eval_id} grading rules require a non-empty list of patterns"
                )
            for pattern in patterns:
                try:
                    re.compile(pattern)
                except re.error as error:
                    raise ValueError(
                        f"eval {eval_id} grading rule has invalid pattern: {pattern}"
                    ) from error
            if rule["critical"] and (
                not rule.get("positive_control") or not rule.get("negative_control")
            ):
                raise ValueError(
                    f"eval {eval_id} critical rules require positive and negative controls"
                )


def load_manifest(path: Path) -> dict[str, Any]:
    """Load and validate an eval manifest."""
    payload = json.loads(path.read_text(encoding="utf-8"))
    validate_manifest(payload, path.parent.parent)
    return payload
