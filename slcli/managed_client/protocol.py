"""Safe MessagePack framing and v3 envelope validation."""

from __future__ import annotations

import base64
import binascii
import hashlib
import importlib
import uuid
from collections.abc import Mapping, MutableMapping
from dataclasses import dataclass
from enum import Enum
from typing import Any, Callable

from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

from .crypto import (
    SALT_SHARED_SECRET_SIZE,
    decrypt_rsa_oaep,
    encrypt_aes_192_cbc_hmac,
    load_rsa_public_key,
    rsa_x931_sign,
    verify_rsa_pkcs1_sha1_result,
)
from .models import ProtocolError, UnsupportedCryptoError

PROTOCOL_VERSION = 3
COMMUNICATION_VERSION = 2
MAX_FRAME_SIZE = 8 * 1024 * 1024
_BINARY_FIELDS = frozenset({"aes", "load", "sig", "token", "tok"})


def _msgpack() -> Any:
    """Load the optional MessagePack dependency only when the feature is used."""
    try:
        return importlib.import_module("msgpack")
    except ImportError as error:
        raise ProtocolError(
            "MessagePack support requires the optional managed-client dependency."
        ) from error


def _validate_value(value: Any) -> None:
    """Reject values that MessagePack could encode ambiguously or unsafely."""
    if value is None or isinstance(value, (bool, int, float, str, bytes)):
        return
    if isinstance(value, (list, tuple)):
        for item in value:
            _validate_value(item)
        return
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str):
                raise ProtocolError("MessagePack map keys must be strings.")
            _validate_value(item)
        return
    raise ProtocolError("The message contains an unsupported value type.")


def _validate_decoded_value(value: Any) -> None:
    """Validate decoded map keys without changing application values."""
    if isinstance(value, Mapping):
        for key, item in value.items():
            if not isinstance(key, str) or any(
                0xD800 <= ord(character) <= 0xDFFF for character in key
            ):
                raise ProtocolError("The MessagePack frame must contain a string-keyed map.")
            _validate_decoded_value(item)
    elif isinstance(value, list):
        for item in value:
            _validate_decoded_value(item)


def _restore_binary_map(value: Mapping[str, Any], fields: frozenset[str]) -> dict[str, Any]:
    """Restore only direct wire fields from raw MessagePack strings."""
    return {
        key: (
            item.encode("utf-8", errors="surrogateescape")
            if key in fields and isinstance(item, str)
            else item
        )
        for key, item in value.items()
    }


def _restore_binary_field(value: Any) -> Any:
    """Restore binary Salt fields without rewriting nested application data."""
    _validate_decoded_value(value)
    if not isinstance(value, Mapping):
        return value
    if isinstance(value.get("body"), Mapping) and isinstance(value.get("head"), Mapping):
        restored = dict(value)
        restored["body"] = _restore_binary_map(value["body"], frozenset({"load", "sig"}))
        return restored
    return _restore_binary_map(value, _BINARY_FIELDS)


def pack_frame(payload: Mapping[str, Any]) -> bytes:
    """Encode one validated MessagePack frame."""
    _validate_value(payload)
    try:
        encoded = _msgpack().packb(payload, use_bin_type=True, strict_types=True)
    except ProtocolError:
        raise
    except Exception as error:
        raise ProtocolError("The message could not be encoded.") from error
    if len(encoded) > MAX_FRAME_SIZE:
        raise ProtocolError("The MessagePack frame exceeds the size limit.")
    return encoded


def unpack_frame(frame: bytes) -> MutableMapping[str, Any]:
    """Decode one MessagePack frame and require a string-keyed map."""
    if not frame or len(frame) > MAX_FRAME_SIZE:
        raise ProtocolError("The MessagePack frame has an invalid size.")
    try:
        value = _restore_binary_field(
            _msgpack().unpackb(
                frame,
                raw=False,
                strict_map_key=True,
                unicode_errors="surrogateescape",
            )
        )
    except Exception as error:
        raise ProtocolError("The MessagePack frame is malformed.") from error
    if not isinstance(value, MutableMapping) or any(not isinstance(key, str) for key in value):
        raise ProtocolError("The MessagePack frame must contain a string-keyed map.")
    return value


