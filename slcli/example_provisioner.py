"""Provision SLE resources from example configurations.

Implements resource provisioning with real API calls to SystemLink Enterprise.
Supports dry-run mode for validation without creating resources.
"""

from __future__ import annotations

import json as json_module
from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

import click
import requests

from .utils import get_base_url, get_headers, make_api_request


class ProvisioningAction(Enum):
    """Type of action taken by the provisioner."""

    CREATED = "created"
    SKIPPED = "skipped"
    FAILED = "failed"
    DELETED = "deleted"


@dataclass
class ProvisioningResult:
    """Result of provisioning a single resource.

    Attributes:
        id_reference: Local identifier defined in config (e.g., "sys_ts1").
        resource_type: Resource type (location, product, system, asset, dut, testtemplate).
        resource_name: Human-readable name.
        action: Action taken (created/skipped/failed).
        server_id: Simulated server ID for created resource.
        error: Error message if provisioning failed.
    """

    id_reference: str
    resource_type: str
    resource_name: str
    action: ProvisioningAction
    server_id: Optional[str] = None
    error: Optional[str] = None


class ExampleProvisioner:
    """Provision resources to SLE.

    Provides dry-run mode to validate and plan without creating resources.
    Tags resources with example name for cleanup.
    """

    def __init__(
        self,
        workspace_id: Optional[str] = None,
        example_name: Optional[str] = None,
        dry_run: bool = False,
    ) -> None:
        """Initialize the provisioner.

        Args:
            workspace_id: Workspace identifier (ID).
            example_name: Example name for tagging resources.
            dry_run: When True, does not create any resources (SKIPPED).
        """
        self.workspace_id = workspace_id
        self.example_name = example_name
        self.dry_run = dry_run
        self.id_map: Dict[str, str] = {}
        self._test_results_deleted: bool = False
        self._files_deleted: bool = False
        self._notebooks_deleted: bool = False

    def provision(
        self, config: Dict[str, Any]
    ) -> Tuple[List[ProvisioningResult], Optional[Exception]]:
        """Provision all resources in the provided config.

        Args:
            config: Validated example config.

        Returns:
            Tuple of (list of provisioning results, optional error).
        """
        results: List[ProvisioningResult] = []
        self.id_map = {}  # Reset id_map for each provision run

        resources = config.get("resources", [])
        if not isinstance(resources, list):
            return [], ValueError("Config 'resources' must be a list")

        try:
            for resource in resources:
                if not isinstance(resource, dict):
                    res = ProvisioningResult(
                        id_reference=str(resource),
                        resource_type="unknown",
                        resource_name="unknown",
                        action=ProvisioningAction.FAILED,
                        error="Resource definition must be a dict",
                    )
                    results.append(res)
                    continue

                res = self._provision_resource(resource, self.id_map)
                results.append(res)

                # Record server_id for reference substitution in subsequent resources
                if res.action == ProvisioningAction.CREATED and res.server_id:
                    self.id_map[res.id_reference] = res.server_id
                elif res.action == ProvisioningAction.SKIPPED:
                    # Use actual server_id if available, otherwise use dryrun marker
                    if res.server_id:
                        self.id_map[res.id_reference] = res.server_id
                    else:
                        # Even in dry-run, populate a predictable simulated ID to enable
                        # reference substitution demonstrations in logs/tests.
                        self.id_map[res.id_reference] = f"dryrun-{res.id_reference}"

            return results, None
        except Exception as exc:  # pragma: no cover - defensive catch
            return results, exc

    def delete(
        self, config: Dict[str, Any], filter_tags: Optional[List[str]] = None
    ) -> Tuple[List[ProvisioningResult], Optional[Exception]]:
        """Delete all resources defined in the provided config.

        Deletes in reverse provisioning order (last created, first deleted).

        Args:
            config: Validated example config.

        Returns:
            Tuple of (list of deletion results, optional error).
        """
        results: List[ProvisioningResult] = []

        resources = config.get("resources", [])
        if not isinstance(resources, list):
            return [], ValueError("Config 'resources' must be a list")

        # Reset per-run flags
        self._test_results_deleted = False
        self._files_deleted = False
        self._notebooks_deleted = False

        try:
            for resource in reversed([r for r in resources if isinstance(r, dict)]):
                rtype = str(resource.get("type", "unknown"))
                rname = str(resource.get("name", "unknown"))
                rid = str(resource.get("id_reference", rname or rtype))
                rtags = resource.get("tags", [])
                if not isinstance(rtags, list):
                    rtags = []

                # Apply tag filter: skip resources that do not match filter tags
                if filter_tags:
                    matches = any(tag in rtags for tag in filter_tags)
                    if not matches:
                        results.append(
                            ProvisioningResult(
                                id_reference=rid,
                                resource_type=rtype,
                                resource_name=rname,
                                action=ProvisioningAction.SKIPPED,
                                error="tag-filter",
                            )
                        )
                        continue

                if self.dry_run:
                    results.append(
                        ProvisioningResult(
                            id_reference=rid,
                            resource_type=rtype,
                            resource_name=rname,
                            action=ProvisioningAction.SKIPPED,
                            server_id=None,
                        )
                    )
                    continue

                # Dispatch to delete method
                delete_map = {
                    "location": self._delete_location,
                    "product": self._delete_product,
                    "system": self._delete_system,
                    "asset": self._delete_asset,
                    "dut": self._delete_dut,
                    "testtemplate": self._delete_testtemplate,
                    "workflow": self._delete_workflow,
                    "work_item": self._delete_work_item,
                    "work_order": self._delete_work_order,
                    "test_result": self._delete_test_result,
                    "data_table": self._delete_data_table,
                    "file": self._delete_file,
                    "notebook": self._delete_notebook,
                }
                delete_fn = delete_map.get(rtype)
                if not delete_fn:
                    results.append(
                        ProvisioningResult(
                            id_reference=rid,
                            resource_type=rtype,
                            resource_name=rname,
                            action=ProvisioningAction.FAILED,
                            error=f"Unsupported resource type: {rtype}",
                        )
                    )
                    continue

                server_id = delete_fn({"name": rname})
                # Determine action: DELETED if successful, SKIPPED if not found
                action = ProvisioningAction.DELETED if server_id else ProvisioningAction.SKIPPED
                results.append(
                    ProvisioningResult(
                        id_reference=rid,
                        resource_type=rtype,
                        resource_name=rname,
                        action=action,
                        server_id=server_id,
                    )
                )

            return results, None
        except Exception as exc:  # pragma: no cover - defensive catch
            return results, exc

    def _provision_resource(
        self, resource_def: Dict[str, Any], id_map: Dict[str, str]
    ) -> ProvisioningResult:
        """Provision a single resource.

        Substitutes ${ref} in properties using id_map built from previous creations.
        """
        rtype = str(resource_def.get("type", "unknown"))
        rname = str(resource_def.get("name", "unknown"))
        rid = str(resource_def.get("id_reference", rname or rtype))
        properties = resource_def.get("properties", {})

        # Substitute ${ref} tokens in properties with server IDs
        props_sub = self._resolve_props(properties, id_map)

        if self.dry_run:
            return ProvisioningResult(
                id_reference=rid,
                resource_type=rtype,
                resource_name=rname,
                action=ProvisioningAction.SKIPPED,
                server_id=None,
            )

        # Dispatch to create method
        create_map = {
            "location": self._create_location,
            "product": self._create_product,
            "system": self._create_system,
            "asset": self._create_asset,
            "dut": self._create_dut,
            "testtemplate": self._create_testtemplate,
            "workflow": self._create_workflow,
            "work_item": self._create_work_item,
            "work_order": self._create_work_order,
            "test_result": self._create_test_result,
            "data_table": self._create_data_table,
            "file": self._create_file,
            "notebook": self._create_notebook,
        }

        create_fn = create_map.get(rtype)
        if not create_fn:
            return ProvisioningResult(
                id_reference=rid,
                resource_type=rtype,
                resource_name=rname,
                action=ProvisioningAction.FAILED,
                error=f"Unsupported resource type: {rtype}",
            )

        try:
            # Add name to props for creation
            props_with_name = dict(props_sub)
            props_with_name["name"] = rname

            # Check if resource already exists to avoid duplicates
            existing_id = None
            if rtype == "location":
                existing_id = self._get_location_by_name(rname)
            elif rtype == "product":
                existing_id = self._get_product_by_name(rname)
            elif rtype == "system":
                existing_id = self._get_system_by_name(rname)
            elif rtype == "asset":
                existing_id = self._get_asset_by_name(rname)
            elif rtype == "dut":
                existing_id = self._get_dut_by_name(rname)
            elif rtype == "testtemplate":
                existing_id = self._get_testtemplate_by_name(rname)
            elif rtype == "workflow":
                existing_id = self._get_workflow_by_name(rname)
            elif rtype == "work_item":
                existing_id = self._get_work_item_by_name(rname)
            elif rtype == "work_order":
                existing_id = self._get_work_order_by_name(rname)
            elif rtype == "test_result":
                existing_id = self._get_test_result_by_name(rname)
            elif rtype == "data_table":
                existing_id = self._get_data_table_by_name(rname)
            elif rtype == "file":
                existing_id = self._get_file_by_name(rname)

            if existing_id:
                # Resource already exists, skip creation
                return ProvisioningResult(
                    id_reference=rid,
                    resource_type=rtype,
                    resource_name=rname,
                    action=ProvisioningAction.SKIPPED,
                    server_id=existing_id,
                    error="Resource already exists",
                )

            server_id = create_fn(props_with_name)
            # Check for duplicate marker from create functions
            if server_id and server_id.startswith("__DUPLICATE_ID__"):
                # Extract actual ID from marker (e.g., "__DUPLICATE_ID__<uuid>" -> "<uuid>")
                actual_id = server_id.replace("__DUPLICATE_ID__", "", 1)
                return ProvisioningResult(
                    id_reference=rid,
                    resource_type=rtype,
                    resource_name=rname,
                    action=ProvisioningAction.SKIPPED,
                    server_id=actual_id,
                    error="Resource already exists (duplicate)",
                )
            elif server_id and server_id.startswith("__DUPLICATE__"):
                # Duplicate detected but ID not found
                return ProvisioningResult(
                    id_reference=rid,
                    resource_type=rtype,
                    resource_name=rname,
                    action=ProvisioningAction.SKIPPED,
                    server_id=None,
                    error="Resource already exists (duplicate)",
                )
            # Only mark as CREATED if server_id is valid
            if server_id:
                return ProvisioningResult(
                    id_reference=rid,
                    resource_type=rtype,
                    resource_name=rname,
                    action=ProvisioningAction.CREATED,
                    server_id=server_id,
                )
            else:
                # Creation returned no valid ID - could be duplicate or actual failure
                return ProvisioningResult(
                    id_reference=rid,
                    resource_type=rtype,
                    resource_name=rname,
                    action=ProvisioningAction.FAILED,
                    server_id=None,
                    error="Creation failed: no valid ID returned",
                )
        except Exception as exc:
            # Try to extract error details from response
            error_msg = str(exc)
            if hasattr(exc, "response") and exc.response is not None:  # type: ignore
                try:
                    error_body = exc.response.json()  # type: ignore
                    if "error" in error_body:
                        error_msg = f"{error_msg}: {error_body['error']}"
                    elif "message" in error_body:
                        error_msg = f"{error_msg}: {error_body['message']}"
                except Exception:
                    pass

            return ProvisioningResult(
                id_reference=rid,
                resource_type=rtype,
                resource_name=rname,
                action=ProvisioningAction.FAILED,
                error=error_msg,
            )

    def _resolve_props(self, obj: Any, id_map: Dict[str, str]) -> Any:
        """Resolve ${ref} tokens recursively in a properties object.

        Args:
            obj: Properties object (dict, list, str, etc.).
            id_map: Map of id_reference to server_id.
        """
        if isinstance(obj, dict):
            return {k: self._resolve_props(v, id_map) for k, v in obj.items()}
        if isinstance(obj, list):
            return [self._resolve_props(v, id_map) for v in obj]
        if isinstance(obj, str) and obj.startswith("${") and obj.endswith("}"):
            ref = obj[2:-1]
            return id_map.get(ref, obj)  # leave as-is if not yet defined
        return obj

    # --- Create methods (real API calls) ---
    def _create_location(self, props: Dict[str, Any]) -> str:
        """Create location via /nilocation/v1/locations API and return server ID."""
        url = f"{get_base_url()}/nilocation/v1/locations"
        payload = {"name": props.get("name", "Unknown Location")}

        # Add workspace if available
        if self.workspace_id:
            payload["workspace"] = self.workspace_id

        # Copy optional fields from CreateLocationRequest schema
        for key in [
            "type",
            "enabled",
            "description",
            "parentId",
            "scanCode",
            "properties",
            "keywords",
        ]:
            if key in props:
                payload[key] = props[key]

        # Tag resource with example name for cleanup
        if self.example_name:
            keywords = payload.get("keywords", [])
            if not isinstance(keywords, list):
                keywords = []
            keywords.append(f"slcli-example:{self.example_name}")
            payload["keywords"] = keywords

        resp = make_api_request("POST", url, payload, handle_errors=False)
        data = resp.json()
        return str(data.get("id", ""))

    def _get_location_by_name(self, name: str) -> Optional[str]:
        """Find a location by exact `name`, constrained to this example tag and workspace.

        The locations API doesn't support filtering or pagination via URL params.
        Instead, request all locations and filter client-side:
        - Match `location['name']` exactly to `name`.
        - If `self.workspace_id` is set, match `location['workspace']`.
        - Ensure `location['keywords']` contains `slcli-example:{self.example_name}`.
        Returns the first matching `id`, or None if not found.
        """
        try:
            url = f"{get_base_url()}/nilocation/v1/locations"
            resp = make_api_request("GET", url, handle_errors=False)
            data = resp.json()
            locations = data.get("locations", [])

            example_tag = f"slcli-example:{self.example_name}" if self.example_name else None

            for loc in locations:
                if str(loc.get("name", "")) != name:
                    continue
                if self.workspace_id and str(loc.get("workspace", "")) != str(self.workspace_id):
                    continue
                if example_tag:
                    keywords = loc.get("keywords", [])
                    if not (isinstance(keywords, list) and example_tag in keywords):
                        continue
                return str(loc.get("id", "")) or None
        except Exception:
            # API unavailable or malformed response; return None to allow fallback to creation
            pass
        return None

    def _create_product(self, props: Dict[str, Any]) -> str:
        """Create product via Test Monitor API and return server ID.

        Uses POST /nitestmonitor/v2/products with request body:
        { "products": [{ partNumber, name, family, keywords, properties, fileIds, workspace }] }
        """
        url = f"{get_base_url()}/nitestmonitor/v2/products"
        product_obj = {
            "name": props.get("name", "Unknown Product"),
            "workspace": self.workspace_id or "",
        }
        # Copy optional fields from ProductRequestObject schema
        for key in ["partNumber", "family", "properties"]:
            if key in props:
                product_obj[key] = props[key]

        # Handle fileIds: resolve file references from id_map
        file_ids: List[str] = []
        # Check for fileIds directly in props
        if "fileIds" in props and isinstance(props["fileIds"], list):
            file_ids.extend([str(fid) for fid in props["fileIds"]])
        # Check for file_id_references that need to be resolved
        if "file_id_references" in props and isinstance(props["file_id_references"], list):
            for ref in props["file_id_references"]:
                if ref in self.id_map:
                    file_ids.append(self.id_map[ref])
                else:
                    click.echo(
                        f"Warning: File reference '{ref}' not found in id_map for product {product_obj['name']}",
                        err=True,
                    )
        # If we have file IDs, add them to the product object
        if file_ids:
            product_obj["fileIds"] = file_ids

        # Ensure part number is present to avoid silent failures
        if "partNumber" not in product_obj:
            fallback_pn = str(product_obj.get("name", "SLCLI-PRODUCT")).replace(" ", "-")
            product_obj["partNumber"] = fallback_pn

        # Tag resource for cleanup using keywords
        keywords: List[str] = []
        if isinstance(props.get("keywords"), list):
            keywords.extend([str(x) for x in props.get("keywords", [])])
        if isinstance(props.get("tags"), list):
            keywords.extend([str(x) for x in props.get("tags", [])])
        keywords.append("slcli-provisioner")
        if self.example_name:
            keywords.append(f"slcli-example:{self.example_name}")
        if keywords:
            seen: set[str] = set()
            dedup = []
            for k in keywords:
                if k not in seen:
                    dedup.append(k)
                    seen.add(k)
            product_obj["keywords"] = dedup

        # Wrap in products array per API schema
        payload = {"products": [product_obj]}
        resp = make_api_request("POST", url, payload, handle_errors=False)
        data = resp.json()
        # Response is { products: [...], failed: [...], error: {...} }
        # Check for successful creation first
        products = data.get("products", [])
        if products and len(products) > 0:
            return str(products[0].get("id", ""))
        # Check for duplicate part number error
        if data.get("error") and data["error"].get("name") == "Skyline.OneOrMoreErrorsOccurred":
            inner_errors = data["error"].get("innerErrors", [])
            for err in inner_errors:
                if "Duplicate" in err.get("message", ""):
                    # Query for existing product by part number
                    part_number = product_obj.get("partNumber", "")
                    name = product_obj.get("name", "")
                    if part_number:
                        try:
                            base_query_url = f"{get_base_url()}/nitestmonitor/v2/products"
                            continuation_token = None

                            # Paginate through all products to find match
                            while True:
                                query_url = base_query_url
                                if continuation_token:
                                    query_url = (
                                        f"{base_query_url}?continuationToken={continuation_token}"
                                    )

                                query_resp = make_api_request("GET", query_url, handle_errors=False)
                                query_data = query_resp.json()

                                # Search through products on this page for match by part number
                                for prod in query_data.get("products", []):
                                    if prod.get("partNumber") == part_number:
                                        prod_id = prod.get("id", "")
                                        if prod_id:
                                            # Return with duplicate marker so provisioning
                                            # knows it's a skip
                                            return f"__DUPLICATE_ID__{prod_id}"

                                # If not found by part number on this page, try by name as fallback
                                if name:
                                    for prod in query_data.get("products", []):
                                        if prod.get("name") == name:
                                            prod_id = prod.get("id", "")
                                            if prod_id:
                                                return f"__DUPLICATE_ID__{prod_id}"

                                # Check for continuation token for next page
                                continuation_token = query_data.get("continuationToken")
                                if not continuation_token:
                                    # No more pages, duplicate not found
                                    break

                            # Duplicate detected but ID not found in any page
                            return "__DUPLICATE_NOTFOUND__"
                        except Exception:
                            # Pagination or query error during duplicate detection; treat as unfound
                            return "__DUPLICATE_NOTFOUND__"
        return ""

    def _get_product_by_name(self, name: str) -> Optional[str]:
        """Find a product by exact `name` within workspace. Returns ID or None.

        Uses Test Monitor API: GET /nitestmonitor/v2/products which returns { products: [...] }.
        Filters client-side on:
        - `name` equals `name`
        - `workspace` equals `self.workspace_id` (if set)
        - `keywords` contains the example tag (if set)
        """
        try:
            url = f"{get_base_url()}/nitestmonitor/v2/products"
            resp = make_api_request("GET", url, handle_errors=False)
            data = resp.json()
            products = data.get("products", [])
            example_tag = f"slcli-example:{self.example_name}" if self.example_name else None
            for prod in products:
                if str(prod.get("name", "")) != name:
                    continue
                if self.workspace_id and str(prod.get("workspace", "")) != str(self.workspace_id):
                    continue
                if example_tag:
                    keywords = prod.get("keywords", [])
                    if not (isinstance(keywords, list) and example_tag in keywords):
                        continue
                return str(prod.get("id", "")) or None
        except Exception:
            # API unavailable or malformed response; return None to allow fallback to creation
            pass
        return None

    def _create_system(self, props: Dict[str, Any]) -> str:
        """Create virtual system via Systems Management API and return server ID.

        Uses POST /nisysmgmt/v1/virtual with request body:
        { alias, workspace }
        """
        url = f"{get_base_url()}/nisysmgmt/v1/virtual"
        # Systems Management API uses 'alias' not 'name'
        payload: Dict[str, Any] = {
            "alias": props.get("name", "Unknown System"),
        }
        # Only include workspace if we have a specific workspace ID
        # Note: Systems API rejects empty string workspace
        if self.workspace_id and self.workspace_id.strip():
            payload["workspace"] = self.workspace_id
        resp = make_api_request("POST", url, payload, handle_errors=False)
        resp.raise_for_status()
        data = resp.json()
        # Response is { minionId }
        return str(data.get("minionId", ""))

    def _get_system_by_name(self, name: str) -> Optional[str]:
        """Find a system by exact alias within workspace. Returns first ID or None.

        Uses Systems Management API: POST /nisysmgmt/v1/query-systems with QuerySystemsRequest.
        Handles both response shapes: { count, data: [...] } and legacy list.
        """
        try:
            url = f"{get_base_url()}/nisysmgmt/v1/query-systems"
            filter_expr = f'alias = "{name}"'
            payload = {
                "skip": 0,
                "take": 100,
                "filter": filter_expr,
                "projection": "new(id,alias,workspace)",
                "orderBy": "alias",
            }
            resp = make_api_request("POST", url, payload, handle_errors=False)
            data = resp.json()
            systems: List[Dict[str, Any]] = []
            if isinstance(data, dict) and isinstance(data.get("data"), list):
                systems = data.get("data", [])
            elif isinstance(data, list):
                # Legacy shape: list of items with optional 'data' field
                for item in data:
                    sys = item.get("data", item) if isinstance(item, dict) else {}
                    if sys:
                        systems.append(sys)
            for sys in systems:
                alias = str(sys.get("alias", ""))
                if alias != name:
                    continue
                if self.workspace_id and str(sys.get("workspace", "")) != str(self.workspace_id):
                    continue
                return str(sys.get("id", "")) or None
        except Exception:
            # API unavailable or malformed response; return None to allow fallback to creation
            pass
        return None

    def _get_system_ids_by_name(self, name: str) -> List[str]:
        """Return all system IDs matching alias and workspace."""
        ids: List[str] = []
        try:
            url = f"{get_base_url()}/nisysmgmt/v1/query-systems"
            filter_expr = f'alias = "{name}"'
            payload = {
                "skip": 0,
                "take": 200,
                "filter": filter_expr,
                "projection": "new(id,alias,workspace)",
                "orderBy": "alias",
            }
            resp = make_api_request("POST", url, payload, handle_errors=False)
            data = resp.json()
            systems: List[Dict[str, Any]] = []
            if isinstance(data, dict) and isinstance(data.get("data"), list):
                systems = data.get("data", [])
            elif isinstance(data, list):
                for item in data:
                    sys = item.get("data", item) if isinstance(item, dict) else {}
                    if sys:
                        systems.append(sys)
            for sys in systems:
                alias = str(sys.get("alias", ""))
                if alias != name:
                    continue
                if self.workspace_id and str(sys.get("workspace", "")) != str(self.workspace_id):
                    continue
                sid = str(sys.get("id", ""))
                if sid:
                    ids.append(sid)
        except Exception:
            # API unavailable or malformed response; return empty list to proceed with creation
            pass
        return ids

    def _create_asset(self, props: Dict[str, Any]) -> str:
        """Create asset via Asset Management API and return server ID.

        Uses POST /niapm/v1/assets with request body:
        { "assets": [{ name, assetType, busType, modelName, vendorName, serialNumber,
                       workspace, keywords, properties, ... }] }
        """
        url = f"{get_base_url()}/niapm/v1/assets"
        asset_obj = {
            "name": props.get("name", "Unknown Asset"),
            "workspace": self.workspace_id or "",
        }
        # Copy optional fields from AssetCreateModel schema, supporting snake_case inputs
        field_map = {
            "assetType": ["assetType"],
            "busType": ["busType", "bus_type"],
            "modelName": ["modelName", "model_name", "model"],
            "modelNumber": ["modelNumber", "model_number"],
            "vendorName": ["vendorName", "vendor_name"],
            "vendorNumber": ["vendorNumber", "vendor_number"],
            "serialNumber": ["serialNumber", "serial_number"],
            "partNumber": ["partNumber", "part_number"],
            "properties": ["properties"],
            "fileIds": ["fileIds", "file_ids"],
        }
        for target, candidates in field_map.items():
            val = None
            for cand in candidates:
                if cand in props:
                    val = props[cand]
                    break
            if val is None:
                continue
            # Special handling: skip invalid serial numbers (empty/whitespace/'0')
            if target == "serialNumber" and isinstance(val, str):
                trimmed = val.strip()
                if trimmed == "" or trimmed == "0":
                    continue
            # Coerce numeric fields to integers when provided as strings
            if target in ("modelNumber", "vendorNumber"):
                if isinstance(val, str):
                    num = val.strip()
                    if num.isdigit():
                        asset_obj[target] = int(num)
                        continue
                    # Skip non-numeric vendor/model numbers to avoid 400
                    continue
                elif isinstance(val, (int,)):
                    asset_obj[target] = val
                    continue
                else:
                    continue
            # Normalize bus type values to OpenAPI enum
            if target == "busType" and isinstance(val, str):
                bt = val.strip().upper()
                if bt == "ETHERNET":
                    bt = "TCP_IP"
                asset_obj[target] = bt
                continue
            asset_obj[target] = val

        # Provide defaults to satisfy identification when missing
        if "busType" not in asset_obj:
            asset_obj["busType"] = "ACCESSORY"
        if "modelName" not in asset_obj:
            asset_obj["modelName"] = "Unknown"
        if "vendorName" not in asset_obj:
            asset_obj["vendorName"] = "Unknown"

        # If a system is provided via resolved "system_id", construct the location object
        # using the system's minion ID per AssetLocationWithPresenceModel.
        if "system_id" in props and isinstance(props["system_id"], str):
            asset_obj["location"] = {
                "minionId": props["system_id"],
                "state": {"assetPresence": "UNKNOWN"},
            }

        # Tag resource with example name for cleanup
        if self.example_name:
            keywords = props.get("keywords", [])
            if not isinstance(keywords, list):
                keywords = []
            keywords.append(f"slcli-example:{self.example_name}")
            asset_obj["keywords"] = keywords

        # Wrap in assets array per API schema
        payload = {"assets": [asset_obj]}
        resp = make_api_request("POST", url, payload, handle_errors=False)
        data = resp.json()
        # Response is { assets: [...], failed: [...], error: {...} }
        # Check for successful creation first
        assets = data.get("assets", [])
        if assets and len(assets) > 0:
            # Prefer 'id', fallback to 'assetIdentifier' if provided
            aid = assets[0].get("id") or assets[0].get("assetIdentifier") or ""
            return str(aid)
        # Check for already exists error - extract ID from error response
        if data.get("error") and data["error"].get("name") == "Skyline.OneOrMoreErrorsOccurred":
            inner_errors = data["error"].get("innerErrors", [])
            for err in inner_errors:
                error_msg = err.get("message", "")
                if "already exists" in error_msg.lower():
                    # Extract asset ID from resourceId field
                    resource_id = err.get("resourceId")
                    if resource_id:
                        return str(resource_id)
        return ""

    def _get_asset_by_name(self, name: str) -> Optional[str]:
        """Find an asset by exact `name` within workspace. Returns ID or None.

        Uses Asset Management API: POST /niapm/v1/query-assets which returns
        { assets: [...], totalCount }.
        Filters via API on workspace/name and client-side on example tag (keywords).
        """
        try:
            url = f"{get_base_url()}/niapm/v1/query-assets"
            filters = []
            if self.workspace_id:
                filters.append(f'Workspace = "{self.workspace_id}"')
            filters.append(f'AssetName = "{name}"')
            filter_expr = " and ".join(filters)
            projection = (
                "new(id,name,modelName,modelNumber,vendorName,vendorNumber,serialNumber,"
                "workspace,properties,keywords,location.minionId,location.parent,"
                "location.physicalLocation,location.state.assetPresence,location.state.systemConnection,"
                "discoveryType,supportsSelfTest,supportsSelfCalibration,supportsReset,"
                "supportsExternalCalibration,scanCode,temperatureSensors.reading,"
                "externalCalibration.resolvedDueDate,selfCalibration.date)"
            )
            payload = {
                "filter": filter_expr,
                "take": 1000,
                "skip": 0,
                "projection": projection,
            }
            resp = make_api_request("POST", url, payload, handle_errors=False)
            data = resp.json()
            assets = data.get("assets", [])
            example_tag = f"slcli-example:{self.example_name}" if self.example_name else None
            for asset in assets:
                if example_tag:
                    keywords = asset.get("keywords", [])
                    if not (isinstance(keywords, list) and example_tag in keywords):
                        continue
                return str(asset.get("id", "")) or None
        except Exception:
            # API unavailable or malformed response; return None to allow fallback to creation
            pass
        return None

    def _create_dut(self, props: Dict[str, Any]) -> str:
        """Create DUT via Asset Management API and return server ID.

        DUTs are assets with assetType=DEVICE_UNDER_TEST.
        Uses POST /niapm/v1/assets with request body:
        { "assets": [{ name, assetType: "DEVICE_UNDER_TEST", ... }] }
        """
        url = f"{get_base_url()}/niapm/v1/assets"
        asset_obj = {
            "name": props.get("name", "Unknown DUT"),
            "assetType": "DEVICE_UNDER_TEST",
            "workspace": self.workspace_id or "",
        }
        # Copy optional fields from AssetCreateModel schema, supporting snake_case inputs
        field_map = {
            "busType": ["busType", "bus_type"],
            "modelName": ["modelName", "model_name", "model"],
            "modelNumber": ["modelNumber", "model_number"],
            "vendorName": ["vendorName", "vendor_name"],
            "vendorNumber": ["vendorNumber", "vendor_number"],
            "serialNumber": ["serialNumber", "serial_number"],
            "partNumber": ["partNumber", "part_number"],
            "properties": ["properties"],
            "fileIds": ["fileIds", "file_ids"],
        }
        for target, candidates in field_map.items():
            val = None
            for cand in candidates:
                if cand in props:
                    val = props[cand]
                    break
            if val is None:
                continue
            # Special handling: skip invalid serial numbers (empty/whitespace/'0')
            if target == "serialNumber" and isinstance(val, str):
                trimmed = val.strip()
                if trimmed == "" or trimmed == "0":
                    continue
            # Coerce numeric fields to integers when provided as strings
            if target in ("modelNumber", "vendorNumber"):
                if isinstance(val, str):
                    num = val.strip()
                    if num.isdigit():
                        asset_obj[target] = int(num)
                        continue
                    # Skip non-numeric vendor/model numbers to avoid 400
                    continue
                elif isinstance(val, (int,)):
                    asset_obj[target] = val
                    continue
                else:
                    continue
            # Normalize bus type values to OpenAPI enum
            if target == "busType" and isinstance(val, str):
                bt = val.strip().upper()
                if bt == "ETHERNET":
                    bt = "TCP_IP"
                asset_obj[target] = bt
                continue
            asset_obj[target] = val

        # Provide defaults to satisfy identification when missing
        if "busType" not in asset_obj:
            asset_obj["busType"] = "ACCESSORY"
        if "modelName" not in asset_obj:
            asset_obj["modelName"] = "Unknown"
        if "vendorName" not in asset_obj:
            asset_obj["vendorName"] = "Unknown"

        # DUTs can be created without explicit location; if the service expects a location,
        # provide a minimal presence state without binding to a system.
        if "location" not in asset_obj:
            asset_obj["location"] = {"state": {"assetPresence": "UNKNOWN"}}

        # Tag resource with example name for cleanup
        if self.example_name:
            keywords = props.get("keywords", [])
            if not isinstance(keywords, list):
                keywords = []
            keywords.append(f"slcli-example:{self.example_name}")
            asset_obj["keywords"] = keywords

        # Wrap in assets array per API schema
        payload = {"assets": [asset_obj]}
        resp = make_api_request("POST", url, payload, handle_errors=False)
        data = resp.json()
        # Response is { assets: [...], failed: [...], error: {...} }
        # Check for successful creation first
        assets = data.get("assets", [])
        if assets and len(assets) > 0:
            # Prefer 'id', fallback to 'assetIdentifier' if provided
            aid = assets[0].get("id") or assets[0].get("assetIdentifier") or ""
            return str(aid)
        # Check for already exists error - extract ID from error response
        if data.get("error") and data["error"].get("name") == "Skyline.OneOrMoreErrorsOccurred":
            inner_errors = data["error"].get("innerErrors", [])
            for err in inner_errors:
                error_msg = err.get("message", "")
                if "already exists" in error_msg.lower():
                    # Extract asset ID from resourceId field
                    resource_id = err.get("resourceId")
                    if resource_id:
                        return str(resource_id)
        return ""

    def _get_dut_by_name(self, name: str) -> Optional[str]:
        """Find a DUT by exact `name` within workspace. Returns ID or None.

        DUTs are managed as assets via Asset Management API: POST /niapm/v1/query-assets
        which returns { assets: [...], totalCount }.
        Filters via API on workspace/name and client-side on example tag (keywords).
        """
        try:
            url = f"{get_base_url()}/niapm/v1/query-assets"
            filters = []
            if self.workspace_id:
                filters.append(f'Workspace = "{self.workspace_id}"')
            filters.append(f'AssetName = "{name}"')
            filter_expr = " and ".join(filters)
            projection = (
                "new(id,name,modelName,modelNumber,vendorName,vendorNumber,serialNumber,"
                "workspace,properties,keywords,location.minionId,location.parent,"
                "location.physicalLocation,location.state.assetPresence,location.state.systemConnection,"
                "discoveryType,supportsSelfTest,supportsSelfCalibration,supportsReset,"
                "supportsExternalCalibration,scanCode,temperatureSensors.reading,"
                "externalCalibration.resolvedDueDate,selfCalibration.date)"
            )
            payload = {
                "filter": filter_expr,
                "take": 1000,
                "skip": 0,
                "projection": projection,
            }
            resp = make_api_request("POST", url, payload, handle_errors=False)
            data = resp.json()
            assets = data.get("assets", [])
            example_tag = f"slcli-example:{self.example_name}" if self.example_name else None
            for asset in assets:
                if example_tag:
                    keywords = asset.get("keywords", [])
                    if not (isinstance(keywords, list) and example_tag in keywords):
                        continue
                return str(asset.get("id", "")) or None
        except Exception:
            # API unavailable or malformed response; return None to allow fallback to creation
            pass
        return None

    def _create_testtemplate(self, props: Dict[str, Any]) -> Optional[str]:
        """Create work item template via Work Item API and return server ID.

        Uses POST /niworkitem/v1/workitem-templates with request body:
        { "workItemTemplates": [{ name, templateGroup, type, workspace, ... }] }
        Required fields: name, templateGroup, type
        """
        url = f"{get_base_url()}/niworkitem/v1/workitem-templates"
        template_obj = {
            "name": props.get("name", "Unknown Test Template"),
            "templateGroup": props.get("templateGroup", "Default"),
            "type": props.get("type", "testplan"),
        }
        # Only include workspace if we have a specific workspace ID
        if self.workspace_id and self.workspace_id.strip():
            template_obj["workspace"] = self.workspace_id
        # Copy optional fields from CreateWorkItemTemplateRequest schema
        for key in [
            "summary",
            "description",
            "testProgram",
            "productFamilies",
            "partNumbers",
            "properties",
            "fileIds",
        ]:
            if key in props:
                template_obj[key] = props[key]

        # Note: Work item templates don't support keywords field
        # To aid cleanup, embed example tag into properties under a reserved key
        if self.example_name:
            props_key = template_obj.get("properties") or {}
            if not isinstance(props_key, dict):
                props_key = {}
            props_key.setdefault("slcliExample", str(self.example_name))
            template_obj["properties"] = props_key

        # Wrap in workItemTemplates array per API schema
        payload = {"workItemTemplates": [template_obj]}
        resp = make_api_request("POST", url, payload, handle_errors=False)
        data = resp.json()
        # Response is { createdWorkItemTemplates: [...] }
        templates = data.get("createdWorkItemTemplates", [])
        if templates and len(templates) > 0:
            tmpl_id = templates[0].get("id")
            # Return None if ID is missing, empty, or invalid
            if tmpl_id and str(tmpl_id).strip():
                return str(tmpl_id)
        return None

    def _get_testtemplate_by_name(self, name: str) -> Optional[str]:
        """Find a test template by exact `name` within workspace. Returns ID or None.

        Uses Work Item API: POST /niworkitem/v1/query-workitem-templates which returns
        { workItemTemplates: [...] }.
        Filters client-side on:
        - `name` equals `name`
        - `workspace` equals `self.workspace_id` (if set)
        Note: Work item templates don't have keywords field for example tagging.
        """
        try:
            url = f"{get_base_url()}/niworkitem/v1/query-workitem-templates"
            resp = make_api_request("POST", url, {}, handle_errors=False)
            data = resp.json()
            templates = data.get("workItemTemplates", [])
            for tmpl in templates:
                if str(tmpl.get("name", "")) != name:
                    continue
                if self.workspace_id and str(tmpl.get("workspace", "")) != str(self.workspace_id):
                    continue
                return str(tmpl.get("id", "")) or None
        except Exception:
            # API unavailable or malformed response; return None to allow fallback to creation
            pass
        return None

    # --- Delete methods ---
    def _delete_location(self, props: Dict[str, Any]) -> Optional[str]:
        """Delete location via /nilocation/v1/locations:deleteMany API.

        Returns the location ID if deletion succeeded, None otherwise.
        """
        name = props.get("name", "")
        if not name:
            return None

        location_id = self._get_location_by_name(name)
        if not location_id:
            # Location doesn't exist, nothing to delete
            return None

        try:
            url = f"{get_base_url()}/nilocation/v1/locations:deleteMany"
            payload = {"locationIds": [location_id]}
            resp = make_api_request("POST", url, payload, handle_errors=False)
            resp.raise_for_status()
            return location_id
        except Exception:
            return None

    def _delete_product(self, props: Dict[str, Any]) -> Optional[str]:
        """Delete products via /nitestmonitor/v2/delete-products using keyword tags.

        Returns an ID summary if deleted, None otherwise.
        """
        example_tag = f"slcli-example:{self.example_name}" if self.example_name else None

        try:
            # Build filter to match products tagged for cleanup
            filter_parts = ['keywords.Any(x => x == "slcli-provisioner")']
            if example_tag:
                filter_parts.append(f'keywords.Any(x => x == "{example_tag}")')
            if self.workspace_id:
                filter_parts.append(f'workspace == "{self.workspace_id}"')

            filter_expr = " && ".join(filter_parts)

            query_url = f"{get_base_url()}/nitestmonitor/v2/query-products"
            query_payload = {"filter": filter_expr, "take": 1000}
            query_resp = make_api_request("POST", query_url, query_payload, handle_errors=False)
            products = query_resp.json().get("products", [])

            product_ids: List[str] = []
            for prod in products:
                pid = prod.get("id")
                if pid:
                    product_ids.append(str(pid))

            if not product_ids:
                return None

            delete_url = f"{get_base_url()}/nitestmonitor/v2/delete-products"
            delete_payload = {"ids": product_ids}
            make_api_request("POST", delete_url, delete_payload, handle_errors=False)

            if len(product_ids) == 1:
                return product_ids[0]
            return f"{product_ids[0]} (+{len(product_ids) - 1} more)"
        except Exception:
            return None

    def _delete_system(self, props: Dict[str, Any]) -> Optional[str]:
        """Delete system via /nisysmgmt/v1/remove-systems.

        Returns ID if deleted, None otherwise.
        """
        name = props.get("name", "")
        if not name:
            return None

        system_ids = self._get_system_ids_by_name(name)
        if not system_ids:
            return None

        try:
            url = f"{get_base_url()}/nisysmgmt/v1/remove-systems"
            payload = {"tgt": system_ids, "force": True}
            resp = make_api_request("POST", url, payload, handle_errors=False)
            resp.raise_for_status()
            # Return the first deleted ID for audit purposes
            return system_ids[0]
        except Exception:
            return None

    def _delete_asset(self, props: Dict[str, Any]) -> Optional[str]:
        """Delete asset via /niapm/v1/delete-assets.

        Returns ID if deleted, None otherwise.
        """
        name = props.get("name", "")
        if not name:
            return None

        asset_id = self._get_asset_by_name(name)
        if not asset_id:
            # Asset doesn't exist
            return None

        try:
            url = f"{get_base_url()}/niapm/v1/delete-assets"
            payload = {"ids": [asset_id]}
            resp = make_api_request("POST", url, payload, handle_errors=False)
            resp.raise_for_status()
            return asset_id
        except Exception:
            return None

    def _delete_dut(self, props: Dict[str, Any]) -> Optional[str]:
        """Delete DUT via /niapm/v1/delete-assets.

        Returns ID if deleted, None otherwise.
        """
        name = props.get("name", "")
        if not name:
            return None

        dut_id = self._get_dut_by_name(name)
        if not dut_id:
            # DUT doesn't exist
            return None

        try:
            url = f"{get_base_url()}/niapm/v1/delete-assets"
            payload = {"ids": [dut_id]}
            resp = make_api_request("POST", url, payload, handle_errors=False)
            resp.raise_for_status()
            return dut_id
        except Exception:
            return None

    def _delete_testtemplate(self, props: Dict[str, Any]) -> Optional[str]:
        """Delete test template via /niworkitem/v1/delete-workitem-templates.

        Returns ID if deleted, None otherwise.
        """
        name = props.get("name", "")
        if not name:
            return None

        template_id = self._get_testtemplate_by_name(name)
        if not template_id:
            # Template doesn't exist
            return None

        try:
            url = f"{get_base_url()}/niworkitem/v1/delete-workitem-templates"
            payload = {"ids": [template_id]}
            resp = make_api_request("POST", url, payload, handle_errors=False)
            resp.raise_for_status()
            return template_id
        except Exception:
            return None

    # ========================================================================
    # Workflow Methods (Tier 2)
    # ========================================================================

    def _create_workflow(self, props: Dict[str, Any]) -> Optional[str]:
        """Create workflow via /niworkorder/v1/workflows.

        Returns workflow ID if created, None on error.
        """
        name = props.get("name", "")
        if not name:
            return None

        try:
            # Use the same schema as workflows init/import command
            # Note: keywords/properties are not supported by this API; include required fields only
            url = f"{get_base_url()}/niworkorder/v1/workflows"
            wf_obj: Dict[str, Any] = {
                "name": name,
                "description": props.get("description", ""),
                "workspace": self.workspace_id or props.get("workspace", ""),
                "actions": [
                    {
                        "name": "START",
                        "displayText": "Start",
                        "privilegeSpecificity": ["ExecuteTest"],
                        "executionAction": {"type": "MANUAL", "action": "START"},
                    },
                    {
                        "name": "COMPLETE",
                        "displayText": "Complete",
                        "privilegeSpecificity": ["Close"],
                        "executionAction": {"type": "MANUAL", "action": "COMPLETE"},
                    },
                    {
                        "name": "RUN_NOTEBOOK",
                        "displayText": "Run Notebook",
                        "iconClass": None,
                        "i18n": [],
                        "privilegeSpecificity": ["ExecuteTest"],
                        "executionAction": {
                            "action": "RUN_NOTEBOOK",
                            "type": "NOTEBOOK",
                            "notebookId": "00000000-0000-0000-0000-000000000000",
                            "parameters": {
                                "partNumber": "<partNumber>",
                                "dut": "<assignedTo>",
                                "operator": "<assignedTo>",
                                "testProgram": "<testProgram>",
                                "location": "<properties.region>-<properties.facility>-<properties.lab>",
                            },
                        },
                    },
                    {
                        "name": "PLAN_SCHEDULE",
                        "displayText": "Schedule Test Plan",
                        "iconClass": "SCHEDULE",
                        "i18n": [],
                        "privilegeSpecificity": [],
                        "executionAction": {"action": "PLAN_SCHEDULE", "type": "SCHEDULE"},
                    },
                    {
                        "name": "RUN_JOB",
                        "displayText": "Run Job",
                        "iconClass": "DEPLOY",
                        "i18n": [],
                        "privilegeSpecificity": [],
                        "executionAction": {
                            "action": "RUN_JOB",
                            "type": "JOB",
                            "jobs": [
                                {
                                    "functions": ["state.apply"],
                                    "arguments": [["<properties.startTestStateId>"]],
                                    "metadata": {},
                                }
                            ],
                        },
                    },
                ],
                "states": [
                    {
                        "name": "NEW",
                        "dashboardAvailable": False,
                        "defaultSubstate": "NEW",
                        "substates": [
                            {
                                "name": "NEW",
                                "displayText": "New",
                                "availableActions": [
                                    {
                                        "action": "PLAN_SCHEDULE",
                                        "nextState": "SCHEDULED",
                                        "nextSubstate": "SCHEDULED",
                                        "showInUI": True,
                                    }
                                ],
                            }
                        ],
                    },
                    {
                        "name": "DEFINED",
                        "dashboardAvailable": False,
                        "defaultSubstate": "DEFINED",
                        "substates": [
                            {
                                "name": "DEFINED",
                                "displayText": "Defined",
                                "availableActions": [],
                            }
                        ],
                    },
                    {
                        "name": "REVIEWED",
                        "dashboardAvailable": False,
                        "defaultSubstate": "REVIEWED",
                        "substates": [
                            {
                                "name": "REVIEWED",
                                "displayText": "Reviewed",
                                "availableActions": [],
                            }
                        ],
                    },
                    {
                        "name": "SCHEDULED",
                        "dashboardAvailable": True,
                        "defaultSubstate": "SCHEDULED",
                        "substates": [
                            {
                                "name": "SCHEDULED",
                                "displayText": "Scheduled",
                                "availableActions": [
                                    {
                                        "action": "START",
                                        "nextState": "IN_PROGRESS",
                                        "nextSubstate": "IN_PROGRESS",
                                        "showInUI": True,
                                    },
                                    {
                                        "action": "RUN_NOTEBOOK",
                                        "nextState": "IN_PROGRESS",
                                        "nextSubstate": "IN_PROGRESS",
                                        "showInUI": True,
                                    },
                                ],
                            }
                        ],
                    },
                    {
                        "name": "IN_PROGRESS",
                        "dashboardAvailable": True,
                        "defaultSubstate": "IN_PROGRESS",
                        "substates": [
                            {
                                "name": "IN_PROGRESS",
                                "displayText": "In progress",
                                "availableActions": [
                                    {
                                        "action": "COMPLETE",
                                        "nextState": "PENDING_APPROVAL",
                                        "nextSubstate": "PENDING_APPROVAL",
                                        "showInUI": True,
                                    }
                                ],
                            }
                        ],
                    },
                    {
                        "name": "PENDING_APPROVAL",
                        "dashboardAvailable": True,
                        "defaultSubstate": "PENDING_APPROVAL",
                        "substates": [
                            {
                                "name": "PENDING_APPROVAL",
                                "displayText": "Pending approval",
                                "availableActions": [
                                    {
                                        "action": "RUN_JOB",
                                        "nextState": "CLOSED",
                                        "nextSubstate": "CLOSED",
                                        "showInUI": True,
                                    }
                                ],
                            }
                        ],
                    },
                    {
                        "name": "CLOSED",
                        "dashboardAvailable": False,
                        "defaultSubstate": "CLOSED",
                        "substates": [
                            {"name": "CLOSED", "displayText": "Closed", "availableActions": []}
                        ],
                    },
                    {
                        "name": "CANCELED",
                        "dashboardAvailable": False,
                        "defaultSubstate": "CANCELED",
                        "substates": [
                            {"name": "CANCELED", "displayText": "Canceled", "availableActions": []}
                        ],
                    },
                ],
            }

            payload = wf_obj
            resp = make_api_request("POST", url, payload, handle_errors=False)
            resp.raise_for_status()
            data = resp.json()
            # Create returns the created workflow object (id at root)
            if isinstance(data, dict) and data.get("id"):
                return str(data.get("id"))
            return None
        except Exception:
            return None

    def _get_workflow_by_name(self, name: str) -> Optional[str]:
        """Look up workflow by name via /niworkorder/v1/query-workflows.

        Returns workflow ID if found, None otherwise.
        """
        if not name:
            return None

        try:
            url = f"{get_base_url()}/niworkorder/v1/query-workflows"
            payload = {
                "filter": "name == @0",
                "substitutions": [name],
                "projection": ["ID", "NAME"],
                "take": 100,  # Get more results to verify exact match
            }
            resp = make_api_request("POST", url, payload, handle_errors=False)
            resp.raise_for_status()
            data = resp.json()
            if "workflows" in data:
                # Find exact case-insensitive match
                for workflow in data["workflows"]:
                    if workflow.get("name", "").lower() == name.lower():
                        return workflow.get("id")
            return None
        except Exception:
            return None

    def _get_workflow_ids_by_name(self, name: str) -> List[str]:
        """Return all workflow IDs with exact name; include workspace if supported."""
        ids: List[str] = []
        if not name:
            return ids
        try:
            url = f"{get_base_url()}/niworkorder/v1/query-workflows"
            filter_str = "name == @0"
            subs: List[str] = [name]
            if self.workspace_id:
                filter_str += " and workspace == @1"
                subs.append(self.workspace_id)
            payload = {
                "filter": filter_str,
                "substitutions": subs,
                "projection": ["ID", "NAME"],
                "take": 500,
            }
            resp = make_api_request("POST", url, payload, handle_errors=False)
            resp.raise_for_status()
            data = resp.json()
            for wf in data.get("workflows", []) or []:
                if str(wf.get("name", "")).lower() == name.lower():
                    wid = wf.get("id")
                    if wid:
                        ids.append(wid)
        except Exception:
            return ids
        return ids

    def _delete_workflow(self, props: Dict[str, Any]) -> Optional[str]:
        """Delete workflow via /niworkorder/v1/delete-workflows.

        Returns ID if deleted, None otherwise.
        """
        name = props.get("name", "")
        if not name:
            return None

        workflow_ids = self._get_workflow_ids_by_name(name)
        if not workflow_ids:
            return None

        try:
            url = f"{get_base_url()}/niworkorder/v1/delete-workflows"
            payload = {"ids": workflow_ids}
            resp = make_api_request("POST", url, payload, handle_errors=False)
            resp.raise_for_status()
            return workflow_ids[0]
        except Exception:
            return None

    # ========================================================================
    # Work Item Methods (Tier 2)
    # ========================================================================

    def _create_work_item(self, props: Dict[str, Any]) -> Optional[str]:
        """Create work item via /niworkitem/v1/workitems.

        Returns work item ID if created, None on error.
        """
        name = props.get("name", "")
        if not name:
            return None

        try:
            url = f"{get_base_url()}/niworkitem/v1/workitems"
            wi_obj: Dict[str, Any] = {
                "name": name,
                "description": props.get("description", ""),
                "state": props.get("state", "NEW"),
            }

            # Add mandatory partNumber for testplan work items (derived from name if not provided)
            work_item_type = props.get("work_item_type", "testplan")
            if work_item_type == "testplan":
                # PartNumber is mandatory for testplan type
                part_number = props.get("partNumber")
                if not part_number:
                    # Generate from name: replace spaces with hyphens, use first 50 chars
                    part_number = name.replace(" ", "-")[:50]
                wi_obj["partNumber"] = part_number

            # Only include workspace if we have a specific workspace ID
            if self.workspace_id and self.workspace_id.strip():
                wi_obj["workspace"] = self.workspace_id
            # Map template and type if provided
            if "test_template_id" in props:
                template_id = props["test_template_id"]
                # Resolve template reference from id_map (e.g., "${tt_acs_validation}" -> "508660")
                if isinstance(template_id, str):
                    # Remove ${} wrapper if present
                    if template_id.startswith("${") and template_id.endswith("}"):
                        template_ref = template_id[2:-1]  # Extract reference name
                        # Look up actual ID from id_map
                        if template_ref in self.id_map:
                            template_id = self.id_map[template_ref]
                        else:
                            # Template reference not found in id_map
                            raise Exception(
                                f"Template '{template_ref}' not found in id_map - template may not have been created successfully"
                            )

                if not template_id or (isinstance(template_id, str) and not template_id.strip()):
                    raise Exception("Template ID is empty - template creation may have failed")
                wi_obj["templateId"] = template_id
            if "work_item_type" in props:
                wi_obj["type"] = props["work_item_type"]
            # Reserve DUT/system resources if provided
            resources: Dict[str, Any] = {}
            if "scheduled_dut" in props:
                dut_id = props["scheduled_dut"]
                # Resolve reference from id_map
                if isinstance(dut_id, str):
                    dut_ref = dut_id
                    if dut_ref.startswith("${") and dut_ref.endswith("}"):
                        dut_ref = dut_ref[2:-1]
                    if dut_ref in self.id_map:
                        dut_id = self.id_map[dut_ref]
                    elif not dut_ref.startswith("${"):
                        # dut_ref is not a reference wrapper, use as-is
                        dut_id = dut_ref
                    else:
                        # Reference not found
                        raise Exception(
                            f"DUT '{dut_ref}' not found in id_map - DUT may not have been created successfully"
                        )
                if dut_id:
                    resources["duts"] = {"selections": [{"id": dut_id}]}
            if "scheduled_system" in props:
                sys_id = props["scheduled_system"]
                # Resolve reference from id_map
                if isinstance(sys_id, str):
                    sys_ref = sys_id
                    if sys_ref.startswith("${") and sys_ref.endswith("}"):
                        sys_ref = sys_ref[2:-1]
                    if sys_ref in self.id_map:
                        sys_id = self.id_map[sys_ref]
                    elif not sys_ref.startswith("${"):
                        # sys_ref is not a reference wrapper, use as-is
                        sys_id = sys_ref
                    else:
                        # Reference not found
                        raise Exception(
                            f"System '{sys_ref}' not found in id_map - System may not have been created successfully"
                        )
                if sys_id:
                    resources["systems"] = {"selections": [{"id": sys_id}]}
            if resources:
                wi_obj["resources"] = resources
            # Merge properties
            if "properties" in props and isinstance(props["properties"], dict):
                wi_obj["properties"] = props["properties"]
            # Add keywords for precise cleanup
            kw: List[str] = []
            if isinstance(props.get("keywords"), list):
                kw.extend([str(x) for x in props.get("keywords", [])])
            if isinstance(props.get("tags"), list):
                kw.extend([str(x) for x in props.get("tags", [])])
            if self.example_name:
                kw.append(f"slcli-example:{self.example_name}")
            if kw:
                seen: set[str] = set()
                dedup = []
                for k in kw:
                    if k not in seen:
                        dedup.append(k)
                        seen.add(k)
                wi_obj["keywords"] = dedup
            payload = {"workItems": [wi_obj]}
            resp = make_api_request("POST", url, payload, handle_errors=False)
            resp.raise_for_status()
            data = resp.json()

            # Handle poorly-designed API: 200 response with failures
            # Check for error object or empty created list
            has_error = data.get("error") is not None
            created = data.get("createdWorkItems") or []

            if has_error and not created:
                error_msg = data["error"].get("message", "Unknown error")
                if data["error"].get("innerErrors"):
                    inner = data["error"]["innerErrors"][0]
                    error_msg = inner.get("message", error_msg)
                raise Exception(f"Work item creation failed: {error_msg}")

            # If we have created work items, return the first one's ID
            if created:
                created_id = created[0].get("id")
                if created_id:
                    return str(created_id)

            # Fallback: check alternate response format
            if "workItems" in data and len(data["workItems"]) > 0:
                work_item_id = data["workItems"][0].get("id")
                if work_item_id:
                    return str(work_item_id)

            # Fallback: lookup by name if ID not returned
            looked_up_id = self._get_work_item_by_name(name)
            if looked_up_id:
                return looked_up_id

            # If still no ID, raise exception to ensure we know creation failed
            raise Exception(f"Work item creation returned no ID: {data}")
        except requests.exceptions.HTTPError:
            # Let HTTP errors propagate to the caller's error handler
            raise
        except Exception as exc:
            # Wrap other exceptions with context
            raise Exception(f"Failed to create work item '{name}': {exc}") from exc

    def _get_work_item_by_name(self, name: str) -> Optional[str]:
        """Look up work item by name via /niworkitem/v1/query-workitems.

        Returns work item ID if found, None otherwise.
        """
        if not name:
            return None

        try:
            url = f"{get_base_url()}/niworkitem/v1/query-workitems"
            filter_str = f"name == @0"
            if self.workspace_id:
                filter_str += f" and workspace == @1"
            payload = {
                "filter": filter_str,
                "substitutions": ([name, self.workspace_id] if self.workspace_id else [name]),
                "projection": ["ID", "NAME"],
                "take": 100,
            }
            resp = make_api_request("POST", url, payload, handle_errors=False)
            resp.raise_for_status()
            data = resp.json()
            if "workItems" in data and len(data["workItems"]) > 0:
                # Find exact case-insensitive match
                for item in data["workItems"]:
                    if item.get("name", "").lower() == name.lower():
                        return item.get("id")
            return None
        except Exception:
            return None

    def _get_work_item_ids_by_name(self, name: str) -> List[str]:
        """Return all work item IDs with exact name in current workspace."""
        ids: List[str] = []
        if not name:
            return ids
        try:
            url = f"{get_base_url()}/niworkitem/v1/query-workitems"
            filter_str = f"name == @0"
            subs: List[str] = [name]
            # Only filter by workspace if we have a specific workspace ID
            # Note: workspace_id can be None or empty string - both mean default workspace
            if self.workspace_id and self.workspace_id.strip():
                filter_str += f" and workspace == @1"
                subs.append(self.workspace_id)
            payload = {
                "filter": filter_str,
                "substitutions": subs,
                "projection": ["ID", "NAME"],
                "take": 500,
            }
            resp = make_api_request("POST", url, payload, handle_errors=False)
            resp.raise_for_status()
            data = resp.json()
            for item in data.get("workItems", []) or []:
                if str(item.get("name", "")).lower() == name.lower():
                    iid = item.get("id")
                    if iid:
                        ids.append(iid)
        except Exception:
            return ids
        return ids

    def _delete_work_item(self, props: Dict[str, Any]) -> Optional[str]:
        """Delete work item via /niworkitem/v1/delete-workitems.

        Returns ID if deleted, None otherwise.
        """
        name = props.get("name", "")
        if not name:
            return None

        work_item_ids = self._get_work_item_ids_by_name(name)
        if not work_item_ids:
            return None

        try:
            url = f"{get_base_url()}/niworkitem/v1/delete-workitems"
            payload = {"ids": work_item_ids}
            resp = make_api_request("POST", url, payload, handle_errors=False)
            resp.raise_for_status()
            return work_item_ids[0]
        except Exception:
            return None

    # ========================================================================
    # Work Order Methods (Tier 2)
    # ========================================================================

    def _create_work_order(self, props: Dict[str, Any]) -> Optional[str]:
        """Create work order via /niworkorder/v1/workorders.

        Returns work order ID if created, None on error.
        """
        name = props.get("name", "")
        if not name:
            return None

        try:
            url = f"{get_base_url()}/niworkorder/v1/workorders"

            # Work order state is mandatory - use explicit state if provided,
            # otherwise default to NEW
            raw_state = props.get("state") or "NEW"
            state = str(raw_state).upper()

            # Map optional fields to API schema
            # Normalize work order type; default to TEST_REQUEST and override only when valid
            provided_type = props.get("work_order_type")
            work_order_type = "TEST_REQUEST"
            if provided_type:
                candidate = str(provided_type).upper()
                if candidate == "TEST_REQUEST":
                    work_order_type = candidate
            requested_by = props.get("requested_by")
            assigned_to = props.get("assigned_to") or props.get("assigned_team")
            earliest_start = props.get("scheduled_start") or props.get("earliest_start")
            due_date = props.get("scheduled_end") or props.get("due_date")

            wo_body: Dict[str, Any] = {
                "name": name,
                "description": props.get("description", ""),
                "state": state,
                "type": work_order_type,
                "workspace": self.workspace_id or props.get("workspace"),
                "properties": props.get("properties", {}),
                # Request field is required; include minimal object if not provided
                "request": props.get("request") or {"properties": {}},
            }

            # Only include optional fields when present
            if requested_by:
                wo_body["requestedBy"] = requested_by
            if assigned_to:
                wo_body["assignedTo"] = assigned_to
            if earliest_start:
                wo_body["earliestStartDate"] = earliest_start
            if due_date:
                wo_body["dueDate"] = due_date

            # API expects capitalized collection name
            payload = {"workOrders": [wo_body]}
            resp = make_api_request("POST", url, payload, handle_errors=False)
            resp.raise_for_status()
            data = resp.json()

            # Handle poorly-designed API: 200 response with failures
            has_error = data.get("error") is not None
            created = data.get("createdWorkOrders") or []

            if has_error and not created:
                error_msg = data["error"].get("message", "Unknown error")
                if data["error"].get("innerErrors"):
                    inner = data["error"]["innerErrors"][0]
                    error_msg = inner.get("message", error_msg)
                raise Exception(f"Work order creation failed: {error_msg}")

            if "workOrders" in data and len(data["workOrders"]) > 0:
                return data["workOrders"][0].get("id") or str(hash(name))

            # Handle standard responses
            if created:
                created_id = created[0].get("id")
                if created_id:
                    return str(created_id)

            # Fallback: lookup by name if ID not returned
            looked_up_id = self._get_work_order_by_name(name)
            if looked_up_id:
                return looked_up_id

            # If still no ID, raise exception to ensure we know creation failed
            raise Exception(f"Work order creation returned no ID: {data}")
        except requests.exceptions.HTTPError as http_err:
            # Extract error details from HTTP response
            try:
                error_body = http_err.response.json()  # type: ignore
                error_msg = error_body.get("error", {}).get("message", str(http_err))
                if error_body.get("error", {}).get("innerErrors"):
                    inner = error_body["error"]["innerErrors"][0]
                    error_msg = inner.get("message", error_msg)
                raise Exception(f"Work order creation failed: {error_msg}")
            except Exception:
                raise Exception(f"Work order creation failed: {http_err}")
        except Exception as exc:
            # Wrap other exceptions with context
            raise Exception(f"Failed to create work order '{name}': {exc}") from exc

    def _get_work_order_by_name(self, name: str) -> Optional[str]:
        """Look up work order by name via /niworkorder/v1/query-workorders.

        Returns work order ID if found, None otherwise.
        """
        if not name:
            return None

        try:
            url = f"{get_base_url()}/niworkorder/v1/query-workorders"
            filter_str = f"name == @0"
            if self.workspace_id:
                filter_str += f" and workspace == @1"
            payload = {
                "filter": filter_str,
                "substitutions": ([name, self.workspace_id] if self.workspace_id else [name]),
                "projection": ["ID", "NAME"],
                "take": 100,
            }
            resp = make_api_request("POST", url, payload, handle_errors=False)
            resp.raise_for_status()
            data = resp.json()
            if "workOrders" in data and len(data["workOrders"]) > 0:
                # Find exact case-insensitive match
                for order in data["workOrders"]:
                    if order.get("name", "").lower() == name.lower():
                        return order.get("id")
            return None
        except Exception:
            return None

    def _get_work_order_ids_by_name(self, name: str) -> List[str]:
        """Return all work order IDs with exact name in current workspace."""
        ids: List[str] = []
        if not name:
            return ids
        try:
            url = f"{get_base_url()}/niworkorder/v1/query-workorders"
            filter_str = f"name == @0"
            subs: List[str] = [name]
            if self.workspace_id:
                filter_str += f" and workspace == @1"
                subs.append(self.workspace_id)
            payload = {
                "filter": filter_str,
                "substitutions": subs,
                "projection": ["ID", "NAME"],
                "take": 500,
            }
            resp = make_api_request("POST", url, payload, handle_errors=False)
            resp.raise_for_status()
            data = resp.json()
            for wo in data.get("workOrders", []) or []:
                if str(wo.get("name", "")).lower() == name.lower():
                    wid = wo.get("id")
                    if wid:
                        ids.append(wid)
        except Exception:
            return ids
        return ids

    def _delete_work_order(self, props: Dict[str, Any]) -> Optional[str]:
        """Delete work order via /niworkorder/v1/delete-workorders.

        Returns ID if deleted, None otherwise.
        """
        name = props.get("name", "")
        if not name:
            return None

        work_order_ids = self._get_work_order_ids_by_name(name)
        if not work_order_ids:
            return None

        try:
            url = f"{get_base_url()}/niworkorder/v1/delete-workorders"
            payload = {"ids": work_order_ids}
            resp = make_api_request("POST", url, payload, handle_errors=False)
            resp.raise_for_status()
            return work_order_ids[0]
        except Exception:
            return None

    # ========================================================================
    # Test Result Methods (Tier 3)
    # ========================================================================

    def _create_test_result(self, props: Dict[str, Any]) -> Optional[str]:
        """Create test result via /nitestmonitor/v2/results.

        Returns test result ID if created, None on error.
        """
        program_name = props.get("program_name") or props.get("test_phase") or props.get("name")
        if not program_name:
            return None

        status_str = str(props.get("status", "passed")).upper()
        status_map = {
            "PASSED": "PASSED",
            "FAILED": "FAILED",
            "DONE": "DONE",
            "RUNNING": "RUNNING",
            "SKIPPED": "SKIPPED",
        }
        status_type = status_map.get(status_str, "PASSED")

        try:
            url = f"{get_base_url()}/nitestmonitor/v2/results"
            result_obj: Dict[str, Any] = {
                "programName": program_name,
                "status": {"statusType": status_type, "statusName": status_type.capitalize()},
                "workspace": self.workspace_id or "",
            }
            if "operator" in props:
                result_obj["operator"] = props["operator"]
            if "system_id" in props:
                result_obj["systemId"] = props["system_id"]
            if "serial_number" in props:
                result_obj["serialNumber"] = props["serial_number"]
            if "part_number" in props:
                result_obj["partNumber"] = props["part_number"]
            if "start_time" in props:
                result_obj["startedAt"] = props["start_time"]
            # Merge measurement key-values into properties
            measurements = props.get("measurements", {})
            if isinstance(measurements, dict) and measurements:
                props_map = {str(k): str(v) for k, v in measurements.items()}
                # include existing properties if provided
                if "properties" in props and isinstance(props["properties"], dict):
                    props_map.update({str(k): str(v) for k, v in props["properties"].items()})
                result_obj["properties"] = props_map

            # Add keywords for precise cleanup
            kw: List[str] = []
            if isinstance(props.get("keywords"), list):
                kw.extend([str(x) for x in props.get("keywords", [])])
            if isinstance(props.get("tags"), list):
                kw.extend([str(x) for x in props.get("tags", [])])
            # Always tag results for cleanup, even without an example name
            kw.append("slcli-provisioner")
            if self.example_name:
                kw.append(f"slcli-example:{self.example_name}")
            if kw:
                seen: set[str] = set()
                dedup = []
                for k in kw:
                    if k not in seen:
                        dedup.append(k)
                        seen.add(k)
                result_obj["keywords"] = dedup

            payload = {"results": [result_obj]}
            resp = make_api_request("POST", url, payload, handle_errors=False)
            data = resp.json()
            # Supports 200 (partial) and 201 (success) with the same shape
            results = data.get("results", [])
            if results:
                rid = results[0].get("id")
                return str(rid) if rid else None
            return None
        except Exception:
            return None

    def _get_test_result_by_name(self, name: str) -> Optional[str]:
        """Look up test results by programName via /nitestmonitor/v2/results.

        Returns first matching result ID in the workspace, None otherwise.
        """
        if not name:
            return None
        try:
            url = f"{get_base_url()}/nitestmonitor/v2/results"
            resp = make_api_request("GET", url, {}, handle_errors=False)
            data = resp.json()
            results = data.get("results") or data
            if isinstance(results, list):
                for r in results:
                    if self.workspace_id and str(r.get("workspace", "")) != str(self.workspace_id):
                        continue
                    if str(r.get("programName", "")) == name:
                        rid = r.get("id")
                        if rid:
                            return str(rid)
            return None
        except Exception:
            return None

    def _get_test_result_ids_by_name(self, name: str) -> List[str]:
        """Return all test result IDs with exact programName in current workspace."""
        ids: List[str] = []
        if not name:
            return ids
        try:
            url = f"{get_base_url()}/nitestmonitor/v2/results"
            resp = make_api_request("GET", url, {}, handle_errors=False)
            data = resp.json()
            results = data.get("results") or data
            if isinstance(results, list):
                for r in results:
                    if self.workspace_id and str(r.get("workspace", "")) != str(self.workspace_id):
                        continue
                    if str(r.get("programName", "")) == name:
                        rid = r.get("id")
                        if rid:
                            ids.append(str(rid))
        except Exception:
            return ids
        return ids

    def _delete_test_result(self, props: Dict[str, Any]) -> Optional[str]:
        """Delete test result via /nitestmonitor/v2/delete-results using keyword tags.

        Uses POST /v2/query-results with Dynamic Linq filter to find results by keyword.
        Returns ID if deleted, None otherwise.
        """
        # Build the expected cleanup keyword based on example name
        example_tag = f"slcli-example:{self.example_name}" if self.example_name else None

        try:
            # Build filter to match results with slcli-provisioner keyword
            # Also match example tag if set
            filter_parts = ['keywords.Any(x => x == "slcli-provisioner")']
            if example_tag:
                filter_parts.append(f'keywords.Any(x => x == "{example_tag}")')

            filter_expr = " && ".join(filter_parts)

            # Add workspace filter if set
            if self.workspace_id:
                filter_expr += f' && workspace == "{self.workspace_id}"'

            url = f"{get_base_url()}/nitestmonitor/v2/query-results"
            payload = {
                "filter": filter_expr,
                "take": 1000,
            }

            resp = make_api_request("POST", url, payload, handle_errors=False)
            data = resp.json()
            results = data.get("results", [])

            if not results:
                # If we've already performed the tagged deletion, treat as already deleted
                if self._test_results_deleted:
                    return "__ALREADY_DELETED__"
                return None

            # Extract IDs from matching results
            result_ids: List[str] = []
            for r in results:
                rid = r.get("id")
                if rid:
                    result_ids.append(str(rid))

            if not result_ids:
                if self._test_results_deleted:
                    return "__ALREADY_DELETED__"
                return None

            # Delete all matching results
            delete_url = f"{get_base_url()}/nitestmonitor/v2/delete-results"
            delete_payload = {"ids": result_ids, "deleteSteps": True}
            make_api_request("POST", delete_url, delete_payload, handle_errors=False)
            self._test_results_deleted = True

            # Return a summary string indicating how many results were deleted
            if len(result_ids) == 1:
                return result_ids[0]
            return f"{result_ids[0]} (+{len(result_ids) - 1} more)"
        except Exception:
            return None

    # ========================================================================
    # Data Table Methods (Tier 3)
    # ========================================================================

    def _create_data_table(self, props: Dict[str, Any]) -> Optional[str]:
        """Create data table via /nidataframe/v1/tables.

        Returns table ID if created, None on error.
        """
        name = props.get("name", "")
        if not name:
            return None

        try:
            url = f"{get_base_url()}/nidataframe/v1/tables"
            # Transform columns: convert 'type' to 'dataType' and add first column as INDEX
            columns = props.get("columns", [])
            transformed_cols: list[Dict[str, Any]] = []
            for idx, col in enumerate(columns):
                col_def: Dict[str, Any] = {"name": col.get("name", f"col_{idx}")}
                # Map type -> dataType
                col_type = col.get("type", "STRING").upper()
                if col_type == "TIMESTAMP":
                    col_def["dataType"] = "TIMESTAMP"
                elif col_type == "NUMBER":
                    col_def["dataType"] = "FLOAT64"
                elif col_type == "STRING":
                    col_def["dataType"] = "STRING"
                elif col_type == "INT":
                    col_def["dataType"] = "INT64"
                elif col_type == "BOOL":
                    col_def["dataType"] = "BOOL"
                else:
                    col_def["dataType"] = "STRING"
                # First column is INDEX; rest are NORMAL
                if idx == 0:
                    col_def["columnType"] = "INDEX"
                    # Ensure INDEX has valid type (not FLOAT64)
                    if col_def.get("dataType") == "FLOAT64":
                        # Prefer INT64 for index when numeric
                        col_def["dataType"] = "INT64"
                transformed_cols.append(col_def)

            payload = {
                "name": name,
                "description": props.get("description", ""),
                "columns": transformed_cols,
                "properties": props.get("properties", {}),
            }
            # Add keywords for precise cleanup
            kw: List[str] = []
            if isinstance(props.get("keywords"), list):
                kw.extend([str(x) for x in props.get("keywords", [])])
            if isinstance(props.get("tags"), list):
                kw.extend([str(x) for x in props.get("tags", [])])
            if self.example_name:
                kw.append(f"slcli-example:{self.example_name}")
            if kw:
                seen: set[str] = set()
                dedup = []
                for k in kw:
                    if k not in seen:
                        dedup.append(k)
                        seen.add(k)
                payload["keywords"] = dedup
            if self.workspace_id:
                payload["workspace"] = self.workspace_id
            resp = make_api_request("POST", url, payload, handle_errors=False)
            resp.raise_for_status()
            data = resp.json()
            # Prefer ID from response if present
            if data.get("id"):
                return data.get("id")
            # Fallback: lookup by name if ID not returned
            looked_up_id = self._get_data_table_by_name(name)
            if looked_up_id:
                return looked_up_id
            # If still no ID, return a generated reference (for audit purposes)
            return str(abs(hash(name)) % (10**12))
        except Exception:
            return None

    def _get_data_table_by_name(self, name: str) -> Optional[str]:
        """Look up data table by name via /nidataframe/v1/query-tables.

        Returns table ID if found, None otherwise.
        """
        if not name:
            return None

        try:
            url = f"{get_base_url()}/nidataframe/v1/query-tables"
            filter_str = f"name == @0"
            if self.workspace_id:
                filter_str += f" and workspace == @1"
            payload = {
                "filter": filter_str,
                "substitutions": ([name, self.workspace_id] if self.workspace_id else [name]),
                "projection": ["NAME", "WORKSPACE"],
                "take": 100,
            }
            resp = make_api_request("POST", url, payload, handle_errors=False)
            resp.raise_for_status()
            data = resp.json()
            if "tables" in data and len(data["tables"]) > 0:
                # Find exact case-insensitive match
                for table in data["tables"]:
                    if table.get("name", "").lower() == name.lower():
                        return table.get("id")
            return None
        except Exception:
            return None

    def _get_data_table_ids_by_name(self, name: str) -> List[str]:
        """Return all data table IDs with exact name in current workspace."""
        ids: List[str] = []
        if not name:
            return ids
        try:
            url = f"{get_base_url()}/nidataframe/v1/query-tables"
            filter_str = f"name == @0"
            subs: List[str] = [name]
            if self.workspace_id:
                filter_str += f" and workspace == @1"
                subs.append(self.workspace_id)
            payload = {
                "filter": filter_str,
                "substitutions": subs,
                "projection": ["NAME", "WORKSPACE"],
                "take": 500,
            }
            resp = make_api_request("POST", url, payload, handle_errors=False)
            resp.raise_for_status()
            data = resp.json()
            for table in data.get("tables", []) or []:
                if str(table.get("name", "")).lower() == name.lower():
                    tid = table.get("id")
                    if tid:
                        ids.append(tid)
        except Exception:
            return ids
        return ids

    def _delete_data_table(self, props: Dict[str, Any]) -> Optional[str]:
        """Delete data table via /nidataframe/v1/delete-tables.

        Returns ID if deleted, None otherwise.
        """
        name = props.get("name", "")
        if not name:
            return None

        table_ids = self._get_data_table_ids_by_name(name)
        if not table_ids:
            return None

        try:
            url = f"{get_base_url()}/nidataframe/v1/delete-tables"
            payload = {"ids": table_ids}
            resp = make_api_request("POST", url, payload, handle_errors=False)
            resp.raise_for_status()
            return table_ids[0]
        except Exception:
            return None

    # ========================================================================
    # File Methods (Tier 1 & 3)
    # ========================================================================

    def _create_file(self, props: Dict[str, Any]) -> Optional[str]:
        """Create file via /nifile/v1/service-groups/Default/upload-files (multipart).

        Returns file ID if created, None on error.
        """
        name = props.get("name", "")
        if not name:
            return None

        # Handle as regular file upload
        try:
            url = f"{get_base_url()}/nifile/v1/service-groups/Default/upload-files"

            # Get file content from file_path if provided, otherwise use placeholder
            file_path = props.get("file_path")
            if file_path:
                file_content = self._read_example_file(file_path)
                if file_content is None:
                    return None
                # Extract filename from file_path to preserve extension
                from pathlib import Path

                file_basename = Path(file_path).name
                # Append extension to name if not already present and we have a file_path
                upload_name = name
                if "." not in upload_name and "." in file_basename:
                    upload_name = f"{name}.{file_basename.split('.')[-1]}"
            else:
                # Create minimal file content (placeholder for demo)
                file_content = (f"# {name}\n# Created by SystemLink example provisioner\n").encode(
                    "utf-8"
                )
                upload_name = name

            # Prepare metadata as JSON string
            # File metadata supports Name, description, and custom properties
            metadata = {
                "description": props.get("description", ""),
                "Name": upload_name,  # Use upload_name which includes extension
            }

            # Build cleanup tags and store in properties
            kw: List[str] = []
            if isinstance(props.get("keywords"), list):
                kw.extend([str(x) for x in props.get("keywords", [])])
            if isinstance(props.get("tags"), list):
                kw.extend([str(x) for x in props.get("tags", [])])
            kw.append("slcli-provisioner")
            if self.example_name:
                kw.append(f"slcli-example:{self.example_name}")
            if kw:
                seen: set[str] = set()
                dedup = []
                for k in kw:
                    if k not in seen:
                        dedup.append(k)
                        seen.add(k)
                # Store tags as comma-separated string in a custom property
                metadata["slcli-tags"] = ",".join(dedup)

            # Prepare multipart form data
            files = {
                "file": (
                    upload_name,
                    file_content,
                    props.get("content_type", "application/octet-stream"),
                )
            }
            data = {"metadata": json_module.dumps(metadata)}
            if self.workspace_id:
                data["workspace"] = self.workspace_id
            # Use requests directly for multipart
            import requests

            headers = get_headers()
            resp = requests.post(url, files=files, data=data, headers=headers, timeout=30)
            resp.raise_for_status()
            response_data = resp.json()
            # Extract ID from URI or response
            if "uri" in response_data:
                # URI format: /nifile/v1/service-groups/Default/files/{id}
                uri = response_data["uri"]
                file_id = uri.split("/")[-1]
                return file_id if file_id else None
            # Fallback: return None (files don't support name-based lookup)
            return None
        except Exception:
            return None

    def _read_example_file(self, file_path: str) -> Optional[bytes]:
        """Read a file from the example directory.

        Args:
            file_path: Path relative to example directory

        Returns:
            File contents as bytes, or None if not found.
        """
        from pathlib import Path

        try:
            if self.example_name:
                # Path relative to slcli/examples/{example_name}/
                example_dir = Path(__file__).parent / "examples" / self.example_name
                full_path = example_dir / file_path
            else:
                full_path = Path(file_path)

            if not full_path.exists():
                click.echo(
                    f"Warning: File not found: {full_path}",
                    err=True,
                )
                return None

            with open(full_path, "rb") as f:
                return f.read()
        except FileNotFoundError:
            click.echo(
                f"Warning: File not found: {file_path}",
                err=True,
            )
            return None
        except PermissionError:
            click.echo(
                f"Warning: Permission denied reading file: {file_path}",
                err=True,
            )
            return None
        except Exception as exc:
            click.echo(
                f"Warning: Error reading file {file_path}: {exc}",
                err=True,
            )
            return None

    def _create_notebook(self, props: Dict[str, Any]) -> Optional[str]:
        """Create a notebook from a file path and assign an interface.

        Args:
            props: Resource properties containing:
                - name: Notebook name in SystemLink
                - file_path: Path to .ipynb file relative to example directory
                - notebook_interface: Notebook interface name (e.g., "File Analysis")

        Returns:
            Notebook ID if created, None on error.
        """
        name = props.get("name", "")
        file_path = props.get("file_path", "")
        interface = props.get("notebook_interface", "")

        if not name or not file_path:
            return None
        from pathlib import Path

        try:
            # Resolve file path relative to example directory
            if self.example_name:
                # Path relative to slcli/examples/{example_name}/
                example_dir = Path(__file__).parent / "examples" / self.example_name
                notebook_file = example_dir / file_path
            else:
                notebook_file = Path(file_path)

            if not notebook_file.exists():
                return None

            # Read notebook content
            with open(notebook_file, "rb") as f:
                content = f.read()

            # Create notebook via multipart API
            base_url = get_base_url()
            headers = get_headers()

            # Create metadata following the SystemLink NotebookMetadata model
            metadata: Dict[str, Any] = {
                "name": name,
                "workspace": self.workspace_id or "Default",
                "properties": {},
                "parameters": {},
            }

            # Add example tag for cleanup
            if self.example_name:
                metadata["properties"]["slcli-example"] = self.example_name

            metadata_json = json_module.dumps(metadata, separators=(",", ":"))
            metadata_bytes = metadata_json.encode("utf-8")

            files = {
                "metadata": ("metadata.json", metadata_bytes, "application/json"),
                "content": ("notebook.ipynb", content, "application/octet-stream"),
            }

            # Create the notebook
            notebook_url = f"{base_url}/ninotebook/v1/notebook"
            resp = requests.post(
                notebook_url, headers=headers, files=files, verify=True, timeout=30
            )
            resp.raise_for_status()
            response_data = resp.json()
            notebook_id = response_data.get("id")

            if not notebook_id:
                return None

            # Assign the interface
            if interface:
                # Merge interface with existing properties to preserve slcli-example tag
                updated_properties = metadata["properties"].copy()
                updated_properties["interface"] = interface

                interface_metadata = {
                    "name": name,
                    "workspace": self.workspace_id or "Default",
                    "properties": updated_properties,
                }

                update_url = f"{base_url}/ninotebook/v1/notebook/{notebook_id}"
                update_files = {
                    "metadata": (
                        "metadata.json",
                        json_module.dumps(interface_metadata, separators=(",", ":")).encode(
                            "utf-8"
                        ),
                        "application/json",
                    )
                }

                resp = requests.put(
                    update_url, headers=headers, files=update_files, verify=True, timeout=30
                )
                resp.raise_for_status()

            return notebook_id
        except FileNotFoundError:
            click.echo(
                f"Warning: Notebook file not found: {file_path}",
                err=True,
            )
            return None
        except Exception as exc:
            click.echo(
                f"Warning: Failed to create notebook {name}: {exc}",
                err=True,
            )
            return None

    def _get_file_by_name(self, name: str) -> Optional[str]:
        """Look up file by name.

        Returns file ID if found, None otherwise.
        Note: Files do not support name-based lookup; always returns None.
        """
        # Files endpoint doesn't support name filtering in LINQ;
        # return None to skip lookups
        return None

    def _delete_file(self, props: Dict[str, Any]) -> Optional[str]:
        """Delete files via /nifile/v1/service-groups/Default/delete-files using tags.

        Returns an ID summary if deleted, None otherwise.
        """
        example_tag = f"slcli-example:{self.example_name}" if self.example_name else None

        try:
            deleted_ids: List[str] = []

            # Try to query files by workspace
            if self.workspace_id and example_tag:
                # Simple query by workspace only - custom properties may not be queryable
                filter_expr = f'workspace == "{self.workspace_id}"'

                query_url = f"{get_base_url()}/nifile/v1/service-groups/Default/query-files-linq"
                query_payload = {"filter": filter_expr, "take": 1000}
                query_resp = make_api_request("POST", query_url, query_payload, handle_errors=False)
                files = query_resp.json().get("availableFiles", [])

                # Filter client-side by checking metadata for our tags
                file_ids: List[str] = []
                for file_item in files:
                    # Check if this file has our example tag in metadata
                    props_meta = file_item.get("properties", {})
                    tags_str = props_meta.get("slcli-tags", "")
                    if example_tag in tags_str and "slcli-provisioner" in tags_str:
                        fid = file_item.get("id")
                        if fid:
                            file_ids.append(str(fid))

                if file_ids:
                    delete_url = f"{get_base_url()}/nifile/v1/service-groups/Default/delete-files"
                    delete_payload = {"ids": file_ids}
                    make_api_request("POST", delete_url, delete_payload, handle_errors=False)
                    deleted_ids.extend(file_ids)
                    self._files_deleted = True

            if not deleted_ids:
                if self._files_deleted:
                    return "__ALREADY_DELETED__"
                return None

            if len(deleted_ids) == 1:
                return deleted_ids[0]
            return f"{deleted_ids[0]} (+{len(deleted_ids) - 1} more)"
        except Exception:
            return None

    def _delete_notebook(self, props: Dict[str, Any]) -> Optional[str]:
        """Delete notebooks via /ninotebook/v1/notebook using tags.

        Returns an ID summary if deleted, None otherwise.
        """
        example_tag = f"slcli-example:{self.example_name}" if self.example_name else None

        try:
            deleted_ids: List[str] = []

            # Query notebooks by workspace and filter client-side
            # Note: Notebook API doesn't support querying on custom properties
            if example_tag and self.workspace_id:
                base_url = get_base_url()

                # Extract example name from tag
                example_name = example_tag.split(":")[-1]

                # Query by workspace only
                filter_str = f'workspace == "{self.workspace_id}"'
                payload: Dict[str, Any] = {"filter": filter_str, "take": 100}
                resp = make_api_request(
                    "POST",
                    f"{base_url}/ninotebook/v1/notebook/query",
                    payload,
                    handle_errors=False,
                )
                notebooks = resp.json().get("notebooks", [])

                # Filter client-side by checking properties for our example tag
                for notebook in notebooks:
                    props_meta = notebook.get("properties", {})
                    if props_meta.get("slcli-example") == example_name:
                        nb_id = notebook.get("id")
                        if nb_id:
                            try:
                                # Delete the notebook
                                delete_nb_url = f"{base_url}/ninotebook/v1/notebook/{nb_id}"
                                make_api_request("DELETE", delete_nb_url, handle_errors=False)
                                deleted_ids.append(nb_id)
                            except Exception:
                                pass  # Continue deleting other notebooks

                # Mark notebooks as deleted after bulk operation
                if deleted_ids:
                    self._notebooks_deleted = True

            if not deleted_ids:
                if self._notebooks_deleted:
                    return "__ALREADY_DELETED__"
                return None

            if len(deleted_ids) == 1:
                return deleted_ids[0]
            return f"{deleted_ids[0]} (+{len(deleted_ids) - 1} more)"
        except Exception:
            return None
