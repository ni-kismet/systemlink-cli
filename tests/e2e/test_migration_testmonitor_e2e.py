"""E2E tests that migrate Test Monitor products, results, and steps.

Requires a source profile, a destination profile, and an existing non-Default
destination workspace that holds only fixture-owned resources. See
``tests/e2e/README.md``.

Seeded source dataset, in one fixture-owned source workspace:

============  =========================================  ==========================
Product       Results                                    Destination before run
============  =========================================  ==========================
fresh         one with a three-level step tree           absent
conflicting   one with no steps                          same part number exists
============  =========================================  ==========================
"""

import re
import uuid
from collections.abc import Generator
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

import pytest
from click.testing import CliRunner, Result

from slcli.main import cli
from slcli.migration.annotations import COMPLETE, MIGRATION_ID, SOURCE_ID, STATUS
from slcli.migration.state import STATE_DIR_ENV
from slcli.migration.testmonitor.client import TestMonitorClient
from tests.e2e.migration_endpoints import (
    MigrationEndpoints,
    get_or_create_workspace,
    resolve_endpoints,
)
from tests.e2e.testmonitor_fixture import OwnedTestMonitorResources

# Shared with the other migration E2E modules: workspaces cannot be deleted on shared
# servers, so tests reuse fixed names. Each module cleans the workspace before and after.
SOURCE_WORKSPACE = "e2e-slcli-migration-source"

pytestmark = [pytest.mark.e2e_migration, pytest.mark.testmonitor]


@dataclass(frozen=True)
class Seeded:
    """Endpoints and IDs of the seeded source and destination data."""

    endpoints: MigrationEndpoints
    fresh_part: str
    fresh_product: str
    conflicting_part: str
    conflicting_product: str
    existing_destination_product: str
    stepped_result: str
    plain_result: str


def _result(part_number: str) -> Dict[str, object]:
    return {
        "programName": f"{part_number} program",
        "partNumber": part_number,
        "serialNumber": "SN-1",
        "status": {"statusType": "PASSED", "statusName": "Passed"},
    }


def _step(result_id: str, name: str, parent_id: str = "root") -> Dict[str, object]:
    return {
        "resultId": result_id,
        "parentId": parent_id,
        "name": name,
        "stepType": "NumericLimitTest",
        "status": {"statusType": "PASSED", "statusName": "Passed"},
        "totalTimeInSeconds": 1.5,
    }


@pytest.fixture(scope="module")
def seeded() -> Generator[Seeded, None, None]:
    """Seed the source, plant one conflicting destination product, and clean both after."""
    endpoints = resolve_endpoints()
    source_workspace_id = get_or_create_workspace(endpoints.source, SOURCE_WORKSPACE)
    source = OwnedTestMonitorResources(endpoints.source, {SOURCE_WORKSPACE: source_workspace_id})
    destination = OwnedTestMonitorResources(
        endpoints.destination,
        {endpoints.destination_workspace: endpoints.destination_workspace_id},
    )
    source.clean()
    destination.clean()
    try:
        run_id = uuid.uuid4().hex[:12]
        fresh, conflicting = (f"migration-e2e-{n}-{run_id}" for n in ("fresh", "conflicting"))
        fresh_id, conflicting_id = source.create_products(
            [{"name": part, "partNumber": part} for part in (fresh, conflicting)],
            SOURCE_WORKSPACE,
        )
        [existing_id] = destination.create_products(
            [{"name": "pre-existing", "partNumber": conflicting}], endpoints.destination_workspace
        )
        stepped, plain = source.create_results(
            [_result(fresh), _result(conflicting)], SOURCE_WORKSPACE
        )
        [parent] = source.create_steps([_step(stepped, "parent")])
        [child] = source.create_steps([_step(stepped, "child", parent)])
        source.create_steps([_step(stepped, "grandchild", child)])
        yield Seeded(
            endpoints=endpoints,
            fresh_part=fresh,
            fresh_product=fresh_id,
            conflicting_part=conflicting,
            conflicting_product=conflicting_id,
            existing_destination_product=existing_id,
            stepped_result=stepped,
            plain_result=plain,
        )
    finally:
        destination.clean()
        source.clean()


def _invoke(args: List[str], prefect_api_url: str) -> Result:
    return CliRunner().invoke(cli, ["migrate", *args, "--prefect-api-url", prefect_api_url])


def _destination_results(seeded: Seeded) -> List[Dict[str, Any]]:
    client = TestMonitorClient(seeded.endpoints.destination)
    return list(
        client.query_records(
            "results", "workspace == @0", [seeded.endpoints.destination_workspace_id]
        )
    )


