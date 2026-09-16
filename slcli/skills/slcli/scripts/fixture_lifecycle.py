"""Prepare, validate, and clean up online eval fixture assignments."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Protocol

from slcli.skills.slcli.scripts.fixture_snapshot import (
    capture_snapshot_phase,
    run_cli,
)

CommandRunner = Callable[[list[str]], subprocess.CompletedProcess[str]]

SUPPORTED_REMOTE_MODES = {"online", "live_readonly", "hybrid"}
RESOURCE_TYPE_ALIASES = {
    "work-item-template": "workitem_template",
    "workitem-template": "workitem_template",
    "spec": "specification",
    "web_app": "webapp",
    "web-app": "webapp",
}
RESOURCE_DELETE_COMMANDS: dict[str, tuple[str, ...]] = {
    "workitem_template": ("workitem", "template", "delete"),
    "specification": ("spec", "delete", "--id"),
    "webapp": ("webapp", "delete", "--id"),
}


class LifecycleAdapter(Protocol):
    """Protocol implemented by online fixture lifecycle adapters."""

    def provision(self, run_dir: Path) -> dict[str, Any]:
        """Validate the externally provisioned fixture for one run."""

    def cleanup(self, run_dir: Path) -> dict[str, Any]:
        """Finalize one run and delete only resources owned by it."""


@dataclass(frozen=True)
class LifecycleContext:
    """Resolved lifecycle metadata for one prepared run."""

    eval_id: int
    execution_mode: str
    fixture_scope: str
    mutation_policy: str
    fixture: dict[str, Any] | None
    cleanup: dict[str, Any] | None
    resource_prerequisites: list[dict[str, Any]]
    assignment: dict[str, Any]


def _load_json(path: Path) -> Any:
    """Load one JSON artifact."""
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    """Write one JSON artifact with stable formatting."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _as_object(value: Any, description: str) -> dict[str, Any]:
    """Validate and return a JSON object."""
    if not isinstance(value, dict):
        raise ValueError(f"{description} must be a JSON object")
    return value


def load_context(run_dir: Path) -> LifecycleContext:
    """Load and validate lifecycle metadata from one run directory."""
    eval_dir = run_dir.parents[1]
    metadata = _as_object(_load_json(eval_dir / "eval_metadata.json"), "eval metadata")
    run_config = _as_object(_load_json(run_dir / "run_config.json"), "run config")
    assignment = _as_object(run_config.get("fixture_assignment", {}), "fixture assignment")
    execution_mode = str(metadata.get("execution_mode", "offline"))
    fixture_scope = str(assignment.get("scope", metadata.get("fixture_scope", "local")))
    mutation_policy = str(metadata.get("mutation_policy", "forbidden"))
    fixture_value = assignment.get("fixture", metadata.get("fixture"))
    fixture = dict(fixture_value) if isinstance(fixture_value, dict) else None
    if fixture is not None:
        for key in ("namespace", "ownership_marker"):
            if key in assignment:
                fixture[key] = assignment[key]
    cleanup = metadata.get("cleanup")
    if cleanup is not None:
        cleanup = _as_object(cleanup, "cleanup metadata")
    prerequisites = metadata.get("resource_prerequisites", [])
    if not isinstance(prerequisites, list) or any(
        not isinstance(item, dict) for item in prerequisites
    ):
        raise ValueError("resource_prerequisites must be a list of JSON objects")
    eval_id = metadata.get("eval_id")
    if not isinstance(eval_id, int) or isinstance(eval_id, bool):
        raise ValueError("eval metadata requires an integer eval_id")
    context = LifecycleContext(
        eval_id=eval_id,
        execution_mode=execution_mode,
        fixture_scope=fixture_scope,
        mutation_policy=mutation_policy,
        fixture=fixture,
        cleanup=cleanup,
        resource_prerequisites=list(prerequisites),
        assignment=assignment,
    )
    validate_context(context)
    return context


