"""Unit tests for online eval fixture lifecycle orchestration."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any

import pytest

from slcli.skills.slcli.scripts.fixture_lifecycle import SlcliFixtureLifecycleAdapter


def make_run(
    tmp_path: Path,
    *,
    execution_mode: str = "online",
    fixture_scope: str = "shared_readonly",
    mutation_policy: str = "forbidden",
    cleanup: dict[str, Any] | None = None,
    prerequisites: list[dict[str, Any]] | None = None,
) -> Path:
    """Create a minimal prepared eval run."""
    run_dir = tmp_path / "iteration-1" / "eval-1-example" / "with_skill" / "run-1"
    outputs = run_dir / "outputs"
    outputs.mkdir(parents=True)
    eval_dir = run_dir.parents[1]
    (eval_dir / "eval_metadata.json").write_text(
        json.dumps(
            {
                "eval_id": 1,
                "execution_mode": execution_mode,
                "fixture_scope": fixture_scope,
                "mutation_policy": mutation_policy,
                "cleanup": cleanup,
                "resource_prerequisites": prerequisites or [],
            }
        ),
        encoding="utf-8",
    )
    fixture = {
        "profile": "test",
        "workspace": "fixture-workspace",
        "workspace_id": "workspace-id",
    }
    assignment: dict[str, Any] = {"scope": fixture_scope, "fixture": fixture}
    if fixture_scope == "isolated":
        assignment.update({"namespace": "run-marker", "ownership_marker": "run-marker"})
    (run_dir / "run_config.json").write_text(
        json.dumps({"fixture_assignment": assignment}), encoding="utf-8"
    )
    return run_dir


def runner_for(resources: dict[str, list[dict[str, Any]]], calls: list[list[str]]):
    """Build a deterministic slcli runner for lifecycle tests."""

    def runner(command: list[str]) -> subprocess.CompletedProcess[str]:
        calls.append(command)
        if command[5:7] == ["workspace", "list"]:
            payload = [{"id": "workspace-id", "name": "fixture-workspace"}]
        else:
            resource_type = next((key for key in resources if key in command), None)
            payload = resources.get(resource_type or "", [])
        return subprocess.CompletedProcess(command, 0, json.dumps(payload), "")

    return runner


def test_provision_captures_declared_shared_fixture_prerequisites(tmp_path: Path) -> None:
    calls: list[list[str]] = []
    run_dir = make_run(
        tmp_path,
        prerequisites=[{"type": "system", "match": {"name": "Station-1"}}],
    )
    adapter = SlcliFixtureLifecycleAdapter(
        runner=runner_for({"system": [{"id": "system-id", "name": "Station-1"}]}, calls)
    )

    report = adapter.provision(run_dir)

    assert report["status"] == "ready"
    assert any("system" in command and "list" in command for command in calls)
    assert (run_dir / "outputs" / "fixture_snapshot_before.json").is_file()
    assert (run_dir / "outputs" / "fixture_snapshot.json").is_file()


def test_cleanup_deletes_only_owned_typed_resources(tmp_path: Path) -> None:
    calls: list[list[str]] = []
    run_dir = make_run(
        tmp_path,
        fixture_scope="isolated",
        mutation_policy="allow_with_cleanup",
        cleanup={"required": True, "strategy": "ownership_marker"},
    )
    (run_dir / "outputs" / "created_resources.json").write_text(
        json.dumps(
            [
                {
                    "resource_type": "workitem_template",
                    "resource_id": "template-id",
                    "workspace": "workspace-id",
                    "ownership_marker": "run-marker",
                }
            ]
        ),
        encoding="utf-8",
    )
    adapter = SlcliFixtureLifecycleAdapter(runner=runner_for({}, calls))

    report = adapter.cleanup(run_dir)

    assert report["status"] == "clean"
    delete_call = next(
        command for command in calls if "template" in command and "delete" in command
    )
    assert delete_call[-2:] == ["template-id", "--yes"]
    assert (run_dir / "outputs" / "fixture_snapshot_after.json").is_file()


def test_cleanup_captures_shared_fixture_after_snapshot(tmp_path: Path) -> None:
    calls: list[list[str]] = []
    run_dir = make_run(
        tmp_path,
        prerequisites=[{"type": "system", "match": {"name": "Station-1"}}],
    )
    adapter = SlcliFixtureLifecycleAdapter(
        runner=runner_for({"system": [{"id": "system-id", "name": "Station-1"}]}, calls)
    )

    report = adapter.cleanup(run_dir)

    assert report["status"] == "not_required"
    assert report["readiness"] == "ready"
    assert (run_dir / "outputs" / "fixture_snapshot_after.json").is_file()


def test_cleanup_rejects_wrong_ownership_without_deleting(tmp_path: Path) -> None:
    calls: list[list[str]] = []
    run_dir = make_run(
        tmp_path,
        fixture_scope="isolated",
        mutation_policy="allow_with_cleanup",
        cleanup={"required": True, "strategy": "ownership_marker"},
    )
    (run_dir / "outputs" / "created_resources.json").write_text(
        json.dumps(
            [
                {
                    "resource_type": "webapp",
                    "resource_id": "webapp-id",
                    "workspace": "workspace-id",
                    "ownership_marker": "different-run",
                }
            ]
        ),
        encoding="utf-8",
    )
    adapter = SlcliFixtureLifecycleAdapter(runner=runner_for({}, calls))

    report = adapter.cleanup(run_dir)

    assert report["status"] == "failed"
    assert any("ownership marker mismatch" in error for error in report["errors"])
    assert not any("delete" in command for command in calls)


def test_cleanup_reports_malformed_created_resources(tmp_path: Path) -> None:
    run_dir = make_run(
        tmp_path,
        fixture_scope="isolated",
        mutation_policy="allow_with_cleanup",
        cleanup={"required": True, "strategy": "ownership_marker"},
    )
    (run_dir / "outputs" / "created_resources.json").write_text("not-json", encoding="utf-8")

    report = SlcliFixtureLifecycleAdapter().cleanup(run_dir)

    assert report["status"] == "failed"
    assert (run_dir / "outputs" / "cleanup_report.json").is_file()
    assert "Expecting value" in report["errors"][0]


def test_isolated_context_requires_unique_marker(tmp_path: Path) -> None:
    run_dir = make_run(
        tmp_path,
        fixture_scope="isolated",
        mutation_policy="allow_with_cleanup",
        cleanup={"required": True, "strategy": "ownership_marker"},
    )
    config_path = run_dir / "run_config.json"
    config = json.loads(config_path.read_text(encoding="utf-8"))
    config["fixture_assignment"]["ownership_marker"] = "other-marker"
    config_path.write_text(json.dumps(config), encoding="utf-8")

    with pytest.raises(ValueError, match="namespace and ownership marker"):
        SlcliFixtureLifecycleAdapter().provision(run_dir)
