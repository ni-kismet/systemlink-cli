"""Tests for system trust store injection utilities."""

from __future__ import annotations

import importlib
import ssl
import sys
import types
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, List

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID


def _make_ca(
    ca: bool = True,
    signing: bool = True,
    expired: bool = False,
    key: rsa.RSAPrivateKey | None = None,
    signer: rsa.RSAPrivateKey | None = None,
) -> x509.Certificate:
    key = key or rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Test CA")])
    now = datetime.now(timezone.utc)
    return (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=2))
        .not_valid_after(now + timedelta(days=-1 if expired else 30))
        .add_extension(x509.BasicConstraints(ca=ca, path_length=None), critical=True)
        .add_extension(x509.SubjectKeyIdentifier.from_public_key(key.public_key()), critical=False)
        .add_extension(
            x509.KeyUsage(False, False, False, False, False, signing, signing, False, False),
            critical=True,
        )
        .sign(signer or key, hashes.SHA256())
    )


@pytest.mark.parametrize("encoding", [serialization.Encoding.PEM, serialization.Encoding.DER])
def test_load_ca_certificate(encoding: serialization.Encoding, tmp_path: Path) -> None:
    """Import a public CA in either encoding without changing its fingerprint."""
    from slcli.ssl_trust import load_ca_certificate

    certificate = _make_ca()
    path = tmp_path / "ca.crt"
    path.write_bytes(certificate.public_bytes(encoding))
    loaded = load_ca_certificate("https://example.com/path", path)
    assert loaded.origin == "https://example.com:443"
    assert loaded.trust_type == "ca"
    assert loaded.self_signed
    assert loaded.fingerprint == certificate.fingerprint(hashes.SHA256()).hex().upper()


@pytest.mark.parametrize(
    "ca,signing,expired,message",
    [
        (False, True, False, "not a CA"),
        (True, False, False, "signing"),
        (True, True, True, "expired"),
    ],
)
def test_load_ca_rejects_invalid_certificate(
    ca: bool, signing: bool, expired: bool, message: str, tmp_path: Path
) -> None:
    """Only valid certificate-signing CAs may be imported."""
    from slcli.ssl_trust import load_ca_certificate

    path = tmp_path / "ca.pem"
    path.write_bytes(_make_ca(ca, signing, expired).public_bytes(serialization.Encoding.PEM))
    with pytest.raises(ValueError, match=message):
        load_ca_certificate("https://example.com", path)


def test_load_ca_rejects_bundle(tmp_path: Path) -> None:
    """Fingerprint approval must not silently trust additional certificates."""
    from slcli.ssl_trust import load_ca_certificate

    path = tmp_path / "bundle.pem"
    path.write_bytes(_make_ca().public_bytes(serialization.Encoding.PEM) * 2)
    with pytest.raises(ValueError, match="exactly one"):
        load_ca_certificate("https://example.com", path)


def test_self_issued_ca_is_not_self_signed(tmp_path: Path) -> None:
    """A same-name CA rollover signed by another key is not self-signed."""
    from slcli.ssl_trust import load_ca_certificate

    signer = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    path = tmp_path / "rollover.pem"
    path.write_bytes(_make_ca(signer=signer).public_bytes(serialization.Encoding.PEM))
    assert not load_ca_certificate("https://example.com", path).self_signed


def test_duplicate_ca_extensions_are_validation_errors(monkeypatch: Any, tmp_path: Path) -> None:
    """Malformed extension errors must not escape as unhandled exceptions."""
    from slcli.ssl_trust import load_ca_certificate

    class Certificate:
        @property
        def extensions(self) -> x509.Extensions:
            raise x509.DuplicateExtension("duplicate", x509.ExtensionOID.BASIC_CONSTRAINTS)

    path = tmp_path / "malformed.pem"
    path.write_bytes(b"-----BEGIN CERTIFICATE-----\nmalformed\n")
    monkeypatch.setattr(x509, "load_pem_x509_certificates", lambda _content: [Certificate()])
    with pytest.raises(ValueError, match="Invalid CA certificate extensions"):
        load_ca_certificate("https://example.com", path)


