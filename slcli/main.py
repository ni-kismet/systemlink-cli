"""slcli entry points."""

import json
import tomllib
from pathlib import Path
from types import ModuleType
from typing import Optional

import click as base_click
import keyring
import questionary

from .asset_click import register_asset_commands
from .comment_click import register_comment_commands
from .completion_click import register_completion_command
from .config_click import register_config_commands
from .dataframe_click import register_dataframe_commands
from .dff_click import register_dff_commands
from .example_click import register_example_commands
from .feed_click import register_feed_commands
from .file_click import register_file_commands
from .function_click import register_function_commands
from .mcp_click import register_mcp_commands
from .notebook_click import register_notebook_commands
from .platform import get_platform_info
from .policy_click import register_policy_commands
from .profiles import set_profile_override
from .rich_output import install_rich_output, render_table
from .routine_click import register_routine_commands
from .skill_click import register_skill_commands
from .spec_click import register_spec_commands
from .ssl_trust import OS_TRUST_INJECTED, OS_TRUST_REASON
from .state_click import register_state_commands
from .system_click import register_system_commands
from .tag_click import register_tag_commands
from .templates_click import register_templates_commands
from .testmonitor_click import register_testmonitor_commands
from .user_click import register_user_commands
from .webapp_click import register_webapp_commands
from .workitem_click import register_workitem_commands
from .workspace_click import register_workspace_commands

click: ModuleType
try:
    import rich_click as rich_click_module  # type: ignore[import-not-found]
except ModuleNotFoundError:
    click = base_click
else:
    click = rich_click_module


def _configure_rich_click_command_groups() -> None:
    """Configure top-level help command groups when rich-click is available."""
    rich_click_config = getattr(click, "rich_click", None)
    if rich_click_config is None:
        return

    # Keep the command-name/help split consistent across top-level panels so
    # descriptions start at the same column in every group.
    rich_click_config.STYLE_COMMANDS_TABLE_EXPAND = True
    rich_click_config.STYLE_COMMANDS_TABLE_COLUMN_WIDTH_RATIO = (1, 5)

    rich_click_config.COMMAND_GROUPS = {
        "slcli": [
            {
                "name": "Configure",
                "commands": ["config", "login", "logout", "info", "completion"],
            },
            {
                "name": "Administer",
                "commands": ["auth", "user", "workspace"],
            },
            {
                "name": "Operate",
                "commands": [
                    "asset",
                    "system",
                    "state",
                    "tag",
                    "file",
                    "feed",
                    "comment",
                    "dataframe",
                ],
            },
            {
                "name": "Build & Automate",
                "commands": ["notebook", "routine", "webapp", "customfield", "skill", "mcp"],
            },
            {
                "name": "Validate & Plan",
                "commands": ["testmonitor", "template", "spec", "workitem", "example"],
            },
        ]
    }


_configure_rich_click_command_groups()


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
def cli(ctx: base_click.Context, version: bool, profile: Optional[str]) -> None:
    """SystemLink CLI for managing SystemLink resources."""  # noqa: D403
    install_rich_output()

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
@click.option(
    "--readonly",
    is_flag=True,
    help=(
        "Enable readonly mode (disables create, update, delete, import, upload, "
        "publish, and disable commands)"
    ),
)
def login(
    profile: Optional[str],
    url: Optional[str],
    api_key: Optional[str],
    web_url: Optional[str],
    workspace: Optional[str],
    set_current: bool,
    readonly: bool,
) -> None:
    """Create or update a SystemLink profile with credentials.

    This is an alias for 'slcli config add'. Use that command
    for the same functionality and more configuration options.

    Profiles allow you to configure multiple SystemLink environments and switch
    between them. Credentials are stored in ~/.config/slcli/config.json.

    Examples:
        slcli login --profile dev
        slcli login -p prod --url https://prod-api.example.com
        slcli login --profile test --workspace "Testing" --readonly
    """
    from .config_click import _add_profile_impl

    # Invoke the shared implementation
    _add_profile_impl(
        profile=profile,
        url=url,
        api_key=api_key,
        web_url=web_url,
        workspace=workspace,
        set_current=set_current,
        readonly=readonly,
    )