def validate_context(context: LifecycleContext) -> None:
    """Validate the safety invariants for one lifecycle assignment."""
    if context.execution_mode == "offline":
        if context.fixture_scope != "local":
            raise ValueError("offline runs must use a local fixture scope")
        return
    if context.execution_mode not in SUPPORTED_REMOTE_MODES:
        raise ValueError(f"unsupported lifecycle execution mode: {context.execution_mode}")
    if context.fixture_scope == "local":
        return
    fixture = context.fixture
    if fixture is None:
        raise ValueError("remote runs require fixture metadata")
    for key in ("profile", "workspace"):
        if not isinstance(fixture.get(key), str) or not fixture[key].strip():
            raise ValueError(f"remote fixture requires a non-empty {key}")
    if context.fixture_scope == "shared_readonly":
        if context.mutation_policy != "forbidden":
            raise ValueError("shared fixtures may only use forbidden mutation policy")
        return
    if context.fixture_scope != "isolated":
        raise ValueError(f"unsupported fixture scope: {context.fixture_scope}")
    for key in ("namespace", "ownership_marker"):
        if not isinstance(fixture.get(key), str) or not fixture[key].strip():
            raise ValueError(f"isolated fixtures require a non-empty {key}")
    if fixture["namespace"] != fixture["ownership_marker"]:
        raise ValueError("isolated fixture namespace and ownership marker must match")
    if context.mutation_policy == "forbidden":
        raise ValueError("isolated fixtures cannot use forbidden mutation policy")
    if not isinstance(context.cleanup, dict) or context.cleanup.get("required") is not True:
        raise ValueError("isolated fixtures require cleanup metadata")


def _snapshot_entry(context: LifecycleContext) -> dict[str, Any]:
    """Build a snapshot entry from runtime lifecycle metadata."""
    return {
        "id": context.eval_id,
        "execution_mode": context.execution_mode,
        "fixture_scope": context.fixture_scope,
        "fixture": context.fixture,
        "resource_prerequisites": context.resource_prerequisites,
    }


def _base_report(context: LifecycleContext) -> dict[str, Any]:
    """Build common lifecycle report metadata."""
    return {
        "schema_version": 1,
        "eval_id": context.eval_id,
        "execution_mode": context.execution_mode,
        "fixture_scope": context.fixture_scope,
        "mutation_policy": context.mutation_policy,
        "fixture": context.fixture,
        "assignment": context.assignment,
    }


class SlcliFixtureLifecycleAdapter:
    """Lifecycle adapter using bounded slcli queries and typed delete commands."""

    def __init__(
        self,
        runner: CommandRunner = run_cli,
        take: int = 1000,
    ) -> None:
        """Initialize the adapter."""
        self._runner = runner
        self._take = take

    def provision(self, run_dir: Path) -> dict[str, Any]:
        """Validate an externally provisioned fixture and capture its baseline."""
        context = load_context(run_dir)
        outputs_dir = run_dir / "outputs"
        report = _base_report(context)
        report["phase"] = "provision"
        if context.execution_mode == "offline" or context.fixture_scope == "local":
            report.update({"status": "not_applicable", "provisioning": "local"})
            _write_json(outputs_dir / "lifecycle_provision.json", report)
            return report

        report["provisioning"] = "external_assignment"
        snapshot = capture_snapshot_phase(
            _snapshot_entry(context),
            outputs_dir,
            "before",
            take=self._take,
            runner=self._runner,
        )
        report["readiness"] = snapshot.get("status")
        report["status"] = snapshot.get("status", "inconclusive")
        _write_json(outputs_dir / "lifecycle_provision.json", report)
        return report

    def cleanup(self, run_dir: Path) -> dict[str, Any]:
        """Finalize a run and delete validated isolated resources."""
        context = load_context(run_dir)
        outputs_dir = run_dir / "outputs"
        report = _base_report(context)
        report["phase"] = "cleanup"
        if context.fixture_scope != "isolated":
            if context.execution_mode in SUPPORTED_REMOTE_MODES and context.fixture is not None:
                after_snapshot = capture_snapshot_phase(
                    _snapshot_entry(context),
                    outputs_dir,
                    "after",
                    take=self._take,
                    runner=self._runner,
                )
                report["readiness"] = after_snapshot.get("status")
            report["status"] = "not_required"
            _write_json(outputs_dir / "cleanup_report.json", report)
            return report

        created_path = outputs_dir / "created_resources.json"
        if not created_path.is_file():
            report.update({"status": "failed", "errors": ["created_resources.json is missing"]})
            _write_json(outputs_dir / "cleanup_report.json", report)
            return report

        try:
            resources = _load_created_resources(created_path)
        except (OSError, TypeError, ValueError, json.JSONDecodeError) as load_error:
            report.update({"status": "failed", "errors": [str(load_error)]})
            _write_json(outputs_dir / "cleanup_report.json", report)
            return report
        deleted: list[dict[str, Any]] = []
        errors: list[str] = []
        for resource in resources:
            error = _validate_resource_ownership(resource, context)
            if error:
                errors.append(error)
                continue
            resource_type = _canonical_resource_type(resource["resource_type"])
            command_parts = RESOURCE_DELETE_COMMANDS.get(resource_type)
            if command_parts is None:
                errors.append(f"unsupported cleanup resource type: {resource_type}")
                continue
            command = [
                sys.executable,
                "-m",
                "slcli",
                "--profile",
                context.fixture["profile"] if context.fixture else "",
                *command_parts,
                resource["resource_id"],
                *(
                    ["--yes"]
                    if resource_type == "workitem_template"
                    else ["--force"] if resource_type == "specification" else []
                ),
            ]
            result = self._runner(command)
            deletion = {
                "resource_type": resource_type,
                "resource_id": resource["resource_id"],
                "command": command,
                "exit_code": result.returncode,
                "stderr": result.stderr[-500:],
            }
            deleted.append(deletion)
            if result.returncode != 0:
                errors.append(
                    f"cleanup command failed for {resource_type}/{resource['resource_id']}"
                )

        final_snapshot: dict[str, Any] | None = None
        if context.execution_mode in SUPPORTED_REMOTE_MODES and context.fixture is not None:
            final_snapshot = capture_snapshot_phase(
                _snapshot_entry(context),
                outputs_dir,
                "after",
                take=self._take,
                runner=self._runner,
            )
            if final_snapshot.get("status") not in {"ready", "not_applicable"}:
                errors.append(f"post-cleanup fixture readiness is {final_snapshot.get('status')!r}")

        report["deleted"] = deleted
        report["errors"] = errors
        report["status"] = "clean" if not errors else "failed"
        _write_json(outputs_dir / "cleanup_report.json", report)
        return report


