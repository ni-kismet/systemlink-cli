"""Scaffold and validate SystemLink Jupyter notebooks with papermill parameters."""

from __future__ import annotations

import argparse
import json
import keyword
import re
import sys
import uuid
from pathlib import Path
from typing import Any

PARAMETER_TYPES = {
    "string",
    "integer",
    "float",
    "boolean",
    "number",
    "string[]",
    "test_monitor_result_query",
}
OUTPUT_TYPES = {"data_frame", "scalar", "array", "string", "string[]", "vector"}
REPORT_OUTPUT_TYPES = {"data_frame", "scalar", "array"}
SUPPORTED_VERSIONS = {1, 2}

DEFAULT_RESULT_QUERY = 'startedWithin <= "30.0:0:0"'
DEFAULT_RESULT_QUERY_DISPLAY: dict[str, Any] = {
    "products_filter": [],
    "results_filter": [
        {
            "queryOperandUnit": "DAYS",
            "queryOperandValue": 30,
            "queryOperator": "LESS_THAN_OR_EQUAL",
            "queryOperatorName": "startedWithin",
        }
    ],
}

# Inputs SystemLink passes to notebooks published with each interface.
# A type of None means the interface passes a value that is not declared in
# systemlink.parameters, so only the papermill parameter is required.
INTERFACE_INPUTS: dict[str, list[tuple[str, str, str | None]]] = {
    "Assets Grid": [],
    "Data Table Analysis": [],
    "Data Space Analysis": [
        ("trace_data", "Trace data", "string"),
        ("analysis_options", "Analysis options", "string[]"),
        ("workspace_id", "Workspace ID", "string"),
    ],
    "File Analysis": [("file_ids", "File IDs", "string[]")],
    "Periodic Execution": [],
    "Resource Changed Routine": [("context", "Context", None)],
    "Specification Analysis": [
        ("spec_ids", "Specification IDs", "string[]"),
        ("product_id", "Product ID", "string"),
    ],
    "Systems Grid": [],
    "Test Data Analysis": [("result_ids", "Result IDs", "string[]")],
    "Test Data Extraction": [
        ("file_id", "File ID", "string"),
        ("part_number", "Part number", "string"),
        ("notebook_id", "Notebook ID", "string"),
    ],
    "Work Item Automations": [("work_item_ids", "Work item IDs", "string[]")],
    "Work Item Operations": [
        ("workItemId", "Work item ID", "string"),
        ("systemId", "System ID", "string"),
    ],
    "Work Item Scheduler": [("work_item_ids", "Work item IDs", "string[]")],
}
INTERFACE_VERSIONS = {"Work Item Automations": 1}
INTERFACE_OUTPUTS: dict[str, dict[str, str]] = {
    "Systems Grid": {"id": "systems_column", "display_name": "Systems Column", "type": "data_frame"}
}

_ASSIGNMENT_PATTERN = re.compile(r"^([A-Za-z_]\w*)\s*(?::[^=\n]+)?=(?!=)", re.MULTILINE)
_RESULT_GLUE_PATTERN = re.compile(r"""sb\.glue\(\s*["']result["']""")


def _cell_source(cell: dict[str, Any]) -> str:
    source = cell.get("source", "")
    if isinstance(source, list):
        return "".join(str(line) for line in source)
    return str(source)


def _default_for_type(param_type: str | None) -> Any:
    if param_type == "string[]":
        return []
    if param_type == "integer":
        return 0
    if param_type in {"float", "number"}:
        return 0.0
    if param_type == "boolean":
        return False
    if param_type == "test_monitor_result_query":
        return DEFAULT_RESULT_QUERY
    if param_type is None:
        return {}
    return ""


def _value_matches_type(value: Any, param_type: str) -> bool:
    if param_type in {"string", "test_monitor_result_query"}:
        return isinstance(value, str)
    if param_type == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if param_type in {"float", "number"}:
        return isinstance(value, (int, float)) and not isinstance(value, bool)
    if param_type == "boolean":
        return isinstance(value, bool)
    if param_type == "string[]":
        return isinstance(value, list) and all(isinstance(item, str) for item in value)
    return True


def _find_parameters_cells(cells: list[Any]) -> list[dict[str, Any]]:
    return [
        cell
        for cell in cells
        if isinstance(cell, dict) and "parameters" in (cell.get("metadata", {}).get("tags") or [])
    ]


