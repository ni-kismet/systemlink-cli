"""E2E tests for example provisioning workflows against SLE."""

import uuid
from pathlib import Path
from typing import Any

import pytest
import yaml  # type: ignore


@pytest.mark.e2e
@pytest.mark.sle
@pytest.mark.asset
def test_external_fixture_install_delete_round_trip(
    cli_runner: Any,
    cli_helper: Any,
    configured_workspace: str,
    require_sle: None,
    tmp_path: Path,
) -> None:
    """An external fixture config installs and deletes the same calibrated asset."""
    unique_id = uuid.uuid4().hex
    fixture_name = f"slcli-e2e-fixture-{unique_id}"
    config_path = tmp_path / "config.yaml"
    config = {
        "format_version": "1.0",
        "name": f"fixture-e2e-{unique_id}",
        "title": "Fixture E2E",
        "resources": [
            {
                "type": "fixture",
                "name": fixture_name,
                "id_reference": "fixture_under_test",
                "properties": {
                    "serial_number": unique_id,
                    "model_name": "slcli E2E Fixture",
                    "vendor_name": "NI",
                    "supports_external_calibration": True,
                    "location": {"physical_location": "slcli E2E Lab"},
                    "external_calibration": {
                        # The service requires a non-empty array although OpenAPI marks it nullable.
                        "temperature_sensors": [{"name": "ambient", "reading": 23.0}],
                        "date": "2026-01-01T00:00:00Z",
                        "recommended_interval": 12,
                        "next_recommended_date": "2027-01-01T00:00:00Z",
                        "entry_type": "MANUAL",
                    },
                },
                "tags": ["slcli-e2e"],
            }
        ],
        "cleanup": {"order": ["fixture"], "filter_tags": ["slcli-e2e"]},
    }
    config_path.write_text(yaml.safe_dump(config), encoding="utf-8")

    try:
        install_result = cli_runner(
            [
                "example",
                "install",
                "--file",
                str(config_path),
                "--workspace",
                configured_workspace,
                "--format",
                "json",
            ]
        )
        cli_helper.assert_success(install_result)
        install_output = cli_helper.get_json_output(install_result)
        assert install_output[0]["action"] == "created"
    finally:
        delete_result = cli_runner(
            [
                "example",
                "delete",
                "--file",
                str(config_path),
                "--workspace",
                configured_workspace,
                "--format",
                "json",
            ]
        )

    cli_helper.assert_success(delete_result)
    delete_output = cli_helper.get_json_output(delete_result)
    assert delete_output[0]["action"] == "deleted"
