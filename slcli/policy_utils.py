"""Utility functions for auth policy management.

Provides helper functions for policy and policy template operations,
including formatting, validation, and API interaction helpers.
"""

from typing import Any, Dict, List, Optional, Tuple

import click

from .utils import get_base_url, make_api_request


def _fetch_policy_details(policy_id: str, handle_errors: bool = True) -> Optional[Dict[str, Any]]:
    """Fetch policy details from the Auth service.

    Args:
        policy_id: The policy ID to fetch
        handle_errors: Whether to raise exceptions on API errors

    Returns:
        Policy details dictionary, or None if not found/no permission
    """
    try:
        url = f"{get_base_url()}/niauth/v1/policies/{policy_id}"
        resp = make_api_request("GET", url, payload=None, handle_errors=handle_errors)
        return resp.json()
    except Exception:
        return None


def _fetch_template_details(
    template_id: str, handle_errors: bool = True
) -> Optional[Dict[str, Any]]:
    """Fetch policy template details from the Auth service.

    Args:
        template_id: The policy template ID to fetch
        handle_errors: Whether to raise exceptions on API errors

    Returns:
        Policy template details dictionary, or None if not found/no permission
    """
    try:
        url = f"{get_base_url()}/niauth/v1/policy-templates/{template_id}"
        resp = make_api_request("GET", url, payload=None, handle_errors=handle_errors)
        return resp.json()
    except Exception:
        return None


def _format_statements_for_display(statements: List[Dict[str, Any]]) -> str:
    """Format statements in a readable way for display.

    Args:
        statements: List of statement dictionaries from API

    Returns:
        Formatted string representation
    """
    if not statements:
        return "No statements"

    lines: List[str] = []
    for i, statement in enumerate(statements, 1):
        lines.append(f"\nStatement {i}:")

        workspace = statement.get("workspace", "N/A")
        lines.append(f"  Workspace: {workspace}")

        # Format actions
        actions = statement.get("actions", [])
        if actions:
            lines.append(f"  Actions ({len(actions)}):")
            for action in actions:
                lines.append(f"    • {action}")

        # Format resources
        resources = statement.get("resource", [])
        if resources:
            lines.append(f"  Resources ({len(resources)}):")
            for resource in resources:
                lines.append(f"    • {resource}")

        # Format description if present
        description = statement.get("description")
        if description:
            lines.append(f"  Description: {description}")

    return "\n".join(lines)


def _validate_statements(statements: List[Dict[str, Any]]) -> Tuple[bool, Optional[str]]:
    """Validate statement structure.

    Args:
        statements: List of statement dictionaries to validate

    Returns:
        Tuple of (is_valid, error_message)
    """
    if not statements:
        return False, "At least one statement is required"

    for i, stmt in enumerate(statements):
        # Validate stmt is a dictionary
        is_dict: bool = isinstance(stmt, dict)
        if not is_dict:
            return False, f"Statement {i + 1} is not a dictionary"

        # Check required fields exist and have correct types
        actions: Any = stmt.get("actions")
        resources: Any = stmt.get("resource")
        workspace: Any = stmt.get("workspace")

        # Validate actions field
        is_actions_list: bool = isinstance(actions, list)
        if not is_actions_list:
            return False, f"Statement {i + 1}: 'actions' must be a list"
        if not actions:  # Empty list check
            return False, f"Statement {i + 1}: 'actions' must not be empty"

        # Validate resources field
        is_resources_list: bool = isinstance(resources, list)
        if not is_resources_list:
            return False, f"Statement {i + 1}: 'resource' must be a list"
        if not resources:  # Empty list check
            return False, f"Statement {i + 1}: 'resource' must not be empty"

        # Validate workspace field
        is_workspace_str: bool = isinstance(workspace, str)
        if not is_workspace_str:
            return False, f"Statement {i + 1}: 'workspace' must be a string"
        if not workspace:  # Empty string check
            return False, f"Statement {i + 1}: 'workspace' must not be empty"

    return True, None


def _format_policy_list_row(policy: Dict[str, Any]) -> List[str]:
    """Format a policy for table list output.

    Args:
        policy: Policy dictionary from API

    Returns:
        List of formatted column values
    """
    policy_id = policy.get("id", "N/A")
    name = policy.get("name", "N/A")
    policy_type = policy.get("type", "N/A")
    is_builtin = policy.get("builtIn", False)
    builtin_str = "Yes" if is_builtin else "No"

    # Count statements (or show "inherited" if template-based)
    template_id = policy.get("templateId")
    if template_id:
        statement_count = "(inherited)"
    else:
        statements = policy.get("statements", [])
        statement_count = str(len(statements))

    return [policy_id, name, policy_type, builtin_str, statement_count]


def _format_template_list_row(template: Dict[str, Any]) -> List[str]:
    """Format a template for table list output.

    Args:
        template: Policy template dictionary from API

    Returns:
        List of formatted column values
    """
    template_id = template.get("id", "N/A")
    name = template.get("name", "N/A")
    template_type = template.get("type", "N/A")
    is_builtin = template.get("builtIn", False)
    builtin_str = "Yes" if is_builtin else "No"

    statements = template.get("statements", [])
    statement_count = str(len(statements))

    return [template_id, name, template_type, builtin_str, statement_count]


def _parse_properties_from_cli(properties: tuple) -> Dict[str, str]:
    """Parse key=value properties from CLI arguments.

    Args:
        properties: Tuple of "key=value" strings

    Returns:
        Dictionary of parsed properties

    Raises:
        ValueError: If format is invalid
    """
    props_dict: Dict[str, str] = {}
    for prop in properties:
        if "=" not in prop:
            raise ValueError(f"Invalid property format: {prop}. Use key=value")
        key, val = prop.split("=", 1)
        props_dict[key.strip()] = val.strip()
    return props_dict


