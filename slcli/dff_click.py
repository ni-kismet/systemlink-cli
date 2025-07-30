"""CLI commands for managing SystemLink Dynamic Form Fields."""

import json
import sys
from typing import Optional

import click
import requests

from .universal_handlers import UniversalResponseHandler
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
from .workspace_utils import filter_by_workspace, resolve_workspace_filter, WorkspaceFormatter

# Valid resource types for Dynamic Form Fields
VALID_RESOURCE_TYPES = [
    "workorder:workorder",
    "workorder:testplan",
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


def _handle_dff_error_response(error_data, operation="operation"):
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


def _handle_dff_creation_errors(error_data, operation="operation"):
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


def _handle_dff_nested_errors(error):
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


def _handle_simple_validation_errors(error_data):
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


def _query_all_groups(workspace_filter: Optional[str] = None, workspace_map: Optional[dict] = None):
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


def _query_all_fields(workspace_filter: Optional[str] = None, workspace_map: Optional[dict] = None):
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
):
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


def register_dff_commands(cli):
    """Register the 'dff' command group and its subcommands."""

    @cli.group()
    def dff():
        """Manage dynamic form fields (configurations, groups, fields, tables)."""
        pass

    # Configuration commands
    @dff.group()
    def config():
        """Manage dynamic form field configurations."""
        pass

    @config.command(name="list")
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
    def list_configurations(workspace: Optional[str] = None, take: int = 25, format: str = "table"):
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
            class FilteredResponse:
                def __init__(self, filtered_data):
                    self._data = {"configurations": filtered_data}

                def json(self):
                    return self._data

                @property
                def status_code(self):
                    return 200

            filtered_resp: Any = FilteredResponse(all_configurations)

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

    @config.command(name="get")
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
    def get_configuration(config_id: str, format: str = "json"):
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

    @config.command(name="create")
    @click.option(
        "--file",
        "-f",
        "input_file",
        required=True,
        help="Input JSON file with configuration data",
    )
    def create_configuration(input_file: str):
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

    @config.command(name="update")
    @click.option(
        "--file",
        "-f",
        "input_file",
        required=True,
        help="Input JSON file with updated configuration data",
    )
    def update_configuration(input_file: str):
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

    @config.command(name="delete")
    @click.option(
        "--id",
        "-i",
        "config_ids",
        multiple=True,
        help="Configuration ID(s) to delete (can be specified multiple times)",
    )
    @click.option(
        "--file",
        "-f",
        "input_file",
        help="JSON file containing IDs to delete",
    )
    @click.confirmation_option(prompt="Are you sure you want to delete these configurations?")
    def delete_configuration(config_ids: tuple, input_file: Optional[str] = None):
        """Delete dynamic form field configurations."""
        if not config_ids and not input_file:
            click.echo("✗ Must provide either --id or --file", err=True)
            sys.exit(ExitCodes.INVALID_INPUT)

        url = f"{get_base_url()}/nidynamicformfields/v1/delete"

        try:
            ids_to_delete = list(config_ids)

            if input_file:
                file_data = load_json_file(input_file)
                if isinstance(file_data, dict):
                    ids_to_delete.extend(file_data.get("configurationIds", []))
                elif isinstance(file_data, list):
                    ids_to_delete.extend(file_data)

            if not ids_to_delete:
                click.echo("✗ No configuration IDs found to delete", err=True)
                sys.exit(ExitCodes.INVALID_INPUT)

            payload = {"configurationIds": ids_to_delete}
            resp = make_api_request("POST", url, payload, handle_errors=False)

            if resp.status_code in (200, 204):
                click.echo(f"✓ {len(ids_to_delete)} configuration(s) deleted successfully.")
            else:
                # Handle partial success if needed
                response_data = resp.json() if resp.text.strip() else {}
                failed_deletes = response_data.get("failed", [])

                if failed_deletes:
                    click.echo("⚠ Some configurations were deleted, but some failed:", err=True)
                    for failure in failed_deletes:
                        config_id = failure.get("id", "Unknown")
                        error = failure.get("error", {})
                        error_msg = error.get("message", "Unknown error")
                        click.echo(f"  ✗ {config_id}: {error_msg}", err=True)
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

    @config.command(name="export")
    @click.option(
        "--id",
        "-i",
        "config_id",
        required=True,
        help="Configuration ID to export",
    )
    @click.option("--output", "-o", help="Output JSON file (default: <config-name>.json)")
    def export_configuration(config_id: str, output: Optional[str] = None):
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

    @config.command(name="init")
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
    ):
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

    # Groups commands
    @dff.group()
    def groups():
        """Manage dynamic form field groups."""
        pass

    @groups.command(name="list")
    @click.option("--workspace", "-w", help="Filter by workspace name or ID")
    @click.option(
        "--take",
        default=25,
        show_default=True,
        help="Maximum number of groups to return",
    )
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"], case_sensitive=False),
        default="table",
        show_default=True,
        help="Output format: table or json",
    )
    def list_groups(workspace: Optional[str] = None, take: int = 25, format: str = "table"):
        """List dynamic form field groups."""
        try:
            # Get workspace map once and reuse it
            workspace_map = get_workspace_map()

            # Use continuation token pagination following the pattern
            all_groups = _query_all_groups(workspace, workspace_map)

            # Use the workspace formatter for consistent formatting
            format_group_row = WorkspaceFormatter.create_group_field_row_formatter(workspace_map)

            # Use UniversalResponseHandler for consistent pagination
            from typing import Any

            # Create a mock response with all data
            class FilteredResponse:
                def __init__(self, filtered_data):
                    self._data = {"groups": filtered_data}

                def json(self):
                    return self._data

                @property
                def status_code(self):
                    return 200

            filtered_resp: Any = FilteredResponse(all_groups)

            handler = UniversalResponseHandler()
            handler.handle_list_response(
                filtered_resp,
                "groups",
                "group",
                format,
                format_group_row,
                ["Workspace", "Name", "Key"],
                [23, 32, 39],
                "No dynamic form field groups found.",
                enable_pagination=True,
            )

        except Exception as exc:
            handle_api_error(exc)

    # Fields commands
    @dff.group()
    def fields():
        """Manage dynamic form field definitions."""
        pass

    @fields.command(name="list")
    @click.option("--workspace", "-w", help="Filter by workspace name or ID")
    @click.option(
        "--take",
        default=25,
        show_default=True,
        help="Maximum number of fields to return",
    )
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"], case_sensitive=False),
        default="table",
        show_default=True,
        help="Output format: table or json",
    )
    def list_fields(workspace: Optional[str] = None, take: int = 25, format: str = "table"):
        """List dynamic form fields."""
        try:
            # Get workspace map once and reuse it
            workspace_map = get_workspace_map()

            # Use continuation token pagination following the pattern
            all_fields = _query_all_fields(workspace, workspace_map)

            # Use the workspace formatter for consistent formatting
            format_field_row = WorkspaceFormatter.create_group_field_row_formatter(workspace_map)

            # Use UniversalResponseHandler for consistent pagination
            from typing import Any

            # Create a mock response with all data
            class FilteredResponse:
                def __init__(self, filtered_data):
                    self._data = {"fields": filtered_data}

                def json(self):
                    return self._data

                @property
                def status_code(self):
                    return 200

            filtered_resp: Any = FilteredResponse(all_fields)

            handler = UniversalResponseHandler()
            handler.handle_list_response(
                filtered_resp,
                "fields",
                "field",
                format,
                format_field_row,
                ["Workspace", "Name", "Key"],
                [23, 32, 39],
                "No dynamic form fields found.",
                enable_pagination=True,
            )

        except Exception as exc:
            handle_api_error(exc)

    # Table properties commands
    @dff.group()
    def tables():
        """Manage table properties."""
        pass

    @tables.command(name="query")
    @click.option(
        "--workspace",
        "-w",
        required=True,
        help="Workspace name or ID to query tables for",
    )
    @click.option(
        "--resource-id",
        "-i",
        required=True,
        help="Resource ID to filter by",
    )
    @click.option(
        "--resource-type",
        "-r",
        required=True,
        type=click.Choice(VALID_RESOURCE_TYPES, case_sensitive=False),
        help=RESOURCE_TYPE_HELP,
    )
    @click.option(
        "--keys",
        "-k",
        multiple=True,
        help="Table keys to filter by (can be specified multiple times)",
    )
    @click.option(
        "--take",
        default=25,
        show_default=True,
        help="Maximum number of table properties to return",
    )
    @click.option(
        "--continuation-token",
        "-c",
        help="Continuation token for pagination",
    )
    @click.option(
        "--return-count",
        is_flag=True,
        help="Return the total count of accessible table properties",
    )
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"], case_sensitive=False),
        default="table",
        show_default=True,
        help="Output format: table or json",
    )
    def query_tables(
        workspace: str,
        resource_id: str,
        resource_type: str,
        keys: tuple = (),
        take: int = 25,
        continuation_token: Optional[str] = None,
        return_count: bool = False,
        format: str = "table",
    ):
        """Query table properties."""
        url = f"{get_base_url()}/nidynamicformfields/v1/query-tables"

        try:
            # Try to resolve workspace name to ID
            try:
                workspace_map = get_workspace_map()
                workspace_id = resolve_workspace_filter(workspace, workspace_map)
            except Exception:
                workspace_id = workspace

            # Build payload according to the correct API schema
            payload = {
                "workspace": workspace_id,
                "resourceType": resource_type,
                "resourceId": resource_id,
                "take": take,
                "returnCount": return_count,
            }

            # Add optional parameters if provided
            if keys:
                payload["keys"] = list(keys)

            if continuation_token:
                payload["continuationToken"] = continuation_token

            resp = make_api_request("POST", url, payload, handle_errors=False)
            data = resp.json()
            tables = data.get("tables", [])

            # Use the workspace formatter for consistent formatting
            format_table_row = WorkspaceFormatter.create_table_row_formatter(workspace_map)

            # Use UniversalResponseHandler for consistent pagination
            from typing import Any

            # Create a mock response with filtered data
            class FilteredResponse:
                def __init__(self, filtered_data):
                    self._data = {"tables": filtered_data}

                def json(self):
                    return self._data

                @property
                def status_code(self):
                    return 200

            filtered_resp: Any = FilteredResponse(tables)

            handler = UniversalResponseHandler()
            handler.handle_list_response(
                filtered_resp,
                "tables",
                "table",
                format,
                format_table_row,
                ["Workspace", "Resource Type", "Resource ID", "Table ID"],
                [36, 30, 18, 36],
                "No table properties found.",
                enable_pagination=True,
            )

        except requests.RequestException as exc:
            # Handle HTTP errors with detailed validation error parsing
            if hasattr(exc, "response") and exc.response is not None:
                try:
                    error_data = exc.response.json()
                    status_code = exc.response.status_code

                    if status_code == 400:
                        # Parse DFF-specific error structure
                        _handle_dff_error_response(error_data, "query")
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

    @tables.command(name="get")
    @click.option(
        "--id",
        "-i",
        "table_id",
        required=True,
        help="Table property ID to retrieve",
    )
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"], case_sensitive=False),
        default="json",
        show_default=True,
        help="Output format: table or json",
    )
    def get_table(table_id: str, format: str = "json"):
        """Get a specific table property by ID."""
        url = f"{get_base_url()}/nidynamicformfields/v1/table"

        try:
            params = {"tablePropertyId": table_id}
            query_string = "&".join([f"{k}={v}" for k, v in params.items()])
            full_url = f"{url}?{query_string}"

            resp = make_api_request("GET", full_url)
            data = resp.json()

            if format == "json":
                click.echo(json.dumps(data, indent=2))
                return

            # Table format - show basic info
            table_property = data.get("tableProperty", {})
            workspace_map = get_workspace_map()
            workspace_id = table_property.get("workspace", "")
            workspace_name = workspace_map.get(workspace_id, workspace_id)

            click.echo("Table Property Details")
            click.echo("=" * 50)
            click.echo(f"ID: {table_property.get('id', '')}")
            click.echo(f"Workspace: {workspace_name}")
            click.echo(f"Resource Type: {table_property.get('resourceType', '')}")
            click.echo(f"Resource ID: {table_property.get('resourceId', '')}")

            # Show data frame info if available
            data_frame = table_property.get("dataFrame", {})
            if data_frame:
                columns = data_frame.get("columns", [])
                data_rows = data_frame.get("data", [])
                click.echo(f"Columns: {len(columns)}")
                click.echo(f"Rows: {len(data_rows)}")

        except Exception as exc:
            handle_api_error(exc)

    # Editor command (future stub)
    @dff.command(name="edit")
    @click.option(
        "--file",
        "-f",
        help="JSON file to edit (will create new if not exists)",
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
        port: int = 8080,
        output_dir: str = "dff-editor",
        no_browser: bool = False,
    ):
        """Launch a local web editor for dynamic form field configurations.

        This command will create a standalone HTML editor in the specified directory
        and start a local HTTP server for editing dynamic form field configurations.
        """
        launch_dff_editor(file=file, port=port, output_dir=output_dir, open_browser=not no_browser)
