"""Load and validate the slcli skill eval manifest."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SUPPORTED_RULE_MODES = {"all_of", "any_of", "none_of"}
SUPPORTED_RULE_SCOPES = {"response", "command"}


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
        if not entry.get("prompt") or not entry.get("expected_output"):
            raise ValueError(f"eval {eval_id} requires prompt and expected_output")
        for relative_path in entry.get("files", []):
            if not (skill_dir / relative_path).is_file():
                raise ValueError(f"eval {eval_id} fixture does not exist: {relative_path}")
        rules = entry.get("grading_rules", [])
        if eval_id in suites["gating"] and not rules:
            raise ValueError(f"gating eval {eval_id} requires grading rules")
        for rule in rules:
            if rule.get("mode") not in SUPPORTED_RULE_MODES:
                raise ValueError(f"eval {eval_id} has unsupported rule mode: {rule.get('mode')}")
            if rule.get("scope", "response") not in SUPPORTED_RULE_SCOPES:
                raise ValueError(f"eval {eval_id} has unsupported rule scope: {rule.get('scope')}")
            if not isinstance(rule.get("critical"), bool):
                raise ValueError(f"eval {eval_id} grading rules require an explicit critical flag")
            if not rule.get("patterns"):
                raise ValueError(f"eval {eval_id} grading rules require patterns")
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
