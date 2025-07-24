"""slcli entry points."""

import getpass

import click
import keyring

from .notebook_click import register_notebook_commands
from .templates_click import register_templates_commands
from .workflows_click import register_workflows_commands


CONTEXT_SETTINGS = dict(help_option_names=["-h", "--help"])


@click.group(context_settings=CONTEXT_SETTINGS, invoke_without_command=True)
@click.pass_context
def cli(ctx):
    """Top level of SystemLink Integrator CLI."""
    if ctx.invoked_subcommand is None:
        click.echo(ctx.get_help())


@cli.command()
def login():
    """Store your SystemLink API key and URL securely."""
    api_key = getpass.getpass("Enter your SystemLink API key: ")
    if not api_key.strip():
        click.echo("API key cannot be empty.")
        raise click.ClickException("API key cannot be empty.")
    url = click.prompt(
        "Enter your SystemLink API URL",
        default="http://demo-api.lifecyclesolutions.ni.com",
    )
    if not url.strip():
        click.echo("SystemLink URL cannot be empty.")
        raise click.ClickException("SystemLink URL cannot be empty.")
    keyring.set_password("systemlink-cli", "SYSTEMLINK_API_KEY", api_key.strip())
    keyring.set_password("systemlink-cli", "SYSTEMLINK_API_URL", url.strip())
    click.echo("API key and URL stored securely.")


@cli.command()
def logout():
    """Remove your stored SystemLink API key and URL from keyring."""
    try:
        keyring.delete_password("systemlink-cli", "SYSTEMLINK_API_KEY")
    except Exception:
        pass
    try:
        keyring.delete_password("systemlink-cli", "SYSTEMLINK_API_URL")
    except Exception:
        pass
    click.echo("API key and URL removed from system keyring.")


register_templates_commands(cli)
register_notebook_commands(cli)
register_workflows_commands(cli)