def test_reading_trust_does_not_create_directory(monkeypatch: Any, tmp_path: Path) -> None:
    """Inspecting missing trust metadata must not require a writable directory."""
    from slcli.ssl_trust import get_managed_trust_records, get_managed_trust_path

    monkeypatch.setenv("SLCLI_CONFIG", str(tmp_path / "config.json"))
    assert get_managed_trust_records() == []
    assert get_managed_trust_path("https://example.com") is None
    assert not (tmp_path / "trust").exists()


def test_legacy_leaf_bundle_is_restricted_to_fingerprinted_certificate(
    monkeypatch: Any, tmp_path: Path
) -> None:
    """Legacy leaf bundles must not trust bundled intermediates as anchors."""
    from slcli.ssl_trust import (
        ServerCertificate,
        get_managed_trust_path,
        save_managed_certificate,
    )

    monkeypatch.setenv("SLCLI_CONFIG", str(tmp_path / "config.json"))
    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca = _make_ca(key=ca_key)
    leaf_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = datetime.now(timezone.utc)
    leaf = (
        x509.CertificateBuilder()
        .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "example.com")]))
        .issuer_name(ca.subject)
        .public_key(leaf_key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=10))
        .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
        .sign(ca_key, hashes.SHA256())
    )
    leaf_pem = leaf.public_bytes(serialization.Encoding.PEM)
    save_managed_certificate(
        ServerCertificate(
            origin="https://example.com:443",
            pem=leaf_pem + ca.public_bytes(serialization.Encoding.PEM),
            fingerprint=leaf.fingerprint(hashes.SHA256()).hex().upper(),
            subject="example.com",
            issuer="Test CA",
            sans=[],
            not_before="before",
            not_after="after",
            self_signed=False,
        )
    )

    trusted_path = get_managed_trust_path("https://example.com")

    assert trusted_path is not None
    assert trusted_path.read_bytes() == leaf_pem


@pytest.mark.parametrize(
    "destination,allowed",
    [
        ("/next", True),
        ("https://other.example.com/next", False),
        ("http://example.com/next", False),
        ("https://example.com:8443/next", False),
    ],
)
def test_managed_trust_rejects_cross_origin_redirects(
    monkeypatch: Any, tmp_path: Path, destination: str, allowed: bool
) -> None:
    """Redirects must not send credentials or managed CA trust to another origin."""
    import requests
    from slcli.ssl_trust import (
        load_ca_certificate,
        save_managed_certificate,
        use_standard_ssl_context,
    )

    monkeypatch.setenv("SLCLI_CONFIG", str(tmp_path / "config.json"))
    ca_path = tmp_path / "ca.pem"
    ca_path.write_bytes(_make_ca().public_bytes(serialization.Encoding.PEM))
    trusted_path = save_managed_certificate(load_ca_certificate("https://example.com", ca_path))
    sent_urls: list[str] = []

    def send(
        adapter: requests.adapters.HTTPAdapter, request: requests.PreparedRequest, **kwargs: Any
    ) -> requests.Response:
        assert request.url is not None
        sent_urls.append(request.url)
        response = requests.Response()
        response.url = request.url
        response.request = request
        response._content = b"{}"
        response.status_code = 302 if len(sent_urls) == 1 else 200
        if response.status_code == 302:
            response.headers["Location"] = destination
        return response

    monkeypatch.setattr(requests.adapters.HTTPAdapter, "send", send)
    with use_standard_ssl_context(str(trusted_path)), requests.Session() as session:
        if allowed:
            assert session.get("https://example.com", verify=str(trusted_path)).status_code == 200
            assert len(sent_urls) == 2
        else:
            with pytest.raises(requests.exceptions.SSLError, match="cross-origin"):
                session.get(
                    "https://example.com",
                    headers={"x-ni-api-key": "test-key"},
                    verify=str(trusted_path),
                )
            assert len(sent_urls) == 1


