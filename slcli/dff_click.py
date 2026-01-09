"""CLI commands for managing SystemLink Dynamic Form Fields."""

import json
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

import click
import requests

from .platform import require_feature
from .universal_handlers import FilteredResponse, UniversalResponseHandler
from .utils import (
    ExitCodes,
    get_base_url,
    get_workspace_map,
    handle_api_error,
    load_json_file,
    make_api_request,
    sanitize_filename,
    save_json_file,
)
from .web_editor import launch_dff_editor
from .workspace_utils import (
    WorkspaceFormatter,
    filter_by_workspace,
    resolve_workspace_filter,
)

# Valid resource types for Dynamic Form Fields
VALID_RESOURCE_TYPES = [
    "workorder:workorder",
    "workitem:workitem",
    "asset:asset",
    "system:system",
    "testmonitor:product",
]

# Valid field types for Dynamic Form Fields
VALID_FIELD_TYPES = [
    "Text",
    "Number",
    "Boolean",
    "Enum",
    "DateTime",
    "Table",
    "LinkedResource",
]

# Help text for resource type parameter
RESOURCE_TYPE_HELP = f"Resource type. Valid values: {', '.join(VALID_RESOURCE_TYPES)}"

# Help text for field type parameter
FIELD_TYPE_HELP = f"Field type. Valid values: {', '.join(VALID_FIELD_TYPES)}"


def _handle_dff_error_response(error_data: Dict[str, Any], operation: str = "operation") -> None:
    """Parse and display DFF-specific error responses."""
    # Check for DFF-specific error structure with failedConfigurations, failedGroups, etc.
    if any(key in error_data for key in ["failedConfigurations", "failedGroups", "failedFields"]):
        _handle_dff_creation_errors(error_data, operation)

    elif "error" in error_data and "innerErrors" in error_data["error"]:
        # Handle nested error structure
        _handle_dff_nested_errors(error_data["error"])

    elif "errors" in error_data:
        # Handle simple validation errors structure
        _handle_simple_validation_errors(error_data)

    else:
        # Fallback for unknown error structure
        click.echo("✗ Request failed with validation errors:", err=True)
        if "message" in error_data:
            click.echo(f"  {error_data['message']}", err=True)
        else:
            click.echo(f"  {error_data}", err=True)


def _handle_dff_creation_errors(error_data: Dict[str, Any], operation: str = "operation") -> None:
    """Handle DFF creation/update response with failed configurations/groups/fields."""
    click.echo(f"✗ Configuration {operation} failed with the following issues:", err=True)

    # Show successful operations if any
    successful_configs = error_data.get("configurations", [])
    if successful_configs:
        click.echo(f"\n✓ Successfully {operation}d configurations:")
        for config in successful_configs:
            click.echo(f"  - {config.get('name', config.get('key', 'Unknown'))}")

    # Show failed configurations
    failed_configs = error_data.get("failedConfigurations", [])
    if failed_configs:
        click.echo("\n✗ Failed configurations:")
        for config in failed_configs:
            click.echo(f"  - {config.get('name', config.get('key', 'Unknown'))}")

    # Show failed groups
    failed_groups = error_data.get("failedGroups", [])
    if failed_groups:
        click.echo("\n✗ Failed groups:")
        for group in failed_groups:
            click.echo(f"  - {group.get('displayText', group.get('key', 'Unknown'))}")


def _handle_dff_nested_errors(error: Dict[str, Any]) -> None:
    """Handle nested error structure with innerErrors."""
    click.echo("✗ Request failed with validation errors:", err=True)

    if "message" in error:
        click.echo(f"  {error['message']}")

    inner_errors = error.get("innerErrors", [])
    if inner_errors:
        click.echo("\nDetailed errors:")
        for inner_error in inner_errors:
            message = inner_error.get("message", "Unknown error")
            click.echo(f"  • {message}")


def _handle_simple_validation_errors(error_data: Dict[str, Any]) -> None:
    """Handle simple validation errors structure."""
    click.echo("✗ Validation errors occurred:", err=True)
    errors = error_data.get("errors", {})

    for field, field_errors in errors.items():
        if isinstance(field_errors, list):
            for error in field_errors:
                click.echo(f"  - {field}: {error}", err=True)
        else:
            click.echo(f"  - {field}: {field_errors}", err=True)

    # Show title if available
    if "title" in error_data:
        click.echo(f"  Summary: {error_data['title']}", err=True)


