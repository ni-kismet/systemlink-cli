"""CLI commands for managing SystemLink DataFrame tables."""

import json
import sys
from collections import defaultdict
from typing import Any, Dict, Iterable, List, NoReturn, Optional, Tuple

import click
import requests as requests_lib
from click.core import ParameterSource

from .cli_utils import confirm_bulk_operation, validate_output_format
from .platform import require_feature
from .rich_output import render_table
from .utils import (
    ExitCodes,
    check_readonly_mode,
    format_success,
    get_base_url,
    get_headers,
    get_ssl_verify,
    get_workspace_map,
    handle_api_error,
    load_json_file,
    make_api_request,
)
from .workspace_utils import (
    get_effective_workspace,
    get_workspace_display_name,
    resolve_workspace_filter,
)

TABLE_ORDER_BY_CHOICES = [
    "CREATED_AT",
    "METADATA_MODIFIED_AT",
    "NAME",
    "NUMBER_OF_ROWS",
    "ROWS_MODIFIED_AT",
]

FILTER_OPERATION_CHOICES = [
    "EQUALS",
    "LESS_THAN",
    "LESS_THAN_EQUALS",
    "GREATER_THAN",
    "GREATER_THAN_EQUALS",
    "NOT_EQUALS",
    "CONTAINS",
    "NOT_CONTAINS",
]

DECIMATION_METHOD_CHOICES = ["LOSSY", "MAX_MIN", "ENTRY_EXIT"]
DECIMATION_DISTRIBUTION_CHOICES = ["EQUAL_FREQUENCY", "EQUAL_WIDTH"]


def _get_dataframe_base_url() -> str:
    """Return the DataFrame service base URL."""
    return f"{get_base_url()}/nidataframe/v1"


def _exit_invalid_input(message: str) -> NoReturn:
    """Exit with a consistent invalid input message."""
    click.echo(f"✗ {message}", err=True)
    sys.exit(ExitCodes.INVALID_INPUT)


def _validate_take(value: int, maximum: int, label: str = "take") -> int:
    """Validate take-style limits against the service maximum."""
    if value < 1 or value > maximum:
        _exit_invalid_input(f"{label} must be between 1 and {maximum}")
    return value


def _parse_substitutions(values: Iterable[str]) -> List[Any]:
    """Parse query-table substitutions from CLI strings."""
    parsed: List[Any] = []
    for value in values:
        try:
            parsed.append(json.loads(value))
        except (json.JSONDecodeError, TypeError):
            parsed.append(value)
    return parsed


def _offset_substitutions(filter_expr: str, offset: int) -> str:
    """Offset substitution indices in a Dynamic LINQ filter."""
    if offset <= 0:
        return filter_expr

    def _replace(match: Any) -> str:
        return f"@{int(match.group(1)) + offset}"

    import re

    return re.sub(r"@(\d+)", _replace, filter_expr)


def _combine_filter_parts(
    base_filter: Optional[str],
    base_substitutions: List[Any],
    extra_filter: Optional[str],
    extra_substitutions: List[Any],
) -> Tuple[Optional[str], List[Any]]:
    """Combine structured and raw table filters."""
    if not extra_filter:
        return base_filter, base_substitutions

    if base_filter:
        offset_filter = _offset_substitutions(extra_filter, len(base_substitutions))
        return (
            f"({base_filter}) && ({offset_filter})",
            base_substitutions + extra_substitutions,
        )

    return extra_filter, extra_substitutions


def _append_filter(
    filter_parts: List[str],
    substitutions: List[Any],
    expression: str,
    value: Optional[Any],
) -> None:
    """Append a filter expression if the value is present."""
    if value is None or value == "":
        return
    index = len(substitutions)
    filter_parts.append(expression.format(index=index))
    substitutions.append(value)


def _resolve_workspace_id(workspace: Optional[str], apply_default: bool = True) -> Optional[str]:
    """Resolve a workspace name or ID to a workspace ID."""
    effective = get_effective_workspace(workspace) if apply_default else workspace
    if not effective:
        return None

    workspace_map = get_workspace_map()
    return resolve_workspace_filter(effective, workspace_map)


def _parse_columns(columns_text: Optional[str]) -> Optional[List[str]]:
    """Parse a comma-separated column list."""
    if not columns_text:
        return None

    columns = [column.strip() for column in columns_text.split(",") if column.strip()]
    return columns or None


def _parse_filter_value(value: str) -> Optional[str]:
    """Parse a row filter value while preserving the API's string semantics."""
    normalized = value.strip()
    if normalized.lower() == "null":
        return None
    return normalized