@pytest.mark.parametrize("strict", [False, True])
@pytest.mark.parametrize(
    "case", ["valid", "renewed", "wrong-issuer", "expired", "hostname", "leaf"]
)
def test_managed_trust_tls_verification(tmp_path: Path, strict: bool, case: str) -> None:
    """CA and legacy leaf trust preserve issuer, hostname, and expiry verification."""
    from slcli import ssl_trust
    from urllib3.util.ssl_ import create_urllib3_context

    ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    ca_certificate = _make_ca(key=ca_key)
    trusted_path = tmp_path / "trusted.pem"
    trusted_path.write_bytes(ca_certificate.public_bytes(serialization.Encoding.PEM))
    if case == "wrong-issuer":
        ca_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        ca_certificate = _make_ca(key=ca_key)
    for _ in range(2 if case == "renewed" else 1):
        leaf_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        now = datetime.now(timezone.utc)
        leaf = (
            x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "example.com")]))
            .issuer_name(ca_certificate.subject)
            .public_key(leaf_key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=2))
            .not_valid_after(now + timedelta(days=-1 if case == "expired" else 10))
            .add_extension(x509.BasicConstraints(ca=False, path_length=None), critical=True)
            .add_extension(
                x509.SubjectAlternativeName([x509.DNSName("example.com")]), critical=False
            )
            .add_extension(
                x509.AuthorityKeyIdentifier.from_issuer_public_key(ca_key.public_key()),
                critical=False,
            )
            .sign(ca_key, hashes.SHA256())
        )
        certificate_path = tmp_path / "server.pem"
        key_path = tmp_path / "server.key"
        certificate_path.write_bytes(leaf.public_bytes(serialization.Encoding.PEM))
        key_path.write_bytes(
            leaf_key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.PKCS8,
                serialization.NoEncryption(),
            )
        )
        if case == "leaf":
            trusted_path.write_bytes(leaf.public_bytes(serialization.Encoding.PEM))
        server_context = ssl_trust._STANDARD_SSL_CONTEXT(ssl.PROTOCOL_TLS_SERVER)
        server_context.load_cert_chain(str(certificate_path), str(key_path))
        with ssl_trust.use_standard_ssl_context(str(trusted_path)):
            client_context = create_urllib3_context()
            client_context.load_verify_locations(cafile=str(trusted_path))
            if strict:
                client_context.verify_flags |= ssl.VERIFY_X509_STRICT
            assert client_context.check_hostname
            assert client_context.verify_mode == ssl.CERT_REQUIRED
            server_in, server_out = ssl.MemoryBIO(), ssl.MemoryBIO()
            client_in, client_out = ssl.MemoryBIO(), ssl.MemoryBIO()
            server = server_context.wrap_bio(server_in, server_out, server_side=True)
            client = client_context.wrap_bio(
                client_in,
                client_out,
                server_hostname="other.example.com" if case == "hostname" else "example.com",
            )

            def handshake() -> None:
                client_done = server_done = False
                for _ in range(10):
                    try:
                        client.do_handshake()
                        client_done = True
                    except ssl.SSLWantReadError:
                        pass
                    server_in.write(client_out.read())
                    try:
                        server.do_handshake()
                        server_done = True
                    except ssl.SSLWantReadError:
                        pass
                    client_in.write(server_out.read())
                    if client_done and server_done:
                        return
                raise AssertionError("TLS handshake did not complete")

            if case in ("wrong-issuer", "expired", "hostname"):
                with pytest.raises(ssl.SSLCertVerificationError):
                    handshake()
            else:
                handshake()


