"""slcli entry points."""

import getpass
import json
from pathlib import Path
from typing import Optional

import click
import keyring
import tomllib

from .completion_click import register_completion_command
from .dff_click import register_dff_commands
from .function_click import register_function_commands
from .notebook_click import register_notebook_commands
from .platform import (
    PLATFORM_SLE,
    PLATFORM_SLS,
    PLATFORM_UNKNOWN,
    detect_platform,
    get_platform_info,
)
from .ssl_trust import OS_TRUST_INJECTED, OS_TRUST_REASON
from .templates_click import register_templates_commands
from .user_click import register_user_commands
from .webapp_click import register_webapp_commands
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
def cli(ctx: click.Context, version: bool) -> None:
    """SystemLink CLI (slcli) - Command-line interface for SystemLink resources."""  # noqa: D403
    if version:
        click.echo(f"slcli version {get_version()}")
        ctx.exit()
    if ctx.invoked_subcommand is None:
        click.echo(get_ascii_art())
        click.echo(ctx.get_help())


@cli.command(hidden=True, name="_ca-info")
def ca_info() -> None:
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
@click.option("--web-url", help="SystemLink Web UI base URL")
def login(url: Optional[str], api_key: Optional[str], web_url: Optional[str]) -> None:
    """Store your SystemLink API key, URL and Web UI URL securely.

    The command will always attempt to persist a combined JSON config into the
    system keyring under service 'systemlink-cli' and key 'SYSTEMLINK_CONFIG'.
    If that fails, separate legacy keyring entries are kept as a fallback.
    """
    # Get URL - either from flag or prompt
    if not url:
        url = click.prompt(
            "Enter your SystemLink API URL",
            default="https://demo-api.lifecyclesolutions.ni.com",
        )
    # Ensure url is a string now
    assert isinstance(url, str)
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
    # Ensure api_key is a string now
    assert isinstance(api_key, str)
    if not api_key.strip():
        click.echo("API key cannot be empty.")
        raise click.ClickException("API key cannot be empty.")

    keyring.set_password("systemlink-cli", "SYSTEMLINK_API_KEY", api_key.strip())
    keyring.set_password("systemlink-cli", "SYSTEMLINK_API_URL", url)
    # Normalize and validate web_url (prompt if not provided)
    if not web_url:
        web_url = click.prompt(
            "Enter your SystemLink Web UI URL", default="https://demo.lifecyclesolutions.ni.com"
        )
    assert isinstance(web_url, str)
    web_url = web_url.strip()
    if web_url.startswith("http://"):
        click.echo("⚠️  Warning: Converting HTTP to HTTPS for security.")
        web_url = web_url.replace("http://", "https://", 1)
    elif not web_url.startswith("https://"):
        click.echo("⚠️  Warning: Adding HTTPS protocol to web URL.")
        web_url = f"https://{web_url}"

    # Attempt to store a combined JSON config in keyring by default
    combined: dict = {"api_url": url, "api_key": api_key.strip(), "web_url": web_url}

    # Detect platform type
    click.echo("Detecting platform type...")
    platform = detect_platform(url, api_key.strip())
    combined["platform"] = platform

    if platform == PLATFORM_SLE:
        click.echo("  Platform: SystemLink Enterprise (Cloud)")
    elif platform == PLATFORM_SLS:
        click.echo("  Platform: SystemLink Server (On-Premises)")
    else:
        click.echo("  Platform: Unknown (will attempt all features)")

    try:
        keyring.set_password("systemlink-cli", "SYSTEMLINK_CONFIG", json.dumps(combined))
        click.echo("API key, URL and web UI URL stored securely (combined entry).")
    except Exception:
        # Fall back to separate entries if combined storage fails
        click.echo("Could not write combined config to keyring; stored API key and URL separately.")


@cli.command()
def logout() -> None:
    """Remove your stored SystemLink API key and URL."""
    try:
        keyring.delete_password("systemlink-cli", "SYSTEMLINK_API_KEY")
    except Exception:
        pass
    try:
        keyring.delete_password("systemlink-cli", "SYSTEMLINK_API_URL")
    except Exception:
        pass
    try:
        keyring.delete_password("systemlink-cli", "SYSTEMLINK_CONFIG")
    except Exception:
        pass
    click.echo("API key and URL removed from system keyring.")


@cli.command()
@click.option("--format", "-f", type=click.Choice(["table", "json"]), default="table")
def info(format: str) -> None:
    """Show current configuration and platform information."""
    platform_info = get_platform_info()

    if format == "json":
        click.echo(json.dumps(platform_info, indent=2))
        return

    # Table format
    click.echo("\n┌─────────────────────────────────────────────────────────────┐")
    click.echo("│                   SystemLink CLI Info                       │")
    click.echo("├─────────────────────────────────────────────────────────────┤")

    # Connection status
    status = "✓ Connected" if platform_info["logged_in"] else "✗ Not logged in"
    click.echo(f"│  Status:    {status:<48}│")

    # Platform
    platform_display = platform_info.get("platform_display", "Unknown")
    click.echo(f"│  Platform:  {platform_display:<48}│")

    # API URL (truncate if too long)
    api_url = platform_info.get("api_url", "Not configured")
    if len(api_url) > 45:
        api_url = api_url[:42] + "..."
    click.echo(f"│  API URL:   {api_url:<48}│")

    # Web URL (truncate if too long)
    web_url = platform_info.get("web_url", "Not configured")
    if len(web_url) > 45:
        web_url = web_url[:42] + "..."
    click.echo(f"│  Web URL:   {web_url:<48}│")

    click.echo("├─────────────────────────────────────────────────────────────┤")
    click.echo("│                      Feature Availability                   │")
    click.echo("├─────────────────────────────────────────────────────────────┤")

    features = platform_info.get("features", {})
    if features:
        for feature_name, available in features.items():
            status_icon = "✓" if available else "✗"
            status_text = "Available" if available else "Not available"
            # Truncate feature name if needed
            if len(feature_name) > 25:
                feature_name = feature_name[:22] + "..."
            click.echo(f"│  {status_icon} {feature_name:<26} {status_text:<20}│")
    else:
        if platform_info["platform"] == PLATFORM_UNKNOWN:
            click.echo("│  Run 'slcli login' to detect platform features.            │")
        else:
            click.echo("│  No feature information available.                          │")

    click.echo("└─────────────────────────────────────────────────────────────┘\n")


register_completion_command(cli)
register_dff_commands(cli)
register_function_commands(cli)
register_templates_commands(cli)
register_notebook_commands(cli)
register_webapp_commands(cli)
register_user_commands(cli)
register_workflows_commands(cli)
register_workspace_commands(cli)
