"""Unit tests for the SystemLink notebook helper."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from slcli.notebook_click import PREDEFINED_NOTEBOOK_INTERFACES
from slcli.skills.slcli.scripts.notebook_helper import (
    INTERFACE_INPUTS,
    build_notebook,
    main,
    validate_notebook,
)


def make_notebook(
    papermill: dict[str, Any],
    systemlink: dict[str, Any],
    parameter_source: str,
    output_source: str = 'result = [{"id": "my_output"}]\nsb.glue("result", result)\n',
) -> dict[str, Any]:
    """Build a minimal notebook with a parameters cell and an output cell."""
    return {
        "cells": [
            {
                "cell_type": "code",
                "metadata": {
                    "papermill": {"parameters": papermill},
                    "systemlink": systemlink,
                    "tags": ["parameters"],
                },
                "source": parameter_source,
            },
            {"cell_type": "code", "metadata": {}, "source": output_source},
        ],
        "nbformat": 4,
        "nbformat_minor": 5,
    }


def make_demo_notebook(**papermill_overrides: Any) -> dict[str, Any]:
    """Build a notebook matching the published papermill demo structure."""
    papermill = {"my_input": "", "my_enum": "Day", "my_query": 'startedWithin <= "30.0:0:0"'}
    papermill.update(papermill_overrides)
    systemlink = {
        "namespaces": ["ni-testmanagement"],
        "outputs": [{"display_name": "My Output", "id": "my_output", "type": "data_frame"}],
        "parameters": [
            {"display_name": "My Input", "id": "my_input", "type": "string"},
            {
                "display_name": "My Enum",
                "id": "my_enum",
                "options": ["Day", "System"],
                "type": "string",
            },
            {
                "default_display": {"products_filter": [], "results_filter": []},
                "display_name": "My Query",
                "id": "my_query",
                "type": "test_monitor_result_query",
            },
        ],
        "version": 2,
    }
    source = 'my_input = ""\nmy_enum = "Day"\nmy_query = \'startedWithin <= "30.0:0:0"\'\n'
    return make_notebook(papermill, systemlink, source)


def test_validate_accepts_demo_structure_and_warns_on_default_outside_options() -> None:
    """A demo-shaped notebook is valid; an enum default outside its options warns."""
    assert validate_notebook(make_demo_notebook()) == ([], [])

    errors, warnings = validate_notebook(make_demo_notebook(my_enum="test2"))

    assert errors == []
    assert any("'test2' is not one of the options" in warning for warning in warnings)


def test_validate_reports_misaligned_metadata() -> None:
    """Mismatched papermill, systemlink, and code-cell declarations are errors."""
    notebook = make_notebook(
        papermill={"count": "5"},
        systemlink={
            "outputs": [{"display_name": "Total", "id": "total", "type": "scalar"}],
            "parameters": [
                {"display_name": "Count", "id": "count", "type": "integer"},
                {"display_name": "Missing", "id": "missing", "type": "string"},
                {"display_name": "Bad", "id": "bad", "type": "datetime"},
            ],
            "version": 2,
        },
        parameter_source="count = 5\n",
        output_source='sb.glue("total", 1)\n',
    )

    errors, _ = validate_notebook(notebook)

    assert "papermill.parameters['count'] default '5' does not match type 'integer'" in errors
    assert "papermill.parameters is missing 'missing'" in errors
    assert "parameters cell does not assign a default to 'missing'" in errors
    assert any(error.startswith("systemlink.parameters[2].type must be one of") for error in errors)
    assert 'outputs are declared but no cell calls sb.glue("result", ...)' in errors


def test_validate_boolean_dropdown_options() -> None:
    """Boolean parameters accept [true, false] options and reject other values."""

    def boolean_notebook(options: Any) -> dict[str, Any]:
        return make_notebook(
            papermill={"enabled": True},
            systemlink={
                "parameters": [
                    {
                        "display_name": "Enabled",
                        "id": "enabled",
                        "options": options,
                        "type": "boolean",
                    }
                ],
                "version": 2,
            },
            parameter_source="enabled = True\n",
        )

    assert validate_notebook(boolean_notebook([True, False])) == ([], [])
    errors, _ = validate_notebook(boolean_notebook(["true", "false"]))
    assert "systemlink.parameters['enabled'].options must be [true, false] for boolean" in errors


def test_validate_requires_parameters_tag() -> None:
    """Papermill cannot inject values without a cell tagged parameters."""
    notebook = make_demo_notebook()
    notebook["cells"][0]["metadata"]["tags"] = []

    assert validate_notebook(notebook) == (['no cell is tagged "parameters"'], [])


def test_build_notebook_supports_scalar_parameter_types() -> None:
    """String, integer, float, and boolean parameters round-trip through validation."""
    spec = {
        "parameters": [
            {"id": "label", "display_name": "Label", "type": "string", "default": 'a "b"'},
            {"id": "count", "display_name": "Count", "type": "integer", "default": 3},
            {"id": "limit", "display_name": "Limit", "type": "float", "default": 1.5},
            {"id": "enabled", "display_name": "Enabled", "type": "boolean", "default": True},
            {"id": "query", "display_name": "Query", "type": "test_monitor_result_query"},
        ],
        "outputs": [{"id": "summary", "display_name": "Summary", "type": "data_frame"}],
    }

    notebook = build_notebook(spec)
    parameters_cell = notebook["cells"][3]
    source = "".join(parameters_cell["source"])
    namespace: dict[str, Any] = {}
    exec(source, namespace)  # noqa: S102 - generated literals only

    assert validate_notebook(notebook) == ([], [])
    assert namespace["label"] == 'a "b"'
    assert namespace["count"] == 3
    assert namespace["limit"] == 1.5
    assert namespace["enabled"] is True
    query_parameter = parameters_cell["metadata"]["systemlink"]["parameters"][4]
    assert query_parameter["default_display"]["results_filter"][0]["queryOperandValue"] == 30


@pytest.mark.parametrize(
    ("interface", "expected_version", "expected_parameter"),
    [
        ("Work Item Automations", 1, ("work_item_ids", "string[]", [])),
        ("Specification Analysis", 2, ("spec_ids", "string[]", [])),
    ],
)
def test_build_notebook_adds_interface_inputs(
    interface: str, expected_version: int, expected_parameter: tuple[str, str, Any]
) -> None:
    """Interface presets add required inputs with matching papermill defaults."""
    notebook = build_notebook({}, interface)
    metadata = notebook["cells"][3]["metadata"]
    parameter_id, parameter_type, default = expected_parameter

    assert validate_notebook(notebook, interface) == ([], [])
    assert metadata["systemlink"]["version"] == expected_version
    parameter = metadata["systemlink"]["parameters"][0]
    assert (parameter["id"], parameter["type"]) == (parameter_id, parameter_type)
    assert metadata["papermill"]["parameters"][parameter_id] == default


def test_validate_interface_requirements() -> None:
    """Interface checks catch missing inputs, wrong types, versions, and outputs."""
    notebook = make_notebook(
        papermill={"work_item_ids": ""},
        systemlink={
            "parameters": [{"display_name": "Work items", "id": "work_item_ids", "type": "string"}],
            "version": 2,
        },
        parameter_source='work_item_ids = ""\n',
    )

    errors, _ = validate_notebook(notebook, "Work Item Automations")
    grid_errors, _ = validate_notebook(notebook, "Systems Grid")

    assert (
        "Work Item Automations requires parameter 'work_item_ids' to have type 'string[]'" in errors
    )
    assert "Work Item Automations requires systemlink.version 1" in errors
    assert "Systems Grid requires a data_frame output" in grid_errors
    assert validate_notebook(build_notebook({}, "Systems Grid"), "Systems Grid")[0] == []


def test_interfaces_match_cli_choices() -> None:
    """Helper interface names stay in sync with notebook manage --interface choices."""
    assert set(INTERFACE_INPUTS) == set(PREDEFINED_NOTEBOOK_INTERFACES)


def test_build_action_notebook_glues_encodable_placeholders() -> None:
    """Version 1 scaffolds glue labeled values that scrapbook can encode."""
    spec = {
        "outputs": [
            {"id": "total", "display_name": "Total", "type": "scalar"},
            {"id": "updated", "display_name": "Updated", "type": "string[]"},
        ]
    }

    notebook = build_notebook(spec, "Work Item Automations")
    output_source = "".join(notebook["cells"][-1]["source"])

    assert 'sb.glue("Total", 0)' in output_source
    assert 'sb.glue("Updated", [])' in output_source
    assert "None" not in output_source


def test_main_init_then_validate(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The init command writes a notebook that the validate command accepts."""
    spec_path = tmp_path / "spec.json"
    spec_path.write_text(
        json.dumps({"parameters": [{"id": "count", "display_name": "Count", "type": "integer"}]}),
        encoding="utf-8",
    )
    notebook_path = tmp_path / "nested" / "report.ipynb"

    monkeypatch.setattr(
        sys,
        "argv",
        ["notebook_helper.py", "init", "--spec", str(spec_path), "--output", str(notebook_path)],
    )
    assert main() == 0
    monkeypatch.setattr(sys, "argv", ["notebook_helper.py", "validate", str(notebook_path)])
    assert main() == 0

    notebook_path.write_text("{}", encoding="utf-8")
    assert main() == 1
