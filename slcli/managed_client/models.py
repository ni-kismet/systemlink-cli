"""Typed configuration, lifecycle state, and errors for a test minion."""

from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, Optional


class ManagedClientError(Exception):
    """Base exception for managed-client failures."""


class ConfigurationError(ManagedClientError):
    """Raised when managed-client configuration is invalid."""


class StateError(ManagedClientError):
    """Raised when isolated minion state cannot be loaded safely."""


class MasterIdentityChangedError(StateError):
    """Raised when a persisted Salt master identity changes unexpectedly."""


class ProtocolError(ManagedClientError):
    """Raised when a protocol frame is malformed or unsupported."""


class UnsupportedCryptoError(ManagedClientError):
    """Raised when a required cryptographic operation has no approved adapter."""


class ReconnectLimitExceededError(ManagedClientError):
    """Raised when a minion exceeds its configured reconnect attempts."""


class TransportError(ManagedClientError):
    """Raised when a Salt socket cannot send or receive a frame."""


class LifecycleTimeoutError(ManagedClientError):
    """Raised when a minion does not reach a requested phase in time."""


class MinionPhase(str, Enum):
    """Observable phases of the managed-client lifecycle."""

    INITIALIZING = "INITIALIZING"
    AUTHENTICATING = "AUTHENTICATING"
    PENDING_APPROVAL = "PENDING_APPROVAL"
    APPROVED_RECONNECTING = "APPROVED_RECONNECTING"
    CONNECTING_PUBLISH = "CONNECTING_PUBLISH"
    CONNECTED = "CONNECTED"
    RUNNING_JOB = "RUNNING_JOB"
    RECONNECTING = "RECONNECTING"
    STOPPING = "STOPPING"
    FAILED = "FAILED"


@dataclass(frozen=True)
class MinionConfiguration:
    """Configuration that contains no REST credentials."""

    master: str
    minion_id: str
    state_dir: Path
    protocol_version: int = 3
    request_timeout: float = 10.0
    reconnect_interval: float = 1.0
    max_reconnect_attempts: int = 5
    request_port: int = 4506
    api_key: Optional[str] = None

    def __post_init__(self) -> None:
        """Validate configuration before any state or socket is opened."""
        if not self.master.strip():
            raise ConfigurationError("The Salt master endpoint is required.")
        if not self.minion_id.strip():
            raise ConfigurationError("The minion ID is required.")
        if self.protocol_version != 3:
            raise ConfigurationError("Only protocol version 3 is supported.")
        if self.request_timeout <= 0:
            raise ConfigurationError("The request timeout must be positive.")
        if self.reconnect_interval <= 0:
            raise ConfigurationError("The reconnect interval must be positive.")
        if self.max_reconnect_attempts < 1:
            raise ConfigurationError("The maximum reconnect attempts must be positive.")
        if not 1 <= self.request_port <= 65535:
            raise ConfigurationError("The request port must be between 1 and 65535.")


@dataclass(frozen=True)
class MinionEvent:
    """Safe lifecycle event data suitable for structured logging."""

    phase: MinionPhase
    message: str
    retry_count: int = 0
    endpoint: Optional[str] = None
    details: Dict[str, str] = field(default_factory=dict)
