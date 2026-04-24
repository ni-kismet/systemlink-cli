"""Platform detection and feature gating for SystemLink CLI.

This module provides utilities to detect and manage the target platform
(SystemLink Enterprise vs SystemLink Server) and gate features accordingly.
"""

import json
import os
import sys
from functools import lru_cache
from typing import Any, Dict, List, Optional

import click
import keyring
import requests

from .utils import ExitCodes, get_ssl_verify

# Platform identifiers
PLATFORM_SLE = "SLE"  # SystemLink Enterprise (cloud)
PLATFORM_SLS = "SLS"  # SystemLink Server (on-premises)
PLATFORM_UNKNOWN = "unknown"
PLATFORM_UNREACHABLE = "unreachable"  # Server could not be contacted

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

FILE_SEARCH_PATH = "/nifile/v1/service-groups/Default/search-files"
FILE_QUERY_PATH = "/nifile/v1/service-groups/Default/query-files"
FILE_QUERY_LINQ_PATH = "/nifile/v1/service-groups/Default/query-files-linq"
SYSTEM_SEARCH_PATH = "/nisysmgmt/v1/materialized/search-systems"
SYSTEM_QUERY_PATH = "/nisysmgmt/v1/query-systems"


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

    Uses check_service_status to probe services and determine:
    - Platform type (SLE vs SLS)
    - Server reachability

    Args:
        api_url: The SystemLink API base URL
        api_key: The API key for authentication

    Returns:
        Platform identifier (PLATFORM_SLE, PLATFORM_SLS, PLATFORM_UNREACHABLE,
        or PLATFORM_UNKNOWN)
    """
    status = check_service_status(api_url, api_key)
    return status["platform"]


@lru_cache(maxsize=1)
def get_platform() -> str:
    """Get the current platform from stored configuration or environment.

    Detection priority:
    1. SYSTEMLINK_PLATFORM environment variable (explicit, most reliable)
    2. Stored platform from keyring config (set during login via endpoint probing)
    3. Return PLATFORM_UNKNOWN if no explicit or stored platform is available

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


# Services to probe during health checks.
# Each entry: (display_name, method, url_path)
SERVICE_CHECKS: List[List[str]] = [
    ["Auth", "GET", "/niauth/v1/policies"],
    ["Test Monitor", "GET", "/nitestmonitor/v2/results?take=0"],
    ["Asset Management", "POST", "/niapm/v1/query-assets"],
    ["Systems", "POST", SYSTEM_QUERY_PATH],
    ["Tag", "GET", "/nitag/v2/tags?take=0"],
    ["File", "POST", FILE_SEARCH_PATH],
    ["Notebook", "POST", "/ninotebook/v1/notebook/query"],
    ["Web Application", "POST", "/niapp/v1/webapps/query"],
    ["Dynamic Form Fields", "GET", "/nidynamicformfields/v1/groups"],
    ["Work Order", "POST", "/niworkorder/v1/query-testplan-templates"],
]


def get_file_query_capability(api_url: str, api_key: str) -> Dict[str, Any]:
    """Determine which file query endpoint is available for this server."""
    headers = {
        "x-ni-api-key": api_key,
        "Content-Type": "application/json",
        "User-Agent": "SystemLink-CLI/1.0 (cross-platform)",
    }
    ssl_verify = get_ssl_verify()

    try:
        search_resp = requests.post(
            f"{api_url}{FILE_SEARCH_PATH}",
            headers=headers,
            json={"take": 1},
            verify=ssl_verify,
            timeout=10,
        )
        if search_resp.status_code in (200, 400):
            return {
                "status": "ok",
                "file_query_endpoint": "search-files",
                "elasticsearch_available": True,
            }
        if search_resp.status_code in (401, 403):
            return {
                "status": "unauthorized",
                "file_query_endpoint": "search-files",
                "elasticsearch_available": True,
            }
        if search_resp.status_code not in (404, 501):
            return {
                "status": "error" if search_resp.status_code >= 500 else "not_found",
                "file_query_endpoint": None,
                "elasticsearch_available": True,
            }
    except requests.RequestException:
        return {
            "status": "unreachable",
            "file_query_endpoint": None,
            "elasticsearch_available": None,
        }

    try:
        query_resp = requests.post(
            f"{api_url}{FILE_QUERY_PATH}",
            headers=headers,
            json={},
            verify=ssl_verify,
            timeout=10,
        )
        if query_resp.status_code in (200, 400):
            return {
                "status": "ok",
                "file_query_endpoint": "query-files",
                "elasticsearch_available": False,
            }
        if query_resp.status_code in (401, 403):
            return {
                "status": "unauthorized",
                "file_query_endpoint": "query-files",
                "elasticsearch_available": False,
            }
        if query_resp.status_code not in (404, 501):
            return {
                "status": "error" if query_resp.status_code >= 500 else "not_found",
                "file_query_endpoint": None,
                "elasticsearch_available": False,
            }
    except requests.RequestException:
        return {
            "status": "unreachable",
            "file_query_endpoint": None,
            "elasticsearch_available": False,
        }

    try:
        fallback_resp = requests.post(
            f"{api_url}{FILE_QUERY_LINQ_PATH}",
            headers=headers,
            json={"take": 1},
            verify=ssl_verify,
            timeout=10,
        )
        if fallback_resp.status_code in (200, 400):
            return {
                "status": "fallback",
                "file_query_endpoint": "query-files-linq",
                "elasticsearch_available": False,
            }
        if fallback_resp.status_code in (401, 403):
            return {
                "status": "unauthorized",
                "file_query_endpoint": "query-files-linq",
                "elasticsearch_available": False,
            }
        if fallback_resp.status_code in (404, 501):
            return {
                "status": "not_found",
                "file_query_endpoint": None,
                "elasticsearch_available": False,
            }
        return {
            "status": "error",
            "file_query_endpoint": None,
            "elasticsearch_available": False,
        }
    except requests.RequestException:
        return {
            "status": "unreachable",
            "file_query_endpoint": None,
            "elasticsearch_available": False,
        }