class MessagePackStream:
    """Decode raw TCP MessagePack data with support for partial reads."""

    def __init__(self, max_frame_size: int = MAX_FRAME_SIZE) -> None:
        """Create a bounded incremental decoder."""
        if max_frame_size <= 0:
            raise ValueError("The maximum frame size must be positive.")
        self._unpacker = _msgpack().Unpacker(
            raw=False,
            strict_map_key=True,
            unicode_errors="surrogateescape",
        )
        self._max_frame_size = max_frame_size
        self._total_fed = 0
        self._total_consumed = 0

    def feed(self, data: bytes) -> list[MutableMapping[str, Any]]:
        """Decode all complete maps currently available in a TCP chunk."""
        if not data:
            raise ProtocolError("The MessagePack stream ended unexpectedly.")
        try:
            self._total_fed += len(data)
            self._unpacker.feed(data)
            values = []
            for value in self._unpacker:
                consumed = self._unpacker.tell()
                if consumed - self._total_consumed > self._max_frame_size:
                    raise ProtocolError("The MessagePack frame exceeds the size limit.")
                self._total_consumed = consumed
                values.append(_restore_binary_field(value))
            if self._total_fed - self._total_consumed > self._max_frame_size:
                raise ProtocolError("The MessagePack frame exceeds the size limit.")
        except Exception as error:
            if isinstance(error, ProtocolError):
                raise
            raise ProtocolError("The MessagePack stream is malformed.") from error
        frames: list[MutableMapping[str, Any]] = []
        for value in values:
            if not isinstance(value, MutableMapping) or any(
                not isinstance(key, str) for key in value
            ):
                raise ProtocolError("The MessagePack frame must contain a string-keyed map.")
            frames.append(value)
        return frames


@dataclass(frozen=True)
class SaltMessage:
    """The observed Salt request/publish envelope."""

    body: Mapping[str, Any]
    head: Mapping[str, Any]

    def __post_init__(self) -> None:
        """Validate the outer map without interpreting encrypted payloads."""
        if not isinstance(self.body, Mapping) or not isinstance(self.head, Mapping):
            raise ProtocolError("A Salt message requires body and head maps.")
        encoding = self.body.get("enc")
        if encoding not in ("clear", "aes", "pub"):
            raise ProtocolError("A Salt message has an unsupported encoding.")
        if "load" not in self.body:
            raise ProtocolError("A Salt message requires a load field.")
        message_id = self.head.get("mid")
        if not isinstance(message_id, (int, str)):
            raise ProtocolError("A Salt message requires a message ID.")
        version = self.body.get("version")
        if version is not None and version != COMMUNICATION_VERSION:
            raise ProtocolError("Only the observed v3 communication version is supported.")
        _validate_value(self.body)
        _validate_value(self.head)

    def to_mapping(self) -> Mapping[str, Any]:
        """Return the exact outer Salt message mapping."""
        return {"body": self.body, "head": self.head}

    def pack(self) -> bytes:
        """Encode the message as one raw MessagePack frame."""
        return pack_frame(self.to_mapping())

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any]) -> "SaltMessage":
        """Validate and construct a message from a decoded outer map."""
        body = value.get("body")
        head = value.get("head")
        if not isinstance(body, Mapping) or not isinstance(head, Mapping):
            raise ProtocolError("A Salt message requires body and head maps.")
        return cls(body=body, head=head)

    @classmethod
    def unpack(cls, frame: bytes) -> "SaltMessage":
        """Decode and validate one Salt message frame."""
        return cls.from_mapping(unpack_frame(frame))


V3Envelope = SaltMessage


def pack_inner_load(load: Mapping[str, Any]) -> bytes:
    """Pack a nested Salt load using the same MessagePack representation."""
    return pack_frame(load)


def unpack_inner_load(load: bytes) -> MutableMapping[str, Any]:
    """Unpack a nested Salt load carried in a clear or AES body."""
    return unpack_frame(load)


