"""CLI commands for managing SystemLink auth policies and policy templates."""

import sys
from typing import Any, Dict, List, Optional

import click

from .cli_utils import validate_output_format
from .policy_utils import (
    _build_policy_payload,
    _display_policy_details,
    _display_template_details,
    _fetch_policy_details,
    _fetch_template_details,
    _format_policy_list_row,
    _format_template_list_row,
    _parse_properties_from_cli,
)
from .universal_handlers import FilteredResponse, UniversalResponseHandler
from .utils import (
    ExitCodes,
    format_success,
    get_base_url,
    handle_api_error,
    make_api_request,
)


def register_policy_commands(cli: Any) -> None:
    """Register the 'policy' command group and its subcommands."""

    @cli.group(name="auth")
    def auth() -> None:
        """Manage SystemLink auth policies and policy templates."""
        pass

    @auth.group(name="policy")
    def policy_group() -> None:
        """Manage authorization policies."""
        pass

    @auth.group(name="template")
    def template_group() -> None:
        """Manage policy templates."""
        pass

    @policy_group.command(name="list")
    @click.option(
        "--type",
        "policy_type",
        type=click.Choice(["default", "internal", "custom", "role"], case_sensitive=False),
        default=None,
        help="Filter by policy type",
    )
    @click.option("--builtin", is_flag=True, help="Show built-in policies only")
    @click.option("--name", type=str, default=None, help="Filter by name (contains search)")
    @click.option(
        "--sortby",
        type=click.Choice(["name", "created", "updated"]),
        default="name",
        show_default=True,
        help="Sort field",
    )
    @click.option(
        "--order",
        type=click.Choice(["asc", "desc"]),
        default="asc",
        show_default=True,
        help="Sort order",
    )
    @click.option(
        "--take",
        "-t",
        type=int,
        default=None,
        help="Limit results (default: 25 for table, all for JSON)",
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
        "--skip",
        "-s",
        type=int,
        default=0,
        show_default=True,
        help="Number of items to skip before returning results",
    )
    def list_policies(
        policy_type: Optional[str],
        builtin: bool,
        name: Optional[str],
        sortby: str,
        order: str,
        take: Optional[int],
        format: str,
        skip: int,
    ) -> None:
        """List policies with optional filtering."""
        validate_output_format(format)

        try:
            from urllib.parse import urlencode

            if take is None:
                take = 25 if format == "table" else 100

            base_url = f"{get_base_url()}/niauth/v1/policies"

            def build_url(page_take: int, page_skip: int) -> str:
                query_params: Dict[str, Any] = {
                    "take": page_take,
                    "skip": page_skip,
                    "sortby": sortby,
                    "order": "ascending" if order == "asc" else "descending",
                }
                if policy_type:
                    query_params["type"] = policy_type.lower()
                if builtin:
                    query_params["builtIn"] = "true"
                if name:
                    query_params["name"] = f"*{name}*"
                return f"{base_url}?{urlencode(query_params)}"

            if format == "json":
                import json

                all_policies: List[Dict[str, Any]] = []
                current_skip = skip
                remaining = take

                while True:
                    page_take = min(remaining, 100) if remaining else 100
                    url = build_url(page_take, current_skip)
                    resp = make_api_request("GET", url, payload=None)
                    data = resp.json()
                    policies_page = data.get("policies", [])

                    if not policies_page:
                        break

                    all_policies.extend(policies_page)

                    if remaining:
                        if len(all_policies) >= remaining:
                            all_policies = all_policies[:remaining]
                            break
                        remaining -= len(policies_page)

                    if len(policies_page) < page_take:
                        break

                    current_skip += page_take

                click.echo(json.dumps(all_policies, indent=2) if all_policies else "[]")
                return

            current_skip = skip

            while True:
                url = build_url(take, current_skip)
                resp = make_api_request("GET", url, payload=None)
                data = resp.json()
                policies = data.get("policies", [])
                total_count = data.get("totalCount")

                if not policies and current_skip == skip:
                    click.echo("No policies found.")
                    return
                if not policies:
                    break

                combined_resp = FilteredResponse({"policies": policies})
                UniversalResponseHandler.handle_list_response(
                    resp=combined_resp,
                    data_key="policies",
                    item_name="policy",
                    format_output=format,
                    formatter_func=_format_policy_list_row,
                    headers=["ID", "Name", "Type", "Built-in", "Statements"],
                    column_widths=[36, 30, 12, 10, 15],
                    enable_pagination=False,
                    page_size=take,
                )

                if total_count is not None:
                    shown = current_skip + len(policies)
                    remaining = max(total_count - shown, 0)
                    message = f"Showing {len(policies)} of {total_count} policy(ies)."
                    if remaining:
                        message += f" {remaining} more available."
                    click.echo(message)

                current_skip += take

                if len(policies) < take:
                    break

                try:
                    is_tty = sys.stdout.isatty() and sys.stdin.isatty()
                except Exception:
                    is_tty = False

                if not is_tty:
                    break
                if not click.confirm(f"Show next {take} policies?", default=True):
                    break

        except Exception as exc:
            handle_api_error(exc)

    @policy_group.command(name="get")
    @click.argument("policy_id")
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    def get_policy(policy_id: str, format: str) -> None:
        """Get policy details."""
        validate_output_format(format)

        try:
            url = f"{get_base_url()}/niauth/v1/policies/{policy_id}"
            resp = make_api_request("GET", url, payload=None)
            _display_policy_details(resp.json(), format)
        except Exception as exc:
            handle_api_error(exc)

    @policy_group.command(name="create")
    @click.argument("template_id")
    @click.option("--name", required=True, help="Name for the new policy")
    @click.option("--workspace", required=True, help="Target workspace ID")
    @click.option(
        "--properties",
        "-p",
        type=str,
        multiple=True,
        help="Custom properties as key=value (repeatable)",
    )
    def create_policy(template_id: str, name: str, workspace: str, properties: tuple) -> None:
        """Create a new policy from a template scoped to a workspace."""
        from .utils import check_readonly_mode

        check_readonly_mode("create a policy")

        try:
            properties_dict = _parse_properties_from_cli(properties) if properties else None

            payload = _build_policy_payload(
                name=name,
                policy_type="custom",
                statements=None,
                template_id=template_id,
                workspace=workspace,
                properties=properties_dict,
            )

            url = f"{get_base_url()}/niauth/v1/policies"
            resp = make_api_request("POST", url, payload=payload)
            created_policy = resp.json()

            format_success(
                "Policy created from template",
                {
                    "name": created_policy.get("name"),
                    "id": created_policy.get("id"),
                    "type": created_policy.get("type"),
                },
            )
        except ValueError as e:
            click.echo(f"✗ Error: {str(e)}", err=True)
            sys.exit(ExitCodes.INVALID_INPUT)
        except Exception as exc:
            handle_api_error(exc)

    @policy_group.command(name="update")
    @click.argument("policy_id")
    @click.option("--name", type=str, default=None, help="New policy name")
    @click.option(
        "--template",
        "template_id",
        type=str,
        default=None,
        help="Policy template ID to apply or reapply",
    )
    @click.option(
        "--workspace",
        type=str,
        default=None,
        help="Workspace ID (required when applying a template)",
    )
    @click.option(
        "--properties",
        "-p",
        type=str,
        multiple=True,
        help="Updated custom properties as key=value (repeatable)",
    )
    def update_policy(
        policy_id: str,
        name: Optional[str],
        template_id: Optional[str],
        workspace: Optional[str],
        properties: tuple,
    ) -> None:
        """Update an existing policy, optionally applying a new template."""
        from .utils import check_readonly_mode

        check_readonly_mode("update a policy")

        try:
            url = f"{get_base_url()}/niauth/v1/policies/{policy_id}"
            current_resp = make_api_request("GET", url, payload=None)
            current_policy = current_resp.json()

            properties_dict = (
                _parse_properties_from_cli(properties)
                if properties
                else current_policy.get("properties")
            )

            # If template is provided, use template; otherwise keep current statements
            statements_list = None
            if not template_id:
                statements_list = current_policy.get("statements")

            # Use provided workspace or current workspace
            effective_workspace = workspace or current_policy.get("workspace")

            payload = _build_policy_payload(
                name=name or current_policy.get("name"),
                policy_type=current_policy.get("type"),
                statements=statements_list,
                template_id=template_id or current_policy.get("templateId"),
                workspace=effective_workspace,
                properties=properties_dict,
            )

            resp = make_api_request("PUT", url, payload=payload)
            updated_policy = resp.json()

            format_success(
                "Policy updated",
                {
                    "name": updated_policy.get("name"),
                    "id": updated_policy.get("id"),
                    "type": updated_policy.get("type"),
                },
            )
        except ValueError as e:
            click.echo(f"✗ Error: {str(e)}", err=True)
            sys.exit(ExitCodes.INVALID_INPUT)
        except Exception as exc:
            handle_api_error(exc)

    @policy_group.command(name="delete")
    @click.argument("policy_id")
    @click.option("--force", is_flag=True, help="Skip confirmation prompt")
    def delete_policy(policy_id: str, force: bool) -> None:
        """Delete a policy."""
        from .utils import check_readonly_mode

        check_readonly_mode("delete a policy")

        try:
            if not force:
                details = _fetch_policy_details(policy_id, handle_errors=False)
                policy_name = details.get("name") if details else policy_id
                if not click.confirm(f"Delete policy '{policy_name}'?", default=False):
                    click.echo("Deletion cancelled.")
                    return

            url = f"{get_base_url()}/niauth/v1/policies/{policy_id}"
            resp = make_api_request("DELETE", url, payload=None)
            if resp.status_code not in (200, 204):
                resp.raise_for_status()

            format_success("Policy deleted", {"id": policy_id})
        except Exception as exc:
            handle_api_error(exc)

    @policy_group.command(name="diff")
    @click.argument("policy_id_1")
    @click.argument("policy_id_2")
    def diff_policies(policy_id_1: str, policy_id_2: str) -> None:
        """Show a basic diff between two policies."""
        try:
            url1 = f"{get_base_url()}/niauth/v1/policies/{policy_id_1}"
            url2 = f"{get_base_url()}/niauth/v1/policies/{policy_id_2}"
            resp1 = make_api_request("GET", url1, payload=None)
            resp2 = make_api_request("GET", url2, payload=None)
            p1 = resp1.json()
            p2 = resp2.json()

            def set_from_list(lst: Any) -> set:
                return set(lst or [])

            click.echo("\nPolicy Diff")
            click.echo("-" * 80)
            click.echo(f"Name: {p1.get('name','')}  vs  {p2.get('name','')}")
            click.echo(f"Type: {p1.get('type','')}  vs  {p2.get('type','')}")
            click.echo(f"Built-in: {p1.get('builtIn',False)}  vs  {p2.get('builtIn',False)}")
            click.echo(f"Workspace: {p1.get('workspace','N/A')}  vs  {p2.get('workspace','N/A')}")

            s1 = p1.get("statements", [])
            s2 = p2.get("statements", [])
            click.echo(f"\nStatements: {len(s1)}  vs  {len(s2)}")

            # Aggregate actions/resources/workspaces for quick comparison
            def aggregate(parts: List[Dict[str, Any]]) -> Dict[str, set]:
                act: set = set()
                res: set = set()
                ws: set = set()
                for st in parts:
                    act |= set_from_list(st.get("actions"))
                    res |= set_from_list(st.get("resource"))
                    w = st.get("workspace")
                    if w:
                        ws.add(w)
                return {"actions": act, "resources": res, "workspaces": ws}

            agg1 = aggregate(s1)
            agg2 = aggregate(s2)

            def show_set_diff(label: str, a: set, b: set) -> None:
                only_a = sorted(a - b)
                only_b = sorted(b - a)
                click.echo(f"\n{label} differences:")
                if not only_a and not only_b:
                    click.echo("  No differences")
                    return
                if only_a:
                    click.echo("  Only in policy 1:")
                    for item in only_a:
                        click.echo(f"    • {item}")
                if only_b:
                    click.echo("  Only in policy 2:")
                    for item in only_b:
                        click.echo(f"    • {item}")

            show_set_diff("Actions", agg1["actions"], agg2["actions"])
            show_set_diff("Resources", agg1["resources"], agg2["resources"])
            show_set_diff("Workspaces", agg1["workspaces"], agg2["workspaces"])

        except Exception as exc:
            handle_api_error(exc)

    @template_group.command(name="list")
    @click.option(
        "--type",
        "template_type",
        type=click.Choice(["user", "service"], case_sensitive=False),
        default=None,
        help="Filter by template type",
    )
    @click.option("--builtin", is_flag=True, help="Show built-in templates only")
    @click.option("--name", type=str, default=None, help="Filter by name (contains search)")
    @click.option(
        "--sortby",
        type=click.Choice(["name", "created", "updated"]),
        default="name",
        show_default=True,
        help="Sort field",
    )
    @click.option(
        "--order",
        type=click.Choice(["asc", "desc"]),
        default="asc",
        show_default=True,
        help="Sort order",
    )
    @click.option(
        "--take",
        "-t",
        type=int,
        default=None,
        help="Limit results (default: 25 for table, all for JSON)",
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
        "--skip",
        "-s",
        type=int,
        default=0,
        show_default=True,
        help="Number of items to skip before returning results",
    )
    def list_templates(
        template_type: Optional[str],
        builtin: bool,
        name: Optional[str],
        sortby: str,
        order: str,
        take: Optional[int],
        format: str,
        skip: int,
    ) -> None:
        """List policy templates with optional filtering."""
        validate_output_format(format)

        try:
            from urllib.parse import urlencode

            if take is None:
                take = 25 if format == "table" else 100

            base_url = f"{get_base_url()}/niauth/v1/policy-templates"

            def build_url(page_take: int, page_skip: int) -> str:
                query_params: Dict[str, Any] = {
                    "take": page_take,
                    "skip": page_skip,
                    "sortby": sortby,
                    "order": "ascending" if order == "asc" else "descending",
                }
                if template_type:
                    query_params["type"] = template_type.lower()
                if builtin:
                    query_params["builtIn"] = "true"
                if name:
                    query_params["name"] = f"*{name}*"
                return f"{base_url}?{urlencode(query_params)}"

            if format == "json":
                import json

                all_templates: List[Dict[str, Any]] = []
                current_skip = skip
                remaining = take

                while True:
                    page_take = min(remaining, 100) if remaining else 100
                    url = build_url(page_take, current_skip)
                    resp = make_api_request("GET", url, payload=None)
                    data = resp.json()
                    templates_page = data.get("policyTemplates", [])

                    if not templates_page:
                        break

                    all_templates.extend(templates_page)

                    if remaining:
                        if len(all_templates) >= remaining:
                            all_templates = all_templates[:remaining]
                            break
                        remaining -= len(templates_page)

                    if len(templates_page) < page_take:
                        break

                    current_skip += page_take

                click.echo(json.dumps(all_templates, indent=2) if all_templates else "[]")
                return

            current_skip = skip

            while True:
                url = build_url(take, current_skip)
                resp = make_api_request("GET", url, payload=None)
                data = resp.json()
                templates = data.get("policyTemplates", [])
                total_count = data.get("totalCount")

                if not templates and current_skip == skip:
                    click.echo("No policy templates found.")
                    return
                if not templates:
                    break

                combined_resp = FilteredResponse({"policyTemplates": templates})
                UniversalResponseHandler.handle_list_response(
                    resp=combined_resp,
                    data_key="policyTemplates",
                    item_name="template",
                    format_output=format,
                    formatter_func=_format_template_list_row,
                    headers=["ID", "Name", "Type", "Built-in", "Statements"],
                    column_widths=[36, 30, 12, 10, 15],
                    enable_pagination=False,
                    page_size=take,
                )

                if total_count is not None:
                    shown = current_skip + len(templates)
                    remaining = max(total_count - shown, 0)
                    message = f"Showing {len(templates)} of {total_count} policy template(s)."
                    if remaining:
                        message += f" {remaining} more available."
                    click.echo(message)

                current_skip += take

                if len(templates) < take:
                    break

                try:
                    is_tty = sys.stdout.isatty() and sys.stdin.isatty()
                except Exception:
                    is_tty = False

                if not is_tty:
                    break
                if not click.confirm(f"Show next {take} templates?", default=True):
                    break

        except Exception as exc:
            handle_api_error(exc)

    @template_group.command(name="get")
    @click.argument("template_id")
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    def get_template(template_id: str, format: str) -> None:
        """Get policy template details."""
        validate_output_format(format)

        try:
            url = f"{get_base_url()}/niauth/v1/policy-templates/{template_id}"
            resp = make_api_request("GET", url, payload=None)
            _display_template_details(resp.json(), format)
        except Exception as exc:
            handle_api_error(exc)

    @template_group.command(name="delete")
    @click.argument("template_id")
    @click.option("--force", is_flag=True, help="Skip confirmation prompt")
    def delete_template(template_id: str, force: bool) -> None:
        """Delete a policy template."""
        from .utils import check_readonly_mode

        check_readonly_mode("delete a policy template")

        try:
            if not force:
                details = _fetch_template_details(template_id, handle_errors=False)
                template_name = details.get("name") if details else template_id
                if not click.confirm(f"Delete policy template '{template_name}'?", default=False):
                    click.echo("Deletion cancelled.")
                    return

            url = f"{get_base_url()}/niauth/v1/policy-templates/{template_id}"
            resp = make_api_request("DELETE", url, payload=None)
            if resp.status_code not in (200, 204):
                resp.raise_for_status()

            format_success("Policy template deleted", {"id": template_id})
        except Exception as exc:
            handle_api_error(exc)