def test_explicit_context_restored_on_failure() -> None:
    """An explicit trust failure must not leave the OS TLS context replaced."""
    import requests.adapters
    import urllib3.util.ssl_ as urllib3_ssl
    from slcli.ssl_trust import use_standard_ssl_context

    original_ssl = ssl.SSLContext
    original_urllib3 = urllib3_ssl.SSLContext
    original_preloaded = getattr(requests.adapters, "_preloaded_ssl_context", None)
    with pytest.raises(ValueError):
        with use_standard_ssl_context("ca.pem"):
            raise ValueError("request failed")
    assert ssl.SSLContext is original_ssl
    assert urllib3_ssl.SSLContext is original_urllib3
    assert getattr(requests.adapters, "_preloaded_ssl_context", None) is original_preloaded


def test_explicit_contexts_are_serialized() -> None:
    """Concurrent explicit verification contexts cannot restore each other's patches."""
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    import requests.sessions
    import urllib3.util.ssl_ as urllib3_ssl
    from slcli.ssl_trust import use_standard_ssl_context

    first_entered, second_attempted, second_entered = Event(), Event(), Event()
    original_ssl = ssl.SSLContext
    original_urllib3 = urllib3_ssl.SSLContext
    original_send = requests.sessions.Session.send

    def first() -> None:
        with use_standard_ssl_context("first.pem"):
            first_entered.set()
            assert second_attempted.wait(5)
            assert not second_entered.wait(0.05)

    def second() -> None:
        assert first_entered.wait(5)
        second_attempted.set()
        with use_standard_ssl_context("second.pem"):
            second_entered.set()

    with ThreadPoolExecutor(max_workers=2) as executor:
        first_future = executor.submit(first)
        second_future = executor.submit(second)
        first_future.result(timeout=10)
        second_future.result(timeout=10)
    assert second_entered.is_set()
    assert ssl.SSLContext is original_ssl
    assert urllib3_ssl.SSLContext is original_urllib3
    assert requests.sessions.Session.send is original_send


def test_certificate_inspection_waits_for_explicit_context(monkeypatch: Any) -> None:
    """Certificate inspection must share the explicit context serialization lock."""
    from concurrent.futures import ThreadPoolExecutor
    from threading import Event
    from slcli import ssl_trust

    original_context = object()
    first_entered, inspection_attempted, inspection_started = Event(), Event(), Event()
    allow_inspection_to_finish = Event()
    monkeypatch.setattr(ssl_trust.ssl, "SSLContext", original_context)

    def connect(*args: Any, **kwargs: Any) -> Any:
        inspection_started.set()
        assert allow_inspection_to_finish.wait(5)
        raise OSError("stop inspection")

    monkeypatch.setattr(ssl_trust.socket, "create_connection", connect)

    def use_explicit_context() -> None:
        with ssl_trust.use_standard_ssl_context("managed.pem"):
            first_entered.set()
            assert inspection_attempted.wait(5)
            assert not inspection_started.wait(0.05)

    def inspect_certificate() -> None:
        assert first_entered.wait(5)
        inspection_attempted.set()
        with pytest.raises(OSError, match="stop inspection"):
            ssl_trust.inspect_server_certificate("https://example.com")

    with ThreadPoolExecutor(max_workers=2) as executor:
        explicit_future = executor.submit(use_explicit_context)
        inspection_future = executor.submit(inspect_certificate)
        explicit_future.result(timeout=10)
        assert inspection_started.wait(5)
        allow_inspection_to_finish.set()
        inspection_future.result(timeout=10)

    assert ssl_trust.ssl.SSLContext is original_context


def _make_dummy_truststore(inject_side_effect: Any = None) -> Any:
    mod = types.ModuleType("truststore")
    called: List[bool] = []

    def inject_into_requests() -> None:  # type: ignore
        if inject_side_effect:
            raise inject_side_effect
        called.append(True)

    mod.inject_into_requests = inject_into_requests  # type: ignore[attr-defined]
    mod._called = called  # type: ignore[attr-defined]
    return mod


def test_injection_success(monkeypatch: Any) -> None:
    dummy = _make_dummy_truststore()
    monkeypatch.setitem(sys.modules, "truststore", dummy)
    from slcli import ssl_trust

    importlib.reload(ssl_trust)
    ssl_trust.inject_os_trust()
    assert dummy._called, "truststore.inject_into_requests should have been called"


