"""Human-readable summaries of migration discovery, mapping, and outcomes."""

from typing import List, Sequence

from slcli.migration.testmonitor.models import BatchResult, FailedItem, TestMonitorDiscovery
from slcli.migration.testmonitor.models import TestMonitorMigration
from slcli.migration.workspaces import WorkspaceMapping

MAX_LISTED_ITEMS = 10


def format_workspace_mapping(mapping: WorkspaceMapping) -> str:
    """Return each source workspace and the destination workspace it migrates to."""
    return "\n".join(
        [
            "Workspace mapping:",
            *(
                f"  {workspace.source_name} -> {workspace.destination_name}"
                for workspace in mapping.workspaces
            ),
        ]
    )


def format_summary(discovery: TestMonitorDiscovery) -> str:
    """Return deterministic Test Monitor discovery counts and failures."""
    lines = [
        "Test Monitor discovery:",
        f"  Products: {len(discovery.products)}",
        f"  Terminal results: {len(discovery.results)}",
        f"  Failed workspaces: {len(discovery.failures)}",
        *(f"    {failure.workspace}: {failure.error_type}" for failure in discovery.failures),
    ]
    if discovery.failures:
        lines.append("  Product workspaces were inferred without the failed workspaces.")
    return "\n".join(lines)


def failed_items(batches: Sequence[BatchResult]) -> List[FailedItem]:
    """Return the failed items of every batch."""
    return [item for batch in batches for item in batch.failed]


def format_migration_summary(migration: TestMonitorMigration) -> str:
    """Return Test Monitor migration counts, conflicts, and the first failed items."""
    conflicts = [c for batch in migration.products for c in batch.conflicts]
    failed_products = failed_items(migration.products)
    failed_results = failed_items(migration.results)
    lines = [
        "Test Monitor migration:",
        f"  Products migrated: {sum(len(b.migrated) for b in migration.products)}",
        f"  Product conflicts: {len(conflicts)}",
        f"  Products failed: {len(failed_products)}",
        f"  Results migrated: {sum(len(b.migrated) for b in migration.results)}",
        f"  Results failed: {len(failed_results)}",
    ]
    for conflict in conflicts[:MAX_LISTED_ITEMS]:
        lines.append(
            f"    Conflict: product {conflict.source_id} part number "
            f"{conflict.part_number!r} exists as {conflict.existing_id}"
        )
    if len(conflicts) > MAX_LISTED_ITEMS:
        lines.append(f"    +{len(conflicts) - MAX_LISTED_ITEMS} more conflicts (see log)")
    failures = [("product", f) for f in failed_products] + [("result", f) for f in failed_results]
    for kind, item in failures[:MAX_LISTED_ITEMS]:
        details = [f"stage={item.stage}", f"error={item.error_type}"]
        if item.destination_id:
            details.append(f"destination={item.destination_id}")
        lines.append(f"    Failed {kind} {item.source_id}: {' '.join(details)}")
    if len(failures) > MAX_LISTED_ITEMS:
        lines.append(f"    +{len(failures) - MAX_LISTED_ITEMS} more failures (see log)")
    return "\n".join(lines)