def build_message(
    load: Mapping[str, Any] | bytes,
    *,
    encoding: str,
    message_id: int | str = 1,
    communication_version: int | None = COMMUNICATION_VERSION,
    api_key: str | None = None,
) -> SaltMessage:
    """Build an observed Salt message with explicit version and API fields."""
    body: dict[str, Any] = {"enc": encoding, "load": load}
    if communication_version is not None:
        if communication_version != COMMUNICATION_VERSION:
            raise ProtocolError("Only communication version 2 is supported for v3.")
        body["version"] = communication_version
    if api_key is not None:
        body["x-ni-api-key"] = api_key
    return SaltMessage(body=body, head={"mid": message_id})


@dataclass(frozen=True)
class AuthRequest:
    """The clear v3 authentication request."""

    minion_id: str
    public_key: str
    nonce: str
    api_key: str | None = None
    token: bytes | None = None

    def to_message(self) -> SaltMessage:
        """Build the request sent on the request channel."""
        load: dict[str, Any] = {
            "cmd": "_auth",
            "id": self.minion_id,
            "pub": self.public_key,
            "nonce": self.nonce,
        }
        if self.token is not None:
            load["token"] = self.token
        return build_message(load, encoding="clear", api_key=self.api_key)


class AuthState(str, Enum):
    """Result categories returned by the v3 authentication handler."""

    PENDING = "pending"
    ACCEPTED = "accepted"


@dataclass(frozen=True)
class AuthResponse:
    """Parsed authentication state and session material."""

    state: AuthState
    nonce: str
    shared_secret: bytes | None = None
    master_public_key: str | None = None
    publish_port: int | None = None
    minion_token: bytes | None = None
    session_signature: bytes | None = None


def parse_auth_response(
    message: SaltMessage,
    *,
    minion_private_key: RSAPrivateKey,
    verify_master_signature: bool = True,
    verify_load_signature: Callable[[bytes, bytes], bool] | None = None,
    verify_session_signature: Callable[[bytes, bytes, str], bool] | None = None,
) -> AuthResponse:
    """Parse pending or accepted auth and decrypt the shared session secret."""
    if message.body.get("enc") != "clear":
        raise ProtocolError("The v3 auth response must use clear encoding.")
    raw_load = message.body["load"]
    if isinstance(raw_load, bytes):
        load = unpack_inner_load(raw_load)
    elif isinstance(raw_load, Mapping):
        load = dict(raw_load)
    else:
        raise ProtocolError("The v3 auth response load must be packed bytes.")
    nonce = load.get("nonce")
    if not isinstance(nonce, str):
        raise ProtocolError("The v3 auth response nonce is missing.")
    if "pub_key" not in load:
        if load.get("ret") is not True:
            raise ProtocolError("The Salt master rejected authentication.")
        return AuthResponse(state=AuthState.PENDING, nonce=nonce)

    master_public_key = load.get("pub_key")
    encrypted_secret = load.get("aes")
    encrypted_signature = load.get("sig")
    publish_port = load.get("publish_port")
    if not isinstance(master_public_key, str):
        raise ProtocolError("The accepted auth response has no master public key.")
    if not isinstance(encrypted_secret, bytes) or not isinstance(encrypted_signature, bytes):
        raise ProtocolError("The accepted auth response has invalid session material.")
    if (
        isinstance(publish_port, bool)
        or not isinstance(publish_port, int)
        or not 1 <= publish_port <= 65535
    ):
        raise ProtocolError("The accepted auth response has an invalid publish port.")

    outer_signature = message.body.get("sig")
    if verify_master_signature:
        if not isinstance(raw_load, bytes) or not isinstance(outer_signature, bytes):
            raise ProtocolError("The v3 auth response signature is missing.")
        if verify_load_signature is not None:
            valid_load_signature = verify_load_signature(raw_load, outer_signature)
        else:
            valid_load_signature = verify_rsa_pkcs1_sha1_result(
                raw_load,
                outer_signature,
                load_rsa_public_key(master_public_key.encode("utf-8")),
            )
        if not valid_load_signature:
            raise ProtocolError("The v3 auth response signature is invalid.")

    encoded_shared_secret = decrypt_rsa_oaep(encrypted_secret, minion_private_key)
    try:
        shared_secret = base64.b64decode(encoded_shared_secret, validate=True)
    except (binascii.Error, ValueError) as error:
        raise ProtocolError("The Salt shared secret is not valid base64.") from error
    if len(shared_secret) != SALT_SHARED_SECRET_SIZE:
        raise ProtocolError("The Salt shared secret has an invalid length.")
    if verify_master_signature:
        if verify_session_signature is None:
            raise UnsupportedCryptoError(
                "v3 session signature verification requires the approved RSA X9.31 adapter."
            )
        session_digest = hashlib.sha256(encoded_shared_secret).hexdigest().encode("ascii")
        if not verify_session_signature(session_digest, encrypted_signature, master_public_key):
            raise ProtocolError("The v3 session signature is invalid.")
    minion_token_value = load.get("token")
    minion_token = None
    if minion_token_value is not None:
        if not isinstance(minion_token_value, bytes):
            raise ProtocolError("The accepted auth token is invalid.")
        minion_token = decrypt_rsa_oaep(minion_token_value, minion_private_key)
    return AuthResponse(
        state=AuthState.ACCEPTED,
        nonce=nonce,
        shared_secret=shared_secret,
        master_public_key=master_public_key,
        publish_port=publish_port,
        minion_token=minion_token,
        session_signature=encrypted_signature,
    )


