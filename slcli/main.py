"""slcli entry points."""

import getpass
from pathlib import Path

import click
import keyring
import tomllib

from .completion_click import register_completion_command
from .dff_click import register_dff_commands
from .function_click import register_function_commands
from .notebook_click import register_notebook_commands
from .ssl_trust import OS_TRUST_INJECTED, OS_TRUST_REASON
from .templates_click import register_templates_commands
from .user_click import register_user_commands
from .workflows_click import register_workflows_commands
from .workspace_click import register_workspace_commands


def get_version() -> str:
    """Get version from _version.py (built binary) or pyproject.toml (development)."""
    try:
        # Try to import from _version.py first (works in built binary)
        from ._version import __version__

        return __version__
    except ImportError:
        # Fall back to reading pyproject.toml (works in development)
        try:
            current_dir = Path(__file__).parent
            pyproject_path = current_dir.parent / "pyproject.toml"

            with open(pyproject_path, "rb") as f:
                pyproject_data = tomllib.load(f)

            return pyproject_data["tool"]["poetry"]["version"]
        except Exception:
            return "unknown"


CONTEXT_SETTINGS = dict(help_option_names=["-h", "--help"])


def get_ascii_art() -> str:
    """Return ASCII art for SystemLink CLI."""
    return """
 ███████╗██╗   ██╗███████╗████████╗███████╗███╗   ███╗██╗     ██╗███╗   ██╗██╗  ██╗     ██████╗██╗     ██╗
 ██╔════╝╚██╗ ██╔╝██╔════╝╚══██╔══╝██╔════╝████╗ ████║██║     ██║████╗  ██║██║ ██╔╝    ██╔════╝██║     ██║
 ███████╗ ╚████╔╝ ███████╗   ██║   █████╗  ██╔████╔██║██║     ██║██╔██╗ ██║█████╔╝     ██║     ██║     ██║
 ╚════██║  ╚██╔╝  ╚════██║   ██║   ██╔══╝  ██║╚██╔╝██║██║     ██║██║╚██╗██║██╔═██╗     ██║     ██║     ██║
 ███████║   ██║   ███████║   ██║   ███████╗██║ ╚═╝ ██║███████╗██║██║ ╚████║██║  ██╗    ╚██████╗███████╗██║
 ╚══════╝   ╚═╝   ╚══════╝   ╚═╝   ╚══════╝╚═╝     ╚═╝╚══════╝╚═╝╚═╝  ╚═══╝╚═╝  ╚═╝     ╚═════╝╚══════╝╚═╝
"""


@click.group(context_settings=CONTEXT_SETTINGS, invoke_without_command=True)
@click.option("--version", "-v", is_flag=True, help="Show version and exit")
@click.pass_context
def cli(ctx, version):
    """SystemLink CLI (slcli) - Command-line interface for SystemLink resources."""  # noqa: D403
    if version:
        click.echo(f"slcli version {get_version()}")
        ctx.exit()
    if ctx.invoked_subcommand is None:
        click.echo(get_ascii_art())
        click.echo(ctx.get_help())


@cli.command(hidden=True, name="_ca-info")
def ca_info() -> None:  # type: ignore
    """Show TLS CA trust source (hidden diagnostic)."""
    if OS_TRUST_INJECTED:
        click.echo(f"CA Source: system (reason={OS_TRUST_REASON})")
    else:
        # Determine if custom verify path set via env
        import os

        verify_env = os.environ.get("REQUESTS_CA_BUNDLE") or os.environ.get("SSL_CERT_FILE")
        if verify_env:
            click.echo(f"CA Source: custom-pem ({verify_env})")
        else:
            click.echo(f"CA Source: certifi (reason={OS_TRUST_REASON})")


@cli.command()
@click.option("--url", help="SystemLink API URL")
@click.option("--api-key", help="SystemLink API key")
def login(url, api_key):
    """Store your SystemLink API key and URL securely."""
    # Get URL - either from flag or prompt
    if not url:
        url = click.prompt(
            "Enter your SystemLink API URL",
            default="https://demo-api.lifecyclesolutions.ni.com",
        )
    if not url.strip():
        click.echo("SystemLink URL cannot be empty.")
        raise click.ClickException("SystemLink URL cannot be empty.")

    # Ensure URL uses HTTPS
    url = url.strip()
    if url.startswith("http://"):
        click.echo("⚠️  Warning: Converting HTTP to HTTPS for security.")
        url = url.replace("http://", "https://", 1)
    elif not url.startswith("https://"):
        click.echo("⚠️  Warning: Adding HTTPS protocol to URL.")
        url = f"https://{url}"

    # Get API key - either from flag or prompt
    if not api_key:
        api_key = getpass.getpass("Enter your SystemLink API key: ")
    if not api_key.strip():
        click.echo("API key cannot be empty.")
        raise click.ClickException("API key cannot be empty.")

    keyring.set_password("systemlink-cli", "SYSTEMLINK_API_KEY", api_key.strip())
    keyring.set_password("systemlink-cli", "SYSTEMLINK_API_URL", url)
    click.echo("API key and URL stored securely.")


@cli.command()
def logout():
    """Remove your stored SystemLink API key and URL."""
    try:
        keyring.delete_password("systemlink-cli", "SYSTEMLINK_API_KEY")
    except Exception:
        pass
    try:
        keyring.delete_password("systemlink-cli", "SYSTEMLINK_API_URL")
    except Exception:
        pass
    click.echo("API key and URL removed from system keyring.")


register_completion_command(cli)
register_dff_commands(cli)
register_function_commands(cli)
register_templates_commands(cli)
register_notebook_commands(cli)
register_user_commands(cli)
register_workflows_commands(cli)
register_workspace_commands(cli)
