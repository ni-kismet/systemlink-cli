"""Isolated persistence for a test-minion identity and master fingerprint."""

from __future__ import annotations

import hashlib
import json
import os
import stat
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Sequence, Tuple, Union
from urllib.parse import urlsplit, urlunsplit

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
HTTP_MASTER_FILE_NAME = "http_master.json"
HTTP_CA_BUNDLE_RELATIVE_PATH = Path("http-client") / "http-client.cer"
ASSET_IDENTIFICATION_FIELDS = (
    "model_name",
    "model_number",
    "vendor_name",
    "vendor_number",
    "serial_number",
)
_WINDOWS_ACL_SCRIPT = """$ErrorActionPreference = 'Stop'
$statePath = $env:SLCLI_MANAGED_CLIENT_STATE_PATH
try {
    $identity = [System.Security.Principal.WindowsIdentity]::GetCurrent().User
    $acl = [System.Security.AccessControl.DirectorySecurity]::new()
    $acl.SetAccessRuleProtection($true, $false)
    $accessRule = [System.Security.AccessControl.FileSystemAccessRule]::new(
        $identity,
        [System.Security.AccessControl.FileSystemRights]::FullControl,
        [System.Security.AccessControl.AccessControlType]::Allow
    )
    $acl.AddAccessRule($accessRule)
    [System.IO.Directory]::SetAccessControl($statePath, $acl)
} catch {
    [Console]::Error.WriteLine('Unable to set managed-client state ACL.')
    exit 1
}

"""


def _windows_system_command(executable: str) -> str:
    """Return an absolute path to a Windows System32 executable."""
    system_root = os.environ.get("SystemRoot")
    if not system_root:
        raise StateError("Unable to resolve the Windows system directory.")
    if not os.path.isabs(system_root):
        raise StateError("Unable to resolve the Windows system directory.")
    return os.path.join(system_root, "System32", executable)


