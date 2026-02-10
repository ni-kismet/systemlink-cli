"""CLI commands for managing slcli configuration and profiles."""

import getpass
import json
import sys
from typing import Any, Optional

import click

from .platform import PLATFORM_SLE, PLATFORM_SLS, detect_platform
from .profiles import ProfileConfig, Profile, check_config_file_permissions
from .table_utils import output_formatted_list
from .utils import ExitCodes


def _add_profile_impl(
    profile: Optional[str],
    url: Optional[str],
    api_key: Optional[str],
    web_url: Optional[str],
    workspace: Optional[str],
    set_current: bool,
    readonly: bool,
) -> None:
    """Shared implementation for add-profile and login commands.

    This function contains the common logic for both the config add-profile
    and login commands. Both commands invoke this function with the same parameters.

    Args:
        profile: Profile name (default: 'default')
        url: SystemLink API URL
        api_key: SystemLink API key
        web_url: SystemLink Web UI base URL
        workspace: Default workspace for this profile
        set_current: Whether to set as the current profile
        readonly: Whether to enable readonly mode
    """
    # Get profile name
    if not profile:
        profile = click.prompt("Profile name", default="default")
    assert isinstance(profile, str)

    # Get URL - either from flag or prompt
    if not url:
        click.echo("Example: https://api.my-systemlink.com")
        url = click.prompt("Enter your SystemLink API URL")
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
        click.echo("Example: https://my-systemlink.com")
        web_url = click.prompt("Enter your SystemLink Web UI URL")
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
        readonly=readonly,
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
    if readonly:
        click.echo(f"  Readonly mode: enabled (mutation operations disabled)")
    if set_current:
        click.echo(f"  Set as current profile: yes")
    click.echo(f"\nConfig file: {ProfileConfig.get_config_path()}")


