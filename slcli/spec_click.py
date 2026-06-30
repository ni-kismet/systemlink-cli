"""CLI commands for managing SystemLink specifications."""

import json
import re
import sys
from typing import Any, Dict, List, Optional, Tuple

import click
import questionary

from .cli_utils import confirm_bulk_operation, validate_output_format
from .rich_output import render_table
from .universal_handlers import FilteredResponse, UniversalResponseHandler
from .utils import (
    ExitCodes,
    check_readonly_mode,
    format_success,
    get_base_url,
    get_workspace_map,
    handle_api_error,
    load_json_file,
    make_api_request,
    sanitize_filename,
    save_json_file,
)
from .workspace_utils import (
    get_effective_workspace,
    get_workspace_display_name,
    resolve_workspace_id,
)

SPEC_TYPES = ["PARAMETRIC", "FUNCTIONAL"]
CONDITION_TYPES = ["NUMERIC", "STRING"]
SPEC_ORDER_BY_FIELDS = ["ID", "SPEC_ID"]
SPEC_PROJECTION_FIELDS = [
    "ID",
    "PRODUCT_ID",
    "SPEC_ID",
    "NAME",
    "CATEGORY",
    "TYPE",
    "SYMBOL",
    "BLOCK",
    "LIMIT",
    "UNIT",
    "CONDITION_NAME",
    "CONDITION_VALUES",
    "CONDITION_UNIT",
    "CONDITION_TYPE",
    "KEYWORDS",
    "PROPERTIES",
    "WORKSPACE",
    "CREATED_AT",
    "CREATED_BY",
]
CONDITION_PROJECTION_FIELDS = [
    "CONDITION_NAME",
    "CONDITION_VALUES",
    "CONDITION_UNIT",
    "CONDITION_TYPE",
]
LIMIT_PROJECTION_FIELDS = ["LIMIT"]

_SPEC_LIST_HEADERS = ["PRODUCT", "SPEC ID", "NAME", "TYPE", "LIMIT", "CONDITIONS", "WORKSPACE"]
_SPEC_LIST_WIDTHS = [18, 18, 28, 12, 24, 22, 20]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _get_spec_base_url() -> str:
    """Get the base URL for the Specification Management API."""
    return f"{get_base_url()}/nispec/v1"


def _get_testmonitor_base_url() -> str:
    """Get the base URL for the Test Monitor API."""
    return f"{get_base_url()}/nitestmonitor/v2"


_UUID_RE = re.compile(
    r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE
)


def _resolve_product_id(identifier: str) -> str:
    """Resolve a product name, part number, or ID to a product ID.

    Resolution order:
    1. If the identifier looks like a UUID, try a direct GET by ID.
    2. Query products whose name matches exactly.
    3. Query products whose part number matches exactly.
    4. If no match is found, exit with an error.
    5. If multiple matches are found, exit with a disambiguation list.
    """
    base = _get_testmonitor_base_url()

    # 1. Direct ID lookup for UUID-shaped identifiers.
    if _UUID_RE.match(identifier):
        try:
            resp = make_api_request("GET", f"{base}/products/{identifier}", handle_errors=False)
            resp.raise_for_status()
            return identifier
        except Exception as exc:
            response = getattr(exc, "response", None)
            status_code = getattr(response, "status_code", None)
            if status_code != 404:
                handle_api_error(exc)
            # Fall through to name/partNumber search on a direct-lookup 404.

    # 2. Search by exact name.
    matches = _query_products_by_field(base, "name", identifier)
    if len(matches) == 1:
        return str(matches[0]["id"])
    if len(matches) > 1:
        _ambiguous_product_error(identifier, matches)

    # 3. Search by exact part number.
    matches = _query_products_by_field(base, "partNumber", identifier)
    if len(matches) == 1:
        return str(matches[0]["id"])
    if len(matches) > 1:
        _ambiguous_product_error(identifier, matches)

    click.echo(f"\u2717 No product found matching '{identifier}'", err=True)
    sys.exit(ExitCodes.NOT_FOUND)


def _query_products_by_field(base_url: str, field: str, value: str) -> List[Dict[str, Any]]:
    """Query products where *field* equals *value* exactly."""
    payload: Dict[str, Any] = {
        "filter": f"{field} == @0",
        "substitutions": [value],
        "take": 10,
    }
    resp = make_api_request("POST", f"{base_url}/query-products", payload=payload)
    data = resp.json()
    products = data.get("products", []) if isinstance(data, dict) else []
    return products if isinstance(products, list) else []


def _ambiguous_product_error(identifier: str, matches: List[Dict[str, Any]]) -> None:
    """Print an error listing ambiguous product matches and exit."""
    click.echo(
        f"\u2717 Multiple products match '{identifier}'. Please be more specific:",
        err=True,
    )
    for product in matches[:10]:
        name = product.get("name", "")
        part = product.get("partNumber", "")
        pid = product.get("id", "")
        click.echo(f"  - {name}  (partNumber={part}, id={pid})", err=True)
    sys.exit(ExitCodes.INVALID_INPUT)


def _escape_filter_value(value: str) -> str:
    """Escape double quotes in filter values."""
    return value.replace('"', '\\"')


def _parse_properties(properties: Tuple[str, ...]) -> Dict[str, str]:
    """Parse key=value property strings into a dictionary."""
    props_dict: Dict[str, str] = {}
    for prop in properties:
        if "=" not in prop:
            click.echo(f"\u2717 Invalid property format: {prop}. Use key=value", err=True)
            sys.exit(ExitCodes.INVALID_INPUT)
        key, val = prop.split("=", 1)
        props_dict[key.strip()] = val.strip()
    return props_dict


def _normalize_spec_type(spec_type: Optional[str]) -> Optional[str]:
    """Normalize a specification type value."""
    if spec_type is None:
        return None
    normalized = spec_type.strip().upper()
    if normalized not in SPEC_TYPES:
        click.echo(
            f"\u2717 Invalid specification type '{spec_type}'. "
            f"Valid options: {', '.join(SPEC_TYPES)}",
            err=True,
        )
        sys.exit(ExitCodes.INVALID_INPUT)
    return normalized


def _validate_spec_required_fields(spec_data: Dict[str, Any], fields: List[str]) -> None:
    """Validate that required fields are present and non-empty."""
    missing_fields = [
        field
        for field in fields
        if field not in spec_data or spec_data[field] is None or spec_data[field] == ""
    ]
    if missing_fields:
        click.echo(
            f"\u2717 Missing required fields for specification: {', '.join(missing_fields)}",
            err=True,
        )
        sys.exit(ExitCodes.INVALID_INPUT)


def _load_single_spec_file(input_file: Optional[str]) -> Dict[str, Any]:
    """Load a single specification object from a JSON file."""
    if not input_file:
        return {}

    data = load_json_file(input_file)
    if isinstance(data, dict):
        specs = data.get("specs")
        if specs is None:
            return dict(data)
        if isinstance(specs, list) and len(specs) == 1 and isinstance(specs[0], dict):
            return dict(specs[0])

    click.echo(
        "\u2717 Input file must contain a single specification object "
        "or a 'specs' array with one item.",
        err=True,
    )
    sys.exit(ExitCodes.INVALID_INPUT)


def _load_spec_list_file(input_file: str) -> List[Dict[str, Any]]:
    """Load a specification list from a JSON file."""
    data = load_json_file(input_file)
    if isinstance(data, dict):
        specs = data.get("specs")
        if isinstance(specs, list) and all(isinstance(item, dict) for item in specs):
            return list(specs)
        if specs is None:
            return [dict(data)]
    elif isinstance(data, list) and all(isinstance(item, dict) for item in data):
        return list(data)

    click.echo(
        "\u2717 Input file must contain a specification object, a 'specs' array, "
        "or a JSON array of specification objects.",
        err=True,
    )
    sys.exit(ExitCodes.INVALID_INPUT)


def _parse_condition_input(condition_input: str) -> Dict[str, Any]:
    """Parse a condition JSON string into a condition object."""
    try:
        parsed = json.loads(condition_input)
    except json.JSONDecodeError as exc:
        click.echo(f"\u2717 Invalid JSON for --condition: {exc}", err=True)
        sys.exit(ExitCodes.INVALID_INPUT)

    if not isinstance(parsed, dict):
        click.echo("\u2717 Each --condition value must decode to a JSON object.", err=True)
        sys.exit(ExitCodes.INVALID_INPUT)
    return parsed


