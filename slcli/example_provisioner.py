"""Provision SLE resources from example configurations.

Implements resource provisioning with real API calls to SystemLink Enterprise.
Supports dry-run mode for validation without creating resources.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple

from .utils import get_base_url, make_api_request


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
        id_map: Dict[str, str] = {}

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

                res = self._provision_resource(resource, id_map)
                results.append(res)

                # Record server_id for reference substitution in subsequent resources
                if res.action == ProvisioningAction.CREATED and res.server_id:
                    id_map[res.id_reference] = res.server_id
                elif res.action == ProvisioningAction.SKIPPED:
                    # Even in dry-run, populate a predictable simulated ID to enable
                    # reference substitution demonstrations in logs/tests.
                    id_map[res.id_reference] = f"dryrun-{res.id_reference}"

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
            return ProvisioningResult(
                id_reference=rid,
                resource_type=rtype,
                resource_name=rname,
                action=ProvisioningAction.CREATED,
                server_id=server_id,
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
        for key in ["partNumber", "family", "properties", "fileIds"]:
            if key in props:
                product_obj[key] = props[key]

        # Ensure part number is present to avoid silent failures
        if "partNumber" not in product_obj:
            fallback_pn = str(product_obj.get("name", "SLCLI-PRODUCT")).replace(" ", "-")
            product_obj["partNumber"] = fallback_pn

        # Tag resource with example name for cleanup
        if self.example_name:
            keywords = props.get("keywords", [])
            if not isinstance(keywords, list):
                keywords = []
            keywords.append(f"slcli-example:{self.example_name}")
            product_obj["keywords"] = keywords

        # Wrap in products array per API schema
        payload = {"products": [product_obj]}
        resp = make_api_request("POST", url, payload, handle_errors=False)
        data = resp.json()
        # Response is { products: [...] }
        products = data.get("products", [])
        if products and len(products) > 0:
            return str(products[0].get("id", ""))
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
            pass
        return None

    def _create_system(self, props: Dict[str, Any]) -> str:
        """Create virtual system via Systems Management API and return server ID.

        Uses POST /nisysmgmt/v1/virtual with request body:
        { alias, workspace }
        """
        url = f"{get_base_url()}/nisysmgmt/v1/virtual"
        # Systems Management API uses 'alias' not 'name'
        payload = {
            "alias": props.get("name", "Unknown System"),
            "workspace": self.workspace_id or "",
        }
        resp = make_api_request("POST", url, payload, handle_errors=False)
        data = resp.json()
        # Response is { minionId }
        return str(data.get("minionId", ""))

    def _get_system_by_name(self, name: str) -> Optional[str]:
        """Find a system by exact alias within workspace. Returns ID or None.

        Uses Systems Management API: POST /nisysmgmt/v1/query-systems with QuerySystemsRequest.
        Filters client-side on:
        - `alias` equals `name`
        - `workspace` equals `self.workspace_id` (if set)
        """
        try:
            url = f"{get_base_url()}/nisysmgmt/v1/query-systems"
            # Build a minimal query: filter by alias; projection narrows fields
            filter_expr = f'alias = "{name}"'
            payload = {
                "skip": 0,
                "take": 100,
                "filter": filter_expr,
                "projection": "new(id,alias,workspace)",
                "orderBy": "alias",
            }
            resp = make_api_request("POST", url, payload, handle_errors=False)
            items = resp.json()
            # Response is an array of SystemsResponse objects, each with 'data' dict
            if isinstance(items, list):
                for item in items:
                    sys = item.get("data", item)
                    alias = str(sys.get("alias", ""))
                    if alias != name:
                        continue
                    if self.workspace_id and str(sys.get("workspace", "")) != str(
                        self.workspace_id
                    ):
                        continue
                    return str(sys.get("id", "")) or None
        except Exception:
            pass
        return None

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
        # Response is { assets: [...] }
        assets = data.get("assets", [])
        if assets and len(assets) > 0:
            # Prefer 'id', fallback to 'assetIdentifier' if provided
            aid = assets[0].get("id") or assets[0].get("assetIdentifier") or ""
            return str(aid)
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
        # Response is { assets: [...] }
        assets = data.get("assets", [])
        if assets and len(assets) > 0:
            # Prefer 'id', fallback to 'assetIdentifier' if provided
            aid = assets[0].get("id") or assets[0].get("assetIdentifier") or ""
            return str(aid)
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
            pass
        return None

    def _create_testtemplate(self, props: Dict[str, Any]) -> str:
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
            "workspace": self.workspace_id or "",
        }
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

        # Wrap in workItemTemplates array per API schema
        payload = {"workItemTemplates": [template_obj]}
        resp = make_api_request("POST", url, payload, handle_errors=False)
        data = resp.json()
        # Response is { createdWorkItemTemplates: [...] }
        templates = data.get("createdWorkItemTemplates", [])
        if templates and len(templates) > 0:
            return str(templates[0].get("id", ""))
        return ""

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
        """Delete product via /nitestmonitor/v2/delete-products.

        Returns ID if deleted, None otherwise.
        """
        name = props.get("name", "")
        if not name:
            return None

        product_id = self._get_product_by_name(name)
        if not product_id:
            # Product doesn't exist
            return None

        try:
            url = f"{get_base_url()}/nitestmonitor/v2/delete-products"
            payload = {"ids": [product_id]}
            resp = make_api_request("POST", url, payload, handle_errors=False)
            resp.raise_for_status()
            return product_id
        except Exception:
            return None

    def _delete_system(self, props: Dict[str, Any]) -> Optional[str]:
        """Delete system via /nisysmgmt/v1/remove-systems.

        Returns ID if deleted, None otherwise.
        """
        name = props.get("name", "")
        if not name:
            return None

        system_id = self._get_system_by_name(name)
        if not system_id:
            # System doesn't exist
            return None

        try:
            url = f"{get_base_url()}/nisysmgmt/v1/remove-systems"
            payload = {"tgt": [system_id], "force": True}
            resp = make_api_request("POST", url, payload, handle_errors=False)
            resp.raise_for_status()
            return system_id
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
            url = f"{get_base_url()}/niworkorder/v1/workflows"
            payload = {
                "workflows": [
                    {
                        "name": name,
                        "description": props.get("description", ""),
                        "properties": props.get("properties", {}),
                    }
                ]
            }
            resp = make_api_request("POST", url, payload, handle_errors=False)
            resp.raise_for_status()
            data = resp.json()
            if "workflows" in data and len(data["workflows"]) > 0:
                return data["workflows"][0].get("id") or str(hash(name))  # Fallback to hash
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
                "filter": f"Name == '{name}'",
                "projection": "new(id,name)",
            }
            resp = make_api_request("POST", url, payload, handle_errors=False)
            resp.raise_for_status()
            data = resp.json()
            if "workflows" in data and len(data["workflows"]) > 0:
                return data["workflows"][0].get("id")
            return None
        except Exception:
            return None

    def _delete_workflow(self, props: Dict[str, Any]) -> Optional[str]:
        """Delete workflow via /niworkorder/v1/delete-workflows.

        Returns ID if deleted, None otherwise.
        """
        name = props.get("name", "")
        if not name:
            return None

        workflow_id = self._get_workflow_by_name(name)
        if not workflow_id:
            return None

        try:
            url = f"{get_base_url()}/niworkorder/v1/delete-workflows"
            payload = {"ids": [workflow_id]}
            resp = make_api_request("POST", url, payload, handle_errors=False)
            resp.raise_for_status()
            return workflow_id
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
            payload = {
                "workitems": [
                    {
                        "name": name,
                        "description": props.get("description", ""),
                        "properties": props.get("properties", {}),
                    }
                ]
            }
            resp = make_api_request("POST", url, payload, handle_errors=False)
            resp.raise_for_status()
            data = resp.json()
            if "workitems" in data and len(data["workitems"]) > 0:
                return data["workitems"][0].get("id") or str(hash(name))
            return None
        except Exception:
            return None

    def _get_work_item_by_name(self, name: str) -> Optional[str]:
        """Look up work item by name via /niworkitem/v1/query-workitems.

        Returns work item ID if found, None otherwise.
        """
        if not name:
            return None

        try:
            url = f"{get_base_url()}/niworkitem/v1/query-workitems"
            payload = {
                "filter": f"Name == '{name}'",
                "projection": "new(id,name)",
            }
            resp = make_api_request("POST", url, payload, handle_errors=False)
            resp.raise_for_status()
            data = resp.json()
            if "workitems" in data and len(data["workitems"]) > 0:
                return data["workitems"][0].get("id")
            return None
        except Exception:
            return None

    def _delete_work_item(self, props: Dict[str, Any]) -> Optional[str]:
        """Delete work item via /niworkitem/v1/delete-workitems.

        Returns ID if deleted, None otherwise.
        """
        name = props.get("name", "")
        if not name:
            return None

        work_item_id = self._get_work_item_by_name(name)
        if not work_item_id:
            return None

        try:
            url = f"{get_base_url()}/niworkitem/v1/delete-workitems"
            payload = {"ids": [work_item_id]}
            resp = make_api_request("POST", url, payload, handle_errors=False)
            resp.raise_for_status()
            return work_item_id
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
            payload = {
                "workorders": [
                    {
                        "name": name,
                        "description": props.get("description", ""),
                        "properties": props.get("properties", {}),
                    }
                ]
            }
            resp = make_api_request("POST", url, payload, handle_errors=False)
            resp.raise_for_status()
            data = resp.json()
            if "workorders" in data and len(data["workorders"]) > 0:
                return data["workorders"][0].get("id") or str(hash(name))
            return None
        except Exception:
            return None

    def _get_work_order_by_name(self, name: str) -> Optional[str]:
        """Look up work order by name via /niworkorder/v1/query-workorders.

        Returns work order ID if found, None otherwise.
        """
        if not name:
            return None

        try:
            url = f"{get_base_url()}/niworkorder/v1/query-workorders"
            payload = {
                "filter": f"Name == '{name}'",
                "projection": "new(id,name)",
            }
            resp = make_api_request("POST", url, payload, handle_errors=False)
            resp.raise_for_status()
            data = resp.json()
            if "workorders" in data and len(data["workorders"]) > 0:
                return data["workorders"][0].get("id")
            return None
        except Exception:
            return None

    def _delete_work_order(self, props: Dict[str, Any]) -> Optional[str]:
        """Delete work order via /niworkorder/v1/delete-workorders.

        Returns ID if deleted, None otherwise.
        """
        name = props.get("name", "")
        if not name:
            return None

        work_order_id = self._get_work_order_by_name(name)
        if not work_order_id:
            return None

        try:
            url = f"{get_base_url()}/niworkorder/v1/delete-workorders"
            payload = {"ids": [work_order_id]}
            resp = make_api_request("POST", url, payload, handle_errors=False)
            resp.raise_for_status()
            return work_order_id
        except Exception:
            return None

    # ========================================================================
    # Test Result Methods (Tier 3)
    # ========================================================================

    def _create_test_result(self, props: Dict[str, Any]) -> Optional[str]:
        """Create test result via /niworkitem/v1/test-results.

        Returns test result ID if created, None on error.
        """
        name = props.get("name", "")
        if not name:
            return None

        try:
            url = f"{get_base_url()}/niworkitem/v1/test-results"
            payload = {
                "results": [
                    {
                        "name": name,
                        "description": props.get("description", ""),
                        "properties": props.get("properties", {}),
                    }
                ]
            }
            resp = make_api_request("POST", url, payload, handle_errors=False)
            resp.raise_for_status()
            data = resp.json()
            if "results" in data and len(data["results"]) > 0:
                return data["results"][0].get("id") or str(hash(name))
            return None
        except Exception:
            return None

    def _get_test_result_by_name(self, name: str) -> Optional[str]:
        """Look up test result by name via /niworkitem/v1/query-test-results.

        Returns test result ID if found, None otherwise.
        """
        if not name:
            return None

        try:
            url = f"{get_base_url()}/niworkitem/v1/query-test-results"
            payload = {
                "filter": f"Name == '{name}'",
                "projection": "new(id,name)",
            }
            resp = make_api_request("POST", url, payload, handle_errors=False)
            resp.raise_for_status()
            data = resp.json()
            if "results" in data and len(data["results"]) > 0:
                return data["results"][0].get("id")
            return None
        except Exception:
            return None

    def _delete_test_result(self, props: Dict[str, Any]) -> Optional[str]:
        """Delete test result via /niworkitem/v1/delete-test-results.

        Returns ID if deleted, None otherwise.
        """
        name = props.get("name", "")
        if not name:
            return None

        result_id = self._get_test_result_by_name(name)
        if not result_id:
            return None

        try:
            url = f"{get_base_url()}/niworkitem/v1/delete-test-results"
            payload = {"ids": [result_id]}
            resp = make_api_request("POST", url, payload, handle_errors=False)
            resp.raise_for_status()
            return result_id
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
            payload = {
                "name": name,
                "description": props.get("description", ""),
                "columns": props.get("columns", []),
                "properties": props.get("properties", {}),
            }
            resp = make_api_request("POST", url, payload, handle_errors=False)
            resp.raise_for_status()
            data = resp.json()
            return data.get("id") or str(hash(name))
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
            payload = {
                "filter": f"Name == '{name}'",
                "projection": "new(id,name)",
            }
            resp = make_api_request("POST", url, payload, handle_errors=False)
            resp.raise_for_status()
            data = resp.json()
            if "tables" in data and len(data["tables"]) > 0:
                return data["tables"][0].get("id")
            return None
        except Exception:
            return None

    def _delete_data_table(self, props: Dict[str, Any]) -> Optional[str]:
        """Delete data table via /nidataframe/v1/delete-tables.

        Returns ID if deleted, None otherwise.
        """
        name = props.get("name", "")
        if not name:
            return None

        table_id = self._get_data_table_by_name(name)
        if not table_id:
            return None

        try:
            url = f"{get_base_url()}/nidataframe/v1/delete-tables"
            payload = {"ids": [table_id]}
            resp = make_api_request("POST", url, payload, handle_errors=False)
            resp.raise_for_status()
            return table_id
        except Exception:
            return None

    # ========================================================================
    # File Methods (Tier 1 & 3)
    # ========================================================================

    def _create_file(self, props: Dict[str, Any]) -> Optional[str]:
        """Create file via /nifile/v1/files.

        Returns file ID if created, None on error.
        """
        name = props.get("name", "")
        if not name:
            return None

        try:
            url = f"{get_base_url()}/nifile/v1/files"
            payload = {
                "name": name,
                "description": props.get("description", ""),
                "content_type": props.get("content_type", "application/octet-stream"),
                "properties": props.get("properties", {}),
            }
            resp = make_api_request("POST", url, payload, handle_errors=False)
            resp.raise_for_status()
            data = resp.json()
            return data.get("id") or str(hash(name))
        except Exception:
            return None

    def _get_file_by_name(self, name: str) -> Optional[str]:
        """Look up file by name via /nifile/v1/query-files.

        Returns file ID if found, None otherwise.
        """
        if not name:
            return None

        try:
            url = f"{get_base_url()}/nifile/v1/query-files"
            payload = {
                "filter": f"Name == '{name}'",
                "projection": "new(id,name)",
            }
            resp = make_api_request("POST", url, payload, handle_errors=False)
            resp.raise_for_status()
            data = resp.json()
            if "files" in data and len(data["files"]) > 0:
                return data["files"][0].get("id")
            return None
        except Exception:
            return None

    def _delete_file(self, props: Dict[str, Any]) -> Optional[str]:
        """Delete file via /nifile/v1/delete-files.

        Returns ID if deleted, None otherwise.
        """
        name = props.get("name", "")
        if not name:
            return None

        file_id = self._get_file_by_name(name)
        if not file_id:
            return None

        try:
            url = f"{get_base_url()}/nifile/v1/delete-files"
            payload = {"ids": [file_id]}
            resp = make_api_request("POST", url, payload, handle_errors=False)
            resp.raise_for_status()
            return file_id
        except Exception:
            return None
