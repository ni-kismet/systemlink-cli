"""System certificate store integration utilities.

Configures the `requests` stack to use the operating system trust store via the
`truststore` library. This enables enterprise / corporate roots without modifying
the bundled certifi CA file.

Environment Variables:
    SLCLI_DISABLE_OS_TRUST=1  -> Skip injection entirely (use certifi)
    SLCLI_FORCE_OS_TRUST=1    -> Raise on any injection failure (fail fast)
    SLCLI_DEBUG_OS_TRUST=1    -> Print traceback on injection errors
"""

from __future__ import annotations

import hashlib
import json
import os
import socket
import ssl
import sys
import traceback
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Dict, Iterator, List, Optional, Union
from urllib.parse import urlparse

from cryptography import x509
from cryptography.exceptions import InvalidSignature, UnsupportedAlgorithm
from cryptography.hazmat.primitives import hashes, serialization

OS_TRUST_INJECTED: bool = False
OS_TRUST_REASON: str = "not-attempted"
_STANDARD_SSL_CONTEXT = ssl.SSLContext
_SSL_CONTEXT_LOCK = RLock()


@dataclass(frozen=True)
class ServerCertificate:
    """Certificate details captured from a server TLS handshake."""

    origin: str
    pem: bytes
    fingerprint: str
    subject: str
    issuer: str
    sans: List[str]
    not_before: str
    not_after: str
    self_signed: bool
    trust_type: str = "leaf"

    def to_dict(self) -> Dict[str, Any]:
        """Return certificate metadata without including the PEM bytes."""
        return {
            "origin": self.origin,
            "fingerprint": self.fingerprint,
            "subject": self.subject,
            "issuer": self.issuer,
            "sans": self.sans,
            "not-before": self.not_before,
            "not-after": self.not_after,
            "self-signed": self.self_signed,
            "trust-type": self.trust_type,
        }


__all__ = [
    "OS_TRUST_INJECTED",
    "OS_TRUST_REASON",
    "ServerCertificate",
    "get_managed_trust_path",
    "get_managed_trust_records",
    "get_ssl_server_origin",
    "inspect_server_certificate",
    "load_ca_certificate",
    "inject_os_trust",
    "remove_managed_trust",
    "save_managed_certificate",
    "use_standard_ssl_context",
]


def get_ssl_server_origin(api_url: str) -> str:
    """Return a normalized HTTPS origin for a SystemLink API URL."""
    parsed = urlparse(api_url)
    if parsed.scheme.lower() != "https" or not parsed.hostname:
        raise ValueError("Managed certificate trust requires an HTTPS server URL.")

    hostname = parsed.hostname.lower()
    if ":" in hostname and not hostname.startswith("["):
        hostname = f"[{hostname}]"
    port = parsed.port or 443
    return f"https://{hostname}:{port}"


@contextmanager
def use_standard_ssl_context(ssl_verify: Union[bool, str]) -> Iterator[None]:
    """Use Python's standard SSL context for explicit CA bundle verification.

    The OS trust integration replaces SSL context implementations globally. For
    explicit CA bundle paths, requests must use the standard implementation so
    the supplied bundle is evaluated instead of the platform trust verifier.
    Partial-chain verification permits explicitly trusted leaves and intermediate
    CAs consistently across supported Python versions without bypassing hostname
    or certificate validity checks.
    Managed bundles reject cross-origin redirects. Explicit contexts are serialized
    so their process-global patches are restored in the correct order.
    """
    if not isinstance(ssl_verify, str):
        yield
        return

    with _SSL_CONTEXT_LOCK:
        with _use_standard_ssl_context(ssl_verify):
            yield