def _load_conditions(
    conditions: Tuple[str, ...],
    condition_file: Optional[str],
) -> Optional[List[Dict[str, Any]]]:
    """Load conditions from repeatable JSON options and/or a JSON file."""
    parsed_conditions: List[Dict[str, Any]] = []

    if condition_file:
        file_data = load_json_file(condition_file)
        if not isinstance(file_data, list) or not all(isinstance(item, dict) for item in file_data):
            click.echo(
                "\u2717 Condition file must contain a JSON array of condition objects.", err=True
            )
            sys.exit(ExitCodes.INVALID_INPUT)
        parsed_conditions.extend(file_data)

    for condition in conditions:
        parsed_conditions.append(_parse_condition_input(condition))

    return parsed_conditions or None


def _build_limit(
    limit_min: Optional[float],
    limit_typical: Optional[float],
    limit_max: Optional[float],
) -> Optional[Dict[str, float]]:
    """Build a specification limit object from CLI options."""
    limit: Dict[str, float] = {}
    if limit_min is not None:
        limit["min"] = limit_min
    if limit_typical is not None:
        limit["typical"] = limit_typical
    if limit_max is not None:
        limit["max"] = limit_max
    return limit or None


def _normalize_condition_type(condition_type: Optional[str]) -> Optional[str]:
    """Normalize a condition type value."""
    if condition_type is None:
        return None
    normalized = condition_type.strip().upper()
    if normalized not in CONDITION_TYPES:
        click.echo(
            f"\u2717 Invalid condition type '{condition_type}'. "
            f"Valid options: {', '.join(CONDITION_TYPES)}",
            err=True,
        )
        sys.exit(ExitCodes.INVALID_INPUT)
    return normalized


def _format_limit(limit: Optional[Dict[str, Any]]) -> str:
    """Format a specification limit object for display."""
    if not isinstance(limit, dict):
        return ""

    parts: List[str] = []
    if limit.get("min") is not None:
        parts.append(f"min={limit['min']}")
    if limit.get("typical") is not None:
        parts.append(f"typ={limit['typical']}")
    if limit.get("max") is not None:
        parts.append(f"max={limit['max']}")
    return ", ".join(parts)


def _format_condition_value(condition_value: Optional[Dict[str, Any]]) -> str:
    """Format a specification condition value for display."""
    if not isinstance(condition_value, dict):
        return ""

    parts: List[str] = []
    discrete = condition_value.get("discrete")
    if isinstance(discrete, list) and discrete:
        parts.append("discrete=" + ", ".join(str(item) for item in discrete))

    ranges = condition_value.get("range")
    if isinstance(ranges, list) and ranges:
        range_parts: List[str] = []
        for range_item in ranges:
            if not isinstance(range_item, dict):
                continue
            min_value = range_item.get("min")
            max_value = range_item.get("max")
            step_value = range_item.get("step")
            bounds = f"{min_value}..{max_value}"
            if step_value is not None:
                bounds += f" step {step_value}"
            range_parts.append(bounds)
        if range_parts:
            parts.append("range=" + "; ".join(range_parts))

    unit = condition_value.get("unit")
    if unit:
        parts.append(f"unit={unit}")

    condition_type = condition_value.get("conditionType")
    if condition_type:
        parts.append(f"type={condition_type}")

    return ", ".join(parts)


def _format_conditions_summary(specification: Dict[str, Any]) -> str:
    """Format a concise condition summary for tabular output."""
    conditions = specification.get("conditions", [])
    if not isinstance(conditions, list) or not conditions:
        return ""

    names = [str(condition.get("name", "")).strip() for condition in conditions if condition]
    names = [name for name in names if name]
    if not names:
        return str(len(conditions))
    if len(names) <= 2:
        return ", ".join(names)
    return f"{', '.join(names[:2])} +{len(names) - 2}"


def _get_product_workspace(product_id: str) -> Optional[str]:
    """Look up the workspace assigned to a product."""
    if not product_id:
        return None

    resp = make_api_request("GET", f"{_get_testmonitor_base_url()}/products/{product_id}")
    resp.raise_for_status()
    product = resp.json()
    workspace = product.get("workspace") if isinstance(product, dict) else None
    if isinstance(workspace, str) and workspace:
        return workspace
    return None


def _resolve_spec_workspace(
    spec_data: Dict[str, Any],
    workspace: Optional[str],
    product_workspace_cache: Optional[Dict[str, Optional[str]]] = None,
) -> Optional[str]:
    """Resolve the effective workspace for a specification payload.

    Precedence is:
    1. Explicit CLI workspace.
    2. Workspace already present on the payload.
    3. Workspace inherited from the referenced product.
    4. Active profile workspace.
    """
    if workspace is not None:
        explicit_workspace = get_effective_workspace(workspace)
        if explicit_workspace:
            resolved_workspace = resolve_workspace_id(explicit_workspace)
            if resolved_workspace:
                return resolved_workspace

    payload_workspace = spec_data.get("workspace")
    if isinstance(payload_workspace, str) and payload_workspace:
        resolved_workspace = resolve_workspace_id(payload_workspace)
        if resolved_workspace:
            return resolved_workspace

    product_id = spec_data.get("productId")
    if isinstance(product_id, str) and product_id:
        if product_workspace_cache is not None and product_id in product_workspace_cache:
            cached_workspace = product_workspace_cache[product_id]
        else:
            cached_workspace = _get_product_workspace(product_id)
            if product_workspace_cache is not None:
                product_workspace_cache[product_id] = cached_workspace
        if cached_workspace:
            return cached_workspace

    default_workspace = get_effective_workspace(None)
    if default_workspace:
        resolved_workspace = resolve_workspace_id(default_workspace)
        if resolved_workspace:
            return resolved_workspace

    return None


def _projection_field_set(
    projection_fields: Tuple[str, ...],
    include_limits: bool = False,
    include_conditions: bool = False,
) -> Optional[List[str]]:
    """Build a projection list with convenience expansions."""
    field_set = {field.upper() for field in projection_fields}

    if include_limits:
        field_set.update(LIMIT_PROJECTION_FIELDS)
    if include_conditions:
        field_set.update(CONDITION_PROJECTION_FIELDS)

    if not field_set:
        return None

    return [field for field in SPEC_PROJECTION_FIELDS if field in field_set]


def _matches_limit_filters(
    specification: Dict[str, Any],
    limit_min_ge: Optional[float],
    limit_min_le: Optional[float],
    limit_typical_ge: Optional[float],
    limit_typical_le: Optional[float],
    limit_max_ge: Optional[float],
    limit_max_le: Optional[float],
) -> bool:
    """Apply client-side limit filters to a specification."""
    limit = specification.get("limit")
    if not isinstance(limit, dict):
        no_limit_filters = all(
            value is None
            for value in (
                limit_min_ge,
                limit_min_le,
                limit_typical_ge,
                limit_typical_le,
                limit_max_ge,
                limit_max_le,
            )
        )
        return no_limit_filters

    def limit_value(name: str) -> Optional[float]:
        value = limit.get(name)
        if isinstance(value, (int, float)):
            return float(value)
        return None

    min_value = limit_value("min")
    typical_value = limit_value("typical")
    max_value = limit_value("max")

    checks = [
        (limit_min_ge, min_value, lambda threshold, actual: actual >= threshold),
        (limit_min_le, min_value, lambda threshold, actual: actual <= threshold),
        (limit_typical_ge, typical_value, lambda threshold, actual: actual >= threshold),
        (limit_typical_le, typical_value, lambda threshold, actual: actual <= threshold),
        (limit_max_ge, max_value, lambda threshold, actual: actual >= threshold),
        (limit_max_le, max_value, lambda threshold, actual: actual <= threshold),
    ]

    for threshold, actual, predicate in checks:
        if threshold is None:
            continue
        if actual is None or not predicate(threshold, actual):
            return False
    return True