def _validate_named_entries(
    entries: Any, prefix: str, allowed_types: set[str], errors: list[str]
) -> list[dict[str, Any]]:
    if not isinstance(entries, list):
        errors.append(f"{prefix} must be a list")
        return []

    valid: list[dict[str, Any]] = []
    seen: set[str] = set()
    for index, entry in enumerate(entries):
        entry_prefix = f"{prefix}[{index}]"
        if not isinstance(entry, dict):
            errors.append(f"{entry_prefix} must be an object")
            continue
        for field_name in ("id", "display_name", "type"):
            value = entry.get(field_name)
            if not isinstance(value, str) or not value.strip():
                errors.append(f"{entry_prefix}.{field_name} must be a non-empty string")
        entry_id = entry.get("id")
        entry_type = entry.get("type")
        if isinstance(entry_type, str) and entry_type and entry_type not in allowed_types:
            errors.append(f"{entry_prefix}.type must be one of {sorted(allowed_types)}")
        if isinstance(entry_id, str) and entry_id:
            if entry_id in seen:
                errors.append(f"duplicate {prefix} id {entry_id!r}")
            seen.add(entry_id)
            valid.append(entry)
    return valid


def _validate_parameters(
    parameters: list[dict[str, Any]],
    papermill_parameters: dict[str, Any],
    errors: list[str],
    warnings: list[str],
) -> None:
    for parameter in parameters:
        param_id = parameter["id"]
        param_type = parameter.get("type")
        prefix = f"systemlink.parameters[{param_id!r}]"

        if not param_id.isidentifier() or keyword.iskeyword(param_id):
            errors.append(f"{prefix}.id must be a valid Python variable name")

        options = parameter.get("options")
        if options is not None:
            if param_type == "boolean":
                if not isinstance(options, list) or set(map(repr, options)) != {"True", "False"}:
                    errors.append(f"{prefix}.options must be [true, false] for boolean")
                    options = None
            elif (
                not isinstance(options, list)
                or not options
                or not all(isinstance(option, str) for option in options)
            ):
                errors.append(f"{prefix}.options must be a non-empty list of strings")
                options = None
            elif param_type != "string":
                warnings.append(
                    f"{prefix}.options is only rendered as a dropdown for string or boolean"
                )

        if "default_display" in parameter and param_type != "test_monitor_result_query":
            warnings.append(
                f"{prefix}.default_display is only used by test_monitor_result_query parameters"
            )
        if param_type == "test_monitor_result_query" and not isinstance(
            parameter.get("default_display"), dict
        ):
            warnings.append(f"{prefix}.default_display is missing; the query builder starts empty")

        if param_id not in papermill_parameters:
            errors.append(f"papermill.parameters is missing {param_id!r}")
            continue
        default = papermill_parameters[param_id]
        if isinstance(param_type, str) and not _value_matches_type(default, param_type):
            errors.append(
                f"papermill.parameters[{param_id!r}] default {default!r} does not match "
                f"type {param_type!r}"
            )
        elif options and default not in options:
            warnings.append(
                f"papermill.parameters[{param_id!r}] default {default!r} is not one of "
                f"the options {options}"
            )


def _validate_interface(
    interface: str,
    version: Any,
    parameters: list[dict[str, Any]],
    papermill_parameters: dict[str, Any],
    outputs: list[dict[str, Any]],
    errors: list[str],
) -> None:
    declared = {parameter["id"]: parameter.get("type") for parameter in parameters}
    for input_id, _display_name, input_type in INTERFACE_INPUTS[interface]:
        if input_type is None:
            if input_id not in papermill_parameters:
                errors.append(f"{interface} requires papermill parameter {input_id!r}")
            continue
        if input_id not in declared:
            errors.append(f"{interface} requires parameter {input_id!r} ({input_type})")
        elif declared[input_id] != input_type:
            errors.append(
                f"{interface} requires parameter {input_id!r} to have type {input_type!r}"
            )

    expected_version = INTERFACE_VERSIONS.get(interface)
    if expected_version is not None and version != expected_version:
        errors.append(f"{interface} requires systemlink.version {expected_version}")

    if interface == "Systems Grid" and not any(
        output.get("type") == "data_frame" for output in outputs
    ):
        errors.append("Systems Grid requires a data_frame output")