@contextmanager
def _use_standard_ssl_context(ssl_verify: str) -> Iterator[None]:
    """Apply process-global explicit trust patches while holding the context lock."""
    import requests.adapters
    import urllib3.util.ssl_ as urllib3_ssl

    patched_ssl_context = ssl.SSLContext
    patched_urllib3_context = urllib3_ssl.SSLContext
    has_preloaded_context = hasattr(requests.adapters, "_preloaded_ssl_context")
    patched_preloaded_context = getattr(requests.adapters, "_preloaded_ssl_context", None)
    original_send = requests.sessions.Session.send
    managed_origin = _get_managed_origin(ssl_verify)

    def send(
        session: requests.Session, request: requests.PreparedRequest, **kwargs: Any
    ) -> requests.Response:
        if managed_origin and kwargs.get("verify") == ssl_verify:
            try:
                request_origin = get_ssl_server_origin(request.url or "")
            except ValueError:
                request_origin = None
            if request_origin != managed_origin:
                raise requests.exceptions.SSLError(
                    f"Managed certificate trust is restricted to {managed_origin}; "
                    "cross-origin redirects are not allowed."
                )
        return original_send(session, request, **kwargs)

    def create_context(protocol: int) -> ssl.SSLContext:
        context = _STANDARD_SSL_CONTEXT(protocol)
        context.verify_flags |= ssl.VERIFY_X509_PARTIAL_CHAIN
        return context

    try:
        setattr(ssl, "SSLContext", _STANDARD_SSL_CONTEXT)
        setattr(urllib3_ssl, "SSLContext", create_context)
        if managed_origin:
            setattr(requests.sessions.Session, "send", send)
        if has_preloaded_context:
            setattr(
                requests.adapters,
                "_preloaded_ssl_context",
                create_context(ssl.PROTOCOL_TLS_CLIENT),
            )
        yield
    finally:
        setattr(ssl, "SSLContext", patched_ssl_context)
        setattr(urllib3_ssl, "SSLContext", patched_urllib3_context)
        if managed_origin:
            setattr(requests.sessions.Session, "send", original_send)
        if has_preloaded_context:
            setattr(requests.adapters, "_preloaded_ssl_context", patched_preloaded_context)


def _get_trust_directory(create: bool = False) -> Path:
    """Return the managed certificate directory, optionally creating it for writes."""
    from .profiles import ProfileConfig

    trust_directory = ProfileConfig.get_config_path().parent / "trust"
    if create:
        trust_directory.mkdir(parents=True, exist_ok=True)
        try:
            trust_directory.chmod(0o700)
        except OSError:
            pass
    return trust_directory


def _get_trust_stem(origin: str) -> str:
    """Return a stable, filesystem-safe name for a server origin."""
    return hashlib.sha256(origin.encode("utf-8")).hexdigest()


def get_managed_trust_path(api_url: str) -> Optional[Path]:
    """Return the managed PEM path for a URL when a trusted certificate exists."""
    origin = get_ssl_server_origin(api_url)
    pem_path = _get_trust_directory() / f"{_get_trust_stem(origin)}.pem"
    metadata_path = pem_path.with_suffix(".json")
    if not pem_path.is_file() or not metadata_path.is_file():
        return None
    try:
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if metadata.get("origin") != origin:
        return None
    return pem_path


def _get_managed_origin(pem_path: str) -> Optional[str]:
    """Identify an explicit PEM that belongs to the origin-scoped managed store."""
    try:
        path = Path(pem_path)
        metadata = json.loads(path.with_suffix(".json").read_text(encoding="utf-8"))
        origin = metadata.get("origin") if isinstance(metadata, dict) else None
        if isinstance(origin, str) and get_managed_trust_path(origin) == path:
            return origin
    except (OSError, ValueError):
        pass
    return None


def _is_self_signed(certificate: x509.Certificate) -> bool:
    """Distinguish self-signed certificates from self-issued rollover certificates."""
    if certificate.subject != certificate.issuer:
        return False
    try:
        certificate.verify_directly_issued_by(certificate)
    except (InvalidSignature, UnsupportedAlgorithm, ValueError):
        return False
    return True


def _certificate_name(name: x509.Name) -> str:
    """Format a certificate distinguished name for user-facing output."""
    return ", ".join(
        f"{attribute.oid._name or attribute.oid.dotted_string}="
        f"{attribute.value.decode('utf-8', errors='replace') if isinstance(attribute.value, bytes) else attribute.value}"
        for attribute in name
    )


def _certificate_validity(certificate: x509.Certificate) -> tuple[str, str]:
    """Read certificate validity dates across supported cryptography versions."""
    not_before = getattr(certificate, "not_valid_before_utc", None)
    not_after = getattr(certificate, "not_valid_after_utc", None)
    if not_before is None:
        not_before = certificate.not_valid_before
    if not_after is None:
        not_after = certificate.not_valid_after
    return not_before.isoformat(), not_after.isoformat()