def _load_created_resources(path: Path) -> list[dict[str, str]]:
    """Load normalized created-resource records."""
    payload = _load_json(path)
    if isinstance(payload, dict):
        payload = payload.get("resources")
    if not isinstance(payload, list):
        raise ValueError("created_resources.json must contain a list or resources object")
    resources: list[dict[str, str]] = []
    for item in payload:
        if not isinstance(item, dict):
            raise ValueError("created resource records must be JSON objects")
        resources.append(
            {
                "resource_type": str(item.get("resource_type", item.get("type", ""))),
                "resource_id": str(item.get("resource_id", item.get("id", ""))),
                "workspace": str(item.get("workspace", item.get("workspace_id", ""))),
                "ownership_marker": str(item.get("ownership_marker", item.get("owner", ""))),
            }
        )
    return resources


def _canonical_resource_type(resource_type: str) -> str:
    """Normalize a resource type alias."""
    return RESOURCE_TYPE_ALIASES.get(resource_type.strip().lower(), resource_type.strip().lower())


def _validate_resource_ownership(
    resource: Mapping[str, str], context: LifecycleContext
) -> str | None:
    """Validate that a resource belongs to the assigned fixture namespace."""
    resource_type = _canonical_resource_type(resource.get("resource_type", ""))
    resource_id = resource.get("resource_id", "")
    marker = resource.get("ownership_marker", "")
    if not resource_type or not resource_id:
        return "created resource requires resource_type and resource_id"
    expected_marker = str((context.fixture or {}).get("ownership_marker", ""))
    if not expected_marker or marker != expected_marker:
        return f"ownership marker mismatch for {resource_type}/{resource_id}"
    workspace = resource.get("workspace", "")
    fixture = context.fixture or {}
    expected_workspaces = {str(fixture.get("workspace", ""))}
    if fixture.get("workspace_id"):
        expected_workspaces.add(str(fixture["workspace_id"]))
    if not workspace or workspace not in expected_workspaces:
        return f"workspace mismatch for {resource_type}/{resource_id}"
    return None


def positive_int(value: str) -> int:
    """Parse a positive integer argument."""
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("value must be greater than zero")
    return parsed


def parse_args() -> argparse.Namespace:
    """Parse lifecycle command-line arguments."""
    parser = argparse.ArgumentParser(description="Run one online eval fixture lifecycle phase.")
    parser.add_argument("phase", choices=["provision", "cleanup"])
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--take", type=positive_int, default=1000)
    return parser.parse_args()


def main() -> None:
    """Run one lifecycle phase and return a machine-readable status."""
    args = parse_args()
    adapter = SlcliFixtureLifecycleAdapter(take=args.take)
    report = (
        adapter.provision(args.run_dir)
        if args.phase == "provision"
        else adapter.cleanup(args.run_dir)
    )
    print(json.dumps(report, indent=2, sort_keys=True))
    success_statuses = {"ready", "clean", "not_applicable", "not_required"}
    if report.get("status") not in success_statuses:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
