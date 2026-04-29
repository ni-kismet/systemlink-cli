"""Platform detection and feature gating for SystemLink CLI.

This module provides utilities to detect and manage the target platform
(SystemLink Enterprise vs SystemLink Server) and gate features accordingly.
"""

import json
import os
import sys
import time
from functools import lru_cache
from typing import Any, Dict, List, Optional, Tuple

import click
import keyring
import requests

from .utils import ExitCodes, get_ssl_verify

DEFAULT_SERVICE_PROBE_CACHE_TTL_SECONDS = 300

# Platform identifiers
PLATFORM_SLE = "SLE"  # SystemLink Enterprise (cloud)
PLATFORM_SLS = "SLS"  # SystemLink Server (on-premises)
PLATFORM_UNKNOWN = "unknown"
PLATFORM_UNREACHABLE = "unreachable"  # Server could not be contacted

# Feature matrix: maps features to platform availability
PLATFORM_FEATURES: Dict[str, Dict[str, bool]] = {
    PLATFORM_SLE: {
        "service_accounts": True,
        "comments_service": True,
        "dataframe_service": True,
        "workorder_service": True,
        "dynamic_form_fields": True,
        "function_execution": True,
        "templates": True,
        "workflows": True,
        "webapp": True,
    },
    PLATFORM_SLS: {
        "service_accounts": False,
        "comments_service": False,
        "dataframe_service": False,
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
    "comments_service": "Comments",
    "dataframe_service": "DataFrames",
    "workorder_service": "Work Order Service",
    "dynamic_form_fields": "Dynamic Form Fields",
    "function_execution": "Function Execution",
    "templates": "Test Plan Templates",
    "workflows": "Workflows",
    "webapp": "Web Applications",
}

FEATURE_SERVICE_DEPENDENCIES: Dict[str, str] = {
    "comments_service": "Comments",
    "dataframe_service": "DataFrame",
    "workorder_service": "Work Order",
    "templates": "Work Order",
    "workflows": "Work Order",
}

FEATURE_REQUIREMENT_MESSAGES: Dict[str, str] = {
    "comments_service": "  This feature requires the Comments service.",
    "dataframe_service": "  This feature requires the DataFrame service.",
    "workorder_service": "  This feature requires the Work Order service.",
    "templates": "  This feature requires the Work Order service.",
    "workflows": "  This feature requires the Work Order service.",
}

FILE_SEARCH_PATH = "/nifile/v1/service-groups/Default/search-files"
FILE_QUERY_PATH = "/nifile/v1/service-groups/Default/query-files"
FILE_QUERY_LINQ_PATH = "/nifile/v1/service-groups/Default/query-files-linq"
SYSTEM_SEARCH_PATH = "/nisysmgmt/v1/materialized/search-systems"
SYSTEM_QUERY_PATH = "/nisysmgmt/v1/query-systems"

SLE_ONLY_SERVICE_NAMES = (
    "Dynamic Form Fields",
    "Comments",
    "Notebook",
    "Routine v2",
)


def _detect_platform_from_services(services: Dict[str, str]) -> str:
    """Infer the platform from SLE-only service probes.

    Args:
        services: Mapping of service display name to probe status.

    Returns:
        PLATFORM_SLE when any SLE-only service is reachable or explicitly
        unauthorized, PLATFORM_SLS when all SLE-only services are missing,
        otherwise PLATFORM_UNKNOWN.
    """
    sle_statuses = [services.get(name) for name in SLE_ONLY_SERVICE_NAMES if name in services]
    if not sle_statuses:
        return PLATFORM_UNKNOWN

    if any(status in ("ok", "unauthorized") for status in sle_statuses):
        return PLATFORM_SLE

    if all(status == "not_found" for status in sle_statuses):
        return PLATFORM_SLS

    return PLATFORM_UNKNOWN


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
    _get_cached_service_status.cache_clear()


def _probe_service_status(api_url: str, api_key: str, method: str, url_path: str) -> str:
    """Probe a single service endpoint and return its normalized status."""
    headers = {
        "x-ni-api-key": api_key,
        "Content-Type": "application/json",
        "User-Agent": "SystemLink-CLI/1.0 (cross-platform)",
    }
    ssl_verify = get_ssl_verify()

    try:
        full_url = f"{api_url}{url_path}"
        if method == "POST":
            response = requests.post(
                full_url,
                headers=headers,
                json={"take": 1},
                verify=ssl_verify,
                timeout=10,
            )
        else:
            response = requests.get(
                full_url,
                headers=headers,
                verify=ssl_verify,
                timeout=10,
            )
    except requests.RequestException:
        return "unreachable"

    if response.status_code in (200, 400):
        return "ok"
    if response.status_code in (401, 403):
        return "unauthorized"
    if response.status_code in (404, 501):
        return "not_found"
    return "error"


@lru_cache(maxsize=None)
def _get_cached_service_status(service_name: str, api_url: str, api_key: str) -> str:
    """Probe and cache a service status for a specific server and credential pair."""
    service_check = next((entry for entry in SERVICE_CHECKS if entry[0] == service_name), None)
    if service_check is None:
        return "error"

    return _probe_service_status(api_url, api_key, service_check[1], service_check[2])


def _get_current_api_context() -> Optional[Tuple[Optional[str], str, str]]:
    """Resolve the current profile name, API URL, and key for service probing."""
    api_url = os.environ.get("SYSTEMLINK_API_URL")
    api_key = os.environ.get("SYSTEMLINK_API_KEY")
    if api_url and api_key:
        return None, api_url, api_key

    cfg = _get_keyring_config()
    config_api_url = cfg.get("api_url") if cfg else None
    config_api_key = cfg.get("api_key") if cfg else None
    if config_api_url and config_api_key:
        return None, str(config_api_url), str(config_api_key)

    try:
        from .profiles import get_active_profile_name
        from .utils import get_api_key, get_base_url

        return get_active_profile_name(), get_base_url(), get_api_key()
    except Exception:
        return None


def _get_service_probe_cache_ttl_seconds() -> int:
    """Return the persisted probe cache TTL in seconds."""
    raw_value = os.environ.get("SLCLI_SERVICE_PROBE_CACHE_TTL_SECONDS")
    if not raw_value:
        return DEFAULT_SERVICE_PROBE_CACHE_TTL_SECONDS

    try:
        ttl_seconds = int(raw_value)
    except ValueError:
        return DEFAULT_SERVICE_PROBE_CACHE_TTL_SECONDS

    return max(ttl_seconds, 0)


def _build_service_probe_cache_key(profile_name: Optional[str], api_url: str, api_key: str) -> str:
    """Build a stable cache key for persisted service probe snapshots."""
    import hashlib

    identity = profile_name or api_url.rstrip("/")
    api_key_fingerprint = hashlib.sha256(api_key.encode("utf-8")).hexdigest()[:16]
    return f"{identity}|{api_url.rstrip('/')}|{api_key_fingerprint}"


def _load_cached_service_status_snapshot(
    api_context: Tuple[Optional[str], str, str], max_age_seconds: Optional[int] = None
) -> Optional[Dict[str, Any]]:
    """Load a fresh persisted service probe snapshot when available."""
    from .profiles import get_service_probe_cache_entry

    ttl_seconds = (
        _get_service_probe_cache_ttl_seconds() if max_age_seconds is None else max_age_seconds
    )
    if ttl_seconds <= 0:
        return None

    profile_name, api_url, api_key = api_context
    cache_key = _build_service_probe_cache_key(profile_name, api_url, api_key)
    entry = get_service_probe_cache_entry(cache_key)
    if entry is None:
        return None

    cached_at = entry.get("cached_at")
    status = entry.get("status")
    if not isinstance(cached_at, (int, float)) or not isinstance(status, dict):
        return None
    if entry.get("server") != api_url:
        return None
    if time.time() - float(cached_at) > ttl_seconds:
        return None
    return status


def _save_service_status_snapshot(
    api_context: Tuple[Optional[str], str, str], status: Dict[str, Any]
) -> None:
    """Persist a service probe snapshot for reuse across CLI invocations."""
    from .profiles import save_service_probe_cache_entry

    profile_name, api_url, api_key = api_context
    cache_key = _build_service_probe_cache_key(profile_name, api_url, api_key)
    save_service_probe_cache_entry(
        cache_key,
        {
            "profile": profile_name,
            "server": api_url,
            "cached_at": time.time(),
            "status": status,
        },
    )


def _get_service_status_snapshot(force_refresh: bool = False) -> Optional[Dict[str, Any]]:
    """Get a cached or live service probe snapshot for the active connection."""
    api_context = _get_current_api_context()
    if api_context is None:
        return None

    if not force_refresh:
        cached_status = _load_cached_service_status_snapshot(api_context)
        if cached_status is not None:
            return cached_status

    _, api_url, api_key = api_context
    status = check_service_status(api_url, api_key)
    _save_service_status_snapshot(api_context, status)
    return status


def _get_service_status(service_name: str) -> Optional[str]:
    """Probe a service endpoint on demand when a feature depends on it."""
    status_snapshot = _get_service_status_snapshot(force_refresh=False)
    if status_snapshot is None:
        return None

    services = status_snapshot.get("services")
    if not isinstance(services, dict):
        return None
    service_status = services.get(service_name)
    return service_status if isinstance(service_status, str) else None


def _get_runtime_platform() -> str:
    """Resolve the best available platform identifier for user-facing feature messages."""
    platform = get_platform()
    if platform != PLATFORM_UNKNOWN:
        return platform

    status_snapshot = _get_service_status_snapshot(force_refresh=False)
    if status_snapshot is None:
        return platform

    detected_platform = status_snapshot.get("platform", PLATFORM_UNKNOWN)
    return detected_platform if isinstance(detected_platform, str) else PLATFORM_UNKNOWN


def has_feature(feature_name: str) -> bool:
    """Check if a feature is available on the current platform.

    Args:
        feature_name: The feature to check (e.g., 'dynamic_form_fields')

    Returns:
        True if the feature is available, False otherwise.
        Returns True if platform is unknown (graceful degradation).
    """
    platform = get_platform()
    service_dependency = FEATURE_SERVICE_DEPENDENCIES.get(feature_name)

    if service_dependency is not None:
        service_status = _get_service_status(service_dependency)
        if service_status in ("ok", "unauthorized"):
            return True
        if service_status == "not_found":
            return False

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

    platform = _get_runtime_platform()
    feature_display = FEATURE_DISPLAY_NAMES.get(feature_name, feature_name)
    platform_display = _get_platform_display_name(platform)

    click.echo(
        f"✗ Error: {feature_display} is not available on {platform_display}.",
        err=True,
    )
    click.echo(
        FEATURE_REQUIREMENT_MESSAGES.get(
            feature_name, "  This feature requires SystemLink Enterprise (SLE)."
        ),
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
    ["DataFrame", "POST", "/nidataframe/v1/query-tables"],
    ["Notebook", "POST", "/ninotebook/v1/notebook/query"],
    [
        "Comments",
        "GET",
        "/nicomments/v1/comments?resourceType=testmonitor%3AResult&resourceId=health-check",
    ],
    ["Routine v2", "GET", "/niroutine/v2/routines?take=1"],
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

    # Determine platform from multiple SLE-only service responses.
    platform = _detect_platform_from_services(services)

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
        status = _get_service_status_snapshot(force_refresh=True)
        if status is not None:
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
