"""Tests for REST connection state delivered to the managed-client minion."""

from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any

import pytest

from slcli.managed_client import MinionConfiguration, health
from slcli.managed_client import TestMinion as ManagedTestMinion
from slcli.managed_client.crypto import (
    encrypt_aes_192_cbc_hmac,
    encrypt_rsa_oaep,
    generate_rsa_key_pair,
    serialize_public_key,
    sign_rsa_pkcs1_sha1,
)
from slcli.managed_client.health import HealthTagPublisher
from slcli.managed_client.models import ManagedClientError, ProtocolError, StateError
from slcli.managed_client.protocol import (
    _wire_bytes,
    decrypt_pillar_reply,
    pack_frame,
    pack_inner_load,
    unpack_frame,
)
from slcli.managed_client.state import HTTP_MASTER_FILE_NAME, StateStore

PILLAR = {"http": {"uri": "https://api.example.com/", "api_key": "key-123", "workspace": "ws-1"}}


def test_record_and_load_http_master_round_trip(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state")

    store.record_http_master("https://api.example.com", "key-123")

    assert store.load_http_master() == ("https://api.example.com", "key-123")
    stored = json.loads((tmp_path / "state" / HTTP_MASTER_FILE_NAME).read_text(encoding="utf-8"))
    assert stored == {"Uri": "https://api.example.com", "ApiKey": "key-123"}


@pytest.mark.skipif(os.name == "nt", reason="POSIX file modes are not enforced on Windows")
def test_http_master_file_is_owner_only(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state")

    store.record_http_master("https://api.example.com", "key-123")

    mode = (tmp_path / "state" / HTTP_MASTER_FILE_NAME).stat().st_mode & 0o777
    assert mode == 0o600


def test_load_http_master_returns_none_when_absent(tmp_path: Path) -> None:
    assert StateStore(tmp_path / "state").load_http_master() is None


def test_pillar_rewrites_uri_host_to_master(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state")

    store.record_http_master_from_pillar(PILLAR, "10.12.234.133")

    assert store.load_http_master() == ("https://10.12.234.133/", "key-123")


def test_pillar_keeps_uri_when_overridden(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state")
    pillar: dict[str, Any] = {"http": {**PILLAR["http"], "uriIsOverridden": True}}

    store.record_http_master_from_pillar(pillar, "10.12.234.133")

    assert store.load_http_master() == ("https://api.example.com/", "key-123")


def test_pillar_without_key_clears_stored_connection(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state")
    store.record_http_master("https://api.example.com", "key-123")

    store.record_http_master_from_pillar({"http": {"uri": "https://api.example.com"}}, "host")

    assert store.load_http_master() is None


def test_pillar_certificate_is_stored_and_removed_with_connection(tmp_path: Path) -> None:
    store = StateStore(tmp_path / "state")

    store.record_http_master_from_pillar(
        {"http": {**PILLAR["http"], "certificate": "-----BEGIN CERTIFICATE-----\nabc\n"}},
        "10.12.234.133",
    )
    ca_bundle = store.load_http_ca_bundle()

    assert ca_bundle is not None
    assert Path(ca_bundle).read_text(encoding="utf-8").startswith("-----BEGIN CERTIFICATE-----")

    store.record_http_master_from_pillar(PILLAR, "10.12.234.133")

    assert store.load_http_ca_bundle() is None


def test_invalid_http_master_file_raises_state_error(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    state_dir.mkdir()
    (state_dir / HTTP_MASTER_FILE_NAME).write_text('{"Uri": ""}', encoding="utf-8")

    with pytest.raises(StateError):
        StateStore(state_dir).load_http_master()


def test_pillar_reply_writes_connection_for_health_publisher(tmp_path: Path) -> None:
    state_dir = tmp_path / "state"
    minion = ManagedTestMinion(
        MinionConfiguration(master="10.12.234.133", minion_id="minion-1", state_dir=state_dir)
    )

    minion._apply_pillar(PILLAR)

    assert StateStore(state_dir).load_http_master() == ("https://10.12.234.133/", "key-123")


def _build_pillar_reply(
    *,
    minion_public: Any,
    master_private: Any,
    secret: bytes,
    nonce: str,
    pillar: dict[str, Any],
    payload_secret: bytes | None = None,
) -> dict[str, Any]:
    """Build a v3 `_pillar` reply the way the master's pillar handler does."""
    data = pack_inner_load({"key": b"k", "pillar": pillar, "nonce": nonce})
    signature = sign_rsa_pkcs1_sha1(data, master_private)
    envelope = encrypt_aes_192_cbc_hmac(
        pack_inner_load({"data": data, "sig": signature}), payload_secret or secret
    ).to_bytes()
    wrapped_key = encrypt_rsa_oaep(base64.b64encode(secret), minion_public)
    return {"body": {"key": wrapped_key, "pillar": envelope}, "head": {"mid": 1}}


def test_unpack_frame_restores_pillar_reply_fields_sent_as_strings() -> None:
    frame = pack_frame({"head": {"mid": 1}, "body": {"key": "abc", "pillar": "def"}})

    body = unpack_frame(frame)["body"]

    assert body["key"] == b"abc"
    assert body["pillar"] == b"def"


def test_wire_bytes_accepts_bytes_and_msgpack_strings() -> None:
    assert _wire_bytes(b"\x84\xff") == b"\x84\xff"
    assert _wire_bytes("abc") == b"abc"
    assert _wire_bytes("\udc84\udcff") == b"\x84\xff"
    assert _wire_bytes(None) is None


def test_decrypt_pillar_reply_returns_verified_pillar() -> None:
    minion = generate_rsa_key_pair()
    master = generate_rsa_key_pair()
    reply = _build_pillar_reply(
        minion_public=minion.public_key,
        master_private=master.private_key,
        secret=bytes(range(1, 57)),
        nonce="n-1",
        pillar=PILLAR,
    )

    pillar = decrypt_pillar_reply(
        reply,
        private_key=minion.private_key,
        master_public_key=serialize_public_key(master.public_key).decode("utf-8"),
        nonce="n-1",
    )

    assert pillar == PILLAR


def test_decrypt_pillar_reply_rejects_bad_signature() -> None:
    minion = generate_rsa_key_pair()
    master = generate_rsa_key_pair()
    impostor = generate_rsa_key_pair()
    reply = _build_pillar_reply(
        minion_public=minion.public_key,
        master_private=impostor.private_key,
        secret=bytes(range(1, 57)),
        nonce="n-1",
        pillar=PILLAR,
    )

    with pytest.raises(ProtocolError, match="signature"):
        decrypt_pillar_reply(
            reply,
            private_key=minion.private_key,
            master_public_key=serialize_public_key(master.public_key).decode("utf-8"),
            nonce="n-1",
        )


def test_decrypt_pillar_reply_rejects_nonce_mismatch() -> None:
    minion = generate_rsa_key_pair()
    master = generate_rsa_key_pair()
    reply = _build_pillar_reply(
        minion_public=minion.public_key,
        master_private=master.private_key,
        secret=bytes(range(1, 57)),
        nonce="stale",
        pillar=PILLAR,
    )

    with pytest.raises(ProtocolError, match="nonce"):
        decrypt_pillar_reply(
            reply,
            private_key=minion.private_key,
            master_public_key=serialize_public_key(master.public_key).decode("utf-8"),
            nonce="n-1",
        )


def test_decrypt_pillar_reply_rejects_key_for_another_minion() -> None:
    minion = generate_rsa_key_pair()
    other_minion = generate_rsa_key_pair()
    master = generate_rsa_key_pair()
    reply = _build_pillar_reply(
        minion_public=other_minion.public_key,
        master_private=master.private_key,
        secret=bytes(range(1, 57)),
        nonce="n-1",
        pillar=PILLAR,
    )

    with pytest.raises(ProtocolError, match="key could not be decrypted"):
        decrypt_pillar_reply(
            reply,
            private_key=minion.private_key,
            master_public_key=serialize_public_key(master.public_key).decode("utf-8"),
            nonce="n-1",
        )


def test_decrypt_pillar_reply_rejects_payload_with_wrong_secret() -> None:
    minion = generate_rsa_key_pair()
    master = generate_rsa_key_pair()
    reply = _build_pillar_reply(
        minion_public=minion.public_key,
        master_private=master.private_key,
        secret=bytes(range(1, 57)),
        payload_secret=bytes(range(2, 58)),
        nonce="n-1",
        pillar=PILLAR,
    )

    with pytest.raises(ProtocolError, match="payload could not be decrypted"):
        decrypt_pillar_reply(
            reply,
            private_key=minion.private_key,
            master_public_key=serialize_public_key(master.public_key).decode("utf-8"),
            nonce="n-1",
        )


def test_decrypt_pillar_reply_rejects_plain_error_body() -> None:
    minion = generate_rsa_key_pair()

    with pytest.raises(ProtocolError, match="body map"):
        decrypt_pillar_reply(
            {"body": "denied", "head": {"mid": 1}},
            private_key=minion.private_key,
            master_public_key="unused",
            nonce="n-1",
        )


class _FakeResponse:
    def __init__(self, payload: Any) -> None:
        self._payload = payload

    def json(self) -> Any:
        return self._payload


def _system_record(minion_id: str) -> dict[str, Any]:
    return {"id": minion_id, "workspace": "ws-1", "grains": {"data": {"host": "host-1"}}}


def test_publisher_uses_stored_connection_and_key(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_dir = tmp_path / "state"
    StateStore(state_dir).record_http_master("https://api.example.com", "key-123")
    calls: list[dict[str, Any]] = []

    def fake_request(method: str, url: str, **kwargs: Any) -> _FakeResponse:
        calls.append({"method": method, "url": url, **kwargs})
        return _FakeResponse([_system_record("minion-1")])

    monkeypatch.setattr(health, "make_api_request", fake_request)
    publisher = HealthTagPublisher("minion-1", state_dir=state_dir, interval=60)

    publisher.publish_once()

    assert calls[0]["url"].startswith("https://api.example.com/nisysmgmt/v1/systems?")
    assert calls[0]["credential"] == "key-123"
    assert calls[0]["auth_scheme"] == "api-key"
    assert calls[0]["ssl_verify"] is None


def test_publisher_verifies_tls_with_delivered_certificate(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    state_dir = tmp_path / "state"
    store = StateStore(state_dir)
    store.record_http_master_from_pillar(
        {"http": {**PILLAR["http"], "certificate": "-----BEGIN CERTIFICATE-----\nabc\n"}},
        "10.12.234.133",
    )
    calls: list[dict[str, Any]] = []

    def fake_request(method: str, url: str, **kwargs: Any) -> _FakeResponse:
        calls.append({"method": method, "url": url, **kwargs})
        return _FakeResponse([_system_record("minion-1")])

    monkeypatch.setattr(health, "make_api_request", fake_request)
    publisher = HealthTagPublisher("minion-1", state_dir=state_dir, interval=60)

    publisher.publish_once()

    assert calls[0]["ssl_verify"] == store.load_http_ca_bundle()


def test_publisher_does_not_use_profile_without_stored_connection(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    calls: list[dict[str, Any]] = []

    def fake_request(method: str, url: str, **kwargs: Any) -> _FakeResponse:
        calls.append({"method": method, "url": url, **kwargs})
        return _FakeResponse([_system_record("minion-1")])

    monkeypatch.setattr(health, "make_api_request", fake_request)
    monkeypatch.setattr(health, "get_base_url", lambda: "https://profile.example")
    publisher = HealthTagPublisher("minion-1", state_dir=tmp_path / "state", interval=60)

    with pytest.raises(ManagedClientError, match="has not delivered REST connection details"):
        publisher.publish_once()

    assert calls == []
