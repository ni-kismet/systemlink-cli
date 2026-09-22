"""Approved cryptographic building blocks for the v3 protocol adapter."""

from __future__ import annotations

import ctypes
import ctypes.util
import hashlib
import os
import sys
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Callable, Union

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding as asym_padding
from cryptography.hazmat.primitives.asymmetric.rsa import (
    RSAPrivateKey,
    RSAPublicKey,
    generate_private_key,
)
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes
from cryptography.hazmat.primitives.hmac import HMAC

from .models import ManagedClientError, UnsupportedCryptoError

AES_192_KEY_SIZE = 24
AES_BLOCK_SIZE = 16
HMAC_TAG_SIZE = 32
SALT_SHARED_SECRET_SIZE = AES_192_KEY_SIZE + HMAC_TAG_SIZE
DEFAULT_RSA_KEY_SIZE = 2048
SALT_PADDING_PREFIX = b"pickle::"
RSA_X931_PADDING = 5


class CryptoError(ManagedClientError):
    """Raised when a cryptographic input is invalid or cannot be verified."""


@dataclass(frozen=True)
class RsaKeyPair:
    """An RSA private key and its derived public key."""

    private_key: RSAPrivateKey = field(repr=False)

    @property
    def public_key(self) -> RSAPublicKey:
        """Return the public key corresponding to the private key."""
        return self.private_key.public_key()


@dataclass(frozen=True)
class EncryptedPayload:
    """AES-CBC ciphertext with its IV and HMAC-SHA256 authentication tag."""

    iv: bytes
    ciphertext: bytes
    tag: bytes

    def __post_init__(self) -> None:
        """Validate the serialized envelope fields."""
        if len(self.iv) != AES_BLOCK_SIZE:
            raise CryptoError("The AES-CBC IV must be 16 bytes.")
        if not self.ciphertext or len(self.ciphertext) % AES_BLOCK_SIZE:
            raise CryptoError("The AES-CBC ciphertext has an invalid length.")
        if len(self.tag) != HMAC_TAG_SIZE:
            raise CryptoError("The HMAC-SHA256 tag must be 32 bytes.")

    def to_bytes(self) -> bytes:
        """Serialize the envelope without exposing any plaintext."""
        return self.iv + self.ciphertext + self.tag

    @classmethod
    def from_bytes(cls, value: bytes) -> "EncryptedPayload":
        """Parse a serialized AES-CBC/HMAC envelope."""
        minimum_size = AES_BLOCK_SIZE + AES_BLOCK_SIZE + HMAC_TAG_SIZE
        if len(value) < minimum_size:
            raise CryptoError("The encrypted payload is truncated.")
        return cls(
            iv=value[:AES_BLOCK_SIZE],
            ciphertext=value[AES_BLOCK_SIZE:-HMAC_TAG_SIZE],
            tag=value[-HMAC_TAG_SIZE:],
        )


def generate_rsa_key_pair(key_size: int = DEFAULT_RSA_KEY_SIZE) -> RsaKeyPair:
    """Generate an RSA key pair for a test-minion identity."""
    if key_size < 2048:
        raise ValueError("RSA keys must be at least 2048 bits.")
    return RsaKeyPair(generate_private_key(public_exponent=65537, key_size=key_size))


def serialize_private_key(private_key: RSAPrivateKey) -> bytes:
    """Serialize an RSA private key for a permission-protected state file."""
    return private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )


def load_rsa_private_key(value: bytes) -> RsaKeyPair:
    """Load an unencrypted PEM RSA private key from isolated state."""
    try:
        private_key = serialization.load_pem_private_key(value, password=None)
    except Exception as error:
        raise CryptoError("The stored RSA private key is invalid.") from error
    if not isinstance(private_key, RSAPrivateKey):
        raise CryptoError("The stored private key is not an RSA key.")
    return RsaKeyPair(private_key)


def serialize_public_key(public_key: RSAPublicKey) -> bytes:
    """Serialize an RSA public key in PEM SubjectPublicKeyInfo format."""
    return public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo,
    )


def load_rsa_public_key(value: bytes) -> RSAPublicKey:
    """Load a PEM RSA public key received from the Salt master."""
    try:
        public_key = serialization.load_pem_public_key(value)
    except Exception as error:
        raise CryptoError("The Salt master public key is invalid.") from error
    if not isinstance(public_key, RSAPublicKey):
        raise CryptoError("The Salt master public key is not an RSA key.")
    return public_key


