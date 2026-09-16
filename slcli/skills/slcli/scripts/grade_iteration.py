"""Grade all available runs in an slcli eval iteration workspace."""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
from datetime import date
from pathlib import Path
from typing import Any

from slcli.skills.slcli.scripts.grade_eval_response import gather_response_text, grade_response
from slcli.skills.slcli.scripts.prepare_eval_workspace import hash_directory


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    skill_dir = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(
        description="Grade every populated run directory in an slcli eval iteration."
    )
    parser.add_argument(
        "iteration_dir",
        type=Path,
        help="Path to an iteration-N directory created by prepare_eval_workspace.py.",
    )
    parser.add_argument(
        "--evals",
        type=Path,
        default=skill_dir / "evals" / "evals.json",
        help="Path to evals.json.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Recompute grading.json even if it already exists.",
    )
    return parser.parse_args()


def load_json(path: Path) -> dict[str, Any]:
    """Load a JSON file into a dict."""
    return json.loads(path.read_text(encoding="utf-8"))


def iter_run_dirs(iteration_dir: Path) -> list[tuple[int, Path]]:
    """Yield eval_id and run directory pairs for all prepared runs."""
    run_pairs: list[tuple[int, Path]] = []
    for eval_dir in sorted(iteration_dir.glob("eval-*")):
        metadata_path = eval_dir / "eval_metadata.json"
        if not metadata_path.exists():
            continue
        eval_id = int(load_json(metadata_path)["eval_id"])
        for config_dir in sorted(eval_dir.iterdir()):
            if not config_dir.is_dir():
                continue
            for run_dir in sorted(config_dir.glob("run-*")):
                run_pairs.append((eval_id, run_dir))
    return run_pairs


def file_manifest(output_dir: Path) -> list[dict[str, object]]:
    """Describe output artifacts with stable content hashes."""
    files: list[dict[str, object]] = []
    for path in sorted(item for item in output_dir.rglob("*") if item.is_file()):
        files.append(
            {
                "path": path.relative_to(output_dir).as_posix(),
                "size": path.stat().st_size,
                "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
            }
        )
    return files


def hash_file(path: Path) -> str:
    """Return a SHA-256 hash for one file."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def load_raw_executor_metadata(path: Path) -> Any:
    """Preserve executor-authored metadata without trusting its structure."""
    if not path.is_file():
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        return text


def load_transcript(path: Path) -> list[dict[str, Any]]:
    """Load a non-empty JSONL transcript containing only JSON objects."""
    events: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if not line.strip():
            continue
        event = json.loads(line)
        if not isinstance(event, dict):
            raise ValueError("transcript events must be JSON objects")
        events.append(event)
    if not events:
        raise ValueError("transcript must contain at least one JSON event")
    return events


def _string_values(value: Any) -> list[str]:
    """Return all string values nested in a JSON-compatible value."""
    if isinstance(value, str):
        return [value]
    if isinstance(value, dict):
        return [text for item in value.values() for text in _string_values(item)]
    if isinstance(value, list):
        return [text for item in value for text in _string_values(item)]
    return []


def _named_string_values(value: Any, field: str) -> list[str]:
    """Return string values for a named field at any nesting depth."""
    if isinstance(value, dict):
        direct = value.get(field)
        values = [direct] if isinstance(direct, str) else []
        return values + [
            text for item in value.values() for text in _named_string_values(item, field)
        ]
    if isinstance(value, list):
        return [text for item in value for text in _named_string_values(item, field)]
    return []


def offline_evidence_error(
    transcript: list[dict[str, Any]], response_text: str, outputs_dir: Path
) -> str | None:
    """Reject operational execution and unsupported live-result claims in offline runs."""
    if (outputs_dir / "execution_records.json").exists():
        return "offline run contains execution records"
    commands = [
        command for event in transcript for command in _named_string_values(event, "command")
    ]
    for command in commands:
        if re.search(r"(?:^|\s)slcli\s+", command) and "--help" not in command:
            return "offline run invoked an operational slcli command"
    evidence_text = "\n".join([response_text, *(_string_values(transcript))])
    unsupported_claim = re.search(
        r"\b(?:I|we)?\s*(?:queried|executed|ran|created|updated|deleted)\b|"
        r"\b(?:found|returned)\s+(?:no\s+)?(?:matching\s+)?(?:results?|resources?|templates?)\b",
        evidence_text,
        re.IGNORECASE,
    )
    if unsupported_claim:
        return "offline run claims live execution without captured evidence"
    return None


def run_skill_hash(run_dir: Path) -> str | None:
    """Hash the skill in a run's isolated repository, or return None when absent."""
    run_config = load_json(run_dir / "run_config.json")
    repository_root = run_config.get("repository_root")
    if repository_root is None:
        return None
    if not isinstance(repository_root, str):
        raise ValueError("run repository_root must be a string or null")
    repository_path = Path(repository_root).resolve()
    if repository_path != (run_dir / "repo").resolve():
        raise ValueError("run repository_root must identify the run's isolated repository")
    skill_dir = repository_path / "slcli" / "skills" / "slcli"
    return hash_directory(skill_dir) if skill_dir.is_dir() else None