def register_config_commands(cli: Any) -> None:
    """Register the 'config' command group and its subcommands."""

    @cli.group()
    def config() -> None:
        """Manage slcli configuration and profiles.

        Profiles allow you to configure multiple SystemLink environments
        (dev, test, prod) and switch between them easily.
        """
        pass

    @config.command(name="list")
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"]),
        default="table",
        help="Output format",
    )
    @click.option(
        "--take",
        "-t",
        type=int,
        default=25,
        show_default=True,
        help="Maximum number of profiles to display per page",
    )
    def list_profiles(format: str, take: int) -> None:
        """List all configured profiles."""
        cfg = ProfileConfig.load()
        profiles = cfg.list_profiles()

        if format == "json":
            output = []
            for p in profiles:
                item = {
                    "name": p.name,
                    "server": p.server,
                    "current": p.name == cfg.current_profile,
                }
                if p.web_url:
                    item["web-url"] = p.web_url
                if p.platform:
                    item["platform"] = p.platform
                if p.workspace:
                    item["workspace"] = p.workspace
                if p.readonly:
                    item["readonly"] = p.readonly
                output.append(item)
            click.echo(json.dumps(output, indent=2))
            return

        if not profiles:
            click.echo("No profiles configured.")
            click.echo("\nRun 'slcli login --profile <name>' to create a profile.")
            return

        # Check for permission warning
        warning = check_config_file_permissions()
        if warning:
            click.echo(f"⚠️  {warning}\n", err=True)

        # Convert Profile objects to dictionaries for type compatibility
        from typing import Any, Dict, List

        table_items: List[Dict[str, Any]] = []
        for p in profiles:
            table_items.append(
                {
                    "name": p.name,
                    "server": p.server,
                    "workspace": p.workspace,
                    "readonly": p.readonly,
                    "is_current": p.name == cfg.current_profile,
                }
            )

        def format_row(profile_dict: Dict[str, Any]) -> List[str]:
            current = "*" if profile_dict.get("is_current") else ""
            # Truncate workspace if too long
            workspace = profile_dict.get("workspace") or "-"
            if profile_dict.get("workspace") and len(str(profile_dict["workspace"])) > 20:
                workspace = str(profile_dict["workspace"])[:17] + "..."
            # Truncate server URL if too long
            server = profile_dict["server"]
            if len(server) > 40:
                server = server[:37] + "..."
            readonly = "✓" if profile_dict.get("readonly") else ""
            return [current, profile_dict["name"], server, workspace, readonly]

        output_formatted_list(
            items=table_items,
            output_format="table",
            headers=["", "NAME", "SERVER", "WORKSPACE", "READONLY"],
            column_widths=[1, 15, 40, 20, 8],
            row_formatter_func=format_row,
            empty_message="No profiles configured.",
            total_label="profile(s)",
        )

    @config.command(name="current")
    def current_profile() -> None:
        """Show the current profile name."""
        cfg = ProfileConfig.load()

        if not cfg.current_profile:
            click.echo("No current profile set.", err=True)
            click.echo("Run 'slcli config use <name>' to set one.", err=True)
            sys.exit(ExitCodes.GENERAL_ERROR)

        click.echo(cfg.current_profile)

    @config.command(name="use")
    @click.argument("name")
    def use_profile(name: str) -> None:
        """Switch to a different profile."""
        cfg = ProfileConfig.load()

        if name not in cfg.profiles:
            click.echo(f"✗ Profile '{name}' not found.", err=True)
            if cfg.profiles:
                click.echo(f"Available profiles: {', '.join(cfg.profiles.keys())}", err=True)
            sys.exit(ExitCodes.NOT_FOUND)

        cfg.set_current_profile(name)
        cfg.save()

        profile = cfg.get_profile(name)
        click.echo(f"✓ Switched to profile '{name}'")
        if profile:
            click.echo(f"  Server: {profile.server}")
            if profile.workspace:
                click.echo(f"  Default workspace: {profile.workspace}")

    @config.command(name="view")
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"]),
        default="table",
        help="Output format",
    )
    @click.option(
        "--show-secrets",
        is_flag=True,
        help="Show API keys in output (use with caution)",
    )
    def view(format: str, show_secrets: bool) -> None:
        """View the full configuration."""
        cfg = ProfileConfig.load()

        if format == "json":
            data: dict = {}
            if cfg.current_profile:
                data["current-profile"] = cfg.current_profile
            if cfg.profiles:
                # Mask API keys unless --show-secrets is specified
                data["profiles"] = {}
                for name, profile in cfg.profiles.items():
                    profile_dict = profile.to_dict()
                    if not show_secrets and "api-key" in profile_dict:
                        # Show only last 4 characters
                        key = profile_dict["api-key"]
                        profile_dict["api-key"] = "****" + key[-4:] if len(key) >= 4 else "****"
                    data["profiles"][name] = profile_dict
            if cfg.settings:
                data.update(cfg.settings)
            click.echo(json.dumps(data, indent=2))
            return

        # Table format
        click.echo("┌─────────────────────────────────────────────────────────────┐")
        click.echo("│ slcli Configuration                                         │")
        click.echo("├─────────────────────────────────────────────────────────────┤")

        if cfg.current_profile:
            click.echo(f"│ Current Profile: {cfg.current_profile:<42} │")
        else:
            click.echo("│ Current Profile: (none)                                     │")

        config_path_str = str(ProfileConfig.get_config_path())
        if len(config_path_str) > 46:
            config_path_str = config_path_str[:43] + "..."
        click.echo(f"│ Config File: {config_path_str:<46} │")

        # Show current profile details
        if cfg.current_profile and cfg.current_profile in cfg.profiles:
            profile = cfg.profiles[cfg.current_profile]
            click.echo("├─────────────────────────────────────────────────────────────┤")

            # Server
            server_str = profile.server
            if len(server_str) > 47:
                server_str = server_str[:44] + "..."
            click.echo(f"│ Server: {server_str:<51} │")

            # Web URL
            if profile.web_url:
                web_url_str = profile.web_url
                if len(web_url_str) > 45:
                    web_url_str = web_url_str[:42] + "..."
                click.echo(f"│ Web URL: {web_url_str:<50} │")

            # Platform
            if profile.platform:
                platform_str = profile.platform or "Unknown"
                click.echo(f"│ Platform: {platform_str:<49} │")

            # API Key (redacted)
            if show_secrets:
                click.echo(f"│ API Key: {profile.api_key:<50} │")
            else:
                # Show only last 4 characters
                key = profile.api_key
                redacted_key = "****" + key[-4:] if len(key) >= 4 else "****"
                click.echo(f"│ API Key: {redacted_key:<50} │")

            # Workspace
            if profile.workspace:
                workspace_str = profile.workspace
                if len(workspace_str) > 45:
                    workspace_str = workspace_str[:42] + "..."
                click.echo(f"│ Workspace: {workspace_str:<48} │")

            # Readonly
            if profile.readonly:
                click.echo("│ Readonly: enabled                                           │")

        click.echo("└─────────────────────────────────────────────────────────────┘")

        # Check for permission warning
        warning = check_config_file_permissions()
        if warning:
            click.echo(f"\n⚠️  {warning}", err=True)

    @config.command(name="delete")
    @click.argument("name")
    @click.option("--force", "-f", is_flag=True, help="Skip confirmation prompt")
    def delete_profile(name: str, force: bool) -> None:
        """Delete a profile."""
        from .utils import check_readonly_mode

        check_readonly_mode("delete a profile")

        cfg = ProfileConfig.load()

        if name not in cfg.profiles:
            click.echo(f"✗ Profile '{name}' not found.", err=True)
            sys.exit(ExitCodes.NOT_FOUND)

        if not force:
            if not click.confirm(f"Delete profile '{name}'?"):
                click.echo("Aborted.")
                sys.exit(ExitCodes.GENERAL_ERROR)

        was_current = cfg.current_profile == name
        cfg.delete_profile(name)
        cfg.save()

        click.echo(f"✓ Profile '{name}' deleted.")
        if was_current and cfg.current_profile:
            click.echo(f"  Current profile is now: {cfg.current_profile}")

    @config.command(name="migrate")
    @click.option(
        "--profile-name",
        "-n",
        default="default",
        help="Name for the migrated profile",
    )
    @click.option(
        "--delete-keyring",
        is_flag=True,
        help="Delete keyring entries after migration",
    )
    def migrate(profile_name: str, delete_keyring: bool) -> None:
        """Migrate credentials from keyring to config file.

        This command reads existing credentials from the system keyring
        and creates a new profile in the config file.
        """
        from .profiles import migrate_from_keyring

        # Check if profile already exists
        cfg = ProfileConfig.load()
        if profile_name in cfg.profiles:
            if not click.confirm(f"Profile '{profile_name}' already exists. Overwrite?"):
                click.echo("Aborted.")
                sys.exit(ExitCodes.GENERAL_ERROR)

        # Use centralized migration function
        profile = migrate_from_keyring(profile_name=profile_name, delete_keyring=delete_keyring)

        if not profile:
            click.echo("✗ No credentials found in keyring.", err=True)
            click.echo("Run 'slcli login --profile <name>' to create a new profile.", err=True)
            sys.exit(ExitCodes.NOT_FOUND)

        click.echo(f"✓ Migrated credentials to profile '{profile_name}'")
        click.echo(f"  Server: {profile.server}")
        if profile.web_url:
            click.echo(f"  Web URL: {profile.web_url}")
        if profile.platform:
            click.echo(f"  Platform: {profile.platform}")

        if delete_keyring:
            click.echo("✓ Deleted keyring entries")
        else:
            click.echo("\nNote: Keyring entries still exist. Use --delete-keyring to remove them.")

    @config.command(name="add")
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
    @click.option(
        "--readonly",
        is_flag=True,
        help=(
            "Enable readonly mode (disables create, update, delete, import, upload, "
            "publish, and disable commands)"
        ),
    )
    def add_profile(
        profile: Optional[str],
        url: Optional[str],
        api_key: Optional[str],
        web_url: Optional[str],
        workspace: Optional[str],
        set_current: bool,
        readonly: bool,
    ) -> None:
        """Add or update a SystemLink profile.

        Profiles allow you to configure multiple SystemLink environments and switch
        between them. Credentials are stored in ~/.config/slcli/config.json.

        The readonly flag enables readonly mode, which disables all delete and edit
        commands in slcli. This is useful for AI agents or untrusted environments.

        Examples:
            slcli config add --profile dev
            slcli config add -p prod --url https://prod-api.example.com
            slcli config add --profile test --workspace "Testing" --readonly
        """
        _add_profile_impl(
            profile=profile,
            url=url,
            api_key=api_key,
            web_url=web_url,
            workspace=workspace,
            set_current=set_current,
            readonly=readonly,
        )
