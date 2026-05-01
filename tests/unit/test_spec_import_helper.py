"""Unit tests for the datasheet spec import helper."""

from __future__ import annotations

from typing import Any

from slcli.skills.slcli.scripts.spec_import_helper import validate_payload


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