def validate_notebook(notebook: Any, interface: str | None = None) -> tuple[list[str], list[str]]:
    """Validate the SystemLink and papermill metadata of a notebook.

    Args:
        notebook: Parsed ``.ipynb`` JSON document.
        interface: Optional SystemLink notebook interface the notebook will be
            published with. Enables interface-specific input checks.

    Returns:
        A tuple of ``(errors, warnings)``. The notebook is valid when the error
        list is empty.
    """
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(notebook, dict) or not isinstance(notebook.get("cells"), list):
        return ["notebook must be an object with a cells list"], warnings

    cells = notebook["cells"]
    parameters_cells = _find_parameters_cells(cells)
    if not parameters_cells:
        return ['no cell is tagged "parameters"'], warnings
    if len(parameters_cells) > 1:
        errors.append('more than one cell is tagged "parameters"')
    parameters_cell = parameters_cells[0]
    if parameters_cell.get("cell_type") != "code":
        errors.append('the "parameters" cell must be a code cell')

    metadata = parameters_cell.get("metadata", {})
    papermill = metadata.get("papermill")
    papermill_parameters = papermill.get("parameters") if isinstance(papermill, dict) else None
    if not isinstance(papermill_parameters, dict):
        errors.append("parameters cell metadata.papermill.parameters must be an object")
        papermill_parameters = {}

    systemlink = metadata.get("systemlink")
    if not isinstance(systemlink, dict):
        errors.append("parameters cell metadata.systemlink must be an object")
        return errors, warnings

    version = systemlink.get("version")
    if version not in SUPPORTED_VERSIONS:
        errors.append(f"systemlink.version must be one of {sorted(SUPPORTED_VERSIONS)}")

    namespaces = systemlink.get("namespaces", [])
    if not isinstance(namespaces, list) or not all(isinstance(ns, str) for ns in namespaces):
        errors.append("systemlink.namespaces must be a list of strings")

    parameters = _validate_named_entries(
        systemlink.get("parameters", []), "systemlink.parameters", PARAMETER_TYPES, errors
    )
    outputs = _validate_named_entries(
        systemlink.get("outputs", []), "systemlink.outputs", OUTPUT_TYPES, errors
    )
    _validate_parameters(parameters, papermill_parameters, errors, warnings)

    declared_ids = {parameter["id"] for parameter in parameters}
    hidden_inputs = {
        input_id
        for input_id, _display_name, input_type in INTERFACE_INPUTS.get(interface or "", [])
        if input_type is None
    }
    for key in sorted(set(papermill_parameters) - declared_ids - hidden_inputs):
        warnings.append(
            f"papermill.parameters[{key!r}] is not declared in systemlink.parameters and "
            "is not shown in the SystemLink UI"
        )

    assigned = set(_ASSIGNMENT_PATTERN.findall(_cell_source(parameters_cell)))
    for key in sorted(set(papermill_parameters) | declared_ids):
        if key not in assigned:
            errors.append(f"parameters cell does not assign a default to {key!r}")
    for name in sorted(assigned - set(papermill_parameters) - declared_ids):
        warnings.append(f"parameters cell variable {name!r} is not a papermill parameter")

    code = "\n".join(
        _cell_source(cell)
        for cell in cells
        if isinstance(cell, dict)
        and cell.get("cell_type") == "code"
        and cell is not parameters_cell
    )
    if outputs:
        if version == 2:
            if not _RESULT_GLUE_PATTERN.search(code):
                errors.append('outputs are declared but no cell calls sb.glue("result", ...)')
            for output in outputs:
                if output["id"] not in code:
                    warnings.append(f"output id {output['id']!r} is not referenced in code")
                if output.get("type") not in REPORT_OUTPUT_TYPES | {"vector"}:
                    warnings.append(
                        f"output {output['id']!r} type {output.get('type')!r} is not "
                        "rendered by dashboards or Grafana"
                    )
        elif "sb.glue(" not in code:
            warnings.append("outputs are declared but no cell calls sb.glue(...)")

    if interface is not None:
        if interface not in INTERFACE_INPUTS:
            errors.append(f"interface must be one of {sorted(INTERFACE_INPUTS)}")
        else:
            _validate_interface(
                interface, version, parameters, papermill_parameters, outputs, errors
            )

    return errors, warnings


def _markdown_cell(text: str) -> dict[str, Any]:
    return {
        "cell_type": "markdown",
        "id": uuid.uuid4().hex[:8],
        "metadata": {},
        "source": text.splitlines(keepends=True),
    }


def _code_cell(text: str, metadata: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "cell_type": "code",
        "execution_count": None,
        "id": uuid.uuid4().hex[:8],
        "metadata": metadata or {},
        "outputs": [],
        "source": text.splitlines(keepends=True),
    }