@cli.command()
@click.option("--profile", "-p", help="Profile to remove (default: current profile)")
@click.option("--all", "remove_all", is_flag=True, help="Remove all profiles")
@click.option("--force", "-f", is_flag=True, help="Skip confirmation prompt")
def logout(profile: Optional[str], remove_all: bool, force: bool) -> None:
    """Remove stored SystemLink profiles and credentials.

    By default, removes the current profile. Use --profile to remove a specific
    profile, or --all to remove all profiles.

    Also cleans up any legacy keyring entries.
    """
    from .profiles import ProfileConfig

    cfg = ProfileConfig.load()

    if remove_all:
        if not force:
            if not questionary.confirm(
                "Remove all profiles and legacy keyring entries?",
                default=False,
            ).ask():
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
            if not questionary.confirm(
                f"Remove profile '{profile}'?",
                default=False,
            ).ask():
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
            if not questionary.confirm(
                f"Remove current profile '{current}'?",
                default=False,
            ).ask():
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
@click.option("--skip-health", is_flag=True, default=False, help="Skip live service health checks.")
def info(format: str, skip_health: bool) -> None:
    """Show the active profile, configuration, and platform status."""
    from .profiles import ProfileConfig, get_active_profile

    platform_info = get_platform_info(skip_health=skip_health)

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

    max_value_width = 45  # Maximum width for values before truncation

    def truncate(value: str, max_len: int = max_value_width) -> str:
        """Truncate a string with ellipsis if it exceeds max length."""
        if len(value) > max_len:
            return value[: max_len - 3] + "..."
        return value

    if not platform_info["logged_in"]:
        status = "✗ Not logged in"
    elif platform_info.get("server_reachable") is False:
        status = "✗ Server unreachable"
    elif platform_info.get("auth_valid") is False:
        status = "✗ API key unauthorized"
    else:
        status = "✓ Connected"

    profile_display = platform_info.get("active_profile_name", "None")
    if platform_info.get("profile_count", 0) > 1:
        profile_display = f"{profile_display} (1 of {platform_info['profile_count']})"
    profile_display = truncate(profile_display)
    platform_display = truncate(platform_info.get("platform_display", "Unknown"))
    api_url = truncate(platform_info.get("api_url", "Not configured"))
    web_url = truncate(platform_info.get("web_url", "Not configured"))

    info_rows = [
        ["Status", status],
        ["Profile", profile_display],
        ["Platform", platform_display],
        ["API URL", api_url],
        ["Web URL", web_url],
    ]

    workspace = platform_info.get("active_profile_workspace")
    if workspace:
        workspace_display = truncate(workspace)
        info_rows.append(["Workspace", workspace_display])

    system_query_endpoint = platform_info.get("system_query_endpoint")
    if system_query_endpoint:
        system_query_display = truncate(str(system_query_endpoint))
        info_rows.append(["System Query", system_query_display])

    file_query_endpoint = platform_info.get("file_query_endpoint")
    if file_query_endpoint:
        if (
            file_query_endpoint == "query-files-linq"
            and platform_info.get("elasticsearch_available") is False
        ):
            file_query_display = f"{file_query_endpoint} (Elasticsearch unavailable)"
        else:
            file_query_display = str(file_query_endpoint)
        file_query_display = truncate(file_query_display)
        info_rows.append(["File Query", file_query_display])

    click.echo()
    click.echo("SystemLink CLI Info:")
    render_table(
        headers=["SETTING", "VALUE"],
        column_widths=[16, 48],
        rows=info_rows,
        show_total=False,
    )

    services = platform_info.get("services")
    if services:
        status_display = {
            "ok": ("✓", "OK"),
            "fallback": ("!", "Fallback (no Elasticsearch)"),
            "unauthorized": ("✗", "Unauthorized"),
            "not_found": ("—", "Not available"),
            "error": ("✗", "Error"),
            "unreachable": ("✗", "Unreachable"),
        }
        service_rows = []
        for svc_name, svc_status in services.items():
            icon, text = status_display.get(svc_status, ("?", svc_status))
            service_rows.append([truncate(svc_name, 29), f"{icon} {text}"])

        click.echo()
        click.echo("Service Health:")
        render_table(
            headers=["SERVICE", "STATUS"],
            column_widths=[26, 32],
            rows=service_rows,
            show_total=False,
        )
        click.echo()


register_completion_command(cli)
register_asset_commands(cli)
register_comment_commands(cli)
register_dataframe_commands(cli)
register_dff_commands(cli)
register_config_commands(cli)
register_example_commands(cli)
register_feed_commands(cli)
register_file_commands(cli)
register_function_commands(cli)
register_mcp_commands(cli)
register_templates_commands(cli)
register_notebook_commands(cli)
register_policy_commands(cli)
register_routine_commands(cli)
register_state_commands(cli)
register_system_commands(cli)
register_spec_commands(cli)
register_tag_commands(cli)
register_testmonitor_commands(cli)
register_webapp_commands(cli)
register_skill_commands(cli)
register_user_commands(cli)
register_workitem_commands(cli)
register_workspace_commands(cli)
