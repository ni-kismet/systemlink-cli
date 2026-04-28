"""E2E tests for dataframe commands against configured tiers."""

import json
import subprocess
import time
import uuid
from pathlib import Path
from typing import Any, Dict

import pytest

_DATAFRAME_AVAILABLE: bool | None = None
_DATAFRAME_SKIP_REASON: str | None = None


def _write_json(path: Path, payload: Dict[str, Any]) -> None:
    """Write a JSON payload to disk for CLI file-based commands."""
    path.write_text(json.dumps(payload), encoding="utf-8")


def _probe_name() -> str:
    """Return a unique list filter that should never match existing tables."""
    return f"slcli-e2e-probe-{uuid.uuid4().hex}"


def _resolve_table_id(
    cli_runner: Any, cli_helper: Any, table_name: str, workspace_name: str
) -> str:
    """Find a table ID by name with a short retry window for eventual consistency."""
    max_attempts = 5
    for attempt in range(max_attempts):
        result = cli_runner(
            [
                "dataframe",
                "list",
                "--name",
                table_name,
                "--workspace",
                workspace_name,
                "--format",
                "json",
                "--take",
                "25",
            ],
            check=False,
        )
        if result.returncode == 0:
            payload = cli_helper.get_json_output(result)
            table = cli_helper.find_resource_by_name(payload.get("tables", []), table_name)
            if table and table.get("id"):
                return str(table["id"])

        if attempt < max_attempts - 1:
            time.sleep(0.5 * (2**attempt))

    pytest.fail(f"DataFrame table '{table_name}' was not visible after creation")


def _wait_for_query_rows(cli_runner: Any, cli_helper: Any, table_id: str) -> Dict[str, Any]:
    """Wait until appended rows are queryable for the target table."""
    for attempt in range(5):
        result = cli_runner(
            ["dataframe", "query", table_id, "--format", "json", "--take", "10"],
            check=False,
        )
        if result.returncode == 0:
            payload = cli_helper.get_json_output(result)
            frame = payload.get("frame", {}) or {}
            if frame.get("data"):
                return payload

        if attempt < 4:
            time.sleep(0.5 * (2**attempt))

    pytest.fail(f"Appended rows for dataframe table '{table_id}' were not queryable in time")


@pytest.fixture
def require_dataframe_service(cli_runner: Any) -> None:
    """Skip dataframe E2E tests when the backend is unavailable on the selected tier."""
    global _DATAFRAME_AVAILABLE, _DATAFRAME_SKIP_REASON

    if _DATAFRAME_AVAILABLE is True:
        return
    if _DATAFRAME_AVAILABLE is False:
        pytest.skip(_DATAFRAME_SKIP_REASON or "DataFrame service is not available")

    try:
        result = cli_runner(["dataframe", "list", "--format", "table", "--take", "1"], check=False)
    except subprocess.TimeoutExpired:
        _DATAFRAME_AVAILABLE = False
        _DATAFRAME_SKIP_REASON = "DataFrame service probe timed out on the selected E2E target"
        pytest.skip(_DATAFRAME_SKIP_REASON)

    if result.returncode == 0:
        _DATAFRAME_AVAILABLE = True
        _DATAFRAME_SKIP_REASON = None
        return

    output = f"{result.stdout}\n{result.stderr}".lower()
    if "404" in output or "not found" in output or "nidataframe" in output:
        _DATAFRAME_AVAILABLE = False
        _DATAFRAME_SKIP_REASON = "DataFrame service is not available on the selected E2E target"
        pytest.skip(_DATAFRAME_SKIP_REASON)

    pytest.fail(
        "DataFrame availability probe failed unexpectedly\n"
        f"STDOUT: {result.stdout}\nSTDERR: {result.stderr}"
    )


