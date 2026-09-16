"""Capture and validate a read-only SystemLink fixture snapshot."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Mapping

from slcli.skills.slcli.scripts.eval_manifest import load_manifest

CommandRunner = Callable[[list[str]], subprocess.CompletedProcess[str]]

SUPPORTED_INVENTORIES: dict[str, tuple[str, ...]] = {
    "system": ("system", "list"),
    "product": ("testmonitor", "product", "list"),
    "test_result": ("testmonitor", "result", "list"),
    "asset": ("asset", "list"),
    "dut": ("asset", "list"),
    "data_table": ("dataframe", "list"),
    "file": ("file", "list"),
    "notebook": ("notebook", "manage", "list"),
    "feed": ("feed", "list"),
    "state": ("state", "list"),
    "tag": ("tag", "list"),
    "alarm": ("alarm", "list"),
    "workflow": ("workflow", "list"),
    "workitem_template": ("workitem", "template", "list"),
}
SNAPSHOT_PHASES = {
    "readiness": "fixture_snapshot.json",
    "before": "fixture_snapshot_before.json",
    "after": "fixture_snapshot_after.json",
}

VOLATILE_FIELDS = frozenset(
    {
        "created",
        "createdAt",
        "lastSeen",
        "updated",
        "updatedAt",
    }
)
FIELD_ALIASES: dict[str, tuple[str, ...]] = {
    "part_number": ("part_number", "partNumber"),
    "serial_number": ("serial_number", "serialNumber"),
    "system_id": ("system_id", "systemId"),
    "workspace_id": ("workspace_id", "workspaceId", "workspace"),
}


def positive_int(value: str) -> int:
    """Parse a positive integer command-line value."""
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be greater than zero")
    return parsed


def run_cli(command: list[str]) -> subprocess.CompletedProcess[str]:
    """Run one CLI command without raising on an API or command failure."""
    return subprocess.run(command, capture_output=True, text=True, check=False)


def canonicalize(value: Any) -> Any:
    """Return JSON-compatible data with volatile fields removed."""
    if isinstance(value, dict):
        return {
            key: canonicalize(item)
            for key, item in sorted(value.items())
            if key not in VOLATILE_FIELDS
        }
    if isinstance(value, list):
        return [canonicalize(item) for item in value]
    return value


def canonical_hash(value: Any) -> str:
    """Hash canonical JSON data."""
    encoded = json.dumps(canonicalize(value), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _lookup(resource: Mapping[str, Any], key: str) -> Any:
    """Look up a possibly snake-case field in a resource."""
    current: Any = resource
    for part in key.split("."):
        if not isinstance(current, Mapping):
            return None
        candidates = FIELD_ALIASES.get(part, (part,))
        found = False
        for candidate in candidates:
            if candidate in current:
                current = current[candidate]
                found = True
                break
        if not found:
            return None
    return current


def _matches_expected(resource: Mapping[str, Any], expected: Mapping[str, Any]) -> bool:
    """Return whether a resource contains all expected field values."""
    for key, expected_value in expected.items():
        actual_value = _lookup(resource, key)
        if isinstance(expected_value, Mapping):
            if not isinstance(actual_value, Mapping) or not _matches_expected(
                actual_value, expected_value
            ):
                return False
        elif actual_value != expected_value:
            return False
    return True


def _extract_items(payload: Any) -> list[dict[str, Any]]:
    """Extract resource dictionaries from common slcli JSON response shapes."""
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in ("items", "resources", "results", "tables", "files", "workspaces"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return [payload]


def resolve_workspace(
    profile: str,
    workspace: str,
    expected_workspace_id: str | None = None,
    runner: CommandRunner = run_cli,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    """Resolve a workspace by exact name or ID using a read-only query."""
    command = [
        sys.executable,
        "-m",
        "slcli",
        "--profile",
        profile,
        "workspace",
        "list",
        "--filter",
        workspace,
        "--format",
        "json",
    ]
    result = runner(command)
    try:
        payload = json.loads(result.stdout)
    except (TypeError, json.JSONDecodeError):
        return None, {"status": "inconclusive", "error": "workspace query returned invalid JSON"}
    if result.returncode != 0:
        return None, {"status": "inconclusive", "error": result.stderr.strip()[:500]}
    matches = [
        item
        for item in _extract_items(payload)
        if item.get("id") == workspace or item.get("name") == workspace
    ]
    if len(matches) != 1:
        return None, {
            "status": "fixture_drift",
            "error": f"expected one exact workspace match for {workspace!r}, found {len(matches)}",
        }
    resolved = matches[0]
    if expected_workspace_id and resolved.get("id") != expected_workspace_id:
        return None, {
            "status": "fixture_drift",
            "error": "resolved workspace ID does not match fixture metadata",
        }
    return resolved, None


def query_inventory(
    profile: str,
    workspace_id: str,
    resource_type: str,
    take: int,
    runner: CommandRunner = run_cli,
) -> dict[str, Any]:
    """Query one bounded resource inventory through slcli."""
    command_parts = SUPPORTED_INVENTORIES.get(resource_type)
    if command_parts is None:
        return {"status": "unsupported", "error": f"no read-only query for {resource_type}"}
    command = [
        sys.executable,
        "-m",
        "slcli",
        "--profile",
        profile,
        *command_parts,
        "--workspace",
        workspace_id,
        "--take",
        str(take),
        "--format",
        "json",
    ]
    result = runner(command)
    if result.returncode != 0:
        return {
            "status": "inconclusive",
            "command": command_parts,
            "error": result.stderr.strip()[:500],
        }
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {
            "status": "inconclusive",
            "command": command_parts,
            "error": "inventory query returned invalid JSON",
        }
    items = _extract_items(payload)
    return {
        "status": "ready",
        "command": command_parts,
        "count": len(items),
        "items": items,
    }


def capture_snapshot(
    eval_entry: dict[str, Any],
    output_path: Path,
    take: int = 1000,
    runner: CommandRunner = run_cli,
) -> dict[str, Any]:
    """Capture fixture prerequisites and write a readiness snapshot."""
    fixture = eval_entry.get("fixture")
    if not isinstance(fixture, dict):
        raise ValueError(f"eval {eval_entry.get('id')} has no fixture metadata")
    profile = fixture["profile"]
    workspace_name = fixture["workspace"]
    workspace, workspace_error = resolve_workspace(
        profile, workspace_name, fixture.get("workspace_id"), runner
    )
    snapshot: dict[str, Any] = {
        "schema_version": 1,
        "captured_at": datetime.now(timezone.utc).isoformat(),
        "eval_id": eval_entry["id"],
        "execution_mode": eval_entry.get("execution_mode", "offline"),
        "fixture": fixture,
        "status": "inconclusive",
        "workspace": workspace,
        "inventories": {},
        "prerequisites": [],
        "unsupported": [],
        "errors": [],
    }
    if workspace_error:
        snapshot["status"] = workspace_error["status"]
        snapshot["errors"].append(workspace_error["error"])
        _write_snapshot(output_path, snapshot)
        return snapshot
    if workspace is None:
        snapshot["status"] = "inconclusive"
        snapshot["errors"].append("workspace query returned no workspace")
        _write_snapshot(output_path, snapshot)
        return snapshot

    workspace_id = workspace["id"]
    prerequisites = eval_entry.get("resource_prerequisites", [])
    if not prerequisites and eval_entry.get("fixture_scope") == "isolated":
        snapshot["status"] = "ready"
        snapshot["snapshot_hash"] = canonical_hash({"workspace": snapshot["workspace"]})
        _write_snapshot(output_path, snapshot)
        return snapshot
    if not prerequisites:
        snapshot["status"] = "inconclusive"
        snapshot["errors"].append("live fixture requires at least one resource prerequisite")
        _write_snapshot(output_path, snapshot)
        return snapshot

    for resource_type in sorted({item["type"] for item in prerequisites}):
        inventory = query_inventory(profile, workspace_id, resource_type, take, runner)
        snapshot["inventories"][resource_type] = inventory
        if inventory["status"] == "unsupported":
            snapshot["unsupported"].append(inventory["error"])
        elif inventory["status"] != "ready":
            snapshot["errors"].append(f"{resource_type}: {inventory['error']}")

    drift = False
    for prerequisite in prerequisites:
        resource_type = prerequisite["type"]
        expected = prerequisite["match"]
        inventory = snapshot["inventories"][resource_type]
        matches = (
            [item for item in inventory.get("items", []) if _matches_expected(item, expected)]
            if inventory.get("status") == "ready"
            else []
        )
        required = prerequisite.get("required", True)
        prerequisite_record = {
            "type": resource_type,
            "match": expected,
            "required": required,
            "match_count": len(matches),
            "resources": [canonicalize(item) for item in matches],
        }
        snapshot["prerequisites"].append(prerequisite_record)
        if required and not matches and inventory.get("status") == "ready":
            drift = True

    if snapshot["unsupported"]:
        snapshot["status"] = "unsupported"
    elif snapshot["errors"]:
        snapshot["status"] = "inconclusive"
    elif drift:
        snapshot["status"] = "fixture_drift"
    else:
        snapshot["status"] = "ready"
    snapshot["snapshot_hash"] = canonical_hash(
        {"workspace": snapshot["workspace"], "prerequisites": snapshot["prerequisites"]}
    )
    _write_snapshot(output_path, snapshot)
    return snapshot


def _write_snapshot(path: Path, snapshot: dict[str, Any]) -> None:
    """Write a snapshot artifact with stable formatting."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def capture_snapshot_phase(
    eval_entry: dict[str, Any],
    output_directory: Path,
    phase: str,
    take: int = 1000,
    runner: CommandRunner = run_cli,
) -> dict[str, Any]:
    """Capture one lifecycle phase and update the standard readiness artifact."""
    try:
        filename = SNAPSHOT_PHASES[phase]
    except KeyError as error:
        raise ValueError(f"unsupported snapshot phase: {phase}") from error
    output_path = output_directory / filename
    snapshot = capture_snapshot(eval_entry, output_path, take, runner)
    if phase != "readiness":
        _write_snapshot(output_directory / SNAPSHOT_PHASES["readiness"], snapshot)
    return snapshot


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    script_dir = Path(__file__).resolve().parent
    default_manifest = script_dir.parent / "evals" / "evals.json"
    parser = argparse.ArgumentParser(description="Capture a read-only SystemLink fixture snapshot.")
    parser.add_argument("--evals", type=Path, default=default_manifest)
    parser.add_argument("--eval-id", type=int, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--fixture-profile")
    parser.add_argument("--fixture-workspace")
    parser.add_argument("--fixture-workspace-id")
    parser.add_argument(
        "--phase",
        choices=sorted(SNAPSHOT_PHASES),
        default="readiness",
        help="Snapshot lifecycle phase to capture.",
    )
    parser.add_argument("--take", type=positive_int, default=1000)
    return parser.parse_args()


def main() -> None:
    """Capture one fixture snapshot and return a readiness-based exit code."""
    args = parse_args()
    manifest = load_manifest(args.evals)
    entry = next((item for item in manifest["evals"] if item["id"] == args.eval_id), None)
    if entry is None:
        raise ValueError(f"Eval id {args.eval_id} not found in {args.evals}")
    if args.fixture_profile or args.fixture_workspace or args.fixture_workspace_id:
        if not args.fixture_profile or not args.fixture_workspace:
            raise ValueError("fixture profile and workspace must be provided together")
        entry = {
            **entry,
            "execution_mode": "online",
            "fixture": {
                "example": "external",
                "profile": args.fixture_profile,
                "workspace": args.fixture_workspace,
                **(
                    {"workspace_id": args.fixture_workspace_id} if args.fixture_workspace_id else {}
                ),
            },
        }
    snapshot = (
        capture_snapshot(entry, args.output, args.take)
        if args.phase == "readiness"
        else capture_snapshot_phase(entry, args.output.parent, args.phase, args.take)
    )
    print(json.dumps(snapshot, indent=2, sort_keys=True))
    if snapshot["status"] != "ready":
        raise SystemExit(2)


if __name__ == "__main__":
    main()
