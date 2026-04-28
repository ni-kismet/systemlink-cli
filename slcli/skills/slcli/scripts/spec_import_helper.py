"""Scaffold and validate datasheet specification import payloads."""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

VALID_SPEC_TYPES = {"PARAMETRIC", "FUNCTIONAL"}
VALID_CONDITION_TYPES = {"NUMERIC", "STRING"}


def _load_template() -> dict[str, Any]:
    template_path = Path(__file__).resolve().parents[1] / "references" / "import-specs.min.json"
    return json.loads(template_path.read_text(encoding="utf-8"))


def _substitute_placeholders(value: Any, replacements: dict[str, str]) -> Any:
    if isinstance(value, str):
        result = value
        for source, target in replacements.items():
            result = result.replace(source, target)
        return result
    if isinstance(value, list):
        return [_substitute_placeholders(item, replacements) for item in value]
    if isinstance(value, dict):
        return {key: _substitute_placeholders(item, replacements) for key, item in value.items()}
    return value


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def _is_number(value: Any) -> bool:
    if isinstance(value, bool):
        return False
    if not isinstance(value, (int, float)):
        return False
    return math.isfinite(float(value))


def _validate_limit(limit: Any, prefix: str, errors: list[str], require_bound: bool) -> None:
    if not isinstance(limit, dict):
        errors.append(f"{prefix} must be an object")
        return

    present_bounds = 0
    for bound_name in ("min", "typical", "max"):
        if bound_name not in limit:
            continue
        present_bounds += 1
        if not _is_number(limit[bound_name]):
            errors.append(f"{prefix}.{bound_name} must be numeric")

    if require_bound and present_bounds == 0:
        errors.append(f"{prefix} must include at least one of min, typical, or max")


def _validate_numeric_range(range_items: Any, prefix: str, errors: list[str]) -> None:
    if not isinstance(range_items, list) or not range_items:
        errors.append(f"{prefix} must be a non-empty list")
        return

    for index, item in enumerate(range_items):
        item_prefix = f"{prefix}[{index}]"
        if not isinstance(item, dict):
            errors.append(f"{item_prefix} must be an object")
            continue
        if "min" not in item and "max" not in item:
            errors.append(f"{item_prefix} must include min or max")
        for bound_name in ("min", "max", "step"):
            if bound_name in item and not _is_number(item[bound_name]):
                errors.append(f"{item_prefix}.{bound_name} must be numeric")


def _validate_conditions(conditions: Any, prefix: str, errors: list[str]) -> None:
    if not isinstance(conditions, list):
        errors.append(f"{prefix} must be a list")
        return

    for index, condition in enumerate(conditions):
        condition_prefix = f"{prefix}[{index}]"
        if not isinstance(condition, dict):
            errors.append(f"{condition_prefix} must be an object")
            continue

        name = condition.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"{condition_prefix}.name must be a non-empty string")

        value = condition.get("value")
        if not isinstance(value, dict):
            errors.append(f"{condition_prefix}.value must be an object")
            continue

        condition_type = value.get("conditionType")
        if condition_type not in VALID_CONDITION_TYPES:
            errors.append(
                f"{condition_prefix}.value.conditionType must be one of "
                f"{sorted(VALID_CONDITION_TYPES)}"
            )
            continue

        has_discrete = "discrete" in value
        has_range = "range" in value
        if not has_discrete and not has_range:
            errors.append(f"{condition_prefix}.value must include discrete or range")

        if condition_type == "NUMERIC":
            if has_discrete:
                discrete = value["discrete"]
                if not isinstance(discrete, list) or not discrete:
                    errors.append(f"{condition_prefix}.value.discrete must be a non-empty list")
                else:
                    for discrete_index, discrete_value in enumerate(discrete):
                        if not _is_number(discrete_value):
                            errors.append(
                                f"{condition_prefix}.value.discrete[{discrete_index}] must be numeric"
                            )
            if has_range:
                _validate_numeric_range(value["range"], f"{condition_prefix}.value.range", errors)
        elif condition_type == "STRING":
            if has_range:
                errors.append(f"{condition_prefix}.value.range is invalid for STRING conditions")
            if has_discrete:
                discrete = value["discrete"]
                if not isinstance(discrete, list) or not discrete:
                    errors.append(f"{condition_prefix}.value.discrete must be a non-empty list")
                else:
                    for discrete_index, discrete_value in enumerate(discrete):
                        if not isinstance(discrete_value, str) or not discrete_value.strip():
                            errors.append(
                                f"{condition_prefix}.value.discrete[{discrete_index}] "
                                "must be a non-empty string"
                            )


