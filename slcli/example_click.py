"""CLI commands for managing example configurations."""

import json
import sys
from typing import Any, Dict, List, Optional

import click

from .example_loader import ExampleLoader
from .example_provisioner import ExampleProvisioner, ProvisioningAction, ProvisioningResult
from .universal_handlers import UniversalResponseHandler, FilteredResponse
from .utils import ExitCodes, format_success, get_workspace_map, handle_api_error, save_json_file


def _resolve_workspace_id(workspace: Optional[str]) -> Optional[str]:
    """Resolve workspace name to ID using workspace map.

    Args:
        workspace: Workspace name or ID provided by the user.

    Returns:
        Workspace ID if resolved; original value if already an ID; None if not provided.
    """
    if not workspace:
        return None

    workspace_map = get_workspace_map()
    if not workspace_map:
        return workspace

    # Direct match on ID
    if workspace in workspace_map:
        return workspace

    # Match on name (case-insensitive)
    for ws_id, ws_name in workspace_map.items():
        if ws_name and workspace.lower() == str(ws_name).lower():
            return ws_id

    click.echo(f"✗ Workspace '{workspace}' not found. Provide a valid name or ID.", err=True)
    sys.exit(ExitCodes.INVALID_INPUT)


def _serialize_results(results: List[ProvisioningResult]) -> List[Dict[str, Any]]:
    """Convert provisioning results into serializable dictionaries."""
    serialized: List[Dict[str, Any]] = []
    for res in results:
        action_value = (
            res.action.value if isinstance(res.action, ProvisioningAction) else str(res.action)
        )
        serialized.append(
            {
                "id_reference": res.id_reference,
                "resource_type": res.resource_type,
                "resource_name": res.resource_name,
                "action": action_value,
                "server_id": res.server_id,
                "error": res.error,
            }
        )
    return serialized


def _result_row_formatter(item: Dict[str, Any]) -> List[str]:
    """Formatter for table rows in provisioning output."""
    return [
        item.get("resource_name", ""),
        item.get("resource_type", ""),
        item.get("action", ""),
        item.get("server_id", "") or "-",
        item.get("error", "") or "",
    ]


def _output_results(results: List[Dict[str, Any]], format_output: str) -> None:
    """Render provisioning results in the requested format."""
    UniversalResponseHandler.handle_list_response(
        resp=FilteredResponse({"resources": results}),
        data_key="resources",
        item_name="resource",
        format_output=format_output,
        formatter_func=_result_row_formatter,
        headers=["Name", "Type", "Action", "Server ID", "Error"],
        column_widths=[24, 12, 10, 38, 30],
        empty_message="No resources processed.",
        enable_pagination=False,
    )


def _write_audit_log(
    results: List[Dict[str, Any]], audit_log: Optional[str], quiet: bool = False
) -> None:
    """Persist results to an audit log file if requested."""
    if not audit_log:
        return
    save_json_file(results, audit_log)
    if not quiet:
        click.echo(f"Audit log saved to {audit_log}", err=True)


