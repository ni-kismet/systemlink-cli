"""Shared helpers for systems query endpoints and projections."""

import re
import sys
from typing import List, Optional, Tuple

import click
import requests as requests_lib

from .utils import ExitCodes, get_base_url

DEFAULT_SYSTEM_JSON_FIELDS = (
    "id",
    "alias",
    "workspace",
    "connected",
    "host",
    "kernel",
)

EXTENDED_SYSTEM_JSON_FIELDS = (
    "osversion",
    "cpuarch",
    "deviceclass",
    "keywords",
    "packages",
)

SYSTEM_JSON_PROJECTION_MAP = {
    "id": "id",
    "alias": "alias",
    "workspace": "workspace",
    "connected": "connected.data.state as connected",
    "host": "grains.data.host as host",
    "kernel": "grains.data.kernel as kernel",
    "osversion": "grains.data.osversion as osversion",
    "cpuarch": "grains.data.cpuarch as cpuarch",
    "deviceclass": "grains.data.deviceclass as deviceclass",
    "keywords": "keywords.data as keywords",
    "packages": "packages.data as packages",
}

ALL_SYSTEM_JSON_FIELDS = DEFAULT_SYSTEM_JSON_FIELDS + EXTENDED_SYSTEM_JSON_FIELDS

MATERIALIZED_SYSTEM_LIST_PROJECTION = [
    "id",
    "alias",
    "workspace",
    "connected",
    "advancedGrains.host",
    "advancedGrains.os",
]

MATERIALIZED_SYSTEM_MCP_PROJECTION = [
    "id",
    "alias",
    "workspace",
    "connected",
    "advancedGrains.host",
    "advancedGrains.os",
]


def get_sysmgmt_base_url() -> str:
    """Get the base URL for the Systems Management API."""
    return f"{get_base_url()}/nisysmgmt/v1"


def get_system_query_url() -> str:
    """Get the query-systems endpoint URL."""
    return f"{get_sysmgmt_base_url()}/query-systems"


def get_system_search_url() -> str:
    """Get the materialized search-systems endpoint URL."""
    return f"{get_sysmgmt_base_url()}/materialized/search-systems"


def build_system_projection(field_names: Tuple[str, ...]) -> str:
    """Build a query-systems projection for the requested system fields."""
    ordered_fields = [
        SYSTEM_JSON_PROJECTION_MAP[field_name]
        for field_name in ALL_SYSTEM_JSON_FIELDS
        if field_name in field_names
    ]
    return f"new({', '.join(ordered_fields)})"


DEFAULT_SYSTEM_LIST_PROJECTION = build_system_projection(DEFAULT_SYSTEM_JSON_FIELDS)
FULL_SYSTEM_LIST_PROJECTION = build_system_projection(ALL_SYSTEM_JSON_FIELDS)


def escape_search_filter_value(value: str) -> str:
    """Escape values for Lucene-style materialized systems search filters."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def quote_search_value(value: str, contains: bool = False) -> str:
    """Quote a materialized systems search value, optionally using wildcards."""
    escaped = escape_search_filter_value(value)
    if contains:
        escaped = f"*{escaped}*"
    return f'"{escaped}"'


def build_materialized_system_search_filter(
    alias: Optional[str] = None,
    state: Optional[str] = None,
    os_filter: Optional[str] = None,
    host: Optional[str] = None,
    has_keyword: Optional[Tuple[str, ...]] = None,
    property_filters: Optional[Tuple[str, ...]] = None,
    workspace_id: Optional[str] = None,
) -> Optional[str]:
    """Build a materialized search-systems filter from convenience options."""
    parts: List[str] = []

    if alias:
        parts.append(f"alias:{quote_search_value(alias, contains=True)}")
    if state:
        parts.append(f"connected:{quote_search_value(state)}")
    if os_filter:
        os_query = quote_search_value(os_filter, contains=True)
        parts.append(f"(advancedGrains.os:{os_query} OR minionDetails.osFullName:{os_query})")
    if host:
        host_query = quote_search_value(host, contains=True)
        parts.append(f"(advancedGrains.host:{host_query} OR minionDetails.localhost:{host_query})")
    if has_keyword:
        for keyword in has_keyword:
            parts.append(f"keywords:{quote_search_value(keyword)}")
    if property_filters:
        for prop in property_filters:
            if "=" not in prop:
                click.echo(
                    f"✗ Invalid property filter '{prop}': expected KEY=VALUE format",
                    err=True,
                )
                sys.exit(ExitCodes.INVALID_INPUT)
            key, val = prop.split("=", 1)
            key = key.strip()
            if not re.match(r"^[A-Za-z0-9_.]+$", key):
                click.echo(
                    f"✗ Invalid property key '{key}': "
                    "only alphanumeric characters, underscores, and dots are allowed",
                    err=True,
                )
                sys.exit(ExitCodes.INVALID_INPUT)
            parts.append(f"properties.{key}:{quote_search_value(val.strip())}")
    if workspace_id:
        parts.append(f"workspace:{quote_search_value(workspace_id)}")

    return " AND ".join(parts) if parts else None


def is_system_search_endpoint_unavailable(exc: requests_lib.HTTPError) -> bool:
    """Return whether the materialized systems search endpoint is unavailable."""
    response = getattr(exc, "response", None)
    return response is not None and response.status_code in (404, 501)