def _parse_where_clause(where_clause: str) -> Dict[str, Any]:
    """Parse a `column,operation,value` row filter clause."""
    parts = [part.strip() for part in where_clause.split(",", maxsplit=2)]
    if len(parts) != 3 or not parts[0] or not parts[1]:
        _exit_invalid_input(
            "--where must use the format column,operation,value "
            "for example Voltage,LESS_THAN,4.8"
        )

    column, operation, value = parts
    if operation not in FILTER_OPERATION_CHOICES:
        _exit_invalid_input(
            f"Unsupported filter operation '{operation}'. "
            f"Valid options: {', '.join(FILTER_OPERATION_CHOICES)}"
        )

    return {"column": column, "operation": operation, "value": _parse_filter_value(value)}


def _parse_order_by_clause(order_by_clause: str) -> Dict[str, Any]:
    """Parse a `column[:asc|desc]` order-by clause."""
    column = order_by_clause.strip()
    descending = False

    if ":" in order_by_clause:
        column, direction = [part.strip() for part in order_by_clause.rsplit(":", maxsplit=1)]
        lowered = direction.lower()
        if lowered not in {"asc", "desc"}:
            _exit_invalid_input("--order-by must use :asc or :desc when a direction is provided")
        descending = lowered == "desc"

    if not column:
        _exit_invalid_input("--order-by requires a column name")

    return {"column": column, "descending": descending}


def _format_properties(properties: Any, maximum_length: int = 60) -> str:
    """Format property dictionaries for compact table output."""
    if not properties:
        return ""

    rendered = json.dumps(properties, sort_keys=True)
    if len(rendered) <= maximum_length:
        return rendered
    return rendered[: maximum_length - 3] + "..."


def _format_bool(value: Any) -> str:
    """Format a boolean-like value for table output."""
    return "✓" if bool(value) else ""


def _calculate_column_widths(
    headers: List[str], rows: List[List[str]], maximum: int = 36
) -> List[int]:
    """Calculate display widths for Rich table rendering."""
    widths: List[int] = []
    for index, header in enumerate(headers):
        width = len(header)
        for row in rows:
            width = max(width, len(row[index]))
        widths.append(min(max(width, 8), maximum))
    return widths


def _render_grid(
    headers: List[str], rows: List[List[str]], total_label: Optional[str] = None
) -> None:
    """Render a grid table using shared rich output."""
    render_table(
        headers,
        _calculate_column_widths(headers, rows),
        rows,
        show_total=bool(total_label),
        total_label=total_label or "item(s)",
    )


def _render_key_value_table(title: str, data: Dict[str, Any]) -> None:
    """Render a vertical key-value table."""
    click.echo(title)
    rows = [[key, "" if value is None else str(value)] for key, value in data.items()]
    _render_grid(["Field", "Value"], rows)


def _render_table_summary(table_data: Dict[str, Any], workspace_map: Dict[str, str]) -> None:
    """Render table metadata in a compact human-readable form."""
    summary = {
        "ID": table_data.get("id", ""),
        "Name": table_data.get("name", ""),
        "Workspace": get_workspace_display_name(table_data.get("workspace", ""), workspace_map),
        "Rows": table_data.get("rowCount", ""),
        "Columns": len(table_data.get("columns", []) or []),
        "Supports Append": table_data.get("supportsAppend", False),
        "Test Result": table_data.get("testResultId", ""),
        "Created": table_data.get("createdAt", ""),
        "Rows Modified": table_data.get("rowsModifiedAt", ""),
        "Metadata Modified": table_data.get("metadataModifiedAt", ""),
        "Properties": _format_properties(table_data.get("properties", {})),
    }
    _render_key_value_table("DataFrame Table", summary)


def _render_schema_table(columns: List[Dict[str, Any]], include_properties: bool) -> None:
    """Render table schema rows."""
    headers = ["Name", "Data Type", "Column Type"]
    if include_properties:
        headers.append("Properties")

    rows: List[List[str]] = []
    for column in columns:
        row = [
            str(column.get("name", "")),
            str(column.get("dataType", "")),
            str(column.get("columnType", "")),
        ]
        if include_properties:
            row.append(_format_properties(column.get("properties", {}), maximum_length=80))
        rows.append(row)

    if not rows:
        click.echo("No columns found.")
        return

    _render_grid(headers, rows, total_label="column(s)")


def _render_frame_table(frame: Dict[str, Any], empty_message: str = "No rows found.") -> None:
    """Render a split-oriented dataframe payload as a Rich table."""
    columns = frame.get("columns") or []
    data_rows = frame.get("data") or []

    if not columns or not data_rows:
        click.echo(empty_message)
        return

    rows: List[List[str]] = []
    for row in data_rows:
        rows.append(["" if value is None else str(value) for value in row])

    _render_grid([str(column) for column in columns], rows, total_label="row(s)")


