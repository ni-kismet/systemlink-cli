"""CLI commands for managing slcli configuration and profiles."""

import json
import sys
from typing import Any, Optional

import click
import keyring

from .profiles import Profile, ProfileConfig, check_config_file_permissions
from .table_utils import output_formatted_list
from .utils import ExitCodes


def register_config_commands(cli: Any) -> None:
    """Register the 'config' command group and its subcommands."""

    @cli.group()
    def config() -> None:
        """Manage slcli configuration and profiles.

        Profiles allow you to configure multiple SystemLink environments
        (dev, test, prod) and switch between them easily.
        """
        pass

    @config.command(name="list-profiles")
    @click.option(
        "--format",
        "-f",
        type=click.Choice(["table", "json"]),
        default="table",
        help="Output format",
    )
    def list_profiles(format: str) -> None:
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

        def format_row(profile: Profile) -> list:
            current = "*" if profile.name == cfg.current_profile else ""
            workspace = profile.workspace or "-"
            # Truncate server URL if too long
            server = profile.server
            if len(server) > 40:
                server = server[:37] + "..."
            return [current, profile.name, server, workspace]

        output_formatted_list(
            items=profiles,  # type: ignore[arg-type]
            output_format="table",
            headers=["", "NAME", "SERVER", "WORKSPACE"],
            column_widths=[1, 15, 40, 20],
            row_formatter_func=format_row,  # type: ignore[arg-type]
            empty_message="No profiles configured.",
            total_label="profile(s)",
        )

    @config.command(name="current-profile")
    def current_profile() -> None:
        """Show the current profile name."""
        cfg = ProfileConfig.load()

        if not cfg.current_profile:
            click.echo("No current profile set.", err=True)
            click.echo("Run 'slcli config use-profile <name>' to set one.", err=True)
            sys.exit(ExitCodes.GENERAL_ERROR)

        click.echo(cfg.current_profile)

    @config.command(name="use-profile")
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
    def view(format: str) -> None:
        """View the full configuration."""
        cfg = ProfileConfig.load()

        if format == "json":
            data: dict = {}
            if cfg.current_profile:
                data["current-profile"] = cfg.current_profile
            if cfg.profiles:
                data["profiles"] = {
                    name: profile.to_dict() for name, profile in cfg.profiles.items()
                }
            if cfg.settings:
                data.update(cfg.settings)
            click.echo(json.dumps(data, indent=2))
            return

        # Table format
        click.echo("┌─────────────────────────────────────────────────────────────┐")
        click.echo("│ slcli Configuration                                         │")
        click.echo("├─────────────────────────────────────────────────────────────┤")

        if cfg.current_profile:
            click.echo(f"│ Current Profile: {cfg.current_profile:<43} │")
        else:
            click.echo("│ Current Profile: (none)                                     │")

        click.echo(f"│ Config File: {str(ProfileConfig.get_config_path()):<47} │"[:64] + "│")

        if cfg.profiles:
            click.echo("├─────────────────────────────────────────────────────────────┤")
            click.echo("│ Profiles:                                                   │")
            for name, profile in cfg.profiles.items():
                marker = " *" if name == cfg.current_profile else "  "
                click.echo(f"│{marker} {name}: {profile.server[:45]:<45} │")
                if profile.workspace:
                    click.echo(f"│      Workspace: {profile.workspace[:42]:<42} │")

        click.echo("└─────────────────────────────────────────────────────────────┘")

        # Check for permission warning
        warning = check_config_file_permissions()
        if warning:
            click.echo(f"\n⚠️  {warning}", err=True)

    @config.command(name="delete-profile")
    @click.argument("name")
    @click.option("--force", "-f", is_flag=True, help="Skip confirmation prompt")
    def delete_profile(name: str, force: bool) -> None:
        """Delete a profile."""
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
        # Try to load existing credentials from keyring
        api_url: Optional[str] = None
        api_key: Optional[str] = None
        web_url: Optional[str] = None
        platform: Optional[str] = None

        # Try combined config first
        try:
            combined = keyring.get_password("systemlink-cli", "SYSTEMLINK_CONFIG")
            if combined:
                data = json.loads(combined)
                api_url = data.get("api_url")
                api_key = data.get("api_key")
                web_url = data.get("web_url")
                platform = data.get("platform")
        except (json.JSONDecodeError, Exception):
            pass

        # Fall back to individual entries
        if not api_url:
            api_url = keyring.get_password("systemlink-cli", "SYSTEMLINK_API_URL")
        if not api_key:
            api_key = keyring.get_password("systemlink-cli", "SYSTEMLINK_API_KEY")
        if not web_url:
            web_url = keyring.get_password("systemlink-cli", "SYSTEMLINK_WEB_URL")

        if not api_url or not api_key:
            click.echo("✗ No credentials found in keyring.", err=True)
            click.echo("Run 'slcli login --profile <name>' to create a new profile.", err=True)
            sys.exit(ExitCodes.NOT_FOUND)

        # Create profile
        profile = Profile(
            name=profile_name,
            server=api_url,
            api_key=api_key,
            web_url=web_url,
            platform=platform,
        )

        # Load config and add profile
        cfg = ProfileConfig.load()

        if profile_name in cfg.profiles:
            if not click.confirm(f"Profile '{profile_name}' already exists. Overwrite?"):
                click.echo("Aborted.")
                sys.exit(ExitCodes.GENERAL_ERROR)

        cfg.add_profile(profile, set_current=True)
        cfg.save()

        click.echo(f"✓ Migrated credentials to profile '{profile_name}'")
        click.echo(f"  Server: {api_url}")
        if web_url:
            click.echo(f"  Web URL: {web_url}")
        if platform:
            click.echo(f"  Platform: {platform}")

        # Optionally delete keyring entries
        if delete_keyring:
            try:
                keyring.delete_password("systemlink-cli", "SYSTEMLINK_API_KEY")
            except Exception:
                pass
            try:
                keyring.delete_password("systemlink-cli", "SYSTEMLINK_API_URL")
            except Exception:
                pass
            try:
                keyring.delete_password("systemlink-cli", "SYSTEMLINK_WEB_URL")
            except Exception:
                pass
            try:
                keyring.delete_password("systemlink-cli", "SYSTEMLINK_CONFIG")
            except Exception:
                pass
            click.echo("✓ Deleted keyring entries")
        else:
            click.echo("\nNote: Keyring entries still exist. Use --delete-keyring to remove them.")