def executor_prompt_hash(run_dir: Path) -> str:
    """Hash the executor prompt for one run."""
    return hashlib.sha256((run_dir / "executor_prompt.txt").read_bytes()).hexdigest()


def run_manifest_key(run_dir: Path) -> str:
    """Return the iteration-relative manifest key for one run."""
    return run_dir.relative_to(run_dir.parents[2]).as_posix()


def eval_lifecycle(iteration_metadata: dict[str, Any], eval_id: int) -> dict[str, Any]:
    """Return lifecycle metadata, including compatibility for older iterations."""
    lifecycle = iteration_metadata.get("lifecycle_by_eval", {})
    if isinstance(lifecycle, dict) and isinstance(lifecycle.get(str(eval_id)), dict):
        return lifecycle[str(eval_id)]
    live_eval_ids = iteration_metadata.get("live_eval_ids", [])
    if isinstance(live_eval_ids, list) and eval_id in live_eval_ids:
        return {
            "execution_mode": "live_readonly",
            "fixture_scope": "shared_readonly",
            "mutation_policy": "forbidden",
        }
    return {"execution_mode": "offline", "fixture_scope": "local"}


def grade_run(
    manifest_path: Path,
    eval_id: int,
    run_dir: Path,
    force: bool,
    iteration_metadata: dict[str, Any],
) -> str:
    """Grade one run directory if response artifacts exist."""
    output_path = run_dir / "grading.json"
    if output_path.exists() and not force:
        return f"skip {run_dir}: grading.json exists"

    outputs_dir = run_dir / "outputs"
    required_artifacts = ("response.txt", "transcript.jsonl", "run_metadata.json")
    missing_artifacts = [name for name in required_artifacts if not (outputs_dir / name).is_file()]
    lifecycle = eval_lifecycle(iteration_metadata, eval_id)
    execution_mode = lifecycle.get("execution_mode", "offline")
    fixture_scope = lifecycle.get("fixture_scope", "local")
    is_online = execution_mode != "offline"
    requires_remote_fixture = is_online and fixture_scope != "local"
    if requires_remote_fixture:
        missing_artifacts.extend(
            name
            for name in (
                "execution_records.json",
                "fixture_snapshot.json",
                "fixture_snapshot_before.json",
                "fixture_snapshot_after.json",
            )
            if not (outputs_dir / name).is_file()
        )
    if (
        fixture_scope == "isolated"
        and isinstance(lifecycle.get("cleanup"), dict)
        and lifecycle["cleanup"].get("required")
    ):
        missing_artifacts.extend(
            name
            for name in ("created_resources.json", "cleanup_report.json")
            if not (outputs_dir / name).is_file()
        )
    if not (run_dir / "timing.json").is_file():
        missing_artifacts.append("timing.json")
    if missing_artifacts:
        return f"skip {run_dir}: required outputs missing: {', '.join(missing_artifacts)}"

    response_path = outputs_dir / "response.txt"
    try:
        transcript = load_transcript(outputs_dir / "transcript.jsonl")
    except (OSError, TypeError, ValueError, json.JSONDecodeError):
        return f"skip {run_dir}: invalid transcript"

    try:
        response_text, _ = gather_response_text(response_path)
        actual_skill_hash = run_skill_hash(run_dir)
        actual_prompt_hash = executor_prompt_hash(run_dir)
        prompt_hashes = iteration_metadata.get("executor_prompt_hashes")
        expected_prompt_hash = (
            prompt_hashes.get(run_manifest_key(run_dir))
            if isinstance(prompt_hashes, dict)
            else None
        )
        if actual_prompt_hash != expected_prompt_hash:
            raise ValueError("executor prompt does not match iteration manifest")
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return f"skip {run_dir}: invalid response or run configuration"

    offline_error = (
        None if is_online else offline_evidence_error(transcript, response_text, outputs_dir)
    )

    timing_path = run_dir / "timing.json"
    run_metadata_path = outputs_dir / "run_metadata.json"
    try:
        run_metadata = load_json(run_metadata_path)
        timing = load_json(timing_path)
        if not isinstance(run_metadata, dict) or not isinstance(timing, dict):
            raise ValueError("run metadata and timing must be JSON objects")
        duration_ms = timing.get("duration_ms")
        duration_seconds = timing.get("total_duration_seconds")
        total_tokens = timing.get("total_tokens")
        if (
            not isinstance(duration_ms, (int, float))
            or isinstance(duration_ms, bool)
            or not math.isfinite(duration_ms)
            or duration_ms < 0
            or not isinstance(duration_seconds, (int, float))
            or isinstance(duration_seconds, bool)
            or not math.isfinite(duration_seconds)
            or duration_seconds < 0
            or abs(duration_seconds - duration_ms / 1000) > 0.1
        ):
            raise ValueError("timing requires consistent nonnegative duration values")
        if not isinstance(total_tokens, int) or isinstance(total_tokens, bool) or total_tokens < 0:
            raise ValueError("timing requires a nonnegative total_tokens value")
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return f"skip {run_dir}: invalid run metadata or timing"

    reference_date_value = iteration_metadata.get("reference_date")
    if not isinstance(reference_date_value, str):
        return f"skip {run_dir}: invalid iteration reference date"
    try:
        reference_date = date.fromisoformat(reference_date_value)
    except ValueError:
        return f"skip {run_dir}: invalid iteration reference date"

    try:
        input_manifest = load_json(run_dir / "inputs_manifest.json")
        input_files = input_manifest.get("files")
        if not isinstance(input_files, list):
            raise ValueError("input manifest files must be a list")
        input_manifest_hashes = iteration_metadata.get("input_manifest_hashes")
        expected_input_manifest_hash = (
            input_manifest_hashes.get(run_manifest_key(run_dir))
            if isinstance(input_manifest_hashes, dict)
            else None
        )
        actual_input_manifest_hash = hash_file(run_dir / "inputs_manifest.json")
        if (
            not isinstance(expected_input_manifest_hash, str)
            or actual_input_manifest_hash != expected_input_manifest_hash
        ):
            raise ValueError("input manifest does not match iteration manifest")
    except (json.JSONDecodeError, OSError, TypeError, ValueError, AttributeError):
        return f"skip {run_dir}: invalid input manifest"
    graded = grade_response(
        manifest_path,
        eval_id,
        response_path,
        timing_path,
        outputs_dir / "transcript.jsonl",
        reference_date,
        {
            "execution_mode": execution_mode,
            "fixture": lifecycle.get("fixture"),
            "fixture_scope": fixture_scope,
            "mutation_policy": lifecycle.get("mutation_policy", "forbidden"),
            "cleanup": lifecycle.get("cleanup"),
        },
    )
    expected_executor = iteration_metadata.get("executor")
    if isinstance(expected_executor, dict):
        expected_metadata = {
            **expected_executor,
            "configuration": run_dir.parent.name,
            "status": run_metadata.get("status"),
        }
        if run_metadata != expected_metadata:
            return f"skip {run_dir}: executor metadata does not match iteration manifest"
    infrastructure_error = run_metadata.get("status") == "infrastructure_error"
    critical_results = [item for item in graded["expectations"] if item.get("critical", True)]
    readiness = graded.get("evaluation", {}).get("fixture_readiness", "not_applicable")
    inconclusive_statuses = {"inconclusive", "fixture_drift", "unsupported"}
    classification = (
        "inconclusive"
        if infrastructure_error or offline_error
        else (
            "inconclusive"
            if readiness in inconclusive_statuses
            or any(item.get("status") == "inconclusive" for item in critical_results)
            else "pass" if all(item["passed"] for item in critical_results) else "fail"
        )
    )
    graded["classification"] = classification
    if offline_error:
        graded["validation_errors"] = [offline_error]
    output_path.write_text(json.dumps(graded, indent=2) + "\n", encoding="utf-8")
    record = {
        "skill_name": iteration_metadata.get("skill_name"),
        "candidate_sha": iteration_metadata.get("candidate_sha"),
        "baseline_ref": iteration_metadata.get("baseline_ref"),
        "baseline_sha": iteration_metadata.get("baseline_sha"),
        "candidate_skill_hash": iteration_metadata.get("candidate_skill_hash"),
        "baseline_skill_hash": iteration_metadata.get("baseline_skill_hash"),
        "candidate_snapshot_hash": iteration_metadata.get("candidate_snapshot_hash"),
        "baseline_snapshot_hash": iteration_metadata.get("baseline_snapshot_hash"),
        "eval_manifest_hash": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "reference_date": reference_date.isoformat(),
        "eval_id": eval_id,
        "trial": int(run_dir.name.removeprefix("run-")),
        "configuration": run_dir.parent.name,
        "run_skill_hash": actual_skill_hash,
        "executor_prompt_hash": actual_prompt_hash,
        "input_manifest_hash": actual_input_manifest_hash,
        "executor": run_metadata,
        "executor_raw": load_raw_executor_metadata(outputs_dir / "executor_metadata_raw.json"),
        "inputs": input_files,
        "timing": timing,
        "outputs": file_manifest(outputs_dir),
        "grading": graded,
        "classification": classification,
    }
    (run_dir / "run_record.json").write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    return f"graded {run_dir}"


def main() -> None:
    """Entry point."""
    args = parse_args()
    messages: list[str] = []
    graded_count = 0
    skipped_count = 0

    iteration_metadata = load_json(args.iteration_dir / "iteration_manifest.json")
    for eval_id, run_dir in iter_run_dirs(args.iteration_dir):
        message = grade_run(args.evals, eval_id, run_dir, args.force, iteration_metadata)
        messages.append(message)
        if message.startswith("graded "):
            graded_count += 1
        else:
            skipped_count += 1

    for message in messages:
        print(message)
    print(f"summary: graded={graded_count} skipped={skipped_count}")


if __name__ == "__main__":
    main()
