"""CLI commands for managing example configurations."""

import sys
from typing import Any, Optional

import click

from .example_loader import ExampleLoader
from .universal_handlers import UniversalResponseHandler, FilteredResponse
from .utils import ExitCodes, format_success, handle_api_error


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
                import json

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
                import json

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
