"""Unit tests for managed-client MessagePack and v3 envelope validation."""

import base64
import hashlib

import msgpack  # type: ignore[import-untyped]
import pytest
from cryptography.hazmat.primitives.asymmetric.rsa import generate_private_key

from slcli.managed_client.crypto import encrypt_rsa_oaep, sign_rsa_pkcs1_sha1, serialize_public_key
from slcli.managed_client.models import ProtocolError
from slcli.managed_client.protocol import (
    AuthRequest,
    AuthState,
    MessagePackStream,
    SaltMessage,
    build_job_return,
    build_pillar_request,
    build_publish_registration,
    decrypt_message_load,
    parse_auth_response,
    pack_frame,
    unpack_frame,
)


def test_messagepack_frame_round_trip() -> None:
    """A string-keyed frame preserves binary nonce and nested values."""
    payload = {"nonce": b"nonce", "payload": {"count": 2}}

    assert unpack_frame(pack_frame(payload)) == payload


def test_messagepack_frame_accepts_salt_raw_strings_and_binary_fields() -> None:
    """Salt emits textual fields as raw strings alongside binary signatures."""
    frame = msgpack.packb(
        {
            b"body": {
                b"enc": b"clear",
                b"load": b"\x81\xa3ret\xc3",
                b"sig": b"\x00\xff\x95",
            },
            b"head": {b"mid": 1},
        },
        use_bin_type=False,
    )

    assert unpack_frame(frame) == {
        "body": {"enc": "clear", "load": b"\x81\xa3ret\xc3", "sig": b"\x00\xff\x95"},
        "head": {"mid": 1},
    }


def test_messagepack_frame_does_not_restore_nested_application_fields() -> None:
    """Only direct protocol fields are restored from raw MessagePack strings."""
    frame = msgpack.packb(
        {
            "token": "wire-token",
            "payload": {"token": "application-text", "sig": "application-signature"},
        },
        use_bin_type=False,
    )

    assert unpack_frame(frame) == {
        "token": b"wire-token",
        "payload": {"token": "application-text", "sig": "application-signature"},
    }


def test_messagepack_frame_rejects_non_string_map_keys() -> None:
    """Protocol maps cannot rely on ambiguous integer or binary keys."""
    with pytest.raises(ProtocolError, match="map keys must be strings"):
        pack_frame({"nested": {1: "invalid"}})


def test_build_message_rejects_api_keys_on_raw_tcp() -> None:
    """Credentials cannot be placed in an unencrypted Salt envelope."""
    with pytest.raises(ProtocolError, match="API keys are not supported"):
        AuthRequest(
            minion_id="minion-1",
            public_key="public-key",
            nonce="nonce-1",
            api_key="secret-api-key",
        ).to_message()


def test_messagepack_frame_rejects_malformed_bytes() -> None:
    """Truncated MessagePack never reaches a handler."""
    with pytest.raises(ProtocolError, match="malformed"):
        unpack_frame(b"\x81\xa1a")


def test_salt_message_round_trip() -> None:
    """The observed body/head message survives the envelope codec."""
    envelope = SaltMessage(
        body={"enc": "clear", "version": 2, "load": {"cmd": "_auth"}},
        head={"mid": 1},
    )

    assert SaltMessage.unpack(envelope.pack()) == envelope


def test_salt_message_rejects_other_versions() -> None:
    """Unknown communication versions fail before dispatch."""
    frame = pack_frame({"body": {"version": 3, "enc": "clear", "load": {}}, "head": {"mid": 1}})

    with pytest.raises(ProtocolError, match="observed v3 communication version"):
        SaltMessage.unpack(frame)


def test_messagepack_stream_handles_partial_and_multiple_frames() -> None:
    """Raw TCP chunks can split frames and carry more than one frame."""
    first = pack_frame({"body": {"enc": "clear", "load": {}}, "head": {"mid": 1}})
    second = pack_frame({"body": {"enc": "clear", "load": {}}, "head": {"mid": 2}})
    stream = MessagePackStream()

    assert stream.feed(first[:2]) == []
    assert stream.feed(first[2:] + second) == [
        {"body": {"enc": "clear", "load": {}}, "head": {"mid": 1}},
        {"body": {"enc": "clear", "load": {}}, "head": {"mid": 2}},
    ]


def test_messagepack_stream_rejects_oversized_incomplete_frame() -> None:
    """An incomplete frame cannot grow without a bounded limit."""
    stream = MessagePackStream(max_frame_size=4)

    assert stream.feed(b"\x81\xa1a") == []
    with pytest.raises(ProtocolError, match="size limit"):
        stream.feed(b"\x81\x81")


