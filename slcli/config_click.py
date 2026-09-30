"""CLI commands for managing slcli configuration and profiles."""

import getpass
import json
import os
import re
import ssl
import sys
from typing import Any, NoReturn, Optional
from urllib.parse import urlparse

import click
import questionary

from .credentials import (
    CredentialStoreError,
    describe_credential_store,
    get_credential,
    set_credential,
)
from .platform import (
    PLATFORM_SLE,
    PLATFORM_SLS,
    check_service_status,
    check_web_server_auth,
)
from .profiles import Profile, ProfileConfig, check_config_file_permissions
from .rich_output import render_table
from .ssl_trust import (
    get_managed_trust_records,
    get_ssl_server_origin,
    inspect_server_certificate,
    remove_managed_trust,
    save_managed_certificate,
)
from .table_utils import output_formatted_list
from .utils import ExitCodes, get_base_url, get_base_url_resolution

API_KEY_LENGTH = 42
API_KEY_PATTERN = re.compile(rf"^[A-Za-z0-9_-]{{{API_KEY_LENGTH}}}$")
ENV_OVERRIDE_FIELDS = (
    ("API URL", ("SLCLI_API_URL", "SYSTEMLINK_API_URL")),
    ("API Key", ("SLCLI_API_KEY", "SYSTEMLINK_API_KEY")),
    ("Web URL", ("SLCLI_WEB_URL", "SYSTEMLINK_WEB_URL")),
)


def _exit_with_validation_error(message: str, exit_code: int = ExitCodes.INVALID_INPUT) -> NoReturn:
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


def _get_active_env_overrides() -> list[str]:
    """Return config fields currently overridden by environment variables."""
    active_overrides: list[str] = []
    for label, env_names in ENV_OVERRIDE_FIELDS:
        if any(os.environ.get(env_name) for env_name in env_names):
            active_overrides.append(label)
    return active_overrides


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


def _any_service_probes_unauthorized(services: dict[str, str]) -> bool:
    """Return True if any recorded service probe failed with authorization."""
    return bool(services) and any(status == "unauthorized" for status in services.values())


def _normalize_fingerprint(fingerprint: str) -> str:
    """Normalize a SHA-256 certificate fingerprint supplied by a user."""
    normalized = fingerprint.replace(":", "").replace(" ", "").strip().upper()
    if len(normalized) != 64 or any(
        character not in "0123456789ABCDEF" for character in normalized
    ):
        _exit_with_validation_error("Certificate fingerprint must be a 64-character SHA-256 value.")
    return normalized


def _show_certificate_details(certificate: dict[str, Any], err: bool = False) -> None:
    """Display certificate identity and validity details."""
    click.echo(f"  Server: {certificate.get('origin', 'unknown')}", err=err)
    click.echo(f"  Subject: {certificate.get('subject', 'unknown')}", err=err)
    click.echo(f"  Issuer: {certificate.get('issuer', 'unknown')}", err=err)
    click.echo(f"  SHA-256: {certificate.get('fingerprint', 'unknown')}", err=err)
    click.echo(f"  Self-signed: {'yes' if certificate.get('self-signed') else 'no'}", err=err)
    click.echo(
        f"  Valid: {certificate.get('not-before', 'unknown')} to "
        f"{certificate.get('not-after', 'unknown')}",
        err=err,
    )


def _show_certificate_warning(certificate: dict[str, Any]) -> None:
    """Display the identity of a certificate before it is trusted."""
    click.echo("\n⚠️  TLS certificate verification failed.", err=True)
    _show_certificate_details(certificate, err=True)


