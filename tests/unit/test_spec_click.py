"""Unit tests for specification CLI commands."""

import json
from typing import Any, Dict, List, Optional

import click
import pytest
from click.testing import CliRunner
from slcli.spec_click import (
    _build_limit,
    _build_spec_filter,
    _resolve_product_id,
    _validate_spec_required_fields,
    register_spec_commands,
)


def patch_keyring(monkeypatch: Any) -> None:
    """Patch keyring to return test values."""
    monkeypatch.setattr(
        "slcli.utils.keyring.get_password",
        lambda service, key: ("test-key" if key == "SYSTEMLINK_API_KEY" else "https://test.com"),
    )


def make_cli() -> click.Group:
    """Create CLI instance with specification commands for testing."""

    @click.group()
    def test_cli() -> None:
        pass

    register_spec_commands(test_cli)
    return test_cli


@pytest.fixture
def runner() -> CliRunner:
    """Create a CliRunner for tests."""
    return CliRunner()


class MockResponse:
    """Mock response class for requests."""

    def __init__(self, json_data: Any, status_code: int = 200, text: Optional[str] = None) -> None:
        """Initialize the mock response."""
        self._json_data = json_data
        self.status_code = status_code
        self.text = text if text is not None else json.dumps(json_data)

    def json(self) -> Any:
        """Return the JSON payload."""
        return self._json_data

    def raise_for_status(self) -> None:
        """Raise on HTTP error status."""
        if self.status_code >= 400:
            raise Exception(f"HTTP error {self.status_code}")


SAMPLE_SPEC: Dict[str, Any] = {
    "id": "spec-1",
    "productId": "product-1",
    "specId": "VSAT01",
    "name": "Saturation voltage",
    "category": "Electrical characteristics",
    "type": "PARAMETRIC",
    "symbol": "VSat",
    "block": "USB",
    "limit": {"min": 1.2, "typical": 1.5, "max": 1.8},
    "unit": "V",
    "conditions": [
        {
            "name": "Temperature",
            "value": {
                "conditionType": "NUMERIC",
                "discrete": [25.0, 85.0],
                "unit": "C",
            },
        }
    ],
    "keywords": ["datasheet", "usb"],
    "properties": {"owner": "qa"},
    "workspace": "ws-1",
    "version": 2,
}


class TestBuildLimit:
    """Tests for _build_limit."""

    def test_returns_none_when_no_values(self) -> None:
        """Test that no values returns None."""
        assert _build_limit(None, None, None) is None

    def test_builds_limit_payload(self) -> None:
        """Test that provided values are included in the limit payload."""
        assert _build_limit(1.0, 2.0, 3.0) == {"min": 1.0, "typical": 2.0, "max": 3.0}


class TestBuildSpecFilter:
    """Tests for _build_spec_filter."""

    def test_returns_none_without_filters(self) -> None:
        """Test that no filter inputs returns None."""
        assert _build_spec_filter() is None

    def test_builds_combined_filter(self) -> None:
        """Test that convenience filters are combined correctly."""
        result = _build_spec_filter(
            spec_id="VSAT01",
            name="Saturation",
            spec_type="PARAMETRIC",
            workspace="ws-1",
        )
        assert result is not None
        assert 'specId == "VSAT01"' in result
        assert 'name.Contains("Saturation")' in result
        assert 'type == "PARAMETRIC"' in result
        assert 'workspace == "ws-1"' in result
        assert " && " in result


def test_list_specifications_json(monkeypatch: Any, runner: CliRunner) -> None:
    """Test listing specifications with JSON output."""
    patch_keyring(monkeypatch)
    monkeypatch.setattr("slcli.spec_click._resolve_product_id", lambda x: x)

    captured_payloads: List[Dict[str, Any]] = []

    def mock_post(*a: Any, **kw: Any) -> Any:
        captured_payloads.append(kw.get("json", {}))
        return MockResponse({"specs": [SAMPLE_SPEC], "continuationToken": None})

    monkeypatch.setattr("requests.post", mock_post)

    cli = make_cli()
    result = runner.invoke(
        cli,
        [
            "spec",
            "list",
            "--product",
            "product-1",
            "--format",
            "json",
            "--take",
            "10",
        ],
    )

    assert result.exit_code == 0
    output_data = json.loads(result.output)
    assert len(output_data) == 1
    assert output_data[0]["specId"] == "VSAT01"
    assert captured_payloads[0]["productIds"] == ["product-1"]
    assert captured_payloads[0]["take"] == 10