def _load_request_payload(path: Optional[str]) -> Dict[str, Any]:
    """Load a JSON request payload from disk when provided."""
    if not path:
        return {}

    payload = load_json_file(path)
    if not isinstance(payload, dict):
        _exit_invalid_input("Request files must contain a JSON object")
    return payload


def _build_table_list_payload(
    name: Optional[str],
    workspace: Optional[str],
    test_result_id: Optional[str],
    supports_append: Optional[bool],
    custom_filter: Optional[str],
    substitutions: Tuple[str, ...],
    order_by: Optional[str],
    descending: bool,
    take: int,
) -> Dict[str, Any]:
    """Build the query-tables payload from list command options."""
    filter_parts: List[str] = []
    base_substitutions: List[Any] = []

    _append_filter(filter_parts, base_substitutions, "name.Contains(@{index})", name)
    _append_filter(filter_parts, base_substitutions, "testResultId == @{index}", test_result_id)
    if supports_append is not None:
        _append_filter(
            filter_parts, base_substitutions, "supportsAppend == @{index}", supports_append
        )

    workspace_id = _resolve_workspace_id(workspace)
    _append_filter(filter_parts, base_substitutions, "workspace == @{index}", workspace_id)

    combined_filter, combined_substitutions = _combine_filter_parts(
        " && ".join(filter_parts) if filter_parts else None,
        base_substitutions,
        custom_filter,
        _parse_substitutions(substitutions),
    )

    payload: Dict[str, Any] = {"take": _validate_take(take, 1000)}
    if combined_filter:
        payload["filter"] = combined_filter
    if combined_substitutions:
        payload["substitutions"] = combined_substitutions
    if order_by:
        payload["orderBy"] = order_by
        payload["orderByDescending"] = descending
    return payload


def _fetch_table_page(payload: Dict[str, Any]) -> Dict[str, Any]:
    """Execute a query-tables request."""
    return make_api_request(
        "POST", f"{_get_dataframe_base_url()}/query-tables", payload=payload
    ).json()


def _confirm_next_page() -> bool:
    """Ask the user if more paged data should be fetched."""
    try:
        is_tty = sys.stdout.isatty() and sys.stdin.isatty()
    except Exception:
        is_tty = False

    if not is_tty:
        return False
    return click.confirm("Show next page?", default=True)


def _display_table_pages(initial_payload: Dict[str, Any], workspace_map: Dict[str, str]) -> None:
    """Interactively page through query-tables results for table output."""
    payload = dict(initial_payload)
    shown = 0

    while True:
        data = _fetch_table_page(payload)
        tables = data.get("tables", []) or []
        continuation_token = data.get("continuationToken")

        if not tables and shown == 0:
            click.echo("No dataframe tables found.")
            return

        if not tables:
            return

        rows = [
            [
                str(table.get("name", "")),
                str(table.get("id", "")),
                get_workspace_display_name(table.get("workspace", ""), workspace_map),
                str(table.get("rowCount", "")),
                _format_bool(table.get("supportsAppend", False)),
                str(table.get("rowsModifiedAt", "")),
            ]
            for table in tables
        ]
        _render_grid(["Name", "ID", "Workspace", "Rows", "Append", "Modified"], rows)

        shown += len(tables)
        if not continuation_token:
            return

        click.echo(f"\nShowing {shown} dataframe table(s) so far. More may be available.")
        if not _confirm_next_page():
            return
        payload["continuationToken"] = continuation_token


def _fetch_all_table_pages(initial_payload: Dict[str, Any]) -> Dict[str, Any]:
    """Fetch every table page for JSON output."""
    payload = dict(initial_payload)
    all_tables: List[Dict[str, Any]] = []

    while True:
        data = _fetch_table_page(payload)
        all_tables.extend(data.get("tables", []) or [])
        continuation_token = data.get("continuationToken")
        if not continuation_token:
            return {"tables": all_tables, "continuationToken": None}
        payload["continuationToken"] = continuation_token


def _build_data_query_payload(
    request: Optional[str],
    columns: Optional[str],
    where: Tuple[str, ...],
    order_by: Tuple[str, ...],
    take: Optional[int],
    continuation_token: Optional[str],
) -> Dict[str, Any]:
    """Build a table row query payload."""
    payload = _load_request_payload(request)

    parsed_columns = _parse_columns(columns)
    if parsed_columns is not None:
        payload["columns"] = parsed_columns
    if where:
        payload["filters"] = [_parse_where_clause(clause) for clause in where]
    if order_by:
        payload["orderBy"] = [_parse_order_by_clause(clause) for clause in order_by]
    if take is not None:
        payload["take"] = _validate_take(take, 10000)
    if continuation_token:
        payload["continuationToken"] = continuation_token

    return payload