def validate_payload(payload: Any) -> list[str]:
    """Validate a spec import payload and return any discovered errors.

    Args:
        payload: Parsed JSON payload to validate.

    Returns:
        A list of human-readable validation errors. The list is empty when the
        payload is valid.
    """
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["payload root must be an object"]

    specs = payload.get("specs")
    if not isinstance(specs, list):
        return ["payload.specs must be a list"]

    seen_spec_ids: dict[str, int] = {}
    for index, spec in enumerate(specs):
        spec_prefix = f"specs[{index}]"
        if not isinstance(spec, dict):
            errors.append(f"{spec_prefix} must be an object")
            continue

        for field_name in ("productId", "specId", "type"):
            value = spec.get(field_name)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"{spec_prefix}.{field_name} is required")

        spec_id = spec.get("specId")
        if isinstance(spec_id, str) and spec_id.strip():
            if spec_id in seen_spec_ids:
                errors.append(
                    f"duplicate specId {spec_id!r} at specs[{seen_spec_ids[spec_id]}] and {spec_prefix}"
                )
            else:
                seen_spec_ids[spec_id] = index

        spec_type = spec.get("type")
        if isinstance(spec_type, str) and spec_type not in VALID_SPEC_TYPES:
            errors.append(f"{spec_prefix}.type must be one of {sorted(VALID_SPEC_TYPES)}")

        if "limit" in spec:
            _validate_limit(
                spec["limit"],
                f"{spec_prefix}.limit",
                errors,
                require_bound=spec_type == "PARAMETRIC",
            )
        elif spec_type == "PARAMETRIC":
            errors.append(f"{spec_prefix}.limit is required for PARAMETRIC specs")

        if "conditions" in spec:
            _validate_conditions(spec["conditions"], f"{spec_prefix}.conditions", errors)

    return errors


def _handle_init(args: argparse.Namespace) -> int:
    replacements = {
        "<PRODUCT_ID>": args.product_id,
        "<WORKSPACE_ID>": args.workspace,
        "<SOURCE_FILE>": args.source,
    }
    payload = _substitute_placeholders(_load_template(), replacements)
    output_path = Path(args.output)
    _write_json(output_path, payload)
    print(f"Wrote starter payload to {output_path}")
    return 0


def _handle_validate(args: argparse.Namespace) -> int:
    payload_path = Path(args.payload)
    try:
        payload = json.loads(payload_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"File not found: {payload_path}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON in {payload_path}: {exc}", file=sys.stderr)
        return 1

    errors = validate_payload(payload)
    if errors:
        print(f"Validation failed for {payload_path}:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1

    spec_count = len(payload.get("specs", []))
    print(f"Payload valid: {spec_count} specs")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser for the helper script.

    Returns:
        Configured argument parser with `init` and `validate` subcommands.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    init_parser = subparsers.add_parser("init", help="Write a starter import payload")
    init_parser.add_argument("--output", required=True, help="Path to the JSON file to create")
    init_parser.add_argument("--product-id", default="<PRODUCT_ID>", help="Product ID placeholder")
    init_parser.add_argument(
        "--workspace", default="<WORKSPACE_ID>", help="Workspace ID placeholder"
    )
    init_parser.add_argument(
        "--source", default="datasheet.pdf", help="Traceability source file name"
    )
    init_parser.set_defaults(handler=_handle_init)

    validate_parser = subparsers.add_parser("validate", help="Validate an import payload")
    validate_parser.add_argument("payload", help="Path to the JSON payload to validate")
    validate_parser.set_defaults(handler=_handle_validate)

    return parser


def main() -> int:
    """Run the CLI entrypoint.

    Returns:
        Process exit code from the selected subcommand handler.
    """
    parser = build_parser()
    args = parser.parse_args()
    return int(args.handler(args))


if __name__ == "__main__":
    raise SystemExit(main())
