"""slcli entry points."""

import getpass
import os

import click
import keyring

from .templates_click import register_templates_commands

CONTEXT_SETTINGS = dict(help_option_names=["-h", "--help"])


def get_ssl_verify():
    """Return SSL verification setting from environment variable, default True."""
    env = os.environ.get("SLCLI_SSL_VERIFY")
    if env is not None:
        return env.lower() not in ("0", "false", "no")
    return True


def get_base_url():
    """Retrieve the SystemLink API base URL from environment or keyring."""
    url = os.environ.get("SYSTEMLINK_API_URL")
    if not url:
        url = keyring.get_password("systemlink-cli", "SYSTEMLINK_API_URL")
    return url or "http://localhost:8000"


def get_api_key():
    """Retrieve the SystemLink API key from environment or keyring."""
    api_key = os.environ.get("SYSTEMLINK_API_KEY")
    if not api_key:
        api_key = keyring.get_password("systemlink-cli", "SYSTEMLINK_API_KEY")
    if not api_key:
        click.echo(
            "Error: API key not found. Please set the SYSTEMLINK_API_KEY "
            "environment variable or run 'slcli login'."
        )
        raise click.ClickException("API key not found.")
    return api_key


def get_headers():
    """Return headers for SystemLink API requests."""
    return {
        "x-ni-api-key": get_api_key(),
        "Content-Type": "application/json",
    }


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
