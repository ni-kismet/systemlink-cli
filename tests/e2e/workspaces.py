"""The only workspaces E2E tests may create.

Workspaces cannot be deleted on shared servers, so every created name leaks
permanently. Fixtures take an ``E2EWorkspace`` member rather than a string, so a
new workspace requires adding a member here. Keep this set small and fixed.
"""

from enum import Enum


class E2EWorkspace(Enum):
    """Fixed, reusable workspace names; values are the server-side names."""

    SOURCE = "e2e-slcli-migration-source"
    SOURCE_OTHER = "e2e-slcli-migration-source-other"
    DESTINATION = "e2e-slcli-migration-destination"
    DISABLED_SOURCE = "e2e-slcli-migration-disabled-source"
    DISABLED_DESTINATION = "e2e-slcli-migration-disabled-destination"