def _trust_certificate_if_requested(
    url: str,
    credential: str,
    status: dict[str, Any],
    trust_fingerprint: Optional[str],
    auth_scheme: str = "api-key",
) -> dict[str, Any]:
    """Prompt for or apply certificate trust after a verification failure."""
    certificate_details = status.get("certificate")
    if not isinstance(certificate_details, dict):
        _exit_with_validation_error(
            "TLS certificate verification failed, but the server certificate could not be "
            "inspected. Profile was not saved.",
            ExitCodes.NETWORK_ERROR,
        )

    _show_certificate_warning(certificate_details)
    expected_fingerprint = _normalize_fingerprint(trust_fingerprint) if trust_fingerprint else None
    actual_fingerprint = str(certificate_details.get("fingerprint", "")).upper()
    if expected_fingerprint:
        if expected_fingerprint != actual_fingerprint:
            _exit_with_validation_error(
                "The server certificate fingerprint does not match --trust-fingerprint. "
                "Profile was not saved.",
                ExitCodes.INVALID_INPUT,
            )
    elif not click.confirm("Trust this certificate for this server?", default=False):
        _exit_with_validation_error("Certificate was not trusted. Profile was not saved.")

    try:
        certificate = inspect_server_certificate(url)
    except (OSError, ValueError, ssl.SSLError) as exc:
        _exit_with_validation_error(
            f"Could not inspect the server certificate: {exc}. Profile was not saved.",
            ExitCodes.NETWORK_ERROR,
        )

    if certificate.fingerprint != actual_fingerprint:
        _exit_with_validation_error(
            "The server certificate changed during approval. Profile was not saved.",
            ExitCodes.NETWORK_ERROR,
        )

    try:
        save_managed_certificate(certificate)
        if auth_scheme == "bearer":
            retry_status = check_web_server_auth(url, credential, auth_scheme=auth_scheme)
        else:
            retry_status = check_service_status(url, credential, auth_scheme=auth_scheme)
    except (OSError, ValueError) as exc:
        _exit_with_validation_error(
            f"Could not save the trusted certificate: {exc}. Profile was not saved.",
            ExitCodes.GENERAL_ERROR,
        )

    if not retry_status.get("server_reachable") or retry_status.get("certificate_error"):
        remove_managed_trust(url)
        _exit_with_validation_error(
            "The server could not be verified after trusting its certificate. "
            "Profile was not saved.",
            ExitCodes.NETWORK_ERROR,
        )

    click.echo("  Certificate: ✓ Trusted for this server")
    return retry_status