def validate_resource_type(resource_type: str) -> None:
    """Validate that the resource type is one of the supported values.

    Args:
        resource_type: The resource type to validate

    Raises:
        click.ClickException: If the resource type is not valid
    """
    if resource_type not in VALID_RESOURCE_TYPES:
        valid_types_str = ", ".join(VALID_RESOURCE_TYPES)
        raise click.ClickException(
            f"Invalid resource type: '{resource_type}'. " f"Valid types are: {valid_types_str}"
        )


def validate_field_type(field_type: str) -> None:
    """Validate that the field type is one of the supported values.

    Args:
        field_type: The field type to validate

    Raises:
        click.ClickException: If the field type is not valid
    """
    if field_type not in VALID_FIELD_TYPES:
        valid_types_str = ", ".join(VALID_FIELD_TYPES)
        raise click.ClickException(
            f"Invalid field type: '{field_type}'. " f"Valid types are: {valid_types_str}"
        )


def _query_all_groups(
    workspace_filter: Optional[str] = None, workspace_map: Optional[dict] = None
) -> List[Dict[str, Any]]:
    """Query all DFF groups using continuation token pagination.

    Args:
        workspace_filter: Optional workspace ID or name to filter by
        workspace_map: Optional workspace mapping to avoid repeated lookups

    Returns:
        List of all groups, optionally filtered by workspace
    """
    url = f"{get_base_url()}/nidynamicformfields/v1/groups"
    all_groups = []
    continuation_token = None

    while True:
        # Build parameters for the request
        params = {"Take": 100}  # Use smaller page size for efficient pagination
        if continuation_token:
            params["ContinuationToken"] = continuation_token

        # Build query string
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        full_url = f"{url}?{query_string}"

        resp = make_api_request("GET", full_url)
        data = resp.json()

        # Extract groups from this page
        groups = data.get("groups", [])
        all_groups.extend(groups)

        # Check if there are more pages
        continuation_token = data.get("continuationToken")
        if not continuation_token:
            break

    # Filter by workspace if specified
    if workspace_filter and workspace_map:
        all_groups = filter_by_workspace(all_groups, workspace_filter, workspace_map)

    return all_groups


def _query_all_fields(
    workspace_filter: Optional[str] = None, workspace_map: Optional[dict] = None
) -> List[Dict[str, Any]]:
    """Query all DFF fields using continuation token pagination.

    Args:
        workspace_filter: Optional workspace ID or name to filter by
        workspace_map: Optional workspace mapping to avoid repeated lookups

    Returns:
        List of all fields, optionally filtered by workspace
    """
    url = f"{get_base_url()}/nidynamicformfields/v1/fields"
    all_fields = []
    continuation_token = None

    while True:
        # Build parameters for the request
        params = {"Take": 500}  # Use smaller page size for efficient pagination
        if continuation_token:
            params["ContinuationToken"] = continuation_token

        # Build query string
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        full_url = f"{url}?{query_string}"

        resp = make_api_request("GET", full_url)
        data = resp.json()

        # Extract fields from this page
        fields = data.get("fields", [])
        all_fields.extend(fields)

        # Check if there are more pages
        continuation_token = data.get("continuationToken")
        if not continuation_token:
            break

    # Filter by workspace if specified
    if workspace_filter and workspace_map:
        all_fields = filter_by_workspace(all_fields, workspace_filter, workspace_map)

    return all_fields


def _query_all_configurations(
    workspace_filter: Optional[str] = None, workspace_map: Optional[dict] = None
) -> List[Dict[str, Any]]:
    """Query all configurations using continuation token pagination.

    Args:
        workspace_filter: Optional workspace ID or name to filter by
        workspace_map: Optional workspace mapping to avoid repeated lookups

    Returns:
        List of all configurations, optionally filtered by workspace
    """
    url = f"{get_base_url()}/nidynamicformfields/v1/configurations"
    all_configurations = []
    continuation_token = None

    while True:
        # Build parameters for the request
        params = {"Take": 100}  # Use smaller page size for efficient pagination
        if continuation_token:
            params["ContinuationToken"] = continuation_token

        # Build query string
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        full_url = f"{url}?{query_string}"

        resp = make_api_request("GET", full_url)
        data = resp.json()

        # Extract configurations from this page
        configurations = data.get("configurations", [])
        all_configurations.extend(configurations)

        # Check if there are more pages
        continuation_token = data.get("continuationToken")
        if not continuation_token:
            break

    # Filter by workspace if specified
    if workspace_filter and workspace_map:
        all_configurations = filter_by_workspace(
            all_configurations, workspace_filter, workspace_map
        )

    return all_configurations


