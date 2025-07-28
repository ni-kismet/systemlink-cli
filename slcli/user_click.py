"""CLI commands for managing SystemLink users via the SystemLink User Service API.

Provides CLI commands for listing, creating, updating, deleting, and querying users.
All commands use Click for robust CLI interfaces and error handling.
"""

import json
import re
import sys
from typing import Optional

import click

from .utils import (
    ExitCodes,
    format_success,
    get_base_url,
    handle_api_error,
    make_api_request,
)


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
            # Display statements table
            click.echo("┌" + "─" * 30 + "┬" + "─" * 20 + "┬" + "─" * 25 + "┐")
            click.echo(f"│ {'Actions':<28} │ {'Resources':<18} │ {'Workspace':<23} │")
            click.echo("├" + "─" * 30 + "┼" + "─" * 20 + "┼" + "─" * 25 + "┤")

            for statement in statements:
                actions = statement.get("actions", [])
                resources = statement.get("resource", [])
                workspace = statement.get("workspace", "")
                description = statement.get("description", "")

                # Format actions (truncate if too long)
                actions_str = ", ".join(actions)[:28]
                if len(", ".join(actions)) > 28:
                    actions_str = actions_str[:25] + "..."

                # Format resources (truncate if too long)
                resources_str = ", ".join(resources)[:18]
                if len(", ".join(resources)) > 18:
                    resources_str = resources_str[:15] + "..."

                # Format workspace (truncate if too long)
                workspace_str = workspace[:23]
                if len(workspace) > 23:
                    workspace_str = workspace[:20] + "..."

                click.echo(f"│ {actions_str:<28} │ {resources_str:<18} │ {workspace_str:<23} │")

                # Show description if available
                if description:
                    click.echo(
                        f"│ Description: {description[:50]:<50}{'│' if len(description) <= 50 else '...│'}"
                    )

            click.echo("└" + "─" * 30 + "┴" + "─" * 20 + "┴" + "─" * 25 + "┘")
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
            click.echo(f"  Workspace: {workspace}")