def _add_profile_impl(
    profile: Optional[str],
    url: Optional[str],
    api_key: Optional[str],
    web_url: Optional[str],
    workspace: Optional[str],
    set_current: bool,
    readonly: bool,
    trust_fingerprint: Optional[str] = None,
    auth_mode: str = "api-key",
    client_id: Optional[str] = None,
    scopes: tuple[str, ...] = (),
    callback_port: Optional[int] = None,
    credential_store: str = "os",
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
        trust_fingerprint: Optional SHA-256 fingerprint for non-interactive trust approval
        auth_mode: Authentication flow to use
        client_id: Public OAuth client ID for the PKCE login
        scopes: OAuth scopes for the PKCE login
        callback_port: Optional loopback callback port; zero selects an ephemeral port
        credential_store: Store for profile API keys and PKCE credentials
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

    if auth_mode == "api-key":
        # Get API key - either from flag or prompt
        if not api_key:
            api_key = getpass.getpass("Enter your SystemLink API key: ")
        assert isinstance(api_key, str)
        api_key = _normalize_api_key(api_key)
    elif auth_mode == "pkce":
        if api_key:
            _exit_with_validation_error(
                "--api-key cannot be combined with --auth pkce. "
                "Use --auth api-key for the API-key login flow."
            )
    else:
        _exit_with_validation_error(f"Unsupported authentication flow: {auth_mode}")

    # Normalize and validate web_url (prompt if not provided)
    if not web_url:
        click.echo("Example: https://my-systemlink.com")
        web_url = click.prompt("Enter your SystemLink Web UI URL")
    assert isinstance(web_url, str)
    web_url = _normalize_base_url(web_url, "SystemLink Web UI URL")

    pkce_result: Any = None
    pkce_scopes = list(scopes) if scopes else ["openid", "profile", "email", "offline_access"]
    if auth_mode == "pkce":
        certificate_status = check_web_server_auth(web_url, "", auth_scheme="bearer")
        if certificate_status.get("certificate_error") and not certificate_status.get(
            "server_reachable"
        ):
            _trust_certificate_if_requested(
                web_url,
                "",
                certificate_status,
                trust_fingerprint,
                auth_scheme="bearer",
            )
        if not client_id:
            client_id = click.prompt("PKCE client ID")
        assert isinstance(client_id, str)
        client_id = client_id.strip()
        if not client_id:
            _exit_with_validation_error("PKCE client ID cannot be empty.")

        from .pkce import PkceError, perform_pkce_login

        click.echo("Opening the SystemLink Web UI for authentication...")
        try:
            if callback_port is None:
                pkce_result = perform_pkce_login(web_url, client_id, pkce_scopes)
            else:
                pkce_result = perform_pkce_login(
                    web_url, client_id, pkce_scopes, callback_port=callback_port
                )
        except PkceError as exc:
            _exit_with_validation_error(f"PKCE login failed: {exc}")
        api_key = pkce_result.access_token

    assert isinstance(api_key, str)

    # Validate PKCE against the Web Server identity route; API-key login retains API probes.
    click.echo("Checking server connectivity and services...")
    if auth_mode == "pkce":
        status = check_web_server_auth(web_url, api_key, auth_scheme="bearer")
    else:
        status = check_service_status(url, api_key)

    if status.get("certificate_error") and not status.get("server_reachable"):
        validation_url = web_url if auth_mode == "pkce" else url
        status = _trust_certificate_if_requested(
            validation_url,
            api_key,
            status,
            trust_fingerprint,
            auth_scheme="bearer" if auth_mode == "pkce" else "api-key",
        )

    platform = status["platform"]
    if auth_mode == "pkce":
        platform_status = check_service_status(web_url, api_key, auth_scheme="bearer")
        detected_platform = platform_status.get("platform")
        if detected_platform in (PLATFORM_SLE, PLATFORM_SLS):
            platform = detected_platform
    services = status.get("services", {})

    if not status["server_reachable"]:
        _exit_with_validation_error(
            "Could not connect to the SystemLink server. Verify the URL and network access. "
            "Profile was not saved.",
            ExitCodes.NETWORK_ERROR,
        )

    if status["auth_valid"] is False and (
        _all_service_probes_unauthorized(services)
        or (_any_service_probes_unauthorized(services) and platform == PLATFORM_SLS)
    ):
        auth_failure_message = (
            "PKCE bearer token validation failed. The server responded, but the token was not authorized. "
            if auth_mode == "pkce"
            else "API key validation failed. The server responded, but the key was not authorized. "
        )
        _exit_with_validation_error(
            auth_failure_message + "Profile was not saved.",
            ExitCodes.PERMISSION_DENIED,
        )

    if status["auth_valid"] is not True:
        verification_message = (
            "Connected to the server, but profile verification was inconclusive. Check the "
            "Web UI URL, bearer token, and service availability. Profile was not saved."
            if auth_mode == "pkce"
            else "Connected to the server, but profile verification was inconclusive. Check the "
            "API URL, API key, and service availability. Profile was not saved."
        )
        _exit_with_validation_error(
            verification_message,
            ExitCodes.GENERAL_ERROR,
        )

    click.echo("  Connection: ✓ Verified")
    if platform == PLATFORM_SLE:
        click.echo("  Platform: SystemLink Enterprise (Cloud)")
    elif platform == PLATFORM_SLS:
        click.echo("  Platform: SystemLink Server (On-Premises)")
    else:
        click.echo("  Platform: Unknown (will attempt all features)")

    if auth_mode == "pkce":
        click.echo("  PKCE bearer token:  ✓ Authorized")
    else:
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
    cfg = ProfileConfig.load()
    previous_profile = cfg.get_profile(profile)
    previous_current_profile = cfg.current_profile
    new_profile = Profile(
        name=profile,
        server=url,
        api_key="" if credential_store == "os" else api_key,
        web_url=web_url,
        platform=platform,
        workspace=workspace,
        readonly=readonly,
        auth_mode=auth_mode,
        pkce_client_id=client_id if auth_mode == "pkce" else None,
        pkce_scopes=pkce_scopes if auth_mode == "pkce" else None,
        credential_store=credential_store,
    )
    if previous_profile:
        new_profile.credential_id = previous_profile.credential_id

    def store_profile_credentials(store: str) -> None:
        if auth_mode == "pkce" and pkce_result is not None:
            from .pkce import save_pkce_credentials

            save_pkce_credentials(
                new_profile.credential_id,
                pkce_result.access_token,
                pkce_result.refresh_token,
                pkce_result.expires_at,
                store,
            )
        elif auth_mode == "api-key":
            set_credential(new_profile.credential_id, "api-key", api_key, store)

    moving_file_credentials_to_os = (
        previous_profile is not None
        and previous_profile.credential_store == "file"
        and new_profile.credential_store == "os"
    )
    staged_os_credentials = False
    if moving_file_credentials_to_os:
        try:
            store_profile_credentials("os")
            staged_os_credentials = True
        except Exception as exc:
            new_profile.credential_store = "file"
            if auth_mode == "api-key":
                new_profile.api_key = api_key
            elif pkce_result is not None:
                new_profile.pkce_credentials = {
                    "access-token": pkce_result.access_token,
                    "refresh-token": pkce_result.refresh_token,
                    "access-expires-at": pkce_result.expires_at,
                }
            click.echo(
                f"⚠️  OS credential store unavailable ({exc}); "
                "storing this profile in the config file.",
                err=True,
            )

    cfg.add_profile(new_profile, set_current=set_current)
    if staged_os_credentials:
        try:
            cfg.save()
        except RuntimeError as save_exc:
            from .credentials import delete_credential

            credential_name = "pkce" if auth_mode == "pkce" else "api-key"
            cleanup_error: Optional[CredentialStoreError] = None
            try:
                delete_credential(new_profile.credential_id, credential_name)
            except CredentialStoreError as exc:
                cleanup_error = exc

            if previous_profile is None:
                cfg.profiles.pop(profile, None)
            else:
                cfg.profiles[profile] = previous_profile
            cfg.current_profile = previous_current_profile
            try:
                cfg.save()
            except RuntimeError as rollback_exc:
                _exit_with_validation_error(
                    f"Could not save the profile or restore the previous config: "
                    f"{save_exc}; {rollback_exc}. Credential ID: "
                    f"{new_profile.credential_id}.",
                    ExitCodes.GENERAL_ERROR,
                )
            if cleanup_error:
                _exit_with_validation_error(
                    f"Could not save the profile: {save_exc}. The previous profile was "
                    f"restored, but staged credentials could not be removed: {cleanup_error}.",
                    ExitCodes.GENERAL_ERROR,
                )
            _exit_with_validation_error(
                f"Could not save the profile: {save_exc}. The previous profile was restored.",
                ExitCodes.GENERAL_ERROR,
            )
    else:
        cfg.save()

    try:
        if not staged_os_credentials:
            store_profile_credentials(new_profile.credential_store)
    except Exception as exc:
        if new_profile.credential_store != "os":
            if previous_profile is None:
                cfg.profiles.pop(profile, None)
            else:
                cfg.profiles[profile] = previous_profile
            cfg.current_profile = previous_current_profile
            cfg.save()
            _exit_with_validation_error(
                f"Could not store credentials: {exc}.", ExitCodes.GENERAL_ERROR
            )

        click.echo(
            f"⚠️  OS credential store unavailable ({exc}); storing this profile in the config file.",
            err=True,
        )
        new_profile.credential_store = "file"
        cfg.save()
        try:
            if auth_mode == "pkce" and pkce_result is not None:
                from .pkce import save_pkce_credentials

                save_pkce_credentials(
                    new_profile.credential_id,
                    pkce_result.access_token,
                    pkce_result.refresh_token,
                    pkce_result.expires_at,
                    "file",
                )
            elif auth_mode == "api-key":
                set_credential(new_profile.credential_id, "api-key", api_key, "file")
        except Exception as fallback_exc:
            if previous_profile is None:
                cfg.profiles.pop(profile, None)
            else:
                cfg.profiles[profile] = previous_profile
            cfg.current_profile = previous_current_profile
            cfg.save()
            _exit_with_validation_error(
                f"Could not store credentials in the config file: {fallback_exc}.",
                ExitCodes.GENERAL_ERROR,
            )

    if previous_profile and previous_profile.credential_store == "os":
        from .credentials import delete_credential

        if new_profile.credential_store == "file":
            active_credential = "pkce" if previous_profile.auth_mode == "pkce" else "api-key"
            obsolete_credentials = tuple(
                credential for credential in ("api-key", "pkce") if credential != active_credential
            ) + (active_credential,)
        else:
            obsolete_credentials = ("pkce",) if auth_mode == "api-key" else ("api-key",)
        for obsolete in obsolete_credentials:
            try:
                delete_credential(previous_profile.credential_id, obsolete)
            except CredentialStoreError as exc:
                if new_profile.credential_store == "file":
                    cfg.profiles[profile] = previous_profile
                    cfg.current_profile = previous_current_profile
                    cfg.save()
                    _exit_with_validation_error(
                        f"Could not remove replaced credentials: {exc}. The previous profile "
                        "was restored; resolve the credential-store issue and retry.",
                        ExitCodes.GENERAL_ERROR,
                    )
                click.echo(f"⚠️  Could not remove replaced credentials: {exc}", err=True)

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


def _get_profile_secret(profile: Profile, credential: str) -> Optional[str]:
    """Read a profile secret only for an explicit secret-display operation."""
    try:
        return get_credential(profile.credential_id, credential, profile.credential_store)
    except CredentialStoreError as exc:
        raise click.ClickException(str(exc)) from exc


def register_config_commands(cli: Any) -> None:
    """Register the 'config' command group and its subcommands."""

    @cli.group()
    def config() -> None:
        """Manage slcli settings and profiles.

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
                    "auth-mode": p.auth_mode,
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
        """View the stored configuration file values."""
        cfg = ProfileConfig.load()
        env_overrides = _get_active_env_overrides()

        if format == "json":
            data: dict = {}
            if cfg.current_profile:
                data["current-profile"] = cfg.current_profile
            if cfg.profiles:
                # Mask API keys unless --show-secrets is specified
                data["profiles"] = {}
                for name, profile in cfg.profiles.items():
                    profile_dict = profile.to_dict()
                    if profile.auth_mode == "pkce":
                        if show_secrets:
                            try:
                                pkce_credentials = json.loads(
                                    _get_profile_secret(profile, "pkce") or "{}"
                                )
                            except json.JSONDecodeError:
                                _exit_with_validation_error(
                                    f"Stored PKCE credentials for profile '{name}' are invalid. "
                                    f"Run 'slcli login --profile {name}' to authenticate again.",
                                    ExitCodes.GENERAL_ERROR,
                                )
                            if not isinstance(pkce_credentials, dict):
                                _exit_with_validation_error(
                                    f"Stored PKCE credentials for profile '{name}' are invalid. "
                                    f"Run 'slcli login --profile {name}' to authenticate again.",
                                    ExitCodes.GENERAL_ERROR,
                                )
                            profile_dict["pkce-credentials"] = pkce_credentials
                        else:
                            profile_dict["pkce-credentials"] = (
                                f"stored in {describe_credential_store(profile.credential_store)}"
                            )
                    elif profile.credential_store == "os":
                        if show_secrets:
                            profile_dict["api-key"] = _get_profile_secret(profile, "api-key")
                        else:
                            profile_dict["api-key"] = (
                                f"stored in {describe_credential_store(profile.credential_store)}"
                            )
                    elif not show_secrets and "api-key" in profile_dict:
                        key = profile_dict["api-key"]
                        profile_dict["api-key"] = "****" + key[-4:] if len(key) >= 4 else "****"
                    data["profiles"][name] = profile_dict
            if cfg.settings:
                data.update(cfg.settings)
            if env_overrides:
                data["env-overrides"] = env_overrides
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

            if profile.auth_mode == "pkce":
                rows.append(
                    [
                        "Authentication",
                        f"PKCE (bearer token in {describe_credential_store(profile.credential_store)})",
                    ]
                )
                if show_secrets:
                    rows.append(["PKCE Credentials", _get_profile_secret(profile, "pkce") or ""])
            else:
                if profile.credential_store == "os":
                    if show_secrets:
                        api_key_display = _get_profile_secret(profile, "api-key") or ""
                    else:
                        api_key_display = (
                            f"stored in {describe_credential_store(profile.credential_store)}"
                        )
                elif show_secrets:
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

        if env_overrides:
            click.echo(
                f"\n⚠️  Environment overrides active ({', '.join(env_overrides)}). "
                "Run 'slcli info' for effective values.",
                err=True,
            )

        # Check for permission warning
        warning = check_config_file_permissions()
        if warning:
            click.echo(f"\n⚠️  {warning}", err=True)

    @config.group(name="trust")
    def trust() -> None:
        """Manage explicitly trusted server certificates."""
        pass

    @trust.command(name="show")
    @click.option("--url", help="HTTPS server URL (defaults to the active API URL)")
    @click.option(
        "--format",
        "output_format",
        "-f",
        type=click.Choice(["table", "json"]),
        default="table",
        show_default=True,
        help="Output format",
    )
    def show_server_certificate(url: Optional[str], output_format: str) -> None:
        """Inspect and display the current server certificate without trusting it."""
        server_url = url or get_base_url_resolution().value
        try:
            certificate = inspect_server_certificate(server_url)
        except (OSError, ValueError, ssl.SSLError) as exc:
            _exit_with_validation_error(
                f"Could not inspect the server certificate: {exc}.", ExitCodes.NETWORK_ERROR
            )

        certificate_details = certificate.to_dict()
        if output_format == "json":
            click.echo(json.dumps(certificate_details, indent=2))
            return

        click.echo(f"Server certificate for {certificate_details.get('origin', 'unknown')}")
        _show_certificate_details(certificate_details)

    @trust.command(name="list")
    @click.option(
        "--format",
        "output_format",
        type=click.Choice(["table", "json"]),
        default="table",
        help="Output format",
    )
    def list_trusted_certificates(output_format: str) -> None:
        """List certificates trusted by slcli."""
        records = get_managed_trust_records()
        if output_format == "json":
            click.echo(json.dumps(records, indent=2))
            return
        if not records:
            click.echo("No managed server certificates.")
            return

        rows = [
            [
                str(record.get("origin", "")),
                str(record.get("fingerprint", "")),
                "yes" if record.get("self-signed") else "no",
            ]
            for record in records
        ]
        render_table(
            headers=["SERVER", "SHA-256", "SELF-SIGNED"],
            column_widths=[40, 64, 12],
            rows=rows,
            show_total=True,
            total_label="certificate(s)",
        )

    @trust.command(name="add")
    @click.option("--url", help="HTTPS server URL (defaults to the active API URL)")
    @click.option(
        "--fingerprint",
        required=True,
        help="Expected SHA-256 fingerprint of the certificate to trust",
    )
    def add_trusted_certificate(url: Optional[str], fingerprint: str) -> None:
        """Trust a server certificate after verifying its fingerprint."""
        server_url = url or get_base_url()
        try:
            expected_fingerprint = _normalize_fingerprint(fingerprint)
            certificate = inspect_server_certificate(server_url)
        except (OSError, ValueError, ssl.SSLError) as exc:
            _exit_with_validation_error(f"Could not inspect the server certificate: {exc}.")

        _show_certificate_warning(certificate.to_dict())
        if certificate.fingerprint != expected_fingerprint:
            _exit_with_validation_error(
                "The server certificate fingerprint does not match the supplied fingerprint."
            )
        try:
            path = save_managed_certificate(certificate)
        except OSError as exc:
            _exit_with_validation_error(f"Could not save the trusted certificate: {exc}.")
        click.echo(f"✓ Trusted certificate for {certificate.origin}")
        click.echo(f"  Certificate file: {path}")

    @trust.command(name="remove")
    @click.option("--url", help="HTTPS server URL (defaults to the active API URL)")
    @click.option("--force", is_flag=True, help="Skip confirmation prompt")
    def remove_trusted_certificate(url: Optional[str], force: bool) -> None:
        """Remove a server certificate from the managed trust store."""
        server_url = url or get_base_url()
        try:
            origin = get_ssl_server_origin(server_url)
        except ValueError as exc:
            _exit_with_validation_error(str(exc))
        if not force and not click.confirm(
            f"Remove trusted certificate for {origin}?", default=False
        ):
            click.echo("Certificate was not removed.")
            return
        try:
            removed = remove_managed_trust(server_url)
        except (OSError, ValueError) as exc:
            _exit_with_validation_error(f"Could not remove the trusted certificate: {exc}.")
        if not removed:
            _exit_with_validation_error(
                f"No trusted certificate found for {origin}.", ExitCodes.NOT_FOUND
            )
        click.echo(f"✓ Removed trusted certificate for {origin}")

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

        profile_to_delete = cfg.profiles[name]
        previous_current_profile = cfg.current_profile
        was_current = cfg.current_profile == name
        cfg.delete_profile(name)
        try:
            cfg.save()
        except RuntimeError as exc:
            cfg.profiles[name] = profile_to_delete
            cfg.current_profile = previous_current_profile
            _exit_with_validation_error(
                f"Could not save profile removal for '{name}': {exc}. "
                "Credentials were not removed.",
                ExitCodes.GENERAL_ERROR,
            )

        if profile_to_delete.credential_store == "os" or profile_to_delete.auth_mode == "pkce":
            from .credentials import delete_profile_credentials

            try:
                delete_profile_credentials(
                    profile_to_delete.credential_id,
                    profile_to_delete.credential_store,
                    profile_to_delete.name if profile_to_delete.auth_mode == "pkce" else None,
                )
            except CredentialStoreError as exc:
                cfg.profiles[name] = profile_to_delete
                cfg.current_profile = previous_current_profile
                try:
                    cfg.save()
                except RuntimeError as rollback_exc:
                    _exit_with_validation_error(
                        f"Could not remove stored credentials: {exc}. "
                        f"Could not restore profile metadata: {rollback_exc}. "
                        f"Credential ID: {profile_to_delete.credential_id}.",
                        ExitCodes.GENERAL_ERROR,
                    )
                _exit_with_validation_error(
                    f"Could not remove stored credentials: {exc}. Profile was not deleted; "
                    "resolve the credential-store issue and retry.",
                    ExitCodes.GENERAL_ERROR,
                )

        click.echo(f"✓ Profile '{name}' deleted.")
        if was_current and cfg.current_profile:
            click.echo(f"  Current profile is now: {cfg.current_profile}")

    @config.command(name="secure")
    @click.option("--profile", "profile_name", help="Profile to secure (defaults to current)")
    @click.option("--all", "secure_all", is_flag=True, help="Secure every file-backed profile")
    def secure_profiles(profile_name: Optional[str], secure_all: bool) -> None:
        """Move plaintext API keys and PKCE credentials into the OS store."""
        if profile_name and secure_all:
            _exit_with_validation_error("Choose either --profile or --all, not both.")

        cfg = ProfileConfig.load()
        if secure_all:
            selected = list(cfg.profiles.values())
        else:
            selected_name = profile_name or cfg.current_profile
            if not selected_name:
                _exit_with_validation_error("No current profile is set.", ExitCodes.NOT_FOUND)
            profile_to_secure = cfg.get_profile(selected_name)
            if not profile_to_secure:
                _exit_with_validation_error(
                    f"Profile '{selected_name}' not found.", ExitCodes.NOT_FOUND
                )
            selected = [profile_to_secure]

        pending: list[tuple[Profile, str, str]] = []
        for profile_to_secure in selected:
            if profile_to_secure.api_key:
                pending.append((profile_to_secure, "api-key", profile_to_secure.api_key))
            if profile_to_secure.pkce_credentials:
                pending.append(
                    (
                        profile_to_secure,
                        "pkce",
                        json.dumps(profile_to_secure.pkce_credentials),
                    )
                )

        if not pending:
            click.echo("All selected profile credentials are already secured.")
            return

        try:
            for profile_to_secure, credential, value in pending:
                set_credential(profile_to_secure.credential_id, credential, value, "os")
        except CredentialStoreError as exc:
            _exit_with_validation_error(f"Could not secure profile credentials: {exc}.")

        for profile_to_secure, _credential, _value in pending:
            profile_to_secure.credential_store = "os"
            profile_to_secure.api_key = ""
            profile_to_secure.pkce_credentials = {}
        cfg.save()
        secured_names = sorted({profile_to_secure.name for profile_to_secure, _, _ in pending})
        click.echo(f"✓ Secured credentials for: {', '.join(secured_names)}")

    @config.command(name="add")
    @click.option("--profile", "-p", help="Profile name (default: 'default')")
    @click.option("--url", help="SystemLink API URL")
    @click.option("--api-key", help="SystemLink API key")
    @click.option("--web-url", help="SystemLink Web UI base URL")
    @click.option(
        "--auth",
        "auth_mode",
        type=click.Choice(["api-key", "pkce"]),
        default="api-key",
        show_default=True,
        help="Authentication flow to use",
    )
    @click.option("--client-id", help="Public OAuth client ID for the PKCE prototype")
    @click.option(
        "--callback-port",
        type=click.IntRange(0, 65535),
        help="Loopback callback port; use 0 for an ephemeral port",
    )
    @click.option(
        "--scope",
        "scopes",
        multiple=True,
        help=(
            "OAuth scope to request; may be repeated "
            "(defaults to openid profile email offline_access)"
        ),
    )
    @click.option(
        "--credential-store",
        type=click.Choice(["os", "file"]),
        default="os",
        envvar="SLCLI_CREDENTIAL_STORE",
        show_default=True,
        help="Store credentials in the OS store or config file",
    )
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
    @click.option(
        "--trust-fingerprint",
        help="Trust a certificate after its SHA-256 fingerprint matches exactly",
    )
    def add_profile(
        profile: Optional[str],
        url: Optional[str],
        api_key: Optional[str],
        web_url: Optional[str],
        auth_mode: str,
        client_id: Optional[str],
        callback_port: Optional[int],
        scopes: tuple[str, ...],
        credential_store: str,
        workspace: Optional[str],
        set_current: bool,
        readonly: bool,
        trust_fingerprint: Optional[str],
    ) -> None:
        """Add or update a SystemLink profile.

        Profiles allow you to configure multiple SystemLink environments and switch
        between them. Credentials use the OS store by default.

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
            auth_mode=auth_mode,
            client_id=client_id,
            callback_port=callback_port,
            scopes=scopes,
            credential_store=credential_store,
            workspace=workspace,
            set_current=set_current,
            readonly=readonly,
            trust_fingerprint=trust_fingerprint,
        )
