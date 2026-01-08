"""CLI commands for managing SystemLink users via the SystemLink User Service API.

Provides CLI commands for listing, creating, updating, deleting, and querying users.
All commands use Click for robust CLI interfaces and error handling.
"""

import json
import re
import shutil
import sys
from typing import Any, Dict, List, Optional
from uuid import uuid4

import click

from .cli_utils import paginate_list_output, validate_output_format
from .utils import (
    ExitCodes,
    format_success,
    get_base_url,
    handle_api_error,
    make_api_request,
)
from .workspace_utils import get_workspace_display_name, resolve_workspace_id


def _get_policy_details(policy_id: str) -> Optional[dict]:
    """Fetch policy details from the Auth service.

    Args:
        policy_id: The policy ID to fetch

    Returns:
        Policy details dictionary, or None if not found or no permission
    """
    try:
        url = f"{get_base_url()}/niauth/v1/policies/{policy_id}"
        resp = make_api_request("GET", url, payload=None, handle_errors=False)
        return resp.json()
    except Exception as exc:
        # Check if this is a permission error
        response = getattr(exc, "response", None)
        if response is not None and response.status_code == 401:
            try:
                error_data = response.json()
                if "error" in error_data and error_data["error"].get("name") == "Unauthorized":
                    # Return a special marker indicating permission denied
                    return {"_permission_error": True, "id": policy_id}
            except (ValueError, KeyError):
                pass
        # If policy fetch fails for other reasons, return None
        return None


def _get_policy_template_details(template_id: str) -> Optional[dict]:
    """Fetch policy template details from the Auth service.

    Args:
        template_id: The policy template ID to fetch

    Returns:
        Policy template details dictionary, or None if not found or no permission
    """
    try:
        url = f"{get_base_url()}/niauth/v1/policy-templates/{template_id}"
        resp = make_api_request("GET", url, payload=None, handle_errors=False)
        return resp.json()
    except Exception as exc:
        # Check if this is a permission error
        response = getattr(exc, "response", None)
        if response is not None and response.status_code == 401:
            try:
                error_data = response.json()
                if "error" in error_data and error_data["error"].get("name") == "Unauthorized":
                    # Return a special marker indicating permission denied
                    return {"_permission_error": True, "id": template_id}
            except (ValueError, KeyError):
                pass
        # If template fetch fails for other reasons, return None
        return None


def _create_workspace_policy_from_template(
    template_id: str, workspace: str, name_hint: Optional[str] = None
) -> str:
    """Create a workspace-scoped policy from a template and return its ID."""
    policy_name = name_hint or "workspace-policy"
    # Ensure a reasonably unique name to avoid conflicts
    generated_name = f"{policy_name}-{workspace}-{uuid4().hex[:8]}"

    payload: Dict[str, Any] = {
        "name": generated_name,
        "type": "custom",
        "templateId": template_id,
        "workspace": workspace,
    }

    url = f"{get_base_url()}/niauth/v1/policies"
    resp = make_api_request("POST", url, payload=payload)
    data = resp.json()
    policy_id = data.get("id")
    if not policy_id:
        raise ValueError("Policy creation did not return an ID")
    return policy_id


def _process_workspace_policies(
    workspace_policies: str, name_hint: Optional[str] = None
) -> List[str]:
    """Process workspace-policies string and create policies from templates.

    Args:
        workspace_policies: Comma-separated list of workspace:templateId pairs
        name_hint: Optional name hint for generated policy names

    Returns:
        List of created policy IDs

    Raises:
        SystemExit: If format is invalid, values are empty, or workspace cannot be resolved
    """
    policy_ids: List[str] = []
    mappings = []

    for item in workspace_policies.split(","):
        pair = item.strip()
        if not pair:
            continue
        if ":" not in pair:
            click.echo(
                "✗ Invalid workspace-policies format. Use workspace:templateId "
                "(e.g., 'myWorkspace:template-123')",
                err=True,
            )
            sys.exit(ExitCodes.INVALID_INPUT)
        ws, template_id = pair.split(":", 1)
        ws = ws.strip()
        template_id = template_id.strip()
        if not ws or not template_id:
            click.echo(
                "✗ Invalid workspace-policies entry. Both workspace and templateId are required.",
                err=True,
            )
            sys.exit(ExitCodes.INVALID_INPUT)

        # Resolve workspace name to ID
        ws_id = resolve_workspace_id(ws)
        if not ws_id:
            click.echo(
                f"✗ Could not resolve workspace '{ws}'. Please verify the workspace exists.",
                err=True,
            )
            sys.exit(ExitCodes.NOT_FOUND)

        mappings.append((ws_id, template_id))

    # Create policies for each mapping
    for ws_id, template_id in mappings:
        try:
            created_policy_id = _create_workspace_policy_from_template(
                template_id=template_id,
                workspace=ws_id,
                name_hint=name_hint or "user",
            )
            policy_ids.append(created_policy_id)
        except ValueError as e:
            click.echo(f"✗ Error: {str(e)}", err=True)
            sys.exit(ExitCodes.INVALID_INPUT)
        except Exception as exc:
            handle_api_error(exc)

    return policy_ids


