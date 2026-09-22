"""Unit tests for managed-client cryptographic adapters."""

import hashlib

import pytest
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey

import slcli.managed_client.crypto as crypto_module
from slcli.managed_client.crypto import (
    CryptoError,
    decrypt_aes_192_cbc_hmac,
    decrypt_rsa_oaep,
    encrypt_aes_192_cbc_hmac,
    encrypt_rsa_oaep,
    generate_rsa_key_pair,
    load_rsa_private_key,
    rsa_x931_decrypt,
    rsa_x931_sign,
    serialize_private_key,
)
from slcli.managed_client.models import UnsupportedCryptoError


def test_aes_192_cbc_hmac_round_trip() -> None:
    """The authenticated AES envelope round-trips deterministic plaintext."""
    key = b"01234567890123456789012345678901234567890123456789012345"
    payload = encrypt_aes_192_cbc_hmac(
        b"managed-client payload",
        key,
        iv=b"1234567890abcdef",
    )

    assert decrypt_aes_192_cbc_hmac(payload.to_bytes(), key) == b"managed-client payload"


def test_aes_192_cbc_hmac_rejects_tampering() -> None:
    """Changing ciphertext fails before plaintext is returned."""
    key = b"01234567890123456789012345678901234567890123456789012345"
    serialized = bytearray(encrypt_aes_192_cbc_hmac(b"payload", key).to_bytes())
    serialized[20] ^= 1

    with pytest.raises(CryptoError, match="integrity verification"):
        decrypt_aes_192_cbc_hmac(bytes(serialized), key)


def test_rsa_oaep_round_trip_and_key_loading() -> None:
    """RSA-OAEP and the persisted PEM representation use the same identity."""
    key_pair = generate_rsa_key_pair()
    ciphertext = encrypt_rsa_oaep(b"session secret", key_pair.public_key)
    loaded = load_rsa_private_key(serialize_private_key(key_pair.private_key))

    assert decrypt_rsa_oaep(ciphertext, loaded.private_key) == b"session secret"
    assert isinstance(loaded.private_key, RSAPrivateKey)


def test_x931_signing_and_public_recovery_use_exact_padding() -> None:
    """The provider performs the raw X9.31 operation required by v3."""
    key_pair = generate_rsa_key_pair()

    try:
        signature = rsa_x931_sign(b"payload", key_pair.private_key)
    except UnsupportedCryptoError:
        pytest.skip("No supported OpenSSL libcrypto X9.31 provider is installed.")

    assert rsa_x931_decrypt(signature, key_pair.public_key) == b"payload"


def test_x931_recovers_v3_session_digest_and_rejects_malformed_signature() -> None:
    """X9.31 recovers the ASCII-hex digest shape used by v3 auth."""
    key_pair = generate_rsa_key_pair()
    digest = hashlib.sha256(b"shared-secret").hexdigest().encode("ascii")

    try:
        signature = rsa_x931_sign(digest, key_pair.private_key)
    except UnsupportedCryptoError:
        pytest.skip("No supported OpenSSL libcrypto X9.31 provider is installed.")

    assert rsa_x931_decrypt(signature, key_pair.public_key) == digest
    with pytest.raises(CryptoError, match="invalid length"):
        rsa_x931_decrypt(signature[:-1], key_pair.public_key)


def test_x931_signing_fails_closed_without_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    """The v3 primitive cannot silently use another padding mode."""
    key_pair = generate_rsa_key_pair()

    def unavailable_provider() -> object:
        raise UnsupportedCryptoError("RSA X9.31 provider unavailable")

    monkeypatch.setattr(crypto_module, "_load_x931_provider", unavailable_provider)
    with pytest.raises(UnsupportedCryptoError, match="X9.31"):
        rsa_x931_sign(b"payload", key_pair.private_key)