def public_key_fingerprint(public_key: RSAPublicKey) -> str:
    """Return a non-secret SHA-256 fingerprint for an RSA public key."""
    return hashlib.sha256(serialize_public_key(public_key)).hexdigest()


def _validate_aes_key(key: bytes) -> None:
    if len(key) != SALT_SHARED_SECRET_SIZE:
        raise CryptoError("The Salt shared secret must be 56 bytes.")


def _secret_parts(secret: bytes) -> tuple[bytes, bytes]:
    """Split a Salt shared secret into AES and HMAC keys."""
    _validate_aes_key(secret)
    return secret[:AES_192_KEY_SIZE], secret[AES_192_KEY_SIZE:]


def _salt_pad(plaintext: bytes, nonce: bytes | None) -> bytes:
    """Apply Salt's pickle prefix, optional nonce, and byte padding."""
    if nonce is not None and len(nonce) != 36:
        raise CryptoError("The Salt nonce must be a 36-byte UUID.")
    data = SALT_PADDING_PREFIX + (nonce or b"") + plaintext
    padding_size = AES_BLOCK_SIZE - (len(data) % AES_BLOCK_SIZE)
    return data + bytes([padding_size]) * padding_size


def _salt_unpad(plaintext: bytes, has_nonce: bool) -> bytes:
    """Remove and validate Salt's padding and optional nonce."""
    if not plaintext or plaintext[: len(SALT_PADDING_PREFIX)] != SALT_PADDING_PREFIX:
        raise CryptoError("The decrypted Salt payload has an invalid prefix.")
    padding_size = plaintext[-1]
    if padding_size < 1 or padding_size > AES_BLOCK_SIZE:
        raise CryptoError("The decrypted Salt payload has invalid padding.")
    if plaintext[-padding_size:] != bytes([padding_size]) * padding_size:
        raise CryptoError("The decrypted Salt payload has invalid padding.")
    start = len(SALT_PADDING_PREFIX) + (36 if has_nonce else 0)
    if len(plaintext) < start + padding_size:
        raise CryptoError("The decrypted Salt payload is truncated.")
    return plaintext[start:-padding_size]


def encrypt_aes_192_cbc_hmac(
    plaintext: bytes,
    secret: bytes,
    iv: bytes | None = None,
    nonce: bytes | None = None,
) -> EncryptedPayload:
    """Encrypt bytes using Salt's AES-192-CBC/HMAC-SHA256 envelope."""
    aes_key, hmac_key = _secret_parts(secret)
    selected_iv = os.urandom(AES_BLOCK_SIZE) if iv is None else iv
    if len(selected_iv) != AES_BLOCK_SIZE:
        raise CryptoError("The AES-CBC IV must be 16 bytes.")

    padded_plaintext = _salt_pad(plaintext, nonce)
    encryptor = Cipher(algorithms.AES(aes_key), modes.CBC(selected_iv)).encryptor()
    ciphertext = encryptor.update(padded_plaintext) + encryptor.finalize()

    authenticator = HMAC(hmac_key, hashes.SHA256())
    authenticator.update(selected_iv + ciphertext)
    return EncryptedPayload(selected_iv, ciphertext, authenticator.finalize())


def decrypt_aes_192_cbc_hmac(
    payload: Union[EncryptedPayload, bytes],
    secret: bytes,
    has_nonce: bool = False,
) -> bytes:
    """Authenticate and decrypt a Salt AES-192-CBC/HMAC-SHA256 envelope."""
    aes_key, hmac_key = _secret_parts(secret)
    envelope = (
        payload if isinstance(payload, EncryptedPayload) else EncryptedPayload.from_bytes(payload)
    )

    authenticator = HMAC(hmac_key, hashes.SHA256())
    authenticator.update(envelope.iv + envelope.ciphertext)
    try:
        authenticator.verify(envelope.tag)
    except Exception as error:
        raise CryptoError("The encrypted payload failed integrity verification.") from error

    decryptor = Cipher(algorithms.AES(aes_key), modes.CBC(envelope.iv)).decryptor()
    padded_plaintext = decryptor.update(envelope.ciphertext) + decryptor.finalize()
    return _salt_unpad(padded_plaintext, has_nonce)