def register_example_commands(cli: Any) -> None:
    """Register example command group.

    Args:
        cli: Click CLI group to register commands on.
    """

    @cli.group()
    def example() -> None:
        """Manage example resource configurations.

        Examples help you quickly set up demo systems for training,
        testing, or evaluation. Each example includes systems, assets,
        DUTs, templates, and other resources needed for a complete workflow.

        Workspace: Uses default workspace unless --workspace specified.
        """
        pass

    @example.command(name="list")
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"]),
        default="table",
        help="Output format",
    )
    def list_examples(format: str) -> None:
        """List available example configurations.

        Shows all examples with descriptions, tags, and estimated setup time.
        """
        try:
            loader = ExampleLoader()
            examples = loader.list_examples()

            if not examples:
                if format == "json":
                    click.echo("[]")
                else:
                    click.echo("No examples available.", err=True)
                return

            if format == "json":
                # JSON: show all at once
                click.echo(json.dumps(examples, indent=2))
            else:
                # Table format without custom formatter
                UniversalResponseHandler.handle_list_response(
                    resp=FilteredResponse({"examples": examples}),
                    data_key="examples",
                    item_name="example",
                    format_output=format,
                    formatter_func=None,
                    headers=None,
                    column_widths=None,
                    enable_pagination=False,  # Unlikely to have > 25 examples
                )

        except Exception as exc:
            handle_api_error(exc)

    @example.command(name="info")
    @click.argument("example_name")
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"]),
        default="table",
        help="Output format",
    )
    def info_example(example_name: str, format: str) -> None:
        """Show detailed information about an example.

        Displays full config including resources, dependencies, and
        estimated setup time.

        Example:
            slcli example info demo-test-plans
        """
        try:
            loader = ExampleLoader()
            config = loader.load_config(example_name)

            if format == "json":
                # JSON: dump full config
                click.echo(json.dumps(config, indent=2))
            else:
                # Table format: show summary and resources
                click.echo(f"\n{'='*70}")
                click.echo(f"Example: {config['title']}")
                click.echo(f"{'='*70}")
                click.echo(f"Name:        {config.get('name', 'N/A')}")
                click.echo(f"Author:      {config.get('author', 'N/A')}")
                click.echo(f"Setup Time:  {config.get('estimated_setup_time_minutes', 0)} minutes")
                click.echo(f"Tags:        {', '.join(config.get('tags', []))}")
                click.echo()
                click.echo(f"Description:\n{config.get('description', 'N/A')}")
                click.echo()

                # Show resources
                resources = config.get("resources", [])
                click.echo(f"\nResources ({len(resources)} total):")
                click.echo("-" * 70)

                for resource in resources:
                    res_type = resource.get("type", "unknown")
                    res_name = resource.get("name", "N/A")
                    res_ref = resource.get("id_reference", "N/A")
                    click.echo(f"  {res_type:15} {res_name:30} (${{{res_ref}}})")

                click.echo(f"{'='*70}\n")

        except FileNotFoundError as e:
            click.echo(f"✗ Error: {e}", err=True)
            sys.exit(ExitCodes.NOT_FOUND)
        except ValueError as e:
            click.echo(f"✗ Error: {e}", err=True)
            sys.exit(ExitCodes.INVALID_INPUT)
        except Exception as exc:
            handle_api_error(exc)

    @example.command(name="install")
    @click.argument("example_name")
    @click.option("--workspace", "-w", help="Workspace name or ID for resources")
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"]),
        default="table",
        help="Output format for provisioning results",
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        help="Validate and preview resource creation without calling APIs.",
    )
    @click.option(
        "--audit-log",
        "-a",
        type=click.Path(dir_okay=False, writable=True, resolve_path=True),
        help="Path to write provisioning results as JSON for auditing.",
    )
    def install_example(
        example_name: str,
        workspace: Optional[str],
        format: str,
        dry_run: bool,
        audit_log: Optional[str],
    ) -> None:
        """Provision all resources defined by an example configuration."""
        try:
            loader = ExampleLoader()
            config = loader.load_config(example_name)

            workspace_id = _resolve_workspace_id(workspace)
            provisioner = ExampleProvisioner(
                workspace_id=workspace_id,
                example_name=example_name,
                dry_run=dry_run,
            )

            results, err = provisioner.provision(config)
            if err:
                handle_api_error(err)

            serialized = _serialize_results(results)
            _write_audit_log(serialized, audit_log, quiet=format == "json")
            _output_results(serialized, format)

            failed = any(r.get("action") == ProvisioningAction.FAILED.value for r in serialized)
            if failed:
                click.echo("✗ One or more resources failed to provision.", err=True)
                sys.exit(ExitCodes.GENERAL_ERROR)

            if format == "json":
                return

            created_count = sum(
                1 for r in serialized if r.get("action") == ProvisioningAction.CREATED.value
            )
            skipped_count = sum(
                1 for r in serialized if r.get("action") == ProvisioningAction.SKIPPED.value
            )

            summary_message = "Dry-run completed" if dry_run else "Example install completed"
            format_success(
                summary_message,
                {
                    "example": example_name,
                    "workspace": workspace_id or "default",
                    "created": created_count,
                    "skipped": skipped_count,
                },
            )

        except FileNotFoundError as e:
            click.echo(f"✗ Error: {e}", err=True)
            sys.exit(ExitCodes.NOT_FOUND)
        except ValueError as e:
            click.echo(f"✗ Error: {e}", err=True)
            sys.exit(ExitCodes.INVALID_INPUT)
        except Exception as exc:
            handle_api_error(exc)

    @example.command(name="delete")
    @click.argument("example_name")
    @click.option("--workspace", "-w", help="Workspace name or ID for resources")
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"]),
        default="table",
        help="Output format for deletion results",
    )
    @click.option(
        "--dry-run",
        is_flag=True,
        help="Preview deletions without calling APIs.",
    )
    @click.option(
        "--audit-log",
        "-a",
        type=click.Path(dir_okay=False, writable=True, resolve_path=True),
        help="Path to write deletion results as JSON for auditing.",
    )
    def delete_example(
        example_name: str,
        workspace: Optional[str],
        format: str,
        dry_run: bool,
        audit_log: Optional[str],
    ) -> None:
        """Delete resources for an example configuration in reverse order."""
        try:
            loader = ExampleLoader()
            config = loader.load_config(example_name)

            workspace_id = _resolve_workspace_id(workspace)
            provisioner = ExampleProvisioner(
                workspace_id=workspace_id,
                example_name=example_name,
                dry_run=dry_run,
            )

            results, err = provisioner.delete(config)
            if err:
                handle_api_error(err)

            serialized = _serialize_results(results)
            _write_audit_log(serialized, audit_log, quiet=format == "json")
            _output_results(serialized, format)

            failed = any(r.get("action") == ProvisioningAction.FAILED.value for r in serialized)
            if failed:
                click.echo("✗ One or more resources failed to delete.", err=True)
                sys.exit(ExitCodes.GENERAL_ERROR)

            if format == "json":
                return

            deleted_count = sum(
                1 for r in serialized if r.get("action") == ProvisioningAction.DELETED.value
            )
            skipped_count = sum(
                1 for r in serialized if r.get("action") == ProvisioningAction.SKIPPED.value
            )

            summary_message = "Dry-run completed" if dry_run else "Example delete completed"
            format_success(
                summary_message,
                {
                    "example": example_name,
                    "workspace": workspace_id or "default",
                    "deleted": deleted_count,
                    "skipped": skipped_count,
                },
            )

        except FileNotFoundError as e:
            click.echo(f"✗ Error: {e}", err=True)
            sys.exit(ExitCodes.NOT_FOUND)
        except ValueError as e:
            click.echo(f"✗ Error: {e}", err=True)
            sys.exit(ExitCodes.INVALID_INPUT)
        except Exception as exc:
            handle_api_error(exc)
