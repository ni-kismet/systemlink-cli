"""Provision SLE resources from example configurations.

Implements resource provisioning with real API calls to SystemLink Enterprise.
Supports dry-run mode for validation without creating resources.
"""

from __future__ import annotations

import json as json_module
import urllib.parse
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
    details: Optional[Dict[str, Any]] = None


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
        self._last_resource_details: Optional[Dict[str, Any]] = None

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
        resources_by_reference = {
            str(resource.get("id_reference")): resource
            for resource in resources
            if isinstance(resource, dict) and resource.get("id_reference")
        }

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
                    "state": self._delete_state,
                    "tag": self._delete_tag,
                    "specification": self._delete_specification,
                    "feed": self._delete_feed,
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

                delete_props = resource.get("properties", {})
                if not isinstance(delete_props, dict):
                    delete_props = {}
                delete_props = dict(delete_props)
                delete_props["name"] = rname
                delete_props = self._resolve_delete_props(delete_props, resources_by_reference)
                server_id = delete_fn(delete_props)
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
        self._last_resource_details = None

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
            "state": self._create_state,
            "tag": self._create_tag,
            "specification": self._create_specification,
            "feed": self._create_feed,
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
                existing_id = self._get_test_result_by_properties(props_with_name)
            elif rtype == "data_table":
                ownership_marker = self._data_table_ownership_marker(props_with_name)
                existing_id = self._get_data_table_by_name(
                    rname,
                    ownership_marker=ownership_marker,
                )
                if not existing_id and ownership_marker and self._get_data_table_by_name(rname):
                    return ProvisioningResult(
                        id_reference=rid,
                        resource_type=rtype,
                        resource_name=rname,
                        action=ProvisioningAction.FAILED,
                        error="Existing table does not have the expected ownership marker",
                    )
            elif rtype == "file":
                existing_id = self._get_file_by_name(rname)
            elif rtype == "state":
                existing_id = self._get_state_by_name(
                    rname,
                    ownership_marker=self._resource_ownership_marker(props_with_name),
                )
            elif rtype == "tag":
                existing_id = self._get_tag_by_path(rname)
            elif rtype == "specification":
                existing_id = self._get_specification_by_key(props_with_name)
            elif rtype == "feed":
                existing_id = self._get_feed_by_name(
                    rname,
                    str(props_with_name.get("platform", "")) or None,
                    ownership_marker=self._resource_ownership_marker(props_with_name),
                )

            if existing_id:
                if rtype == "data_table":
                    try:
                        self._ensure_data_table_rows(str(existing_id), props_with_name)
                    except Exception as exc:
                        return ProvisioningResult(
                            id_reference=rid,
                            resource_type=rtype,
                            resource_name=rname,
                            action=ProvisioningAction.FAILED,
                            server_id=str(existing_id),
                            error=str(exc),
                            details=self._last_resource_details,
                        )
                elif rtype == "tag":
                    try:
                        self._write_tag_history(props_with_name)
                    except Exception as exc:
                        return ProvisioningResult(
                            id_reference=rid,
                            resource_type=rtype,
                            resource_name=rname,
                            action=ProvisioningAction.FAILED,
                            server_id=str(existing_id),
                            error=str(exc),
                        )
                # Resource already exists, skip creation
                return ProvisioningResult(
                    id_reference=rid,
                    resource_type=rtype,
                    resource_name=rname,
                    action=ProvisioningAction.SKIPPED,
                    server_id=existing_id,
                    error="Resource already exists",
                    details=self._last_resource_details,
                )

            self._last_resource_details = None
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
                    details=self._last_resource_details,
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

    def _resolve_delete_props(
        self, props: Dict[str, Any], resources_by_reference: Dict[str, Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Resolve resource references needed by property-dependent delete handlers."""
        resolved = dict(props)
        for key in ("product_id", "productId"):
            value = resolved.get(key)
            if not isinstance(value, str) or not value.startswith("${") or not value.endswith("}"):
                continue
            reference = value[2:-1]
            referenced_resource = resources_by_reference.get(reference)
            if not referenced_resource or referenced_resource.get("type") != "product":
                continue
            product_id = self._get_product_by_name(str(referenced_resource.get("name", "")))
            if product_id:
                resolved[key] = product_id
        return resolved

    @staticmethod
    def _deduplicate_keywords(keywords: List[str]) -> List[str]:
        """Return deduplicated keywords preserving insertion order."""
        seen: set[str] = set()
        result = []
        for kw in keywords:
            if kw not in seen:
                result.append(kw)
                seen.add(kw)
        return result

    def _resource_ownership_marker(self, props: Dict[str, Any]) -> Optional[str]:
        """Return the configured or example-derived ownership marker."""
        marker = props.get("ownership_marker")
        resource_properties = props.get("properties")
        if marker is None and isinstance(resource_properties, dict):
            marker = resource_properties.get("ownership_marker")
        if marker:
            return str(marker)
        if self.example_name:
            return f"slcli-example:{self.example_name}"
        return None

    def _create_state(self, props: Dict[str, Any]) -> Optional[str]:
        """Create a systems state and return its server ID."""
        payload: Dict[str, Any] = {
            "name": props.get("name", ""),
            "distribution": props.get("distribution", ""),
            "architecture": props.get("architecture", ""),
        }
        if self.workspace_id:
            payload["workspace"] = self.workspace_id

        for source_key, api_key in (
            ("description", "description"),
            ("feeds", "feeds"),
            ("packages", "packages"),
            ("system_image", "systemImage"),
            ("systemImage", "systemImage"),
        ):
            if source_key in props:
                payload[api_key] = props[source_key]

        state_properties = props.get("properties")
        if isinstance(state_properties, dict):
            state_properties = dict(state_properties)
        else:
            state_properties = {}
        ownership_marker = self._resource_ownership_marker(props)
        if ownership_marker:
            state_properties.setdefault("slcli-example", ownership_marker)
        if state_properties:
            payload["properties"] = state_properties

        resp = make_api_request(
            "POST",
            f"{get_base_url()}/nisystemsstate/v1/states",
            payload,
            handle_errors=False,
        )
        data = resp.json()
        if not isinstance(data, dict) or not data.get("id"):
            return None
        return str(data["id"])

    def _get_state_by_name(
        self, name: str, ownership_marker: Optional[str] = None
    ) -> Optional[str]:
        """Find a state by exact name and workspace."""
        if not ownership_marker:
            return None

        url = f"{get_base_url()}/nisystemsstate/v1/states?Skip=0&Take=1000"
        if self.workspace_id:
            url += f"&Workspace={self.workspace_id}"
        resp = make_api_request("GET", url, payload=None, handle_errors=False)
        data = resp.json()
        states = data.get("states", []) if isinstance(data, dict) else []
        if not isinstance(states, list):
            return None

        for state in states:
            if not isinstance(state, dict) or state.get("name") != name:
                continue
            if self.workspace_id and state.get("workspace") != self.workspace_id:
                continue
            state_properties = state.get("properties", {})
            if not isinstance(state_properties, dict):
                continue
            if str(state_properties.get("slcli-example", "")) != ownership_marker:
                continue
            state_id = state.get("id")
            if state_id:
                return str(state_id)
        return None

    def _delete_state(self, props: Dict[str, Any]) -> Optional[str]:
        """Delete a state by exact name and return its server ID."""
        state_id = self._get_state_by_name(
            str(props.get("name", "")),
            ownership_marker=self._resource_ownership_marker(props),
        )
        if not state_id:
            return None

        make_api_request(
            "DELETE",
            f"{get_base_url()}/nisystemsstate/v1/states/{state_id}",
            payload=None,
            handle_errors=False,
        )
        return state_id

    def _tag_url(self, path: str) -> str:
        """Build the metadata URL for a workspace-scoped tag path."""
        workspace_path = f"{self.workspace_id}/" if self.workspace_id else ""
        encoded_path = urllib.parse.quote(path, safe="")
        return f"{get_base_url()}/nitag/v2/tags/{workspace_path}{encoded_path}"

    def _create_tag(self, props: Dict[str, Any]) -> Optional[str]:
        """Create tag metadata and return its path as the resource ID."""
        path = str(props.get("name", ""))
        payload: Dict[str, Any] = {
            "path": path,
            "type": props.get("type", props.get("tag_type", "")),
            "workspace": self.workspace_id,
            "collectAggregates": bool(props.get("collectAggregates", False)),
        }
        for key in ("keywords",):
            if key in props:
                payload[key] = props[key]
        tag_properties: Dict[str, Any] = {}
        if isinstance(props.get("properties"), dict):
            tag_properties.update(props["properties"])
        if props.get("history"):
            tag_properties["nitagRetention"] = str(
                props.get("retention", tag_properties.get("nitagRetention", "PERMANENT"))
            ).upper()
        if tag_properties:
            payload["properties"] = tag_properties

        make_api_request("PUT", self._tag_url(path), payload=payload, handle_errors=False)
        self._write_tag_history(props)
        return path or None

    def _write_tag_history(self, props: Dict[str, Any]) -> None:
        """Write configured timestamped values to a tag."""
        history = props.get("history", [])
        if history is None:
            return
        if not isinstance(history, list):
            raise ValueError("Tag history must be a list")
        if not history:
            return

        path = str(props.get("name", ""))
        tag_type = str(props.get("type", props.get("tag_type", "")))
        if not path or not tag_type:
            raise ValueError("Tag history requires a tag name and type")

        values: List[Dict[str, Any]] = []
        for index, entry in enumerate(history):
            if not isinstance(entry, dict):
                raise ValueError(f"Tag history entry {index} must be an object")
            timestamp = entry.get("timestamp")
            if not timestamp:
                raise ValueError(f"Tag history entry {index} is missing timestamp")
            if "value" not in entry or entry["value"] is None:
                raise ValueError(f"Tag history entry {index} is missing value")

            value = entry["value"]
            value_text = str(value).lower() if isinstance(value, bool) else str(value)
            value_entry: Dict[str, Any] = {
                "path": path,
                "value": value_text,
                "timestamp": str(timestamp),
            }
            if self.workspace_id:
                value_entry["workspace"] = self.workspace_id
            values.append(value_entry)

        configured_properties = props.get("properties")
        configured_retention = (
            configured_properties.get("nitagRetention")
            if isinstance(configured_properties, dict)
            else None
        )
        retention = str(props.get("retention", configured_retention or "PERMANENT")).upper()
        tag_metadata: Dict[str, Any] = {
            "path": path,
            "type": tag_type,
            "workspace": self.workspace_id,
            "properties": {"nitagRetention": retention},
        }

        base_url = get_base_url()
        make_api_request(
            "POST",
            f"{base_url}/nitag/v2/tags",
            payload=tag_metadata,
            handle_errors=False,
        )
        query: Dict[str, Any] = {
            "path": path,
            "startTime": "0001-01-01T00:00:00Z",
            "endTime": "9999-12-31T23:59:59Z",
            "take": max(len(values), 1000),
            "sortOrder": "ASCENDING",
        }
        if self.workspace_id:
            query["workspace"] = self.workspace_id
        history_url = f"{base_url}/nitaghistorian/v2/tags/query-history"
        existing_response = make_api_request(
            "POST", history_url, payload=query, handle_errors=False
        )
        existing_data = existing_response.json()
        existing_values = existing_data.get("values", []) if isinstance(existing_data, dict) else []
        existing_keys = {
            (
                str(item.get("timestamp", "")).replace(".000000", ""),
                str(item.get("value")),
            )
            for item in existing_values
            if isinstance(item, dict)
        }
        pending_values = [
            item
            for item in values
            if (
                item["timestamp"].replace(".000000", ""),
                item["value"],
            )
            not in existing_keys
        ]
        timestamped_values: List[Dict[str, Any]] = []
        for item in pending_values:
            timestamped_values.append(
                {
                    "value": {"type": tag_type, "value": item["value"]},
                    "timestamp": item["timestamp"],
                }
            )
        update_url = f"{base_url}/nitag/v2/tags/{urllib.parse.quote(path, safe='')}/update-values"
        if self.workspace_id:
            update_url = f"{update_url}?workspace={urllib.parse.quote(self.workspace_id, safe='')}"
        if timestamped_values:
            make_api_request(
                "POST",
                update_url,
                payload=timestamped_values,
                handle_errors=False,
            )

        response = make_api_request("POST", history_url, payload=query, handle_errors=False)
        response_data = response.json()
        recorded_values = response_data.get("values", []) if isinstance(response_data, dict) else []
        recorded = {
            (
                str(item.get("timestamp", "")).replace(".000000", ""),
                str(item.get("value")),
            )
            for item in recorded_values
            if isinstance(item, dict)
        }
        expected = {(item["timestamp"], item["value"]) for item in values}
        if not expected.issubset(recorded):
            raise RuntimeError(
                "history: unsupported - Tag Historian did not retain all configured values"
            )

    def _get_tag_by_path(self, path: str) -> Optional[str]:
        """Return a tag path when metadata exists, otherwise None."""
        try:
            resp = make_api_request("GET", self._tag_url(path), payload=None, handle_errors=False)
            data = resp.json()
            return path if isinstance(data, dict) and data.get("path") == path else None
        except Exception:
            return None

    def _delete_tag(self, props: Dict[str, Any]) -> Optional[str]:
        """Delete tag metadata by path and return that path."""
        path = str(props.get("name", ""))
        if not self._get_tag_by_path(path):
            return None
        make_api_request("DELETE", self._tag_url(path), payload=None, handle_errors=False)
        return path or None

    @staticmethod
    def _spec_product_id(props: Dict[str, Any]) -> Optional[str]:
        """Read a specification product reference from config properties."""
        product_id = props.get("productId", props.get("product_id"))
        return str(product_id) if product_id else None

    @staticmethod
    def _spec_id(props: Dict[str, Any]) -> str:
        """Read a specification identifier, defaulting to its resource name."""
        return str(props.get("specId", props.get("spec_id", props.get("name", ""))))

    def _create_specification(self, props: Dict[str, Any]) -> Optional[str]:
        """Create one specification through the bulk specification endpoint."""
        product_id = self._spec_product_id(props)
        if not product_id:
            return None

        payload: Dict[str, Any] = {
            "productId": product_id,
            "specId": self._spec_id(props),
            "type": str(props.get("type", props.get("spec_type", ""))).upper(),
        }
        for api_key, source_keys in {
            "name": ("name",),
            "category": ("category",),
            "symbol": ("symbol",),
            "block": ("block",),
            "unit": ("unit",),
            "limit": ("limit",),
            "conditions": ("conditions",),
            "keywords": ("keywords",),
            "properties": ("properties",),
            "workspace": ("workspace",),
        }.items():
            for source_key in source_keys:
                if source_key in props:
                    payload[api_key] = props[source_key]
                    break
        if "workspace" not in payload and self.workspace_id:
            payload["workspace"] = self.workspace_id

        resp = make_api_request(
            "POST",
            f"{get_base_url()}/nispec/v1/specs",
            payload={"specs": [payload]},
            handle_errors=False,
        )
        data = resp.json()
        created_specs = data.get("createdSpecs", []) if isinstance(data, dict) else []
        if isinstance(created_specs, list) and created_specs:
            created = created_specs[0]
            if isinstance(created, dict) and created.get("id"):
                return str(created["id"])
            if isinstance(created, str) and created:
                return created
        return None

    def _get_specification_by_key(self, props: Dict[str, Any]) -> Optional[str]:
        """Find a specification by exact product ID and spec ID."""
        product_id = self._spec_product_id(props)
        spec_id = self._spec_id(props)
        if not product_id or not spec_id:
            return None

        resp = make_api_request(
            "POST",
            f"{get_base_url()}/nispec/v1/query-specs",
            payload={"productIds": [product_id], "take": 1000},
            handle_errors=False,
        )
        data = resp.json()
        specs = data.get("specs", []) if isinstance(data, dict) else []
        if not isinstance(specs, list):
            return None
        for spec in specs:
            if not isinstance(spec, dict):
                continue
            if str(spec.get("productId", "")) != product_id:
                continue
            if str(spec.get("specId", "")) != spec_id:
                continue
            specification_id = spec.get("id")
            if specification_id:
                return str(specification_id)
        return None

    def _delete_specification(self, props: Dict[str, Any]) -> Optional[str]:
        """Delete a specification by product/spec key and return its ID."""
        specification_id = self._get_specification_by_key(props)
        if not specification_id:
            return None

        resp = make_api_request(
            "POST",
            f"{get_base_url()}/nispec/v1/delete-specs",
            payload={"ids": [specification_id]},
            handle_errors=False,
        )
        if getattr(resp, "status_code", None) == 204:
            return specification_id
        data = resp.json()
        if isinstance(data, dict):
            failed_ids = data.get("failedSpecIds", [])
            if isinstance(failed_ids, list) and specification_id in failed_ids:
                return None
            deleted_ids = data.get("deletedSpecIds")
            if isinstance(deleted_ids, list) and specification_id not in deleted_ids:
                return None
        return specification_id

    def _get_feed_by_name(
        self,
        name: str,
        platform: Optional[str] = None,
        ownership_marker: Optional[str] = None,
    ) -> Optional[str]:
        """Find a feed by exact name, platform, and workspace."""
        from .feed_click import _get_feed_base_url, _normalize_platform

        if not ownership_marker:
            return None

        params: List[str] = []
        if platform:
            params.append(f"platform={_normalize_platform(platform)}")
        if self.workspace_id:
            params.append(f"workspace={self.workspace_id}")
        url = f"{_get_feed_base_url()}/feeds"
        if params:
            url += "?" + "&".join(params)

        try:
            resp = make_api_request("GET", url, payload=None, handle_errors=False)
            data = resp.json()
        except Exception:
            return None
        feeds = data.get("feeds", []) if isinstance(data, dict) else []
        if not isinstance(feeds, list):
            return None

        for feed in feeds:
            if not isinstance(feed, dict):
                continue
            feed_name = feed.get("name") or feed.get("feedName")
            feed_workspace = feed.get("workspace", feed.get("workspaceId"))
            if feed_name != name:
                continue
            if self.workspace_id and feed_workspace != self.workspace_id:
                continue
            if f"[{ownership_marker}]" not in str(feed.get("description", "")):
                continue
            feed_id = feed.get("id") or feed.get("feedId")
            if feed_id:
                return str(feed_id)
        return None

    def _create_feed(self, props: Dict[str, Any]) -> Optional[str]:
        """Create a feed and wait for an asynchronous create job when needed."""
        from .feed_click import _create_feed as create_feed, _wait_for_job

        name = str(props.get("name", ""))
        platform = str(props.get("platform", ""))
        if not name or not platform:
            return None

        ownership_marker = self._resource_ownership_marker(props)
        description = props.get("description")
        if ownership_marker:
            marker_text = f"[{ownership_marker}]"
            description_text = "" if description is None else str(description)
            if marker_text not in description_text:
                description = (
                    f"{description_text}\n{marker_text}" if description_text else marker_text
                )

        result = create_feed(
            name=name,
            platform=platform,
            description=description,
            workspace=self.workspace_id,
        )
        job = result.get("job", {}) if isinstance(result, dict) else {}
        job_id = result.get("jobId") if isinstance(result, dict) else None
        if not job_id and isinstance(job, dict):
            job_id = job.get("id")
        if job_id:
            completed_job = _wait_for_job(str(job_id), timeout=int(props.get("timeout", 300)))
            feed_id = completed_job.get("resourceId") or completed_job.get("feedId")
        else:
            feed_id = result.get("id") if isinstance(result, dict) else None
        return str(feed_id) if feed_id else None

    def _delete_feed(self, props: Dict[str, Any]) -> Optional[str]:
        """Delete a feed by exact name and wait for an asynchronous job."""
        from .feed_click import _delete_feed as delete_feed, _wait_for_job

        name = str(props.get("name", ""))
        platform = str(props.get("platform", "")) or None
        feed_id = self._get_feed_by_name(
            name,
            platform,
            ownership_marker=self._resource_ownership_marker(props),
        )
        if not feed_id:
            return None

        job_id = delete_feed(feed_id)
        if job_id:
            _wait_for_job(str(job_id), timeout=int(props.get("timeout", 300)))
        return feed_id

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
        # Also accept snake_case aliases from config.yaml
        if "partNumber" not in product_obj and "part_number" in props:
            product_obj["partNumber"] = props["part_number"]

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
            product_obj["keywords"] = self._deduplicate_keywords(keywords)

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

    def _build_asset_obj(
        self,
        props: Dict[str, Any],
        default_name: str = "Unknown Asset",
        asset_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Build an AssetCreateModel dict from *props*, shared by asset and DUT creation.

        Handles field-map resolution (snake_case → camelCase), numeric coercion,
        busType normalisation, defaults, description, system_id → location, and
        keyword deduplication.

        Args:
            props: Resource properties from the config YAML.
            default_name: Fallback name when props lacks ``name``.
            asset_type: Explicit ``assetType`` value (e.g. ``"DEVICE_UNDER_TEST"``).
                        When *None*, the field-map resolution decides.
        """
        asset_obj: Dict[str, Any] = {
            "name": props.get("name", default_name),
            "workspace": self.workspace_id or "",
        }
        if asset_type is not None:
            asset_obj["assetType"] = asset_type

        # Copy optional fields from AssetCreateModel schema, supporting snake_case inputs
        field_map: Dict[str, List[str]] = {
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
            # If the caller already set asset_type, skip the assetType field-map entry
            if target == "assetType" and asset_type is not None:
                continue
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

        # Pass description directly (no camelCase alias needed)
        if "description" in props:
            asset_obj["description"] = props["description"]

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
        elif "location" not in asset_obj:
            asset_obj["location"] = {"state": {"assetPresence": "UNKNOWN"}}

        # Tag resource with example name for cleanup
        keywords: List[str] = []
        if isinstance(props.get("keywords"), list):
            keywords.extend([str(x) for x in props["keywords"]])
        if isinstance(props.get("tags"), list):
            keywords.extend([str(x) for x in props["tags"]])
        keywords.append("slcli-provisioner")
        if self.example_name:
            keywords.append(f"slcli-example:{self.example_name}")
        if keywords:
            asset_obj["keywords"] = self._deduplicate_keywords(keywords)

        return asset_obj

    def _post_asset(self, asset_obj: Dict[str, Any]) -> str:
        """POST an asset to /niapm/v1/assets and return the server ID."""
        url = f"{get_base_url()}/niapm/v1/assets"
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

    def _create_asset(self, props: Dict[str, Any]) -> str:
        """Create asset via Asset Management API and return server ID.

        Uses POST /niapm/v1/assets with request body:
        { "assets": [{ name, assetType, busType, modelName, vendorName, serialNumber,
                       workspace, keywords, properties, ... }] }
        """
        asset_obj = self._build_asset_obj(props, default_name="Unknown Asset")
        return self._post_asset(asset_obj)

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
        asset_obj = self._build_asset_obj(
            props, default_name="Unknown DUT", asset_type="DEVICE_UNDER_TEST"
        )
        return self._post_asset(asset_obj)

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
                wi_obj["keywords"] = self._deduplicate_keywords(kw)
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
                result_obj["keywords"] = self._deduplicate_keywords(kw)

            payload = {"results": [result_obj]}
            resp = make_api_request("POST", url, payload, handle_errors=False)
            data = resp.json()
            # Supports 200 (partial) and 201 (success) with the same shape
            results = data.get("results", [])
            if results:
                rid = results[0].get("id")
                if rid:
                    # Create steps if specified in props
                    steps_cfg = props.get("steps")
                    if isinstance(steps_cfg, list) and steps_cfg:
                        self._create_test_steps(str(rid), steps_cfg, result_obj.get("keywords", []))
                    return str(rid)
            return None
        except Exception:
            return None

    def _create_test_steps(
        self,
        result_id: str,
        steps: List[Dict[str, Any]],
        result_keywords: List[str],
    ) -> None:
        """Create test steps for an existing result via POST /nitestmonitor/v2/steps.

        Each entry in `steps` may contain:
          - name (str)
          - step_type / stepType (str, default "NumericLimitTest")
          - status (str: passed/failed/done/running/skipped)
          - step_id / stepId (str, optional — server auto-generates if absent)
          - parent_id / parentId (str, optional)
          - started_at / startedAt (ISO-8601 str, optional)
          - total_time_in_seconds / totalTimeInSeconds (float, optional)
          - data (dict with optional keys: text, parameters)
            - parameters is a list of dicts (each dict is a string key-value map)
          - inputs (list of {name, value} dicts, optional)
          - outputs (list of {name, value} dicts, optional)
          - properties (dict of string key-value pairs, optional)
          - children (list of nested step dicts, optional)
        """
        status_map = {
            "PASSED": "PASSED",
            "FAILED": "FAILED",
            "DONE": "DONE",
            "RUNNING": "RUNNING",
            "SKIPPED": "SKIPPED",
        }

        def _build_step(step_cfg: Dict[str, Any]) -> Dict[str, Any]:
            """Recursively build a TestStepRequestObject from config dict."""
            step_obj: Dict[str, Any] = {
                "resultId": result_id,
            }
            name = step_cfg.get("name")
            if name:
                step_obj["name"] = str(name)

            # step_type accepts both snake_case and camelCase
            step_type = step_cfg.get("step_type") or step_cfg.get("stepType") or "NumericLimitTest"
            step_obj["stepType"] = str(step_type)

            # dataModel (optional, defaults to TestStand for NumericLimitTest)
            data_model = step_cfg.get("data_model") or step_cfg.get("dataModel")
            if data_model:
                step_obj["dataModel"] = str(data_model)

            # status
            raw_status = str(step_cfg.get("status", "passed")).upper()
            if raw_status not in status_map:
                click.echo(
                    f"Warning: unrecognized step status '{step_cfg.get('status')}' "
                    f"for step '{step_cfg.get('name')}', defaulting to PASSED",
                    err=True,
                )
            status_type = status_map.get(raw_status, "PASSED")
            step_obj["status"] = {"statusType": status_type, "statusName": status_type.capitalize()}

            # optional ID fields
            step_id = step_cfg.get("step_id") or step_cfg.get("stepId")
            if step_id:
                step_obj["stepId"] = str(step_id)
            parent_id = step_cfg.get("parent_id") or step_cfg.get("parentId")
            if parent_id:
                step_obj["parentId"] = str(parent_id)

            # timestamps / timing
            started_at = step_cfg.get("started_at") or step_cfg.get("startedAt")
            if started_at:
                step_obj["startedAt"] = str(started_at)
            tts = step_cfg.get("total_time_in_seconds") or step_cfg.get("totalTimeInSeconds")
            if tts is not None:
                step_obj["totalTimeInSeconds"] = float(tts)

            # data block (text + parameters)
            data_cfg = step_cfg.get("data")
            if isinstance(data_cfg, dict):
                data_obj: Dict[str, Any] = {}
                if "text" in data_cfg:
                    data_obj["text"] = str(data_cfg["text"])
                params = data_cfg.get("parameters")
                if isinstance(params, list):
                    data_obj["parameters"] = [
                        (
                            {str(k): str(v) for k, v in p.items() if v is not None}
                            if isinstance(p, dict)
                            else {}
                        )
                        for p in params
                    ]
                if data_obj:
                    step_obj["data"] = data_obj

            # inputs / outputs (list of {name, value})
            for field in ("inputs", "outputs"):
                vals = step_cfg.get(field)
                if isinstance(vals, list):
                    step_obj[field] = vals

            # properties (string key-value map)
            step_props = step_cfg.get("properties")
            if isinstance(step_props, dict):
                step_obj["properties"] = {str(k): str(v) for k, v in step_props.items()}

            # keywords: inherit from result so steps are cleaned up together
            kw: List[str] = list(result_keywords)
            extra_kw = step_cfg.get("keywords")
            if isinstance(extra_kw, list):
                kw.extend([str(k) for k in extra_kw])
            if kw:
                step_obj["keywords"] = self._deduplicate_keywords(kw)

            # children (nested steps, recursive)
            children_cfg = step_cfg.get("children")
            if isinstance(children_cfg, list) and children_cfg:
                step_obj["children"] = [_build_step(c) for c in children_cfg if isinstance(c, dict)]

            return step_obj

        try:
            step_url = f"{get_base_url()}/nitestmonitor/v2/steps"
            step_objs = [_build_step(s) for s in steps if isinstance(s, dict)]
            if not step_objs:
                return
            payload: Dict[str, Any] = {"steps": step_objs, "updateResultTotalTime": True}
            make_api_request("POST", step_url, payload, handle_errors=False)
        except Exception as exc:
            click.echo(
                f"Warning: failed to create test steps for result {result_id}: {exc}",
                err=True,
            )

    def _get_test_result_by_properties(self, props: Dict[str, Any]) -> Optional[str]:
        """Look up a result by its stable fixture identity fields."""
        program_name = props.get("program_name") or props.get("test_phase")
        if not program_name:
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
                    if str(r.get("programName", "")) != str(program_name):
                        continue
                    for property_name, response_name in (
                        ("start_time", "startedAt"),
                        ("serial_number", "serialNumber"),
                        ("part_number", "partNumber"),
                    ):
                        expected = props.get(property_name)
                        if expected is not None and str(r.get(response_name, "")) != str(expected):
                            break
                    else:
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

        Returns table ID if created, or None when the API returns no table ID.
        """
        name = props.get("name", "")
        if not name:
            return None

        try:
            url = f"{get_base_url()}/nidataframe/v1/tables"
            columns = props.get("columns", [])
            transformed_cols: list[Dict[str, Any]] = []
            for idx, col in enumerate(columns):
                col_def: Dict[str, Any] = {"name": col.get("name", f"col_{idx}")}
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
                if idx == 0:
                    col_def["columnType"] = "INDEX"
                    if col_def.get("dataType") == "FLOAT64":
                        col_def["dataType"] = "INT64"
                transformed_cols.append(col_def)

            table_properties: Dict[str, str] = {}
            configured_properties = props.get("properties", {})
            if isinstance(configured_properties, dict):
                table_properties = {
                    str(key): "" if value is None else str(value)
                    for key, value in configured_properties.items()
                }
            description = props.get("description")
            if description:
                table_properties.setdefault("description", str(description))
            if self.example_name:
                table_properties.setdefault("slcli-example", self.example_name)

            payload = {
                "name": name,
                "columns": transformed_cols,
                "properties": table_properties,
            }
            if self.workspace_id:
                payload["workspace"] = self.workspace_id
            resp = make_api_request("POST", url, payload, handle_errors=False)
            resp.raise_for_status()
            data = resp.json()
            table_id = data.get("id") if isinstance(data, dict) else None
            if not table_id:
                table_id = self._get_data_table_by_name(
                    name,
                    ownership_marker=self._data_table_ownership_marker(props),
                )
            if not table_id:
                return None
            self._ensure_data_table_rows(str(table_id), props)
            return str(table_id)
        except Exception:
            raise

    @staticmethod
    def _data_table_ownership_marker(props: Dict[str, Any]) -> Optional[str]:
        """Return the configured ownership marker for a DataFrame table."""
        marker = props.get("ownership_marker")
        table_properties = props.get("properties")
        if marker is None and isinstance(table_properties, dict):
            marker = table_properties.get("ownership_marker")
        return str(marker) if marker else None

    def _get_data_table_candidates_by_name(self, name: str) -> List[Dict[str, Any]]:
        """Return exact-name DataFrame table metadata in the current workspace."""
        if not name:
            return []

        try:
            url = f"{get_base_url()}/nidataframe/v1/query-tables"
            filter_str = "name == @0"
            substitutions: List[str] = [name]
            if self.workspace_id:
                filter_str += " and workspace == @1"
                substitutions.append(self.workspace_id)
            payload = {
                "filter": filter_str,
                "substitutions": substitutions,
                "projection": ["ID", "NAME", "PROPERTIES", "WORKSPACE"],
                "take": 100,
            }
            resp = make_api_request("POST", url, payload, handle_errors=False)
            resp.raise_for_status()
            data = resp.json()
            tables = data.get("tables", []) if isinstance(data, dict) else []
            return [
                table
                for table in tables
                if isinstance(table, dict) and str(table.get("name", "")).lower() == name.lower()
            ]
        except Exception:
            return []

    def _get_data_table_by_name(
        self, name: str, ownership_marker: Optional[str] = None
    ) -> Optional[str]:
        """Look up data table by name via /nidataframe/v1/query-tables.

        Returns table ID if found, None otherwise.
        """
        for table in self._get_data_table_candidates_by_name(name):
            if ownership_marker:
                table_properties = table.get("properties", {})
                if not isinstance(table_properties, dict):
                    continue
                if str(table_properties.get("ownership_marker", "")) != ownership_marker:
                    continue
            table_id = table.get("id")
            if table_id:
                return str(table_id)
        return None

    def _get_data_table_ids_by_name(
        self, name: str, ownership_marker: Optional[str] = None
    ) -> List[str]:
        """Return all data table IDs with exact name in current workspace."""
        ids: List[str] = []
        for table in self._get_data_table_candidates_by_name(name):
            if ownership_marker:
                table_properties = table.get("properties", {})
                if not isinstance(table_properties, dict):
                    continue
                if str(table_properties.get("ownership_marker", "")) != ownership_marker:
                    continue
            table_id = table.get("id")
            if table_id:
                ids.append(str(table_id))
        return ids

    def _load_data_table_append_payload(self, props: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """Load and validate a DataFrame append payload from example properties."""
        rows_file = props.get("rows_file") or props.get("data_file")
        rows = props.get("rows")
        if rows_file and rows is not None:
            raise ValueError("DataFrame table cannot define both rows_file and rows")
        if rows_file:
            if not isinstance(rows_file, str):
                raise ValueError("DataFrame rows_file must be a string")
            file_content = self._read_example_file(rows_file)
            if file_content is None:
                raise ValueError(f"Unable to read DataFrame rows file: {rows_file}")
            try:
                source = json_module.loads(file_content.decode("utf-8"))
            except (UnicodeDecodeError, json_module.JSONDecodeError) as exc:
                raise ValueError(f"Invalid DataFrame rows JSON in {rows_file}: {exc}") from exc
        elif rows is not None:
            source = {"frame": {"data": rows}}
        else:
            return None

        if isinstance(source, list):
            source = {"frame": {"data": source}}
        if not isinstance(source, dict):
            raise ValueError("DataFrame rows must be a JSON object or array")

        frame = source.get("frame")
        if not isinstance(frame, dict):
            raise ValueError("DataFrame rows must contain a frame object")

        configured_columns = props.get("columns", [])
        column_names = [
            str(column.get("name", f"col_{index}"))
            for index, column in enumerate(configured_columns)
            if isinstance(column, dict)
        ]
        frame_columns = frame.get("columns")
        if frame_columns is None:
            frame_columns = column_names
        if not isinstance(frame_columns, list) or not frame_columns:
            raise ValueError("DataFrame rows must define a non-empty columns array")
        frame_columns = [str(column) for column in frame_columns]
        if column_names and frame_columns != column_names:
            raise ValueError("DataFrame row columns do not match the table columns")

        raw_rows = frame.get("data")
        if not isinstance(raw_rows, list):
            raise ValueError("DataFrame rows frame must contain a data array")
        normalized_rows: List[List[Optional[str]]] = []
        for index, row in enumerate(raw_rows):
            if not isinstance(row, list) or len(row) != len(frame_columns):
                raise ValueError(f"DataFrame row {index} must contain {len(frame_columns)} values")
            normalized_rows.append([None if value is None else str(value) for value in row])

        payload: Dict[str, Any] = {"frame": {"columns": frame_columns, "data": normalized_rows}}
        if source.get("endOfData") is True or props.get("end_of_data") is True:
            payload["endOfData"] = True
        return payload

    @staticmethod
    def _data_table_row_signature(row: List[Optional[str]]) -> str:
        """Create a stable comparison key for a DataFrame row."""
        return json_module.dumps(row, ensure_ascii=True, separators=(",", ":"))

    def _query_data_table_rows(
        self, table_id: str, columns: List[str]
    ) -> List[List[Optional[str]]]:
        """Read all existing rows from a DataFrame table."""
        rows: List[List[Optional[str]]] = []
        continuation_token: Optional[str] = None
        seen_tokens: set[str] = set()
        while True:
            payload: Dict[str, Any] = {"columns": columns, "take": 10000}
            if continuation_token:
                if continuation_token in seen_tokens:
                    raise ValueError("DataFrame row query returned a repeated continuation token")
                seen_tokens.add(continuation_token)
                payload["continuationToken"] = continuation_token
            response = make_api_request(
                "POST",
                f"{get_base_url()}/nidataframe/v1/tables/{table_id}/query-data",
                payload,
                handle_errors=False,
            )
            response.raise_for_status()
            data = response.json()
            frame = data.get("frame", {}) if isinstance(data, dict) else {}
            page_rows = frame.get("data", []) if isinstance(frame, dict) else []
            if isinstance(page_rows, list):
                for row in page_rows:
                    if isinstance(row, list):
                        rows.append([None if value is None else str(value) for value in row])
            next_token = data.get("continuationToken") if isinstance(data, dict) else None
            if not next_token:
                return rows
            continuation_token = str(next_token)

    def _ensure_data_table_rows(self, table_id: str, props: Dict[str, Any]) -> None:
        """Append missing DataFrame rows without duplicating an installed fixture."""
        append_payload = self._load_data_table_append_payload(props)
        if append_payload is None:
            return

        frame = append_payload["frame"]
        columns = frame["columns"]
        rows = frame["data"]
        if not rows and append_payload.get("endOfData") is not True:
            self._last_resource_details = {
                "rows_expected": 0,
                "rows_existing": 0,
                "rows_added": 0,
            }
            return

        input_indexes: set[Optional[str]] = set()
        for row in rows:
            index_value = row[0]
            if index_value in input_indexes:
                raise ValueError(f"DataFrame rows contain duplicate index value: {index_value}")
            input_indexes.add(index_value)

        existing_rows = self._query_data_table_rows(table_id, columns)
        existing_signatures = {self._data_table_row_signature(row) for row in existing_rows}
        existing_indexes = {row[0] for row in existing_rows if row}
        rows_to_append: List[List[Optional[str]]] = []
        for row in rows:
            signature = self._data_table_row_signature(row)
            if signature in existing_signatures:
                continue
            if row[0] in existing_indexes:
                raise ValueError(f"DataFrame index {row[0]} exists with different row contents")
            rows_to_append.append(row)

        if rows_to_append:
            payload: Dict[str, Any] = {"frame": {"columns": columns, "data": rows_to_append}}
            if append_payload.get("endOfData") is True:
                payload["endOfData"] = True
            response = make_api_request(
                "POST",
                f"{get_base_url()}/nidataframe/v1/tables/{table_id}/data",
                payload,
                handle_errors=False,
            )
            response.raise_for_status()
        elif append_payload.get("endOfData") is True:
            response = make_api_request(
                "POST",
                f"{get_base_url()}/nidataframe/v1/tables/{table_id}/data",
                {"endOfData": True},
                handle_errors=False,
            )
            response.raise_for_status()

        self._last_resource_details = {
            "rows_expected": len(rows),
            "rows_existing": len(existing_rows),
            "rows_added": len(rows_to_append),
        }

    def _delete_data_table(self, props: Dict[str, Any]) -> Optional[str]:
        """Delete data table via /nidataframe/v1/delete-tables.

        Returns ID if deleted, None otherwise.
        """
        name = props.get("name", "")
        if not name:
            return None

        table_ids = self._get_data_table_ids_by_name(
            name,
            ownership_marker=self._data_table_ownership_marker(props),
        )
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
                # Store tags as comma-separated string in a custom property
                metadata["slcli-tags"] = ",".join(self._deduplicate_keywords(kw))

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
