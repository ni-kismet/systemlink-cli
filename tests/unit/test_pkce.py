"""Unit tests for the prototype PKCE login flow."""

import base64
import hashlib
import json
from typing import Any, Mapping
from unittest.mock import MagicMock
from urllib.parse import parse_qs, urlparse

import pytest
from click.testing import CliRunner

from slcli.main import cli
from slcli.pkce import (
    PkceError,
    PkceLoginResult,
    _callback_response,
    _render_callback_page,
    build_authorization_url,
    generate_pkce_pair,
    get_pkce_access_token,
    perform_pkce_login,
    refresh_pkce_credentials,
    save_pkce_credentials,
)


def test_render_callback_success_page_is_branded_and_escapes_message() -> None:
    """The callback page matches the login styling without exposing callback values."""
    page = _render_callback_page("Login <complete> authorization-code", True).decode("utf-8")

    assert "Login complete | SystemLink" in page
    assert "Source Sans Pro" in page
    assert "00ad7c" in page
    assert "SystemLink" in page
    assert 'src="data:image/svg+xml;base64,' in page
    assert 'alt="SystemLink"' in page
    assert "brand-mark" not in page
    assert "status-icon success" in page
    assert "You can close this browser tab and return to slcli." in page
    assert "Login &lt;complete&gt; authorization-code" in page
    assert "<script>" not in page


def test_render_callback_error_page_omits_close_instruction() -> None:
    """Error callback pages retain the branded shell without implying successful login."""
    page = _render_callback_page("The login callback path was not found.", False).decode("utf-8")

    assert "Login callback unavailable | SystemLink" in page
    assert "status-icon error" in page
    assert "You can close this browser tab and return to slcli." not in page


class Response:
    """Small requests response double for token calls."""

    def __init__(self, payload: Mapping[str, Any]) -> None:
        """Initialize a response with a JSON payload."""
        self.payload = dict(payload)

    def raise_for_status(self) -> None:
        """Treat the mocked response as successful."""

    def json(self) -> Mapping[str, Any]:
        """Return the mocked JSON payload."""
        return self.payload


def test_generate_pkce_pair_uses_s256() -> None:
    """The generated challenge must match the verifier and use base64url encoding."""
    verifier, challenge = generate_pkce_pair()

    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest())
    assert challenge == expected.rstrip(b"=").decode()
    assert len(verifier) >= 43
    assert "=" not in verifier


def test_build_authorization_url_contains_required_parameters() -> None:
    """Authorization URLs contain the native-app PKCE parameters."""
    url = build_authorization_url(
        "https://web.example/nitoken/v1/authorize",
        "cli-client",
        "http://127.0.0.1:4321/callback",
        "state-value",
        "challenge-value",
        ("openid", "offline_access"),
    )
    query = parse_qs(urlparse(url).query)

    assert query["response_type"] == ["code"]
    assert query["client_id"] == ["cli-client"]
    assert query["redirect_uri"] == ["http://127.0.0.1:4321/callback"]
    assert query["scope"] == ["openid offline_access"]
    assert query["state"] == ["state-value"]
    assert query["code_challenge_method"] == ["S256"]


def test_callback_response_rejects_unverified_callback() -> None:
    """The browser page must not claim success before callback validation."""
    status, message = _callback_response(
        {"state": ["wrong-state"], "code": ["authorization-code"]}, "expected-state"
    )

    assert status == 400
    assert message == "The login callback could not be verified."


def test_callback_response_rejects_authorization_error() -> None:
    """The browser page must show an error when the provider denies authorization."""
    status, message = _callback_response(
        {"state": ["expected-state"], "error": ["access_denied"]}, "expected-state"
    )

    assert status == 400
    assert message == "SystemLink sign-in was denied."


def test_perform_pkce_login_returns_bearer_token(
    monkeypatch: Any,
) -> None:
    """The browser callback is exchanged for an access token without a session exchange."""
    import slcli.pkce as pkce

    class FakeServer:
        def __init__(self, *_args: Any) -> None:
            server_bind.append(_args[0])
            self.server_address = _args[0]
            self.callback_params = None

        def server_close(self) -> None:
            pass

    authorization_url: list[str] = []
    server_bind: list[tuple[str, int]] = []
    monkeypatch.setattr(pkce, "_CallbackServer", FakeServer)
    monkeypatch.setattr(pkce, "get_ssl_verify", lambda _url: True)

    def open_browser(_self: Any, url: str, new: int = 0) -> bool:
        """Capture the authorization URL and report a successful browser launch."""
        authorization_url.append(url)
        return True

    monkeypatch.setattr(
        pkce,
        "webbrowser",
        type(
            "Browser",
            (),
            {"open": open_browser},
        )(),
    )

    def wait_for_callback(_server: Any, _timeout: int) -> Mapping[str, list[str]]:
        query = parse_qs(urlparse(authorization_url[0]).query)
        assert query["scope"] == ["openid profile email offline_access"]
        return {"state": query["state"], "code": ["authorization-code"]}

    monkeypatch.setattr(pkce, "_wait_for_callback", wait_for_callback)
    requests_seen: list[tuple[str, Any]] = []

    def post(url: str, **kwargs: Any) -> Response:
        requests_seen.append((url, kwargs))
        assert kwargs["data"]["code"] == "authorization-code"
        assert kwargs["data"]["code_verifier"]
        return Response({"access_token": "access-token", "refresh_token": "refresh-token"})

    monkeypatch.setattr(pkce.requests, "post", post)

    result = perform_pkce_login("https://web.example", "client-id")

    assert result == PkceLoginResult("access-token", "refresh-token")
    assert server_bind == [("127.0.0.1", pkce.PKCE_CALLBACK_PORT)]
    assert [item[0] for item in requests_seen] == ["https://web.example/nitoken/v1/token"]


