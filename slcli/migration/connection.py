"""Profile-explicit SystemLink connections for migration operations."""

from dataclasses import dataclass, field
from typing import Any, Dict, Iterable, Optional, Union

import click
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

from slcli.profiles import Profile, ProfileConfig
from slcli.ssl_trust import use_standard_ssl_context
from slcli.utils import get_auth_headers, profile_ssl_verify, resolve_profile_auth

# Default retry policy: GET is replayed, but not POST, since a failure
# may be ambiguous about whether it created data, and we don't want to replay it.
_DEFAULT_RETRY = Retry(
    total=5,
    backoff_factor=0.5,
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=frozenset({"GET"}),
    respect_retry_after_header=True,
    raise_on_status=False,
)
# Retry policy that includes POSTs as well, to be used for query endpoints.
_QUERY_RETRY = _DEFAULT_RETRY.new(allowed_methods=frozenset({"GET", "POST"}))


class _ProfileSession(requests.Session):
    """Session that evaluates an explicit CA bundle despite injected OS trust."""

    def __init__(self, ssl_verify: Union[bool, str]) -> None:
        """Bind the session to one TLS verification setting."""
        super().__init__()
        self.verify = self._ssl_verify = ssl_verify

    def request(self, *args: Any, **kwargs: Any) -> requests.Response:  # type: ignore[override]
        """Send a request using the standard SSL context for CA bundle paths."""
        with use_standard_ssl_context(self._ssl_verify):
            return super().request(*args, **kwargs)


@dataclass(frozen=True)
class MigrationConnection:
    """Endpoint, authentication, TLS, and read-only settings from a named profile."""

    profile_name: str
    base_url: str
    headers: Dict[str, str] = field(repr=False)
    ssl_verify: Union[bool, str] = True
    readonly: bool = False

    def create_session(self, query_paths: Iterable[str] = ()) -> requests.Session:
        """Return a session bound to this connection's credentials and TLS.

        Requests are matched to a retry policy by URL prefix. URLs under any
        ``query_paths`` entry use the query policy, which replays POST requests.
        All other URLs use the default policy, which never replays POST requests.

        Args:
            query_paths: Route prefixes relative to ``base_url`` whose POST requests
                are read-only queries, such as ``"nitestmonitor/v2/query-"``.
        """
        session = _ProfileSession(self.ssl_verify)
        session.headers.update(self.headers)
        query_adapter = HTTPAdapter(max_retries=_QUERY_RETRY)
        write_adapter = HTTPAdapter(max_retries=_DEFAULT_RETRY)
        session.mount("https://", write_adapter)
        session.mount("http://", write_adapter)
        base = self.base_url.rstrip("/")
        for path in query_paths:
            session.mount(f"{base}/{path.lstrip('/')}", query_adapter)
        return session


def _require(value: Optional[str], profile: Profile, description: str) -> str:
    if not value:
        raise click.ClickException(f"Profile '{profile.name}' does not define {description}")
    return value


def resolve_migration_connection(
    profile_name: str, config: Optional[ProfileConfig] = None
) -> MigrationConnection:
    """Resolve one named profile as a unit.

    The current profile, ``SLCLI_PROFILE``, and ``SLCLI_API_URL``/``_API_KEY``/
    ``_WEB_URL`` environment overrides are deliberately ignored, including during
    PKCE token refresh. TLS follows normal CLI policy for this profile:
    ``SLCLI_SSL_VERIFY``, the profile's ``ssl-verify``, managed trust, CA bundles.

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
    else:
        base_url = _require(profile.server, profile, "a server URL")
    base_url = base_url.rstrip("/")

    # For PKCE, base_url is the Web URL, so refresh and requests share one TLS setting.
    ssl_verify = profile_ssl_verify(base_url, profile)
    auth = resolve_profile_auth(profile)
    if auth is None:
        raise click.ClickException(f"Profile '{profile.name}' does not define an API key")
    headers = get_auth_headers(auth.value, auth.scheme)
    return MigrationConnection(profile.name, base_url, headers, ssl_verify, profile.readonly)
