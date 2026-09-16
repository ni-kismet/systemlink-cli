"""Unit tests for read-only fixture snapshots."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Any

from slcli.skills.slcli.scripts.fixture_snapshot import (
    canonical_hash,
    capture_snapshot,
    capture_snapshot_phase,
    resolve_workspace,
)


def fake_runner(
    resources: dict[str, list[dict[str, Any]]], invalid: set[str] | None = None
) -> Callable[[list[str]], subprocess.CompletedProcess[str]]:
    """Build a subprocess runner for bounded fixture snapshot tests."""
    invalid = invalid or set()

    def run(command: list[str]) -> subprocess.CompletedProcess[str]:
        if "workspace" in command:
            payload: Any = [{"id": "workspace-id", "name": "fixture-workspace"}]
            return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")
        resource_type = next(
            (resource_type for resource_type in resources if resource_type in command), None
        )
        if resource_type in invalid:
            return subprocess.CompletedProcess(command, 0, "not-json", "")
        payload = resources.get(resource_type or "", [])
        if resource_type == "data_table":
            payload = {"tables": payload}
        return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

    return run


def live_entry(
    prerequisites: list[dict[str, Any]], execution_mode: str = "live_readonly"
) -> dict[str, Any]:
    """Build a minimal live eval entry."""
    return {
        "id": 1,
        "execution_mode": execution_mode,
        "fixture": {
            "example": "demo-data-3",
            "profile": "test",
            "workspace": "fixture-workspace",
        },
        "resource_prerequisites": prerequisites,
    }


def test_canonical_hash_ignores_api_timestamps() -> None:
    first = {"id": "resource", "updatedAt": "2026-09-01T00:00:00Z", "name": "fixture"}
    second = {"id": "resource", "updatedAt": "2026-09-02T00:00:00Z", "name": "fixture"}

    assert canonical_hash(first) == canonical_hash(second)


def test_resolve_workspace_filters_by_manifest_workspace() -> None:
    commands: list[list[str]] = []

    def runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        commands.append(command)
        return subprocess.CompletedProcess(
            command,
            0,
            json.dumps([{"id": "workspace-id", "name": "fixture-workspace"}]),
            "",
        )

    resolved, error = resolve_workspace("test", "fixture-workspace", runner=runner)

    assert error is None
    assert resolved == {"id": "workspace-id", "name": "fixture-workspace"}
    filter_index = commands[0].index("--filter")
    assert commands[0][filter_index + 1] == "fixture-workspace"


def test_capture_snapshot_reports_ready_and_writes_hash(tmp_path: Path) -> None:
    entry = live_entry(
        [
            {"type": "system", "match": {"name": "PXI-Rack-07"}},
            {"type": "product", "match": {"part_number": "XYZ-2025-001"}},
        ]
    )
    runner = fake_runner(
        {
            "system": [{"id": "system-id", "name": "PXI-Rack-07", "updatedAt": "now"}],
            "product": [{"id": "product-id", "partNumber": "XYZ-2025-001"}],
        }
    )

    output_path = tmp_path / "snapshot.json"
    snapshot = capture_snapshot(entry, output_path, runner=runner)

    assert snapshot["status"] == "ready"
    assert snapshot["snapshot_hash"]
    assert json.loads(output_path.read_text(encoding="utf-8"))["status"] == "ready"


def test_capture_snapshot_reports_fixture_drift_for_missing_required_resource(
    tmp_path: Path,
) -> None:
    entry = live_entry([{"type": "system", "match": {"name": "PXI-Rack-07"}}])
    runner = fake_runner({"system": [{"id": "system-id", "name": "PXI-Rack-12"}]})

    snapshot = capture_snapshot(entry, tmp_path / "snapshot.json", runner=runner)

    assert snapshot["status"] == "fixture_drift"
    assert snapshot["prerequisites"][0]["match_count"] == 0


def test_capture_snapshot_reports_unsupported_inventory(tmp_path: Path) -> None:
    entry = live_entry([{"type": "specification", "match": {"name": "Output"}}])

    snapshot = capture_snapshot(entry, tmp_path / "snapshot.json", runner=fake_runner({}))

    assert snapshot["status"] == "unsupported"
    assert "specification" in snapshot["unsupported"][0]


def test_capture_snapshot_reports_inconclusive_invalid_inventory_json(tmp_path: Path) -> None:
    entry = live_entry([{"type": "system", "match": {"name": "PXI-Rack-07"}}])
    runner = fake_runner({"system": []}, invalid={"system"})

    snapshot = capture_snapshot(entry, tmp_path / "snapshot.json", runner=runner)

    assert snapshot["status"] == "inconclusive"
    assert "invalid JSON" in snapshot["errors"][0]


def test_capture_snapshot_phase_writes_before_after_and_readiness_artifacts(
    tmp_path: Path,
) -> None:
    entry = live_entry([{"type": "system", "match": {"name": "PXI-Rack-07"}}])
    runner = fake_runner({"system": [{"id": "system-id", "name": "PXI-Rack-07"}]})

    before = capture_snapshot_phase(entry, tmp_path, "before", runner=runner)
    after = capture_snapshot_phase(entry, tmp_path, "after", runner=runner)

    assert before["status"] == after["status"] == "ready"
    assert (tmp_path / "fixture_snapshot_before.json").is_file()
    assert (tmp_path / "fixture_snapshot_after.json").is_file()
    readiness = json.loads((tmp_path / "fixture_snapshot.json").read_text(encoding="utf-8"))
    assert readiness["snapshot_hash"] == after["snapshot_hash"]