def _calculate_policy_column_widths() -> List[int]:
    """Calculate dynamic column widths for policy statements based on terminal size."""
    try:
        terminal_width = shutil.get_terminal_size().columns
    except Exception:
        terminal_width = 120

    actions_width = 48
    resources_width = 24
    workspace_width = 18
    border_overhead = 14  # Table borders plus spacing for four columns

    description_width = terminal_width - (
        actions_width + resources_width + workspace_width + border_overhead
    )
    description_width = max(30, description_width)

    return [actions_width, resources_width, workspace_width, description_width]


def _truncate_cell(value: str, width: int) -> str:
    """Truncate cell content to fit within the specified width."""
    if len(value) > width:
        return value[: max(0, width - 3)] + "..."
    return value


def _format_policy_table(policies: list) -> None:
    """Format and display policies in a table format.

    Args:
        policies: List of policy IDs to expand and display
    """
    if not policies:
        return

    click.echo("\nPolicies:")
    click.echo("=" * 80)

    # Fetch policy details for each policy ID
    policy_details = []
    permission_errors = []

    for policy_id in policies:
        details = _get_policy_details(policy_id)
        if details:
            # Check if this is a permission error
            if details.get("_permission_error"):
                permission_errors.append(policy_id)
                continue

            # If policy has a templateId, fetch template details too
            template_id = details.get("templateId")
            if template_id:
                template_details = _get_policy_template_details(template_id)
                if template_details:
                    # Check if template access failed due to permissions
                    if template_details.get("_permission_error"):
                        details["template_permission_error"] = True
                    else:
                        # Merge template details into policy details
                        details["template"] = template_details
                        # If policy doesn't have statements but template does
                        if not details.get("statements") and template_details.get("statements"):
                            details["statements"] = template_details.get("statements", [])
            policy_details.append(details)
        else:
            # If we can't fetch details, show just the ID
            policy_details.append({"id": policy_id, "name": "Unknown", "statements": []})

    if not policy_details and not permission_errors:
        click.echo("No policy details available.")
        return

    # Show permission errors if any
    if permission_errors:
        click.echo("✗ Access denied to the following policies (insufficient permissions):")
        for policy_id in permission_errors:
            click.echo(f"  - Policy ID: {policy_id}")
        if policy_details:
            click.echo()  # Add spacing before showing accessible policies

    # Display policy table
    for i, policy in enumerate(policy_details):
        if i > 0:
            click.echo()  # Add spacing between policies

        policy_name = policy.get("name", "Unknown")
        policy_id = policy.get("id", "Unknown")
        policy_type = policy.get("type", "Unknown")

        click.echo(f"Policy: {policy_name} (ID: {policy_id}, Type: {policy_type})")
        click.echo("-" * 60)

        statements = policy.get("statements", [])
        if statements:
            column_widths = _calculate_policy_column_widths()
            headers = ["Actions", "Resources", "Workspace", "Description"]

            def _border(left: str, junction: str, right: str) -> str:
                parts = [left] + ["─" * (w + 2) for w in column_widths]
                border_line = parts[0] + parts[1]
                for segment in parts[2:]:
                    border_line += junction + segment
                return border_line + right

            click.echo(_border("┌", "┬", "┐"))
            header_parts = ["│"]
            for header, width in zip(headers, column_widths):
                header_parts.append(f" {header:<{width}} │")
            click.echo("".join(header_parts))
            click.echo(_border("├", "┼", "┤"))

            for statement in statements:
                row_data = [
                    ", ".join(statement.get("actions", [])),
                    ", ".join(statement.get("resource", [])),
                    statement.get("workspace", ""),
                    statement.get("description", "") or "",
                ]
                row_parts = ["│"]
                for value, width in zip(row_data, column_widths):
                    cell = _truncate_cell(str(value), width)
                    row_parts.append(f" {cell:<{width}} │")
                click.echo("".join(row_parts))

            click.echo(_border("└", "┴", "┘"))
        else:
            click.echo("  No statements defined for this policy.")

        # Show additional policy info if available
        template = policy.get("template")
        if template:
            template_name = template.get("name", "Unknown")
            template_id = policy.get("templateId", "Unknown")
            click.echo(f"  Template: {template_name} (ID: {template_id})")
            template_type = template.get("type")
            if template_type:
                click.echo(f"  Template Type: {template_type}")
        elif policy.get("template_permission_error"):
            template_id = policy.get("templateId", "Unknown")
            click.echo(f"  Template ID: {template_id} (access denied - insufficient permissions)")
        elif policy.get("templateId"):
            click.echo(f"  Template ID: {policy.get('templateId')} (details unavailable)")

        if policy.get("builtIn"):
            click.echo("  Built-in: Yes")

        workspace = policy.get("workspace")
        if workspace:
            workspace_name = get_workspace_display_name(workspace)
            if workspace_name and workspace_name != workspace:
                click.echo(f"  Workspace: {workspace_name} (ID: {workspace})")
            else:
                click.echo(f"  Workspace: {workspace}")


