"""CLI commands for managing slcli configuration and profiles."""

import getpass
import json
import re
import sys
from typing import Any, Optional
from urllib.parse import urlparse

import click
import questionary

from .platform import (
    PLATFORM_SLE,
    PLATFORM_SLS,
    check_service_status,
)
from .profiles import ProfileConfig, Profile, check_config_file_permissions
from .rich_output import render_table
from .table_utils import output_formatted_list
from .utils import ExitCodes

API_KEY_LENGTH = 42
API_KEY_PATTERN = re.compile(rf"^[A-Za-z0-9_-]{{{API_KEY_LENGTH}}}$")


def _exit_with_validation_error(message: str, exit_code: int = ExitCodes.INVALID_INPUT) -> None:
    """Exit the command with a consistent validation message."""
    click.echo(f"✗ {message}", err=True)
    sys.exit(exit_code)


def _normalize_profile_name(profile: str) -> str:
    """Normalize and validate a profile name."""
    normalized = profile.strip()
    if not normalized:
        _exit_with_validation_error("Profile name cannot be empty.")
    return normalized


def _normalize_base_url(raw_url: str, label: str) -> str:
    """Normalize and validate a SystemLink base URL."""
    normalized = raw_url.strip()
    if not normalized:
        _exit_with_validation_error(f"{label} cannot be empty.")

    if "://" not in normalized:
        click.echo(f"⚠️  Warning: Adding HTTPS protocol to {label.lower()}.")
        normalized = f"https://{normalized}"

    parsed = urlparse(normalized)
    if parsed.scheme not in ("http", "https"):
        _exit_with_validation_error(f"{label} must use HTTP or HTTPS.")
    if not parsed.hostname:
        _exit_with_validation_error(f"{label} must include a valid host name.")
    if parsed.path and parsed.path.strip("/"):
        _exit_with_validation_error(
            f"{label} must be a base URL without a path, query string, or fragment."
        )
    if parsed.params or parsed.query or parsed.fragment:
        _exit_with_validation_error(
            f"{label} must be a base URL without a path, query string, or fragment."
        )

    return normalized.rstrip("/")


def _normalize_api_key(api_key: str) -> str:
    """Normalize and validate an API key before probing the server."""
    normalized = api_key.strip()
    if not normalized:
        _exit_with_validation_error("API key cannot be empty.")
    if any(character.isspace() for character in normalized):
        _exit_with_validation_error("API key must not contain spaces or line breaks.")
    if not API_KEY_PATTERN.fullmatch(normalized):
        _exit_with_validation_error(
            f"API key must be a {API_KEY_LENGTH}-character URL-safe token containing only "
            "letters, digits, '-' and '_'."
        )
    return normalized


def _all_service_probes_unauthorized(services: dict[str, str]) -> bool:
    """Return True only when every recorded service probe failed with authorization."""
    return bool(services) and all(status == "unauthorized" for status in services.values())


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
    profile = _normalize_profile_name(profile)

    # Get URL - either from flag or prompt
    if not url:
        click.echo("Example: https://api.my-systemlink.com")
        url = click.prompt("Enter your SystemLink API URL")
    assert isinstance(url, str)
    url = _normalize_base_url(url, "SystemLink API URL")

    # Get API key - either from flag or prompt
    if not api_key:
        api_key = getpass.getpass("Enter your SystemLink API key: ")
    assert isinstance(api_key, str)
    api_key = _normalize_api_key(api_key)

    # Normalize and validate web_url (prompt if not provided)
    if not web_url:
        click.echo("Example: https://my-systemlink.com")
        web_url = click.prompt("Enter your SystemLink Web UI URL")
    assert isinstance(web_url, str)
    web_url = _normalize_base_url(web_url, "SystemLink Web UI URL")

    # Detect platform type and check service status
    click.echo("Checking server connectivity and services...")
    status = check_service_status(url, api_key)
    platform = status["platform"]
    services = status.get("services", {})

    if not status["server_reachable"]:
        _exit_with_validation_error(
            "Could not connect to the SystemLink server. Verify the URL and network access. "
            "Profile was not saved.",
            ExitCodes.NETWORK_ERROR,
        )

    if status["auth_valid"] is False and _all_service_probes_unauthorized(services):
        _exit_with_validation_error(
            "API key validation failed. The server responded, but the key was not authorized. "
            "Profile was not saved.",
            ExitCodes.PERMISSION_DENIED,
        )

    if status["auth_valid"] is not True:
        _exit_with_validation_error(
            "Connected to the server, but profile verification was inconclusive. Check the "
            "API URL, API key, and service availability. Profile was not saved.",
            ExitCodes.GENERAL_ERROR,
        )

    click.echo("  Connection: ✓ Verified")
    if platform == PLATFORM_SLE:
        click.echo("  Platform: SystemLink Enterprise (Cloud)")
    elif platform == PLATFORM_SLS:
        click.echo("  Platform: SystemLink Server (On-Premises)")
    else:
        click.echo("  Platform: Unknown (will attempt all features)")

    click.echo("  API key:  ✓ Authorized")

    if status.get("file_query_endpoint") == "query-files":
        click.echo("  File query: query-files")
    elif status.get("elasticsearch_available") is False:
        click.echo("  File query: query-files-linq (Elasticsearch unavailable)")
        click.echo(
            "      'slcli file list' will fall back automatically; 'slcli file query' requires search-files."
        )

    problem_services = [
        name for name, svc_status in services.items() if svc_status == "unauthorized"
    ]
    for svc_name in problem_services:
        click.echo(f"  ⚠️  {svc_name}: unauthorized", err=True)

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
        api_key=api_key,
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

        rows = [
            ["Current Profile", cfg.current_profile or "(none)"],
            ["Config File", str(ProfileConfig.get_config_path())],
        ]

        if cfg.current_profile and cfg.current_profile in cfg.profiles:
            profile = cfg.profiles[cfg.current_profile]
            rows.append(["Server", profile.server])

            if profile.web_url:
                rows.append(["Web URL", profile.web_url])

            if profile.platform:
                rows.append(["Platform", profile.platform or "Unknown"])

            if show_secrets:
                api_key_display = profile.api_key
            else:
                api_key_display = (
                    "****" + profile.api_key[-4:] if len(profile.api_key) >= 4 else "****"
                )
            rows.append(["API Key", api_key_display])

            if profile.workspace:
                rows.append(["Workspace", profile.workspace])

            if profile.readonly:
                rows.append(["Readonly", "enabled"])

        click.echo("slcli Configuration:")
        render_table(
            headers=["SETTING", "VALUE"],
            column_widths=[18, 70],
            rows=rows,
            show_total=False,
        )

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
            if not questionary.confirm(
                f"Delete profile '{name}'?",
                default=False,
            ).ask():
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
            if not questionary.confirm(
                f"Profile '{profile_name}' already exists. Overwrite?",
                default=False,
            ).ask():
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
