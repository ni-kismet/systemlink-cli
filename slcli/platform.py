"""Platform detection and feature gating for SystemLink CLI.

This module provides utilities to detect and manage the target platform
(SystemLink Enterprise vs SystemLink Server) and gate features accordingly.
"""

import json
import os
import sys
from functools import lru_cache
from typing import Any, Dict

import click
import keyring
import requests

from .utils import ExitCodes, get_ssl_verify


# Platform identifiers
PLATFORM_SLE = "SLE"  # SystemLink Enterprise (cloud)
PLATFORM_SLS = "SLS"  # SystemLink Server (on-premises)
PLATFORM_UNKNOWN = "unknown"

# Feature matrix: maps features to platform availability
PLATFORM_FEATURES: Dict[str, Dict[str, bool]] = {
    PLATFORM_SLE: {
        "service_accounts": True,
        "workorder_service": True,
        "dynamic_form_fields": True,
        "function_execution": True,
        "templates": True,
        "workflows": True,
        "webapp": True,
    },
    PLATFORM_SLS: {
        "service_accounts": False,
        "workorder_service": False,
        "dynamic_form_fields": False,
        "function_execution": False,
        "templates": False,  # Uses workorder service
        "workflows": False,  # Uses workorder service
        "webapp": True,  # May be available
    },
}

# Human-readable feature names for error messages
FEATURE_DISPLAY_NAMES: Dict[str, str] = {
    "service_accounts": "Service Accounts",
    "workorder_service": "Work Order Service",
    "dynamic_form_fields": "Dynamic Form Fields",
    "function_execution": "Function Execution",
    "templates": "Test Plan Templates",
    "workflows": "Workflows",
    "webapp": "Web Applications",
}


def _get_keyring_config() -> Dict[str, Any]:
    """Attempt to read a single JSON config entry from keyring.

    Returns:
        Dictionary with config values or empty dict on failure.
    """
    try:
        cfg_text = keyring.get_password("systemlink-cli", "SYSTEMLINK_CONFIG")
        if not cfg_text:
            return {}
        parsed = json.loads(cfg_text)
        if isinstance(parsed, dict):
            return parsed
    except Exception:  # noqa: BLE001
        # Intentionally catch all exceptions: keyring access can fail for many reasons
        # (missing backend, corrupted data, permission issues, JSON decode errors).
        # None of these should prevent CLI operation - we just return empty config.
        pass
    return {}


def detect_platform(api_url: str, api_key: str) -> str:
    """Detect the SystemLink platform type by probing endpoints.

    Detection strategy:
    1. Try SLE-only endpoint (/niworkorder/v1/query-testplan-templates)
       - If accessible -> SLE
    2. Check URL pattern (*.systemlink.io, *.lifecyclesolutions.ni.com)
       - If matches -> SLE
    3. Default to SLS for on-premises/custom URLs

    Args:
        api_url: The SystemLink API base URL
        api_key: The API key for authentication

    Returns:
        Platform identifier (PLATFORM_SLE, PLATFORM_SLS, or PLATFORM_UNKNOWN)
    """
    headers = {
        "x-ni-api-key": api_key,
        "Content-Type": "application/json",
        "User-Agent": "SystemLink-CLI/1.0 (cross-platform)",
    }
    ssl_verify = get_ssl_verify()

    # Strategy 1: Probe SLE-only endpoint (Work Order service)
    try:
        # This endpoint only exists on SLE
        workorder_url = f"{api_url}/niworkorder/v1/query-testplan-templates"
        resp = requests.post(
            workorder_url,
            headers=headers,
            json={"take": 1},
            verify=ssl_verify,
            timeout=10,
        )
        # If we get a 200 or 400 (bad request but endpoint exists), it's SLE
        if resp.status_code in (200, 400):
            return PLATFORM_SLE
        # 404 means endpoint doesn't exist -> likely SLS
        if resp.status_code == 404:
            return PLATFORM_SLS
    except requests.RequestException:
        # Connection error - continue with other detection methods
        pass

    # Strategy 2: URL pattern matching
    # SLE (cloud and hosted) service has specific URL patterns
    api_url_lower = api_url.lower()
    sle_patterns = [
        "api.systemlink.io",  # SLE production
        "-api.lifecyclesolutions.ni.com",  # SLE dev/demo with -api suffix
        "dev-api.lifecyclesolutions",
        "demo-api.lifecyclesolutions",
    ]
    for pattern in sle_patterns:
        if pattern in api_url_lower:
            return PLATFORM_SLE

    # Strategy 3: Default to SLS for on-premises deployments
    # This includes on-prem servers that may use *.systemlink.io subdomains
    return PLATFORM_SLS


