"""Unit tests for the prototype PKCE login flow."""

import base64
import hashlib
import json
from pathlib import Path
from typing import Any, Mapping
from unittest.mock import MagicMock
from urllib.parse import parse_qs, urlparse

import pytest
import requests
from click.testing import CliRunner

from slcli.credentials import CredentialStoreError
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
    resolve_pkce_token,
    save_pkce_credentials,
)
from slcli.profiles import Profile, ProfileConfig


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
    monkeypatch.setattr(pkce, "get_ssl_verify", lambda *_args: True)

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
    monkeypatch.setattr(pkce, "get_ssl_verify", lambda *_args: True)

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


def test_pkce_credentials_are_stored_as_one_bundle(monkeypatch: Any) -> None:
    """PKCE access and refresh secrets are never serialized in a profile."""
    import slcli.pkce as pkce

    values: dict[tuple[str, str], str] = {}
    monkeypatch.setattr(
        pkce,
        "set_credential",
        lambda profile_id, name, value, _store: values.__setitem__((profile_id, name), value),
    )
    monkeypatch.setattr(
        pkce,
        "get_credential",
        lambda profile_id, name, _store: values.get((profile_id, name)),
    )

    save_pkce_credentials("test", "access-token", "refresh-token")

    assert get_pkce_access_token("test") == "access-token"
    bundle = json.loads(values[("test", "pkce")])
    assert bundle["refresh-token"] == "refresh-token"
    assert "api-key" not in json.dumps({"auth-mode": "pkce"})


@pytest.mark.parametrize(
    "bundle_text", ['["not an object"]', '"not an object"', '{"access-token": []}']
)
def test_get_pkce_access_token_rejects_non_object_bundle(
    monkeypatch: Any, bundle_text: str
) -> None:
    """Invalid shapes and token types are rejected as malformed bundles."""
    monkeypatch.setattr("slcli.pkce.get_credential", lambda *_args, **_kwargs: bundle_text)

    with pytest.raises(PkceError, match="Stored PKCE credentials are invalid"):
        get_pkce_access_token("test")


@pytest.mark.parametrize(
    "bundle_text", ['["not an object"]', '"not an object"', '{"refresh-token": []}']
)
def test_refresh_pkce_credentials_rejects_non_object_bundle(
    monkeypatch: Any, bundle_text: str
) -> None:
    """Refresh reports a controlled PKCE error for invalid bundles."""
    monkeypatch.setattr("slcli.pkce.get_credential", lambda *_args, **_kwargs: bundle_text)

    with pytest.raises(PkceError, match="Stored PKCE credentials are invalid"):
        refresh_pkce_credentials("test", "https://web.example", "client-id")


@pytest.mark.parametrize("expiry", ["NaN", "Infinity", "-Infinity", 10**400, True])
def test_get_pkce_access_token_rejects_invalid_expiry(monkeypatch: Any, expiry: Any) -> None:
    """Non-finite, overflowing, and boolean expiries cannot bypass token validation."""
    bundle = json.dumps({"access-token": "token", "access-expires-at": expiry})
    monkeypatch.setattr("slcli.pkce.get_credential", lambda *_args: bundle)

    with pytest.raises(PkceError, match="Stored PKCE credentials are invalid"):
        get_pkce_access_token("test")


def test_save_pkce_credentials_reports_store_failure(monkeypatch: Any) -> None:
    """A failed bundle write is reported as a PKCE storage error."""
    import slcli.pkce as pkce

    from slcli.credentials import CredentialStoreError

    monkeypatch.setattr(
        pkce,
        "set_credential",
        lambda *_args: (_ for _ in ()).throw(CredentialStoreError("store unavailable")),
    )

    with pytest.raises(PkceError, match="store unavailable"):
        save_pkce_credentials("test", "new-access-token", "new-refresh-token", 300.0)


def test_refresh_pkce_credentials_rotates_tokens(monkeypatch: Any) -> None:
    """Refreshing credentials replaces the old refresh and access tokens."""
    import slcli.pkce as pkce

    values = {("test", "pkce"): json.dumps({"refresh-token": "old-refresh-token"})}
    monkeypatch.setattr(pkce, "get_ssl_verify", lambda *_args: True)
    monkeypatch.setattr(
        pkce,
        "get_credential",
        lambda profile_id, name, _store: values.get((profile_id, name)),
    )
    monkeypatch.setattr(
        pkce,
        "set_credential",
        lambda profile_id, name, value, _store: values.__setitem__((profile_id, name), value),
    )

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
    bundle = json.loads(values[("test", "pkce")])
    assert bundle["access-token"] == "new-access-token"
    assert bundle["refresh-token"] == "new-refresh-token"
    assert bundle["access-expires-at"] is not None
    assert [item[0] for item in requests_seen] == ["https://web.example/nitoken/v1/token"]


