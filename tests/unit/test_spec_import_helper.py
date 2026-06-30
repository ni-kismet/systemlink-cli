"""Unit tests for the datasheet spec import helper."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from slcli.skills.slcli.scripts.spec_import_helper import main, validate_payload


def make_spec(**overrides: Any) -> dict[str, Any]:
    """Build a valid baseline spec payload for tests."""
    spec: dict[str, Any] = {
        "productId": "product-1",
        "workspace": "workspace-1",
        "specId": "VSAT01",
        "type": "PARAMETRIC",
        "limit": {"max": 1.5},
    }
    spec.update(overrides)
    return spec


def test_validate_payload_reports_required_fields() -> None:
    """Test that missing required spec fields are reported."""
    errors = validate_payload({"specs": [{"workspace": "workspace-1"}]})

    assert "specs[0].productId is required" in errors
    assert "specs[0].specId is required" in errors
    assert "specs[0].type is required" in errors


def test_validate_payload_scopes_duplicate_detection_by_product_and_workspace() -> None:
    """Test that duplicate detection is scoped to product and workspace."""
    valid_payload = {
        "specs": [
            make_spec(specId="ICC"),
            make_spec(specId="ICC", workspace="workspace-2"),
            make_spec(specId="ICC", productId="product-2"),
            make_spec(specId="ICC", workspace=""),
        ]
    }

    assert validate_payload(valid_payload) == []

    duplicate_errors = validate_payload(
        {
            "specs": [
                make_spec(specId="ICC"),
                make_spec(specId="ICC"),
            ]
        }
    )

    assert len(duplicate_errors) == 1
    assert "duplicate spec for productId 'product-1'" in duplicate_errors[0]
    assert "specId 'ICC'" in duplicate_errors[0]


def test_validate_payload_requires_limit_for_parametric_specs() -> None:
    """Test that PARAMETRIC specs require at least one limit bound."""
    errors = validate_payload(
        {
            "specs": [
                make_spec(limit={}),
                make_spec(specId="IDD", limit={"max": "high"}),
                make_spec(specId="VOUT", limit=None),
            ]
        }
    )

    assert "specs[0].limit must include at least one of min, typical, or max" in errors
    assert "specs[1].limit.max must be numeric" in errors
    assert "specs[2].limit must be an object" in errors


def test_validate_payload_rejects_invalid_numeric_conditions() -> None:
    """Test that NUMERIC conditions require numeric discrete values."""
    errors = validate_payload(
        {
            "specs": [
                make_spec(
                    conditions=[
                        {
                            "name": "Temperature",
                            "value": {
                                "conditionType": "NUMERIC",
                                "discrete": [25, "hot"],
                                "unit": "C",
                            },
                        }
                    ]
                )
            ]
        }
    )

    assert "specs[0].conditions[0].value.discrete[1] must be numeric" in errors


def test_validate_payload_rejects_invalid_string_conditions() -> None:
    """Test that STRING conditions reject ranges and blank discrete values."""
    errors = validate_payload(
        {
            "specs": [
                make_spec(
                    conditions=[
                        {
                            "name": "Mode",
                            "value": {
                                "conditionType": "STRING",
                                "range": [{"min": 1}],
                                "discrete": [""],
                            },
                        }
                    ]
                )
            ]
        }
    )

    assert "specs[0].conditions[0].value.range is invalid for STRING conditions" in errors
    assert "specs[0].conditions[0].value.discrete[0] must be a non-empty string" in errors


def test_validate_payload_rejects_invalid_root_shapes() -> None:
    """Test that invalid payload roots and specs containers are rejected."""
    assert validate_payload([]) == ["payload root must be an object"]
    assert validate_payload({"specs": {}}) == ["payload.specs must be a list"]


def test_validate_payload_reports_additional_shape_errors() -> None:
    """Test that malformed specs and conditions report detailed validation errors."""
    errors = validate_payload(
        {
            "specs": [
                "not-an-object",
                {
                    "productId": "product-1",
                    "specId": "BADTYPE",
                    "type": "UNKNOWN",
                    "conditions": "invalid",
                },
                {
                    "productId": "product-1",
                    "specId": "COND-1",
                    "type": "PARAMETRIC",
                    "limit": {"min": True},
                    "conditions": [
                        None,
                        {"name": "", "value": None},
                        {"name": "Mode", "value": {"conditionType": "BOOLEAN"}},
                        {
                            "name": "Temperature",
                            "value": {
                                "conditionType": "NUMERIC",
                                "range": [{}, {"min": "cold"}, 3],
                            },
                        },
                        {
                            "name": "State",
                            "value": {"conditionType": "STRING"},
                        },
                    ],
                },
            ]
        }
    )

    assert "specs[0] must be an object" in errors
    assert "specs[1].type must be one of ['FUNCTIONAL', 'PARAMETRIC']" in errors
    assert "specs[1].conditions must be a list" in errors
    assert "specs[2].limit.min must be numeric" in errors
    assert "specs[2].conditions[0] must be an object" in errors
    assert "specs[2].conditions[1].name must be a non-empty string" in errors
    assert "specs[2].conditions[1].value must be an object" in errors
    assert (
        "specs[2].conditions[2].value.conditionType must be one of ['NUMERIC', 'STRING']"
        in errors
    )
    assert "specs[2].conditions[3].value.range[0] must include min or max" in errors
    assert "specs[2].conditions[3].value.range[1].min must be numeric" in errors
    assert "specs[2].conditions[3].value.range[2] must be an object" in errors
    assert "specs[2].conditions[4].value must include discrete or range" in errors


def test_main_init_writes_starter_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test that the init command writes a substituted starter payload."""
    output_path = tmp_path / "starter.json"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "spec_import_helper.py",
            "init",
            "--output",
            str(output_path),
            "--product-id",
            "product-42",
            "--workspace",
            "workspace-42",
            "--source",
            "device.pdf",
        ],
    )

    exit_code = main()

    assert exit_code == 0
    payload = json.loads(output_path.read_text(encoding="utf-8"))
    assert payload["specs"][0]["productId"] == "product-42"
    assert payload["specs"][0]["workspace"] == "workspace-42"
    assert payload["specs"][0]["properties"]["source"] == "device.pdf"
    captured = capsys.readouterr()
    assert f"Wrote starter payload to {output_path}" in captured.out


