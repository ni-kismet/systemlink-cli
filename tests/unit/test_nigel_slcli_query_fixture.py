"""Contract tests for the Nigel slcli query fixture."""

import json
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from slcli.example_loader import ExampleLoader


def test_nigel_fixture_declares_deterministic_core_resources() -> None:
    """The fixture keeps its supported core inventory and incomplete contract stable."""
    config = ExampleLoader().load_config("nigel-slcli-query-fixture")
    resources = config["resources"]
    counts = Counter(resource["type"] for resource in resources)

    assert config["install_manifest"] is True
    assert config["example_version"] == "1.2.0"
    assert counts["system"] == 5
    assert counts["asset"] + counts["dut"] == 6
    assert counts["product"] == 2
    assert counts["feed"] == 1
    assert counts["state"] == 1
    assert counts["tag"] == 1
    tag = next(resource for resource in resources if resource["type"] == "tag")
    history = tag["properties"]["history"]
    assert len(history) == 12
    assert history[0] == {"timestamp": "2026-08-05T12:00:00Z", "value": 21.0}
    assert history[-1] == {"timestamp": "2026-08-05T12:55:00Z", "value": 22.1}
    assert counts["specification"] == 1
    assert counts["test_result"] == 12
    assert counts["data_table"] == 3
    assert counts["file"] == 2
    specification = next(resource for resource in resources if resource["type"] == "specification")
    conditions = specification["properties"]["conditions"]
    assert len(conditions) == 5
    assert {condition["name"] for condition in conditions} == {
        "Overvoltage margin at high temperature",
        "Leakage current at 5 V standby",
        "Cold-start response time",
        "Nominal output voltage",
        "Thermal shutdown behavior",
    }
    data_tables = [resource for resource in resources if resource["type"] == "data_table"]
    assert {table["properties"]["rows_file"] for table in data_tables} == {
        "overvoltage-results.json",
        "leakage-current-results.json",
        "thermal-response-results.json",
    }
    fixture_dir = Path(__file__).resolve().parents[2] / "slcli" / "examples" / config["name"]
    analysis_start = datetime(2025, 1, 1, tzinfo=timezone.utc)
    analysis_end = datetime(2025, 6, 30, 23, 59, 59, tzinfo=timezone.utc)
    for table in data_tables:
        rows_path = fixture_dir / table["properties"]["rows_file"]
        assert rows_path.exists()
        rows_config = json.loads(rows_path.read_text(encoding="utf-8"))
        assert rows_config["frame"]["columns"] == [
            column["name"] for column in table["properties"]["columns"]
        ]
        rows = rows_config["frame"]["data"]
        assert len(rows) >= 12
        assert {row[-1] for row in rows} == {"PASS", "FAIL"}
        timestamps = []
        for row in rows:
            timestamps.append(datetime.fromisoformat(row[0].replace("Z", "+00:00")))
        assert all(analysis_start <= timestamp <= analysis_end for timestamp in timestamps)
    unsupported = config["validation"]["unsupported"]
    assert not any("populated DataFrame rows" in item for item in unsupported)
    assert any("specification condition evidence" in item for item in unsupported)
    assert len(config["validation"]["required_relationships"]) >= 5
    assert config["validation"]["unsupported"]

    resource_references = {resource["id_reference"] for resource in resources}
    assert "system_pxi_rack_07" in resource_references
    assert "asset_dmm_pxi4071" in resource_references
    assert "result_tr_xyz_traceability" in resource_references


def test_nigel_fixture_compliance_report_references_fixture_results() -> None:
    """Compliance evidence IDs must resolve to fixture result references."""
    config = ExampleLoader().load_config("nigel-slcli-query-fixture")
    resource_references = {resource["id_reference"] for resource in config["resources"]}
    report_path = (
        Path(__file__).resolve().parents[2]
        / "slcli"
        / "examples"
        / "nigel-slcli-query-fixture"
        / "product-xyz-compliance-report.json"
    )
    report = json.loads(report_path.read_text(encoding="utf-8"))
    evidence_references = {evidence_id for gap in report["gaps"] for evidence_id in gap["evidence"]}

    assert evidence_references <= resource_references