def _display_query_pages(table_id: str, payload: Dict[str, Any], endpoint: str) -> None:
    """Display paged query responses for table output."""
    query_payload = dict(payload)
    first_page = True

    while True:
        data = make_api_request(
            "POST",
            f"{_get_dataframe_base_url()}/tables/{table_id}/{endpoint}",
            payload=query_payload,
        ).json()
        frame = data.get("frame", {}) or {}

        if not frame.get("data") and first_page:
            click.echo("No rows found.")
            return

        _render_frame_table(frame)

        continuation_token = data.get("continuationToken")
        if not continuation_token:
            return

        click.echo(f"\nMatched {data.get('totalRowCount', '?')} row(s). More rows are available.")
        if not _confirm_next_page():
            click.echo(f"Next continuation token: {continuation_token}")
            return

        query_payload["continuationToken"] = continuation_token
        first_page = False


def _build_decimation_payload(
    request: Optional[str],
    columns: Optional[str],
    where: Tuple[str, ...],
    x_column: Optional[str],
    y_columns: Tuple[str, ...],
    intervals: Optional[int],
    method: Optional[str],
    distribution: Optional[str],
) -> Dict[str, Any]:
    """Build a decimated data query payload."""
    payload = _load_request_payload(request)
    parsed_columns = _parse_columns(columns)
    if parsed_columns is not None:
        payload["columns"] = parsed_columns
    if where:
        payload["filters"] = [_parse_where_clause(clause) for clause in where]

    decimation = payload.get("decimation", {})
    if decimation and not isinstance(decimation, dict):
        _exit_invalid_input("The decimation request payload must be a JSON object")
    if not isinstance(decimation, dict):
        decimation = {}

    if intervals is not None:
        decimation["intervals"] = _validate_take(intervals, 2147483647, label="intervals")
    if x_column:
        decimation["xColumn"] = x_column
    if y_columns:
        decimation["yColumns"] = [column for column in y_columns]
    if method:
        decimation["method"] = method
    if distribution:
        decimation["distribution"] = distribution

    payload["decimation"] = decimation
    return payload


def _parse_property_assignment(value: str) -> Tuple[str, str]:
    """Parse a KEY=VALUE property assignment."""
    if "=" not in value:
        _exit_invalid_input(f"Expected KEY=VALUE but received '{value}'")
    key, property_value = value.split("=", maxsplit=1)
    if not key.strip():
        _exit_invalid_input(f"Expected KEY=VALUE but received '{value}'")
    return key.strip(), property_value


def _parse_column_property_assignment(value: str) -> Tuple[str, str, str]:
    """Parse a COLUMN:KEY=VALUE column property assignment."""
    if ":" not in value or "=" not in value:
        _exit_invalid_input(f"Expected COLUMN:KEY=VALUE but received '{value}'")
    column_name, remainder = value.split(":", maxsplit=1)
    property_key, property_value = _parse_property_assignment(remainder)
    if not column_name.strip():
        _exit_invalid_input(f"Expected COLUMN:KEY=VALUE but received '{value}'")
    return column_name.strip(), property_key, property_value


def _parse_column_property_removal(value: str) -> Tuple[str, str]:
    """Parse a COLUMN:KEY column property removal."""
    if ":" not in value:
        _exit_invalid_input(f"Expected COLUMN:KEY but received '{value}'")
    column_name, property_key = value.split(":", maxsplit=1)
    if not column_name.strip() or not property_key.strip():
        _exit_invalid_input(f"Expected COLUMN:KEY but received '{value}'")
    return column_name.strip(), property_key.strip()


def _build_update_payload(
    name: Optional[str],
    workspace: Optional[str],
    test_result_id: Optional[str],
    property_assignments: Tuple[str, ...],
    remove_properties: Tuple[str, ...],
    column_property_assignments: Tuple[str, ...],
    remove_column_properties: Tuple[str, ...],
    metadata_revision: Optional[int],
) -> Dict[str, Any]:
    """Build a modify-table payload from CLI options."""
    payload: Dict[str, Any] = {}
    if name is not None:
        payload["name"] = name
    if workspace is not None:
        payload["workspace"] = _resolve_workspace_id(workspace, apply_default=False)
    if test_result_id is not None:
        payload["testResultId"] = test_result_id
    if metadata_revision is not None:
        payload["metadataRevision"] = metadata_revision

    properties: Dict[str, Optional[str]] = {}
    for assignment in property_assignments:
        key, value = _parse_property_assignment(assignment)
        properties[key] = value
    for key in remove_properties:
        properties[key] = None
    if properties:
        payload["properties"] = properties

    column_properties: Dict[str, Dict[str, Optional[str]]] = defaultdict(dict)
    for assignment in column_property_assignments:
        column_name, property_key, value = _parse_column_property_assignment(assignment)
        column_properties[column_name][property_key] = value
    for removal in remove_column_properties:
        column_name, property_key = _parse_column_property_removal(removal)
        column_properties[column_name][property_key] = None
    if column_properties:
        payload["columns"] = [
            {"name": column_name, "properties": properties}
            for column_name, properties in column_properties.items()
        ]

    return payload


