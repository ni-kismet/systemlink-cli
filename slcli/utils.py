"""Shared utility functions for SystemLink CLI."""

import os
from typing import Dict

import keyring


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


def get_headers() -> Dict[str, str]:
    """Return headers for SystemLink API requests."""
    return {
        "x-ni-api-key": get_api_key(),
        "Content-Type": "application/json",
    }


def get_ssl_verify() -> bool:
    """Return SSL verification setting from environment variable. Defaults to True."""
    env = os.environ.get("SLCLI_SSL_VERIFY")
    if env is not None:
        return env.lower() not in ("0", "false", "no")
    return True
