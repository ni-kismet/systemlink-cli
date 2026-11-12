"""Profile-explicit SystemLink connections for migration operations."""

import logging
from dataclasses import dataclass, field
from types import TracebackType
from typing import Any, Dict, Optional, Union

import click
import requests
from requests.adapters import HTTPAdapter
from urllib3.connectionpool import ConnectionPool
from urllib3.response import BaseHTTPResponse
from urllib3.util.retry import Retry

from slcli.profiles import Profile, ProfileConfig
from slcli.ssl_trust import use_standard_ssl_context
from slcli.utils import get_auth_headers, profile_ssl_verify, resolve_profile_auth

_logger = logging.getLogger(__name__)


class LoggingRetry(Retry):
    """Retry policy that logs every retry decision to the migration log."""

    def increment(
        self,
        method: Optional[str] = None,
        url: Optional[str] = None,
        response: Optional[BaseHTTPResponse] = None,
        error: Optional[Exception] = None,
        _pool: Optional[ConnectionPool] = None,
        _stacktrace: Optional[TracebackType] = None,
    ) -> "LoggingRetry":
        """Log the retry decision, then defer to :class:`Retry`."""
        reason = f"status={response.status}" if response is not None else type(error).__name__
        try:
            retry = super().increment(method, url, response, error, _pool, _stacktrace)
        except Exception:
            _logger.warning(
                "HTTP retry exhausted: %s %s %s",
                method,
                url,
                reason,
            )
            raise
        _logger.warning(
            "HTTP retry: %s %s %s attempt=%d backoff=%.1fs",
            method,
            url,
            reason,
            len(retry.history),
            retry.get_backoff_time(),
        )
        return retry


# Policy for read-only queries, including POST query endpoints, which are safe to replay.
_QUERY_RETRY = LoggingRetry(
    total=5,
    backoff_factor=0.5,
    status_forcelist=(429, 500, 502, 503, 504),
    allowed_methods=frozenset({"GET", "POST"}),
    respect_retry_after_header=True,
    raise_on_status=False,
)

# Policy for destination writes. Only failures where the server did not process the
# request are retried: refused connections and explicit 429/503 back-pressure. Read
# timeouts and other 5xx responses are ambiguous and are never replayed.
_WRITE_RETRY = LoggingRetry(
    total=5,
    connect=5,
    read=0,
    other=0,
    backoff_factor=1.0,
    status_forcelist=(429, 503),
    allowed_methods=None,
    respect_retry_after_header=True,
    raise_on_status=False,
)


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
    """Endpoint, authentication, and TLS settings from one explicitly named profile."""

    profile_name: str
    base_url: str
    headers: Dict[str, str] = field(repr=False)
    ssl_verify: Union[bool, str] = True

    def create_session(self) -> requests.Session:
        """Return a query session bound to this connection's credentials and TLS."""
        return self._session(_QUERY_RETRY)

    def create_write_session(self) -> requests.Session:
        """Return a session for non-idempotent writes that never replays ambiguous failures."""
        return self._session(_WRITE_RETRY)

    def _session(self, retry: Retry) -> requests.Session:
        session = _ProfileSession(self.ssl_verify)
        session.headers.update(self.headers)
        adapter = HTTPAdapter(max_retries=retry)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
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
    return MigrationConnection(profile.name, base_url, headers, ssl_verify)