def test_perform_pkce_login_supports_a_custom_callback_port(monkeypatch: Any) -> None:
    """Registered loopback clients can select a port other than the default."""
    import slcli.pkce as pkce

    class FakeServer:
        def __init__(self, *_args: Any) -> None:
            server_bind.append(_args[0])
            self.server_address = _args[0]
            self.callback_params = None

        def server_close(self) -> None:
            pass

    authorization_url: list[str] = []
    server_bind: list[tuple[str, int]] = []
    monkeypatch.setattr(pkce, "_CallbackServer", FakeServer)
    monkeypatch.setattr(pkce, "get_ssl_verify", lambda _url: True)

    def open_browser(url: str, new: int = 0) -> bool:
        authorization_url.append(url)
        return True

    monkeypatch.setattr(pkce.webbrowser, "open", open_browser)
    monkeypatch.setattr(
        pkce,
        "_wait_for_callback",
        lambda *_args: {
            "state": [parse_qs(urlparse(authorization_url[0]).query)["state"][0]],
            "code": ["code"],
        },
    )
    monkeypatch.setattr(
        pkce.requests,
        "post",
        lambda *_args, **_kwargs: Response({"access_token": "access-token"}),
    )

    perform_pkce_login("https://web.example", "client-id", callback_port=4320)

    assert server_bind == [("127.0.0.1", 4320)]
    query = parse_qs(urlparse(authorization_url[0]).query)
    assert query["redirect_uri"] == ["http://127.0.0.1:4320/callback"]


def test_perform_pkce_login_rejects_state_mismatch(monkeypatch: Any) -> None:
    """A callback from another request must not be accepted."""
    import slcli.pkce as pkce

    class FakeServer:
        server_address = ("127.0.0.1", 4321)

        def __init__(self, *_args: Any) -> None:
            pass

        def server_close(self) -> None:
            pass

    monkeypatch.setattr(pkce, "_CallbackServer", FakeServer)
    monkeypatch.setattr(pkce.webbrowser, "open", lambda *_args, **_kwargs: True)
    monkeypatch.setattr(
        pkce, "_wait_for_callback", lambda *_args: {"state": ["wrong-state"], "code": ["code"]}
    )

    try:
        perform_pkce_login("https://web.example", "client-id")
    except PkceError as exc:
        assert str(exc) == "Login callback state did not match the request."
    else:
        raise AssertionError("Expected state mismatch")


def test_pkce_credentials_are_keyring_backed(monkeypatch: Any) -> None:
    """PKCE access and refresh secrets are never serialized in a profile."""
    import slcli.pkce as pkce

    values: dict[str, str] = {}
    monkeypatch.setattr(
        pkce.keyring,
        "set_password",
        lambda _s, key, value: values.__setitem__(key, value),
    )
    monkeypatch.setattr(pkce.keyring, "get_password", lambda _s, key: values.get(key))

    save_pkce_credentials("test", "access-token", "refresh-token")

    assert get_pkce_access_token("test") == "access-token"
    assert values["PKCE:test:refresh-token"] == "refresh-token"
    assert "api-key" not in json.dumps({"auth-mode": "pkce"})


def test_save_pkce_credentials_restores_previous_values_on_failure(monkeypatch: Any) -> None:
    """A partial keyring update must not replace the existing credentials."""
    import slcli.pkce as pkce

    values = {
        "PKCE:test:access-token": "old-access-token",
        "PKCE:test:refresh-token": "old-refresh-token",
        "PKCE:test:access-expires-at": "100.0",
        "PKCE:test:session-key": "old-session-key",
        "PKCE:test:session-expires-at": "200.0",
    }
    previous_values = values.copy()

    monkeypatch.setattr(pkce.keyring, "get_password", lambda _service, key: values.get(key))

    def set_password(_service: str, key: str, value: str) -> None:
        if key == "PKCE:test:access-expires-at" and value == "300.0":
            raise RuntimeError("keyring unavailable")
        values[key] = value

    monkeypatch.setattr(pkce.keyring, "set_password", set_password)
    monkeypatch.setattr(
        pkce.keyring, "delete_password", lambda _service, key: values.pop(key, None)
    )

    with pytest.raises(RuntimeError, match="keyring unavailable"):
        save_pkce_credentials("test", "new-access-token", "new-refresh-token", 300.0)

    assert values == previous_values