def get_system_query_capability(api_url: str, api_key: str) -> Dict[str, Any]:
    """Determine which systems query endpoint is available for this server."""
    headers = {
        "x-ni-api-key": api_key,
        "Content-Type": "application/json",
        "User-Agent": "SystemLink-CLI/1.0 (cross-platform)",
    }
    ssl_verify = get_ssl_verify()

    try:
        search_resp = requests.post(
            f"{api_url}{SYSTEM_SEARCH_PATH}",
            headers=headers,
            json={"take": 1, "projection": ["id"]},
            verify=ssl_verify,
            timeout=10,
        )
        if search_resp.status_code in (200, 400):
            return {
                "status": "ok",
                "system_query_endpoint": "search-systems",
                "materialized_search_available": True,
            }
        if search_resp.status_code in (401, 403):
            return {
                "status": "unauthorized",
                "system_query_endpoint": "search-systems",
                "materialized_search_available": True,
            }
        if search_resp.status_code not in (404, 501):
            return {
                "status": "error" if search_resp.status_code >= 500 else "not_found",
                "system_query_endpoint": None,
                "materialized_search_available": True,
            }
    except requests.RequestException:
        return {
            "status": "unreachable",
            "system_query_endpoint": None,
            "materialized_search_available": None,
        }

    try:
        query_resp = requests.post(
            f"{api_url}{SYSTEM_QUERY_PATH}",
            headers=headers,
            json={"take": 1, "projection": "new(id)"},
            verify=ssl_verify,
            timeout=10,
        )
        if query_resp.status_code in (200, 400):
            return {
                "status": "ok",
                "system_query_endpoint": "query-systems",
                "materialized_search_available": False,
            }
        if query_resp.status_code in (401, 403):
            return {
                "status": "unauthorized",
                "system_query_endpoint": "query-systems",
                "materialized_search_available": False,
            }
        if query_resp.status_code in (404, 501):
            return {
                "status": "not_found",
                "system_query_endpoint": None,
                "materialized_search_available": False,
            }
        return {
            "status": "error",
            "system_query_endpoint": None,
            "materialized_search_available": False,
        }
    except requests.RequestException:
        return {
            "status": "unreachable",
            "system_query_endpoint": None,
            "materialized_search_available": False,
        }


