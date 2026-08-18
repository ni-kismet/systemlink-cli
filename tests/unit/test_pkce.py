"""Unit tests for the prototype PKCE login flow."""

import base64
import hashlib
import json
from typing import Any, Mapping
from urllib.parse import parse_qs, urlparse

from click.testing import CliRunner

from slcli.main import cli
from slcli.pkce import (
    PkceError,
    PkceLoginResult,
    build_authorization_url,
    generate_pkce_pair,
    get_pkce_access_token,
    perform_pkce_login,
    refresh_pkce_credentials,
    save_pkce_credentials,
)


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


def test_perform_pkce_login_returns_bearer_token(
    monkeypatch: Any,
) -> None:
    """The browser callback is exchanged for an access token without a session exchange."""
    import slcli.pkce as pkce

    class FakeServer:
        server_address = ("127.0.0.1", 4321)

        def __init__(self, *_args: Any) -> None:
            server_bind.append(_args[0])
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
    monkeypatch.setattr(
        config_click,
        "check_service_status",
        lambda _url, credential, auth_scheme: {
            "server_reachable": True,
            "auth_valid": credential == "access-token" and auth_scheme == "bearer",
            "services": {"Auth": "ok"},
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