def test_refresh_pkce_credentials_rotates_tokens(monkeypatch: Any) -> None:
    """Refreshing credentials replaces the old refresh and access tokens."""
    import slcli.pkce as pkce

    values = {
        "PKCE:test:refresh-token": "old-refresh-token",
    }
    monkeypatch.setattr(pkce, "get_ssl_verify", lambda _url: True)
    monkeypatch.setattr(pkce.keyring, "get_password", lambda _s, key: values.get(key))
    monkeypatch.setattr(
        pkce.keyring,
        "set_password",
        lambda _s, key, value: values.__setitem__(key, value),
    )
    monkeypatch.setattr(pkce.keyring, "delete_password", lambda *_args: None)

    requests_seen: list[tuple[str, Any]] = []

    def post(url: str, **kwargs: Any) -> Response:
        requests_seen.append((url, kwargs))
        assert kwargs["data"]["refresh_token"] == "old-refresh-token"
        return Response(
            {
                "access_token": "new-access-token",
                "refresh_token": "new-refresh-token",
                "expires_in": 3600,
            }
        )

    monkeypatch.setattr(
        pkce.requests,
        "post",
        post,
    )

    result = refresh_pkce_credentials("test", "https://web.example", "client-id")

    assert result.access_token == "new-access-token"
    assert values["PKCE:test:access-token"] == "new-access-token"
    assert values["PKCE:test:refresh-token"] == "new-refresh-token"
    assert "PKCE:test:access-expires-at" in values
    assert [item[0] for item in requests_seen] == ["https://web.example/nitoken/v1/token"]


def test_refresh_pkce_credentials_keeps_existing_refresh_token_when_omitted(
    monkeypatch: Any,
) -> None:
    """A refresh response may omit a replacement while retaining the old token."""
    import slcli.pkce as pkce

    values = {"PKCE:test:refresh-token": "old-refresh-token"}
    monkeypatch.setattr(pkce, "get_ssl_verify", lambda _url: True)
    monkeypatch.setattr(pkce.keyring, "get_password", lambda _s, key: values.get(key))
    monkeypatch.setattr(
        pkce.keyring,
        "set_password",
        lambda _s, key, value: values.__setitem__(key, value),
    )
    monkeypatch.setattr(pkce.keyring, "delete_password", lambda *_args: None)
    monkeypatch.setattr(
        pkce.requests,
        "post",
        lambda *_args, **_kwargs: Response({"access_token": "new-access-token"}),
    )

    refresh_pkce_credentials("test", "https://web.example", "client-id")

    assert values["PKCE:test:refresh-token"] == "old-refresh-token"


def test_login_pkce_uses_bearer_token_and_stores_metadata(monkeypatch: Any, tmp_path: Any) -> None:
    """The CLI can create a PKCE profile without prompting for an API key."""
    import slcli.config_click as config_click
    import slcli.pkce as pkce

    config_file = tmp_path / "config.json"
    monkeypatch.setattr(
        "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
    )
    monkeypatch.setattr(
        pkce,
        "perform_pkce_login",
        lambda *_args, **_kwargs: PkceLoginResult("access-token", "refresh-token"),
    )
    monkeypatch.setattr(pkce, "save_pkce_credentials", lambda *_args, **_kwargs: None)
    mock_web_probe = MagicMock(
        return_value={
            "server_reachable": True,
            "auth_valid": True,
            "services": {"Web Server": "ok"},
            "platform": "unknown",
        }
    )
    monkeypatch.setattr(config_click, "check_web_server_auth", mock_web_probe)
    monkeypatch.setattr(
        config_click,
        "check_service_status",
        lambda *_args, **_kwargs: {
            "server_reachable": True,
            "auth_valid": True,
            "services": {"Auth": "ok", "Work Order": "ok"},
            "platform": "SLE",
        },
    )

    result = CliRunner().invoke(
        cli,
        [
            "login",
            "--profile",
            "pkce",
            "--url",
            "https://api.example",
            "--web-url",
            "https://web.example",
            "--auth",
            "pkce",
            "--client-id",
            "client-id",
        ],
        input="\n",
    )

    assert result.exit_code == 0, result.output
    saved = json.loads(config_file.read_text())
    profile = saved["profiles"]["pkce"]
    assert profile["auth-mode"] == "pkce"
    assert profile["pkce-client-id"] == "client-id"
    assert "api-key" not in profile
    assert "PKCE bearer token:  ✓ Authorized" in result.output
    assert mock_web_probe.call_args_list == [
        (("https://web.example", ""), {"auth_scheme": "bearer"})
    ]
