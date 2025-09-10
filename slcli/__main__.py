"""Entry point for the SystemLink CLI application.

Performs system trust store injection (via truststore) before loading the main CLI.
Environment controls:
    SLCLI_DISABLE_OS_TRUST=1  -> skip injection
    SLCLI_FORCE_OS_TRUST=1    -> raise if injection fails
    SLCLI_DEBUG_OS_TRUST=1    -> show traceback on injection failure
"""

from __future__ import annotations

# Use absolute import to remain robust when executed as a standalone script
# (e.g. PyInstaller / Homebrew launcher contexts)
from slcli.ssl_trust import inject_os_trust  # noqa: E402,I100,I202

# Perform trust injection before importing the main CLI so that any subsequent
# imports of requests-based utilities see the patched SSL configuration.
inject_os_trust()

from slcli.main import cli  # noqa: E402,I100,I202

if __name__ == "__main__":
    cli()