def _windows_powershell_environment() -> Dict[str, str]:
    """Return an environment with the Windows PowerShell 5.1 module path."""
    system_root = os.environ.get("SystemRoot")
    if not system_root or not os.path.isabs(system_root):
        raise StateError("Unable to resolve the Windows system directory.")
    environment = {
        name: value for name, value in os.environ.items() if name.casefold() != "psmodulepath"
    }
    environment["PSModulePath"] = os.path.join(
        system_root, "System32", "WindowsPowerShell", "v1.0", "Modules"
    )
    return environment


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
        self._http_master_path = self.state_dir / HTTP_MASTER_FILE_NAME
        self._http_ca_bundle_path = self.state_dir / HTTP_CA_BUNDLE_RELATIVE_PATH

    def ensure_directory(self) -> None:
        """Create the state directory with owner-only permissions where supported."""
        try:
            self.state_dir.mkdir(parents=True, exist_ok=True)
            self._restrict_permissions(self.state_dir, STATE_DIRECTORY_MODE)
        except (OSError, StateError) as error:
            raise StateError("Unable to create the isolated minion state directory.") from error

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

    def get_blackout_state(self) -> bool:
        """Return the locally persisted Salt blackout state."""
        value = self._read_metadata().get("blackout", False)
        if not isinstance(value, bool):
            raise StateError("The stored blackout state must be a boolean.")
        return value

    def record_blackout_state(self, blackout: bool) -> None:
        """Persist the Salt blackout state in the isolated metadata file."""
        if not isinstance(blackout, bool):
            raise StateError("The blackout state must be a boolean.")
        self.ensure_directory()
        metadata = self._read_metadata()
        metadata["blackout"] = blackout
        self._write_metadata(metadata)

    def record_asset_records(self, assets: Sequence[Mapping[str, Any]]) -> None:
        """Persist asset records with their names and hardware identification."""
        if not assets:
            raise StateError("At least one asset record is required.")
        records: list[Dict[str, Any]] = []
        for asset in assets:
            name = asset.get("name")
            if not isinstance(name, str) or not name.strip():
                raise StateError("The asset names must be non-empty strings.")
            records.append(
                {
                    "name": name,
                    "identification": {
                        field: asset[field]
                        for field in ASSET_IDENTIFICATION_FIELDS
                        if field in asset
                    },
                }
            )

        self.ensure_directory()
        metadata = self._read_metadata()
        stored_records = metadata.get("asset_records", [])
        if not isinstance(stored_records, list) or any(
            not isinstance(record, Mapping) for record in stored_records
        ):
            stored_records = []
        for record in records:
            if record not in stored_records:
                stored_records.append(record)

        metadata["asset_records"] = stored_records
        self._write_metadata(metadata)

    def get_installed_packages(self) -> Dict[str, Dict[str, Any]]:
        """Return mock software inventory without inspecting the host."""
        packages = self._read_metadata().get("installed_packages", {})
        if not isinstance(packages, dict) or any(
            not isinstance(name, str)
            or not name.strip()
            or not isinstance(package, dict)
            or not {"version", "arch"}.issubset(package)
            or any(
                not isinstance(package[key], str) or not package[key].strip()
                for key in ("version", "arch")
            )
            for name, package in packages.items()
        ):
            raise StateError("The stored mock package inventory is invalid.")
        return packages

    def install_mock_packages(
        self, packages: Mapping[str, str], dry_run: bool = False
    ) -> Dict[str, Dict[str, str]]:
        """Persist mock versions and return Salt changes without installing software."""
        if not packages or any(
            not isinstance(name, str)
            or not name.strip()
            or not isinstance(version, str)
            or not version.strip()
            for name, version in packages.items()
        ):
            raise StateError("Mock package names and versions must be non-empty strings.")
        installed = self.get_installed_packages()
        changes: Dict[str, Dict[str, str]] = {}
        for name, version in packages.items():
            old_version = installed.get(name, {}).get("version", "")
            if old_version != version:
                changes[name] = {"old": old_version, "new": version}
                installed[name] = {"version": version, "arch": "all"}
        if changes and not dry_run:
            metadata = self._read_metadata()
            metadata["installed_packages"] = installed
            self._write_metadata(metadata)
        return changes

    def replace_mock_packages(
        self, packages: Mapping[str, Mapping[str, Any]], dry_run: bool = False
    ) -> Dict[str, Dict[str, str]]:
        """Atomically persist a resolved inventory without applying host transactions.

        Args:
            packages: Complete proposed mock inventory from the solver.
            dry_run: Whether to report changes without writing state.

        Returns:
            Version changes for all affected package names.
        """
        inventory = {name: dict(record) for name, record in packages.items()}
        if any(
            not isinstance(name, str)
            or not name.strip()
            or not {"version", "arch"}.issubset(record)
            or any(
                not isinstance(record[key], str) or not record[key].strip()
                for key in ("version", "arch")
            )
            for name, record in inventory.items()
        ):
            raise StateError("Resolved mock package inventory is invalid.")
        installed = self.get_installed_packages()
        changes = {}
        for name in installed.keys() | inventory.keys():
            old = installed.get(name, {}).get("version", "")
            new = inventory.get(name, {}).get("version", "")
            if old != new:
                changes[name] = {"old": old, "new": new}
        if not dry_run and installed != inventory:
            metadata = self._read_metadata()
            metadata["installed_packages"] = inventory
            self._write_metadata(metadata)
        return changes

    def remove_mock_packages(
        self, packages: Sequence[str], dry_run: bool = False
    ) -> Dict[str, Dict[str, str]]:
        """Remove named packages from mock state without uninstalling host software.

        Args:
            packages: Explicit package names to remove.
            dry_run: Whether to report changes without persisting them.

        Returns:
            Salt-style old and new versions for packages currently installed.
        """
        if (
            not packages
            or isinstance(packages, str)
            or any(not isinstance(name, str) or not name.strip() for name in packages)
            or not isinstance(dry_run, bool)
        ):
            raise StateError("Mock package removal requires non-empty package names.")
        installed = self.get_installed_packages()
        changes = {
            name: {"old": installed[name]["version"], "new": ""}
            for name in packages
            if name in installed
        }
        if changes and not dry_run:
            for name in changes:
                del installed[name]
            metadata = self._read_metadata()
            metadata["installed_packages"] = installed
            self._write_metadata(metadata)
        return changes

    def get_mock_repositories(self) -> Dict[str, Dict[str, Any]]:
        """Return isolated mock feed records without reading host configuration."""
        repositories = self._read_metadata().get("repositories", {})
        if not isinstance(repositories, dict) or any(
            not isinstance(name, str)
            or not name.strip()
            or not isinstance(repository, dict)
            or set(repository) != {"uri", "enabled", "trusted"}
            or not isinstance(repository["uri"], str)
            or not repository["uri"].strip()
            or not isinstance(repository["enabled"], bool)
            or not isinstance(repository["trusted"], bool)
            for name, repository in repositories.items()
        ):
            raise StateError("The stored mock repository inventory is invalid.")
        return repositories

    def modify_mock_repository(
        self, name: str, properties: Mapping[str, Any], allow_renaming: bool = False
    ) -> Dict[str, Dict[str, Any]]:
        """Create or update mock feed metadata without contacting a repository.

        Args:
            name: The requested repository name.
            properties: URI and enabled/trusted flags to merge into the record.
            allow_renaming: Whether an existing URI may be renamed to the requested name.

        Returns:
            The updated repository record keyed by its name.
        """
        if (
            not isinstance(name, str)
            or not name.strip()
            or not isinstance(allow_renaming, bool)
            or set(properties) - {"uri", "enabled", "trusted"}
        ):
            raise StateError("The mock repository arguments are invalid.")
        repositories = self.get_mock_repositories()
        repository = {
            "enabled": True,
            "trusted": False,
            **repositories.get(name, {}),
            **properties,
        }
        if (
            not isinstance(repository.get("uri"), str)
            or not repository["uri"].strip()
            or not isinstance(repository["enabled"], bool)
            or not isinstance(repository["trusted"], bool)
        ):
            raise StateError("A mock repository requires a URI and boolean flags.")
        if allow_renaming:
            repositories = {
                stored_name: stored_repository
                for stored_name, stored_repository in repositories.items()
                if stored_name == name or stored_repository["uri"] != repository["uri"]
            }
        repositories[name] = repository
        metadata = self._read_metadata()
        metadata["repositories"] = repositories
        self._write_metadata(metadata)
        return {name: repository}

    def remove_asset(self, identification: Mapping[str, Any]) -> bool:
        """Remove an identified asset record from isolated metadata."""
        if not isinstance(identification, Mapping) or any(
            field not in identification for field in ASSET_IDENTIFICATION_FIELDS
        ):
            raise StateError("The asset identification is incomplete.")

        metadata = self._read_metadata()
        stored_records = metadata.get("asset_records", [])
        if not isinstance(stored_records, list):
            stored_records = []
        matching_index = next(
            (
                index
                for index, record in enumerate(stored_records)
                if isinstance(record, Mapping)
                and isinstance(record.get("identification"), Mapping)
                and all(
                    record["identification"].get(field) == identification[field]
                    for field in ASSET_IDENTIFICATION_FIELDS
                )
            ),
            None,
        )

        if matching_index is None:
            return False

        stored_records.pop(matching_index)
        metadata["asset_records"] = stored_records
        self._write_metadata(metadata)
        return True

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

    def record_http_master(self, uri: str, api_key: str) -> None:
        """Persist the REST endpoint and API key delivered to this minion.

        The file is owner-only and lives in the isolated state directory, so the
        health publisher can authenticate without environment variables or a profile.
        """
        if not uri.strip() or not api_key.strip():
            raise StateError("The REST URI and API key are required.")
        self.ensure_directory()
        self._write_private_json(
            self._http_master_path,
            {"Uri": uri, "ApiKey": api_key},
            "REST connection state",
        )

    def record_http_master_from_pillar(
        self, pillar: Mapping[str, Any], master_host: str | None
    ) -> None:
        """Apply the ``http`` pillar the same way as the Salt ``http_credentials`` state.

        The URI host is replaced with the master host unless ``uriIsOverridden`` is set.
        Missing URI or key values remove any previously stored connection state.
        """
        http = pillar.get("http")
        if not isinstance(http, Mapping):
            http = {}
        uri = http.get("uri")
        api_key = http.get("api_key")
        if not uri or not api_key:
            self.clear_http_master()
            return
        if not http.get("uriIsOverridden") and master_host:
            components = urlsplit(str(uri))
            if components.hostname:
                netloc = components.netloc.replace(components.hostname, master_host)
                uri = urlunsplit(
                    (
                        components.scheme,
                        netloc,
                        components.path,
                        components.query,
                        components.fragment,
                    )
                )
        self.record_http_master(str(uri), str(api_key))
        self._record_http_ca_bundle(http.get("certificate"))

    def load_http_ca_bundle(self) -> Optional[str]:
        """Return the path to the delivered HTTP server certificate, or None."""
        path = self._http_ca_bundle_path
        return str(path) if path.is_file() else None

    def _record_http_ca_bundle(self, certificate: Any) -> None:
        """Store or remove the delivered HTTP server certificate used to verify TLS."""
        if not isinstance(certificate, str) or not certificate.strip():
            self._http_ca_bundle_path.unlink(missing_ok=True)
            return
        self.ensure_directory()
        self._http_ca_bundle_path.parent.mkdir(parents=True, exist_ok=True)
        self._http_ca_bundle_path.write_text(certificate, encoding="utf-8")

    def load_http_master(self) -> Optional[Tuple[str, str]]:
        """Return the stored ``(uri, api_key)`` pair, or None when none is stored."""
        if not self._http_master_path.exists():
            return None
        try:
            value = json.loads(self._http_master_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as error:
            raise StateError("The stored REST connection state is invalid.") from error
        uri = value.get("Uri") if isinstance(value, dict) else None
        api_key = value.get("ApiKey") if isinstance(value, dict) else None
        if (
            not isinstance(uri, str)
            or not uri.strip()
            or not isinstance(api_key, str)
            or not api_key.strip()
        ):
            raise StateError("The stored REST connection state is invalid.")
        return uri, api_key

    def clear_http_master(self) -> None:
        """Remove any stored REST connection state and delivered certificate."""
        try:
            self._http_master_path.unlink(missing_ok=True)
            self._http_ca_bundle_path.unlink(missing_ok=True)
        except OSError as error:
            raise StateError("Unable to remove the stored REST connection state.") from error

    @staticmethod
    def _restrict_permissions(path: Path, mode: int) -> None:
        """Restrict a state path to the current user on every supported OS."""
        if os.name == "nt":
            try:
                powershell = _windows_system_command(
                    os.path.join("WindowsPowerShell", "v1.0", "powershell.exe")
                )
                environment = _windows_powershell_environment()
                environment["SLCLI_MANAGED_CLIENT_STATE_PATH"] = os.fspath(path)
                subprocess.run(
                    [powershell, "-NoProfile", "-NonInteractive", "-Command", "-"],
                    check=True,
                    capture_output=True,
                    text=True,
                    input=_WINDOWS_ACL_SCRIPT,
                    env=environment,
                )
            except (OSError, StateError, subprocess.CalledProcessError) as error:
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
        self._write_private_json(self._metadata_path, metadata, "isolated minion metadata")

    def _write_private_json(self, path: Path, payload: Dict[str, Any], description: str) -> None:
        temporary_path: Path | None = None
        try:
            self.ensure_directory()
            with tempfile.NamedTemporaryFile(
                mode="w",
                encoding="utf-8",
                dir=self.state_dir,
                prefix=f".{path.stem}-",
                suffix=".tmp",
                delete=False,
            ) as temporary_file:
                temporary_path = Path(temporary_file.name)
                temporary_file.write(json.dumps(payload, indent=2, sort_keys=True) + "\n")
                temporary_file.flush()
                os.fsync(temporary_file.fileno())
            self._restrict_permissions(temporary_path, STATE_FILE_MODE)
            os.replace(temporary_path, path)
            temporary_path = None
        except (OSError, StateError, TypeError) as error:
            raise StateError(f"Unable to write {description}.") from error
        finally:
            if temporary_path is not None:
                try:
                    temporary_path.unlink()
                except OSError:
                    pass