def encrypt_rsa_oaep(plaintext: bytes, public_key: RSAPublicKey) -> bytes:
    """Encrypt bytes with the RSA-OAEP parameters used by Salt."""
    return public_key.encrypt(
        plaintext,
        asym_padding.OAEP(
            mgf=asym_padding.MGF1(algorithm=hashes.SHA1()),
            algorithm=hashes.SHA1(),
            label=None,
        ),
    )


def decrypt_rsa_oaep(ciphertext: bytes, private_key: RSAPrivateKey) -> bytes:
    """Decrypt RSA-OAEP bytes with the parameters used by Salt."""
    return private_key.decrypt(
        ciphertext,
        asym_padding.OAEP(
            mgf=asym_padding.MGF1(algorithm=hashes.SHA1()),
            algorithm=hashes.SHA1(),
            label=None,
        ),
    )


def sign_rsa_pkcs1_sha1(message: bytes, private_key: RSAPrivateKey) -> bytes:
    """Sign an auth response load with Salt's public-key signature path."""
    return private_key.sign(message, asym_padding.PKCS1v15(), hashes.SHA1())


def verify_rsa_pkcs1_sha1(message: bytes, signature: bytes, public_key: RSAPublicKey) -> None:
    """Verify a Salt auth response signature."""
    public_key.verify(signature, message, asym_padding.PKCS1v15(), hashes.SHA1())


def verify_rsa_pkcs1_sha1_result(
    message: bytes, signature: bytes, public_key: RSAPublicKey
) -> bool:
    """Return whether an ordinary RSA-SHA1 signature is valid."""
    try:
        verify_rsa_pkcs1_sha1(message, signature, public_key)
    except Exception:
        return False
    return True


class _OpenSSLX931Provider:
    """Minimal libcrypto adapter for Salt's raw RSA X9.31 operation."""

    def __init__(self, library: ctypes.CDLL) -> None:
        self._library = library
        self._bio_new_mem_buf = self._bind(
            "BIO_new_mem_buf",
            [ctypes.c_void_p, ctypes.c_int],
            ctypes.c_void_p,
        )
        self._bio_free = self._bind("BIO_free", [ctypes.c_void_p], ctypes.c_int)
        self._read_private_key = self._bind(
            "PEM_read_bio_RSAPrivateKey",
            [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p, ctypes.c_void_p],
            ctypes.c_void_p,
        )
        self._read_public_key = self._bind(
            "PEM_read_bio_RSA_PUBKEY",
            [ctypes.c_void_p, ctypes.POINTER(ctypes.c_void_p), ctypes.c_void_p, ctypes.c_void_p],
            ctypes.c_void_p,
        )
        self._rsa_free = self._bind("RSA_free", [ctypes.c_void_p], None)
        self._rsa_size = self._bind("RSA_size", [ctypes.c_void_p], ctypes.c_int)
        self._rsa_private_encrypt = self._bind(
            "RSA_private_encrypt",
            [ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int],
            ctypes.c_int,
        )
        self._rsa_public_decrypt = self._bind(
            "RSA_public_decrypt",
            [ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int],
            ctypes.c_int,
        )

    def _bind(self, name: str, argtypes: list[Any], restype: Any) -> Callable[..., Any]:
        try:
            function: Any = getattr(self._library, name)
        except AttributeError as error:
            raise UnsupportedCryptoError(
                "The OpenSSL libcrypto provider lacks a required RSA X9.31 symbol."
            ) from error
        function.argtypes = argtypes
        function.restype = restype
        return function

    def _read_rsa_key(self, pem: bytes, reader: Callable[..., Any]) -> ctypes.c_void_p:
        pem_buffer = ctypes.create_string_buffer(pem)
        bio = self._bio_new_mem_buf(ctypes.cast(pem_buffer, ctypes.c_void_p), len(pem))
        if not bio:
            raise CryptoError("The OpenSSL provider could not read the RSA key.")

        rsa = ctypes.c_void_p()
        try:
            result = reader(bio, ctypes.byref(rsa), None, None)
            if not result or not rsa.value:
                raise CryptoError("The OpenSSL provider could not read the RSA key.")
            return rsa
        finally:
            self._bio_free(bio)

    def _key_size(self, rsa: ctypes.c_void_p) -> int:
        key_size = self._rsa_size(rsa)
        if key_size <= 0:
            raise CryptoError("The OpenSSL provider returned an invalid RSA key size.")
        return key_size

    def sign(self, message: bytes, private_key: RSAPrivateKey) -> bytes:
        """Apply RSA private-key X9.31 padding and transformation."""
        pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
        rsa = self._read_rsa_key(pem, self._read_private_key)
        try:
            key_size = self._key_size(rsa)
            if not message or len(message) > key_size - 3:
                raise CryptoError("The RSA X9.31 message has an invalid length.")
            source = ctypes.create_string_buffer(message)
            destination = ctypes.create_string_buffer(key_size)
            result = self._rsa_private_encrypt(
                len(message),
                ctypes.cast(source, ctypes.c_void_p),
                ctypes.cast(destination, ctypes.c_void_p),
                rsa,
                RSA_X931_PADDING,
            )
            if result != key_size:
                raise CryptoError("The RSA X9.31 private operation failed.")
            return destination.raw[:result]
        finally:
            self._rsa_free(rsa)

    def recover(self, signature: bytes, public_key: RSAPublicKey) -> bytes:
        """Recover the raw message from an RSA X9.31 signature."""
        pem = serialize_public_key(public_key)
        rsa = self._read_rsa_key(pem, self._read_public_key)
        try:
            key_size = self._key_size(rsa)
            if len(signature) != key_size:
                raise CryptoError("The RSA X9.31 signature has an invalid length.")
            source = ctypes.create_string_buffer(signature)
            destination = ctypes.create_string_buffer(key_size)
            result = self._rsa_public_decrypt(
                len(signature),
                ctypes.cast(source, ctypes.c_void_p),
                ctypes.cast(destination, ctypes.c_void_p),
                rsa,
                RSA_X931_PADDING,
            )
            if result <= 0:
                raise CryptoError("The RSA X9.31 public operation failed.")
            return destination.raw[:result]
        finally:
            self._rsa_free(rsa)