def build_publish_registration(
    *,
    minion_id: str,
    shared_secret: bytes,
    private_key: RSAPrivateKey,
    message_id: int | str = 1,
    api_key: str | None = None,
    signer: Any = rsa_x931_sign,
) -> SaltMessage:
    """Build the encrypted publish registration message."""
    token = signer(b"salt", private_key)
    return build_message(
        encrypt_aes_192_cbc_hmac(
            pack_inner_load({"id": minion_id, "tok": token}), shared_secret
        ).to_bytes(),
        encoding="aes",
        message_id=message_id,
        api_key=api_key,
    )


def build_pillar_request(
    *,
    grains: Mapping[str, Any],
    minion_id: str,
    shared_secret: bytes,
    private_key: RSAPrivateKey,
    nonce: str | None = None,
    message_id: int | str = 1,
    api_key: str | None = None,
    signer: Any = rsa_x931_sign,
) -> SaltMessage:
    """Build the authenticated encrypted v3 `_pillar` request."""
    token = signer(b"salt", private_key)
    request_nonce = nonce if nonce is not None else uuid.uuid4().hex
    load = {
        "cmd": "_pillar",
        "id": minion_id,
        "grains": dict(grains),
        "tok": token,
        "nonce": request_nonce,
    }
    return build_message(
        encrypt_aes_192_cbc_hmac(pack_inner_load(load), shared_secret).to_bytes(),
        encoding="aes",
        message_id=message_id,
        api_key=api_key,
    )


def decrypt_message_load(message: SaltMessage, shared_secret: bytes) -> MutableMapping[str, Any]:
    """Decrypt and unpack an AES message load."""
    if message.body.get("enc") != "aes":
        raise ProtocolError("The message does not contain an AES load.")
    encrypted_load = message.body.get("load")
    if not isinstance(encrypted_load, bytes):
        raise ProtocolError("The AES message load must be bytes.")
    from .crypto import decrypt_aes_192_cbc_hmac

    return unpack_inner_load(decrypt_aes_192_cbc_hmac(encrypted_load, shared_secret))


def build_job_return(
    *,
    job: Mapping[str, Any],
    result: Mapping[str, Any],
    minion_id: str,
    shared_secret: bytes,
    private_key: RSAPrivateKey,
    nonce: str | None = None,
    message_id: int | str = 1,
    api_key: str | None = None,
    signer: Any = rsa_x931_sign,
) -> SaltMessage:
    """Build the encrypted v3 `_return` request for a fixture job."""
    token = signer(b"salt", private_key)
    request_nonce = nonce if nonce is not None else uuid.uuid4().hex
    load = {
        "cmd": "_return",
        "jid": job.get("jid"),
        "id": minion_id,
        "tok": token,
        "return": result.get("return"),
        "retcode": result.get("retcode"),
        "success": result.get("success"),
        "fun": job.get("fun", job.get("function")),
        "fun_args": job.get("arg", job.get("args", ())),
        "nonce": request_nonce,
    }
    return build_message(
        encrypt_aes_192_cbc_hmac(pack_inner_load(load), shared_secret).to_bytes(),
        encoding="aes",
        message_id=message_id,
        api_key=api_key,
    )
