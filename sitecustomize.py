"""Project-wide Python startup customizations.

Suppress the external pkg_resources deprecation warning emitted by
flake8-import-order during interpreter startup so lint output stays focused
on repository issues.
"""

from __future__ import annotations

import warnings


warnings.filterwarnings(
    "ignore",
    message=r"pkg_resources is deprecated as an API.*",
    category=UserWarning,
)
warnings.filterwarnings(
    "ignore",
    message=r"pkg_resources is deprecated as an API.*",
    category=DeprecationWarning,
)