def _matches_condition_filters(
    specification: Dict[str, Any],
    condition_name: Optional[str],
    condition_type: Optional[str],
    condition_unit: Optional[str],
    condition_value: Optional[str],
) -> bool:
    """Apply client-side condition filters to a specification."""
    normalized_type = _normalize_condition_type(condition_type)
    normalized_name = condition_name.lower() if condition_name else None
    normalized_unit = condition_unit.lower() if condition_unit else None
    normalized_value = condition_value.lower() if condition_value else None

    no_condition_filters = all(
        value is None
        for value in (normalized_name, normalized_type, normalized_unit, normalized_value)
    )
    if no_condition_filters:
        return True

    conditions = specification.get("conditions")
    if not isinstance(conditions, list):
        return False

    for condition in conditions:
        if not isinstance(condition, dict):
            continue
        if normalized_name:
            name = str(condition.get("name", "")).lower()
            if normalized_name not in name:
                continue

        value_object = condition.get("value")
        if not isinstance(value_object, dict):
            if normalized_type or normalized_unit or normalized_value:
                continue
            return True

        if normalized_type:
            if str(value_object.get("conditionType", "")).upper() != normalized_type:
                continue

        if normalized_unit:
            unit = str(value_object.get("unit", "")).lower()
            if normalized_unit not in unit:
                continue

        if normalized_value:
            discrete = value_object.get("discrete", [])
            range_values = value_object.get("range", [])
            rendered_parts: List[str] = []
            if isinstance(discrete, list):
                rendered_parts.extend(str(item).lower() for item in discrete)
            if isinstance(range_values, list):
                for range_item in range_values:
                    if not isinstance(range_item, dict):
                        continue
                    rendered_parts.extend(
                        str(range_item.get(key, "")).lower()
                        for key in ("min", "max", "step")
                        if range_item.get(key) is not None
                    )
            if not any(normalized_value in part for part in rendered_parts):
                continue

        return True

    return False


def _apply_client_side_filters(
    specifications: List[Dict[str, Any]],
    condition_name: Optional[str],
    condition_type: Optional[str],
    condition_unit: Optional[str],
    condition_value: Optional[str],
    limit_min_ge: Optional[float],
    limit_min_le: Optional[float],
    limit_typical_ge: Optional[float],
    limit_typical_le: Optional[float],
    limit_max_ge: Optional[float],
    limit_max_le: Optional[float],
) -> List[Dict[str, Any]]:
    """Filter queried specifications client-side for condition and limit fields."""
    filtered_specs: List[Dict[str, Any]] = []
    for specification in specifications:
        if not _matches_condition_filters(
            specification,
            condition_name,
            condition_type,
            condition_unit,
            condition_value,
        ):
            continue
        if not _matches_limit_filters(
            specification,
            limit_min_ge,
            limit_min_le,
            limit_typical_ge,
            limit_typical_le,
            limit_max_ge,
            limit_max_le,
        ):
            continue
        filtered_specs.append(specification)
    return filtered_specs


def _default_export_filename(product_ids: List[str]) -> str:
    """Generate a default export filename for specifications."""
    if len(product_ids) == 1:
        return f"{sanitize_filename(product_ids[0], 'specs')}-specs.json"
    return "specifications-export.json"


def _report_mutation_result(
    data: Dict[str, Any],
    success_key: str,
    operation: str,
) -> None:
    """Report a create or update specifications response."""
    success_specs = data.get(success_key, []) if isinstance(data, dict) else []
    failed_specs = data.get("failedSpecs", []) if isinstance(data, dict) else []

    if isinstance(success_specs, list) and success_specs:
        spec = success_specs[0]
        format_success(
            f"Specification {operation}",
            {
                "id": spec.get("id", ""),
                "specId": spec.get("specId", ""),
                "productId": spec.get("productId", ""),
                "version": spec.get("version", ""),
            },
        )
        if failed_specs:
            click.echo(f"! {len(failed_specs)} specification request(s) failed.")
        return

    error = data.get("error", {}) if isinstance(data, dict) else {}
    click.echo(
        f"\u2717 Failed to {operation.lower().rstrip('d')} specification: "
        f"{error.get('message', 'Unknown error')}",
        err=True,
    )
    sys.exit(ExitCodes.GENERAL_ERROR)


def _extract_failure_messages(error_data: Any) -> List[str]:
    """Flatten error and nested inner-error messages for display."""
    messages: List[str] = []

    def visit(candidate: Any) -> None:
        if isinstance(candidate, dict):
            message = candidate.get("message")
            if isinstance(message, str) and message and message not in messages:
                messages.append(message)
            for key in ("innerErrors", "innererrors", "errors", "details"):
                nested = candidate.get(key)
                if isinstance(nested, list):
                    for item in nested:
                        visit(item)
                elif isinstance(nested, dict):
                    visit(nested)
        elif isinstance(candidate, list):
            for item in candidate:
                visit(item)
        elif candidate is not None:
            text = str(candidate).strip()
            if text and text not in messages:
                messages.append(text)

    visit(error_data)
    return messages


def _index_global_failure_messages(error_data: Any) -> Dict[str, List[str]]:
    """Map top-level inner errors to a failed spec identifier when possible."""
    indexed_messages: Dict[str, List[str]] = {}

    if not isinstance(error_data, dict):
        return indexed_messages

    inner_errors = error_data.get("innerErrors") or error_data.get("innererrors")
    if not isinstance(inner_errors, list):
        return indexed_messages

    for inner_error in inner_errors:
        if not isinstance(inner_error, dict):
            continue
        resource_id = inner_error.get("resourceId")
        if not isinstance(resource_id, str) or not resource_id:
            continue
        messages = _extract_failure_messages(inner_error)
        if messages:
            indexed_messages[resource_id] = messages

    return indexed_messages


def _report_failed_specs(
    failed_specs: List[Dict[str, Any]],
    overall_error: Optional[Dict[str, Any]] = None,
    err: bool = True,
) -> None:
    """Render per-spec failure details, including nested inner errors."""
    if not failed_specs:
        return

    global_messages = _index_global_failure_messages(overall_error)

    click.echo("! Failure details:", err=err)
    for failure in failed_specs:
        identifier = str(
            failure.get("specId") or failure.get("id") or failure.get("name") or "Unknown spec"
        )
        error_messages = _extract_failure_messages(
            failure.get("error")
            or failure.get("errors")
            or failure.get("innerErrors")
            or failure.get("innererrors")
            or failure
        )
        if not error_messages:
            error_messages = global_messages.get(identifier, [])
        if error_messages:
            click.echo(f"  - {identifier}: {error_messages[0]}", err=err)
            for inner_message in error_messages[1:]:
                click.echo(f"    inner: {inner_message}", err=err)
        else:
            click.echo(f"  - {identifier}: Unknown error", err=err)


def _report_bulk_create_result(data: Dict[str, Any]) -> None:
    """Report a bulk create-specifications response."""
    created_specs = data.get("createdSpecs", []) if isinstance(data, dict) else []
    failed_specs = data.get("failedSpecs", []) if isinstance(data, dict) else []
    overall_error = (
        data.get("error")
        if isinstance(data, dict) and isinstance(data.get("error"), dict)
        else None
    )

    created_count = len(created_specs)
    failed_count = len(failed_specs)

    if created_count == 0 and failed_count > 0:
        click.echo("✗ Specification import failed", err=True)
        click.echo(f"  created: {created_count}", err=True)
        click.echo(f"  {click.style('failed', fg='red')}: {failed_count}", err=True)
        _report_failed_specs(failed_specs, overall_error=overall_error, err=True)
        click.echo(
            "! No specifications were created. Inspect the source payload and failure details to resolve.",
            err=True,
        )
        sys.exit(ExitCodes.GENERAL_ERROR)

    click.echo("✓ Specification import completed")
    click.echo(f"  created: {created_count}")
    click.echo(f"  {click.style('failed', fg='red')}: {failed_count}")

    if failed_specs:
        _report_failed_specs(failed_specs, overall_error=overall_error, err=True)
        click.echo(
            "! Some specifications failed to import. "
            "Inspect the source payload and failure details to resolve."
        )


def _report_delete_result(data: Optional[Dict[str, Any]], requested_ids: List[str]) -> None:
    """Report a delete-specifications response."""
    if not data:
        format_success("Specification(s) deleted", {"count": len(requested_ids)})
        return

    deleted_ids = data.get("deletedSpecIds", []) if isinstance(data, dict) else []
    failed_ids = data.get("failedSpecIds", []) if isinstance(data, dict) else []

    if deleted_ids:
        format_success("Specification(s) deleted", {"count": len(deleted_ids)})

    if failed_ids:
        click.echo(
            f"\u2717 Failed to delete {len(failed_ids)} specification(s): "
            f"{', '.join(str(item) for item in failed_ids)}",
            err=True,
        )
        sys.exit(ExitCodes.GENERAL_ERROR)

    if not deleted_ids:
        click.echo("\u2717 No specifications were deleted.", err=True)
        sys.exit(ExitCodes.GENERAL_ERROR)


