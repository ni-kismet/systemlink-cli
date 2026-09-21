"""Deterministic loopback Salt fixture for managed-client tests."""

from __future__ import annotations

import base64
import hashlib
import queue
import socket
import threading
from collections.abc import Mapping, MutableMapping
from typing import Any

from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey

from slcli.managed_client.crypto import (
    encrypt_aes_192_cbc_hmac,
    encrypt_rsa_oaep,
    generate_rsa_key_pair,
    rsa_x931_decrypt,
    rsa_x931_sign,
    sign_rsa_pkcs1_sha1,
    serialize_public_key,
)
from slcli.managed_client.protocol import SaltMessage, decrypt_message_load, pack_inner_load
from slcli.managed_client.transport import SaltChannel


class FixtureSaltServer:
    """Drive one pending-to-connected v3 lifecycle over local TCP sockets."""

    def __init__(self, *, reconnect: bool = False) -> None:
        """Bind request and publish listeners on loopback."""
        self._request_listener = self._bind_listener()
        self._publish_listener = self._bind_listener()
        self._reconnect = reconnect
        self.request_port = self._request_listener.getsockname()[1]
        self.publish_port = self._publish_listener.getsockname()[1]
        self.registration_ready = threading.Event()
        self.pending = threading.Event()
        self.approve = threading.Event()
        self.release_job = threading.Event()
        self.reconnected = threading.Event()
        self._shutdown = threading.Event()
        self.public_keys: list[str] = []
        self.projected_grains: dict[str, Any] = {}
        self.projected_grains_history: list[dict[str, Any]] = []
        self._minion_public_key: RSAPublicKey | None = None
        self._minion_token = b"fixture-minion-token"
        self._token_issued = False
        self.result: queue.Queue[MutableMapping[str, Any]] = queue.Queue()
        self.errors: queue.Queue[Exception] = queue.Queue()
        self._thread = threading.Thread(target=self._run, daemon=True)

    @staticmethod
    def _bind_listener() -> socket.socket:
        """Bind one reusable loopback listener."""
        listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        listener.bind(("127.0.0.1", 0))
        listener.listen(1)
        return listener

    def start(self) -> None:
        """Start accepting the fixture lifecycle."""
        self._thread.start()

    def close(self) -> None:
        """Close listeners and join the fixture thread."""
        self._shutdown.set()
        self._request_listener.close()
        self._publish_listener.close()
        self._thread.join(timeout=5)
        if not self.errors.empty():
            raise self.errors.get()

    def _run(self) -> None:
        """Serve pending auth, accepted auth, registration, and one job."""
        request_channel: SaltChannel | None = None
        publish_channel: SaltChannel | None = None
        try:
            request_channel = self._accept_auth()
            request_channel.close()
            request_channel = self._accept_auth()
            publish_socket, _ = self._publish_listener.accept()
            publish_channel = SaltChannel(publish_socket)
            registration = decrypt_message_load(publish_channel.receive(), self._shared_secret)
            assert registration["id"] == self._minion_id
            assert self._minion_public_key is not None
            assert isinstance(registration["tok"], bytes)
            assert rsa_x931_decrypt(registration["tok"], self._minion_public_key) == b"salt"
            self._receive_grains(request_channel)
            self.registration_ready.set()
            assert self.release_job.wait(5)
            self._send_job(publish_channel, "fixture-jid-001")
            returned = decrypt_message_load(request_channel.receive(), self._shared_secret)
            assert self._minion_public_key is not None
            assert isinstance(returned["tok"], bytes)
            assert rsa_x931_decrypt(returned["tok"], self._minion_public_key) == b"salt"
            self.result.put(returned)
            if self._reconnect:
                publish_channel.close()
                publish_channel = None
                request_channel.close()
                request_channel = None
                request_channel = self._accept_auth()
                publish_socket, _ = self._publish_listener.accept()
                publish_channel = SaltChannel(publish_socket)
                registration = decrypt_message_load(publish_channel.receive(), self._shared_secret)
                assert registration["id"] == self._minion_id
                assert self._minion_public_key is not None
                assert isinstance(registration["tok"], bytes)
                assert rsa_x931_decrypt(registration["tok"], self._minion_public_key) == b"salt"
                self._receive_grains(request_channel)
                self.reconnected.set()
                self._send_job(publish_channel, "fixture-jid-002")
                returned = decrypt_message_load(request_channel.receive(), self._shared_secret)
                assert isinstance(returned["tok"], bytes)
                assert rsa_x931_decrypt(returned["tok"], self._minion_public_key) == b"salt"
                self.result.put(returned)
            self._shutdown.wait(5)
        except Exception as error:
            self.errors.put(error)
        finally:
            if request_channel is not None:
                request_channel.close()
            if publish_channel is not None:
                publish_channel.close()

    def _receive_grains(self, request_channel: SaltChannel) -> None:
        """Validate and retain the grains projected by an authenticated request."""
        request = decrypt_message_load(request_channel.receive(), self._shared_secret)
        assert request["cmd"] == "_pillar"
        assert request["id"] == self._minion_id
        assert self._minion_public_key is not None
        assert isinstance(request["tok"], bytes)
        assert rsa_x931_decrypt(request["tok"], self._minion_public_key) == b"salt"
        assert isinstance(request["nonce"], str)
        grains = request["grains"]
        assert isinstance(grains, Mapping)
        self.projected_grains = dict(grains)
        self.projected_grains_history.append(self.projected_grains.copy())

    def _send_job(self, publish_channel: SaltChannel, jid: str) -> None:
        """Send the observed multi-function refresh job."""
        job = {
            "jid": jid,
            "tgt": [self._minion_id],
            "fun": [
                "saltutil.refresh_pillar",
                "nisysmgmt.state_apply",
                "pkg.list_repos",
                "nisysmgmt.grains_items",
                "pkg.info_installed",
            ],
            "arg": [
                [],
                [],
                [],
                [],
                [{"__kwarg__": True, "attr": ["version", "arch"]}],
            ],
            "kwarg": {},
            "nonce": self._nonce,
        }
        encrypted = encrypt_aes_192_cbc_hmac(pack_inner_load(job), self._shared_secret).to_bytes()
        publish_channel.send(
            SaltMessage(
                body={"enc": "aes", "load": encrypted},
                head={"mid": 1},
            )
        )

    def _accept_auth(self) -> SaltChannel:
        """Accept an auth request and send pending or accepted response."""
        connection, _ = self._request_listener.accept()
        channel = SaltChannel(connection)
        request = channel.receive()
        load = request.body["load"]
        assert isinstance(load, Mapping)
        self._minion_id = load["id"]
        self._nonce = load["nonce"]
        if self._token_issued:
            assert load.get("token") == self._minion_token
        else:
            assert "token" not in load
        public_key_value = load["pub"]
        assert isinstance(public_key_value, str)
        public_key = serialization.load_pem_public_key(public_key_value.encode("utf-8"))
        assert isinstance(public_key, RSAPublicKey)
        self._minion_public_key = public_key
        self.public_keys.append(public_key_value)
        if not hasattr(self, "_shared_secret"):
            self._shared_secret = bytes(range(56))
            channel.send(
                SaltMessage(
                    body={
                        "enc": "clear",
                        "version": 2,
                        "load": pack_inner_load({"ret": True, "nonce": self._nonce}),
                        "sig": b"fixture-load",
                    },
                    head={"mid": request.head["mid"]},
                )
            )
            self.pending.set()
            assert self.approve.wait(5)
            return channel

        if not hasattr(self, "_master_key"):
            self._master_key = generate_rsa_key_pair()
        master_public_key = serialize_public_key(self._master_key.public_key).decode("utf-8")
        accepted_load = {
            "pub_key": master_public_key,
            "publish_port": self.publish_port,
            "sig": rsa_x931_sign(
                hashlib.sha256(base64.b64encode(self._shared_secret)).hexdigest().encode("ascii"),
                self._master_key.private_key,
            ),
            "aes": encrypt_rsa_oaep(base64.b64encode(self._shared_secret), public_key),
            "nonce": self._nonce,
            "token": encrypt_rsa_oaep(self._minion_token, public_key),
        }
        self._token_issued = True
        raw_load = pack_inner_load(accepted_load)
        channel.send(
            SaltMessage(
                body={
                    "enc": "clear",
                    "version": 2,
                    "load": raw_load,
                    "sig": sign_rsa_pkcs1_sha1(raw_load, self._master_key.private_key),
                },
                head={"mid": request.head["mid"]},
            )
        )
        return channel
