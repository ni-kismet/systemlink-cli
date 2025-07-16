"""Shared utility functions for SystemLink CLI."""

import os
from typing import Dict

import keyring
import requests
from nisystemlink.clients.core._http_configuration import HttpConfiguration


# --- SystemLink HTTP Configuration ---
def get_http_configuration() -> HttpConfiguration:
    """Return a configured SystemLink HttpConfiguration using environment or keyring credentials."""
    server_uri = (
        os.environ.get("SYSTEMLINK_API_URL")
        or keyring.get_password("systemlink-cli", "SYSTEMLINK_API_URL")
        or "http://localhost:8000"
    )
    api_key = os.environ.get("SYSTEMLINK_API_KEY") or keyring.get_password(
        "systemlink-cli", "SYSTEMLINK_API_KEY"
    )
    if not api_key:
        raise RuntimeError("API key not found. Please set SYSTEMLINK_API_KEY or run 'slcli login'.")
    return HttpConfiguration(
        server_uri=server_uri,
        api_key=api_key,
    )


def get_base_url() -> str:
    """Retrieve the SystemLink API base URL from environment or keyring."""
    url = os.environ.get("SYSTEMLINK_API_URL")
    if not url:
        url = keyring.get_password("systemlink-cli", "SYSTEMLINK_API_URL")
    return url or "http://localhost:8000"


def get_api_key() -> str:
    """Retrieve the SystemLink API key from environment or keyring."""
    import click

    api_key = os.environ.get("SYSTEMLINK_API_KEY")
    if not api_key:
        api_key = keyring.get_password("systemlink-cli", "SYSTEMLINK_API_KEY")
    if not api_key:
        click.echo(
            "Error: API key not found. Please set the SYSTEMLINK_API_KEY "
            "environment variable or run 'slcli login'."
        )
        raise click.ClickException("API key not found.")
    return api_key


def get_headers(content_type: str = "") -> Dict[str, str]:
    """Return headers for SystemLink API requests.

    Allows caller to override Content-Type. If content_type is None or empty, omit the header.
    """
    headers = {
        "x-ni-api-key": get_api_key(),
    }
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def get_ssl_verify() -> bool:
    """Return SSL verification setting from environment variable. Defaults to True."""
    env = os.environ.get("SLCLI_SSL_VERIFY")
    if env is not None:
        return env.lower() not in ("0", "false", "no")
    return True


def get_workspace_map() -> Dict[str, str]:
    """Return a mapping of workspace id to workspace name."""
    url = f"{get_base_url()}/niuser/v1/workspaces"
    resp = requests.get(url, headers=get_headers(), verify=get_ssl_verify())
    resp.raise_for_status()
    ws_data = resp.json()
    return {ws.get("id"): ws.get("name", ws.get("id")) for ws in ws_data.get("workspaces", [])}


def get_workspace_id_by_name(name: str) -> str:
    """Return the workspace id for a given workspace name (case-sensitive). Raises if not found."""
    ws_map = get_workspace_map()
    for ws_id, ws_name in ws_map.items():
        if ws_name == name:
            return ws_id
    raise ValueError(f"Workspace name '{name}' not found.")