def register_user_commands(cli):
    """Register CLI commands for managing SystemLink users."""

    @cli.group()
    def user():
        """Manage SystemLink users."""
        pass

    @user.command(name="list")
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"], case_sensitive=False),
        default="table",
        show_default=True,
        help="Output format: table or json",
    )
    @click.option(
        "--filter",
        help=(
            "Dynamic LINQ filter for users "
            '(e.g., \'firstName.StartsWith("John") && status == "active"\')'
        ),
    )
    @click.option(
        "--take",
        default=50,
        show_default=True,
        help="Maximum number of users to return",
    )
    @click.option(
        "--sortby",
        type=click.Choice(["firstName", "lastName", "email", "niuaId", "login", "status"]),
        default="lastName",
        show_default=True,
        help="Field to sort by",
    )
    @click.option(
        "--order",
        type=click.Choice(["ascending", "descending"]),
        default="ascending",
        show_default=True,
        help="Sort order",
    )
    def list_users(
        format: str = "table",
        filter: Optional[str] = None,
        take: int = 50,
        sortby: str = "lastName",
        order: str = "ascending",
    ):
        """List users with optional filtering and sorting."""
        url = f"{get_base_url()}/niuser/v1/users/query"

        # Build query payload
        payload = {
            "take": min(take, 100),  # API maximum is 100
            "sortby": sortby,
            "order": order,
        }

        if filter:
            payload["filter"] = filter

        try:
            resp = make_api_request("POST", url, payload=payload)
            data = resp.json()
            users = data.get("users", [])

            if format.lower() == "json":
                # For JSON output, show all results without pagination
                all_users = users.copy()
                continuation_token = data.get("continuationToken")

                while continuation_token:
                    next_payload = payload.copy()
                    next_payload["continuationToken"] = continuation_token

                    next_resp = make_api_request("POST", url, payload=next_payload)
                    next_data = next_resp.json()
                    all_users.extend(next_data.get("users", []))
                    continuation_token = next_data.get("continuationToken")

                click.echo(json.dumps(all_users, indent=2))
                return

            # Table format with pagination
            if not users:
                click.echo("No users found.")
                return

            # Display table header
            click.echo("┌" + "─" * 32 + "┬" + "─" * 32 + "┬" + "─" * 40 + "┬" + "─" * 12 + "┐")
            click.echo(
                f"│ {'First Name':<30} │ {'Last Name':<30} │ {'Email':<38} │ {'Status':<10} │"
            )
            click.echo("├" + "─" * 32 + "┼" + "─" * 32 + "┼" + "─" * 40 + "┼" + "─" * 12 + "┤")

            for user in users:
                first_name = user.get("firstName", "")[:30]
                last_name = user.get("lastName", "")[:30]
                email = user.get("email", "")[:38]
                status = user.get("status", "")[:10]

                click.echo(f"│ {first_name:<30} │ {last_name:<30} │ {email:<38} │ {status:<10} │")

            click.echo("└" + "─" * 32 + "┴" + "─" * 32 + "┴" + "─" * 40 + "┴" + "─" * 12 + "┘")
            click.echo(f"\nTotal: {len(users)} user(s) shown")

            # Handle pagination for table output
            continuation_token = data.get("continuationToken")
            while continuation_token:
                if not click.confirm(f"Show next {take} users?", default=True):
                    break

                next_payload = payload.copy()
                next_payload["continuationToken"] = continuation_token

                next_resp = make_api_request("POST", url, payload=next_payload)
                next_data = next_resp.json()
                next_users = next_data.get("users", [])

                if not next_users:
                    click.echo("No more users found.")
                    break

                # Display next page
                click.echo()
                click.echo("┌" + "─" * 32 + "┬" + "─" * 32 + "┬" + "─" * 40 + "┬" + "─" * 12 + "┐")
                click.echo(
                    f"│ {'First Name':<30} │ {'Last Name':<30} │ {'Email':<38} │ {'Status':<10} │"
                )
                click.echo("├" + "─" * 32 + "┼" + "─" * 32 + "┼" + "─" * 40 + "┼" + "─" * 12 + "┤")

                for user in next_users:
                    first_name = user.get("firstName", "")[:30]
                    last_name = user.get("lastName", "")[:30]
                    email = user.get("email", "")[:38]
                    status = user.get("status", "")[:10]

                    click.echo(
                        f"│ {first_name:<30} │ {last_name:<30} │ {email:<38} │ {status:<10} │"
                    )

                click.echo("└" + "─" * 32 + "┴" + "─" * 32 + "┴" + "─" * 40 + "┴" + "─" * 12 + "┘")
                click.echo(f"\nTotal: {len(next_users)} user(s) shown")

                continuation_token = next_data.get("continuationToken")

        except Exception as exc:
            handle_api_error(exc)

    @user.command(name="get")
    @click.option("--id", "user_id", help="User ID to retrieve")
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
    ):
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
            click.echo("User Details:")
            click.echo("=" * 50)
            click.echo(f"ID: {user.get('id', 'N/A')}")
            click.echo(f"First Name: {user.get('firstName', 'N/A')}")
            click.echo(f"Last Name: {user.get('lastName', 'N/A')}")
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
    @click.option("--first-name", help="User's first name")
    @click.option("--last-name", help="User's last name")
    @click.option("--email", help="User's email address")
    @click.option("--niua-id", help="User's NIUA ID")
    @click.option("--accepted-tos", is_flag=True, help="Whether user has accepted terms of service")
    @click.option(
        "--policies",
        help="Comma-separated list of policy IDs to assign to the user",
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
        first_name: Optional[str] = None,
        last_name: Optional[str] = None,
        email: Optional[str] = None,
        niua_id: Optional[str] = None,
        accepted_tos: bool = False,
        policies: Optional[str] = None,
        keywords: Optional[str] = None,
        properties: Optional[str] = None,
    ):
        """Create a new user.

        If niuaId is not provided, it will default to the email address.
        Required fields (first name, last name, email) will be prompted for if not provided.
        """
        # Prompt for required fields if not provided
        if not first_name:
            first_name = click.prompt("User's first name", type=str)

        if not last_name:
            last_name = click.prompt("User's last name", type=str)

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
        payload = {
            "firstName": first_name,
            "lastName": last_name,
            "email": email,
            "niuaId": niua_id,
            "acceptedToS": accepted_tos,
        }

        if policies:
            payload["policies"] = [p.strip() for p in policies.split(",")]

        if keywords:
            payload["keywords"] = [k.strip() for k in keywords.split(",")]

        if properties:
            try:
                payload["properties"] = json.loads(properties)
            except json.JSONDecodeError:
                click.echo("✗ Invalid JSON format for properties.", err=True)
                sys.exit(ExitCodes.INVALID_INPUT)

        try:
            resp = make_api_request("POST", url, payload=payload)
            user = resp.json()
            format_success("User created", {"ID": user.get("id"), "Email": user.get("email")})

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
    @click.option("--id", "user_id", required=True, help="User ID to update")
    @click.option("--first-name", help="User's first name")
    @click.option("--last-name", help="User's last name")
    @click.option("--email", help="User's email address")
    @click.option(
        "--accepted-tos",
        type=click.Choice(["true", "false"]),
        help="Whether user has accepted terms of service",
    )
    @click.option(
        "--policies",
        help="Comma-separated list of policy IDs to assign to the user",
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
        accepted_tos: Optional[str] = None,
        policies: Optional[str] = None,
        keywords: Optional[str] = None,
        properties: Optional[str] = None,
    ):
        """Update an existing user."""
        url = f"{get_base_url()}/niuser/v1/users/{user_id}"

        # Build update payload (only include provided fields)
        payload = {}

        if first_name:
            payload["firstName"] = first_name

        if last_name:
            payload["lastName"] = last_name

        if email:
            payload["email"] = email

        if accepted_tos:
            payload["acceptedToS"] = accepted_tos.lower() == "true"

        if policies:
            payload["policies"] = [p.strip() for p in policies.split(",")]

        if keywords:
            payload["keywords"] = [k.strip() for k in keywords.split(",")]

        if properties:
            try:
                payload["properties"] = json.loads(properties)
            except json.JSONDecodeError:
                click.echo("✗ Invalid JSON format for properties.", err=True)
                sys.exit(ExitCodes.INVALID_INPUT)

        if not payload:
            click.echo("✗ No fields provided to update.", err=True)
            sys.exit(ExitCodes.INVALID_INPUT)

        try:
            resp = make_api_request("PUT", url, payload=payload)
            user = resp.json()
            format_success("User updated", {"ID": user.get("id"), "Email": user.get("email")})

        except Exception as exc:
            handle_api_error(exc)

    @user.command(name="delete")
    @click.option("--id", "user_id", required=True, help="User ID to delete")
    @click.confirmation_option(
        prompt="Are you sure you want to delete this user? This action cannot be undone."
    )
    def delete_user(user_id: str):
        """Delete a user by ID."""
        url = f"{get_base_url()}/niuser/v1/users/{user_id}"

        try:
            make_api_request("DELETE", url, payload=None)
            format_success("User deleted", {"ID": user_id})

        except Exception as exc:
            handle_api_error(exc)