def test_query_specifications_json_preserves_continuation_token(
    monkeypatch: Any, runner: CliRunner
) -> None:
    """Test raw query output includes continuation token."""
    patch_keyring(monkeypatch)
    monkeypatch.setattr("slcli.spec_click._resolve_product_id", lambda x: x)

    def mock_post(*a: Any, **kw: Any) -> Any:
        return MockResponse({"specs": [SAMPLE_SPEC], "continuationToken": "next-token"})

    monkeypatch.setattr("requests.post", mock_post)

    cli = make_cli()
    result = runner.invoke(
        cli,
        [
            "spec",
            "query",
            "--product",
            "product-1",
            "--projection",
            "ID",
            "--projection",
            "SPEC_ID",
        ],
    )

    assert result.exit_code == 0
    output_data = json.loads(result.output)
    assert output_data["continuationToken"] == "next-token"
    assert output_data["specs"][0]["id"] == "spec-1"


def test_query_specifications_applies_projection_and_client_filters(
    monkeypatch: Any, runner: CliRunner
) -> None:
    """Test raw query expands convenience projections and filters returned specs client-side."""
    patch_keyring(monkeypatch)
    monkeypatch.setattr("slcli.spec_click._resolve_product_id", lambda x: x)

    captured_payloads: List[Dict[str, Any]] = []
    other_spec = dict(SAMPLE_SPEC)
    other_spec["id"] = "spec-2"
    other_spec["specId"] = "VSAT02"
    other_spec["conditions"] = [
        {
            "name": "Mode",
            "value": {
                "conditionType": "STRING",
                "discrete": ["OFF"],
            },
        }
    ]

    def mock_post(*a: Any, **kw: Any) -> Any:
        captured_payloads.append(kw.get("json", {}))
        return MockResponse({"specs": [SAMPLE_SPEC, other_spec], "continuationToken": "next-token"})

    monkeypatch.setattr("requests.post", mock_post)

    cli = make_cli()
    result = runner.invoke(
        cli,
        [
            "spec",
            "query",
            "--product",
            "product-1",
            "--include-limits",
            "--include-conditions",
            "--condition-name",
            "temp",
            "--limit-max-le",
            "2.0",
        ],
    )

    assert result.exit_code == 0
    output_data = json.loads(result.output)
    assert len(output_data["specs"]) == 1
    assert output_data["specs"][0]["id"] == "spec-1"
    assert captured_payloads[0]["projection"] == [
        "LIMIT",
        "CONDITION_NAME",
        "CONDITION_VALUES",
        "CONDITION_UNIT",
        "CONDITION_TYPE",
    ]


def test_get_specification_json(monkeypatch: Any, runner: CliRunner) -> None:
    """Test getting a specification as JSON."""
    patch_keyring(monkeypatch)

    def mock_get(*a: Any, **kw: Any) -> Any:
        return MockResponse(SAMPLE_SPEC)

    monkeypatch.setattr("requests.get", mock_get)

    cli = make_cli()
    result = runner.invoke(cli, ["spec", "get", "--id", "spec-1", "--format", "json"])

    assert result.exit_code == 0
    output_data = json.loads(result.output)
    assert output_data["id"] == "spec-1"
    assert output_data["conditions"][0]["name"] == "Temperature"


