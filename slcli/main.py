"""slcli entry points."""

import getpass
import json
from pathlib import Path
from typing import Optional

import click
import keyring
import tomllib

from .completion_click import register_completion_command
from .config_click import register_config_commands
from .dff_click import register_dff_commands
from .example_click import register_example_commands
from .feed_click import register_feed_commands
from .file_click import register_file_commands
from .function_click import register_function_commands
from .notebook_click import register_notebook_commands
from .platform import (
    PLATFORM_SLE,
    PLATFORM_SLS,
    PLATFORM_UNKNOWN,
    detect_platform,
    get_platform_info,
)
from .policy_click import register_policy_commands
from .profiles import set_profile_override
from .ssl_trust import OS_TRUST_INJECTED, OS_TRUST_REASON
from .tag_click import register_tag_commands
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
@click.option(
    "--profile",
    "-p",
    envvar="SLCLI_PROFILE",
    help="Use a specific profile for this command",
)
@click.pass_context
def cli(ctx: click.Context, version: bool, profile: Optional[str]) -> None:
    """SystemLink CLI for managing SystemLink resources."""  # noqa: D403
    if version:
        click.echo(f"slcli version {get_version()}")
        ctx.exit()

    # Set profile override if specified (applies to all subcommands)
    if profile:
        set_profile_override(profile)

    # Check for mandatory migration BEFORE any command runs
    # Skip migration check only for version flag and config migrate command
    if ctx.invoked_subcommand not in (None, "config"):
        from .profiles import ProfileConfig, has_keyring_credentials, migrate_from_keyring

        config_path = ProfileConfig.get_config_path()
        if not config_path.exists() and has_keyring_credentials():
            click.echo("⚠️  Migration Required")
            click.echo("")
            click.echo("slcli now uses profile-based configuration.")
            click.echo("Existing keyring credentials detected and will be migrated to:")
            click.echo(f"  {config_path}")
            click.echo("")
            click.echo("Migrating credentials...")

            try:
                migrated_profile = migrate_from_keyring(profile_name="default", delete_keyring=True)
                if migrated_profile:
                    click.echo(f"✓ Migrated credentials to profile 'default'")
                    click.echo(f"  Server: {migrated_profile.server}")
                    if migrated_profile.web_url:
                        click.echo(f"  Web URL: {migrated_profile.web_url}")
                    if migrated_profile.platform:
                        click.echo(f"  Platform: {migrated_profile.platform}")
                    click.echo("✓ Deleted keyring entries")
                    click.echo("")
                    click.echo("Migration complete! Continuing with your command...")
                    click.echo("")
                else:
                    click.echo(
                        "✗ Migration failed: No valid credentials found in keyring.", err=True
                    )
                    ctx.exit(1)
            except Exception as e:
                click.echo(f"✗ Migration failed: {e}", err=True)
                click.echo("Run 'slcli config migrate' to try again.", err=True)
                ctx.exit(1)

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
@click.option("--profile", "-p", help="Profile name (default: 'default')")
@click.option("--url", help="SystemLink API URL")
@click.option("--api-key", help="SystemLink API key")
@click.option("--web-url", help="SystemLink Web UI base URL")
@click.option("--workspace", "-w", help="Default workspace for this profile")
@click.option(
    "--set-current/--no-set-current",
    default=True,
    help="Set as current profile (default: yes)",
)
def login(
    profile: Optional[str],
    url: Optional[str],
    api_key: Optional[str],
    web_url: Optional[str],
    workspace: Optional[str],
    set_current: bool,
) -> None:
    """Save SystemLink credentials to a profile.

    Profiles allow you to configure multiple SystemLink environments and switch
    between them. Credentials are stored in ~/.config/slcli/config.json.

    Examples:
        slcli login --profile dev
        slcli login -p prod --url https://prod-api.example.com
        slcli login --profile test --workspace "Testing"
    """
    from .profiles import Profile, ProfileConfig

    # Get profile name
    if not profile:
        profile = click.prompt("Profile name", default="default")
    assert isinstance(profile, str)

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

    # Detect platform type
    click.echo("Detecting platform type...")
    platform = detect_platform(url, api_key.strip())

    if platform == PLATFORM_SLE:
        click.echo("  Platform: SystemLink Enterprise (Cloud)")
    elif platform == PLATFORM_SLS:
        click.echo("  Platform: SystemLink Server (On-Premises)")
    else:
        click.echo("  Platform: Unknown (will attempt all features)")

    # Get default workspace (optional)
    if workspace is None:
        workspace_input = click.prompt(
            "Default workspace (optional, press Enter to skip)", default="", show_default=False
        )
        workspace = workspace_input if workspace_input else None

    # Create profile
    new_profile = Profile(
        name=profile,
        server=url,
        api_key=api_key.strip(),
        web_url=web_url,
        platform=platform,
        workspace=workspace,
    )

    # Load config and add profile
    cfg = ProfileConfig.load()
    cfg.add_profile(new_profile, set_current=set_current)
    cfg.save()

    click.echo(f"\n✓ Profile '{profile}' saved successfully.")
    click.echo(f"  Server: {url}")
    click.echo(f"  Web URL: {web_url}")
    if workspace:
        click.echo(f"  Default workspace: {workspace}")
    if set_current:
        click.echo(f"  Set as current profile: yes")
    click.echo(f"\nConfig file: {ProfileConfig.get_config_path()}")


