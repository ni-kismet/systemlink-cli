"""OAuth authorization-code flow with PKCE for Stratus."""

import base64
import hashlib
import html
import secrets
import time
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from typing import Any, Dict, Mapping, Optional, Sequence
from urllib.parse import parse_qs, urlencode, urlparse

import keyring
import requests

from .ssl_trust import use_standard_ssl_context
from .utils import get_ssl_verify

TOKEN_SERVICE_PATH = "/nitoken/v1"
DEFAULT_SCOPES = ("openid", "profile", "email", "offline_access")
PKCE_KEYRING_SERVICE = "systemlink-cli"
PKCE_TIMEOUT_SECONDS = 300
PKCE_CALLBACK_PORT = 9876


class PkceError(RuntimeError):
    """Raised when the prototype PKCE flow cannot complete."""


@dataclass(frozen=True)
class PkceLoginResult:
    """Credentials returned by a successful PKCE login."""

    access_token: str
    refresh_token: Optional[str]
    expires_at: Optional[float] = None


class _CallbackServer(HTTPServer):
    callback_params: Optional[Dict[str, list[str]]] = None


class _CallbackHandler(BaseHTTPRequestHandler):
    """Receive one OAuth callback without logging its query string."""

    def do_GET(self) -> None:  # noqa: N802
        """Capture callback parameters and display a completion page."""
        parsed = urlparse(self.path)
        if parsed.path != "/callback":
            self._respond(404, "The login callback path was not found.")
            return

        self.server.callback_params = parse_qs(parsed.query, keep_blank_values=True)  # type: ignore[attr-defined]
        self._respond(200, "Login complete. You can close this browser tab.")

    def log_message(self, format: str, *args: Any) -> None:
        """Keep authorization codes and errors out of stderr logs."""

    def _respond(self, status: int, message: str) -> None:
        body = (
            "<!doctype html><html><head><meta charset='utf-8'><title>slcli</title></head>"
            f"<body><p>{html.escape(message)}</p></body></html>"
        ).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def generate_pkce_pair() -> tuple[str, str]:
    """Return a fresh PKCE verifier and its S256 challenge."""
    verifier = secrets.token_urlsafe(32)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


def build_authorization_url(
    authorization_url: str,
    client_id: str,
    redirect_uri: str,
    state: str,
    code_challenge: str,
    scopes: Sequence[str],
) -> str:
    """Build a standards-compliant authorization URL."""
    parsed = urlparse(authorization_url)
    if parsed.scheme not in ("http", "https") or not parsed.netloc:
        raise PkceError("Authorization endpoint must be an absolute HTTP(S) URL.")

    query = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "scope": " ".join(scopes),
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    separator = "&" if parsed.query else "?"
    return f"{authorization_url}{separator}{urlencode(query)}"


def _service_url(web_url: str, suffix: str) -> str:
    """Build a Token Service URL proxied by the configured Web UI host."""
    return f"{web_url.rstrip('/')}{TOKEN_SERVICE_PATH}{suffix}"


def _response_json(response: requests.Response, description: str) -> Mapping[str, Any]:
    """Read a JSON object without exposing response credentials in errors."""
    try:
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise PkceError(f"{description} failed: {exc}") from exc
    if not isinstance(payload, dict):
        raise PkceError(f"{description} returned an invalid response.")
    return payload


def _request_token(
    web_url: str, data: Dict[str, str], description: str, ssl_verify: bool | str
) -> Mapping[str, Any]:
    """Request a token using the configured TLS verification policy."""
    try:
        with use_standard_ssl_context(ssl_verify):
            response = requests.post(
                _service_url(web_url, "/token"),
                data=data,
                headers={"Accept": "application/json"},
                verify=ssl_verify,
                timeout=30,
            )
        return _response_json(response, description)
    except requests.RequestException as exc:
        raise PkceError(f"{description} failed: {exc}") from exc


def _token_expiry(payload: Mapping[str, Any]) -> Optional[float]:
    """Convert a token response's lifetime to an absolute expiry time."""
    expires_in = payload.get("expires_in")
    if isinstance(expires_in, (int, float)) and expires_in > 0:
        return time.time() + float(expires_in)
    return None


def _token_result(payload: Mapping[str, Any]) -> PkceLoginResult:
    """Validate a token response for direct bearer authentication."""
    access_token = payload.get("access_token")
    if not isinstance(access_token, str) or not access_token:
        raise PkceError("Token response did not contain an access token.")
    refresh_token = payload.get("refresh_token")
    if refresh_token is not None and not isinstance(refresh_token, str):
        raise PkceError("Token response contained an invalid refresh token.")
    return PkceLoginResult(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_at=_token_expiry(payload),
    )


def _single_callback_value(params: Mapping[str, list[str]], name: str) -> Optional[str]:
    """Return one callback query value when present."""
    values = params.get(name)
    return values[0] if values else None


def _wait_for_callback(server: _CallbackServer, timeout_seconds: int) -> Mapping[str, list[str]]:
    """Serve the loopback callback until completion or timeout."""
    deadline = time.monotonic() + timeout_seconds
    server.timeout = 0.5
    while server.callback_params is None and time.monotonic() < deadline:
        server.handle_request()
    if server.callback_params is None:
        raise PkceError("Login timed out waiting for the browser callback.")
    return server.callback_params