def test_create_specification_builds_payload(monkeypatch: Any, runner: CliRunner) -> None:
    """Test creating a specification with limits, conditions, keywords, and properties."""
    patch_keyring(monkeypatch)
    monkeypatch.setattr("slcli.spec_click._resolve_product_id", lambda x: x)

    captured_payloads: List[Dict[str, Any]] = []

    def mock_post(*a: Any, **kw: Any) -> Any:
        captured_payloads.append(kw.get("json", {}))
        return MockResponse(
            {
                "createdSpecs": [
                    {
                        "id": "spec-1",
                        "specId": "VSAT01",
                        "productId": "product-1",
                        "version": 0,
                    }
                ]
            },
            status_code=201,
        )

    monkeypatch.setattr("requests.post", mock_post)
    monkeypatch.setattr("slcli.spec_click._get_product_workspace", lambda product_id: "ws-product")

    cli = make_cli()
    result = runner.invoke(
        cli,
        [
            "spec",
            "create",
            "--product",
            "product-1",
            "--spec-id",
            "VSAT01",
            "--type",
            "PARAMETRIC",
            "--name",
            "Saturation voltage",
            "--limit-min",
            "1.2",
            "--limit-max",
            "1.8",
            "--condition",
            '{"name":"Temperature","value":{"conditionType":"NUMERIC","discrete":[25],"unit":"C"}}',
            "--keyword",
            "datasheet",
            "--property",
            "owner=qa",
        ],
    )

    assert result.exit_code == 0
    request_payload = captured_payloads[0]["specs"][0]
    assert request_payload["productId"] == "product-1"
    assert request_payload["specId"] == "VSAT01"
    assert request_payload["type"] == "PARAMETRIC"
    assert request_payload["limit"] == {"min": 1.2, "max": 1.8}
    assert request_payload["conditions"][0]["name"] == "Temperature"
    assert request_payload["keywords"] == ["datasheet"]
    assert request_payload["properties"] == {"owner": "qa"}
    assert request_payload["workspace"] == "ws-product"
    assert "Specification created" in result.output


def test_create_specification_prefers_explicit_workspace_over_product_workspace(
    monkeypatch: Any, runner: CliRunner
) -> None:
    """Test explicit CLI workspace overrides the product workspace default."""
    patch_keyring(monkeypatch)
    monkeypatch.setattr("slcli.spec_click._resolve_product_id", lambda x: x)

    captured_payloads: List[Dict[str, Any]] = []

    def mock_post(*a: Any, **kw: Any) -> Any:
        captured_payloads.append(kw.get("json", {}))
        return MockResponse(
            {
                "createdSpecs": [
                    {
                        "id": "spec-1",
                        "specId": "VSAT01",
                        "productId": "product-1",
                        "version": 0,
                    }
                ]
            },
            status_code=201,
        )

    monkeypatch.setattr("requests.post", mock_post)
    monkeypatch.setattr(
        "slcli.spec_click.resolve_workspace_id", lambda workspace: f"resolved-{workspace}"
    )
    monkeypatch.setattr("slcli.spec_click._get_product_workspace", lambda product_id: "ws-product")

    cli = make_cli()
    result = runner.invoke(
        cli,
        [
            "spec",
            "create",
            "--product",
            "product-1",
            "--spec-id",
            "VSAT01",
            "--type",
            "PARAMETRIC",
            "--workspace",
            "Engineering",
        ],
    )

    assert result.exit_code == 0
    request_payload = captured_payloads[0]["specs"][0]
    assert request_payload["workspace"] == "resolved-Engineering"


def test_update_specification_builds_payload(monkeypatch: Any, runner: CliRunner) -> None:
    """Test updating a specification with versioned payload."""
    patch_keyring(monkeypatch)

    captured_payloads: List[Dict[str, Any]] = []

    def mock_post(*a: Any, **kw: Any) -> Any:
        captured_payloads.append(kw.get("json", {}))
        return MockResponse(
            {
                "updatedSpecs": [
                    {
                        "id": "spec-1",
                        "specId": "VSAT01",
                        "productId": "product-1",
                        "version": 3,
                    }
                ]
            }
        )

    monkeypatch.setattr("requests.post", mock_post)

    cli = make_cli()
    result = runner.invoke(
        cli,
        [
            "spec",
            "update",
            "--id",
            "spec-1",
            "--version",
            "2",
            "--name",
            "Updated saturation voltage",
            "--limit-typical",
            "1.5",
        ],
    )

    assert result.exit_code == 0
    request_payload = captured_payloads[0]["specs"][0]
    assert request_payload["id"] == "spec-1"
    assert request_payload["version"] == 2
    assert request_payload["name"] == "Updated saturation voltage"
    assert request_payload["limit"] == {"typical": 1.5}
    assert "Specification updated" in result.output