def check_service_status(api_url: str, api_key: str) -> Dict[str, Any]:
    """Probe key SystemLink services and report their status.

    Checks reachability, authorization, and availability of core services.

    Args:
        api_url: The SystemLink API base URL.
        api_key: The API key for authentication.

    Returns:
        Dictionary with:
        - server_reachable: bool - whether any service responded
        - auth_valid: bool | None - whether the API key is authorized (None if unreachable)
        - services: dict mapping service name to status string
          ("ok", "unauthorized", "not_found", "error", "unreachable")
        - file_query_endpoint: selected file query endpoint, if available
        - elasticsearch_available: bool | None - whether search-files is available
        - system_query_endpoint: selected systems query endpoint, if available
        - materialized_search_available: bool | None - whether search-systems is available
        - platform: detected platform string (PLATFORM_SLE, PLATFORM_SLS,
          PLATFORM_UNREACHABLE, PLATFORM_UNKNOWN)
    """
    headers = {
        "x-ni-api-key": api_key,
        "Content-Type": "application/json",
        "User-Agent": "SystemLink-CLI/1.0 (cross-platform)",
    }
    ssl_verify = get_ssl_verify()

    services: Dict[str, str] = {}
    any_responded = False
    any_authorized = False
    all_unauthorized = True

    for display_name, method, url_path in SERVICE_CHECKS:
        try:
            full_url = f"{api_url}{url_path}"
            if method == "POST":
                resp = requests.post(
                    full_url,
                    headers=headers,
                    json={"take": 1},
                    verify=ssl_verify,
                    timeout=10,
                )
            else:
                resp = requests.get(
                    full_url,
                    headers=headers,
                    verify=ssl_verify,
                    timeout=10,
                )
            any_responded = True

            if resp.status_code in (200, 400):
                services[display_name] = "ok"
                any_authorized = True
                all_unauthorized = False
            elif resp.status_code == 401:
                services[display_name] = "unauthorized"
            elif resp.status_code == 403:
                services[display_name] = "unauthorized"
            elif resp.status_code == 404:
                services[display_name] = "not_found"
                all_unauthorized = False
            else:
                services[display_name] = "error"
                all_unauthorized = False
        except requests.RequestException:
            services[display_name] = "unreachable"

    # Determine overall status
    if not any_responded:
        return {
            "server_reachable": False,
            "auth_valid": None,
            "services": services,
            "file_query_endpoint": None,
            "elasticsearch_available": None,
            "system_query_endpoint": None,
            "materialized_search_available": None,
            "platform": PLATFORM_UNREACHABLE,
        }

    # Determine auth status: valid if any service accepted the key
    # If all responding services returned 401/403, the key is invalid
    auth_valid = any_authorized if any_responded else None
    if all_unauthorized and any_responded:
        auth_valid = False

    # Determine platform from service responses
    workorder_status = services.get("Work Order")
    if workorder_status in ("ok",):
        platform = PLATFORM_SLE
    elif workorder_status == "not_found":
        platform = PLATFORM_SLS
    else:
        platform = PLATFORM_UNKNOWN

    file_capability = get_file_query_capability(api_url, api_key)
    services["File"] = file_capability["status"]
    system_capability = get_system_query_capability(api_url, api_key)
    services["Systems"] = system_capability["status"]

    return {
        "server_reachable": True,
        "auth_valid": auth_valid,
        "services": services,
        "file_query_endpoint": file_capability["file_query_endpoint"],
        "elasticsearch_available": file_capability["elasticsearch_available"],
        "system_query_endpoint": system_capability["system_query_endpoint"],
        "materialized_search_available": system_capability["materialized_search_available"],
        "platform": platform,
    }


def get_platform_info(skip_health: bool = False) -> Dict[str, Any]:
    """Get detailed information about the current platform configuration.

    Args:
        skip_health: If True, skip live service health checks.

    Returns:
        Dictionary with platform info including URL, platform type, and services.
    """
    from .utils import get_api_key, get_base_url, get_web_url

    # Use profile-aware functions instead of keyring directly
    try:
        api_url = get_base_url()
    except Exception:
        api_url = "Not configured"

    try:
        web_url = get_web_url()
    except Exception:
        web_url = "Not configured"

    try:
        api_key = get_api_key()
        logged_in = bool(api_key)
    except Exception:
        logged_in = False

    # Get platform from profile or keyring config
    from .profiles import get_active_profile

    active_profile = get_active_profile()
    if active_profile and active_profile.platform:
        stored_platform = active_profile.platform
    else:
        # Fall back to keyring config
        cfg = _get_keyring_config()
        stored_platform = cfg.get("platform", PLATFORM_UNKNOWN)

    # Live service health check when logged in
    server_reachable: Optional[bool] = None
    auth_valid: Optional[bool] = None
    services: Optional[Dict[str, str]] = None
    platform = stored_platform
    file_query_endpoint: Optional[str] = None
    elasticsearch_available: Optional[bool] = None
    system_query_endpoint: Optional[str] = None
    materialized_search_available: Optional[bool] = None

    if not skip_health and logged_in and isinstance(api_url, str) and api_url != "Not configured":
        status = check_service_status(api_url, api_key)
        server_reachable = status["server_reachable"]
        auth_valid = status["auth_valid"]
        services = status["services"]
        platform = status["platform"]
        file_query_endpoint = status.get("file_query_endpoint")
        elasticsearch_available = status.get("elasticsearch_available")
        system_query_endpoint = status.get("system_query_endpoint")
        materialized_search_available = status.get("materialized_search_available")

    info: Dict[str, Any] = {
        "api_url": api_url,
        "web_url": web_url,
        "platform": platform,
        "platform_display": _get_platform_display_name(platform),
        "logged_in": logged_in,
        "server_reachable": server_reachable,
        "auth_valid": auth_valid,
    }

    if file_query_endpoint is not None:
        info["file_query_endpoint"] = file_query_endpoint
    if elasticsearch_available is not None:
        info["elasticsearch_available"] = elasticsearch_available
    if system_query_endpoint is not None:
        info["system_query_endpoint"] = system_query_endpoint
    if materialized_search_available is not None:
        info["materialized_search_available"] = materialized_search_available

    if services is not None:
        info["services"] = services

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
        PLATFORM_UNREACHABLE: "Unreachable (could not connect to server)",
    }
    return names.get(platform, platform)
