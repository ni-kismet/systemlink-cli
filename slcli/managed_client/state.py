"""Isolated persistence for a test-minion identity and master fingerprint."""

from __future__ import annotations

import getpass
import hashlib
import json
import os
import stat
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Union

from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey

from .crypto import (
    RsaKeyPair,
    generate_rsa_key_pair,
    load_rsa_private_key,
    public_key_fingerprint,
    serialize_private_key,
    serialize_public_key,
)
from .models import MasterIdentityChangedError, StateError

STATE_DIRECTORY_MODE = stat.S_IRWXU
STATE_FILE_MODE = stat.S_IRUSR | stat.S_IWUSR


@dataclass(frozen=True)
class MinionIdentity:
    """A stable minion ID and its private key loaded from isolated state."""

    minion_id: str
    key_pair: RsaKeyPair = field(repr=False)

    @property
    def public_key(self) -> RSAPublicKey:
        """Return the public key used during Salt authentication."""
        return self.key_pair.public_key


class StateStore:
    """Persist only the identity and protocol metadata for one test minion."""

    def __init__(self, state_dir: Path) -> None:
        """Initialize a store rooted at an explicit directory."""
        self.state_dir = Path(state_dir)
        self._metadata_path = self.state_dir / "metadata.json"
        self._private_key_path = self.state_dir / "minion-key.pem"
        self._public_key_path = self.state_dir / "minion-key.pub.pem"

    def ensure_directory(self) -> None:
        """Create the state directory with owner-only permissions where supported."""
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self._restrict_permissions(self.state_dir, STATE_DIRECTORY_MODE)

    def load_or_create_identity(self, minion_id: str) -> MinionIdentity:
        """Load a stable identity or create it on the first run."""
        if not minion_id.strip():
            raise StateError("The minion ID is required for state initialization.")
        self.ensure_directory()
        metadata = self._read_metadata()
        stored_id = metadata.get("minion_id")
        if stored_id is not None and stored_id != minion_id:
            raise StateError("The state directory belongs to a different minion ID.")

        if self._private_key_path.exists():
            key_pair = self._load_existing_key()
        else:
            if stored_id is not None or self._public_key_path.exists():
                raise StateError("The minion identity state is incomplete.")
            key_pair = generate_rsa_key_pair()
            self._write_key_files(key_pair)

        if stored_id is None:
            metadata["minion_id"] = minion_id
            metadata["public_key_fingerprint"] = public_key_fingerprint(key_pair.public_key)
            self._write_metadata(metadata)
        elif metadata.get("public_key_fingerprint") != public_key_fingerprint(key_pair.public_key):
            raise StateError("The stored minion public-key fingerprint does not match.")
        return MinionIdentity(minion_id=minion_id, key_pair=key_pair)

    def record_master_identity(self, master_identity: Union[str, bytes]) -> str:
        """Record a master fingerprint and reject unexpected identity changes."""
        self.ensure_directory()
        identity_bytes = (
            master_identity.encode("utf-8") if isinstance(master_identity, str) else master_identity
        )
        fingerprint = hashlib.sha256(identity_bytes).hexdigest()
        metadata = self._read_metadata()
        existing = metadata.get("master_identity_fingerprint")
        if existing is not None and existing != fingerprint:
            raise MasterIdentityChangedError(
                "The Salt master identity changed; reset isolated state explicitly."
            )
        metadata["master_identity_fingerprint"] = fingerprint
        self._write_metadata(metadata)
        return fingerprint

    def reset(self) -> None:
        """Delete only this minion's identity and metadata files."""
        for path in (self._metadata_path, self._private_key_path, self._public_key_path):
            try:
                path.unlink()
            except FileNotFoundError:
                pass
            except OSError as error:
                raise StateError("Unable to reset isolated minion state.") from error

    def _load_existing_key(self) -> RsaKeyPair:
        try:
            self._restrict_permissions(self._private_key_path, STATE_FILE_MODE)
            return load_rsa_private_key(self._private_key_path.read_bytes())
        except (OSError, StateError) as error:
            raise StateError("Unable to read the isolated minion key.") from error

    def _write_key_files(self, key_pair: RsaKeyPair) -> None:
        try:
            self._private_key_path.write_bytes(serialize_private_key(key_pair.private_key))
            self._public_key_path.write_bytes(serialize_public_key(key_pair.public_key))
            self._restrict_permissions(self._private_key_path, STATE_FILE_MODE)
            self._restrict_permissions(self._public_key_path, STATE_FILE_MODE)
        except OSError as error:
            raise StateError("Unable to write isolated minion identity state.") from error

    @staticmethod
    def _restrict_permissions(path: Path, mode: int) -> None:
        """Restrict a state path to the current user on every supported OS."""
        if os.name == "nt":
            try:
                username = getpass.getuser()
                subprocess.run(
                    [
                        "icacls",
                        str(path),
                        "/reset",
                        "/inheritance:r",
                        "/grant:r",
                        f"{username}:F",
                    ],
                    check=True,
                    capture_output=True,
                    text=True,
                )
            except (KeyError, OSError, subprocess.CalledProcessError) as error:
                raise StateError(f"Unable to protect isolated state at {path}.") from error
            return

        try:
            path.chmod(mode)
        except OSError as error:
            raise StateError(f"Unable to protect isolated state at {path}.") from error

    def _read_metadata(self) -> Dict[str, Any]:
        if not self._metadata_path.exists():
            return {}
        try:
            value = json.loads(self._metadata_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise StateError("The isolated minion metadata is invalid.") from error
        if not isinstance(value, dict):
            raise StateError("The isolated minion metadata must be an object.")
        return value

    def _write_metadata(self, metadata: Dict[str, Any]) -> None:
        try:
            self._metadata_path.write_text(
                json.dumps(metadata, indent=2, sort_keys=True) + "\n", encoding="utf-8"
            )
            self._restrict_permissions(self._metadata_path, STATE_FILE_MODE)
        except OSError as error:
            raise StateError("Unable to write isolated minion metadata.") from error