def _step_parents(seeded: Seeded, destination_result_id: str) -> Dict[str, Optional[str]]:
    """Return each destination step name mapped to its parent step name."""
    client = TestMonitorClient(seeded.endpoints.destination)
    steps = list(client.query_records("steps", "resultId == @0", [destination_result_id]))
    by_id = {step["stepId"]: step for step in steps}
    return {step["name"]: by_id.get(step.get("parentId"), {}).get("name") for step in steps}


@pytest.fixture(scope="module")
def one_completed_migration_run(
    seeded: Seeded, test_prefect_server: str, tmp_path_factory: pytest.TempPathFactory
) -> Generator[Result, None, None]:
    """Run the migration command once and share its result across this module.

    Each live migration takes about a minute, so the tests below check different
    parts of one run instead of migrating separately. As a consequence:

    - The tests share destination state and must not change anything another
      test checks; ``test_rerun_does_not_duplicate`` only adds a no-op re-run.
    - A failed migration fails every test that uses this fixture, each
      reporting the same command output.
    """
    state = tmp_path_factory.mktemp("migration-state")
    with pytest.MonkeyPatch.context() as patch:
        patch.setenv(STATE_DIR_ENV, str(state))
        yield _invoke(
            [
                "--source-profile",
                seeded.endpoints.source.profile_name,
                "--destination-profile",
                seeded.endpoints.destination.profile_name,
                "--workspace-mappings",
                f"{SOURCE_WORKSPACE}:{seeded.endpoints.destination_workspace}",
            ],
            test_prefect_server,
        )


def _migration_id(result: Result) -> str:
    match = re.search(r"^Migration ID: (\S+)$", result.output, re.MULTILINE)
    assert match, result.output
    return match.group(1)


def test_summary_reports_migration_and_conflict(
    seeded: Seeded, one_completed_migration_run: Result
) -> None:
    """The run succeeds, reporting the conflicting product without failing."""
    assert one_completed_migration_run.exit_code == 0, one_completed_migration_run.output
    assert (
        "Products migrated: 1\n  Product conflicts: 1\n  Products failed: 0"
        in one_completed_migration_run.output
    )
    assert "Results migrated: 2\n  Results failed: 0" in one_completed_migration_run.output
    assert f"Conflict: product {seeded.conflicting_product}" in one_completed_migration_run.output


def test_products_migrate_except_conflicts(
    seeded: Seeded, one_completed_migration_run: Result
) -> None:
    """The fresh product is annotated; the existing destination product is unchanged."""
    client = TestMonitorClient(seeded.endpoints.destination)
    products = {
        p["partNumber"]: p
        for p in client.query_records(
            "products",
            "partNumber == @0 || partNumber == @1",
            [seeded.fresh_part, seeded.conflicting_part],
        )
    }

    fresh = products[seeded.fresh_part]
    assert fresh["workspace"] == seeded.endpoints.destination_workspace_id
    assert fresh["properties"][SOURCE_ID] == seeded.fresh_product
    assert fresh["properties"][MIGRATION_ID] == _migration_id(one_completed_migration_run)
    existing = products[seeded.conflicting_part]
    assert existing["id"] == seeded.existing_destination_product
    assert existing["name"] == "pre-existing"
    assert MIGRATION_ID not in existing["properties"]


def test_results_complete_with_step_tree(
    seeded: Seeded, one_completed_migration_run: Result
) -> None:
    """Both results migrate complete, keep part numbers, and drop file references."""
    results = {r["properties"][SOURCE_ID]: r for r in _destination_results(seeded)}

    assert set(results) == {seeded.stepped_result, seeded.plain_result}
    assert results[seeded.stepped_result]["partNumber"] == seeded.fresh_part
    assert results[seeded.plain_result]["partNumber"] == seeded.conflicting_part
    for result in results.values():
        assert result["properties"][STATUS] == COMPLETE
        assert not result.get("fileIds")
    assert _step_parents(seeded, results[seeded.stepped_result]["id"]) == {
        "parent": None,
        "child": "parent",
        "grandchild": "child",
    }


def test_rerun_does_not_duplicate(
    seeded: Seeded, one_completed_migration_run: Result, test_prefect_server: str
) -> None:
    """Re-running a migration by ID reuses completed batches instead of writing again."""
    before = len(_destination_results(seeded))
    state = Path(one_completed_migration_run.output.split("Log: ")[-1].strip()).parents[1]

    with pytest.MonkeyPatch.context() as patch:
        patch.setenv(STATE_DIR_ENV, str(state))
        rerun = _invoke(
            ["--migration-id", _migration_id(one_completed_migration_run)], test_prefect_server
        )

    assert rerun.exit_code == 0, rerun.output
    assert "Results migrated: 2" in rerun.output
    assert len(_destination_results(seeded)) == before