def test_main_validate_reports_success_for_valid_payload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test that the validate command reports success for a valid payload."""
    payload_path = tmp_path / "valid.json"
    payload_path.write_text(json.dumps({"specs": [make_spec()]}) + "\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["spec_import_helper.py", "validate", str(payload_path)])

    exit_code = main()

    assert exit_code == 0
    captured = capsys.readouterr()
    assert "Payload valid: 1 specs" in captured.out


def test_main_validate_reports_invalid_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test that the validate command reports invalid JSON input."""
    payload_path = tmp_path / "invalid.json"
    payload_path.write_text("{not-json}\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["spec_import_helper.py", "validate", str(payload_path)])

    exit_code = main()

    assert exit_code == 1
    captured = capsys.readouterr()
    assert f"Invalid JSON in {payload_path}:" in captured.err


def test_main_validate_reports_missing_file(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test that the validate command reports a missing payload file."""
    payload_path = tmp_path / "missing.json"
    monkeypatch.setattr(sys, "argv", ["spec_import_helper.py", "validate", str(payload_path)])

    exit_code = main()

    assert exit_code == 1
    captured = capsys.readouterr()
    assert f"File not found: {payload_path}" in captured.err


def test_main_validate_reports_validation_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    """Test that the validate command prints discovered payload validation errors."""
    payload_path = tmp_path / "invalid-payload.json"
    payload_path.write_text(json.dumps({"specs": [{"workspace": "ws-1"}]}) + "\n", encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["spec_import_helper.py", "validate", str(payload_path)])

    exit_code = main()

    assert exit_code == 1
    captured = capsys.readouterr()
    assert f"Validation failed for {payload_path}:" in captured.err
    assert "- specs[0].productId is required" in captured.err