def test_refresh_pkce_credentials_keeps_existing_refresh_token_when_omitted(
    monkeypatch: Any,
) -> None:
    """A refresh response may omit a replacement while retaining the old token."""
    import slcli.pkce as pkce

    values = {("test", "pkce"): json.dumps({"refresh-token": "old-refresh-token"})}
    monkeypatch.setattr(pkce, "get_ssl_verify", lambda *_args: True)
    monkeypatch.setattr(
        pkce,
        "get_credential",
        lambda profile_id, name, _store: values.get((profile_id, name)),
    )
    monkeypatch.setattr(
        pkce,
        "set_credential",
        lambda profile_id, name, value, _store: values.__setitem__((profile_id, name), value),
    )
    monkeypatch.setattr(
        pkce.requests,
        "post",
        lambda *_args, **_kwargs: Response({"access_token": "new-access-token"}),
    )

    refresh_pkce_credentials("test", "https://web.example", "client-id")

    assert json.loads(values[("test", "pkce")])["refresh-token"] == "old-refresh-token"


@pytest.mark.parametrize("store", ["os", "file"])
@pytest.mark.parametrize("expiry", [None, 1061.0, 1060.0, 999.0])
@pytest.mark.parametrize("replacement", [None, "rotated-refresh"])
def test_resolve_pkce_token_lifecycle(
    monkeypatch: Any, store: str, expiry: Any, replacement: Any
) -> None:
    """Resolution assesses expiry, persists rotation, and reports provenance."""
    values = {
        "access-token": "cached-access",
        "refresh-token": "old-refresh",
        "access-expires-at": expiry,
    }
    read = MagicMock(return_value=json.dumps(values))
    write = MagicMock()
    payload = {"access_token": "fresh-access", "expires_in": 3600}
    if replacement:
        payload["refresh_token"] = replacement
    post = MagicMock(return_value=Response(payload))
    monkeypatch.setattr("slcli.pkce.time.time", lambda: 1000.0)
    monkeypatch.setattr("slcli.pkce.get_credential", read)
    monkeypatch.setattr("slcli.pkce.set_credential", write)
    monkeypatch.setattr("slcli.pkce.requests.post", post)
    monkeypatch.setattr("slcli.pkce.get_ssl_verify", lambda *_args: True)
    profile = Profile(
        name="test",
        server="https://api.example",
        web_url="https://web.example",
        pkce_client_id="client-id",
        credential_store=store,
        auth_mode="pkce",
    )

    result = resolve_pkce_token(profile)

    read.assert_called_with(profile.credential_id, "pkce", store)
    if expiry is None or expiry > 1060:
        assert result.access_token == "cached-access"
        assert result.source == f"{store}:pkce"
        post.assert_not_called()
        write.assert_not_called()
    else:
        assert result.access_token == "fresh-access"
        assert result.source == f"{store}:pkce-refresh"
        assert post.call_args.args == ("https://web.example/nitoken/v1/token",)
        assert post.call_args.kwargs["data"] == {
            "grant_type": "refresh_token",
            "client_id": "client-id",
            "refresh_token": "old-refresh",
        }
        assert write.call_args.args[:2] == (profile.credential_id, "pkce")
        assert write.call_args.args[3] == store
        assert json.loads(write.call_args.args[2]) == {
            "access-token": "fresh-access",
            "refresh-token": replacement or "old-refresh",
            "access-expires-at": 4600.0,
        }