def _merge_interface_inputs(spec: dict[str, Any], interface: str | None) -> dict[str, Any]:
    if interface is None:
        return spec
    merged = dict(spec)
    parameters = list(spec.get("parameters", []))
    existing = {parameter.get("id") for parameter in parameters if isinstance(parameter, dict)}
    hidden_inputs = dict(spec.get("hidden_parameters", {}))
    for input_id, display_name, input_type in INTERFACE_INPUTS[interface]:
        if input_id in existing:
            continue
        if input_type is None:
            hidden_inputs.setdefault(input_id, _default_for_type(None))
        else:
            parameters.append({"id": input_id, "display_name": display_name, "type": input_type})
    merged["parameters"] = parameters
    merged["hidden_parameters"] = hidden_inputs
    if interface in INTERFACE_VERSIONS:
        merged["version"] = INTERFACE_VERSIONS[interface]
    if interface in INTERFACE_OUTPUTS and not spec.get("outputs"):
        merged["outputs"] = [dict(INTERFACE_OUTPUTS[interface])]
    return merged


def _report_output_entry(output: dict[str, Any], frame_name: str | None) -> str:
    header = (
        f'        "id": {json.dumps(output["id"])},\n'
        f'        "display_name": {json.dumps(output["display_name"])},\n'
        f'        "type": {json.dumps(output["type"])},\n'
    )
    if output["type"] == "data_frame":
        body = (
            '        "data": {\n'
            f'            "columns": pd.io.json.build_table_schema({frame_name}, index=False)'
            '["fields"],\n'
            f'            "values": {frame_name}.values.tolist(),\n'
            "        },\n"
        )
    elif output["type"] in {"array", "vector"}:
        body = '        "data": [],  # TODO: list of strings or numbers\n'
    else:
        body = '        "value": None,  # TODO: computed value\n'
    return "    {\n" + header + body + "    },\n"


def _output_code(outputs: list[dict[str, Any]], version: int) -> str:
    lines: list[str] = []
    if version == 1:
        lines.append(
            "# Action notebooks report labeled values that SystemLink shows with the execution."
        )
        for output in outputs:
            placeholder = {"string": '""', "string[]": "[]"}.get(output["type"], "0")
            lines.append(
                f"sb.glue({json.dumps(output['display_name'])}, {placeholder})  # TODO: value"
            )
        return "\n".join(lines) + "\n"

    frame_names: dict[str, str] = {}
    for index, output in enumerate(outputs, start=1):
        if output["type"] == "data_frame":
            frame_name = f"output_frame_{index}"
            frame_names[output["id"]] = frame_name
            lines.append(f"{frame_name} = pd.DataFrame()  # TODO: replace with computed data")
    entries = "".join(
        _report_output_entry(output, frame_names.get(output["id"])) for output in outputs
    )
    lines.append("")
    lines.append("result = [\n" + entries + "]")
    lines.append('sb.glue("result", result)')
    return "\n".join(lines) + "\n"