def test_injection_disabled(monkeypatch: Any) -> None:
    dummy = _make_dummy_truststore()
    monkeypatch.setitem(sys.modules, "truststore", dummy)
    monkeypatch.setenv("SLCLI_DISABLE_OS_TRUST", "1")
    from slcli import ssl_trust

    importlib.reload(ssl_trust)
    ssl_trust.inject_os_trust()
    assert not dummy._called, "Injection should be skipped when disabled"


def test_injection_force_failure(monkeypatch: Any) -> None:
    dummy = _make_dummy_truststore(inject_side_effect=RuntimeError("boom"))
    monkeypatch.setitem(sys.modules, "truststore", dummy)
    monkeypatch.setenv("SLCLI_FORCE_OS_TRUST", "1")
    from slcli import ssl_trust

    importlib.reload(ssl_trust)
    with pytest.raises(RuntimeError):
        ssl_trust.inject_os_trust()


def test_server_origin_normalization() -> None:
    """Managed trust should normalize IDNs, ports, and non-HTTPS URLs."""
    from slcli.ssl_trust import get_ssl_server_origin

    assert get_ssl_server_origin("https://Example.com/path") == "https://example.com:443"
    assert get_ssl_server_origin("https://example.com:8443") == "https://example.com:8443"
    assert get_ssl_server_origin("https://bücher.example") == "https://xn--bcher-kva.example:443"
    with pytest.raises(ValueError, match="HTTPS"):
        get_ssl_server_origin("http://example.com")


def test_managed_trust_accepts_legacy_unicode_origin_for_initial_request(
    monkeypatch: Any, tmp_path: Path
) -> None:
    """A Unicode-keyed trust record matches requests' prepared IDNA origin."""
    import hashlib
    import json

    import requests
    from slcli.ssl_trust import get_managed_trust_path, use_standard_ssl_context

    config_file = tmp_path / "config.json"
    monkeypatch.setattr(
        "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
    )
    legacy_origin = "https://bücher.example:443"
    certificate = _make_ca()
    fingerprint = certificate.fingerprint(hashes.SHA256()).hex().upper()
    trust_directory = tmp_path / "trust"
    trust_directory.mkdir()
    stem = hashlib.sha256(legacy_origin.encode("utf-8")).hexdigest()
    pem_path = trust_directory / f"{stem}.pem"
    pem_path.write_bytes(certificate.public_bytes(serialization.Encoding.PEM))
    pem_path.with_suffix(".json").write_text(
        json.dumps({"origin": legacy_origin, "fingerprint": fingerprint, "trust-type": "ca"}),
        encoding="utf-8",
    )
    sent_urls: list[str] = []

    def send(
        adapter: requests.adapters.HTTPAdapter, request: requests.PreparedRequest, **kwargs: Any
    ) -> requests.Response:
        assert request.url is not None
        sent_urls.append(request.url)
        response = requests.Response()
        response.url = request.url
        response.request = request
        response._content = b"{}"
        response.status_code = 200
        return response

    monkeypatch.setattr(requests.adapters.HTTPAdapter, "send", send)
    assert get_managed_trust_path("https://xn--bcher-kva.example") == pem_path
    with use_standard_ssl_context(str(pem_path)), requests.Session() as session:
        response = session.get("https://bücher.example", verify=str(pem_path))

    assert response.status_code == 200
    assert sent_urls == ["https://xn--bcher-kva.example/"]