def _build_spec_filter(
    spec_id: Optional[str] = None,
    name: Optional[str] = None,
    category: Optional[str] = None,
    spec_type: Optional[str] = None,
    block: Optional[str] = None,
    symbol: Optional[str] = None,
    unit: Optional[str] = None,
    workspace: Optional[str] = None,
    created_by: Optional[str] = None,
    updated_by: Optional[str] = None,
    custom_filter: Optional[str] = None,
) -> Optional[str]:
    """Build a query-specs dynamic linq filter expression."""
    parts: List[str] = []

    if spec_id:
        parts.append(f'specId == "{_escape_filter_value(spec_id)}"')
    if name:
        parts.append(f'name.Contains("{_escape_filter_value(name)}")')
    if category:
        parts.append(f'category.Contains("{_escape_filter_value(category)}")')
    if spec_type:
        parts.append(f'type == "{_normalize_spec_type(spec_type)}"')
    if block:
        parts.append(f'block.Contains("{_escape_filter_value(block)}")')
    if symbol:
        parts.append(f'symbol.Contains("{_escape_filter_value(symbol)}")')
    if unit:
        parts.append(f'unit.Contains("{_escape_filter_value(unit)}")')
    if workspace:
        parts.append(f'workspace == "{_escape_filter_value(workspace)}"')
    if created_by:
        parts.append(f'createdBy == "{_escape_filter_value(created_by)}"')
    if updated_by:
        parts.append(f'updatedBy == "{_escape_filter_value(updated_by)}"')
    if custom_filter:
        parts.append(custom_filter)

    return " && ".join(parts) if parts else None