def _detect_platform_from_url(api_url: str) -> str:
    """Detect platform from URL pattern without making network requests.

    This is a lightweight detection for use when environment variables
    are set and we need quick platform detection.

    SLE (SystemLink Enterprise Cloud) URLs typically contain:
    - api.systemlink.io (production)
    - dev-api.lifecyclesolutions.ni.com (development)
    - demo-api.lifecyclesolutions.ni.com (demo)

    On-premises SystemLink Server (SLS) instances may use custom domains
    or even *.systemlink.io subdomains (like base.systemlink.io).

    Args:
        api_url: The SystemLink API base URL

    Returns:
        Platform identifier: PLATFORM_SLE or PLATFORM_SLS.
        Note: This function never returns PLATFORM_UNKNOWN - it defaults to SLS.
    """
    api_url_lower = api_url.lower()

    # SLE cloud service has specific URL patterns
    sle_patterns = [
        "api.systemlink.io",  # SLE production
        "-api.lifecyclesolutions.ni.com",  # SLE dev/demo with -api suffix
        "dev-api.lifecyclesolutions",
        "demo-api.lifecyclesolutions",
    ]
    for pattern in sle_patterns:
        if pattern in api_url_lower:
            return PLATFORM_SLE

    # Default to SLS for on-premises/custom URLs
    # This includes on-prem servers that may use *.systemlink.io subdomains
    return PLATFORM_SLS


@lru_cache(maxsize=1)
def get_platform() -> str:
    """Get the current platform from stored configuration or environment.

    Detection priority:
    1. SYSTEMLINK_PLATFORM environment variable (explicit, most reliable)
    2. Stored platform from keyring config (set during login via endpoint probing)
    3. URL pattern matching (fallback, less reliable)
    4. Return PLATFORM_UNKNOWN if all methods fail

    Note: Results are cached for performance. Use clear_platform_cache() to reset.

    Returns:
        Platform identifier (PLATFORM_SLE, PLATFORM_SLS, or PLATFORM_UNKNOWN)
    """
    # Priority 1: Explicit platform environment variable (most reliable)
    # This allows users/tests to explicitly specify the platform
    env_platform = os.environ.get("SYSTEMLINK_PLATFORM", "").upper()
    if env_platform in (PLATFORM_SLE, PLATFORM_SLS):
        return env_platform

    # Priority 2: Stored platform from keyring config (set during login)
    # This was detected via endpoint probing, which is reliable
    cfg = _get_keyring_config()
    if cfg:
        platform = cfg.get("platform", "")
        if platform in (PLATFORM_SLE, PLATFORM_SLS):
            return platform

    # Priority 3: URL pattern matching (fallback, less reliable)
    # Only used when env vars are set but no explicit platform is provided
    env_url = os.environ.get("SYSTEMLINK_API_URL")
    if env_url:
        return _detect_platform_from_url(env_url)

    return PLATFORM_UNKNOWN


def clear_platform_cache() -> None:
    """Clear the cached platform result.

    Call this when the platform configuration changes (e.g., after login/logout)
    to ensure the next get_platform() call re-detects the platform.
    """
    get_platform.cache_clear()


def has_feature(feature_name: str) -> bool:
    """Check if a feature is available on the current platform.

    Args:
        feature_name: The feature to check (e.g., 'dynamic_form_fields')

    Returns:
        True if the feature is available, False otherwise.
        Returns True if platform is unknown (graceful degradation).
    """
    platform = get_platform()

    # If platform is unknown, allow all features (fail later if actually unavailable)
    if platform == PLATFORM_UNKNOWN:
        return True

    platform_features = PLATFORM_FEATURES.get(platform, {})
    return platform_features.get(feature_name, True)  # Default to available


def require_feature(feature_name: str) -> None:
    """Require a feature to be available, exit gracefully if not.

    This function should be called at the start of commands that require
    platform-specific features. It will display a helpful error message
    and exit if the feature is not available.

    Args:
        feature_name: The feature to require (e.g., 'dynamic_form_fields')
    """
    if has_feature(feature_name):
        return

    platform = get_platform()
    feature_display = FEATURE_DISPLAY_NAMES.get(feature_name, feature_name)
    platform_display = "SystemLink Server" if platform == PLATFORM_SLS else platform

    click.echo(
        f"✗ Error: {feature_display} is not available on {platform_display}.",
        err=True,
    )
    click.echo(
        "  This feature requires SystemLink Enterprise (SLE).",
        err=True,
    )
    sys.exit(ExitCodes.INVALID_INPUT)


def get_platform_info() -> Dict[str, Any]:
    """Get detailed information about the current platform configuration.

    Returns:
        Dictionary with platform info including URL, platform type, and features.
    """
    cfg = _get_keyring_config()

    info: Dict[str, Any] = {
        "api_url": cfg.get("api_url", "Not configured"),
        "web_url": cfg.get("web_url", "Not configured"),
        "platform": cfg.get("platform", PLATFORM_UNKNOWN),
        "platform_display": _get_platform_display_name(cfg.get("platform", PLATFORM_UNKNOWN)),
        "logged_in": bool(cfg.get("api_key")),
    }

    # Add feature availability if platform is known
    platform = cfg.get("platform", PLATFORM_UNKNOWN)
    if platform in PLATFORM_FEATURES:
        info["features"] = {}
        for feature, available in PLATFORM_FEATURES[platform].items():
            display_name = FEATURE_DISPLAY_NAMES.get(feature, feature)
            info["features"][display_name] = available

    return info


def _get_platform_display_name(platform: str) -> str:
    """Get human-readable platform name.

    Args:
        platform: Platform identifier

    Returns:
        Human-readable platform name
    """
    names = {
        PLATFORM_SLE: "SystemLink Enterprise",
        PLATFORM_SLS: "SystemLink Server",
        PLATFORM_UNKNOWN: "Unknown",
    }
    return names.get(platform, platform)
