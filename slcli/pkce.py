"""OAuth authorization-code flow with PKCE for Stratus."""

import base64
import hashlib
import html
import secrets
import time
import webbrowser
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence
from urllib.parse import parse_qs, quote, urlencode, urlparse

import keyring
import requests

from .ssl_trust import use_standard_ssl_context
from .utils import get_ssl_verify

TOKEN_SERVICE_PATH = "/nitoken/v1"
DEFAULT_SCOPES = ("openid", "profile", "email", "offline_access")
PKCE_KEYRING_SERVICE = "systemlink-cli"
PKCE_TIMEOUT_SECONDS = 300
PKCE_CALLBACK_PORT = 9876
_PKCE_CREDENTIAL_NAMES = (
    "access-token",
    "refresh-token",
    "access-expires-at",
    "session-key",
    "session-expires-at",
)
_SYSTEMLINK_LOGO_DATA = base64.b64encode(
    Path(__file__).with_name("systemlink-logo.svg").read_bytes()
).decode("ascii")

_CALLBACK_BACKGROUND_SVG = """
<svg id="Layer_1" data-name="Layer 1" xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" viewBox="0 0 2560 1444">
    <defs>
        <style>
            .cls-1 { fill: url(#linear-gradient); }
            .cls-2 { fill: #00ad7c; opacity: .12; }
        </style>
        <linearGradient id="linear-gradient" x1="-4361" y1="5785" x2="-4361" y2="8345" gradientTransform="translate(-5785 5083) rotate(90) scale(1 -1)" gradientUnits="userSpaceOnUse">
            <stop offset="0" stop-color="#00ad7c" />
            <stop offset=".05" stop-color="#01a479" />
            <stop offset=".37" stop-color="#0c6d68" />
            <stop offset=".65" stop-color="#14465c" />
            <stop offset=".87" stop-color="#192d54" />
            <stop offset="1" stop-color="#1b2552" />
        </linearGradient>
    </defs>
    <rect class="cls-1" width="2560" height="1444" />
    <path class="cls-2" d="M2560,1444c-189.63,0-377.4-37.35-552.59-109.92-175.2-72.57-334.38-178.93-468.47-313.02-134.09-134.09-240.45-293.27-313.02-468.47-72.57-175.19-109.92-362.97-109.92-552.59h1444v1444Z" />
    <path class="cls-2" d="M0,0v916.33c29.86,36.37,61.54,71.33,94.94,104.73,134.09,134.09,293.27,240.45,468.47,313.02 175.19,72.57,362.96,109.92,552.59,109.92s377.4-37.35,552.59-109.92c175.2-72.57,334.38-178.93,468.47-313.02 134.09-134.09,240.45-293.27,313.02-468.47 72.57-175.19 109.92-362.97 109.92-552.59H0Z" />
</svg>
""".strip()

_CALLBACK_PAGE_BACKGROUND = (
    'url("data:image/svg+xml,'
    + quote(_CALLBACK_BACKGROUND_SVG, safe="")
    + '") no-repeat center bottom / cover, '
    "linear-gradient(rgb(241, 241, 242), rgba(241, 241, 242, 0))"
)

_CALLBACK_PAGE_CSS = """
:root {
    color: #161617;
    font-family: "Source Sans Pro", "Source Sans Pro Fallback", Arial, sans-serif;
    font-size: 14px;
    font-weight: 400;
}

* {
    box-sizing: border-box;
}

html,
body {
    min-height: 100%;
    margin: 0;
}

body {
    background: #1b2552;
}

.page-shell {
    align-items: center;
    display: flex;
    justify-content: center;
    min-height: 100vh;
    padding: 32px;
}

.card {
    align-items: center;
    background: #ffffff;
    border: 1px solid #d9d9da;
    display: flex;
    flex-direction: column;
    justify-content: center;
    max-width: 480px;
    min-height: 376px;
    padding: 32px;
    text-align: center;
    width: 100%;
}

.brand-logo {
    display: block;
    height: 72px;
    margin-bottom: 26px;
    object-fit: contain;
    width: 144px;
}

.status-icon {
    border: 2px solid;
    border-radius: 50%;
    height: 48px;
    margin-bottom: 18px;
    position: relative;
    width: 48px;
}

.status-icon.success {
    border-color: #00844a;
}

.status-icon.success span {
    border-bottom: 3px solid #00844a;
    border-left: 3px solid #00844a;
    height: 11px;
    left: 13px;
    position: absolute;
    top: 12px;
    transform: rotate(-45deg);
    width: 19px;
}

.status-icon.error {
    border-color: #c62828;
}

.status-icon.error::before,
.status-icon.error::after {
    background: #c62828;
    content: "";
    height: 3px;
    left: 11px;
    position: absolute;
    top: 20px;
    transform: rotate(45deg);
    width: 22px;
}

.status-icon.error::after {
    transform: rotate(-45deg);
}

h1 {
    font-size: 24px;
    font-weight: 400;
    line-height: 1.2;
    margin: 0 0 10px;
}

.message {
    color: #434445;
    font-size: 16px;
    line-height: 1.45;
    margin: 0;
    max-width: 340px;
}

.close-hint {
    border-top: 1px solid #d9d9da;
    color: #606162;
    font-size: 14px;
    line-height: 1.4;
    margin: 26px 0 0;
    padding-top: 18px;
    width: 100%;
}

@media (max-width: 560px) {
    .page-shell {
        padding: 16px;
    }

    .card {
        min-height: 344px;
        padding: 28px 24px;
    }
}
"""


