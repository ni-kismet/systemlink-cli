from __future__ import annotations

import sys
from pathlib import Path

import pytest
from slcli.web_editor import DFFWebEditor, _build_proxy_url, _validated_proxy_origin

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
        query="take=25&skip=0",
    )

    assert (
        url
        == "https://systemlink.example.test/nidynamicformfields/v1/configurations?take=25&skip=0"
    )
