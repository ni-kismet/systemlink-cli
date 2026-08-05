"""Contract tests for the Nigel slcli query fixture."""

from collections import Counter

from slcli.example_loader import ExampleLoader


def test_nigel_fixture_declares_deterministic_core_resources() -> None:
    """The fixture keeps its supported core inventory and incomplete contract stable."""
    config = ExampleLoader().load_config("nigel-slcli-query-fixture")
    resources = config["resources"]
    counts = Counter(resource["type"] for resource in resources)

    assert config["install_manifest"] is True
    assert config["example_version"] == "1.0.0"
    assert counts["system"] == 5
    assert counts["asset"] + counts["dut"] == 6
    assert counts["product"] == 2
    assert counts["feed"] == 1
    assert counts["state"] == 1
    assert counts["tag"] == 1
    assert counts["specification"] == 1
    assert counts["test_result"] == 12
    assert counts["data_table"] == 3
    assert counts["file"] == 2
    assert len(config["validation"]["required_relationships"]) >= 5
    assert config["validation"]["unsupported"]

    resource_references = {resource["id_reference"] for resource in resources}
    assert "system_pxi_rack_07" in resource_references
    assert "asset_dmm_pxi4071" in resource_references
    assert "result_tr_xyz_traceability" in resource_references