def _x931_library_candidates() -> tuple[str, ...]:
    """Return platform-specific libcrypto names in discovery order."""
    candidates: list[str] = []
    discovered = ctypes.util.find_library("crypto")
    if discovered:
        candidates.append(discovered)

    if sys.platform == "darwin":
        candidates.extend(
            (
                "/opt/homebrew/opt/openssl@3/lib/libcrypto.3.dylib",
                "/usr/local/opt/openssl@3/lib/libcrypto.3.dylib",
                "/opt/homebrew/opt/openssl@1.1/lib/libcrypto.1.1.dylib",
                "/usr/local/opt/openssl@1.1/lib/libcrypto.1.1.dylib",
                "libcrypto.4.dylib",
                "libcrypto.3.dylib",
                "libcrypto.1.1.dylib",
            )
        )
    elif os.name == "nt":
        candidates.extend(
            (
                "libcrypto-3-x64.dll",
                "libcrypto-3.dll",
                "libcrypto-1_1-x64.dll",
                "libcrypto-1_1.dll",
                "libeay32.dll",
            )
        )
    else:
        candidates.extend(("libcrypto.so.3", "libcrypto.so.1.1", "libcrypto.so"))

    return tuple(dict.fromkeys(candidates))


@lru_cache(maxsize=1)
def _load_x931_provider() -> _OpenSSLX931Provider:
    """Load a libcrypto provider exposing the required legacy RSA symbols."""
    for candidate in _x931_library_candidates():
        try:
            return _OpenSSLX931Provider(ctypes.CDLL(candidate))
        except (OSError, UnsupportedCryptoError):
            continue
    raise UnsupportedCryptoError(
        "RSA X9.31 requires an OpenSSL libcrypto provider with legacy RSA symbols."
    )


def rsa_x931_sign(message: bytes, private_key: RSAPrivateKey) -> bytes:
    """Sign raw bytes with Salt-compatible RSA X9.31 padding."""
    return _load_x931_provider().sign(message, private_key)


def rsa_x931_decrypt(ciphertext: bytes, public_key: RSAPublicKey) -> bytes:
    """Recover raw bytes with Salt-compatible RSA X9.31 verification."""
    return _load_x931_provider().recover(ciphertext, public_key)