def perform_pkce_login(
    web_url: str,
    client_id: str,
    scopes: Sequence[str] = DEFAULT_SCOPES,
    timeout_seconds: int = PKCE_TIMEOUT_SECONDS,
) -> PkceLoginResult:
    """Run the browser PKCE flow and return credentials for bearer requests."""
    if not client_id.strip():
        raise PkceError("PKCE client ID cannot be empty.")
    if not scopes:
        raise PkceError("At least one PKCE scope is required.")
    if timeout_seconds <= 0:
        raise PkceError("PKCE timeout must be greater than zero.")

    verifier, challenge = generate_pkce_pair()
    state = secrets.token_urlsafe(32)
    try:
        server = _CallbackServer(("127.0.0.1", PKCE_CALLBACK_PORT), _CallbackHandler)
    except OSError as exc:
        raise PkceError(
            f"Could not bind the PKCE callback port {PKCE_CALLBACK_PORT}: {exc}"
        ) from exc
    try:
        port = int(server.server_address[1])
        redirect_uri = f"http://127.0.0.1:{port}/callback"
        authorization_url = build_authorization_url(
            _service_url(web_url, "/authorize"),
            client_id,
            redirect_uri,
            state,
            challenge,
            scopes,
        )
        if not webbrowser.open(authorization_url, new=2):
            raise PkceError("Could not open the default browser for login.")

        callback = _wait_for_callback(server, timeout_seconds)
    finally:
        server.server_close()

    returned_state = _single_callback_value(callback, "state")
    if returned_state != state:
        raise PkceError("Login callback state did not match the request.")

    callback_error = _single_callback_value(callback, "error")
    if callback_error:
        description = _single_callback_value(callback, "error_description")
        suffix = f": {description}" if description else ""
        raise PkceError(f"Authorization was denied ({callback_error}){suffix}.")

    code = _single_callback_value(callback, "code")
    if not code:
        raise PkceError("Login callback did not contain an authorization code.")

    ssl_verify = get_ssl_verify(web_url)
    token_payload = _request_token(
        web_url,
        {
            "grant_type": "authorization_code",
            "client_id": client_id,
            "code": code,
            "redirect_uri": redirect_uri,
            "code_verifier": verifier,
        },
        "Token exchange",
        ssl_verify,
    )
    return _token_result(token_payload)


def _credential_key(profile_name: str, credential: str) -> str:
    """Return the keyring key for a profile-scoped PKCE credential."""
    return f"PKCE:{profile_name}:{credential}"


def save_pkce_credentials(
    profile_name: str,
    access_token: str,
    refresh_token: Optional[str],
    expires_at: Optional[float] = None,
) -> None:
    """Persist PKCE bearer credentials in the operating-system keyring."""
    keyring.set_password(
        PKCE_KEYRING_SERVICE, _credential_key(profile_name, "access-token"), access_token
    )
    if refresh_token:
        keyring.set_password(
            PKCE_KEYRING_SERVICE,
            _credential_key(profile_name, "refresh-token"),
            refresh_token,
        )
    else:
        try:
            keyring.delete_password(
                PKCE_KEYRING_SERVICE, _credential_key(profile_name, "refresh-token")
            )
        except Exception:
            pass
    if expires_at is not None:
        keyring.set_password(
            PKCE_KEYRING_SERVICE,
            _credential_key(profile_name, "access-expires-at"),
            str(expires_at),
        )
    else:
        try:
            keyring.delete_password(
                PKCE_KEYRING_SERVICE, _credential_key(profile_name, "access-expires-at")
            )
        except Exception:
            pass
    for credential in ("session-key", "session-expires-at"):
        try:
            keyring.delete_password(PKCE_KEYRING_SERVICE, _credential_key(profile_name, credential))
        except Exception:
            pass


def get_pkce_access_token(profile_name: str) -> Optional[str]:
    """Return a stored, non-expired PKCE access token, if one exists."""
    try:
        access_token = keyring.get_password(
            PKCE_KEYRING_SERVICE, _credential_key(profile_name, "access-token")
        )
        expires_at = keyring.get_password(
            PKCE_KEYRING_SERVICE, _credential_key(profile_name, "access-expires-at")
        )
        if access_token and expires_at:
            try:
                if float(expires_at) <= time.time() + 60:
                    return None
            except ValueError:
                pass
        return access_token
    except Exception:
        return None


def refresh_pkce_credentials(profile_name: str, web_url: str, client_id: str) -> PkceLoginResult:
    """Refresh a profile's bearer credentials and persist rotated tokens."""
    try:
        refresh_token = keyring.get_password(
            PKCE_KEYRING_SERVICE, _credential_key(profile_name, "refresh-token")
        )
    except Exception as exc:
        raise PkceError("Could not read the PKCE refresh token from the keyring.") from exc
    if not refresh_token:
        raise PkceError("No PKCE refresh token is available.")

    ssl_verify = get_ssl_verify(web_url)
    payload = _request_token(
        web_url,
        {
            "grant_type": "refresh_token",
            "client_id": client_id,
            "refresh_token": refresh_token,
        },
        "Token refresh",
        ssl_verify,
    )
    result = _token_result(payload)
    save_pkce_credentials(
        profile_name, result.access_token, result.refresh_token, result.expires_at
    )
    return result


def delete_pkce_credentials(profile_name: str) -> None:
    """Delete PKCE bearer and refresh credentials from the keyring."""
    for credential in (
        "access-token",
        "refresh-token",
        "access-expires-at",
        "session-key",
        "session-expires-at",
    ):
        try:
            credential_key = _credential_key(profile_name, credential)
            keyring.delete_password(PKCE_KEYRING_SERVICE, credential_key)
        except Exception:
            pass