@cli.command()
@click.option("--profile", "-p", help="Profile to remove (default: current profile)")
@click.option("--all", "remove_all", is_flag=True, help="Remove all profiles")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation prompt")
def logout(profile: Optional[str], remove_all: bool, force: bool) -> None:
    """Remove stored SystemLink credentials.

    By default, removes the current profile. Use --profile to remove a specific
    profile, or --all to remove all profiles.

    Also cleans up any legacy keyring entries.
    """
    from .profiles import ProfileConfig

    cfg = ProfileConfig.load()

    if remove_all:
        if not force:
            if not click.confirm("Remove all profiles and legacy keyring entries?"):
                click.echo("Aborted.")
                return

        # Clear all profiles
        cfg.profiles.clear()
        cfg.current_profile = None
        cfg.save()
        click.echo("✓ All profiles removed.")

    elif profile:
        # Remove specific profile
        if profile not in cfg.profiles:
            click.echo(f"✗ Profile '{profile}' not found.", err=True)
            return

        if not force:
            if not click.confirm(f"Remove profile '{profile}'?"):
                click.echo("Aborted.")
                return

        cfg.delete_profile(profile)
        cfg.save()
        click.echo(f"✓ Profile '{profile}' removed.")

    else:
        # Remove current profile
        if not cfg.current_profile:
            click.echo("No current profile set.", err=True)
            return

        current = cfg.current_profile
        if not force:
            if not click.confirm(f"Remove current profile '{current}'?"):
                click.echo("Aborted.")
                return

        cfg.delete_profile(current)
        cfg.save()
        click.echo(f"✓ Profile '{current}' removed.")
        if cfg.current_profile:
            click.echo(f"  Current profile is now: {cfg.current_profile}")

    # Also clean up legacy keyring entries
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


@cli.command()
@click.option("--format", "-f", type=click.Choice(["table", "json"]), default="table")
def info(format: str) -> None:
    """Show current configuration and detected platform."""
    from .profiles import ProfileConfig, get_active_profile

    platform_info = get_platform_info()

    # Add profile information
    cfg = ProfileConfig.load()
    active_profile = get_active_profile()
    platform_info["current_profile"] = cfg.current_profile
    platform_info["profile_count"] = len(cfg.profiles)
    if active_profile:
        platform_info["active_profile_workspace"] = active_profile.workspace
        platform_info["active_profile_name"] = active_profile.name

    if format == "json":
        click.echo(json.dumps(platform_info, indent=2))
        return

    # Table format using box-drawing characters for key-value display.
    # Note: This uses a custom layout rather than table_utils because table_utils
    # is designed for list-style output (multiple uniform rows), while this command
    # displays a single record with key-value pairs and feature availability.
    # All text fields are truncated to prevent formatting issues with long values.
    max_value_width = 45  # Maximum width for values before truncation
    content_width = 61  # Total width inside the box

    def truncate(value: str, max_len: int = max_value_width) -> str:
        """Truncate a string with ellipsis if it exceeds max length."""
        if len(value) > max_len:
            return value[: max_len - 3] + "..."
        return value

    click.echo("\n┌" + "─" * content_width + "┐")
    click.echo("│" + "SystemLink CLI Info".center(content_width) + "│")
    click.echo("├" + "─" * content_width + "┤")

    # Connection status
    status = "✓ Connected" if platform_info["logged_in"] else "✗ Not logged in"
    click.echo(f"│  Status:    {status:<48}│")

    # Profile information
    profile_display = platform_info.get("active_profile_name", "None")
    if platform_info.get("profile_count", 0) > 1:
        profile_display = f"{profile_display} (1 of {platform_info['profile_count']})"
    profile_display = truncate(profile_display)
    click.echo(f"│  Profile:   {profile_display:<48}│")

    # Platform
    platform_display = truncate(platform_info.get("platform_display", "Unknown"))
    click.echo(f"│  Platform:  {platform_display:<48}│")

    # API URL
    api_url = truncate(platform_info.get("api_url", "Not configured"))
    click.echo(f"│  API URL:   {api_url:<48}│")

    # Web URL
    web_url = truncate(platform_info.get("web_url", "Not configured"))
    click.echo(f"│  Web URL:   {web_url:<48}│")

    # Default workspace
    workspace = platform_info.get("active_profile_workspace")
    if workspace:
        workspace_display = truncate(workspace)
        click.echo(f"│  Workspace: {workspace_display:<48}│")

    click.echo("├" + "─" * content_width + "┤")
    click.echo("│" + "Feature Availability".center(content_width) + "│")
    click.echo("├" + "─" * content_width + "┤")

    features = platform_info.get("features", {})
    if features:
        for feature_name, available in features.items():
            status_icon = "✓" if available else "✗"
            status_text = "Available" if available else "Not available"
            # Truncate feature name if needed
            display_name = truncate(feature_name, 29)
            click.echo(f"│  {status_icon} {display_name:<30} {status_text:<26}│")
    else:
        if platform_info["platform"] == PLATFORM_UNKNOWN:
            click.echo("│  Run 'slcli login' to detect platform features.            │")
        else:
            click.echo("│  No feature information available.                          │")

    click.echo("└" + "─" * content_width + "┘\n")


register_completion_command(cli)
register_dff_commands(cli)
register_config_commands(cli)
register_example_commands(cli)
register_feed_commands(cli)
register_file_commands(cli)
register_function_commands(cli)
register_templates_commands(cli)
register_notebook_commands(cli)
register_policy_commands(cli)
register_tag_commands(cli)
register_webapp_commands(cli)
register_user_commands(cli)
register_workflows_commands(cli)
register_workspace_commands(cli)
