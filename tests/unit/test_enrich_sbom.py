"""Tests for SBOM enrichment helpers."""

from __future__ import annotations

import base64
from pathlib import Path, PurePath, PureWindowsPath
from typing import Any, Dict, List, Optional

import pytest
from scripts.enrich_sbom import (
    SBOM_SUPPLIER,
    decode_record_sha256,
    enrich_metadata,
    get_package_metadata,
)


class FakeMetadata:
    """Minimal metadata mapping for importlib metadata tests."""

    def __init__(self, values: Dict[str, Any]) -> None:
        """Store metadata values for test lookups."""
        self._values = values

    def __getitem__(self, key: str) -> Any:
        """Return a required metadata field."""
        return self._values[key]

    def get(self, key: str, default: Optional[Any] = None) -> Any:
        """Return an optional metadata field."""
        return self._values.get(key, default)

    def get_all(self, key: str) -> Optional[List[str]]:
        """Return metadata values as a list when present."""
        value = self._values.get(key)
        if value is None:
            return None
        if isinstance(value, list):
            return value
        return [value]


class FakeDistribution:
    """Test double exposing only the public distribution API used by the script."""

    def __init__(self, record_relative_path: PurePath, record_location: Path) -> None:
        """Create a fake distribution with a locatable RECORD file."""
        self.metadata = FakeMetadata(
            {
                "Name": "demo-package",
                "License": "MIT License",
                "Author": "Demo Author <demo@example.com>",
                "Home-page": "https://example.invalid",
                "Project-URL": ["Source, https://github.com/example/demo-package"],
            }
        )
        self.files = [record_relative_path]
        self._record_location = record_location

    def locate_file(self, path: PurePath) -> Path:
        """Resolve a relative package path to the fake RECORD file."""
        assert path == self.files[0]
        return self._record_location


def test_decode_record_sha256_accepts_padded_and_unpadded_values() -> None:
    """RECORD hashes should decode whether or not padding is present."""
    digest_hex = "ab" * 32
    digest_bytes = bytes.fromhex(digest_hex)
    padded = base64.urlsafe_b64encode(digest_bytes).decode("ascii")
    unpadded = padded.rstrip("=")

    assert decode_record_sha256(padded) == digest_hex
    assert decode_record_sha256(unpadded) == digest_hex


def test_enrich_metadata_creates_component_when_missing() -> None:
    """Metadata enrichment should persist changes even when component is absent."""
    sbom: Dict[str, Any] = {"metadata": {}}

    enrich_metadata(sbom)

    assert sbom["metadata"]["component"]["supplier"] == SBOM_SUPPLIER
    assert sbom["metadata"]["component"]["licenses"] == [
        {"license": {"id": "MIT", "acknowledgement": "declared"}}
    ]


def test_get_package_metadata_uses_public_record_lookup(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Package metadata extraction should use locate_file and not private attributes."""
    record_relative_path = Path("demo_package-1.0.0.dist-info/RECORD")
    record_location = tmp_path / record_relative_path
    record_location.parent.mkdir(parents=True)

    digest_hex = "cd" * 32
    digest_b64 = base64.urlsafe_b64encode(bytes.fromhex(digest_hex)).decode("ascii")
    record_location.write_text(
        f"demo_package/__init__.py,sha256={digest_b64},123\n",
        encoding="utf-8",
    )

    fake_dist = FakeDistribution(record_relative_path, record_location)
    monkeypatch.setattr("importlib.metadata.distributions", lambda: [fake_dist])

    metadata = get_package_metadata()

    assert metadata == {
        "demo-package": {
            "license": "MIT License",
            "author": "Demo Author <demo@example.com>",
            "vcs_url": "https://github.com/example/demo-package",
            "hashes": [{"alg": "SHA-256", "content": digest_hex}],
        }
    }


def test_get_package_metadata_accepts_windows_style_record_paths(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Package metadata extraction should handle Windows-style RECORD paths."""
    record_relative_path = PureWindowsPath("demo_package-1.0.0.dist-info/RECORD")
    record_location = tmp_path / "demo_package-1.0.0.dist-info" / "RECORD"
    record_location.parent.mkdir(parents=True)

    digest_hex = "ef" * 32
    digest_b64 = base64.urlsafe_b64encode(bytes.fromhex(digest_hex)).decode("ascii")
    record_location.write_text(
        f"demo_package/__init__.py,sha256={digest_b64},123\n",
        encoding="utf-8",
    )

    fake_dist = FakeDistribution(record_relative_path, record_location)
    monkeypatch.setattr("importlib.metadata.distributions", lambda: [fake_dist])

    metadata = get_package_metadata()

    assert metadata["demo-package"]["hashes"] == [{"alg": "SHA-256", "content": digest_hex}]