def test_resolve_pkce_token_refresh_persists_to_file(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A refreshed bundle survives reload and is reused without another token request."""
    config_path = tmp_path / "config.json"
    monkeypatch.setattr(ProfileConfig, "get_config_path", classmethod(lambda cls: config_path))
    profile = Profile(
        name="test",
        server="https://api.example",
        web_url="https://web.example",
        pkce_client_id="client-id",
        auth_mode="pkce",
        credential_store="file",
        pkce_credentials={
            "access-token": "expired",
            "refresh-token": "old-refresh",
            "access-expires-at": 999.0,
        },
    )
    config = ProfileConfig()
    config.add_profile(profile)
    config.save()
    monkeypatch.setattr("slcli.pkce.time.time", lambda: 1000.0)
    monkeypatch.setattr("slcli.pkce.get_ssl_verify", lambda *_args: True)
    post = MagicMock(
        return_value=Response(
            {"access_token": "fresh-access", "refresh_token": "rotated-refresh", "expires_in": 3600}
        )
    )
    monkeypatch.setattr("slcli.pkce.requests.post", post)

    result = resolve_pkce_token(profile)

    assert result.access_token == "fresh-access"
    assert result.source == "file:pkce-refresh"
    reloaded = ProfileConfig.load().profiles["test"]
    assert reloaded.pkce_credentials == {
        "access-token": "fresh-access",
        "refresh-token": "rotated-refresh",
        "access-expires-at": 4600.0,
    }
    cached = resolve_pkce_token(reloaded)
    assert cached.access_token == "fresh-access"
    assert cached.source == "file:pkce"
    post.assert_called_once()


@pytest.mark.parametrize(
    "failure",
    ["missing", "no-refresh", "no-web", "no-client", "refresh", "persist"],
)
@pytest.mark.parametrize("emit_error", [True, False])
def test_resolve_pkce_token_unavailable(monkeypatch: Any, failure: str, emit_error: bool) -> None:
    """Unavailable or unpersisted credentials never yield a bearer token."""
    bundle = (
        None
        if failure == "missing"
        else json.dumps({"refresh-token": None if failure == "no-refresh" else "refresh"})
    )
    monkeypatch.setattr("slcli.pkce.get_credential", lambda *_args: bundle)
    monkeypatch.setattr("slcli.pkce.get_ssl_verify", lambda *_args: True)
    post = MagicMock(return_value=Response({"access_token": "fresh"}))
    if failure == "refresh":
        post.side_effect = requests.RequestException("unavailable")
    write = MagicMock(side_effect=CredentialStoreError("store unavailable"))
    monkeypatch.setattr("slcli.pkce.requests.post", post)
    monkeypatch.setattr("slcli.pkce.set_credential", write)
    profile = Profile(
        name="test",
        server="https://api.example",
        web_url="" if failure == "no-web" else "https://web.example",
        pkce_client_id=None if failure == "no-client" else "client-id",
        auth_mode="pkce",
    )

    with pytest.raises(PkceError) as error:
        resolve_pkce_token(profile, emit_error=emit_error)

    assert str(error.value) == (
        "PKCE bearer token for profile 'test' is unavailable. "
        "Run 'slcli login --profile test --auth pkce' again."
        if emit_error
        else "PKCE bearer token not found."
    )
    if failure not in ("refresh", "persist"):
        post.assert_not_called()
    if failure != "persist":
        write.assert_not_called()


@pytest.mark.parametrize("bundle", ["[]", '{"access-token": []}', '{"access-expires-at": true}'])
def test_resolve_pkce_token_malformed(monkeypatch: Any, bundle: str) -> None:
    """Malformed cached credentials are reported without attempting refresh."""
    monkeypatch.setattr("slcli.pkce.get_credential", lambda *_args: bundle)
    post = MagicMock()
    monkeypatch.setattr("slcli.pkce.requests.post", post)
    profile = Profile(
        name="test",
        server="https://api.example",
        web_url="https://web.example",
        pkce_client_id="client-id",
        auth_mode="pkce",
    )

    with pytest.raises(PkceError, match="Stored PKCE credentials are invalid"):
        resolve_pkce_token(profile)

    post.assert_not_called()


def test_resolve_pkce_token_store_unreadable(monkeypatch: Any) -> None:
    """Store access failures remain visible rather than becoming missing tokens."""
    monkeypatch.setattr(
        "slcli.pkce.get_credential", MagicMock(side_effect=CredentialStoreError("locked"))
    )
    with pytest.raises(PkceError, match="Could not read PKCE credentials: locked"):
        resolve_pkce_token(Profile(name="test", server="https://api.example"))


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
            "platform": "SLE",
        }
    )
    monkeypatch.setattr(config_click, "check_web_server_auth", mock_web_probe)
    mock_service_probe = MagicMock(return_value={"platform": "SLE"})
    monkeypatch.setattr(config_click, "check_service_status", mock_service_probe)

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
    assert mock_web_probe.call_args_list[-1] == (
        ("https://web.example", "access-token"),
        {"auth_scheme": "bearer"},
    )
    assert mock_service_probe.call_args_list[-1] == (
        ("https://web.example", "access-token"),
        {"auth_scheme": "bearer"},
    )
