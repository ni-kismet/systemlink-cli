"""Load and validate the slcli skill eval manifest."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

SUPPORTED_RULE_MODES = {"all_of", "any_of", "none_of"}
SUPPORTED_RULE_SCOPES = {"response", "command"}
SUPPORTED_RULE_VALIDATORS = {"previous_calendar_month"}
SUPPORTED_EXECUTION_MODES = {"offline", "online", "live_readonly", "hybrid"}
SUPPORTED_SUITES = {"gating", "regression", "live_readonly", "online"}
SUPPORTED_MUTATION_POLICIES = {"forbidden", "isolated_only", "allow_with_cleanup"}
SUPPORTED_FIXTURE_SCOPES = {"local", "shared_readonly", "isolated"}
SUPPORTED_GRADER_TYPES = {
    "regex",
    "resource_query",
    "resource_set",
    "relationship",
    "negative_query",
    "snapshot",
    "mutation_safety",
    "cleanup",
}


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
    if any(not isinstance(eval_id, int) or isinstance(eval_id, bool) for eval_id in ids) or len(
        ids
    ) != len(set(ids)):
        raise ValueError("eval IDs must be unique integers")

    by_id = set(ids)
    suites = payload.get("recommended_suites", {})
    if not isinstance(suites, dict) or not {"gating", "regression"}.issubset(suites):
        raise ValueError("recommended_suites must define gating and regression")
    unknown_suites = set(suites) - SUPPORTED_SUITES
    if unknown_suites:
        raise ValueError(f"recommended_suites has unsupported suites: {sorted(unknown_suites)}")
    for suite, suite_ids in suites.items():
        if (
            not isinstance(suite_ids, list)
            or any(
                not isinstance(eval_id, int) or isinstance(eval_id, bool) for eval_id in suite_ids
            )
            or len(suite_ids) != len(set(suite_ids))
        ):
            raise ValueError(f"suite {suite} IDs must be a unique list of integers")
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
        if not isinstance(entry["prompt"], str) or not isinstance(entry["expected_output"], str):
            raise ValueError(f"eval {eval_id} prompt and expected_output must be strings")
        if not entry["prompt"] or not entry["expected_output"]:
            raise ValueError(f"eval {eval_id} requires prompt and expected_output")
        if not isinstance(entry["files"], list) or not isinstance(entry["expectations"], list):
            raise ValueError(f"eval {eval_id} files and expectations must be lists")
        execution_mode = entry.get("execution_mode", "offline")
        if execution_mode not in SUPPORTED_EXECUTION_MODES:
            raise ValueError(f"eval {eval_id} has unsupported execution mode: {execution_mode}")
        fixture = entry.get("fixture")
        if execution_mode != "offline":
            if not isinstance(fixture, dict):
                raise ValueError(f"eval {eval_id} requires fixture metadata for live execution")
            missing_fixture_fields = {"example", "profile", "workspace"} - fixture.keys()
            if missing_fixture_fields:
                raise ValueError(
                    f"eval {eval_id} fixture is missing fields: {sorted(missing_fixture_fields)}"
                )
            if any(
                not isinstance(fixture[field], str) or not fixture[field]
                for field in ("example", "profile", "workspace")
            ):
                raise ValueError(
                    f"eval {eval_id} fixture identity fields must be non-empty strings"
                )
        mutation_policy = entry.get("mutation_policy", "forbidden")
        if mutation_policy not in SUPPORTED_MUTATION_POLICIES:
            raise ValueError(f"eval {eval_id} has unsupported mutation policy: {mutation_policy}")
        fixture_scope = entry.get(
            "fixture_scope", "local" if execution_mode == "offline" else "shared_readonly"
        )
        if fixture_scope not in SUPPORTED_FIXTURE_SCOPES:
            raise ValueError(f"eval {eval_id} has unsupported fixture scope: {fixture_scope}")
        cleanup = entry.get("cleanup")
        if mutation_policy in {"isolated_only", "allow_with_cleanup"}:
            if fixture_scope != "isolated":
                raise ValueError(f"eval {eval_id} mutating runs require an isolated fixture")
            if not isinstance(cleanup, dict) or cleanup.get("required") is not True:
                raise ValueError(f"eval {eval_id} mutating runs require cleanup metadata")
            if cleanup.get("strategy") not in {"ownership_marker", "workspace"}:
                raise ValueError(f"eval {eval_id} has unsupported cleanup strategy")
        elif cleanup is not None and not isinstance(cleanup, dict):
            raise ValueError(f"eval {eval_id} cleanup metadata must be an object")
        prerequisites = entry.get("resource_prerequisites", [])
        if not isinstance(prerequisites, list):
            raise ValueError(f"eval {eval_id} resource_prerequisites must be a list")
        for prerequisite in prerequisites:
            if not isinstance(prerequisite, dict) or not isinstance(prerequisite.get("type"), str):
                raise ValueError(f"eval {eval_id} resource prerequisites require a type")
            if not isinstance(prerequisite.get("match"), dict) or not prerequisite["match"]:
                raise ValueError(
                    f"eval {eval_id} resource prerequisites require a non-empty match object"
                )
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
            required_in_modes = rule.get("required_in_modes")
            if required_in_modes is not None and (
                not isinstance(required_in_modes, list)
                or not required_in_modes
                or any(mode not in SUPPORTED_EXECUTION_MODES for mode in required_in_modes)
            ):
                raise ValueError(
                    f"eval {eval_id} grading rules require supported required_in_modes"
                )
            missing_rule_fields = {"text"} - rule.keys()
            if missing_rule_fields:
                raise ValueError(
                    f"eval {eval_id} grading rule is missing fields: {sorted(missing_rule_fields)}"
                )
            if not isinstance(rule["text"], str) or not rule["text"]:
                raise ValueError(f"eval {eval_id} grading rule text must be non-empty")
            if rule.get("scope", "response") not in SUPPORTED_RULE_SCOPES:
                raise ValueError(f"eval {eval_id} has unsupported rule scope: {rule.get('scope')}")
            grader_type = rule.get("grader_type", "regex")
            if grader_type not in SUPPORTED_GRADER_TYPES:
                raise ValueError(f"eval {eval_id} has unsupported grader type: {grader_type}")
            if grader_type == "regex":
                if rule.get("mode") not in SUPPORTED_RULE_MODES:
                    raise ValueError(
                        f"eval {eval_id} has unsupported rule mode: {rule.get('mode')}"
                    )
                missing_regex_fields = {"mode", "patterns"} - rule.keys()
                if missing_regex_fields:
                    raise ValueError(
                        f"eval {eval_id} regex grading rule is missing fields: "
                        f"{sorted(missing_regex_fields)}"
                    )
            elif not isinstance(rule.get("grader_config"), dict):
                raise ValueError(f"eval {eval_id} structured graders require grader_config")
            validator = rule.get("validator")
            if validator is not None and validator not in SUPPORTED_RULE_VALIDATORS:
                raise ValueError(f"eval {eval_id} has unsupported rule validator: {validator}")
            patterns = rule.get("patterns")
            if grader_type == "regex":
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