def register_dff_commands(cli: Any) -> None:
    """Register the 'dff' command group and its subcommands."""

    @cli.group()
    @click.pass_context
    def dff(ctx: click.Context) -> None:
        """Manage dynamic form field configurations."""
        # Check for platform feature availability
        # Only check if a subcommand is being invoked (not just --help)
        if ctx.invoked_subcommand is not None:
            require_feature("dynamic_form_fields")

    # Configuration commands (now at top level under dff)
    @dff.command(name="list")
    @click.option("--workspace", "-w", help="Filter by workspace name or ID")
    @click.option(
        "--take",
        default=25,
        show_default=True,
        help="Maximum number of configurations to return",
    )
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"], case_sensitive=False),
        default="table",
        show_default=True,
        help="Output format: table or json",
    )
    def list_configurations(
        workspace: Optional[str] = None, take: int = 25, format: str = "table"
    ) -> None:
        """List dynamic form field configurations."""
        try:
            # Get workspace map once and reuse it
            workspace_map = get_workspace_map()

            # Use the workspace formatter for consistent formatting
            format_config_row = WorkspaceFormatter.create_config_row_formatter(workspace_map)

            # Use continuation token pagination following user_click.py pattern
            all_configurations = _query_all_configurations(workspace, workspace_map)

            # Use UniversalResponseHandler for consistent pagination
            from typing import Any

            # Create a mock response with all data
            filtered_resp: Any = FilteredResponse({"configurations": all_configurations})

            handler = UniversalResponseHandler()
            handler.handle_list_response(
                filtered_resp,
                "configurations",
                "configuration",
                format,
                format_config_row,
                ["Workspace", "Name", "Configuration ID"],
                [36, 40, 36],
                "No dynamic form field configurations found.",
                enable_pagination=True,
            )

        except Exception as exc:
            handle_api_error(exc)

    @dff.command(name="get")
    @click.option(
        "--id",
        "-i",
        "config_id",
        required=True,
        help="Configuration ID to retrieve",
    )
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"], case_sensitive=False),
        default="json",
        show_default=True,
        help="Output format: table or json",
    )
    def get_configuration(config_id: str, format: str = "json") -> None:
        """Get a specific dynamic form field configuration by ID."""
        url = f"{get_base_url()}/nidynamicformfields/v1/resolved-configuration"

        try:
            params = {"configurationId": config_id}
            query_string = "&".join([f"{k}={v}" for k, v in params.items()])
            full_url = f"{url}?{query_string}"

            resp = make_api_request("GET", full_url)
            data = resp.json()

            if format == "json":
                click.echo(json.dumps(data, indent=2))
                return

            # Table format - show basic info
            configuration = data.get("configuration", {})
            workspace_map = get_workspace_map()
            workspace_id = configuration.get("workspace", "")
            workspace_name = workspace_map.get(workspace_id, workspace_id)

            click.echo("Configuration Details")
            click.echo("=" * 50)
            click.echo(f"ID: {configuration.get('id', '')}")
            click.echo(f"Name: {configuration.get('name', '')}")
            click.echo(f"Workspace: {workspace_name}")
            click.echo(f"Resource Type: {configuration.get('resourceType', '')}")

            groups = data.get("groups", [])
            fields = data.get("fields", [])
            click.echo(f"Groups: {len(groups)}")
            click.echo(f"Fields: {len(fields)}")

        except Exception as exc:
            handle_api_error(exc)

    @dff.command(name="create")
    @click.option(
        "--file",
        "-f",
        "input_file",
        required=True,
        help="Input JSON file with configuration data",
    )
    def create_configuration(input_file: str) -> None:
        """Create dynamic form field configurations from a JSON file."""
        url = f"{get_base_url()}/nidynamicformfields/v1/configurations"

        try:
            data = load_json_file(input_file)

            # Ensure data is in the expected format
            if isinstance(data, dict) and "configurations" not in data:
                # Wrap single configuration
                data = {"configurations": [data]}
            elif isinstance(data, list):
                # Wrap list of configurations
                data = {"configurations": data}

            # Validate resource types in configurations
            configurations = data.get("configurations", [])
            for i, config in enumerate(configurations):
                if isinstance(config, dict):
                    resource_type = config.get("resourceType")
                    if resource_type:
                        try:
                            validate_resource_type(resource_type)
                        except click.ClickException as e:
                            raise click.ClickException(
                                f"Invalid resource type in configuration {i + 1}: {e.message}"
                            )

            # Validate field types in fields
            fields = data.get("fields", [])
            for i, field in enumerate(fields):
                if isinstance(field, dict):
                    field_type = field.get("type")
                    if field_type:
                        try:
                            validate_field_type(field_type)
                        except click.ClickException as e:
                            raise click.ClickException(
                                f"Invalid field type in field {i + 1}: {e.message}"
                            )

            # Make API request without automatic error handling to parse validation errors
            resp = make_api_request("POST", url, data, handle_errors=False)

            # Check for partial success response
            response_data = resp.json() if resp.text.strip() else {}

            if resp.status_code == 201:
                # Full success
                click.echo("✓ Dynamic form field configurations created successfully.")
                created_configs = response_data.get("configurations", [])
                for config in created_configs:
                    click.echo(f"  - {config.get('name', 'Unknown')}: {config.get('id', '')}")
            elif resp.status_code == 200:
                # Partial success - may contain DFF-specific error structure
                if any(
                    key in response_data
                    for key in ["failedConfigurations", "failedGroups", "failedFields"]
                ):
                    # Use DFF-specific error handling for partial failures
                    _handle_dff_error_response(response_data, "creation")
                    sys.exit(ExitCodes.INVALID_INPUT)
                else:
                    # Handle legacy partial success format
                    click.echo("⚠ Some configurations were created, but some failed:", err=True)

                    # Show successful creations
                    successful = response_data.get("created", [])
                    if successful:
                        click.echo("Created:")
                        for config in successful:
                            click.echo(
                                f"  ✓ {config.get('name', 'Unknown')}: {config.get('id', '')}"
                            )

                    # Show failures
                    failed = response_data.get("failed", [])
                    if failed:
                        click.echo("Failed:")
                        for failure in failed:
                            name = failure.get("name", "Unknown")
                            error = failure.get("error", {})
                            error_msg = error.get("message", "Unknown error")
                            click.echo(f"  ✗ {name}: {error_msg}", err=True)

                    sys.exit(ExitCodes.GENERAL_ERROR)

        except requests.RequestException as exc:
            # Handle HTTP errors with detailed validation error parsing
            if hasattr(exc, "response") and exc.response is not None:
                try:
                    error_data = exc.response.json()
                    status_code = exc.response.status_code

                    if status_code == 400:
                        # Parse DFF-specific error structure
                        _handle_dff_error_response(error_data, "creation")
                        sys.exit(ExitCodes.INVALID_INPUT)
                    else:
                        # Fallback to general error handling for other HTTP errors
                        handle_api_error(exc)
                except (ValueError, KeyError):
                    # If JSON parsing fails, fall back to general error handling
                    handle_api_error(exc)
            else:
                # For non-HTTP errors, use general error handling
                handle_api_error(exc)
        except Exception as exc:
            handle_api_error(exc)

    @dff.command(name="update")
    @click.option(
        "--file",
        "-f",
        "input_file",
        required=True,
        help="Input JSON file with updated configuration data",
    )
    def update_configuration(input_file: str) -> None:
        """Update dynamic form field configurations from a JSON file."""
        url = f"{get_base_url()}/nidynamicformfields/v1/update-configurations"

        try:
            data = load_json_file(input_file)

            # Ensure data is in the expected format
            if isinstance(data, dict) and "configurations" not in data:
                data = {"configurations": [data]}
            elif isinstance(data, list):
                data = {"configurations": data}

            resp = make_api_request("POST", url, data, handle_errors=False)
            response_data = resp.json() if resp.text.strip() else {}

            if resp.status_code == 200:
                # Check if it's a DFF-specific partial success response
                if any(
                    key in response_data
                    for key in ["failedConfigurations", "failedGroups", "failedFields"]
                ):
                    # Use DFF-specific error handling for partial failures
                    _handle_dff_error_response(response_data, "update")
                    sys.exit(ExitCodes.INVALID_INPUT)
                else:
                    # Handle legacy partial success format
                    updated_configs = response_data.get("configurations", [])
                    failed_updates = response_data.get("failed", [])

                    if failed_updates:
                        click.echo("⚠ Some configurations were updated, but some failed:", err=True)

                        if updated_configs:
                            click.echo("Updated:")
                            for config in updated_configs:
                                click.echo(
                                    f"  ✓ {config.get('name', 'Unknown')}: {config.get('id', '')}"
                                )

                        click.echo("Failed:")
                        for failure in failed_updates:
                            name = failure.get("name", "Unknown")
                            error = failure.get("error", {})
                            error_msg = error.get("message", "Unknown error")
                            click.echo(f"  ✗ {name}: {error_msg}", err=True)

                        sys.exit(ExitCodes.GENERAL_ERROR)
                    else:
                        click.echo("✓ Dynamic form field configurations updated successfully.")
                        for config in updated_configs:
                            click.echo(
                                f"  - {config.get('name', 'Unknown')}: {config.get('id', '')}"
                            )

        except requests.RequestException as exc:
            # Handle HTTP errors with detailed validation error parsing
            if hasattr(exc, "response") and exc.response is not None:
                try:
                    error_data = exc.response.json()
                    status_code = exc.response.status_code

                    if status_code == 400:
                        # Parse DFF-specific error structure
                        _handle_dff_error_response(error_data, "update")
                        sys.exit(ExitCodes.INVALID_INPUT)
                    else:
                        # Fallback to general error handling for other HTTP errors
                        handle_api_error(exc)
                except (ValueError, KeyError):
                    # If JSON parsing fails, fall back to general error handling
                    handle_api_error(exc)
            else:
                # For non-HTTP errors, use general error handling
                handle_api_error(exc)
        except Exception as exc:
            handle_api_error(exc)

    @dff.command(name="delete")
    @click.option(
        "--id",
        "-i",
        "config_ids",
        multiple=True,
        help="Configuration ID(s) to delete (can be specified multiple times)",
    )
    @click.option(
        "--group-id",
        "-g",
        "group_ids",
        multiple=True,
        help="Group ID(s) to delete (can be specified multiple times)",
    )
    @click.option(
        "--field-id",
        "--fid",
        "field_ids",
        multiple=True,
        help="Field ID(s) to delete (can be specified multiple times)",
    )
    @click.option(
        "--no-recursive",
        "recursive",
        is_flag=True,
        flag_value=False,
        default=True,
        help="Do not recursively delete dependent items (groups/fields when deleting configs)",
    )
    @click.confirmation_option(prompt="Are you sure you want to delete these items?")
    def delete_configuration(
        config_ids: tuple[str, ...],
        group_ids: tuple[str, ...],
        field_ids: tuple[str, ...],
        recursive: bool = True,
    ) -> None:
        """Delete dynamic form field configurations, groups, and fields."""
        if not config_ids and not group_ids and not field_ids:
            click.echo("✗ Must provide at least one of: --id, --group-id, or --field-id", err=True)
            sys.exit(ExitCodes.INVALID_INPUT)

        url = f"{get_base_url()}/nidynamicformfields/v1/delete"

        try:
            ids_to_delete = {
                "configurationIds": list(config_ids),
                "groupIds": list(group_ids),
                "fieldIds": list(field_ids),
            }

            # Build payload with only non-empty ID lists
            payload: dict[str, Any] = {k: v for k, v in ids_to_delete.items() if v}
            payload["recursive"] = recursive

            if not payload or all(not v for k, v in payload.items() if k != "recursive"):
                click.echo("✗ No IDs found to delete", err=True)
                sys.exit(ExitCodes.INVALID_INPUT)

            resp = make_api_request("POST", url, payload, handle_errors=False)

            if resp.status_code in (200, 204):
                # Build summary
                summary_parts = []
                if ids_to_delete.get("configurationIds"):
                    summary_parts.append(
                        f"{len(ids_to_delete['configurationIds'])} configuration(s)"
                    )
                if ids_to_delete.get("groupIds"):
                    summary_parts.append(f"{len(ids_to_delete['groupIds'])} group(s)")
                if ids_to_delete.get("fieldIds"):
                    summary_parts.append(f"{len(ids_to_delete['fieldIds'])} field(s)")

                summary = " and ".join(summary_parts) if summary_parts else "item(s)"
                click.echo(f"✓ {summary} deleted successfully.")

                # File-based delete removed; no input file updates
            else:
                # Handle partial success if needed
                response_data = resp.json() if resp.text.strip() else {}
                failed_deletes = response_data.get("failed", [])

                if failed_deletes:
                    click.echo("⚠ Some items were deleted, but some failed:", err=True)
                    for failure in failed_deletes:
                        item_id = failure.get("id", "Unknown")
                        error = failure.get("error", {})
                        error_msg = error.get("message", "Unknown error")
                        click.echo(f"  ✗ {item_id}: {error_msg}", err=True)

                    sys.exit(ExitCodes.GENERAL_ERROR)

        except requests.RequestException as exc:
            # Handle HTTP errors with detailed validation error parsing
            if hasattr(exc, "response") and exc.response is not None:
                try:
                    error_data = exc.response.json()
                    status_code = exc.response.status_code

                    if status_code == 400:
                        # Parse DFF-specific error structure
                        _handle_dff_error_response(error_data, "deletion")
                        sys.exit(ExitCodes.INVALID_INPUT)
                    else:
                        # Fallback to general error handling for other HTTP errors
                        handle_api_error(exc)
                except (ValueError, KeyError):
                    # If JSON parsing fails, fall back to general error handling
                    handle_api_error(exc)
            else:
                # For non-HTTP errors, use general error handling
                handle_api_error(exc)
        except Exception as exc:
            handle_api_error(exc)

    @dff.command(name="export")
    @click.option(
        "--id",
        "-i",
        "config_id",
        required=True,
        help="Configuration ID to export",
    )
    @click.option("--output", "-o", help="Output JSON file (default: <config-name>.json)")
    def export_configuration(config_id: str, output: Optional[str] = None) -> None:
        """Export a dynamic form field configuration to a JSON file."""
        url = f"{get_base_url()}/nidynamicformfields/v1/resolved-configuration"

        try:
            params = {"configurationId": config_id}
            query_string = "&".join([f"{k}={v}" for k, v in params.items()])
            full_url = f"{url}?{query_string}"

            resp = make_api_request("GET", full_url)
            data = resp.json()

            # Generate output filename if not provided
            if not output:
                config_name = data.get("configuration", {}).get("name", f"config-{config_id}")
                safe_name = sanitize_filename(config_name, f"config-{config_id}")
                output = f"{safe_name}.json"

            save_json_file(data, output)
            click.echo(f"✓ Configuration exported to {output}")

        except Exception as exc:
            handle_api_error(exc)

    @dff.command(name="init")
    @click.option(
        "--name",
        "-n",
        help="Configuration name (will prompt if not provided)",
    )
    @click.option(
        "--workspace",
        "-w",
        help="Workspace name or ID (will prompt if not provided)",
    )
    @click.option(
        "--resource-type",
        "-r",
        type=click.Choice(VALID_RESOURCE_TYPES, case_sensitive=False),
        help=RESOURCE_TYPE_HELP,
    )
    @click.option(
        "--output",
        "-o",
        help="Output file path (default: <name>-config.json)",
    )
    def init_configuration(
        name: Optional[str] = None,
        workspace: Optional[str] = None,
        resource_type: Optional[str] = None,
        output: Optional[str] = None,
    ) -> None:
        """Create a template configuration file for dynamic form fields."""
        try:
            # Prompt for required fields if not provided
            if not name:
                name = click.prompt("Configuration name")

            if not workspace:
                workspace = click.prompt("Workspace name or ID")

            if not resource_type:
                resource_type = click.prompt(
                    "Resource type", type=click.Choice(VALID_RESOURCE_TYPES, case_sensitive=False)
                )

            # Validate resource type (resource_type is guaranteed to be str at this point)
            if resource_type:
                validate_resource_type(resource_type)

            # Generate output filename if not provided
            if not output:
                safe_name = sanitize_filename(name or "config", "config")
                output = f"{safe_name}-config.json"

            # Try to resolve workspace name to ID
            try:
                workspace_map = get_workspace_map()
                workspace_id = resolve_workspace_filter(workspace or "", workspace_map)
            except Exception:
                workspace_id = workspace or ""

            # Create template configuration
            safe_name = sanitize_filename(name or "config", "config")
            import uuid

            unique_suffix = str(uuid.uuid4())[:8]  # Use first 8 chars of UUID for uniqueness

            template_config = {
                "configurations": [
                    {
                        "name": name,
                        "key": f"{safe_name}-config-{unique_suffix}",
                        "workspace": workspace_id,
                        "resourceType": resource_type,
                        "views": [
                            {
                                "key": f"default-view-{unique_suffix}",
                                "displayText": "Default View",
                                "groups": [f"group1-{unique_suffix}"],
                            }
                        ],
                    }
                ],
                "groups": [
                    {
                        "key": f"group1-{unique_suffix}",
                        "workspace": workspace_id,
                        "displayText": "Example Group",
                        "fields": [f"field1-{unique_suffix}", f"field2-{unique_suffix}"],
                    }
                ],
                "fields": [
                    {
                        "key": f"field1-{unique_suffix}",
                        "workspace": workspace_id,
                        "displayText": "Example Field",
                        "type": "Text",
                        "mandatory": False,
                    },
                    {
                        "key": f"field2-{unique_suffix}",
                        "workspace": workspace_id,
                        "displayText": "Example Field 2",
                        "type": "Text",
                        "mandatory": False,
                    },
                ],
            }

            save_json_file(template_config, output)
            click.echo(f"✓ Configuration template created: {output}")
            click.echo("Edit the file to customize:")
            click.echo("  - Add/modify groups and fields")
            click.echo(
                "  - Set field types (Text, Number, Boolean, Enum, DateTime, Table, LinkedResource)"
            )
            click.echo("  - Configure mandatory/optional fields")
            click.echo("  - Add validation rules and properties as needed")

        except Exception as exc:
            click.echo(f"✗ Error creating configuration template: {exc}", err=True)
            sys.exit(ExitCodes.GENERAL_ERROR)

    # Editor command
    @dff.command(name="edit")
    @click.option(
        "--file",
        "-f",
        help="JSON file to edit (will create new if not exists)",
    )
    @click.option(
        "--id",
        "-i",
        "config_id",
        help="Configuration ID to load in the editor",
    )
    @click.option(
        "--port",
        "-p",
        default=8080,
        show_default=True,
        help="Port for local HTTP server",
    )
    @click.option(
        "--output-dir",
        "-o",
        default="dff-editor",
        show_default=True,
        help="Directory to create editor files in",
    )
    @click.option(
        "--no-browser",
        is_flag=True,
        help="Don't automatically open browser",
    )
    def edit_configuration(
        file: Optional[str] = None,
        config_id: Optional[str] = None,
        port: int = 8080,
        output_dir: str = "dff-editor",
        no_browser: bool = False,
    ) -> None:
        """Launch a local web editor for dynamic form field configurations.

        This command will create a standalone HTML editor in the specified directory
        and start a local HTTP server for editing dynamic form field configurations.

        You can provide a JSON file to edit, or load a configuration by ID from the server.
        """
        try:
            # If config_id is provided, fetch and export it temporarily
            if config_id:
                url = f"{get_base_url()}/nidynamicformfields/v1/resolved-configuration"
                params = {"configurationId": config_id}
                query_string = "&".join([f"{k}={v}" for k, v in params.items()])
                full_url = f"{url}?{query_string}"

                resp = make_api_request("GET", full_url)
                data = resp.json()

                # Ensure output directory exists before writing fetched file
                output_path = Path(output_dir)
                output_path.mkdir(parents=True, exist_ok=True)

                # Use a temp file or generate a filename inside output_dir
                if not file:
                    config_name = data.get("configuration", {}).get("name", f"config-{config_id}")
                    safe_name = sanitize_filename(config_name, f"config-{config_id}")
                    file = str(output_path / f"{safe_name}.json")
                else:
                    file = str(Path(file))

                # Save the fetched configuration to file
                save_json_file(data, file)
                click.echo(f"✓ Configuration loaded from server: {file}")

                # Save editor metadata with config ID
                metadata = {"configId": config_id, "configFile": Path(file).name}
                save_json_file(metadata, str(output_path / ".editor-metadata.json"))

            launch_dff_editor(
                file=file, port=port, output_dir=output_dir, open_browser=not no_browser
            )
        except Exception as exc:
            handle_api_error(exc)