def test_delete_specification_builds_payload(monkeypatch: Any, runner: CliRunner) -> None:
    """Test deleting one or more specifications."""
    patch_keyring(monkeypatch)

    captured_payloads: List[Dict[str, Any]] = []

    def mock_post(*a: Any, **kw: Any) -> Any:
        captured_payloads.append(kw.get("json", {}))
        return MockResponse({"deletedSpecIds": ["spec-1", "spec-2"], "failedSpecIds": []})

    monkeypatch.setattr("requests.post", mock_post)

    cli = make_cli()
    result = runner.invoke(
        cli,
        [
            "spec",
            "delete",
            "--id",
            "spec-1",
            "--id",
            "spec-2",
            "--force",
        ],
    )

    assert result.exit_code == 0
    assert captured_payloads[0] == {"ids": ["spec-1", "spec-2"]}
    assert "Specification(s) deleted" in result.output


def test_export_specifications_writes_json_payload(monkeypatch: Any, runner: CliRunner) -> None:
    """Test exporting specifications wraps query results in a specs payload file."""
    patch_keyring(monkeypatch)
    monkeypatch.setattr("slcli.spec_click._resolve_product_id", lambda x: x)

    saved_output: Dict[str, Any] = {}

    def mock_post(*a: Any, **kw: Any) -> Any:
        return MockResponse({"specs": [SAMPLE_SPEC], "continuationToken": None})

    def mock_save_json_file(data: Any, filepath: str, custom_serializer: Any = None) -> None:
        saved_output["data"] = data
        saved_output["filepath"] = filepath

    monkeypatch.setattr("requests.post", mock_post)
    monkeypatch.setattr("slcli.spec_click.save_json_file", mock_save_json_file)

    cli = make_cli()
    result = runner.invoke(
        cli,
        [
            "spec",
            "export",
            "--product",
            "product-1",
            "--output",
            "specs.json",
        ],
    )

    assert result.exit_code == 0
    assert saved_output["filepath"] == "specs.json"
    assert saved_output["data"] == {"specs": [SAMPLE_SPEC]}
    assert "Specifications exported" in result.output


def test_import_specifications_builds_bulk_payload(monkeypatch: Any, runner: CliRunner) -> None:
    """Test importing specifications posts a bulk specs payload."""
    patch_keyring(monkeypatch)

    captured_payloads: List[Dict[str, Any]] = []

    def mock_post(*a: Any, **kw: Any) -> Any:
        captured_payloads.append(kw.get("json", {}))
        return MockResponse(
            {
                "createdSpecs": [
                    {"id": "spec-1", "specId": "VSAT01", "productId": "product-1"},
                    {"id": "spec-2", "specId": "VSAT02", "productId": "product-1"},
                ],
                "failedSpecs": [],
            },
            status_code=201,
        )

    monkeypatch.setattr("requests.post", mock_post)
    monkeypatch.setattr("slcli.spec_click._get_product_workspace", lambda product_id: "ws-product")

    cli = make_cli()
    with runner.isolated_filesystem():
        with open("import-specs.json", "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "specs": [
                        {
                            "productId": "product-1",
                            "specId": "VSAT01",
                            "type": "PARAMETRIC",
                        },
                        {
                            "productId": "product-1",
                            "specId": "VSAT02",
                            "type": "FUNCTIONAL",
                        },
                    ]
                },
                handle,
            )

        result = runner.invoke(cli, ["spec", "import", "--file", "import-specs.json"])

    assert result.exit_code == 0
    assert len(captured_payloads[0]["specs"]) == 2
    assert captured_payloads[0]["specs"][0]["specId"] == "VSAT01"
    assert captured_payloads[0]["specs"][0]["workspace"] == "ws-product"
    assert captured_payloads[0]["specs"][1]["workspace"] == "ws-product"
    assert "Specification import completed" in result.output


def test_import_specifications_preserves_workspace_in_payload(
    monkeypatch: Any, runner: CliRunner
) -> None:
    """Test import keeps an explicit payload workspace instead of inheriting from the product."""
    patch_keyring(monkeypatch)

    captured_payloads: List[Dict[str, Any]] = []

    def mock_post(*a: Any, **kw: Any) -> Any:
        captured_payloads.append(kw.get("json", {}))
        return MockResponse(
            {
                "createdSpecs": [
                    {"id": "spec-1", "specId": "VSAT01", "productId": "product-1"},
                ],
                "failedSpecs": [],
            },
            status_code=201,
        )

    monkeypatch.setattr("requests.post", mock_post)
    monkeypatch.setattr("slcli.spec_click._get_product_workspace", lambda product_id: "ws-product")
    monkeypatch.setattr(
        "slcli.spec_click.resolve_workspace_id", lambda workspace: f"resolved-{workspace}"
    )

    cli = make_cli()
    with runner.isolated_filesystem():
        with open("import-specs.json", "w", encoding="utf-8") as handle:
            json.dump(
                {
                    "specs": [
                        {
                            "productId": "product-1",
                            "specId": "VSAT01",
                            "type": "PARAMETRIC",
                            "workspace": "Engineering",
                        }
                    ]
                },
                handle,
            )

        result = runner.invoke(cli, ["spec", "import", "--file", "import-specs.json"])

    assert result.exit_code == 0
    assert captured_payloads[0]["specs"][0]["workspace"] == "resolved-Engineering"


