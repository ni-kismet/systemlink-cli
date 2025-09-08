"""System certificate store integration utilities.

Configures the `requests` stack to use the operating system trust store via the
`truststore` library. This enables enterprise / corporate roots without modifying
the bundled certifi CA file.

Environment Variables:
    SLCLI_DISABLE_OS_TRUST=1  -> Skip injection entirely (use certifi)
    SLCLI_FORCE_OS_TRUST=1    -> Raise on any injection failure (fail fast)
    SLCLI_DEBUG_OS_TRUST=1    -> Print traceback on injection errors
"""

from __future__ import annotations

import os
import sys
import traceback

OS_TRUST_INJECTED: bool = False
OS_TRUST_REASON: str = "not-attempted"

__all__ = ["inject_os_trust", "OS_TRUST_INJECTED", "OS_TRUST_REASON"]


def inject_os_trust() -> None:
    """Inject system certificate store into requests via truststore.

    Steps:
      1. Respect SLCLI_DISABLE_OS_TRUST.
      2. Import truststore and call inject_into_requests().
      3. On failure: if SLCLI_FORCE_OS_TRUST set, re-raise; else log and fall back.

    Silence on success keeps CLI output clean.
    """
    global OS_TRUST_INJECTED, OS_TRUST_REASON
    if os.environ.get("SLCLI_DISABLE_OS_TRUST") == "1":
        OS_TRUST_INJECTED = False
        OS_TRUST_REASON = "disabled-env"
        return
    try:  # pragma: no cover - success path trivial
        import truststore  # type: ignore

        # Attempt known injection entry points in preferred order.
        candidates = [
            ("inject_into_requests", "requests"),  # modern direct requests patch
            ("inject_into_ssl", "ssl"),  # base SSL context patch
            ("inject_into_urllib3", "urllib3"),  # older fallback (affects requests indirectly)
        ]
        injected_variant = None
        for attr_name, label in candidates:
            if hasattr(truststore, attr_name):
                try:
                    getattr(truststore, attr_name)()  # type: ignore[misc]
                    injected_variant = label
                    break
                except Exception:  # pragma: no cover - try next variant
                    continue
        if injected_variant is None:
            raise AttributeError(
                "No compatible injection function on truststore module (expected one of: "
                + ", ".join(name for name, _ in candidates)
                + ")"
            )
        OS_TRUST_INJECTED = True
        OS_TRUST_REASON = f"injected:{injected_variant}"
    except Exception as exc:  # pragma: no cover - defensive
        if os.environ.get("SLCLI_FORCE_OS_TRUST") == "1":
            raise
        sys.stderr.write(
            f"[slcli] Info: system trust store injection skipped: {exc.__class__.__name__}: {exc}.\n"
        )
        if os.environ.get("SLCLI_DEBUG_OS_TRUST") == "1":
            traceback.print_exc()
        OS_TRUST_INJECTED = False
        OS_TRUST_REASON = f"error:{exc.__class__.__name__}"