def _query_all_users(
    filter_str: Optional[str] = None,
    sortby: str = "firstName",
    order: str = "asc",
    include_disabled: bool = False,
) -> list:
    """Query all users from the API with server-side pagination using continuation tokens.

    Uses proper Dynamic LINQ filter syntax as specified in the User Service OpenAPI spec.
    Pagination uses continuationToken (not skip/take) as per API specification.
    Filter syntax follows SystemLink User Service API specification:
    - Uses 'and'/'or' operators (not '&&'/'||')
    - String values in double quotes
    - Uses 'status = "active"' for filtering disabled users

    TODO: Follow this pattern for other API clients that support continuation tokens
    Reference: https://dev-api.lifecyclesolutions.ni.com/niuser/swagger/v1/niuser.yaml

    Args:
        filter_str: Filter expression for users
        sortby: Field to sort by
        order: Sort order ('asc' or 'desc')
        include_disabled: Whether to include disabled users

    Returns:
        List of all users
    """
    url = f"{get_base_url()}/niuser/v1/users/query"
    all_users = []
    continuation_token = None
    page_size = 100  # API maximum take limit is 100

    # Build the base filter - combine user filter with active status filter if needed
    combined_filter = filter_str
    if not include_disabled:
        # Add active status filter to the query using correct Dynamic LINQ syntax
        # Note: User API uses 'status' field with values 'pending' or 'active'
        active_filter = 'status = "active"'
        if filter_str:
            combined_filter = f"({filter_str}) and {active_filter}"
        else:
            combined_filter = active_filter

    while True:
        payload = {
            "take": page_size,
            "sortby": sortby,
            "order": "ascending" if order == "asc" else "descending",
        }

        if combined_filter:
            payload["filter"] = combined_filter

        if continuation_token:
            payload["continuationToken"] = continuation_token

        resp = make_api_request("POST", url, payload=payload)
        data = resp.json()
        users = data.get("users", [])

        if not users:
            break

        all_users.extend(users)

        # Check for continuation token to get next page
        continuation_token = data.get("continuationToken")
        if not continuation_token:
            break  # No more pages available

    return all_users