def test_list_specifications_table_output(monkeypatch: Any, runner: CliRunner) -> None:
    """Test listing specifications renders table output via UniversalResponseHandler."""
    patch_keyring(monkeypatch)
    monkeypatch.setattr("slcli.spec_click._resolve_product_id", lambda x: x)

    def mock_post(*a: Any, **kw: Any) -> Any:
        return MockResponse({"specs": [SAMPLE_SPEC], "continuationToken": None})

    monkeypatch.setattr("requests.post", mock_post)
    monkeypatch.setattr("slcli.spec_click.get_workspace_map", lambda: {"ws-1": "Production"})
    monkeypatch.setattr(
        "slcli.spec_click._build_product_name_map",
        lambda ids: {pid: "Test Product" for pid in ids},
    )

    cli = make_cli()
    result = runner.invoke(
        cli,
        [
            "spec",
            "list",
            "--product",
            "product-1",
            "--format",
            "table",
            "--take",
            "10",
        ],
    )

    assert result.exit_code == 0
    assert "VSAT01" in result.output
    assert "Saturation voltage" in result.output
    assert "Test Product" in result.output


def test_list_specifications_invalid_take(monkeypatch: Any, runner: CliRunner) -> None:
    """Test that --take 0 exits with an error."""
    patch_keyring(monkeypatch)

    cli = make_cli()
    result = runner.invoke(
        cli,
        ["spec", "list", "--product", "product-1", "--take", "0"],
    )

    assert result.exit_code != 0
    assert "--take must be greater than 0" in result.output


def test_create_specification_missing_required_fields(monkeypatch: Any, runner: CliRunner) -> None:
    """Test creating a specification without required fields exits with an error."""
    patch_keyring(monkeypatch)
    monkeypatch.setattr("slcli.spec_click._resolve_product_id", lambda x: x)

    cli = make_cli()
    result = runner.invoke(
        cli,
        ["spec", "create", "--product", "product-1"],
    )

    assert result.exit_code != 0
    assert "Missing required fields" in result.output


def test_create_specification_invalid_condition_json(monkeypatch: Any, runner: CliRunner) -> None:
    """Test creating a specification with malformed --condition JSON exits with an error."""
    patch_keyring(monkeypatch)
    monkeypatch.setattr("slcli.spec_click._resolve_product_id", lambda x: x)

    cli = make_cli()
    result = runner.invoke(
        cli,
        [
            "spec",
            "create",
            "--product",
            "product-1",
            "--spec-id",
            "VSAT01",
            "--type",
            "PARAMETRIC",
            "--condition",
            "not-valid-json",
        ],
    )

    assert result.exit_code != 0
    assert "Invalid JSON for --condition" in result.output


def test_get_specification_table_output(monkeypatch: Any, runner: CliRunner) -> None:
    """Test getting a specification in table format renders detail view."""
    patch_keyring(monkeypatch)

    def mock_get(*a: Any, **kw: Any) -> Any:
        return MockResponse(SAMPLE_SPEC)

    monkeypatch.setattr("requests.get", mock_get)
    monkeypatch.setattr("slcli.spec_click.get_workspace_map", lambda: {"ws-1": "Production"})

    cli = make_cli()
    result = runner.invoke(cli, ["spec", "get", "--id", "spec-1", "--format", "table"])

    assert result.exit_code == 0
    assert "VSAT01" in result.output
    assert "Temperature" in result.output
    assert "datasheet" in result.output


