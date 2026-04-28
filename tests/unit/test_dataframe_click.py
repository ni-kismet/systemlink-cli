"""Unit tests for dataframe CLI commands."""

import json
from typing import Any, Dict, List, Optional

import click
import pytest
from click.testing import CliRunner

from slcli.dataframe_click import register_dataframe_commands


def patch_keyring(monkeypatch: Any) -> None:
    """Patch keyring to return test credentials."""
    monkeypatch.setattr(
        "slcli.utils.keyring.get_password",
        lambda service, key: "test-key" if key == "SYSTEMLINK_API_KEY" else "https://test.com",
    )


def make_cli() -> click.Group:
    """Create a CLI with the dataframe command group registered."""

    @click.group()
    def test_cli() -> None:
        pass

    register_dataframe_commands(test_cli)
    return test_cli


@pytest.fixture
def runner() -> CliRunner:
    return CliRunner()


class MockResponse:
    """Mock requests-style response for CLI unit tests."""

    def __init__(
        self,
        json_data: Any = None,
        status_code: int = 200,
        text_data: Optional[str] = None,
    ) -> None:
        """Initialize a mock response payload and status code."""
        self._json_data = json_data
        self.status_code = status_code
        if text_data is not None:
            self.text = text_data
        elif json_data is None:
            self.text = ""
        else:
            self.text = json.dumps(json_data)

    def json(self) -> Any:
        return self._json_data

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise Exception(f"HTTP error {self.status_code}")


