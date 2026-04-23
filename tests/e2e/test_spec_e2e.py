"""E2E tests for specification commands against dev tier."""

import json
import os
import tempfile
import uuid
from typing import Any, Dict, List, Optional

import pytest


def _find_spec_by_spec_id(
    specifications: List[Dict[str, Any]], spec_id: str
) -> Optional[Dict[str, Any]]:
    """Find a specification by specId in a list response."""
    return next((item for item in specifications if item.get("specId") == spec_id), None)


@pytest.mark.e2e
@pytest.mark.sle
@pytest.mark.usefixtures("require_sle")
class TestSpecificationE2E:
    """End-to-end tests for specification commands on SLE."""

    def test_spec_lifecycle_export_import(
        self, sle_cli_runner: Any, sle_cli_helper: Any, sle_workspace: str
    ) -> None:
        """Create, update, export, import, and delete specifications for a temporary product."""
        unique = uuid.uuid4().hex[:8]
        product_id: Optional[str] = None
        created_spec_ids: List[str] = []
        export_path: Optional[str] = None

        part_number = f"E2E-SPEC-PN-{unique}"
        product_name = f"e2e-spec-product-{unique}"
        spec_id = f"E2E_SPEC_{unique}"
        imported_spec_id = f"E2E_SPEC_IMPORT_{unique}"
        initial_name = f"E2E Spec {unique}"
        updated_name = f"E2E Updated Spec {unique}"

        try:
            create_product = sle_cli_runner(
                [
                    "testmonitor",
                    "product",
                    "create",
                    "--part-number",
                    part_number,
                    "--name",
                    product_name,
                    "--workspace",
                    sle_workspace,
                    "--format",
                    "json",
                ],
                check=False,
            )
            if "readonly" in create_product.stderr.lower():
                pytest.skip("Profile is in readonly mode")
            sle_cli_helper.assert_success(create_product)
            product = sle_cli_helper.get_json_output(create_product)
            product_id = product.get("id")
            assert product_id, "Created product missing ID"

            create_spec = sle_cli_runner(
                [
                    "spec",
                    "create",
                    "--product",
                    product_id,
                    "--spec-id",
                    spec_id,
                    "--name",
                    initial_name,
                    "--category",
                    "Electrical characteristics",
                    "--type",
                    "PARAMETRIC",
                    "--symbol",
                    "VSat",
                    "--block",
                    "USB",
                    "--unit",
                    "V",
                    "--workspace",
                    sle_workspace,
                    "--limit-min",
                    "1.2",
                    "--limit-max",
                    "1.8",
                    "--condition",
                    '{"name":"Temperature","value":{"conditionType":"NUMERIC","discrete":[25,85],"unit":"C"}}',
                    "--keyword",
                    "e2e",
                    "--property",
                    f"testRun={unique}",
                ],
                check=False,
            )
            sle_cli_helper.assert_success(create_spec, "Specification created")

            list_result = sle_cli_runner(
                [
                    "spec",
                    "list",
                    "--product",
                    product_id,
                    "--spec-id",
                    spec_id,
                    "--format",
                    "json",
                    "--take",
                    "10",
                ]
            )
            specifications = sle_cli_helper.get_json_output(list_result)
            assert isinstance(specifications, list)
            created_spec = _find_spec_by_spec_id(specifications, spec_id)
            assert created_spec is not None, f"Specification '{spec_id}' not found after creation"

            created_spec_id = created_spec.get("id")
            created_version = created_spec.get("version")
            assert created_spec_id, "Created specification missing ID"
            assert isinstance(created_version, int), "Created specification missing version"
            created_spec_ids.append(created_spec_id)

            get_result = sle_cli_runner(
                ["spec", "get", "--id", created_spec_id, "--format", "json"]
            )
            fetched = sle_cli_helper.get_json_output(get_result)
            assert fetched.get("id") == created_spec_id
            assert fetched.get("name") == initial_name
            assert fetched.get("limit", {}).get("max") == 1.8

            update_result = sle_cli_runner(
                [
                    "spec",
                    "update",
                    "--id",
                    created_spec_id,
                    "--version",
                    str(created_version),
                    "--name",
                    updated_name,
                    "--limit-typical",
                    "1.5",
                ],
                check=False,
            )
            sle_cli_helper.assert_success(update_result, "Specification updated")

            get_updated = sle_cli_runner(
                ["spec", "get", "--id", created_spec_id, "--format", "json"]
            )
            updated_spec = sle_cli_helper.get_json_output(get_updated)
            assert updated_spec.get("name") == updated_name
            assert updated_spec.get("limit", {}).get("typical") == 1.5

            with tempfile.NamedTemporaryFile(suffix=".json", delete=False) as export_file:
                export_path = export_file.name

            export_result = sle_cli_runner(
                [
                    "spec",
                    "export",
                    "--product",
                    product_id,
                    "--spec-id",
                    spec_id,
                    "--projection",
                    "PRODUCT_ID",
                    "--projection",
                    "SPEC_ID",
                    "--projection",
                    "NAME",
                    "--projection",
                    "CATEGORY",
                    "--projection",
                    "TYPE",
                    "--projection",
                    "SYMBOL",
                    "--projection",
                    "BLOCK",
                    "--projection",
                    "UNIT",
                    "--include-limits",
                    "--include-conditions",
                    "--output",
                    export_path,
                ],
                check=False,
            )
            sle_cli_helper.assert_success(export_result, "Specifications exported")

            with open(export_path, encoding="utf-8") as export_handle:
                exported_payload = json.load(export_handle)

            exported_specs = exported_payload.get("specs", [])
            assert len(exported_specs) == 1
            assert exported_specs[0].get("specId") == spec_id

            exported_specs[0]["specId"] = imported_spec_id
            exported_specs[0]["name"] = f"Imported {updated_name}"

            with open(export_path, "w", encoding="utf-8") as export_handle:
                json.dump(exported_payload, export_handle, indent=2)

            import_result = sle_cli_runner(["spec", "import", "--file", export_path], check=False)
            sle_cli_helper.assert_success(import_result, "Specification import completed")

            imported_list = sle_cli_runner(
                [
                    "spec",
                    "list",
                    "--product",
                    product_id,
                    "--spec-id",
                    imported_spec_id,
                    "--format",
                    "json",
                    "--take",
                    "10",
                ]
            )
            imported_specs = sle_cli_helper.get_json_output(imported_list)
            imported_spec = _find_spec_by_spec_id(imported_specs, imported_spec_id)
            assert (
                imported_spec is not None
            ), f"Imported specification '{imported_spec_id}' not found"

            imported_id = imported_spec.get("id")
            assert imported_id, "Imported specification missing ID"
            created_spec_ids.append(imported_id)

        finally:
            for created_spec_id in reversed(created_spec_ids):
                sle_cli_runner(
                    ["spec", "delete", "--id", created_spec_id, "--force"],
                    check=False,
                )

            if product_id:
                sle_cli_runner(
                    ["testmonitor", "product", "delete", product_id, "--yes"],
                    check=False,
                )

            if export_path and os.path.exists(export_path):
                os.unlink(export_path)