def test_delete_specification_reports_failures(monkeypatch: Any, runner: CliRunner) -> None:
    """Test deleting specifications reports partial failures."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        return MockResponse(
            {"deletedSpecIds": [], "failedSpecIds": ["spec-1"]},
        )

    monkeypatch.setattr("requests.post", mock_post)

    cli = make_cli()
    result = runner.invoke(
        cli,
        ["spec", "delete", "--id", "spec-1", "--force"],
    )

    assert result.exit_code != 0
    assert "Failed to delete" in result.output


# ---------------------------------------------------------------------------
# _resolve_product_id tests
# ---------------------------------------------------------------------------

SAMPLE_PRODUCT: Dict[str, Any] = {
    "id": "c81ab7f0-0f90-4b2f-be2c-5cb2c65cc105",
    "name": "Stereo Audio Amplifier",
    "partNumber": "TPA3139D2.v1",
    "family": "Audio",
    "workspace": "ws-1",
}


def test_resolve_product_id_by_uuid(monkeypatch: Any) -> None:
    """Test that a valid UUID resolves via direct GET."""
    patch_keyring(monkeypatch)

    def mock_get(*a: Any, **kw: Any) -> Any:
        return MockResponse(SAMPLE_PRODUCT)

    monkeypatch.setattr("requests.get", mock_get)

    result = _resolve_product_id("c81ab7f0-0f90-4b2f-be2c-5cb2c65cc105")
    assert result == "c81ab7f0-0f90-4b2f-be2c-5cb2c65cc105"


def test_resolve_product_id_by_name(monkeypatch: Any) -> None:
    """Test that a product name resolves via query-products."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        payload = kw.get("json", {})
        if payload.get("filter") == "name == @0":
            return MockResponse({"products": [SAMPLE_PRODUCT]})
        return MockResponse({"products": []})

    monkeypatch.setattr("requests.post", mock_post)

    result = _resolve_product_id("Stereo Audio Amplifier")
    assert result == "c81ab7f0-0f90-4b2f-be2c-5cb2c65cc105"


def test_resolve_product_id_by_part_number(monkeypatch: Any) -> None:
    """Test that a part number resolves via query-products when name doesn't match."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        payload = kw.get("json", {})
        if payload.get("filter") == "partNumber == @0":
            return MockResponse({"products": [SAMPLE_PRODUCT]})
        return MockResponse({"products": []})

    monkeypatch.setattr("requests.post", mock_post)

    result = _resolve_product_id("TPA3139D2.v1")
    assert result == "c81ab7f0-0f90-4b2f-be2c-5cb2c65cc105"


def test_resolve_product_id_not_found(monkeypatch: Any) -> None:
    """Test that an unrecognized identifier exits with NOT_FOUND."""
    patch_keyring(monkeypatch)

    def mock_post(*a: Any, **kw: Any) -> Any:
        return MockResponse({"products": []})

    monkeypatch.setattr("requests.post", mock_post)

    with pytest.raises(SystemExit) as exc_info:
        _resolve_product_id("NonexistentProduct")
    assert exc_info.value.code == 3  # ExitCodes.NOT_FOUND


def test_resolve_product_id_ambiguous(monkeypatch: Any) -> None:
    """Test that multiple matching products exits with INVALID_INPUT."""
    patch_keyring(monkeypatch)

    product_a = dict(SAMPLE_PRODUCT)
    product_b = dict(SAMPLE_PRODUCT)
    product_b["id"] = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee"
    product_b["partNumber"] = "TPA3139D2.v2"

    def mock_post(*a: Any, **kw: Any) -> Any:
        return MockResponse({"products": [product_a, product_b]})

    monkeypatch.setattr("requests.post", mock_post)

    with pytest.raises(SystemExit) as exc_info:
        _resolve_product_id("Stereo Audio Amplifier")
    assert exc_info.value.code == 2  # ExitCodes.INVALID_INPUT


def test_validate_spec_required_fields_version_zero() -> None:
    """Test that version=0 is treated as a valid (present) value."""
    # Should NOT raise for version=0 (falsy but valid)
    spec_data: Dict[str, Any] = {"id": "123", "version": 0}
    _validate_spec_required_fields(spec_data, ["id", "version"])


def test_validate_spec_required_fields_missing() -> None:
    """Test that truly missing fields are caught."""
    spec_data: Dict[str, Any] = {"id": "123"}
    with pytest.raises(SystemExit):
        _validate_spec_required_fields(spec_data, ["id", "version"])