@pytest.mark.e2e
@pytest.mark.dataframe
@pytest.mark.usefixtures("require_dataframe_service")
class TestDataframeE2E:
    """End-to-end tests for dataframe commands."""

    def test_dataframe_list_basic(
        self, cli_runner: Any, cli_helper: Any, configured_workspace: str
    ) -> None:
        """Ensure dataframe list returns the expected JSON shape."""
        probe_name = _probe_name()
        result = cli_runner(
            [
                "dataframe",
                "list",
                "--name",
                probe_name,
                "--workspace",
                configured_workspace,
                "--format",
                "json",
                "--take",
                "5",
            ]
        )
        cli_helper.assert_success(result)

        payload = cli_helper.get_json_output(result)
        assert isinstance(payload, dict)
        assert "tables" in payload
        assert isinstance(payload["tables"], list)
        assert "continuationToken" in payload

    def test_dataframe_lifecycle(
        self, cli_runner: Any, cli_helper: Any, configured_workspace: str, tmp_path: Path
    ) -> None:
        """Create, inspect, append, query, export, update, and delete a dataframe table."""
        unique_id = uuid.uuid4().hex[:8]
        table_name = f"e2e-dataframe-{unique_id}"
        definition_path = tmp_path / "table.json"
        append_path = tmp_path / "append.json"
        export_path = tmp_path / "rows.csv"
        table_id = ""

        _write_json(
            definition_path,
            {
                "name": table_name,
                "columns": [
                    {"name": "Time", "dataType": "TIMESTAMP", "columnType": "INDEX"},
                    {"name": "Voltage", "dataType": "FLOAT64", "columnType": "NORMAL"},
                    {"name": "State", "dataType": "STRING", "columnType": "NORMAL"},
                ],
                "properties": {"owner": "e2e", "suite": "dataframe"},
            },
        )
        _write_json(
            append_path,
            {
                "frame": {
                    "columns": ["Time", "Voltage", "State"],
                    "data": [
                        ["2026-04-28T00:00:00.000Z", "5.01", "PASS"],
                        ["2026-04-28T00:00:01.000Z", "4.72", "FAIL"],
                    ],
                }
            },
        )

        try:
            create_result = cli_runner(
                [
                    "dataframe",
                    "create",
                    "--definition",
                    str(definition_path),
                    "--workspace",
                    configured_workspace,
                    "--format",
                    "json",
                ]
            )
            cli_helper.assert_success(create_result)
            created = cli_helper.get_json_output(create_result)
            table_id = str(created.get("id") or "")
            if not table_id:
                table_id = _resolve_table_id(
                    cli_runner, cli_helper, table_name, configured_workspace
                )

            get_result = cli_runner(["dataframe", "get", table_id, "--format", "json"])
            cli_helper.assert_success(get_result)
            table_data = cli_helper.get_json_output(get_result)
            assert table_data.get("id") == table_id
            assert table_data.get("name") == table_name

            schema_result = cli_runner(["dataframe", "schema", table_id, "--format", "json"])
            cli_helper.assert_success(schema_result)
            schema = cli_helper.get_json_output(schema_result)
            assert isinstance(schema, list)
            assert any(column.get("columnType") == "INDEX" for column in schema)
            assert [column.get("name") for column in schema] == ["Time", "Voltage", "State"]

            append_result = cli_runner(
                ["dataframe", "append", table_id, "--input", str(append_path)]
            )
            cli_helper.assert_success(append_result)
            assert "Dataframe rows appended" in append_result.stdout

            queried = _wait_for_query_rows(cli_runner, cli_helper, table_id)
            assert queried.get("totalRowCount", 0) >= 2

            fail_query_result = cli_runner(
                [
                    "dataframe",
                    "query",
                    table_id,
                    "--columns",
                    "Time,Voltage,State",
                    "--where",
                    "State,EQUALS,FAIL",
                    "--format",
                    "json",
                ]
            )
            cli_helper.assert_success(fail_query_result)
            fail_rows = cli_helper.get_json_output(fail_query_result)
            assert fail_rows.get("frame", {}).get("columns") == ["Time", "Voltage", "State"]
            assert len(fail_rows.get("frame", {}).get("data", [])) >= 1

            export_result = cli_runner(
                ["dataframe", "export", table_id, "--output", str(export_path)]
            )
            cli_helper.assert_success(export_result)
            assert export_path.exists()
            exported_csv = export_path.read_text(encoding="utf-8")
            assert "Time" in exported_csv
            assert "Voltage" in exported_csv
            assert "FAIL" in exported_csv

            update_result = cli_runner(
                [
                    "dataframe",
                    "update",
                    table_id,
                    "--property",
                    "owner=qa",
                    "--column-property",
                    "Voltage:units=V",
                ]
            )
            cli_helper.assert_success(update_result)

            updated_get_result = cli_runner(["dataframe", "get", table_id, "--format", "json"])
            cli_helper.assert_success(updated_get_result)
            updated = cli_helper.get_json_output(updated_get_result)
            assert updated.get("properties", {}).get("owner") == "qa"
            voltage_column = next(
                (
                    column
                    for column in updated.get("columns", [])
                    if column.get("name") == "Voltage"
                ),
                None,
            )
            assert voltage_column is not None
            assert voltage_column.get("properties", {}).get("units") == "V"

            delete_result = cli_runner(["dataframe", "delete", table_id, "--yes"])
            cli_helper.assert_success(delete_result)
            deleted_table_id = table_id
            table_id = ""

            missing_result = cli_runner(
                ["dataframe", "get", deleted_table_id, "--format", "json"],
                check=False,
            )
            cli_helper.assert_failure(missing_result)

        finally:
            if table_id:
                cli_runner(["dataframe", "delete", table_id, "--yes"], check=False)