def register_user_commands(cli: click.Group) -> None:
    """Register CLI commands for managing SystemLink users."""

    @cli.group()
    def user() -> None:
        """Manage SystemLink users."""
        pass

    @user.command(name="list")
    @click.option(
        "--workspace",
        "-w",
        help="Filter by workspace name or ID",
    )
    @click.option(
        "--take",
        "-t",
        type=int,
        default=25,
        show_default=True,
        help="Maximum number of users to return",
    )
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    @click.option(
        "--include-disabled",
        is_flag=True,
        help="Include disabled users in the results",
    )
    @click.option(
        "--sortby",
        type=click.Choice(["firstName", "lastName", "email"]),
        default="firstName",
        show_default=True,
        help="Sort users by field",
    )
    @click.option(
        "--order",
        type=click.Choice(["asc", "desc"]),
        default="asc",
        show_default=True,
        help="Sort order",
    )
    @click.option(
        "--filter",
        help="Search text to filter users by first name, last name, or email",
    )
    @click.option(
        "--type",
        "user_type",
        type=click.Choice(["all", "user", "service"]),
        default="all",
        show_default=True,
        help="Filter by account type",
    )
    def list_users(
        workspace: Optional[str] = None,
        take: int = 25,
        format: str = "table",
        include_disabled: bool = False,
        sortby: str = "firstName",
        order: str = "asc",
        filter: Optional[str] = None,
        user_type: str = "all",
    ) -> None:
        """List users with optional filtering and sorting."""
        format_output = validate_output_format(format)

        try:
            # Build search filter from user's filter text
            # Convert simple search text to Dynamic LINQ query across name/email fields
            search_filter = None
            if filter:
                # Escape quotes in the search text
                escaped_filter = filter.replace('"', '\\"')
                # Build a LINQ query that searches firstName, lastName, and email
                search_filter = (
                    f'firstName.Contains("{escaped_filter}") or '
                    f'lastName.Contains("{escaped_filter}") or '
                    f'email.Contains("{escaped_filter}")'
                )

            # Build type filter if specified
            type_filter = None
            if user_type != "all":
                type_filter = f'type = "{user_type}"'

            # For JSON format, we can respect the take parameter and use server-side pagination
            # For table format, we fetch all users and do client-side pagination for better UX
            if format_output.lower() == "json":
                # Use server-side pagination for JSON output
                url = f"{get_base_url()}/niuser/v1/users/query"

                # Build the filter - combine search filter with active status filter if needed
                combined_filter = search_filter
                if not include_disabled:
                    # Add active status filter to the query using correct Dynamic LINQ syntax
                    # Note: User API uses 'status' field with values 'pending' or 'active'
                    active_filter = 'status = "active"'
                    if combined_filter:
                        combined_filter = f"({combined_filter}) and {active_filter}"
                    else:
                        combined_filter = active_filter

                # Add type filter
                if type_filter:
                    if combined_filter:
                        combined_filter = f"({combined_filter}) and {type_filter}"
                    else:
                        combined_filter = type_filter

                payload = {
                    "take": take,
                    "sortby": sortby,
                    "order": "ascending" if order == "asc" else "descending",
                }

                if combined_filter:
                    payload["filter"] = combined_filter

                resp = make_api_request("POST", url, payload=payload)
                data = resp.json()
                users = data.get("users", [])

                click.echo(json.dumps(users, indent=2))
                return
            else:
                # For table format, fetch all users for proper client-side pagination
                # Combine filters for table output
                combined_filter_for_table = search_filter
                if type_filter:
                    if combined_filter_for_table:
                        combined_filter_for_table = (
                            f"({combined_filter_for_table}) and {type_filter}"
                        )
                    else:
                        combined_filter_for_table = type_filter

                all_users = _query_all_users(
                    filter_str=combined_filter_for_table,
                    sortby=sortby,
                    order=order,
                    include_disabled=include_disabled,
                )

                def user_formatter(user: dict) -> list:
                    status = "Active" if user.get("active", True) else "Inactive"
                    acct_type = user.get("type", "user")
                    type_display = "Service" if acct_type == "service" else "User"
                    return [
                        user.get("id", ""),
                        user.get("firstName", ""),
                        user.get("lastName", ""),
                        user.get("email", "") or "-",
                        type_display,
                        status,
                    ]

                # Use client-side pagination with all fetched users
                paginate_list_output(
                    items=all_users,
                    page_size=take,
                    format_output=format_output,
                    formatter_func=user_formatter,
                    headers=["ID", "First Name", "Last Name", "Email", "Type", "Status"],
                    column_widths=[36, 15, 15, 25, 10, 10],
                    empty_message="No users found.",
                    total_label="user(s)",
                )

        except Exception as exc:
            handle_api_error(exc)

    @user.command(name="get")
    @click.option("--id", "-i", "user_id", help="User ID to retrieve")
    @click.option("--email", "user_email", help="User email to retrieve")
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"], case_sensitive=False),
        default="table",
        show_default=True,
        help="Output format: table or json",
    )
    def get_user(
        user_id: Optional[str] = None, user_email: Optional[str] = None, format: str = "table"
    ) -> None:
        """Get details for a specific user by ID or email."""
        if not user_id and not user_email:
            click.echo("✗ Must provide either --id or --email.", err=True)
            sys.exit(ExitCodes.INVALID_INPUT)

        if user_id and user_email:
            click.echo("✗ Cannot specify both --id and --email. Choose one.", err=True)
            sys.exit(ExitCodes.INVALID_INPUT)

        try:
            user = None

            if user_email:
                # Search for user by email using query endpoint
                query_url = f"{get_base_url()}/niuser/v1/users/query"
                query_payload = {"filter": f'email = "{user_email}"', "take": 1}

                query_resp = make_api_request(
                    "POST", query_url, payload=query_payload, handle_errors=False
                )
                query_data = query_resp.json()
                users = query_data.get("users", [])

                if not users:
                    click.echo(f"✗ User with email '{user_email}' not found.", err=True)
                    sys.exit(ExitCodes.NOT_FOUND)

                if len(users) > 1:
                    click.echo(
                        f"✗ Multiple users found with email '{user_email}'. This should not happen.",
                        err=True,
                    )
                    sys.exit(ExitCodes.GENERAL_ERROR)

                user = users[0]
            else:
                # Get user by ID using direct endpoint
                url = f"{get_base_url()}/niuser/v1/users/{user_id}"
                resp = make_api_request("GET", url, payload=None, handle_errors=False)
                user = resp.json()

            if format.lower() == "json":
                # For JSON output, optionally expand policies
                if user.get("policies"):
                    expanded_policies = []
                    policy_permission_errors = []

                    for policy_id in user.get("policies", []):
                        policy_details = _get_policy_details(policy_id)
                        if policy_details:
                            # Check if this is a permission error
                            if policy_details.get("_permission_error"):
                                policy_permission_errors.append(policy_id)
                                continue

                            # If policy has a templateId, fetch template details too
                            template_id = policy_details.get("templateId")
                            if template_id:
                                template_details = _get_policy_template_details(template_id)
                                if template_details:
                                    # Check if template access failed due to permissions
                                    if template_details.get("_permission_error"):
                                        policy_details["template_permission_error"] = True
                                        policy_details["templateId"] = template_id
                                    else:
                                        # Include template details in the expanded policy
                                        policy_details["template"] = template_details
                                        # If policy doesn't have statements but template does
                                        if not policy_details.get(
                                            "statements"
                                        ) and template_details.get("statements"):
                                            policy_details["statements"] = template_details.get(
                                                "statements", []
                                            )
                            expanded_policies.append(policy_details)
                        else:
                            expanded_policies.append({"id": policy_id, "name": "Unknown"})

                    user["expanded_policies"] = expanded_policies
                    if policy_permission_errors:
                        user["policy_permission_errors"] = policy_permission_errors

                click.echo(json.dumps(user, indent=2))
                return

            # Table format
            user_type = user.get("type", "user")
            type_display = "Service Account" if user_type == "service" else "User"
            click.echo(f"{type_display} Details:")
            click.echo("=" * 50)
            click.echo(f"ID: {user.get('id', 'N/A')}")
            click.echo(f"Type: {type_display}")
            click.echo(f"First Name: {user.get('firstName', 'N/A')}")
            click.echo(f"Last Name: {user.get('lastName', 'N/A')}")
            # Only show user-specific fields for non-service accounts
            if user_type != "service":
                click.echo(f"Email: {user.get('email', 'N/A')}")
                click.echo(f"Phone: {user.get('phone', 'N/A')}")
                click.echo(f"Login: {user.get('login', 'N/A')}")
                click.echo(f"NIUA ID: {user.get('niuaId', 'N/A')}")
            click.echo(f"Status: {user.get('status', 'N/A')}")
            click.echo(f"Organization ID: {user.get('orgId', 'N/A')}")
            click.echo(f"Created: {user.get('created', 'N/A')}")
            click.echo(f"Updated: {user.get('updated', 'N/A')}")

            policies = user.get("policies", [])
            if policies:
                _format_policy_table(policies)

            keywords = user.get("keywords", [])
            if keywords:
                click.echo(f"\nKeywords: {', '.join(keywords)}")

            properties = user.get("properties", {})
            if properties:
                click.echo("\nProperties:")
                for key, value in properties.items():
                    click.echo(f"  {key}: {value}")

        except Exception as exc:
            # Check if this is a permission error for user access
            response = getattr(exc, "response", None)
            if response is not None and response.status_code == 401:
                try:
                    error_data = response.json()
                    if "error" in error_data and error_data["error"].get("name") == "Unauthorized":
                        click.echo(
                            "✗ Access denied to user information (insufficient permissions).",
                            err=True,
                        )
                        sys.exit(ExitCodes.PERMISSION_DENIED)
                except (ValueError, KeyError):
                    pass

            # Fall back to standard error handling
            handle_api_error(exc)

    @user.command(name="create")
    @click.option(
        "--type",
        "user_type",
        type=click.Choice(["user", "service"]),
        help="Type of account: 'user' for human users, 'service' for API/automation accounts",
    )
    @click.option("--first-name", help="User's first name (or service account name)")
    @click.option(
        "--last-name",
        help="User's last name (defaults to 'ServiceAccount' for service accounts)",
    )
    @click.option("--email", help="User's email address (not valid for service accounts)")
    @click.option("--niua-id", help="User's NIUA ID (not valid for service accounts)")
    @click.option("--login", help="User's login name (not valid for service accounts)")
    @click.option("--phone", help="User's phone number (not valid for service accounts)")
    @click.option("--accepted-tos", is_flag=True, help="Whether user has accepted terms of service")
    @click.option(
        "--policies",
        help="Comma-separated list of policy IDs to assign to the user",
    )
    @click.option(
        "--policy",
        help="Single policy ID to assign to the user",
    )
    @click.option(
        "--workspace-policies",
        help=(
            "Comma-separated list of workspace:templateId entries (workspace can be name or"
            " ID); a policy will be created per workspace from the template and assigned to"
            " the user"
        ),
    )
    @click.option(
        "--keywords",
        help="Comma-separated list of keywords to associate with the user",
    )
    @click.option(
        "--properties",
        help="JSON string of key-value properties to associate with the user",
    )
    def create_user(
        user_type: Optional[str] = None,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        email: Optional[str] = None,
        niua_id: Optional[str] = None,
        login: Optional[str] = None,
        phone: Optional[str] = None,
        accepted_tos: bool = False,
        policy: Optional[str] = None,
        policies: Optional[str] = None,
        workspace_policies: Optional[str] = None,
        keywords: Optional[str] = None,
        properties: Optional[str] = None,
    ) -> None:
        """Create a new user or service account.

        For regular users (--type user):
            If niuaId is not provided, it will default to the email address.
            Required fields (first name, last name, email) will be prompted for.

        For service accounts (--type service):
            First name is required. Last name defaults to "ServiceAccount" if not provided.
            Email, phone, niuaId, and login are not valid for service accounts.
        """
        # If user_type wasn't specified via CLI, prompt for it first
        if user_type is None:
            user_type = click.prompt(
                "Account type",
                type=click.Choice(["user", "service"]),
                default="user",
                show_choices=True,
            )

        is_service_account = user_type == "service"

        # Validate that service accounts don't have invalid fields
        if is_service_account:
            invalid_fields = []
            if email:
                invalid_fields.append("--email")
            if niua_id:
                invalid_fields.append("--niua-id")
            if login:
                invalid_fields.append("--login")
            if phone:
                invalid_fields.append("--phone")

            if invalid_fields:
                click.echo(
                    f"✗ Service accounts cannot have: {', '.join(invalid_fields)}",
                    err=True,
                )
                sys.exit(ExitCodes.INVALID_INPUT)

        # Prompt for required fields if not provided
        if not first_name:
            prompt_text = "Service account name" if is_service_account else "User's first name"
            first_name = click.prompt(prompt_text, type=str)

        # lastName is required for all account types
        # For service accounts, default to "ServiceAccount" if not provided
        if not last_name:
            if is_service_account:
                last_name = "ServiceAccount"
            else:
                last_name = click.prompt("User's last name", type=str)

        if not is_service_account:
            # Regular user also requires email
            if not email:
                email = click.prompt("User's email address", type=str)

            # Validate email format (basic validation)
            email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
            if email and not re.match(email_pattern, email):
                click.echo("✗ Invalid email format.", err=True)
                sys.exit(ExitCodes.INVALID_INPUT)

            # If niua_id is not provided, default it to the email
            if not niua_id:
                niua_id = email

        url = f"{get_base_url()}/niuser/v1/users"

        # Build user payload
        payload: Dict[str, Any] = {
            "type": user_type,
            "firstName": first_name,
        }

        # lastName is required for all account types
        payload["lastName"] = last_name

        # Add additional fields for regular users
        if not is_service_account:
            payload["email"] = email
            payload["niuaId"] = niua_id
            payload["acceptedToS"] = accepted_tos
            if login:
                payload["login"] = login
            if phone:
                payload["phone"] = phone

        policy_ids: list[str] = []
        if policy:
            policy_ids.append(policy.strip())
        if policies:
            policy_ids.extend([p.strip() for p in policies.split(",")])

        if workspace_policies:
            policy_ids.extend(_process_workspace_policies(workspace_policies, first_name))

        if policy_ids:
            # de-duplicate while preserving order
            seen: set[str] = set()
            deduped: list[str] = []
            for pid in policy_ids:
                if pid and pid not in seen:
                    seen.add(pid)
                    deduped.append(pid)
            payload["policies"] = deduped

        if keywords:
            payload["keywords"] = [k.strip() for k in keywords.split(",")]

        # Start properties with provided JSON, if any
        props_obj: Dict[str, Any] = {}
        if properties:
            try:
                props_obj = json.loads(properties)
            except json.JSONDecodeError:
                click.echo("✗ Invalid JSON format for properties.", err=True)
                sys.exit(ExitCodes.INVALID_INPUT)

        if props_obj:
            payload["properties"] = props_obj

        try:
            resp = make_api_request("POST", url, payload=payload)
            user = resp.json()
            user_id = user.get("id")

            if is_service_account:
                format_success(
                    "Service account created",
                    {"ID": user_id, "Name": user.get("firstName")},
                )
            else:
                format_success("User created", {"ID": user_id, "Email": user.get("email")})

        except Exception as exc:
            # Try to parse API error response for better error messages
            # Check if this is an HTTP error with JSON response
            response = getattr(exc, "response", None)
            if response is not None:
                try:
                    error_data = response.json()
                    if "error" in error_data:
                        error_info = error_data["error"]
                        api_message = error_info.get("message", "")
                        error_name = error_info.get("name", "")

                        if api_message:
                            click.echo(f"✗ {api_message}", err=True)
                            if error_name == "Auth.ValidationError":
                                sys.exit(ExitCodes.INVALID_INPUT)
                            else:
                                sys.exit(ExitCodes.GENERAL_ERROR)
                except (ValueError, KeyError, AttributeError):
                    # Fall back to original error if we can't parse the JSON
                    pass

            # Fall back to standard error handling
            handle_api_error(exc)

    @user.command(name="update")
    @click.option("--id", "-i", "user_id", required=True, help="User ID to update")
    @click.option("--first-name", help="User's first name (or service account name)")
    @click.option("--last-name", help="User's last name")
    @click.option("--email", help="User's email address (not valid for service accounts)")
    @click.option("--login", help="User's login name (not valid for service accounts)")
    @click.option("--phone", help="User's phone number (not valid for service accounts)")
    @click.option("--niua-id", help="User's NIUA ID (not valid for service accounts)")
    @click.option(
        "--accepted-tos",
        type=click.Choice(["true", "false"]),
        help="Whether user has accepted terms of service",
    )
    @click.option(
        "--policy",
        help="Single policy ID to assign to the user",
    )
    @click.option(
        "--policies",
        help="Comma-separated list of policy IDs to assign to the user",
    )
    @click.option(
        "--workspace-policies",
        help=(
            "Comma-separated list of workspace:templateId entries (workspace can be name or"
            " ID); a policy will be created per workspace from the template and assigned to"
            " the user"
        ),
    )
    @click.option(
        "--keywords",
        help="Comma-separated list of keywords to associate with the user",
    )
    @click.option(
        "--properties",
        help="JSON string of key-value properties to associate with the user",
    )
    def update_user(
        user_id: str,
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        email: Optional[str] = None,
        login: Optional[str] = None,
        phone: Optional[str] = None,
        niua_id: Optional[str] = None,
        accepted_tos: Optional[str] = None,
        policy: Optional[str] = None,
        policies: Optional[str] = None,
        workspace_policies: Optional[str] = None,
        keywords: Optional[str] = None,
        properties: Optional[str] = None,
    ) -> None:
        """Update an existing user or service account."""
        # First, fetch the user to check if it's a service account
        get_url = f"{get_base_url()}/niuser/v1/users/{user_id}"
        try:
            get_resp = make_api_request("GET", get_url, payload=None, handle_errors=False)
            existing_user = get_resp.json()
            is_service_account = existing_user.get("type") == "service"
        except Exception:
            # If we can't fetch the user, proceed without validation
            # The API will reject invalid fields anyway
            is_service_account = False

        # Validate that service accounts don't get invalid field updates
        if is_service_account:
            invalid_fields = []
            if email:
                invalid_fields.append("--email")
            if login:
                invalid_fields.append("--login")
            if phone:
                invalid_fields.append("--phone")
            if niua_id:
                invalid_fields.append("--niua-id")
            if accepted_tos:
                invalid_fields.append("--accepted-tos")

            if invalid_fields:
                click.echo(
                    f"✗ Service accounts cannot be updated with: {', '.join(invalid_fields)}",
                    err=True,
                )
                sys.exit(ExitCodes.INVALID_INPUT)

        url = f"{get_base_url()}/niuser/v1/users/{user_id}"

        # Build update payload (only include provided fields)
        payload: Dict[str, Any] = {}

        if first_name:
            payload["firstName"] = first_name

        if last_name:
            payload["lastName"] = last_name

        if email:
            payload["email"] = email

        if login:
            payload["login"] = login

        if phone:
            payload["phone"] = phone

        if niua_id:
            payload["niuaId"] = niua_id

        if accepted_tos:
            payload["acceptedToS"] = accepted_tos.lower() == "true"

        policy_ids_upd: list[str] = []
        if policy:
            policy_ids_upd.append(policy.strip())
        if policies:
            policy_ids_upd.extend([p.strip() for p in policies.split(",")])

        if workspace_policies:
            policy_ids_upd.extend(_process_workspace_policies(workspace_policies, first_name))

        if policy_ids_upd:
            seen_upd: set[str] = set()
            deduped_upd: list[str] = []
            for pid in policy_ids_upd:
                if pid and pid not in seen_upd:
                    seen_upd.add(pid)
                    deduped_upd.append(pid)
            payload["policies"] = deduped_upd

        if keywords:
            payload["keywords"] = [k.strip() for k in keywords.split(",")]

        props_upd: Dict[str, Any] = {}
        if properties:
            try:
                props_upd = json.loads(properties)
            except json.JSONDecodeError:
                click.echo("✗ Invalid JSON format for properties.", err=True)
                sys.exit(ExitCodes.INVALID_INPUT)

        if props_upd:
            payload["properties"] = props_upd

        if not payload:
            click.echo("✗ No fields provided to update.", err=True)
            sys.exit(ExitCodes.INVALID_INPUT)

        try:
            resp = make_api_request("PUT", url, payload=payload)
            user = resp.json()
            if is_service_account:
                format_success(
                    "Service account updated",
                    {"ID": user.get("id"), "Name": user.get("firstName")},
                )
            else:
                format_success("User updated", {"ID": user.get("id"), "Email": user.get("email")})

        except Exception as exc:
            handle_api_error(exc)

    @user.command(name="delete")
    @click.option("--id", "-i", "user_id", required=True, help="User ID to delete")
    @click.confirmation_option(
        prompt="Are you sure you want to delete this user? This action cannot be undone."
    )
    def delete_user(user_id: str) -> None:
        """Delete a user by ID."""
        url = f"{get_base_url()}/niuser/v1/users/{user_id}"

        try:
            make_api_request("DELETE", url, payload=None)
            format_success("User deleted", {"ID": user_id})

        except Exception as exc:
            handle_api_error(exc)
