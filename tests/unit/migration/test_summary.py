"""Tests for migration summaries."""

from datetime import datetime, timezone

from slcli.migration.summary import format_migration_summary, format_summary
from slcli.migration.testmonitor.models import (
    BatchResult,
    DiscoveredProduct,
    DiscoveredResult,
    FailedItem,
    MigratedItem,
    ProductConflict,
    TestMonitorDiscovery,
    WorkspaceFailure,
)
from slcli.migration.testmonitor.models import TestMonitorMigration

DISCOVERY = TestMonitorDiscovery(
    products=(DiscoveredProduct(id="p", workspace="Lab"),),
    results=(
        DiscoveredResult(
            id="r",
            product_id="p",
            workspace="Lab",
            status="PASSED",
            updated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        ),
    ),
    failures=(WorkspaceFailure(workspace="Broken", error_type="HTTPError"),),
    workspaces=("Broken", "Lab"),
)

MIGRATION = TestMonitorMigration(
    products=(
        BatchResult(
            resource="products",
            batch=0,
            migrated=(MigratedItem(source_id="p1", destination_id="d1"),),
            conflicts=(
                ProductConflict(
                    source_id="p2",
                    part_number="PN-2",
                    expected_workspace="Dest-id",
                ),
            ),
        ),
    ),
    results=(
        BatchResult(
            resource="results",
            batch=0,
            migrated=(MigratedItem(source_id="r1", destination_id="dr1", steps=3),),
            failed=(
                FailedItem(
                    source_id="r2", stage="steps", error_type="HTTPError", destination_id="dr2"
                ),
            ),
        ),
    ),
)


def test_summary_is_deterministic() -> None:
    """The summary reports counts and each failed workspace."""
    assert format_summary(DISCOVERY) == (
        "Test Monitor discovery:\n"
        "  Products: 1\n"
        "  Terminal results: 1\n"
        "  Failed workspaces: 1\n"
        "    Broken: HTTPError\n"
        "  Product workspaces were inferred without the failed workspaces."
    )


def test_summary_omits_failure_note_without_failures() -> None:
    """The inference caveat appears only when a workspace failed."""
    summary = format_summary(DISCOVERY.model_copy(update={"failures": ()}))

    assert summary.endswith("  Failed workspaces: 0")


def test_migration_summary_lists_conflicts_and_failures() -> None:
    """Counts precede conflict and failure details with their identifiers."""
    assert format_migration_summary(MIGRATION) == (
        "Test Monitor migration:\n"
        "  Products migrated: 1\n"
        "  Product conflicts: 1\n"
        "  Products failed: 0\n"
        "  Results migrated: 1\n"
        "  Results failed: 1\n"
        "    Conflict: product p2 part number 'PN-2' already exists on the destination\n"
        "    Failed result r2: stage=steps error=HTTPError destination=dr2"
    )


def test_migration_summary_truncates_long_failure_lists() -> None:
    """Only the first failures are listed; the remainder points at the log."""
    failed = tuple(
        FailedItem(source_id=f"r{i}", stage="create", error_type="HTTPError") for i in range(12)
    )
    migration = TestMonitorMigration(
        results=(BatchResult(resource="results", batch=0, failed=failed),)
    )

    summary = format_migration_summary(migration)

    assert "Failed result r9:" in summary
    assert "Failed result r10:" not in summary
    assert "+2 more failures (see log)" in summary