def _validate_append_payload(payload: Dict[str, Any]) -> None:
    """Validate JSON append payload structure before sending it to the API."""
    if payload.get("endOfData") is True:
        return

    frame = payload.get("frame")
    if not isinstance(frame, dict):
        _exit_invalid_input("Append payload must contain a JSON object under 'frame'")

    data_rows = frame.get("data")
    if not isinstance(data_rows, list):
        _exit_invalid_input("Append payload frame must contain a 'data' array")

    columns = frame.get("columns")
    if columns is not None and not isinstance(columns, list):
        _exit_invalid_input("Append payload frame 'columns' must be an array when provided")


def _post_arrow_append(table_id: str, input_path: str, end_of_data: bool) -> requests_lib.Response:
    """Append Arrow IPC stream data to a table."""
    url = f"{_get_dataframe_base_url()}/tables/{table_id}/data"
    if end_of_data:
        url += "?endOfData=true"

    try:
        with open(input_path, "rb") as arrow_file:
            response = requests_lib.post(
                url,
                headers=get_headers("application/vnd.apache.arrow.stream"),
                data=arrow_file,
                verify=get_ssl_verify(),
            )
        response.raise_for_status()
        return response
    except requests_lib.RequestException as exc:
        handle_api_error(exc)
        raise


def register_dataframe_commands(cli: Any) -> None:
    """Register the dataframe command group and subcommands."""

    @cli.group()
    @click.pass_context
    def dataframe(ctx: click.Context) -> None:
        """Manage SystemLink DataFrame tables and rows."""
        if ctx.invoked_subcommand is not None:
            require_feature("dataframe_service")

    @dataframe.command(name="list")
    @click.option("--name", help="Filter tables by name using contains matching")
    @click.option(
        "--workspace",
        "workspace_name",
        "-w",
        help="Workspace name or ID. Use 'all' to disable workspace filtering.",
    )
    @click.option("--test-result-id", help="Filter by associated test result ID")
    @click.option(
        "--supports-append/--no-supports-append",
        default=None,
        help="Filter by whether the table supports append",
    )
    @click.option("--filter", "custom_filter", help="Raw query-tables Dynamic LINQ filter")
    @click.option(
        "--substitution",
        multiple=True,
        help="Substitution value for --filter. Repeat for multiple values.",
    )
    @click.option(
        "--order-by",
        type=click.Choice(TABLE_ORDER_BY_CHOICES),
        help="Sort field for tables",
    )
    @click.option("--descending/--ascending", default=False, help="Sort descending")
    @click.option("--take", "-t", type=int, default=25, show_default=True, help="Page size")
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    def list_tables(
        name: Optional[str],
        workspace_name: Optional[str],
        test_result_id: Optional[str],
        supports_append: Optional[bool],
        custom_filter: Optional[str],
        substitution: Tuple[str, ...],
        order_by: Optional[str],
        descending: bool,
        take: int,
        format: str,
    ) -> None:
        """List DataFrame tables."""
        format_output = validate_output_format(format)
        payload = _build_table_list_payload(
            name=name,
            workspace=workspace_name,
            test_result_id=test_result_id,
            supports_append=supports_append,
            custom_filter=custom_filter,
            substitutions=substitution,
            order_by=order_by,
            descending=descending,
            take=take,
        )

        try:
            if format_output == "json":
                click.echo(json.dumps(_fetch_all_table_pages(payload), indent=2))
                return

            _display_table_pages(payload, get_workspace_map())
        except Exception as exc:
            handle_api_error(exc)

    @dataframe.command(name="get")
    @click.argument("table_id")
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    def get_table(table_id: str, format: str) -> None:
        """Get DataFrame table metadata."""
        format_output = validate_output_format(format)

        try:
            data = make_api_request("GET", f"{_get_dataframe_base_url()}/tables/{table_id}").json()
            if format_output == "json":
                click.echo(json.dumps(data, indent=2))
                return

            workspace_map = get_workspace_map()
            _render_table_summary(data, workspace_map)
            if data.get("columns"):
                click.echo("")
                click.echo("Schema")
                _render_schema_table(data.get("columns", []), include_properties=False)
        except Exception as exc:
            handle_api_error(exc)

    @dataframe.command(name="schema")
    @click.argument("table_id")
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    @click.option(
        "--properties/--no-properties",
        default=False,
        help="Include column property maps in table output",
    )
    def show_schema(table_id: str, format: str, properties: bool) -> None:
        """Show table schema and column definitions."""
        format_output = validate_output_format(format)

        try:
            data = make_api_request("GET", f"{_get_dataframe_base_url()}/tables/{table_id}").json()
            columns = data.get("columns", []) or []
            if format_output == "json":
                click.echo(json.dumps(columns, indent=2))
                return
            _render_schema_table(columns, include_properties=properties)
        except Exception as exc:
            handle_api_error(exc)

    @dataframe.command(name="query")
    @click.argument("table_id")
    @click.option("--columns", help="Comma-separated list of columns to return")
    @click.option(
        "--where",
        multiple=True,
        help="Filter clause in the form column,operation,value. Repeat for multiple filters.",
    )
    @click.option(
        "--order-by",
        "order_by_clauses",
        multiple=True,
        help="Sort clause in the form column[:asc|desc]. Repeat for multiple clauses.",
    )
    @click.option("--take", "-t", type=int, default=100, show_default=True, help="Rows per page")
    @click.option("--continuation-token", help="Continuation token for paged reads")
    @click.option(
        "--request",
        type=click.Path(exists=True, dir_okay=False, readable=True),
        help="Path to raw query JSON",
    )
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    def query_table_data(
        table_id: str,
        columns: Optional[str],
        where: Tuple[str, ...],
        order_by_clauses: Tuple[str, ...],
        take: int,
        continuation_token: Optional[str],
        request: Optional[str],
        format: str,
    ) -> None:
        """Query row data from a DataFrame table."""
        format_output = validate_output_format(format)
        ctx = click.get_current_context()
        take_source = ctx.get_parameter_source("take")
        effective_take = None if request and take_source == ParameterSource.DEFAULT else take
        payload = _build_data_query_payload(
            request=request,
            columns=columns,
            where=where,
            order_by=order_by_clauses,
            take=effective_take,
            continuation_token=continuation_token,
        )

        try:
            if format_output == "json":
                data = make_api_request(
                    "POST",
                    f"{_get_dataframe_base_url()}/tables/{table_id}/query-data",
                    payload=payload,
                ).json()
                click.echo(json.dumps(data, indent=2))
                return

            _display_query_pages(table_id, payload, endpoint="query-data")
        except Exception as exc:
            handle_api_error(exc)

    @dataframe.command(name="decimate")
    @click.argument("table_id")
    @click.option("--columns", help="Comma-separated list of columns to return")
    @click.option(
        "--where",
        multiple=True,
        help="Filter clause in the form column,operation,value. Repeat for multiple filters.",
    )
    @click.option("--x-column", help="Column to use as the x-axis for decimation")
    @click.option(
        "--y-column", "y_columns", multiple=True, help="Y column for MAX_MIN or ENTRY_EXIT"
    )
    @click.option(
        "--intervals", type=int, default=1000, show_default=True, help="Number of intervals"
    )
    @click.option(
        "--method",
        type=click.Choice(DECIMATION_METHOD_CHOICES),
        help="Decimation method",
    )
    @click.option(
        "--distribution",
        type=click.Choice(DECIMATION_DISTRIBUTION_CHOICES),
        help="Distribution for interval bucketing",
    )
    @click.option(
        "--request",
        type=click.Path(exists=True, dir_okay=False, readable=True),
        help="Path to raw decimation JSON",
    )
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    def decimate_table_data(
        table_id: str,
        columns: Optional[str],
        where: Tuple[str, ...],
        x_column: Optional[str],
        y_columns: Tuple[str, ...],
        intervals: int,
        method: Optional[str],
        distribution: Optional[str],
        request: Optional[str],
        format: str,
    ) -> None:
        """Query decimated row data for numeric or timeseries tables."""
        format_output = validate_output_format(format)
        ctx = click.get_current_context()
        intervals_source = ctx.get_parameter_source("intervals")
        effective_intervals = (
            None if request and intervals_source == ParameterSource.DEFAULT else intervals
        )
        payload = _build_decimation_payload(
            request=request,
            columns=columns,
            where=where,
            x_column=x_column,
            y_columns=y_columns,
            intervals=effective_intervals,
            method=method,
            distribution=distribution,
        )

        try:
            data = make_api_request(
                "POST",
                f"{_get_dataframe_base_url()}/tables/{table_id}/query-decimated-data",
                payload=payload,
            ).json()
            if format_output == "json":
                click.echo(json.dumps(data, indent=2))
                return
            _render_frame_table(data.get("frame", {}) or {})
        except Exception as exc:
            handle_api_error(exc)

    @dataframe.command(name="export")
    @click.argument("table_id")
    @click.option("--columns", help="Comma-separated list of columns to export")
    @click.option(
        "--where",
        multiple=True,
        help="Filter clause in the form column,operation,value. Repeat for multiple filters.",
    )
    @click.option(
        "--order-by",
        "order_by_clauses",
        multiple=True,
        help="Sort clause in the form column[:asc|desc]. Repeat for multiple clauses.",
    )
    @click.option("--take", type=int, help="Limit the number of exported rows")
    @click.option(
        "--request",
        type=click.Path(exists=True, dir_okay=False, readable=True),
        help="Path to raw export JSON",
    )
    @click.option(
        "--output",
        "-o",
        type=click.Path(dir_okay=False, writable=True),
        help="Output CSV file path",
    )
    def export_table_data(
        table_id: str,
        columns: Optional[str],
        where: Tuple[str, ...],
        order_by_clauses: Tuple[str, ...],
        take: Optional[int],
        request: Optional[str],
        output: Optional[str],
    ) -> None:
        """Export table rows as CSV."""
        payload = _build_data_query_payload(
            request=request,
            columns=columns,
            where=where,
            order_by=order_by_clauses,
            take=take,
            continuation_token=None,
        )
        payload["responseFormat"] = "CSV"
        payload["destination"] = "INLINE"

        try:
            response = make_api_request(
                "POST",
                f"{_get_dataframe_base_url()}/tables/{table_id}/export-data",
                payload=payload,
            )
            csv_text = response.text
            if output:
                with open(output, "w", encoding="utf-8") as output_file:
                    output_file.write(csv_text)
                format_success("DataFrame table exported", {"id": table_id, "output": output})
                return

            click.echo(csv_text, nl=not csv_text.endswith("\n"))
        except Exception as exc:
            handle_api_error(exc)

    @dataframe.command(name="append")
    @click.argument("table_id")
    @click.option(
        "--input",
        "input_path",
        "-i",
        required=True,
        type=click.Path(exists=True, dir_okay=False, readable=True),
        help="Input file path",
    )
    @click.option(
        "--input-format",
        type=click.Choice(["json", "arrow"]),
        default="json",
        show_default=True,
        help="Input payload format",
    )
    @click.option("--end-of-data", is_flag=True, help="Mark the table as complete after append")
    def append_table_data(
        table_id: str, input_path: str, input_format: str, end_of_data: bool
    ) -> None:
        """Append JSON or Arrow row data to a DataFrame table."""
        check_readonly_mode("append dataframe rows")

        try:
            if input_format == "arrow":
                _post_arrow_append(table_id, input_path, end_of_data)
                format_success(
                    "DataFrame rows appended",
                    {"id": table_id, "input": input_path, "format": input_format},
                )
                return

            payload = load_json_file(input_path)
            if not isinstance(payload, dict):
                _exit_invalid_input("Append input file must contain a JSON object")
            if end_of_data:
                payload["endOfData"] = True
            _validate_append_payload(payload)
            make_api_request(
                "POST", f"{_get_dataframe_base_url()}/tables/{table_id}/data", payload=payload
            )
            frame = payload.get("frame", {}) if isinstance(payload.get("frame"), dict) else {}
            rows_appended = len(frame.get("data", []) or [])
            format_success(
                "DataFrame rows appended",
                {
                    "id": table_id,
                    "rows": rows_appended,
                    "endOfData": payload.get("endOfData", False),
                },
            )
        except Exception as exc:
            handle_api_error(exc)

    @dataframe.command(name="create")
    @click.option(
        "--definition",
        type=click.Path(exists=True, dir_okay=False, readable=True),
        required=True,
        help="Create request JSON",
    )
    @click.option("--name", help="Override the table name in the definition file")
    @click.option("--workspace", "workspace_name", "-w", help="Workspace name or ID")
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    def create_table(
        definition: str,
        name: Optional[str],
        workspace_name: Optional[str],
        format: str,
    ) -> None:
        """Create a new DataFrame table."""
        check_readonly_mode("create a dataframe table")
        format_output = validate_output_format(format)

        payload = load_json_file(definition)
        if not isinstance(payload, dict):
            _exit_invalid_input("Table definition must contain a JSON object")
        if name is not None:
            payload["name"] = name

        workspace_id = _resolve_workspace_id(workspace_name)
        if workspace_id and "workspace" not in payload:
            payload["workspace"] = workspace_id

        try:
            response = make_api_request(
                "POST", f"{_get_dataframe_base_url()}/tables", payload=payload
            )
            created = response.json() if response.text.strip() else {}
            if format_output == "json":
                click.echo(json.dumps(created, indent=2))
                return

            format_success(
                "DataFrame table created",
                {"id": created.get("id", ""), "name": payload.get("name", "")},
            )
        except Exception as exc:
            handle_api_error(exc)

    @dataframe.command(name="update")
    @click.argument("table_id")
    @click.option("--name", help="New table name")
    @click.option("--workspace", "workspace_name", "-w", help="New workspace name or ID")
    @click.option("--test-result-id", help="New associated test result ID")
    @click.option(
        "--property", "property_assignments", multiple=True, help="Set KEY=VALUE property"
    )
    @click.option("--remove-property", multiple=True, help="Remove a table property by key")
    @click.option(
        "--column-property",
        "column_property_assignments",
        multiple=True,
        help="Set COLUMN:KEY=VALUE property",
    )
    @click.option(
        "--remove-column-property",
        multiple=True,
        help="Remove a column property with COLUMN:KEY",
    )
    @click.option("--metadata-revision", type=int, help="Expected next metadata revision")
    def update_table(
        table_id: str,
        name: Optional[str],
        workspace_name: Optional[str],
        test_result_id: Optional[str],
        property_assignments: Tuple[str, ...],
        remove_property: Tuple[str, ...],
        column_property_assignments: Tuple[str, ...],
        remove_column_property: Tuple[str, ...],
        metadata_revision: Optional[int],
    ) -> None:
        """Update table metadata or column properties."""
        check_readonly_mode("update dataframe metadata")
        payload = _build_update_payload(
            name=name,
            workspace=workspace_name,
            test_result_id=test_result_id,
            property_assignments=property_assignments,
            remove_properties=remove_property,
            column_property_assignments=column_property_assignments,
            remove_column_properties=remove_column_property,
            metadata_revision=metadata_revision,
        )
        if not payload:
            _exit_invalid_input("Specify at least one field to update")

        try:
            make_api_request(
                "PATCH", f"{_get_dataframe_base_url()}/tables/{table_id}", payload=payload
            )
            format_success("DataFrame table updated", {"id": table_id})
        except Exception as exc:
            handle_api_error(exc)

    @dataframe.command(name="update-many")
    @click.option(
        "--definition",
        type=click.Path(exists=True, dir_okay=False, readable=True),
        required=True,
        help="Modify-tables request JSON",
    )
    def update_many_tables(definition: str) -> None:
        """Update metadata for one or more DataFrame tables."""
        check_readonly_mode("update dataframe metadata")
        payload = load_json_file(definition)
        if not isinstance(payload, dict):
            _exit_invalid_input("Batch update definition must contain a JSON object")

        try:
            response = make_api_request(
                "POST", f"{_get_dataframe_base_url()}/modify-tables", payload=payload
            )
            if response.status_code == 204:
                format_success("DataFrame tables updated")
                return

            data = response.json() if response.text.strip() else {}
            modified_ids = data.get("modifiedTableIds", []) or []
            format_success(
                "DataFrame tables updated with partial success", {"updated": len(modified_ids)}
            )
            if data.get("failedModifications"):
                error_value = data.get("error")
                error_data: Dict[str, Any] = error_value if isinstance(error_value, dict) else {}
                click.echo(
                    f"✗ Failed modifications: {len(data.get('failedModifications', []))}", err=True
                )
                click.echo(str(error_data.get("message", "Unknown error")), err=True)
                sys.exit(ExitCodes.GENERAL_ERROR)
        except Exception as exc:
            handle_api_error(exc)

    @dataframe.command(name="delete")
    @click.argument("table_ids", nargs=-1, required=True)
    @click.option("--yes", "force", is_flag=True, help="Skip confirmation prompt")
    def delete_tables(table_ids: Tuple[str, ...], force: bool) -> None:
        """Delete one or more DataFrame tables."""
        check_readonly_mode("delete dataframe table(s)")

        ids = list(table_ids)
        if not confirm_bulk_operation("delete", "dataframe table", len(ids), force=force):
            return

        try:
            if len(ids) == 1:
                make_api_request("DELETE", f"{_get_dataframe_base_url()}/tables/{ids[0]}")
                format_success("DataFrame table deleted", {"id": ids[0]})
                return

            response = make_api_request(
                "POST", f"{_get_dataframe_base_url()}/delete-tables", payload={"ids": ids}
            )
            if response.status_code == 204:
                format_success("DataFrame tables deleted", {"count": len(ids)})
                return

            data = response.json() if response.text.strip() else {}
            deleted_ids = data.get("deletedTableIds", []) or []
            failed_ids = data.get("failedTableIds", []) or []
            format_success(
                "DataFrame tables deleted with partial success", {"deleted": len(deleted_ids)}
            )
            if failed_ids:
                error_value = data.get("error")
                error_data: Dict[str, Any] = error_value if isinstance(error_value, dict) else {}
                click.echo(f"✗ Failed to delete: {', '.join(failed_ids)}", err=True)
                click.echo(str(error_data.get("message", "Unknown error")), err=True)
                sys.exit(ExitCodes.GENERAL_ERROR)
        except Exception as exc:
            handle_api_error(exc)