def _load_statements_from_file(file_path: str) -> List[Dict[str, Any]]:
    """Load statements from a JSON file.

    Args:
        file_path: Path to JSON file containing statements

    Returns:
        List of statement dictionaries

    Raises:
        ValueError: If file cannot be read or parsed
    """
    import json

    try:
        with open(file_path, "r") as f:
            data = json.load(f)
    except FileNotFoundError:
        raise ValueError(f"File not found: {file_path}")
    except json.JSONDecodeError as e:
        raise ValueError(f"Invalid JSON in file: {e}")

    # Support both direct statements list or wrapped in "statements" key
    if isinstance(data, list):
        return data
    elif isinstance(data, dict) and "statements" in data:
        statements = data["statements"]
        if not isinstance(statements, list):
            raise ValueError('"statements" field must be a list')
        return statements
    else:
        raise ValueError('File must contain a list of statements or a "statements" key')


def _build_policy_payload(
    name: str,
    policy_type: str,
    statements: Optional[List[Dict[str, Any]]] = None,
    template_id: Optional[str] = None,
    workspace: Optional[str] = None,
    properties: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Build a policy creation/update payload.

    Args:
        name: Policy name
        policy_type: Policy type (default|internal|custom|role)
        statements: List of statement dictionaries (optional if template_id used)
        template_id: Policy template ID (optional)
        workspace: Workspace ID (required if template_id used)
        properties: Custom properties dictionary

    Returns:
        Policy payload for API request

    Raises:
        ValueError: If required fields are missing
    """
    payload: Dict[str, Any] = {
        "name": name,
        "type": policy_type,
    }

    if template_id:
        if not workspace:
            raise ValueError("workspace is required when using a template")
        payload["templateId"] = template_id
        payload["workspace"] = workspace
    else:
        if not statements:
            raise ValueError("statements are required if template_id is not used")
        is_valid, error_msg = _validate_statements(statements)
        if not is_valid:
            raise ValueError(error_msg)
        payload["statements"] = statements

    if properties:
        payload["properties"] = properties

    return payload


def _build_template_payload(
    name: str,
    template_type: str,
    statements: Optional[List[Dict[str, Any]]] = None,
    properties: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Build a policy template creation/update payload.

    Args:
        name: Template name
        template_type: Template type (user|service)
        statements: List of statement dictionaries
        properties: Custom properties dictionary

    Returns:
        Template payload for API request

    Raises:
        ValueError: If required fields are missing
    """
    if not statements:
        raise ValueError("statements are required for policy templates")

    is_valid, error_msg = _validate_statements(statements)
    if not is_valid:
        raise ValueError(error_msg)

    payload: Dict[str, Any] = {
        "name": name,
        "type": template_type,
        "statements": statements,
    }

    if properties:
        payload["properties"] = properties

    return payload


def _display_policy_details(policy: Dict[str, Any], format_output: str = "table") -> None:
    """Display detailed policy information.

    Args:
        policy: Policy dictionary from API
        format_output: Output format (table or json)
    """
    import json

    if format_output.lower() == "json":
        click.echo(json.dumps(policy, indent=2))
        return

    # Table format
    click.echo(f"\n✓ Policy: {policy.get('name', 'N/A')}")
    click.echo("-" * 80)
    click.echo(f"  ID:              {policy.get('id', 'N/A')}")
    click.echo(f"  Type:            {policy.get('type', 'N/A')}")
    click.echo(f"  Built-in:        {'Yes' if policy.get('builtIn') else 'No'}")
    click.echo(f"  Owner ID:        {policy.get('userId', 'N/A')}")
    click.echo(f"  Created:         {policy.get('created', 'N/A')}")
    click.echo(f"  Updated:         {policy.get('updated', 'N/A')}")

    # Show template reference if present
    template_id = policy.get("templateId")
    if template_id:
        click.echo(f"\n  Template-based Policy:")
        click.echo(f"    Template ID:   {template_id}")
        click.echo(f"    Workspace:     {policy.get('workspace', 'N/A')}")

    # Show properties if present
    properties = policy.get("properties", {})
    if properties:
        click.echo(f"\n  Properties:")
        for key, val in properties.items():
            click.echo(f"    {key}: {val}")

    # Show statements
    statements = policy.get("statements", [])
    if statements:
        click.echo(f"\n  Statements ({len(statements)}):")
        click.echo(_format_statements_for_display(statements))

    click.echo()


def _display_template_details(template: Dict[str, Any], format_output: str = "table") -> None:
    """Display detailed template information.

    Args:
        template: Policy template dictionary from API
        format_output: Output format (table or json)
    """
    import json

    if format_output.lower() == "json":
        click.echo(json.dumps(template, indent=2))
        return

    # Table format
    click.echo(f"\n✓ Policy Template: {template.get('name', 'N/A')}")
    click.echo("-" * 80)
    click.echo(f"  ID:              {template.get('id', 'N/A')}")
    click.echo(f"  Type:            {template.get('type', 'N/A')}")
    click.echo(f"  Built-in:        {'Yes' if template.get('builtIn') else 'No'}")
    click.echo(f"  Owner ID:        {template.get('userId', 'N/A')}")
    click.echo(f"  Created:         {template.get('created', 'N/A')}")
    click.echo(f"  Updated:         {template.get('updated', 'N/A')}")

    # Show properties if present
    properties = template.get("properties", {})
    if properties:
        click.echo(f"\n  Properties:")
        for key, val in properties.items():
            click.echo(f"    {key}: {val}")

    # Show statements
    statements = template.get("statements", [])
    if statements:
        click.echo(f"\n  Statements ({len(statements)}):")
        click.echo(_format_statements_for_display(statements))

    click.echo()