def inspect_server_certificate(api_url: str, timeout: float = 5) -> ServerCertificate:
    """Inspect a server's leaf certificate without trusting it.

    This function is only for displaying certificate identity before explicit trust
    approval. It does not alter global SSL settings or persist the certificate.
    """
    origin = get_ssl_server_origin(api_url)
    parsed = urlparse(origin)
    assert parsed.hostname is not None
    port = parsed.port or 443
    certificate_chain_pem: Optional[bytes] = None
    patched_ssl_context = ssl.SSLContext
    try:
        setattr(ssl, "SSLContext", _STANDARD_SSL_CONTEXT)
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE

        with socket.create_connection((parsed.hostname, port), timeout=timeout) as tcp_socket:
            with context.wrap_socket(tcp_socket, server_hostname=parsed.hostname) as tls_socket:
                certificate_der = tls_socket.getpeercert(binary_form=True)
                ssl_object = getattr(tls_socket, "_sslobj", None)
                get_unverified_chain = getattr(ssl_object, "get_unverified_chain", None)
                if callable(get_unverified_chain):
                    try:
                        chain = get_unverified_chain()
                        chain_pem = b"".join(
                            (pem.encode("ascii") if isinstance(pem, str) else pem)
                            for chain_certificate in chain
                            for pem in (chain_certificate.public_bytes(),)
                        )
                        if chain_pem:
                            certificate_chain_pem = chain_pem
                    except (AttributeError, OSError, ValueError):
                        pass
    finally:
        setattr(ssl, "SSLContext", patched_ssl_context)

    if not certificate_der:
        raise ssl.SSLError("The server did not provide a TLS certificate.")

    certificate = x509.load_der_x509_certificate(certificate_der)
    not_before, not_after = _certificate_validity(certificate)
    sans: List[str] = []
    try:
        san_extension = certificate.extensions.get_extension_for_class(x509.SubjectAlternativeName)
        sans = [str(value) for value in san_extension.value]
    except x509.ExtensionNotFound:
        pass

    return ServerCertificate(
        origin=origin,
        pem=certificate_chain_pem or certificate.public_bytes(serialization.Encoding.PEM),
        fingerprint=certificate.fingerprint(hashes.SHA256()).hex().upper(),
        subject=_certificate_name(certificate.subject),
        issuer=_certificate_name(certificate.issuer),
        sans=sans,
        not_before=not_before,
        not_after=not_after,
        self_signed=_is_self_signed(certificate),
    )


def load_ca_certificate(api_url: str, certificate_path: Path) -> ServerCertificate:
    """Load one PEM or DER CA certificate for origin-scoped trust.

    Args:
        api_url: HTTPS origin to associate with the CA.
        certificate_path: Public CA certificate file, not a private key or bundle.

    Returns:
        Validated CA certificate and identity metadata.

    Raises:
        ValueError: The file is not a currently valid CA certificate.
        OSError: The certificate file cannot be read.
    """
    origin = get_ssl_server_origin(api_url)
    content = certificate_path.read_bytes()
    if b"-----BEGIN" in content:
        certificates = x509.load_pem_x509_certificates(content)
        if len(certificates) != 1 or b"PRIVATE KEY" in content:
            raise ValueError("Import exactly one public CA certificate, not a bundle or key.")
        certificate = certificates[0]
    else:
        certificate = x509.load_der_x509_certificate(content)
    try:
        extensions = certificate.extensions
    except (x509.DuplicateExtension, x509.UnsupportedGeneralNameType, ValueError) as exc:
        raise ValueError(f"Invalid CA certificate extensions: {exc}") from exc
    try:
        constraints = extensions.get_extension_for_class(x509.BasicConstraints)
    except x509.ExtensionNotFound as exc:
        raise ValueError("The certificate must have CA basic constraints.") from exc
    if not constraints.value.ca:
        raise ValueError("The certificate is not a CA certificate.")
    try:
        usage = extensions.get_extension_for_class(x509.KeyUsage)
    except x509.ExtensionNotFound:
        pass
    else:
        if not usage.value.key_cert_sign:
            raise ValueError("The CA certificate does not permit certificate signing.")
    not_before, not_after = _certificate_validity(certificate)
    now = datetime.now(timezone.utc)
    if not (
        datetime.fromisoformat(not_before).replace(tzinfo=timezone.utc)
        <= now
        <= datetime.fromisoformat(not_after).replace(tzinfo=timezone.utc)
    ):
        raise ValueError("The CA certificate is expired or not yet valid.")
    return ServerCertificate(
        origin=origin,
        pem=certificate.public_bytes(serialization.Encoding.PEM),
        fingerprint=certificate.fingerprint(hashes.SHA256()).hex().upper(),
        subject=_certificate_name(certificate.subject),
        issuer=_certificate_name(certificate.issuer),
        sans=[],
        not_before=not_before,
        not_after=not_after,
        self_signed=_is_self_signed(certificate),
        trust_type="ca",
    )


