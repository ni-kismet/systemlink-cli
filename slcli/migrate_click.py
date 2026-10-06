"""CLI registration for the discovery-only ``migrate`` command.

Migration depends on the optional ``migration`` extra, so this module imports
``slcli.migration`` only when the command runs.
"""

from importlib.util import find_spec
from typing import Dict, Optional
from urllib.parse import urlparse

import click

_MIGRATION_EXTRA_PACKAGES = frozenset({"prefect", "psutil", "pydantic"})


def migration_extra_installed() -> bool:
    """Return whether the ``migration`` extra's packages are installed, without importing them."""
    return all(find_spec(package) is not None for package in _MIGRATION_EXTRA_PACKAGES)


def _parse_workspace_mappings(
    ctx: click.Context, param: click.Parameter, value: Optional[str]
) -> Optional[Dict[str, str]]:
    """Parse comma-delimited SOURCE or SOURCE:DESTINATION workspace mappings."""
    if value is None:
        return None
    mappings: Dict[str, str] = {}
    for item in value.split(","):
        source, _, destination = (part.strip() for part in item.partition(":"))
        if not source or (":" in item and not destination):
            raise click.BadParameter("workspace mappings must be SOURCE or SOURCE:DESTINATION")
        if source in mappings:
            raise click.BadParameter(f"workspace '{source}' is mapped more than once")
        mappings[source] = destination or source
    return mappings


def _validate_prefect_api_url(
    ctx: click.Context, param: click.Parameter, value: Optional[str]
) -> Optional[str]:
    if value is not None:
        parsed = urlparse(value)
        if parsed.scheme not in ("http", "https") or not parsed.netloc:
            raise click.BadParameter("must be an HTTP or HTTPS URL")
    return value


def register_migrate_command(cli: click.Group) -> None:
    """Register the discovery-only migrate command, hidden without the migration extra."""

    @cli.command(name="migrate", hidden=not migration_extra_installed())
    @click.option("--source-profile", help="Named source SystemLink profile for a new migration.")
    @click.option(
        "--workspace-mappings",
        callback=_parse_workspace_mappings,
        help=(
            "Comma-delimited SOURCE or SOURCE:DESTINATION workspace mappings. "
            "Only the listed source workspaces are discovered; all when omitted."
        ),
    )
    @click.option("--migration-id", help="Repeat discovery for an existing migration.")
    @click.option(
        "--prefect-api-url",
        callback=_validate_prefect_api_url,
        help="Use an externally managed Prefect server instead of starting one.",
    )
    def migrate(
        source_profile: Optional[str],
        workspace_mappings: Optional[Dict[str, str]],
        migration_id: Optional[str],
        prefect_api_url: Optional[str],
    ) -> None:
        """Discover resources to migrate from a SystemLink Server."""
        if migration_id is not None and (
            source_profile is not None or workspace_mappings is not None
        ):
            raise click.UsageError(
                "--migration-id cannot be combined with --source-profile or --workspace-mappings"
            )
        if migration_id is None and source_profile is None:
            raise click.UsageError(
                "Provide --source-profile for a new migration or --migration-id for an existing one"
            )

        try:
            from slcli.migration import command
        except ModuleNotFoundError as exc:
            if (exc.name or "").partition(".")[0] not in _MIGRATION_EXTRA_PACKAGES:
                raise
            raise click.ClickException(
                "Migration dependencies are not installed. Install systemlink-cli with "
                "the 'migration' extra, for example: pipx install 'systemlink-cli[migration]'."
            ) from exc

        if migration_id is not None:
            command.resume_migration(migration_id, prefect_api_url)
        elif source_profile is not None:
            command.start_migration(source_profile, workspace_mappings, prefect_api_url)
