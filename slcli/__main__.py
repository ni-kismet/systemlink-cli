"""Entry point for the SystemLink CLI application.

Adds optional truststore-based system certificate store injection on all supported
platforms when the `truststore` extra is installed. Controlled via environment:
  SLCLI_DISABLE_OS_TRUST=1  -> skip injection
  SLCLI_FORCE_OS_TRUST=1    -> raise if injection fails
"""

from __future__ import annotations

import os
import sys
import traceback

# PyInstaller workaround for package imports
if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def _inject_os_trust() -> None:
    """Inject system certificate store into requests via truststore if available.

    Falls back silently to certifi when:
    - truststore isn't installed
    - injection raises an unexpected exception
    Unless SLCLI_FORCE_OS_TRUST=1 is set, in which case an ImportError or runtime
    error will abort startup.
    """
    if os.environ.get("SLCLI_DISABLE_OS_TRUST") == "1":
        return
    try:
        import truststore  # type: ignore

        truststore.inject_into_requests()
    except Exception as exc:  # pragma: no cover - defensive
        if os.environ.get("SLCLI_FORCE_OS_TRUST") == "1":
            # Re-raise to make failure explicit (e.g. in controlled environments)
            raise
        # Best-effort logging to stderr (avoid click dependency here)
        sys.stderr.write(
            f"[slcli] Info: truststore injection skipped ({exc.__class__.__name__}: {exc}).\n"
        )
        if os.environ.get("SLCLI_DEBUG_OS_TRUST") == "1":
            traceback.print_exc()


_inject_os_trust()

from slcli.main import cli  # noqa: E402  (import after injection)

if __name__ == "__main__":
    cli()