def build_notebook(spec: dict[str, Any], interface: str | None = None) -> dict[str, Any]:
    """Build a SystemLink notebook document from a parameter and output spec.

    Args:
        spec: Notebook spec with optional ``title``, ``version``, ``namespaces``,
            ``parameters``, and ``outputs`` keys. Parameters accept ``id``,
            ``display_name``, ``type``, and optional ``default``, ``options``,
            and ``default_display`` keys.
        interface: Optional interface whose required inputs are added.

    Returns:
        The notebook document as a JSON-serializable dictionary.
    """
    spec = _merge_interface_inputs(spec, interface)
    version = spec.get("version", 2)
    title = spec.get("title", "SystemLink Notebook")

    systemlink_parameters: list[dict[str, Any]] = []
    papermill_parameters: dict[str, Any] = {}
    for parameter in spec.get("parameters", []):
        param_type = parameter.get("type", "string")
        entry: dict[str, Any] = {
            "display_name": parameter.get("display_name", parameter.get("id", "")),
            "id": parameter.get("id", ""),
            "type": param_type,
        }
        if "options" in parameter:
            entry["options"] = parameter["options"]
        if param_type == "test_monitor_result_query":
            entry["default_display"] = parameter.get(
                "default_display", DEFAULT_RESULT_QUERY_DISPLAY
            )
        elif "default_display" in parameter:
            entry["default_display"] = parameter["default_display"]
        systemlink_parameters.append(entry)

        if "default" in parameter:
            default = parameter["default"]
        elif parameter.get("options"):
            default = parameter["options"][0]
        else:
            default = _default_for_type(param_type)
        papermill_parameters[entry["id"]] = default
    papermill_parameters.update(spec.get("hidden_parameters", {}))

    outputs = [
        {
            "display_name": output.get("display_name", output.get("id", "")),
            "id": output.get("id", ""),
            "type": output.get("type", "scalar"),
        }
        for output in spec.get("outputs", [])
    ]

    parameter_metadata = {
        "papermill": {"parameters": papermill_parameters},
        "systemlink": {
            "namespaces": list(spec.get("namespaces", [])),
            "outputs": outputs,
            "parameters": systemlink_parameters,
            "version": version,
        },
        "tags": ["parameters"],
    }
    parameter_code = "".join(f"{key} = {value!r}\n" for key, value in papermill_parameters.items())
    parameter_docs = "".join(
        f"- `{parameter['id']}` ({parameter['type']}): {parameter['display_name']}\n"
        for parameter in systemlink_parameters
    )

    cells = [
        _markdown_cell(f"# {title}\n"),
        _code_cell("import pandas as pd\nimport scrapbook as sb\n"),
        _markdown_cell(
            "### Parameters\n\n"
            "SystemLink injects these values with papermill. Edit the cell metadata, not only "
            "the defaults, when adding or renaming a parameter.\n\n" + parameter_docs
        ),
        _code_cell(parameter_code or "# No parameters\n", parameter_metadata),
        _markdown_cell("### Analysis\n"),
        _code_cell("# TODO: query SystemLink and compute the outputs.\n"),
    ]
    if outputs:
        cells.append(_markdown_cell("### Outputs\n"))
        cells.append(_code_cell(_output_code(outputs, version)))

    return {
        "cells": cells,
        "metadata": {
            "kernelspec": {
                "display_name": "Python 3 (ipykernel)",
                "language": "python",
                "name": "python3",
            },
            "language_info": {"name": "python"},
        },
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def _print_findings(path: Path, errors: list[str], warnings: list[str]) -> None:
    for warning in warnings:
        print(f"warning: {warning}", file=sys.stderr)
    if errors:
        print(f"Validation failed for {path}:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)


def _handle_init(args: argparse.Namespace) -> int:
    spec: dict[str, Any] = {}
    if args.spec:
        spec_path = Path(args.spec)
        try:
            loaded = json.loads(spec_path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            print(f"File not found: {spec_path}", file=sys.stderr)
            return 1
        except json.JSONDecodeError as exc:
            print(f"Invalid JSON in {spec_path}: {exc}", file=sys.stderr)
            return 1
        if not isinstance(loaded, dict):
            print(f"Spec root must be an object: {spec_path}", file=sys.stderr)
            return 1
        spec = loaded
    if args.title:
        spec["title"] = args.title

    output_path = Path(args.output)
    if output_path.exists() and not args.force:
        print(f"{output_path} already exists. Use --force to overwrite.", file=sys.stderr)
        return 1

    notebook = build_notebook(spec, args.interface)
    errors, warnings = validate_notebook(notebook, args.interface)
    _print_findings(output_path, errors, warnings)
    if errors:
        return 1

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(notebook, indent=1) + "\n", encoding="utf-8")
    print(f"Wrote notebook to {output_path}")
    return 0


def _handle_validate(args: argparse.Namespace) -> int:
    notebook_path = Path(args.notebook)
    try:
        notebook = json.loads(notebook_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        print(f"File not found: {notebook_path}", file=sys.stderr)
        return 1
    except json.JSONDecodeError as exc:
        print(f"Invalid JSON in {notebook_path}: {exc}", file=sys.stderr)
        return 1

    errors, warnings = validate_notebook(notebook, args.interface)
    _print_findings(notebook_path, errors, warnings)
    if errors:
        return 1
    print(f"Notebook valid: {notebook_path}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    """Build the command-line parser for the helper script.

    Returns:
        Configured argument parser with `init` and `validate` subcommands.
    """
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    interfaces = sorted(INTERFACE_INPUTS)

    init_parser = subparsers.add_parser("init", help="Write a notebook with a parameters cell")
    init_parser.add_argument("--output", required=True, help="Path to the .ipynb file to create")
    init_parser.add_argument("--spec", help="JSON file describing parameters and outputs")
    init_parser.add_argument("--title", help="Notebook title")
    init_parser.add_argument(
        "--interface", choices=interfaces, help="Add the inputs this interface requires"
    )
    init_parser.add_argument("--force", action="store_true", help="Overwrite an existing file")
    init_parser.set_defaults(handler=_handle_init)

    validate_parser = subparsers.add_parser("validate", help="Validate notebook metadata")
    validate_parser.add_argument("notebook", help="Path to the .ipynb file to validate")
    validate_parser.add_argument(
        "--interface", choices=interfaces, help="Also check this interface's required inputs"
    )
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