def _query_specs_once(
    product_ids: List[str],
    take: int,
    continuation_token: Optional[str] = None,
    filter_expr: Optional[str] = None,
    order_by: Optional[str] = None,
    descending: bool = False,
    projection: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Execute one query-specs request."""
    payload: Dict[str, Any] = {
        "productIds": product_ids,
        "take": take,
        "orderByDescending": descending,
    }
    if continuation_token:
        payload["continuationToken"] = continuation_token
    if filter_expr:
        payload["filter"] = filter_expr
    if order_by:
        payload["orderBy"] = order_by
    if projection:
        payload["projection"] = projection

    resp = make_api_request("POST", f"{_get_spec_base_url()}/query-specs", payload=payload)
    data = resp.json()
    if not isinstance(data, dict):
        return {"specs": [], "continuationToken": None}
    return data


def _collect_specs(
    product_ids: List[str],
    take: int,
    filter_expr: Optional[str],
    order_by: str,
    descending: bool,
    projection: Optional[List[str]] = None,
    condition_name: Optional[str] = None,
    condition_type: Optional[str] = None,
    condition_unit: Optional[str] = None,
    condition_value: Optional[str] = None,
    limit_min_ge: Optional[float] = None,
    limit_min_le: Optional[float] = None,
    limit_typical_ge: Optional[float] = None,
    limit_typical_le: Optional[float] = None,
    limit_max_ge: Optional[float] = None,
    limit_max_le: Optional[float] = None,
) -> List[Dict[str, Any]]:
    """Collect specifications across query pages, applying client-side filters."""
    collected_specs: List[Dict[str, Any]] = []
    continuation_token: Optional[str] = None

    while len(collected_specs) < take:
        remaining = max(take - len(collected_specs), 1)
        page = _query_specs_once(
            product_ids=product_ids,
            take=remaining,
            continuation_token=continuation_token,
            filter_expr=filter_expr,
            order_by=order_by,
            descending=descending,
            projection=projection,
        )
        specs = page.get("specs", [])
        if not isinstance(specs, list) or not specs:
            break

        filtered_specs = _apply_client_side_filters(
            specs,
            condition_name,
            condition_type,
            condition_unit,
            condition_value,
            limit_min_ge,
            limit_min_le,
            limit_typical_ge,
            limit_typical_le,
            limit_max_ge,
            limit_max_le,
        )
        collected_specs.extend(filtered_specs)

        continuation_token = page.get("continuationToken")
        if not continuation_token:
            break

    return collected_specs[:take]


def _fetch_spec_page(
    product_ids: List[str],
    take: int,
    filter_expr: Optional[str],
    order_by: str,
    descending: bool,
    continuation_token: Optional[str],
    condition_name: Optional[str] = None,
    condition_type: Optional[str] = None,
    condition_unit: Optional[str] = None,
    condition_value: Optional[str] = None,
    limit_min_ge: Optional[float] = None,
    limit_min_le: Optional[float] = None,
    limit_typical_ge: Optional[float] = None,
    limit_typical_le: Optional[float] = None,
    limit_max_ge: Optional[float] = None,
    limit_max_le: Optional[float] = None,
) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Fetch one visual page of specs, accumulating across server pages.

    Accumulates across server pages if client-side filters reduce results.

    Returns:
        Tuple of (page_items up to *take*, next continuation_token or None).
    """
    collected: List[Dict[str, Any]] = []
    token = continuation_token

    while len(collected) < take:
        remaining = max(take - len(collected), 1)
        page = _query_specs_once(
            product_ids=product_ids,
            take=remaining,
            continuation_token=token,
            filter_expr=filter_expr,
            order_by=order_by,
            descending=descending,
        )
        specs = page.get("specs", [])
        if not isinstance(specs, list) or not specs:
            token = None
            break

        filtered = _apply_client_side_filters(
            specs,
            condition_name,
            condition_type,
            condition_unit,
            condition_value,
            limit_min_ge,
            limit_min_le,
            limit_typical_ge,
            limit_typical_le,
            limit_max_ge,
            limit_max_le,
        )
        collected.extend(filtered)

        token = page.get("continuationToken")
        if not token:
            break

    return collected[:take], token


def _handle_spec_interactive_pagination(
    product_ids: List[str],
    take: int,
    filter_expr: Optional[str],
    order_by: str,
    descending: bool,
    format_output: str,
    condition_name: Optional[str] = None,
    condition_type: Optional[str] = None,
    condition_unit: Optional[str] = None,
    condition_value: Optional[str] = None,
    limit_min_ge: Optional[float] = None,
    limit_min_le: Optional[float] = None,
    limit_typical_ge: Optional[float] = None,
    limit_typical_le: Optional[float] = None,
    limit_max_ge: Optional[float] = None,
    limit_max_le: Optional[float] = None,
) -> None:
    """Interactively paginate spec list results with server-side fetching."""
    cont: Optional[str] = None
    shown_count = 0

    while True:
        page_items, cont = _fetch_spec_page(
            product_ids=product_ids,
            take=take,
            filter_expr=filter_expr,
            order_by=order_by,
            descending=descending,
            continuation_token=cont,
            condition_name=condition_name,
            condition_type=condition_type,
            condition_unit=condition_unit,
            condition_value=condition_value,
            limit_min_ge=limit_min_ge,
            limit_min_le=limit_min_le,
            limit_typical_ge=limit_typical_ge,
            limit_typical_le=limit_typical_le,
            limit_max_ge=limit_max_ge,
            limit_max_le=limit_max_le,
        )

        if not page_items:
            if shown_count == 0:
                click.echo("No specifications found.")
            break

        shown_count += len(page_items)

        mock_resp: Any = FilteredResponse({"specs": page_items})
        UniversalResponseHandler.handle_list_response(
            resp=mock_resp,
            data_key="specs",
            item_name="specification",
            format_output=format_output,
            formatter_func=_spec_formatter,
            headers=_SPEC_LIST_HEADERS,
            column_widths=_SPEC_LIST_WIDTHS,
            enable_pagination=False,
            page_size=take,
            shown_count=shown_count,
        )

        try:
            sys.stdout.flush()
        except Exception:
            pass

        if not cont:
            break

        if not questionary.confirm("Show next set of results?", default=True).ask():
            break


def _get_product_name(product_id: str) -> str:
    """Fetch the display name for a single product ID."""
    try:
        resp = make_api_request("GET", f"{_get_testmonitor_base_url()}/products/{product_id}")
        resp.raise_for_status()
        data = resp.json()
        return str(data.get("name") or data.get("partNumber") or product_id)
    except Exception:
        return product_id


def _build_product_name_map(product_ids: List[str]) -> Dict[str, str]:
    """Build a mapping of product IDs to display names."""
    name_map: Dict[str, str] = {}
    for pid in set(product_ids):
        if pid and pid not in name_map:
            name_map[pid] = _get_product_name(pid)
    return name_map


def _spec_formatter(specification: Dict[str, Any]) -> List[str]:
    """Format a specification row for table output."""
    workspace_map = _spec_formatter.workspace_map  # type: ignore[attr-defined]
    product_map = _spec_formatter.product_map  # type: ignore[attr-defined]
    product_id = str(specification.get("productId", ""))
    return [
        product_map.get(product_id, product_id),
        str(specification.get("specId", "")),
        str(specification.get("name", "")),
        str(specification.get("type", "")),
        _format_limit(specification.get("limit")),
        _format_conditions_summary(specification),
        get_workspace_display_name(str(specification.get("workspace", "")), workspace_map),
    ]


def _render_spec_details(specification: Dict[str, Any], workspace_map: Dict[str, str]) -> None:
    """Render a single specification in a detailed table view."""
    rows = [
        ["ID", str(specification.get("id", ""))],
        ["Product ID", str(specification.get("productId", ""))],
        ["Spec ID", str(specification.get("specId", ""))],
        ["Name", str(specification.get("name", ""))],
        ["Category", str(specification.get("category", ""))],
        ["Type", str(specification.get("type", ""))],
        ["Symbol", str(specification.get("symbol", ""))],
        ["Block", str(specification.get("block", ""))],
        ["Limit", _format_limit(specification.get("limit"))],
        ["Unit", str(specification.get("unit", ""))],
        [
            "Workspace",
            get_workspace_display_name(str(specification.get("workspace", "")), workspace_map),
        ],
        ["Created At", str(specification.get("createdAt", ""))],
        ["Created By", str(specification.get("createdBy", ""))],
        ["Updated At", str(specification.get("updatedAt", ""))],
        ["Updated By", str(specification.get("updatedBy", ""))],
        ["Version", str(specification.get("version", ""))],
    ]

    render_table(headers=["FIELD", "VALUE"], column_widths=[18, 80], rows=rows, show_total=False)

    keywords = specification.get("keywords")
    if isinstance(keywords, list) and keywords:
        click.echo(f"\nKeywords: {', '.join(str(keyword) for keyword in keywords)}")

    properties = specification.get("properties")
    if isinstance(properties, dict) and properties:
        click.echo("\nProperties:")
        for key, value in properties.items():
            click.echo(f"  {key}: {value}")

    conditions = specification.get("conditions")
    if isinstance(conditions, list) and conditions:
        click.echo("\nConditions:")
        for index, condition in enumerate(conditions, start=1):
            if not isinstance(condition, dict):
                continue
            name = str(condition.get("name", f"Condition {index}"))
            value_str = _format_condition_value(condition.get("value"))
            click.echo(f"  {index}. {name}")
            if value_str:
                click.echo(f"     {value_str}")


def _apply_spec_options(
    spec_data: Dict[str, Any],
    product_id: Optional[str],
    spec_id: Optional[str],
    name: Optional[str],
    category: Optional[str],
    spec_type: Optional[str],
    symbol: Optional[str],
    block: Optional[str],
    unit: Optional[str],
    workspace: Optional[str],
    keywords: Tuple[str, ...],
    properties: Tuple[str, ...],
    conditions: Tuple[str, ...],
    condition_file: Optional[str],
    limit_min: Optional[float],
    limit_typical: Optional[float],
    limit_max: Optional[float],
) -> Dict[str, Any]:
    """Apply CLI option values to a specification payload."""
    if product_id:
        spec_data["productId"] = _resolve_product_id(product_id)
    if spec_id:
        spec_data["specId"] = spec_id
    if name is not None:
        spec_data["name"] = name
    if category is not None:
        spec_data["category"] = category
    if spec_type is not None:
        spec_data["type"] = _normalize_spec_type(spec_type)
    if symbol is not None:
        spec_data["symbol"] = symbol
    if block is not None:
        spec_data["block"] = block
    if unit is not None:
        spec_data["unit"] = unit

    resolved_workspace = _resolve_spec_workspace(spec_data, workspace)
    if resolved_workspace:
        spec_data["workspace"] = resolved_workspace

    parsed_limit = _build_limit(limit_min, limit_typical, limit_max)
    if parsed_limit is not None:
        spec_data["limit"] = parsed_limit

    parsed_conditions = _load_conditions(conditions, condition_file)
    if parsed_conditions is not None:
        spec_data["conditions"] = parsed_conditions

    if keywords:
        spec_data["keywords"] = list(keywords)
    if properties:
        spec_data["properties"] = _parse_properties(properties)

    # Normalize type from file payload only when CLI did not already set it.
    if spec_type is None:
        existing_type = spec_data.get("type")
        if existing_type is not None:
            spec_data["type"] = _normalize_spec_type(str(existing_type))

    return spec_data


def _resolve_filter_and_workspace(
    workspace_filter: Optional[str],
    spec_id: Optional[str],
    name: Optional[str],
    category: Optional[str],
    spec_type: Optional[str],
    block: Optional[str],
    symbol: Optional[str],
    unit: Optional[str],
    created_by: Optional[str],
    updated_by: Optional[str],
    custom_filter: Optional[str],
) -> Optional[str]:
    """Build filter expression after resolving the workspace."""
    effective_workspace = get_effective_workspace(workspace_filter)
    resolved_workspace = resolve_workspace_id(effective_workspace) if effective_workspace else None
    return _build_spec_filter(
        spec_id=spec_id,
        name=name,
        category=category,
        spec_type=spec_type,
        block=block,
        symbol=symbol,
        unit=unit,
        workspace=resolved_workspace,
        created_by=created_by,
        updated_by=updated_by,
        custom_filter=custom_filter,
    )


# ---------------------------------------------------------------------------
# Command registration
# ---------------------------------------------------------------------------


def register_spec_commands(cli: Any) -> None:
    """Register the 'spec' command group and its subcommands."""

    @cli.group(name="spec")
    def spec() -> None:
        """Manage SystemLink specifications."""
        pass

    # -- list ---------------------------------------------------------------

    @spec.command(name="list")
    @click.option(
        "--product",
        "product_ids",
        multiple=True,
        required=True,
        help="Product name, part number, or ID. Repeat for multiple products.",
    )
    @click.option("--spec-id", help="Filter by exact specification ID")
    @click.option("--name", help="Filter by specification name (contains match)")
    @click.option("--category", help="Filter by category (contains match)")
    @click.option(
        "--type",
        "spec_type",
        type=click.Choice(SPEC_TYPES, case_sensitive=False),
        help="Filter by specification type",
    )
    @click.option("--block", help="Filter by block name (contains match)")
    @click.option("--symbol", help="Filter by symbol (contains match)")
    @click.option("--unit", help="Filter by unit (contains match)")
    @click.option(
        "-w",
        "--workspace",
        "workspace_filter",
        help="Filter by workspace name or ID. Use 'all' to disable the profile default.",
    )
    @click.option("--created-by", help="Filter by creator user ID")
    @click.option("--updated-by", help="Filter by updater user ID")
    @click.option("--filter", "custom_filter", help="Advanced Dynamic Linq filter")
    @click.option("--condition-name", help="Filter by condition name (contains match)")
    @click.option(
        "--condition-type",
        type=click.Choice(CONDITION_TYPES, case_sensitive=False),
        help="Filter by condition type",
    )
    @click.option("--condition-unit", help="Filter by condition unit (contains match)")
    @click.option("--condition-value", help="Filter by discrete or range condition values")
    @click.option("--limit-min-ge", type=float, help="Filter: limit.min >= value")
    @click.option("--limit-min-le", type=float, help="Filter: limit.min <= value")
    @click.option("--limit-typical-ge", type=float, help="Filter: limit.typical >= value")
    @click.option("--limit-typical-le", type=float, help="Filter: limit.typical <= value")
    @click.option("--limit-max-ge", type=float, help="Filter: limit.max >= value")
    @click.option("--limit-max-le", type=float, help="Filter: limit.max <= value")
    @click.option(
        "--order-by",
        type=click.Choice(SPEC_ORDER_BY_FIELDS, case_sensitive=False),
        default="ID",
        show_default=True,
        help="Field to sort by",
    )
    @click.option("--descending", is_flag=True, help="Sort results in descending order")
    @click.option(
        "-t",
        "--take",
        "take",
        type=int,
        default=25,
        show_default=True,
        help="Items per page for table output, or max items for JSON output",
    )
    @click.option(
        "-f",
        "--format",
        "format_output",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    def list_specifications(
        product_ids: Tuple[str, ...],
        spec_id: Optional[str],
        name: Optional[str],
        category: Optional[str],
        spec_type: Optional[str],
        block: Optional[str],
        symbol: Optional[str],
        unit: Optional[str],
        workspace_filter: Optional[str],
        created_by: Optional[str],
        updated_by: Optional[str],
        custom_filter: Optional[str],
        condition_name: Optional[str],
        condition_type: Optional[str],
        condition_unit: Optional[str],
        condition_value: Optional[str],
        limit_min_ge: Optional[float],
        limit_min_le: Optional[float],
        limit_typical_ge: Optional[float],
        limit_typical_le: Optional[float],
        limit_max_ge: Optional[float],
        limit_max_le: Optional[float],
        order_by: str,
        descending: bool,
        take: int,
        format_output: str,
    ) -> None:
        """List specifications for one or more products."""
        normalized_format = validate_output_format(format_output)
        if take <= 0:
            click.echo("\u2717 --take must be greater than 0", err=True)
            sys.exit(ExitCodes.INVALID_INPUT)

        resolved_product_ids = [_resolve_product_id(p) for p in product_ids]

        filter_expr = _resolve_filter_and_workspace(
            workspace_filter,
            spec_id=spec_id,
            name=name,
            category=category,
            spec_type=spec_type,
            block=block,
            symbol=symbol,
            unit=unit,
            created_by=created_by,
            updated_by=updated_by,
            custom_filter=custom_filter,
        )

        try:
            if normalized_format == "json":
                # JSON: collect all matching specs up to --take and dump at once
                specs = _collect_specs(
                    product_ids=resolved_product_ids,
                    take=take,
                    filter_expr=filter_expr,
                    order_by=order_by.upper(),
                    descending=descending,
                    condition_name=condition_name,
                    condition_type=condition_type,
                    condition_unit=condition_unit,
                    condition_value=condition_value,
                    limit_min_ge=limit_min_ge,
                    limit_min_le=limit_min_le,
                    limit_typical_ge=limit_typical_ge,
                    limit_typical_le=limit_typical_le,
                    limit_max_ge=limit_max_ge,
                    limit_max_le=limit_max_le,
                )
                filtered_resp: Any = FilteredResponse({"specs": specs})
                UniversalResponseHandler.handle_list_response(
                    resp=filtered_resp,
                    data_key="specs",
                    item_name="specification",
                    format_output=normalized_format,
                    formatter_func=_spec_formatter,
                    headers=_SPEC_LIST_HEADERS,
                    column_widths=_SPEC_LIST_WIDTHS,
                    enable_pagination=False,
                    page_size=take,
                )
            else:
                # Table: interactive server-side pagination — fetch one page at
                # a time and prompt the user before fetching the next.
                _spec_formatter.workspace_map = get_workspace_map()  # type: ignore[attr-defined]
                _spec_formatter.product_map = _build_product_name_map(resolved_product_ids)  # type: ignore[attr-defined]
                _handle_spec_interactive_pagination(
                    product_ids=resolved_product_ids,
                    take=take,
                    filter_expr=filter_expr,
                    order_by=order_by.upper(),
                    descending=descending,
                    format_output=normalized_format,
                    condition_name=condition_name,
                    condition_type=condition_type,
                    condition_unit=condition_unit,
                    condition_value=condition_value,
                    limit_min_ge=limit_min_ge,
                    limit_min_le=limit_min_le,
                    limit_typical_ge=limit_typical_ge,
                    limit_typical_le=limit_typical_le,
                    limit_max_ge=limit_max_ge,
                    limit_max_le=limit_max_le,
                )
        except Exception as exc:
            handle_api_error(exc)

    # -- query --------------------------------------------------------------

    @spec.command(name="query")
    @click.option(
        "--product",
        "product_ids",
        multiple=True,
        required=True,
        help="Product name, part number, or ID. Repeat for multiple products.",
    )
    @click.option("--spec-id", help="Filter by exact specification ID")
    @click.option("--name", help="Filter by specification name (contains match)")
    @click.option("--category", help="Filter by category (contains match)")
    @click.option(
        "--type",
        "spec_type",
        type=click.Choice(SPEC_TYPES, case_sensitive=False),
        help="Filter by specification type",
    )
    @click.option("--block", help="Filter by block name (contains match)")
    @click.option("--symbol", help="Filter by symbol (contains match)")
    @click.option("--unit", help="Filter by unit (contains match)")
    @click.option(
        "-w",
        "--workspace",
        "workspace_filter",
        help="Filter by workspace name or ID. Use 'all' to disable the profile default.",
    )
    @click.option("--created-by", help="Filter by creator user ID")
    @click.option("--updated-by", help="Filter by updater user ID")
    @click.option("--filter", "custom_filter", help="Advanced Dynamic Linq filter")
    @click.option("--condition-name", help="Filter by condition name (contains match)")
    @click.option(
        "--condition-type",
        type=click.Choice(CONDITION_TYPES, case_sensitive=False),
        help="Filter by condition type",
    )
    @click.option("--condition-unit", help="Filter by condition unit (contains match)")
    @click.option("--condition-value", help="Filter by discrete or range condition values")
    @click.option("--limit-min-ge", type=float, help="Filter: limit.min >= value")
    @click.option("--limit-min-le", type=float, help="Filter: limit.min <= value")
    @click.option("--limit-typical-ge", type=float, help="Filter: limit.typical >= value")
    @click.option("--limit-typical-le", type=float, help="Filter: limit.typical <= value")
    @click.option("--limit-max-ge", type=float, help="Filter: limit.max >= value")
    @click.option("--limit-max-le", type=float, help="Filter: limit.max <= value")
    @click.option(
        "--projection",
        "projection_fields",
        multiple=True,
        type=click.Choice(SPEC_PROJECTION_FIELDS, case_sensitive=False),
        help="Field to include in the returned payload. Repeatable.",
    )
    @click.option(
        "--include-limits",
        is_flag=True,
        help="Convenience projection: include the LIMIT field.",
    )
    @click.option(
        "--include-conditions",
        is_flag=True,
        help="Convenience projection: include all condition-related fields.",
    )
    @click.option(
        "--order-by",
        type=click.Choice(SPEC_ORDER_BY_FIELDS, case_sensitive=False),
        default="ID",
        show_default=True,
        help="Field to sort by",
    )
    @click.option("--descending", is_flag=True, help="Sort results in descending order")
    @click.option("--continuation-token", help="Continuation token from a previous query")
    @click.option(
        "-t",
        "--take",
        "take",
        type=int,
        default=25,
        show_default=True,
        help="Maximum number of specifications to request in this query",
    )
    @click.option(
        "-f",
        "--format",
        "format_output",
        type=click.Choice(["table", "json"]),
        default="json",
        show_default=True,
        help="Output format. JSON preserves the continuation token.",
    )
    def query_specifications(
        product_ids: Tuple[str, ...],
        spec_id: Optional[str],
        name: Optional[str],
        category: Optional[str],
        spec_type: Optional[str],
        block: Optional[str],
        symbol: Optional[str],
        unit: Optional[str],
        workspace_filter: Optional[str],
        created_by: Optional[str],
        updated_by: Optional[str],
        custom_filter: Optional[str],
        condition_name: Optional[str],
        condition_type: Optional[str],
        condition_unit: Optional[str],
        condition_value: Optional[str],
        limit_min_ge: Optional[float],
        limit_min_le: Optional[float],
        limit_typical_ge: Optional[float],
        limit_typical_le: Optional[float],
        limit_max_ge: Optional[float],
        limit_max_le: Optional[float],
        projection_fields: Tuple[str, ...],
        include_limits: bool,
        include_conditions: bool,
        order_by: str,
        descending: bool,
        continuation_token: Optional[str],
        take: int,
        format_output: str,
    ) -> None:
        """Run a single raw specification query request."""
        normalized_format = validate_output_format(format_output)
        if take <= 0:
            click.echo("\u2717 --take must be greater than 0", err=True)
            sys.exit(ExitCodes.INVALID_INPUT)

        resolved_product_ids = [_resolve_product_id(p) for p in product_ids]

        filter_expr = _resolve_filter_and_workspace(
            workspace_filter,
            spec_id=spec_id,
            name=name,
            category=category,
            spec_type=spec_type,
            block=block,
            symbol=symbol,
            unit=unit,
            created_by=created_by,
            updated_by=updated_by,
            custom_filter=custom_filter,
        )
        projection = _projection_field_set(
            projection_fields,
            include_limits=include_limits,
            include_conditions=include_conditions,
        )

        try:
            response_data = _query_specs_once(
                product_ids=resolved_product_ids,
                take=take,
                continuation_token=continuation_token,
                filter_expr=filter_expr,
                order_by=order_by.upper(),
                descending=descending,
                projection=projection,
            )

            specs = response_data.get("specs", [])
            if isinstance(specs, list):
                response_data["specs"] = _apply_client_side_filters(
                    specs,
                    condition_name,
                    condition_type,
                    condition_unit,
                    condition_value,
                    limit_min_ge,
                    limit_min_le,
                    limit_typical_ge,
                    limit_typical_le,
                    limit_max_ge,
                    limit_max_le,
                )

            if normalized_format == "json":
                click.echo(json.dumps(response_data, indent=2))
                return

            specs = response_data.get("specs", [])
            if not isinstance(specs, list) or not specs:
                click.echo("No specifications found.")
                return

            _spec_formatter.workspace_map = get_workspace_map()  # type: ignore[attr-defined]
            _spec_formatter.product_map = _build_product_name_map(resolved_product_ids)  # type: ignore[attr-defined]
            filtered_resp: Any = FilteredResponse({"specs": specs})
            UniversalResponseHandler.handle_list_response(
                resp=filtered_resp,
                data_key="specs",
                item_name="specification",
                format_output=normalized_format,
                formatter_func=_spec_formatter,
                headers=_SPEC_LIST_HEADERS,
                column_widths=_SPEC_LIST_WIDTHS,
                enable_pagination=False,
            )
            next_token = response_data.get("continuationToken")
            if next_token:
                click.echo(
                    "\nMore results are available. " "Re-run with --continuation-token to continue."
                )
        except Exception as exc:
            handle_api_error(exc)

    # -- get ----------------------------------------------------------------

    @spec.command(name="get")
    @click.option("--id", "specification_id", required=True, help="Specification ID to retrieve")
    @click.option(
        "-f",
        "--format",
        "format_output",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    def get_specification(specification_id: str, format_output: str) -> None:
        """Show a specification by ID."""
        normalized_format = validate_output_format(format_output)
        try:
            resp = make_api_request("GET", f"{_get_spec_base_url()}/specs/{specification_id}")
            data = resp.json()
            if normalized_format == "json":
                click.echo(json.dumps(data, indent=2))
                return

            if not isinstance(data, dict):
                click.echo("\u2717 Unexpected response while retrieving specification.", err=True)
                sys.exit(ExitCodes.GENERAL_ERROR)
            _render_spec_details(data, get_workspace_map())
        except Exception as exc:
            handle_api_error(exc)

    # -- export -------------------------------------------------------------

    @spec.command(name="export")
    @click.option(
        "--product",
        "product_ids",
        multiple=True,
        required=True,
        help="Product name, part number, or ID. Repeat for multiple products.",
    )
    @click.option("--spec-id", help="Filter by exact specification ID")
    @click.option("--name", help="Filter by specification name (contains match)")
    @click.option("--category", help="Filter by category (contains match)")
    @click.option(
        "--type",
        "spec_type",
        type=click.Choice(SPEC_TYPES, case_sensitive=False),
        help="Filter by specification type",
    )
    @click.option("--block", help="Filter by block name (contains match)")
    @click.option("--symbol", help="Filter by symbol (contains match)")
    @click.option("--unit", help="Filter by unit (contains match)")
    @click.option(
        "-w",
        "--workspace",
        "workspace_filter",
        help="Filter by workspace name or ID. Use 'all' to disable the profile default.",
    )
    @click.option("--created-by", help="Filter by creator user ID")
    @click.option("--updated-by", help="Filter by updater user ID")
    @click.option("--filter", "custom_filter", help="Advanced Dynamic Linq filter")
    @click.option("--condition-name", help="Filter by condition name (contains match)")
    @click.option(
        "--condition-type",
        type=click.Choice(CONDITION_TYPES, case_sensitive=False),
        help="Filter by condition type",
    )
    @click.option("--condition-unit", help="Filter by condition unit (contains match)")
    @click.option("--condition-value", help="Filter by discrete or range condition values")
    @click.option("--limit-min-ge", type=float, help="Filter: limit.min >= value")
    @click.option("--limit-min-le", type=float, help="Filter: limit.min <= value")
    @click.option("--limit-typical-ge", type=float, help="Filter: limit.typical >= value")
    @click.option("--limit-typical-le", type=float, help="Filter: limit.typical <= value")
    @click.option("--limit-max-ge", type=float, help="Filter: limit.max >= value")
    @click.option("--limit-max-le", type=float, help="Filter: limit.max <= value")
    @click.option(
        "--projection",
        "projection_fields",
        multiple=True,
        type=click.Choice(SPEC_PROJECTION_FIELDS, case_sensitive=False),
        help="Field to include in the returned payload. Repeatable.",
    )
    @click.option(
        "--include-limits",
        is_flag=True,
        help="Convenience projection: include the LIMIT field.",
    )
    @click.option(
        "--include-conditions",
        is_flag=True,
        help="Convenience projection: include all condition-related fields.",
    )
    @click.option(
        "--order-by",
        type=click.Choice(SPEC_ORDER_BY_FIELDS, case_sensitive=False),
        default="ID",
        show_default=True,
        help="Field to sort by",
    )
    @click.option("--descending", is_flag=True, help="Sort results in descending order")
    @click.option(
        "-t",
        "--take",
        type=int,
        default=1000,
        show_default=True,
        help="Maximum number of specifications to export (default is higher than list)",
    )
    @click.option(
        "--output",
        "output_file",
        "-o",
        help="Output JSON file (default: derived from product ID)",
    )
    def export_specifications(
        product_ids: Tuple[str, ...],
        spec_id: Optional[str],
        name: Optional[str],
        category: Optional[str],
        spec_type: Optional[str],
        block: Optional[str],
        symbol: Optional[str],
        unit: Optional[str],
        workspace_filter: Optional[str],
        created_by: Optional[str],
        updated_by: Optional[str],
        custom_filter: Optional[str],
        condition_name: Optional[str],
        condition_type: Optional[str],
        condition_unit: Optional[str],
        condition_value: Optional[str],
        limit_min_ge: Optional[float],
        limit_min_le: Optional[float],
        limit_typical_ge: Optional[float],
        limit_typical_le: Optional[float],
        limit_max_ge: Optional[float],
        limit_max_le: Optional[float],
        projection_fields: Tuple[str, ...],
        include_limits: bool,
        include_conditions: bool,
        order_by: str,
        descending: bool,
        take: int,
        output_file: Optional[str],
    ) -> None:
        """Export specifications to a JSON payload file."""
        if take <= 0:
            click.echo("\u2717 --take must be greater than 0", err=True)
            sys.exit(ExitCodes.INVALID_INPUT)

        resolved_product_ids = [_resolve_product_id(p) for p in product_ids]

        filter_expr = _resolve_filter_and_workspace(
            workspace_filter,
            spec_id=spec_id,
            name=name,
            category=category,
            spec_type=spec_type,
            block=block,
            symbol=symbol,
            unit=unit,
            created_by=created_by,
            updated_by=updated_by,
            custom_filter=custom_filter,
        )
        projection = _projection_field_set(
            projection_fields,
            include_limits=include_limits,
            include_conditions=include_conditions,
        )

        try:
            specifications = _collect_specs(
                product_ids=resolved_product_ids,
                take=take,
                filter_expr=filter_expr,
                order_by=order_by.upper(),
                descending=descending,
                projection=projection,
                condition_name=condition_name,
                condition_type=condition_type,
                condition_unit=condition_unit,
                condition_value=condition_value,
                limit_min_ge=limit_min_ge,
                limit_min_le=limit_min_le,
                limit_typical_ge=limit_typical_ge,
                limit_typical_le=limit_typical_le,
                limit_max_ge=limit_max_ge,
                limit_max_le=limit_max_le,
            )
            export_path = output_file or _default_export_filename(resolved_product_ids)
            save_json_file({"specs": specifications}, export_path)
            format_success(
                "Specifications exported",
                {"count": len(specifications), "output": export_path},
            )
        except Exception as exc:
            handle_api_error(exc)

    # -- import -------------------------------------------------------------

    @spec.command(name="import")
    @click.option(
        "--file",
        "input_file",
        required=True,
        help="Input JSON file containing a specification object or 'specs' array.",
    )
    def import_specifications(input_file: str) -> None:
        """Import one or more specifications from a JSON payload file."""
        check_readonly_mode("import specifications")

        try:
            specifications = _load_spec_list_file(input_file)
            product_workspace_cache: Dict[str, Optional[str]] = {}
            for specification in specifications:
                resolved_workspace = _resolve_spec_workspace(
                    specification,
                    workspace=None,
                    product_workspace_cache=product_workspace_cache,
                )
                if resolved_workspace:
                    specification["workspace"] = resolved_workspace

                existing_type = specification.get("type")
                if existing_type is not None:
                    specification["type"] = _normalize_spec_type(str(existing_type))

                _validate_spec_required_fields(specification, ["productId", "specId", "type"])

            resp = make_api_request(
                "POST",
                f"{_get_spec_base_url()}/specs",
                payload={"specs": specifications},
            )
            _report_bulk_create_result(resp.json() if resp.text.strip() else {})
        except Exception as exc:
            handle_api_error(exc)

    # -- create -------------------------------------------------------------

    @spec.command(name="create")
    @click.option("--file", "input_file", help="Input JSON file with a specification object")
    @click.option("--product", "product_id", help="Product name, part number, or ID")
    @click.option("--spec-id", help="Unique spec identifier within the product/workspace")
    @click.option("--name", help="Display name for the specification")
    @click.option("--category", help="Category for the specification")
    @click.option(
        "--type",
        "spec_type",
        type=click.Choice(SPEC_TYPES, case_sensitive=False),
        help="Specification type",
    )
    @click.option("--symbol", help="Short symbol for the specification")
    @click.option("--block", help="Block name for the specification")
    @click.option("--unit", help="Unit for the specification")
    @click.option(
        "-w",
        "--workspace",
        help="Workspace name or ID. Defaults to the active profile workspace when available.",
    )
    @click.option("--limit-min", type=float, help="Minimum specification limit")
    @click.option("--limit-typical", type=float, help="Typical specification limit")
    @click.option("--limit-max", type=float, help="Maximum specification limit")
    @click.option(
        "--condition",
        "conditions",
        multiple=True,
        help="Condition JSON object. Repeat for multiple conditions.",
    )
    @click.option(
        "--condition-file",
        help="JSON file containing an array of condition objects.",
    )
    @click.option(
        "--keyword",
        "keywords",
        multiple=True,
        help="Keyword to attach to the specification. Repeatable.",
    )
    @click.option(
        "--property",
        "properties",
        multiple=True,
        help="Property in key=value format. Repeatable.",
    )
    def create_specification(
        input_file: Optional[str],
        product_id: Optional[str],
        spec_id: Optional[str],
        name: Optional[str],
        category: Optional[str],
        spec_type: Optional[str],
        symbol: Optional[str],
        block: Optional[str],
        unit: Optional[str],
        workspace: Optional[str],
        limit_min: Optional[float],
        limit_typical: Optional[float],
        limit_max: Optional[float],
        conditions: Tuple[str, ...],
        condition_file: Optional[str],
        keywords: Tuple[str, ...],
        properties: Tuple[str, ...],
    ) -> None:
        """Create a specification."""
        check_readonly_mode("create a specification")

        try:
            spec_data = _load_single_spec_file(input_file)
            spec_data = _apply_spec_options(
                spec_data=spec_data,
                product_id=product_id,
                spec_id=spec_id,
                name=name,
                category=category,
                spec_type=spec_type,
                symbol=symbol,
                block=block,
                unit=unit,
                workspace=workspace,
                keywords=keywords,
                properties=properties,
                conditions=conditions,
                condition_file=condition_file,
                limit_min=limit_min,
                limit_typical=limit_typical,
                limit_max=limit_max,
            )
            _validate_spec_required_fields(spec_data, ["productId", "specId", "type"])

            resp = make_api_request(
                "POST", f"{_get_spec_base_url()}/specs", payload={"specs": [spec_data]}
            )
            _report_mutation_result(
                resp.json() if resp.text.strip() else {},
                success_key="createdSpecs",
                operation="created",
            )
        except Exception as exc:
            handle_api_error(exc)

    # -- update -------------------------------------------------------------

    @spec.command(name="update")
    @click.option("--file", "input_file", help="Input JSON file with a specification object")
    @click.option("--id", "specification_id", help="Specification ID to update")
    @click.option("--version", type=int, help="Current specification version")
    @click.option("--product", "product_id", help="Product name, part number, or ID")
    @click.option("--spec-id", help="Update spec identifier")
    @click.option("--name", help="Update display name")
    @click.option("--category", help="Update category")
    @click.option(
        "--type",
        "spec_type",
        type=click.Choice(SPEC_TYPES, case_sensitive=False),
        help="Update specification type",
    )
    @click.option("--symbol", help="Update symbol")
    @click.option("--block", help="Update block")
    @click.option("--unit", help="Update unit")
    @click.option(
        "-w",
        "--workspace",
        help="Update workspace name or ID. Defaults to the active profile workspace.",
    )
    @click.option("--limit-min", type=float, help="Update minimum specification limit")
    @click.option("--limit-typical", type=float, help="Update typical specification limit")
    @click.option("--limit-max", type=float, help="Update maximum specification limit")
    @click.option(
        "--condition",
        "conditions",
        multiple=True,
        help="Condition JSON object. Repeat for multiple conditions.",
    )
    @click.option(
        "--condition-file",
        help="JSON file containing an array of condition objects.",
    )
    @click.option(
        "--keyword",
        "keywords",
        multiple=True,
        help="Replace specification keywords. Repeatable.",
    )
    @click.option(
        "--property",
        "properties",
        multiple=True,
        help="Replace specification properties in key=value format. Repeatable.",
    )
    def update_specification(
        input_file: Optional[str],
        specification_id: Optional[str],
        version: Optional[int],
        product_id: Optional[str],
        spec_id: Optional[str],
        name: Optional[str],
        category: Optional[str],
        spec_type: Optional[str],
        symbol: Optional[str],
        block: Optional[str],
        unit: Optional[str],
        workspace: Optional[str],
        limit_min: Optional[float],
        limit_typical: Optional[float],
        limit_max: Optional[float],
        conditions: Tuple[str, ...],
        condition_file: Optional[str],
        keywords: Tuple[str, ...],
        properties: Tuple[str, ...],
    ) -> None:
        """Update a specification."""
        check_readonly_mode("update a specification")

        try:
            spec_data = _load_single_spec_file(input_file)
            if specification_id:
                spec_data["id"] = specification_id
            if version is not None:
                spec_data["version"] = version

            spec_data = _apply_spec_options(
                spec_data=spec_data,
                product_id=product_id,
                spec_id=spec_id,
                name=name,
                category=category,
                spec_type=spec_type,
                symbol=symbol,
                block=block,
                unit=unit,
                workspace=workspace,
                keywords=keywords,
                properties=properties,
                conditions=conditions,
                condition_file=condition_file,
                limit_min=limit_min,
                limit_typical=limit_typical,
                limit_max=limit_max,
            )
            _validate_spec_required_fields(spec_data, ["id", "version"])

            resp = make_api_request(
                "POST",
                f"{_get_spec_base_url()}/update-specs",
                payload={"specs": [spec_data]},
            )
            _report_mutation_result(
                resp.json() if resp.text.strip() else {},
                success_key="updatedSpecs",
                operation="updated",
            )
        except Exception as exc:
            handle_api_error(exc)

    # -- delete -------------------------------------------------------------

    @spec.command(name="delete")
    @click.option(
        "--id",
        "specification_ids",
        multiple=True,
        required=True,
        help="Specification ID to delete. Repeat for multiple IDs.",
    )
    @click.option("--force", is_flag=True, help="Skip confirmation prompt")
    def delete_specification(specification_ids: Tuple[str, ...], force: bool) -> None:
        """Delete one or more specifications."""
        check_readonly_mode("delete specification(s)")

        ids = list(specification_ids)
        if not confirm_bulk_operation("delete", "specification", len(ids), force=force):
            return

        try:
            resp = make_api_request(
                "POST",
                f"{_get_spec_base_url()}/delete-specs",
                payload={"ids": ids},
            )

            if resp.status_code == 204:
                _report_delete_result(None, ids)
                return

            _report_delete_result(resp.json() if resp.text.strip() else {}, ids)
        except Exception as exc:
            handle_api_error(exc)
