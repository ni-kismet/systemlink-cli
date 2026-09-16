"""Load normalized command execution records from eval artifacts."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterable

RECORD_FILE_NAME = "execution_records.json"


def _record_path(response_path: Path) -> Path:
    """Return the execution record path for a response artifact."""
    return (
        response_path / RECORD_FILE_NAME
        if response_path.is_dir()
        else response_path.parent / RECORD_FILE_NAME
    )


def _parse_stdout_json(record: dict[str, Any]) -> Any:
    """Use explicit parsed output or decode a JSON stdout string."""
    if "stdout_json" in record:
        return record["stdout_json"]
    stdout = record.get("stdout")
    if not isinstance(stdout, str) or not stdout.strip():
        return None
    try:
        return json.loads(stdout)
    except json.JSONDecodeError:
        return None


def normalize_record(record: dict[str, Any]) -> dict[str, Any]:
    """Validate and normalize one command execution record."""
    command = record.get("command")
    if not isinstance(command, str) or not command.strip():
        raise ValueError("execution records require a non-empty command")
    exit_code = record.get("exit_code")
    if exit_code is not None and (not isinstance(exit_code, int) or isinstance(exit_code, bool)):
        raise ValueError("execution record exit_code must be an integer or null")
    duration = record.get("duration_seconds")
    if duration is not None and (
        not isinstance(duration, (int, float)) or isinstance(duration, bool) or duration < 0
    ):
        raise ValueError("execution record duration_seconds must be nonnegative")
    normalized = {
        "command": command,
        "exit_code": exit_code,
        "stdout": record.get("stdout", ""),
        "stderr": record.get("stderr", ""),
        "stdout_json": _parse_stdout_json(record),
        "duration_seconds": duration,
        "status": record.get("status", "completed" if exit_code == 0 else "command_error"),
        "api_error": record.get("api_error"),
    }
    if not isinstance(normalized["stdout"], str) or not isinstance(normalized["stderr"], str):
        raise ValueError("execution record stdout and stderr must be strings")
    return normalized


def load_execution_records(
    response_path: Path, fallback_commands: Iterable[str]
) -> tuple[list[dict[str, Any]], list[str]]:
    """Load explicit records or create unavailable records from response commands."""
    path = _record_path(response_path)
    if not path.is_file():
        return [
            {
                "command": command,
                "exit_code": None,
                "stdout": "",
                "stderr": "",
                "stdout_json": None,
                "duration_seconds": None,
                "status": "unavailable",
                "api_error": None,
            }
            for command in fallback_commands
        ], []
    payload = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(payload, dict):
        payload = payload.get("records")
    if not isinstance(payload, list):
        raise ValueError("execution_records.json must contain a list or a records object")
    records = [normalize_record(record) for record in payload if isinstance(record, dict)]
    if len(records) != len(payload):
        raise ValueError("execution records must be JSON objects")
    return records, [str(path)]