def test_messagepack_stream_rejects_oversized_complete_frame() -> None:
    """A complete frame is checked independently of the TCP chunk size."""
    stream = MessagePackStream(max_frame_size=3)

    with pytest.raises(ProtocolError, match="size limit"):
        stream.feed(b"\x81\xa1a\x01")


def test_auth_pending_does_not_require_master_signature() -> None:
    """Pending approval can be observed before the master key is known."""
    minion_key = generate_private_key(public_exponent=65537, key_size=2048)
    message = SaltMessage(
        body={
            "enc": "clear",
            "load": pack_frame({"ret": True, "nonce": "nonce-1"}),
            "sig": b"pending-signature",
        },
        head={"mid": 1},
    )

    response = parse_auth_response(
        message,
        minion_private_key=minion_key,
    )

    assert response.state is AuthState.PENDING


def test_auth_request_includes_reconnect_token() -> None:
    """A Salt-issued token is sent on subsequent authentication requests."""
    request = AuthRequest(
        minion_id="minion-1",
        public_key="public-key",
        nonce="nonce-1",
        token=b"issued-token",
    )

    message = request.to_message()

    assert message.body["load"]["token"] == b"issued-token"


def test_auth_accepted_verifies_outer_load_signature() -> None:
    """Accepted auth verifies ordinary RSA-SHA1 before requiring X9.31."""
    minion_key = generate_private_key(public_exponent=65537, key_size=2048)
    master_key = generate_private_key(public_exponent=65537, key_size=2048)
    shared_secret = bytes(range(56))
    load = pack_frame(
        {
            "pub_key": serialize_public_key(master_key.public_key()).decode("utf-8"),
            "publish_port": 4505,
            "sig": b"x931-session-signature",
            "aes": encrypt_rsa_oaep(base64.b64encode(shared_secret), minion_key.public_key()),
            "nonce": "nonce-1",
        }
    )
    master_public_key = serialize_public_key(master_key.public_key()).decode("utf-8")
    message = SaltMessage(
        body={"enc": "clear", "load": load, "sig": sign_rsa_pkcs1_sha1(load, master_key)},
        head={"mid": 1},
    )

    session_calls: list[tuple[bytes, bytes, str]] = []

    def verify_session(digest: bytes, signature: bytes, public_key: str) -> bool:
        session_calls.append((digest, signature, public_key))
        return True

    response = parse_auth_response(
        message,
        minion_private_key=minion_key,
        verify_session_signature=verify_session,
    )

    assert response.state is AuthState.ACCEPTED
    assert response.shared_secret == shared_secret
    assert session_calls == [
        (
            hashlib.sha256(base64.b64encode(shared_secret)).hexdigest().encode("ascii"),
            b"x931-session-signature",
            master_public_key,
        )
    ]

    invalid_message = SaltMessage(
        body={**message.body, "sig": b"invalid"},
        head=message.head,
    )
    with pytest.raises(ProtocolError, match="signature is invalid"):
        parse_auth_response(
            invalid_message,
            minion_private_key=minion_key,
            verify_session_signature=verify_session,
        )


@pytest.mark.parametrize("publish_port", [True, 0, 65536])
def test_auth_accepted_rejects_invalid_publish_ports(publish_port: object) -> None:
    """Accepted auth rejects boolean and out-of-range publish ports."""
    minion_key = generate_private_key(public_exponent=65537, key_size=2048)
    master_key = generate_private_key(public_exponent=65537, key_size=2048)
    shared_secret = bytes(range(56))
    load = pack_frame(
        {
            "pub_key": serialize_public_key(master_key.public_key()).decode("utf-8"),
            "publish_port": publish_port,
            "sig": b"x931-session-signature",
            "aes": encrypt_rsa_oaep(base64.b64encode(shared_secret), minion_key.public_key()),
            "nonce": "nonce-1",
        }
    )
    message = SaltMessage(
        body={"enc": "clear", "load": load, "sig": b"master-signature"},
        head={"mid": 1},
    )

    with pytest.raises(ProtocolError, match="invalid publish port"):
        parse_auth_response(
            message,
            minion_private_key=minion_key,
            verify_master_signature=False,
        )


