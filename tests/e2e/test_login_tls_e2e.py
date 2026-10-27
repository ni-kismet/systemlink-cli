"""Local HTTPS login tests without external services or credential-store access.

These run the real CLI in subprocesses against a loopback self-signed server. They
need no SystemLink environment; they live under e2e only because they are slow.
"""

import ipaddress
import json
import os
import ssl
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from typing import Iterator, NamedTuple

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.x509.oid import NameOID

from slcli.utils import ExitCodes


class _ServiceHandler(BaseHTTPRequestHandler):
    """Return synthetic successful SystemLink service responses."""

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler interface
        """Respond to a service probe."""
        payload = json.dumps({"v1": {}, "version": "1"}).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler interface
        """Consume a query body and respond to a service probe."""
        self.rfile.read(int(self.headers.get("Content-Length", "0")))
        self.do_GET()

    def log_message(self, format: str, *args: object) -> None:
        """Suppress routine HTTP access logs."""
        pass


class _TlsServer(NamedTuple):
    """A running self-signed HTTPS server."""

    url: str
    fingerprint: str
    certificate_pem: bytes


@pytest.fixture
def self_signed_server(tmp_path: Path) -> Iterator[_TlsServer]:
    """Serve synthetic SystemLink endpoints over real self-signed TLS on loopback."""
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "localhost")])
    now = datetime.now(timezone.utc)
    certificate = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(minutes=1))
        .not_valid_after(now + timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName([x509.IPAddress(ipaddress.ip_address("127.0.0.1"))]),
            critical=False,
        )
        .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
        .sign(key, hashes.SHA256())
    )
    certificate_pem = certificate.public_bytes(serialization.Encoding.PEM)
    certificate_file = tmp_path / "certificate.pem"
    key_file = tmp_path / "key.pem"
    certificate_file.write_bytes(certificate_pem)
    key_file.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.PKCS8,
            serialization.NoEncryption(),
        )
    )
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.load_cert_chain(certificate_file, key_file)
    with ThreadingHTTPServer(("127.0.0.1", 0), _ServiceHandler) as server:
        server.socket = context.wrap_socket(server.socket, server_side=True)
        thread = Thread(target=server.serve_forever)
        thread.start()
        try:
            yield _TlsServer(
                f"https://127.0.0.1:{server.server_port}",
                certificate.fingerprint(hashes.SHA256()).hex().upper(),
                certificate_pem,
            )
        finally:
            server.shutdown()
            thread.join(timeout=10)
            assert not thread.is_alive(), "Local TLS server did not stop."


@pytest.mark.e2e
@pytest.mark.parametrize("command", [["login"], ["config", "add"]])
@pytest.mark.parametrize("trust_certificate", [False, True])
def test_login_self_signed_tls(
    command: list[str], trust_certificate: bool, self_signed_server: _TlsServer, tmp_path: Path
) -> None:
    """Reject untrusted TLS despite an insecure active profile, then opt out or trust."""
    server = self_signed_server
    config_dir = tmp_path / "config"
    config_dir.mkdir()
    config_file = config_dir / "config.json"
    old_profile = {"server": server.url, "web-url": server.url, "ssl-verify": False}
    config_file.write_text(
        json.dumps({"current-profile": "old", "profiles": {"old": old_profile}}),
        encoding="utf-8",
    )
    env = {name: value for name, value in os.environ.items() if not name.startswith("SLCLI_")}
    for name in ("REQUESTS_CA_BUNDLE", "SSL_CERT_FILE"):
        env.pop(name, None)
    env.update(SLCLI_CONFIG=str(config_file), PYTHONIOENCODING="utf-8", NO_PROXY="127.0.0.1")
    args = [
        sys.executable,
        "-m",
        "slcli",
        *command,
        "--profile",
        "new",
        "--url",
        server.url,
        "--web-url",
        server.url,
        "--api-key",
        "a" * 42,
        "--workspace",
        "",
        "--credential-store",
        "file",
    ]

    def run(*extra: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [*args, *extra],
            env=env,
            stdin=subprocess.DEVNULL,
            capture_output=True,
            encoding="utf-8",
            timeout=60,
            check=False,
        )

    def profiles() -> dict[str, dict[str, object]]:
        return json.loads(config_file.read_text(encoding="utf-8"))["profiles"]

    # A fingerprint mismatch is only reachable after real certificate verification fails,
    # so it proves the insecure active profile did not leak into this login.
    rejected = run("--trust-fingerprint", "0" * 64)
    assert rejected.returncode == ExitCodes.INVALID_INPUT, rejected.stdout + rejected.stderr
    assert "new" not in profiles()

    option = (
        ("--trust-fingerprint", server.fingerprint) if trust_certificate else ("--no-ssl-verify",)
    )
    accepted = run(*option)
    assert accepted.returncode == 0, accepted.stdout + accepted.stderr
    saved = profiles()
    assert saved["old"]["ssl-verify"] is False
    assert saved["new"].get("ssl-verify", True) is trust_certificate
    trusted = list((config_dir / "trust").glob("*.pem"))
    if trust_certificate:
        assert [path.read_bytes() for path in trusted] == [server.certificate_pem]
    else:
        assert trusted == []
