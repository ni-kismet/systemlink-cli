from __future__ import annotations

import sys
from pathlib import Path

import pytest

from slcli.web_editor import (
    DFFWebEditor,
    _build_proxy_url,
    _resolve_proxy_target,
    _validated_proxy_origin,
    _validated_proxy_path,
    _validated_proxy_query_params,
)

ESSENTIAL_FILES = ["index.html", "editor.js", "README.md"]


def _make_assets(base: Path) -> None:
    base.mkdir(parents=True, exist_ok=True)
    for name in ESSENTIAL_FILES:
        (base / name).write_text(f"src-{name}")


def test_source_from_meipass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that DFFWebEditor resolves editor directory from PyInstaller MEIPASS."""
    meipass = tmp_path / "meipass"
    _make_assets(meipass / "dff-editor")

    monkeypatch.setattr(sys, "_MEIPASS", str(meipass), raising=False)
    monkeypatch.setattr(sys, "frozen", False, raising=False)

    editor = DFFWebEditor(port=0)

    # Verify it resolved to the MEIPASS location
    assert editor._editor_dir == meipass / "dff-editor"


def test_source_from_frozen_onedir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that DFFWebEditor resolves editor directory from frozen onedir layout."""
    monkeypatch.setattr(sys, "_MEIPASS", None, raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    app_dir = tmp_path / "appdir"
    assets = app_dir / "dff-editor"
    _make_assets(assets)

    fake_executable = app_dir / "slcli"
    fake_executable.write_text("")
    monkeypatch.setattr(sys, "executable", str(fake_executable))

    editor = DFFWebEditor(port=0)

    # Verify it resolved to the frozen onedir location
    assert editor._editor_dir == assets


def test_source_from_site_packages(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test that DFFWebEditor resolves editor directory from site-packages."""
    import slcli.web_editor as web_editor

    monkeypatch.setattr(sys, "_MEIPASS", None, raising=False)
    monkeypatch.setattr(sys, "frozen", False, raising=False)

    site_root = tmp_path / "site-packages"
    slcli_pkg = site_root / "slcli"
    slcli_pkg.mkdir(parents=True)

    fake_module_file = slcli_pkg / "web_editor.py"
    monkeypatch.setattr(web_editor, "__file__", str(fake_module_file))

    _make_assets(site_root / "dff-editor")

    editor = DFFWebEditor(port=0)

    # Verify it resolved to the site-packages location
    assert editor._editor_dir == site_root / "dff-editor"


@pytest.mark.parametrize(
    ("api_base", "message"),
    [
        ("ftp://example.test", r"HTTP\(S\)"),
        ("https://user:pass@example.test", "embedded credentials"),
        ("https://example.test/nested", "without path"),
        ("https://example.test?query=1", "without path"),
    ],
)
def test_validated_proxy_origin_rejects_unsafe_base_urls(api_base: str, message: str) -> None:
    """Proxy origin validation should reject malformed or overly broad base URLs."""
    with pytest.raises(ValueError, match=message):
        _validated_proxy_origin(api_base)


def test_build_proxy_url_uses_validated_origin() -> None:
    """Proxy URLs should be rebuilt from the validated origin and allowlisted path."""
    scheme, netloc = _validated_proxy_origin("https://systemlink.example.test")

    url = _build_proxy_url(
        origin_scheme=scheme,
        origin_netloc=netloc,
        target_path="/nidynamicformfields/v1/configurations",
    )

    assert url == "https://systemlink.example.test/nidynamicformfields/v1/configurations"


@pytest.mark.parametrize(
    "request_path",
    [
        "/nidynamicformfields/v1/../niauth/v1/tokens",
        "/nidynamicformfields/v1/%2e%2e/niauth/v1/tokens",
        "/nidynamicformfields/v1/%2E%2E/niauth/v1/tokens",
        "/nidynamicformfields/v1/%2e%2e%2fniuser/v1/workspaces",
    ],
)
def test_validated_proxy_path_rejects_dot_segment_bypass(request_path: str) -> None:
    """Proxy path validation should reject raw and encoded dot-segment bypass attempts."""
    with pytest.raises(ValueError, match="dot-segments"):
        _validated_proxy_path(request_path)


def test_validated_proxy_path_accepts_allowlisted_path() -> None:
    """Proxy path validation should preserve simple absolute allowlisted paths."""
    assert (
        _validated_proxy_path("/nidynamicformfields/v1/configurations")
        == "/nidynamicformfields/v1/configurations"
    )


def test_validated_proxy_query_params_parse_pairs() -> None:
    """Proxy query validation should parse key-value pairs."""
    assert _validated_proxy_query_params("take=25&skip=0") == {"take": ["25"], "skip": ["0"]}


def test_validated_proxy_query_params_reject_malformed_query() -> None:
    """Proxy query validation should reject malformed key-value input."""
    with pytest.raises(ValueError, match="invalid query string"):
        _validated_proxy_query_params("take=25&broken")


def test_resolve_proxy_target_for_workspaces() -> None:
    """Workspace proxying should resolve to a fixed path with validated params."""
    assert _resolve_proxy_target("GET", "/niuser/v1/workspaces", "take=100&skip=0") == (
        "/niuser/v1/workspaces",
        {"take": "100", "skip": "0"},
    )


def test_resolve_proxy_target_for_resolved_configuration() -> None:
    """Resolved configuration proxying should keep only the allowed ID parameter."""
    assert _resolve_proxy_target(
        "GET",
        "/nidynamicformfields/v1/resolved-configuration",
        "configurationId=cfg-123",
    ) == (
        "/nidynamicformfields/v1/resolved-configuration",
        {"configurationId": "cfg-123"},
    )


def test_resolve_proxy_target_rejects_unsupported_route() -> None:
    """Unsupported proxy routes should not resolve."""
    assert _resolve_proxy_target("GET", "/nidynamicformfields/v1/anything-else", "") is None


def test_resolve_proxy_target_rejects_unsupported_workspace_query_param() -> None:
    """Workspace proxying should reject unexpected query parameters."""
    with pytest.raises(ValueError, match="unsupported workspace query parameters"):
        _resolve_proxy_target("GET", "/niuser/v1/workspaces", "admin=true")
