"""Profile-explicit SystemLink connections for migration operations."""

from dataclasses import dataclass, field
from typing import Dict, Optional, Union

import click
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from slcli.pkce import PkceError, get_pkce_access_token, refresh_pkce_credentials
from slcli.profiles import Profile, ProfileConfig
from slcli.ssl_trust import get_managed_trust_path
from slcli.utils import get_auth_headers

# Policy for read-only queries, including POST query endpoints, which are safe to replay.
# Destination writes will need a stricter policy that never replays ambiguous failures.
_QUERY_RETRY = Retry(
    total=5,
    backoff_factor=0.5,
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=frozenset({"GET", "POST"}),
    respect_retry_after_header=True,
    raise_on_status=False,
)


@dataclass(frozen=True)
class MigrationConnection:
    """Endpoint, authentication, and TLS settings from one explicitly named profile."""

    profile_name: str
    base_url: str
    headers: Dict[str, str] = field(repr=False)
    ssl_verify: Union[bool, str] = True

    def create_session(self) -> requests.Session:
        """Return a query session bound to this connection's credentials and TLS."""
        session = requests.Session()
        session.headers.update(self.headers)
        session.verify = self.ssl_verify
        adapter = HTTPAdapter(max_retries=_QUERY_RETRY)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session


def _require(value: Optional[str], profile: Profile, description: str) -> str:
    if not value:
        raise click.ClickException(f"Profile '{profile.name}' does not define {description}")
    return value


def _pkce_token(profile: Profile) -> str:
    """Resolve a bearer token using only the selected profile's credentials."""
    access_token = get_pkce_access_token(profile.name)
    if access_token:
        return access_token
    if profile.web_url and profile.pkce_client_id:
        try:
            return refresh_pkce_credentials(
                profile.name, profile.web_url, profile.pkce_client_id
            ).access_token
        except PkceError:
            pass
    raise click.ClickException(
        f"PKCE bearer token for profile '{profile.name}' is unavailable. "
        f"Run 'slcli login --profile {profile.name} --auth pkce' again."
    )


def resolve_migration_connection(
    profile_name: str, config: Optional[ProfileConfig] = None
) -> MigrationConnection:
    """Resolve one named profile as a unit.

    The current profile, ``SLCLI_PROFILE``, and ``SLCLI_API_URL``/``_API_KEY``/
    ``_SSL_VERIFY`` environment overrides are deliberately ignored.

    Args:
        profile_name: Name of the profile to resolve.
        config: Profile configuration; loaded from the user config when None.
    """
    profile = (config or ProfileConfig.load()).get_profile(profile_name)
    if profile is None:
        raise click.ClickException(f"Profile '{profile_name}' not found")

    # PKCE bearer tokens are accepted by the Web Server route, not the API route.
    if profile.auth_mode == "pkce":
        base_url = _require(profile.web_url, profile, "a Web UI URL")
        headers = get_auth_headers(_pkce_token(profile), "bearer")
    else:
        base_url = _require(profile.server, profile, "a server URL")
        headers = get_auth_headers(_require(profile.api_key, profile, "an API key"), "api-key")
    base_url = base_url.rstrip("/")

    ssl_verify: Union[bool, str] = profile.ssl_verify
    if profile.ssl_verify:
        managed_trust = get_managed_trust_path(base_url)
        ssl_verify = str(managed_trust) if managed_trust is not None else True
    return MigrationConnection(profile.name, base_url, headers, ssl_verify)