def test_managed_certificate_persistence_is_origin_scoped(monkeypatch: Any, tmp_path: Any) -> None:
    """Managed certificates should persist securely and only match their origin."""
    import json

    from slcli.ssl_trust import (
        ServerCertificate,
        get_managed_trust_path,
        get_managed_trust_records,
        remove_managed_trust,
        save_managed_certificate,
    )

    config_file = tmp_path / "config.json"
    monkeypatch.setattr(
        "slcli.profiles.ProfileConfig.get_config_path", classmethod(lambda cls: config_file)
    )
    trusted_certificate = _make_ca()
    certificate = ServerCertificate(
        origin="https://bücher.example:443",
        pem=trusted_certificate.public_bytes(serialization.Encoding.PEM),
        fingerprint=trusted_certificate.fingerprint(hashes.SHA256()).hex().upper(),
        subject="commonName=example.com",
        issuer="commonName=example.com",
        sans=["example.com"],
        not_before="2026-01-01T00:00:00+00:00",
        not_after="2027-01-01T00:00:00+00:00",
        self_signed=True,
        trust_type="ca",
    )

    path = save_managed_certificate(certificate)
    assert path.read_bytes() == certificate.pem
    assert json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))["origin"] == (
        "https://xn--bcher-kva.example:443"
    )
    if sys.platform != "win32":
        assert path.stat().st_mode & 0o777 == 0o600
    assert get_managed_trust_path("https://bücher.example/path") == path
    assert get_managed_trust_path("https://other.example.com") is None
    assert get_managed_trust_records()[0]["fingerprint"] == certificate.fingerprint
    assert remove_managed_trust("https://bücher.example") is True
    assert get_managed_trust_path("https://bücher.example") is None


def test_certificate_inspection_uses_unpatched_context_and_peer_chain(monkeypatch: Any) -> None:
    """Inspection should bypass truststore and retain the full peer certificate chain."""
    from slcli import ssl_trust

    class FakeCertificate:
        subject = object()
        issuer = subject
        extensions = types.SimpleNamespace(
            get_extension_for_class=lambda _certificate_type: types.SimpleNamespace(
                value=["example.com"]
            )
        )

        def public_bytes(self, _encoding: Any) -> bytes:
            return b"leaf-pem"

        def fingerprint(self, _algorithm: Any) -> bytes:
            return b"\x01" * 32

        def verify_directly_issued_by(self, _issuer: Any) -> None:
            pass

    class FakePeerCertificate:
        def public_bytes(self) -> str:
            return "chain-pem"

    class FakeTlsSocket:
        _sslobj = types.SimpleNamespace(
            get_unverified_chain=lambda: [FakePeerCertificate(), FakePeerCertificate()]
        )

        def __enter__(self) -> "FakeTlsSocket":
            return self

        def __exit__(self, *args: Any) -> None:
            pass

        def getpeercert(self, binary_form: bool = False) -> bytes:
            assert binary_form is True
            return b"certificate-der"

    class FakeTcpSocket:
        def __enter__(self) -> "FakeTcpSocket":
            return self

        def __exit__(self, *args: Any) -> None:
            pass

    class FakeContext:
        def __init__(self, _protocol: int) -> None:
            self.check_hostname = True
            self.verify_mode = ssl_trust.ssl.CERT_REQUIRED

        def wrap_socket(self, _socket: Any, server_hostname: str) -> FakeTlsSocket:
            assert server_hostname == "example.com"
            return FakeTlsSocket()

    patched_context = object()
    monkeypatch.setattr(ssl_trust.ssl, "SSLContext", patched_context)
    monkeypatch.setattr(ssl_trust, "_STANDARD_SSL_CONTEXT", FakeContext)
    monkeypatch.setattr(
        ssl_trust.socket, "create_connection", lambda *args, **kwargs: FakeTcpSocket()
    )
    monkeypatch.setattr(
        ssl_trust.x509, "load_der_x509_certificate", lambda _certificate_der: FakeCertificate()
    )
    monkeypatch.setattr(ssl_trust, "_certificate_name", lambda _name: "name")
    monkeypatch.setattr(
        ssl_trust, "_certificate_validity", lambda _certificate: ("before", "after")
    )

    certificate = ssl_trust.inspect_server_certificate("https://example.com")

    assert ssl_trust.ssl.SSLContext is patched_context
    assert certificate.pem == b"chain-pemchain-pem"
    assert certificate.fingerprint == "01" * 32