def save_managed_certificate(certificate: ServerCertificate) -> Path:
    """Persist a server certificate and metadata in the managed trust directory."""
    trust_directory = _get_trust_directory(create=True)
    stem = _get_trust_stem(certificate.origin)
    pem_path = trust_directory / f"{stem}.pem"
    metadata_path = pem_path.with_suffix(".json")
    metadata = certificate.to_dict()

    temporary_pem = pem_path.with_suffix(".pem.tmp")
    temporary_metadata = metadata_path.with_suffix(".json.tmp")
    try:
        temporary_pem.write_bytes(certificate.pem)
        temporary_metadata.write_text(json.dumps(metadata, indent=2), encoding="utf-8")
        temporary_pem.chmod(0o600)
        temporary_metadata.chmod(0o600)
        temporary_pem.replace(pem_path)
        temporary_metadata.replace(metadata_path)
    except OSError:
        for temporary_path in (temporary_pem, temporary_metadata):
            try:
                temporary_path.unlink()
            except OSError:
                pass
        raise
    return pem_path


def get_managed_trust_records() -> List[Dict[str, Any]]:
    """Return metadata for all managed server certificates."""
    records: List[Dict[str, Any]] = []
    for metadata_path in sorted(_get_trust_directory().glob("*.json")):
        try:
            metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(metadata, dict) and isinstance(metadata.get("origin"), str):
            metadata.setdefault("trust-type", "leaf")
            records.append(metadata)
    return records


def remove_managed_trust(api_url: str) -> bool:
    """Remove the managed certificate trust entry for a server URL."""
    origin = get_ssl_server_origin(api_url)
    pem_path = _get_trust_directory() / f"{_get_trust_stem(origin)}.pem"
    metadata_path = pem_path.with_suffix(".json")
    removed = False
    for path in (pem_path, metadata_path):
        try:
            path.unlink()
            removed = True
        except FileNotFoundError:
            pass
    return removed


def inject_os_trust() -> None:
    """Inject system certificate store into requests via truststore.

    Steps:
      1. Respect SLCLI_DISABLE_OS_TRUST.
      2. Import truststore and call inject_into_requests().
      3. On failure: if SLCLI_FORCE_OS_TRUST set, re-raise; else log and fall back.

    Silence on success keeps CLI output clean.
    """
    global OS_TRUST_INJECTED, OS_TRUST_REASON
    force = os.environ.get("SLCLI_FORCE_OS_TRUST") == "1"
    if os.environ.get("SLCLI_DISABLE_OS_TRUST") == "1":
        OS_TRUST_INJECTED = False
        OS_TRUST_REASON = "disabled-env"
        return
    try:
        # Attempt OS trust injection using available truststore entry points.
        # Multiple variants are tried in order; exceptions are handled per force/fallback rules.
        import truststore  # type: ignore

        # Attempt known injection entry points in preferred order.
        candidates = [
            ("inject_into_requests", "requests"),  # modern direct requests patch
            ("inject_into_ssl", "ssl"),  # base SSL context patch
            ("inject_into_urllib3", "urllib3"),  # older fallback (affects requests indirectly)
        ]
        injected_variant = None
        injection_errors = (RuntimeError, OSError, ssl.SSLError, ValueError)
        for attr_name, label in candidates:
            if hasattr(truststore, attr_name):
                try:
                    getattr(truststore, attr_name)()  # type: ignore[misc]
                    injected_variant = label
                    break
                except injection_errors:  # pragma: no cover - try next variant
                    if force:
                        # Respect force mode: propagate the first injection failure
                        raise
                    continue
        if injected_variant is None:
            raise AttributeError(
                "No compatible injection function on truststore module (expected one of: "
                + ", ".join(name for name, _ in candidates)
                + ")"
            )
        OS_TRUST_INJECTED = True
        OS_TRUST_REASON = f"injected:{injected_variant}"
    except ImportError as exc:
        if force:
            raise
        sys.stderr.write(
            f"[slcli] Info: system trust store injection skipped: {exc.__class__.__name__}: {exc}.\n"
        )
        if os.environ.get("SLCLI_DEBUG_OS_TRUST") == "1":
            traceback.print_exc()
        OS_TRUST_INJECTED = False
        OS_TRUST_REASON = f"error:{exc.__class__.__name__}"
    except (AttributeError, RuntimeError, OSError, ssl.SSLError, ValueError) as exc:
        if force:
            raise
        sys.stderr.write(
            f"[slcli] Info: system trust store injection skipped: {exc.__class__.__name__}: {exc}.\n"
        )
        if os.environ.get("SLCLI_DEBUG_OS_TRUST") == "1":
            traceback.print_exc()
        OS_TRUST_INJECTED = False
        OS_TRUST_REASON = f"error:{exc.__class__.__name__}"