def test_dataframe_list_builds_filters(monkeypatch: Any, runner: CliRunner) -> None:
    """Test list filter building, substitution offsets, and JSON output."""
    patch_keyring(monkeypatch)
    captured_payloads: List[Dict[str, Any]] = []

    def mock_request(
        method: str,
        url: str,
        payload: Optional[Dict[str, Any]] = None,
        **_: Any,
    ) -> Any:
        if payload is not None:
            captured_payloads.append(payload)
        return MockResponse(
            {
                "tables": [
                    {
                        "id": "tbl-1",
                        "name": "Voltage Log",
                        "workspace": "ws-1",
                        "rowCount": 42,
                        "supportsAppend": True,
                    }
                ],
                "continuationToken": None,
            }
        )

    monkeypatch.setattr("slcli.dataframe_click.make_api_request", mock_request)
    monkeypatch.setattr("slcli.dataframe_click.get_workspace_map", lambda: {"ws-1": "Dev"})

    cli = make_cli()
    result = runner.invoke(
        cli,
        [
            "dataframe",
            "list",
            "--name",
            "Voltage",
            "--workspace",
            "Dev",
            "--supports-append",
            "--filter",
            'properties["tester"] == @0',
            "--substitution",
            '"12"',
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0
    output = json.loads(result.output)
    assert output["tables"][0]["id"] == "tbl-1"
    assert captured_payloads
    payload = captured_payloads[0]
    assert "name.Contains(@0)" in payload["filter"]
    assert "supportsAppend == @1" in payload["filter"]
    assert "workspace == @2" in payload["filter"]
    assert 'properties["tester"] == @3' in payload["filter"]
    assert payload["substitutions"] == ["Voltage", True, "ws-1", "12"]


def test_dataframe_schema_table_output(monkeypatch: Any, runner: CliRunner) -> None:
    """Test schema command table output."""
    patch_keyring(monkeypatch)

    def mock_request(method: str, url: str, **_: Any) -> Any:
        return MockResponse(
            {
                "id": "tbl-1",
                "columns": [
                    {"name": "Time", "dataType": "TIMESTAMP", "columnType": "INDEX"},
                    {"name": "Voltage", "dataType": "FLOAT64", "columnType": "NORMAL"},
                ],
            }
        )

    monkeypatch.setattr("slcli.dataframe_click.make_api_request", mock_request)

    cli = make_cli()
    result = runner.invoke(cli, ["dataframe", "schema", "tbl-1"])

    assert result.exit_code == 0
    assert "Time" in result.output
    assert "TIMESTAMP" in result.output
    assert "Voltage" in result.output


def test_dataframe_get_json_output(monkeypatch: Any, runner: CliRunner) -> None:
    """Test get command JSON output."""
    patch_keyring(monkeypatch)
    calls: List[Dict[str, str]] = []

    def mock_request(method: str, url: str, **_: Any) -> Any:
        calls.append({"method": method, "url": url})
        return MockResponse(
            {
                "id": "tbl-1",
                "name": "Voltage Log",
                "workspace": "ws-1",
                "rowCount": 42,
                "columns": [{"name": "Time", "dataType": "TIMESTAMP", "columnType": "INDEX"}],
            }
        )

    monkeypatch.setattr("slcli.dataframe_click.make_api_request", mock_request)
    monkeypatch.setattr("slcli.dataframe_click.get_base_url", lambda: "https://test.com")

    cli = make_cli()
    result = runner.invoke(cli, ["dataframe", "get", "tbl-1", "--format", "json"])

    assert result.exit_code == 0
    assert calls == [{"method": "GET", "url": "https://test.com/nidataframe/v1/tables/tbl-1"}]
    output = json.loads(result.output)
    assert output["id"] == "tbl-1"
    assert output["columns"][0]["name"] == "Time"


def test_dataframe_get_table_output_includes_schema_preview(
    monkeypatch: Any, runner: CliRunner
) -> None:
    """Test get command table output includes a schema preview."""
    patch_keyring(monkeypatch)

    def mock_request(method: str, url: str, **_: Any) -> Any:
        return MockResponse(
            {
                "id": "tbl-1",
                "name": "Voltage Log",
                "workspace": "ws-1",
                "rowCount": 42,
                "supportsAppend": True,
                "columns": [
                    {"name": "Time", "dataType": "TIMESTAMP", "columnType": "INDEX"},
                    {"name": "Voltage", "dataType": "FLOAT64", "columnType": "NORMAL"},
                ],
            }
        )

    monkeypatch.setattr("slcli.dataframe_click.make_api_request", mock_request)
    monkeypatch.setattr("slcli.dataframe_click.get_workspace_map", lambda: {"ws-1": "Dev"})

    cli = make_cli()
    result = runner.invoke(cli, ["dataframe", "get", "tbl-1"])

    assert result.exit_code == 0
    assert "DataFrame Table" in result.output
    assert "Voltage Log" in result.output
    assert "Schema" in result.output
    assert "Time" in result.output
    assert "Voltage" in result.output


def test_dataframe_query_builds_payload(monkeypatch: Any, runner: CliRunner) -> None:
    """Test query payload construction from shorthand flags."""
    patch_keyring(monkeypatch)
    captured_payloads: List[Dict[str, Any]] = []

    def mock_request(
        method: str,
        url: str,
        payload: Optional[Dict[str, Any]] = None,
        **_: Any,
    ) -> Any:
        if payload is not None:
            captured_payloads.append(payload)
        return MockResponse(
            {
                "frame": {
                    "columns": ["Time", "Voltage"],
                    "data": [["2026-04-27T10:00:00.000Z", "5.01"]],
                },
                "totalRowCount": 1,
                "continuationToken": None,
            }
        )

    monkeypatch.setattr("slcli.dataframe_click.make_api_request", mock_request)

    cli = make_cli()
    result = runner.invoke(
        cli,
        [
            "dataframe",
            "query",
            "tbl-1",
            "--columns",
            "Time,Voltage",
            "--where",
            "State,EQUALS,FAIL",
            "--order-by",
            "Time:desc",
            "--take",
            "50",
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0
    payload = captured_payloads[0]
    assert payload["columns"] == ["Time", "Voltage"]
    assert payload["filters"] == [{"column": "State", "operation": "EQUALS", "value": "FAIL"}]
    assert payload["orderBy"] == [{"column": "Time", "descending": True}]
    assert payload["take"] == 50


def test_dataframe_query_request_preserves_file_take(monkeypatch: Any, runner: CliRunner) -> None:
    """Test raw query request files are not overridden by default take."""
    patch_keyring(monkeypatch)
    captured_payloads: List[Dict[str, Any]] = []

    def mock_request(
        method: str,
        url: str,
        payload: Optional[Dict[str, Any]] = None,
        **_: Any,
    ) -> Any:
        if payload is not None:
            captured_payloads.append(payload)
        return MockResponse({"frame": {"columns": ["Time"], "data": [["1"]]}})

    monkeypatch.setattr("slcli.dataframe_click.make_api_request", mock_request)

    cli = make_cli()
    with runner.isolated_filesystem():
        with open("query.json", "w", encoding="utf-8") as query_file:
            json.dump(
                {
                    "take": 250,
                    "filters": [{"column": "State", "operation": "EQUALS", "value": "FAIL"}],
                },
                query_file,
            )

        result = runner.invoke(
            cli,
            ["dataframe", "query", "tbl-1", "--request", "query.json", "--format", "json"],
        )

    assert result.exit_code == 0
    assert captured_payloads[0]["take"] == 250


def test_dataframe_query_rejects_invalid_filter_operation(
    monkeypatch: Any, runner: CliRunner
) -> None:
    """Test invalid row filter operations exit with invalid input."""
    patch_keyring(monkeypatch)

    cli = make_cli()
    result = runner.invoke(
        cli,
        ["dataframe", "query", "tbl-1", "--where", "State,INVALID,FAIL", "--format", "json"],
    )

    assert result.exit_code == 2
    assert "Unsupported filter operation 'INVALID'" in result.output


def test_dataframe_export_writes_csv(monkeypatch: Any, runner: CliRunner) -> None:
    """Test CSV export to an output file."""
    patch_keyring(monkeypatch)

    def mock_request(method: str, url: str, **_: Any) -> Any:
        return MockResponse(text_data='"Voltage","State"\n"5.01","PASS"\n')

    monkeypatch.setattr("slcli.dataframe_click.make_api_request", mock_request)

    cli = make_cli()
    with runner.isolated_filesystem():
        result = runner.invoke(
            cli,
            ["dataframe", "export", "tbl-1", "--output", "rows.csv"],
        )
        assert result.exit_code == 0
        with open("rows.csv", "r", encoding="utf-8") as exported:
            assert exported.read() == '"Voltage","State"\n"5.01","PASS"\n'


def test_dataframe_create_uses_definition_and_workspace(
    monkeypatch: Any, runner: CliRunner
) -> None:
    """Test table creation with definition override and workspace resolution."""
    patch_keyring(monkeypatch)
    captured_payloads: List[Dict[str, Any]] = []

    def mock_request(
        method: str,
        url: str,
        payload: Optional[Dict[str, Any]] = None,
        **_: Any,
    ) -> Any:
        if payload is not None:
            captured_payloads.append(payload)
        return MockResponse({"id": "tbl-created"})

    monkeypatch.setattr("slcli.dataframe_click.make_api_request", mock_request)
    monkeypatch.setattr("slcli.dataframe_click.get_workspace_map", lambda: {"ws-1": "Dev"})

    cli = make_cli()
    with runner.isolated_filesystem():
        with open("definition.json", "w", encoding="utf-8") as definition_file:
            json.dump(
                {
                    "columns": [
                        {"name": "Time", "dataType": "TIMESTAMP", "columnType": "INDEX"},
                        {"name": "Voltage", "dataType": "FLOAT64"},
                    ]
                },
                definition_file,
            )

        result = runner.invoke(
            cli,
            [
                "dataframe",
                "create",
                "--definition",
                "definition.json",
                "--name",
                "Voltage Log",
                "--workspace",
                "Dev",
                "--format",
                "json",
            ],
        )

        assert result.exit_code == 0
        assert captured_payloads[0]["name"] == "Voltage Log"
        assert captured_payloads[0]["workspace"] == "ws-1"


def test_dataframe_update_builds_patch(monkeypatch: Any, runner: CliRunner) -> None:
    """Test metadata update payload construction."""
    patch_keyring(monkeypatch)
    captured_payloads: List[Dict[str, Any]] = []

    def mock_request(
        method: str,
        url: str,
        payload: Optional[Dict[str, Any]] = None,
        **_: Any,
    ) -> Any:
        if payload is not None:
            captured_payloads.append(payload)
        return MockResponse(status_code=204, text_data="")

    monkeypatch.setattr("slcli.dataframe_click.make_api_request", mock_request)

    cli = make_cli()
    result = runner.invoke(
        cli,
        [
            "dataframe",
            "update",
            "tbl-1",
            "--property",
            "team=qa",
            "--remove-property",
            "obsolete",
            "--column-property",
            "Voltage:units=V",
            "--remove-column-property",
            "Voltage:alias",
            "--metadata-revision",
            "4",
        ],
    )

    assert result.exit_code == 0
    payload = captured_payloads[0]
    assert payload["properties"] == {"team": "qa", "obsolete": None}
    assert payload["columns"] == [{"name": "Voltage", "properties": {"units": "V", "alias": None}}]
    assert payload["metadataRevision"] == 4


def test_dataframe_delete_multiple_uses_batch_endpoint(monkeypatch: Any, runner: CliRunner) -> None:
    """Test multi-delete routing to the batch endpoint."""
    patch_keyring(monkeypatch)
    calls: List[Dict[str, Any]] = []

    def mock_request(
        method: str,
        url: str,
        payload: Optional[Dict[str, Any]] = None,
        **_: Any,
    ) -> Any:
        calls.append({"method": method, "url": url, "payload": payload})
        return MockResponse(status_code=204, text_data="")

    monkeypatch.setattr("slcli.dataframe_click.make_api_request", mock_request)

    cli = make_cli()
    result = runner.invoke(cli, ["dataframe", "delete", "tbl-1", "tbl-2", "--yes"])

    assert result.exit_code == 0
    assert calls[0]["method"] == "POST"
    assert calls[0]["payload"] == {"ids": ["tbl-1", "tbl-2"]}


def test_dataframe_append_arrow_uses_binary_request(monkeypatch: Any, runner: CliRunner) -> None:
    """Test Arrow append path with raw binary request."""
    patch_keyring(monkeypatch)
    captured_request: Dict[str, Any] = {}

    def mock_post(url: str, headers: Dict[str, str], data: Any, verify: bool) -> Any:
        captured_request["url"] = url
        captured_request["headers"] = headers
        captured_request["data"] = data.read()
        captured_request["verify"] = verify
        return MockResponse(status_code=204, text_data="")

    monkeypatch.setattr("slcli.dataframe_click.requests_lib.post", mock_post)

    cli = make_cli()
    with runner.isolated_filesystem():
        with open("rows.arrow", "wb") as arrow_file:
            arrow_file.write(b"arrow-data")

        result = runner.invoke(
            cli,
            [
                "dataframe",
                "append",
                "tbl-1",
                "--input",
                "rows.arrow",
                "--input-format",
                "arrow",
                "--end-of-data",
            ],
        )

        assert result.exit_code == 0
        assert captured_request["url"].endswith("/tables/tbl-1/data?endOfData=true")
        assert captured_request["headers"]["Content-Type"] == "application/vnd.apache.arrow.stream"
        assert captured_request["data"] == b"arrow-data"


def test_dataframe_append_uses_click_path_validation(monkeypatch: Any, runner: CliRunner) -> None:
    """Test append rejects missing input paths before issuing any request."""
    patch_keyring(monkeypatch)

    def fail_request(*args: Any, **kwargs: Any) -> Any:
        raise AssertionError("append should not issue a request for an invalid input path")

    monkeypatch.setattr("slcli.dataframe_click.make_api_request", fail_request)

    cli = make_cli()
    result = runner.invoke(cli, ["dataframe", "append", "tbl-1", "--input", "missing.json"])

    assert result.exit_code == 2
    assert "does not exist" in result.output


def test_dataframe_decimate_builds_payload(monkeypatch: Any, runner: CliRunner) -> None:
    """Test decimation request payload construction."""
    patch_keyring(monkeypatch)
    captured_payloads: List[Dict[str, Any]] = []

    def mock_request(
        method: str,
        url: str,
        payload: Optional[Dict[str, Any]] = None,
        **_: Any,
    ) -> Any:
        if payload is not None:
            captured_payloads.append(payload)
        return MockResponse({"frame": {"columns": ["Time"], "data": [["1"]]}})

    monkeypatch.setattr("slcli.dataframe_click.make_api_request", mock_request)

    cli = make_cli()
    result = runner.invoke(
        cli,
        [
            "dataframe",
            "decimate",
            "tbl-1",
            "--x-column",
            "Time",
            "--y-column",
            "Voltage",
            "--intervals",
            "25",
            "--method",
            "MAX_MIN",
            "--distribution",
            "EQUAL_WIDTH",
            "--format",
            "json",
        ],
    )

    assert result.exit_code == 0
    payload = captured_payloads[0]
    assert payload["decimation"] == {
        "intervals": 25,
        "xColumn": "Time",
        "yColumns": ["Voltage"],
        "method": "MAX_MIN",
        "distribution": "EQUAL_WIDTH",
    }


def test_dataframe_decimate_request_preserves_file_intervals(
    monkeypatch: Any, runner: CliRunner
) -> None:
    """Test raw decimation request files are not overridden by default intervals."""
    patch_keyring(monkeypatch)
    captured_payloads: List[Dict[str, Any]] = []

    def mock_request(
        method: str,
        url: str,
        payload: Optional[Dict[str, Any]] = None,
        **_: Any,
    ) -> Any:
        if payload is not None:
            captured_payloads.append(payload)
        return MockResponse({"frame": {"columns": ["Time"], "data": [["1"]]}})

    monkeypatch.setattr("slcli.dataframe_click.make_api_request", mock_request)

    cli = make_cli()
    with runner.isolated_filesystem():
        with open("decimate.json", "w", encoding="utf-8") as decimate_file:
            json.dump(
                {
                    "decimation": {
                        "intervals": 25,
                        "xColumn": "Time",
                        "yColumns": ["Voltage"],
                    }
                },
                decimate_file,
            )

        result = runner.invoke(
            cli,
            [
                "dataframe",
                "decimate",
                "tbl-1",
                "--request",
                "decimate.json",
                "--format",
                "json",
            ],
        )

    assert result.exit_code == 0
    assert captured_payloads[0]["decimation"]["intervals"] == 25


def test_dataframe_update_many_posts_definition(monkeypatch: Any, runner: CliRunner) -> None:
    """Test batch metadata update routing to modify-tables."""
    patch_keyring(monkeypatch)
    captured_payloads: List[Dict[str, Any]] = []

    def mock_request(
        method: str,
        url: str,
        payload: Optional[Dict[str, Any]] = None,
        **_: Any,
    ) -> Any:
        if payload is not None:
            captured_payloads.append(payload)
        return MockResponse(status_code=204, text_data="")

    monkeypatch.setattr("slcli.dataframe_click.make_api_request", mock_request)

    cli = make_cli()
    with runner.isolated_filesystem():
        with open("modify.json", "w", encoding="utf-8") as modify_file:
            json.dump({"tables": [{"id": "tbl-1", "properties": {"team": "qa"}}]}, modify_file)

        result = runner.invoke(
            cli,
            ["dataframe", "update-many", "--definition", "modify.json"],
        )

        assert result.exit_code == 0
        assert captured_payloads[0] == {"tables": [{"id": "tbl-1", "properties": {"team": "qa"}}]}


def test_dataframe_update_many_partial_success_exits_with_error(
    monkeypatch: Any, runner: CliRunner
) -> None:
    """Test batch update partial success reports failures and exits nonzero."""
    patch_keyring(monkeypatch)

    def mock_request(method: str, url: str, **_: Any) -> Any:
        return MockResponse(
            {
                "modifiedTableIds": ["tbl-1"],
                "failedModifications": [{"tableId": "tbl-2"}],
                "error": {"message": "metadata revision conflict"},
            }
        )

    monkeypatch.setattr("slcli.dataframe_click.make_api_request", mock_request)

    cli = make_cli()
    with runner.isolated_filesystem():
        with open("modify.json", "w", encoding="utf-8") as modify_file:
            json.dump({"tables": [{"id": "tbl-1"}, {"id": "tbl-2"}]}, modify_file)

        result = runner.invoke(cli, ["dataframe", "update-many", "--definition", "modify.json"])

    assert result.exit_code == 1
    assert "Failed modifications: 1" in result.output
    assert "metadata revision conflict" in result.output


def test_dataframe_delete_partial_success_exits_with_error(
    monkeypatch: Any, runner: CliRunner
) -> None:
    """Test batch delete partial success reports failed IDs and exits nonzero."""
    patch_keyring(monkeypatch)

    def mock_request(method: str, url: str, **_: Any) -> Any:
        return MockResponse(
            {
                "deletedTableIds": ["tbl-1"],
                "failedTableIds": ["tbl-2"],
                "error": {"message": "table is locked"},
            }
        )

    monkeypatch.setattr("slcli.dataframe_click.make_api_request", mock_request)

    cli = make_cli()
    result = runner.invoke(cli, ["dataframe", "delete", "tbl-1", "tbl-2", "--yes"])

    assert result.exit_code == 1
    assert "Failed to delete: tbl-2" in result.output
    assert "table is locked" in result.output