def test_publish_and_job_return_use_salt_field_names() -> None:
    """Registration and returns preserve the observed Salt payload fields."""
    key_pair = generate_private_key(public_exponent=65537, key_size=2048)
    shared_secret = bytes(range(56))

    def signer(message: bytes, private_key: object) -> bytes:
        del private_key
        return b"token:" + message

    job = {
        "jid": "jid-001",
        "fun": "slcli.test.return_success",
        "arg": [],
    }

    registration = build_publish_registration(
        minion_id="minion-1",
        shared_secret=shared_secret,
        private_key=key_pair,
        signer=signer,
    )
    assert decrypt_message_load(registration, shared_secret) == {
        "id": "minion-1",
        "tok": b"token:salt",
    }

    pillar = build_pillar_request(
        grains={"minion_blackout": True},
        minion_id="minion-1",
        shared_secret=shared_secret,
        private_key=key_pair,
        nonce="nonce-1",
        signer=signer,
    )
    assert decrypt_message_load(pillar, shared_secret) == {
        "cmd": "_pillar",
        "id": "minion-1",
        "grains": {"minion_blackout": True},
        "tok": b"token:salt",
        "nonce": "nonce-1",
    }

    returned = build_job_return(
        job=job,
        result={"return": {"value": "success"}, "retcode": 0, "success": True},
        minion_id="minion-1",
        shared_secret=shared_secret,
        private_key=key_pair,
        nonce="nonce-1",
        signer=signer,
    )
    assert decrypt_message_load(returned, shared_secret) == {
        "cmd": "_return",
        "jid": "jid-001",
        "id": "minion-1",
        "tok": b"token:salt",
        "return": {"value": "success"},
        "retcode": 0,
        "success": True,
        "fun": "slcli.test.return_success",
        "fun_args": [],
        "nonce": "nonce-1",
    }


def test_job_return_preserves_multi_function_refresh_arrays() -> None:
    """A multi-function refresh uses array-valued Salt return fields."""
    key_pair = generate_private_key(public_exponent=65537, key_size=2048)
    shared_secret = bytes(range(56))
    job = {
        "jid": "refresh-001",
        "fun": [
            "saltutil.refresh_pillar",
            "nisysmgmt.state_apply",
            "pkg.list_repos",
            "nisysmgmt.grains_items",
            "pkg.info_installed",
        ],
        "arg": [[], [], [], [], [{"__kwarg__": True, "attr": ["version"]}]],
    }

    def signer(message: bytes, private_key: object) -> bytes:
        del private_key
        return b"token:" + message

    returned = build_job_return(
        job=job,
        result={
            "return": [True, True, None, {"minion_blackout": False}, None],
            "retcode": [0, 0, 0, 0, 0],
            "success": [True, True, True, True, True],
        },
        minion_id="minion-1",
        shared_secret=shared_secret,
        private_key=key_pair,
        nonce="nonce-1",
        signer=signer,
    )

    assert decrypt_message_load(returned, shared_secret) == {
        "cmd": "_return",
        "jid": "refresh-001",
        "id": "minion-1",
        "tok": b"token:salt",
        "return": [True, True, None, {"minion_blackout": False}, None],
        "retcode": [0, 0, 0, 0, 0],
        "success": [True, True, True, True, True],
        "fun": [
            "saltutil.refresh_pillar",
            "nisysmgmt.state_apply",
            "pkg.list_repos",
            "nisysmgmt.grains_items",
            "pkg.info_installed",
        ],
        "fun_args": [[], [], [], [], [{"__kwarg__": True, "attr": ["version"]}]],
        "nonce": "nonce-1",
    }


def test_job_returns_generate_distinct_request_nonces() -> None:
    """Each encrypted return gets a fresh nonce instead of reusing auth state."""
    key_pair = generate_private_key(public_exponent=65537, key_size=2048)
    shared_secret = bytes(range(56))
    job = {"jid": "jid-001", "fun": "slcli.test.return_success", "arg": []}
    result = {"return": {"value": "success"}, "retcode": 0, "success": True}

    def signer(message: bytes, private_key: object) -> bytes:
        del private_key
        return b"token:" + message

    first = decrypt_message_load(
        build_job_return(
            job=job,
            result=result,
            minion_id="minion-1",
            shared_secret=shared_secret,
            private_key=key_pair,
            signer=signer,
        ),
        shared_secret,
    )
    second = decrypt_message_load(
        build_job_return(
            job=job,
            result=result,
            minion_id="minion-1",
            shared_secret=shared_secret,
            private_key=key_pair,
            signer=signer,
        ),
        shared_secret,
    )

    assert first["nonce"] != "nonce-1"
    assert first["nonce"] != second["nonce"]
    assert len(first["nonce"]) == 32
    assert len(second["nonce"]) == 32