def _render_callback_page(message: str, success: bool) -> bytes:
    """Render the self-contained browser page shown after the PKCE callback."""
    status_class = "success" if success else "error"
    heading = "Login complete" if success else "Login callback unavailable"
    icon = f'<div class="status-icon {status_class}" aria-hidden="true"><span></span></div>'
    close_hint = (
        '<p class="close-hint">You can close this browser tab and return to slcli.</p>'
        if success
        else ""
    )
    return f"""<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <meta name="color-scheme" content="light">
    <title>{heading} | SystemLink</title>
    <style>{_CALLBACK_PAGE_CSS}</style>
</head>
<body>
    <main class="page-shell" style='background: {_CALLBACK_PAGE_BACKGROUND};'>
        <section class="card" aria-labelledby="page-title">
            <img
                class="brand-logo"
                src="data:image/svg+xml;base64,{_SYSTEMLINK_LOGO_DATA}"
                alt="SystemLink"
            >
            {icon}
            <h1 id="page-title">{heading}</h1>
            <p class="message" role="status">{html.escape(message)}</p>
            {close_hint}
        </section>
    </main>
</body>
</html>""".encode("utf-8")


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
    expected_state: Optional[str] = None


class _CallbackHandler(BaseHTTPRequestHandler):
    """Receive one OAuth callback without logging its query string."""

    def do_GET(self) -> None:  # noqa: N802
        """Capture callback parameters and display a completion page."""
        parsed = urlparse(self.path)
        if parsed.path != "/callback":
            self._respond(404, "The login callback path was not found.")
            return

        callback_params = parse_qs(parsed.query, keep_blank_values=True)
        self.server.callback_params = callback_params  # type: ignore[attr-defined]
        expected_state = self.server.expected_state  # type: ignore[attr-defined]
        status, message = _callback_response(callback_params, expected_state)
        self._respond(status, message)

    def log_message(self, format: str, *args: Any) -> None:
        """Keep authorization codes and errors out of stderr logs."""

    def _respond(self, status: int, message: str) -> None:
        body = _render_callback_page(message, status == 200)
        self.send_response(status)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'none'; style-src 'unsafe-inline'; img-src data:",
        )
        self.send_header("X-Content-Type-Options", "nosniff")
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
    if refresh_token is not None and (not isinstance(refresh_token, str) or not refresh_token):
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


def _callback_response(
    params: Mapping[str, list[str]], expected_state: Optional[str]
) -> tuple[int, str]:
    """Return the browser response for a received OAuth callback."""
    if _single_callback_value(params, "state") != expected_state:
        return 400, "The login callback could not be verified."
    if _single_callback_value(params, "error"):
        return 400, "SystemLink sign-in was denied."
    if not _single_callback_value(params, "code"):
        return 400, "The login callback did not contain an authorization code."
    return 200, "Your SystemLink sign-in was successful."


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
    callback_port: int = PKCE_CALLBACK_PORT,
) -> PkceLoginResult:
    """Run the browser PKCE flow and return credentials for bearer requests."""
    if not client_id.strip():
        raise PkceError("PKCE client ID cannot be empty.")
    if not scopes:
        raise PkceError("At least one PKCE scope is required.")
    if timeout_seconds <= 0:
        raise PkceError("PKCE timeout must be greater than zero.")
    if not 0 <= callback_port <= 65535:
        raise PkceError("PKCE callback port must be between 0 and 65535.")

    verifier, challenge = generate_pkce_pair()
    state = secrets.token_urlsafe(32)
    try:
        server = _CallbackServer(("127.0.0.1", callback_port), _CallbackHandler)
        server.expected_state = state
    except OSError as exc:
        raise PkceError(f"Could not bind the PKCE callback port {callback_port}: {exc}") from exc
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
    previous_values = {
        credential: keyring.get_password(
            PKCE_KEYRING_SERVICE, _credential_key(profile_name, credential)
        )
        for credential in _PKCE_CREDENTIAL_NAMES
    }

    try:
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
            _delete_pkce_credential(profile_name, "refresh-token")
        if expires_at is not None:
            keyring.set_password(
                PKCE_KEYRING_SERVICE,
                _credential_key(profile_name, "access-expires-at"),
                str(expires_at),
            )
        else:
            _delete_pkce_credential(profile_name, "access-expires-at")
        _delete_pkce_credential(profile_name, "session-key")
        _delete_pkce_credential(profile_name, "session-expires-at")
    except Exception:
        for credential, value in previous_values.items():
            try:
                if value is None:
                    keyring.delete_password(
                        PKCE_KEYRING_SERVICE, _credential_key(profile_name, credential)
                    )
                else:
                    keyring.set_password(
                        PKCE_KEYRING_SERVICE,
                        _credential_key(profile_name, credential),
                        value,
                    )
            except Exception:
                pass
        raise


def _delete_pkce_credential(profile_name: str, credential: str) -> None:
    """Delete an optional PKCE credential without failing the save operation."""
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
    refresh_token_to_save = result.refresh_token or refresh_token
    save_pkce_credentials(
        profile_name, result.access_token, refresh_token_to_save, result.expires_at
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
