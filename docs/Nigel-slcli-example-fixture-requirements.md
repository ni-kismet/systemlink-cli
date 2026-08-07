[[_TOC_]]

# Nigel slcli example fixture requirements

## Purpose

This document defines the data contract for an installable `slcli example`
fixture that can validate the 14 Systems and Products examples in
[Nigel answers questions about select SystemLink resources](../Nigel-answers-questions-about-select-SystemLink-resources.md).
The fixture must be useful in two ways:

1. `slcli` can install it, query it, and return deterministic JSON results.
2. Nigel can query the same workspace and produce grounded answers with
   positive, negative, relationship, and time-bounded cases.

This is a fixture requirement, not a claim that every current `slcli` command
already exposes every required relationship. The installer must use supported
SystemLink resource fields and must report an explicit provisioning failure
when a required relationship cannot be represented. It must not create data
that looks complete in the UI but cannot be retrieved by the CLI or Nigel.

The current baseline is recorded in
[Nigel slcli example-query validation](Nigel-slcli-example-query-validation.md).
The dev run against `a-fred-test-workspace` showed that the existing examples
provide products, assets, systems, results, tables, and notebooks, but lack
positive package inventory, alarms, jobs, feeds, states, tags, specifications,
and cross-resource traceability.

## Implementation review and v1.0 decision

The full acceptance matrix below is broader than the current generic example
installer. The first implementation therefore ships a deliberately incomplete
phase-one fixture rather than fabricating relationships that the accepted CLI
or Nigel queries cannot retrieve.

The current fixture at
[`slcli/examples/nigel-slcli-query-fixture/`](../slcli/examples/nigel-slcli-query-fixture/)
provisions 5 virtual systems, 6 DUT/instrument assets, 2 products, 12 test
results, 3 DataFrame schemas, and 2 supporting files. Test results carry the
system, product, DUT serial, station, and instrument asset ID as API fields;
six results also carry measurement steps. The fixture uses the opt-in install
manifest and returns `validation.complete: false` with a nonzero exit code
until the unsupported capabilities are implemented or removed from the
acceptance scope.

The following requirements need an additional verified provisioning layer:

| Requirement                 | Review outcome                                                                                                                                                                                                 |
| --------------------------- | -------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Workspace                   | The installer requires an existing workspace. It does not create, own, or delete workspaces.                                                                                                                   |
| Package inventory           | Virtual-system creation creates aliases only; it does not seed the package projection used by `system list` and `system get`.                                                                                  |
| Alarms and jobs             | No generic example resource type currently creates alarm instances or system jobs with the required states and relationships.                                                                                  |
| Feeds and deployment states | CLI create helpers exist, but feed package upload and state population are separate workflows and are not idempotent example resources.                                                                        |
| Tag history                 | The normal example path has no bounded history writer; current tag values are not a substitute for history.                                                                                                    |
| Specifications and evidence | Specification helpers are not wired into the generic provisioner, and condition outcomes have not been verified as queryable evidence.                                                                         |
| DataFrame rows              | The generic provisioner creates table schemas only; row append is a separate API operation.                                                                                                                    |
| Ownership and cleanup       | The provisioner adds its example marker where the resource API supports keywords or metadata. Virtual systems do not accept that marker, so system ownership must be solved before claiming cleanup isolation. |

This is intentional pushback on the proposal, not an acceptance waiver. The
definition of done remains appropriate for a complete fixture, but the current
release must be evaluated as a core-data fixture plus an explicit unsupported
capability report. The next phase should add and test each resource family with
raw `slcli -f json` checks before changing `validation.complete` to `true`.

## Proposed example

- Example name: `nigel-slcli-query-fixture`
- Install command:

  ```bash
  slcli example install nigel-slcli-query-fixture \
    -w a-fred-test-workspace -f json
  ```

- Delete command:

  ```bash
  slcli example delete nigel-slcli-query-fixture \
    -w a-fred-test-workspace -f json
  ```

- Scope: one dedicated workspace per installation.
- Ownership marker on every resource: `slcli-example:nigel-slcli-query-fixture`.
- Idempotence: a second install updates or skips the same logical resources;
  it does not duplicate results, tag history, packages, or alarms.
- Cleanup: delete removes only resources carrying the ownership marker. It must
  not remove a pre-existing workspace or user-owned resources.
- Reproducibility: dates, values, names, logical IDs, and expected counts are
  fixed by the fixture version. The installer may substitute server IDs, but
  it must return a logical-ID to server-ID map in JSON.

The fixture should be installed into a clean workspace for acceptance testing.
The existing `a-fred-test-workspace` is useful for comparison, but it contains
resources from other examples and should not be treated as a clean expected
count baseline.

## Shared data conventions

Use these conventions across all resource types:

- Workspace: `nigel-slcli-query-fixture-workspace`.
- Primary system: `PXI-Rack-07`.
- Additional systems: `PXI-Rack-12`, `HIL-03`, `BurnIn-02`, and `TestBench-44`.
- Primary product: `Product XYZ`, part number `XYZ-2025-001`, family
  `Power Electronics`.
- Primary DUT: serial number `1234567`, model `Product XYZ`.
- Primary test station: `cRIO0100101NIC`.
- Primary feed: `Nigel Fixture Windows Feed`.
- Primary deployment state: `Nigel Fixture Windows State`.
- Primary tag: `nigel/fixture/temperature`, units `C`.
- Primary specification: `Output Voltage`.

All timestamps must be explicit UTC timestamps. The fixture must use a date
range relative to the evaluation date only if the installer also writes the
resolved dates into its manifest. Otherwise, use the fixed dates below so
commands and expected answers remain reproducible.

## Required resource inventory

The installer must create the following resource families. Counts are minimums;
logical names and relationships are normative.

| Resource family                   |                        Minimum | Required purpose                                                                                             |
| --------------------------------- | -----------------------------: | ------------------------------------------------------------------------------------------------------------ |
| Workspace                         |                              1 | Isolate the fixture and provide a stable query scope.                                                        |
| Systems                           |                              5 | Positive package matches, a version-negative system, current-system context, and cross-domain relationships. |
| Installed package records         |       5 systems with inventory | Validate package name filtering, package detail, and version comparison.                                     |
| Alarms                            |        3 on the primary system | Validate multiple active alarms and a grounded empty-alarm response on another system.                       |
| Assets                            |                              6 | DUT, PXI-4071 traceability, connected asset summary, calibration state, and asset filtering.                 |
| Products                          |                              2 | Product-scoped results and a product with no results for negative validation.                                |
| DUTs                              |                              2 | Serial history and comparison between a populated and unknown serial.                                        |
| Test results                      |                    At least 12 | Serial history, failures by product/time/station, instrument traceability, and result detail.                |
| Test steps or measurement records |  At least 6 results with steps | Store the instrument and channel used for the DUT measurement in a CLI-readable relationship.                |
| Feed                              |                              1 | Package summary with names and versions.                                                                     |
| Feed packages                     |                             12 | Exercise package enumeration and grouped version summaries.                                                  |
| Deployment state                  |           1 populated, 1 empty | Positive software summary and grounded no-package response.                                                  |
| Jobs                              |        3 on the primary system | Queued, running, and failed job states.                                                                      |
| Tags                              |                 1 with history | Current value and recent trend.                                                                              |
| Tag history samples               |                    At least 12 | Cover the last hour with a stable range and a visible upward drift.                                          |
| Specifications                    |   1 with at least 5 conditions | Product compliance query.                                                                                    |
| Compliance evidence               |  At least 5 condition outcomes | Three open gaps, one pass, and one not-run condition.                                                        |
| DataFrame tables                  |                    3 populated | Provide bounded measurement data for result and analysis workflows.                                          |
| Notebooks                         |   1 optional analysis notebook | Demonstrate the compliance calculation workflow when direct CLI gap computation is unavailable.              |
| Files                             | 2 optional source/report files | Preserve a specification source and a generated compliance report for traceability.                          |

## System and software inventory

Create five systems with stable aliases and different inventory outcomes.
`PXI-Rack-07` is the primary current-page system.

| System         | Package inventory                                                                 | Expected use                                                                         |
| -------------- | --------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------ |
| `PXI-Rack-07`  | `NI-DAQmx 2025 Q1`, `NI-DMM 2025 Q1`, `NI-SCOPE 24.8`, `SystemLink Client 2025.3` | Current-system software, alarms, jobs, connected assets, and version-positive query. |
| `PXI-Rack-12`  | `NI-DAQmx 24.8`, `NI-DMM 24.8`, `SystemLink Client 2025.3`                        | Additional package match.                                                            |
| `HIL-03`       | `NI-DAQmx 20.1`, `NI-SCOPE 24.8`, `SystemLink Client 2025.2`                      | Boundary and version-positive query.                                                 |
| `BurnIn-02`    | `NI-DAQmx 19.0`, `SystemLink Client 2024.4`                                       | Name match but version-negative for `> 20.0`.                                        |
| `TestBench-44` | `NI-DMM 2025 Q1`, `NI-SCOPE 24.8`                                                 | Non-match for DAQmx and negative filtering.                                          |

Each system must expose package name and version through the same system detail
or inventory projection that `slcli system get --include-all` and the Nigel
system tool can read. The installer must not encode versions only in a display
name or unrelated property.

Acceptance checks:

```bash
slcli system list -w <WORKSPACE_ID> --has-package DAQmx -f json --take 100
slcli system get <PXI_RACK_07_ID> --include-all -f json
```

The first command must return four systems, and the second must include the
four packages above plus the related alarms, assets, jobs, and result sections.
A package-version query must identify `PXI-Rack-07`, `PXI-Rack-12`, and `HIL-03`
as later than `20.0`, while excluding `BurnIn-02` and `TestBench-44`.

## Alarms and jobs

Attach three active alarms to `PXI-Rack-07`:

| Logical alarm             | State                    | Summary                                  | Related resource          |
| ------------------------- | ------------------------ | ---------------------------------------- | ------------------------- |
| `alarm-disk-space`        | Active                   | Disk space low on controller C:          | `PXI-Rack-07`             |
| `alarm-calibration-due`   | Active                   | Calibration overdue for DMM `DMM-000184` | Asset `asset-dmm-pxi4071` |
| `alarm-inventory-refresh` | Acknowledged or inactive | Inventory refresh required               | `PXI-Rack-07`             |

Only the first two may be returned by an active-alarm query. Include severity,
created time, source, and related system or asset IDs. Add a second system with
no active alarms to verify that Nigel returns a grounded zero rather than
reusing the primary system's alarms.

Attach these jobs to `PXI-Rack-07`:

- `job-package-deployment`: queued, package deployment action.
- `job-inventory-refresh`: running, inventory refresh action.
- `job-reboot-failed`: failed, reboot action with a recent failure timestamp.

Each job must include state, action, created or updated time, system ID, and an
error or result summary when applicable. The job records must be returned by
the system detail relationship used by `slcli system get --include-jobs`.

## Assets and time-aware traceability

Create these assets and connect them to the systems and results as shown.

| Logical asset        | Type       | Model        | Serial       | System        | Calibration      |
| -------------------- | ---------- | ------------ | ------------ | ------------- | ---------------- |
| `asset-dut-1234567`  | DUT        | Product XYZ  | `1234567`    | `PXI-Rack-07` | Not applicable   |
| `asset-dmm-pxi4071`  | Instrument | NI PXI-4071  | `DMM-000184` | `PXI-Rack-07` | Due `2026-09-15` |
| `asset-scope-a2231`  | Instrument | NI PXI-5105  | `A-2231`     | `PXI-Rack-07` | OK               |
| `asset-power-a8870`  | Instrument | Power Supply | `A-8870`     | `PXI-Rack-07` | OK               |
| `asset-switch-a1902` | Instrument | PXI Switch   | `A-1902`     | `PXI-Rack-07` | OK               |
| `asset-dmm-other`    | Instrument | NI PXI-4071  | `DMM-000199` | `PXI-Rack-12` | OK               |

The primary system must return four connected instruments and the DUT through
its supported asset relationship. The PXI-4071 asset must be searchable by
model and serial number. Its calibration record must be retrievable by ID and
include the due date.

For every traceability result, preserve the complete path:

```text
DUT serial 1234567
  -> test result TR-XYZ-OV-001
  -> test station cRIO0100101NIC
  -> system PXI-Rack-07
  -> instrument asset DMM-000184
```

The test result or test-step representation must expose the instrument asset ID
and measurement channel through a field supported by the Test Monitor API and
returned by the CLI/Nigel tool. A matching model name alone is insufficient and
must fail acceptance.

Required checks include:

```bash
slcli asset list --model PXI-4071 -w <WORKSPACE_ID> -f json --take 100
slcli asset get <DMM_000184_ID> -f json
slcli asset calibration <DMM_000184_ID> -f json
slcli testmonitor result get <TRACEABILITY_RESULT_ID> --include-steps -f json
```

## Products, DUTs, and test results

Create two products:

- `Product XYZ`, part number `XYZ-2025-001`, family `Power Electronics`.
- `Product ABC`, part number `ABC-2025-001`, with no results in the fixture.

Create at least these result groups for `Product XYZ`:

| Result group                                           | Minimum | Required fields                                                                                                                        |
| ------------------------------------------------------ | ------: | -------------------------------------------------------------------------------------------------------------------------------------- |
| Serial history for DUT `1234567`                       |       6 | Result ID, status, start time, program name, product/part number, station, system, and measurements.                                   |
| Failed Overvoltage results on station `cRIO0100101NIC` |       3 | Failed status, failure reason, timestamp, station, DUT serial, and product. At least two must fall in the selected two-quarter window. |
| Passing Overvoltage results                            |       3 | Passed status and measurements for comparison with failures.                                                                           |
| Traceability result                                    |       1 | Instrument asset ID `asset-dmm-pxi4071`, channel, and test step. This may overlap another group.                                       |
| Boundary/unknown result                                |       1 | A result outside the selected time window or for `Product ABC` to test filtering.                                                      |

Use fixed result dates spanning `2025-01-01` through `2025-06-30` for the
example's two-quarter query. Include numeric measurements, units, limits,
operator, failure category, and optional attachments. The result detail must
make it possible to answer both count and explanation questions without
inventing a failure cause from status alone.

Required checks include:

```bash
slcli testmonitor result list -w <WORKSPACE_ID> \
  --serial-number 1234567 -f json --take 100

slcli testmonitor result list -w <WORKSPACE_ID> \
  --part-number XYZ-2025-001 --status FAILED \
  --filter 'startedAt > DateTime(2025, 1, 1)' \
  --summary --group-by programName -f json
```

The expected serial history must contain at least six records. The failed
summary must contain at least three failures and exclude the boundary result.

## Feed and deployment state

Create one feed named `2025 Q1 Validation Feed` containing 12 packages,
including these names and versions:

- `NI-DAQmx 2025 Q1`
- `NI-DMM 2025 Q1`
- `NI-SCOPE 24.8`
- `SystemLink Client 2025.3`
- Eight additional packages from at least three package families

Each package must have a package identifier, display name, version, feed ID,
and enough metadata for a grouped summary. Package enumeration must be
available through the feed commands; package names in the feed description are
not sufficient.

Create two deployment states:

- `2025 Q1 validation`: populated with the four named packages above and at
  least two additional packages.
- `empty validation state`: a valid state with an empty package list.

Required checks include:

```bash
slcli feed list -w <WORKSPACE_ID> -f json --take 100
slcli feed get --id <FEED_ID> -f json
slcli feed package list --feed-id <FEED_ID> -f json
slcli state list -w <WORKSPACE_ID> -f json --take 100
slcli state get --id <STATE_ID> -f json
```

The feed and populated state must return package names and versions. The empty
state must remain available as a negative case.

## Tags and history

Create tag `ChamberTemp-07` with:

- Data type: numeric floating point.
- Units: `C`.
- Current value: `24.8`.
- Twelve or more samples at five-minute intervals over the preceding hour.
- Values ranging from `24.1` to `25.0` and increasing by approximately `0.5 C`.
- Tag metadata that identifies its source system as `PXI-Rack-07`.

The fixture must preserve the history in the tag service or in a documented
related table that the Nigel tag-history tool can read. `slcli 1.17.3` exposes
current-value lookup but does not expose a tag-history command, so this
requirement has two acceptance levels:

1. `slcli tag list` and `slcli tag get-value` return the tag and current value.
2. The SystemLink API or Nigel tool can retrieve the bounded history and
   calculate the range and trend.

If the installer cannot seed tag history through an authorized API, it must
return a structured `history: unsupported` provisioning result rather than
claiming that the tag example is complete.

## Specifications and compliance evidence

Create specification `Product XYZ 2025 Compliance` for `Product XYZ` with at
least these five conditions:

| Condition                              | Expected result    | Fixture outcome        |
| -------------------------------------- | ------------------ | ---------------------- |
| Overvoltage margin at high temperature | At least `10%`     | Gap: measured `7%`     |
| Leakage current at 5 V standby         | At most `2 mA`     | Gap: measured `3.4 mA` |
| Cold-start response time               | At most `100 ms`   | Gap: measured `142 ms` |
| Nominal output voltage                 | `12 V +/- 0.5 V`   | Pass                   |
| Thermal shutdown behavior              | Shutdown at `85 C` | Not run                |

Each condition must have an explicit status, expected limits, observed value
when available, evidence result IDs, and a human-readable gap explanation.
The product-to-specification relationship must be queryable by product ID.

Required checks include:

```bash
slcli spec list --product <PRODUCT_XYZ_ID> -f json
slcli spec get --id <SPEC_ID> -f json
```

Because the current CLI baseline exposes specification records but not a
single direct compliance-gap command, the installable example must provide one
of these supported paths:

- specification condition records already contain the compliance outcomes;
- a documented `slcli` query or notebook produces the three gaps; or
- the Nigel tool performs the bounded calculation from returned specs and
  result evidence.

A notebook or report may supplement the CLI path, but it must not replace the
underlying product, specification, condition, and evidence records.

## DataFrames, notebooks, and files

Create three populated DataFrame tables with stable names and schemas:

- `Overvoltage Results - XYZ`: timestamp, DUT serial, station, voltage,
  temperature, measured value, lower limit, upper limit, status.
- `Leakage Current Results - XYZ`: timestamp, DUT serial, station, current,
  temperature, measured value, upper limit, status.
- `Thermal Response Results - XYZ`: timestamp, DUT serial, station,
  temperature, response time, limit, status.

Each table must contain at least 12 rows, including passing and failing rows,
three timestamps in the selected analysis window, and enough numeric values to
reproduce the specification gaps. Table metadata must include workspace and
ownership marker.

Optionally create notebook `Product XYZ Compliance Calculation.ipynb` that
reads the three tables and writes a bounded compliance summary. If installed,
it must be deterministic, read-only, and return the three expected gaps using
SystemLink notebook output or a generated report file.

Optionally upload:

- `product-xyz-specification.csv` or equivalent source file.
- `product-xyz-compliance-report.json` containing the calculated gap summary.

Files are supporting evidence only. A successful fixture install must still
leave the resource relationships queryable through the relevant APIs.

## Install manifest and result contract

The example installer must emit JSON with these sections:

```json
{
  "example": "nigel-slcli-query-fixture",
  "version": "1.0.0",
  "workspace": { "name": "...", "id": "..." },
  "resources": {
    "created": [],
    "updated": [],
    "skipped": [],
    "failed": []
  },
  "logical_ids": {
    "system-pxi-rack-07": "server-id",
    "asset-dmm-pxi4071": "server-id",
    "result-tr-xyz-ov-001": "server-id"
  },
  "validation": {
    "required_relationships": [],
    "unsupported": []
  }
}
```

A resource is not considered installed when creation succeeds but a required
relationship fails. The installer must classify that relationship as failed
or unsupported and return a non-success result for the example installation.
This is especially important for system inventory, system-to-asset links,
result-to-instrument traceability, tag history, and specification evidence.

## Query acceptance matrix

The following outcomes are the minimum acceptance targets for the 14 examples.
Counts may be greater, but must be deterministic and documented in the example
manifest.

| Example                              | Required positive data                                                     | Required negative or safety case                                            |
| ------------------------------------ | -------------------------------------------------------------------------- | --------------------------------------------------------------------------- |
| 1. Software on current system        | Current system has four named packages with versions.                      | Unknown system returns not found; no version inferred from client metadata. |
| 2. Active alarms                     | Primary system has two active alarms with severity and related resources.  | Second system has zero active alarms.                                       |
| 3. PXI-4071 used for DUT measurement | DUT `1234567` links through a result and channel to `DMM-000184`.          | An unrelated PXI-4071 is not selected by model name alone.                  |
| 4. Serial history                    | `1234567` has at least six dated results.                                  | Unknown serial returns an empty result with no invented history.            |
| 5. Systems with NI-DAQmx             | Four systems match package name.                                           | `TestBench-44` is excluded because it has no DAQmx.                         |
| 6. Failed product measurements       | At least three failures for `XYZ-2025-001` in the selected window.         | Boundary/out-of-window and other-product results are excluded.              |
| 7. Feed software                     | Feed contains 12 enumerable packages with versions.                        | Empty or unknown feed returns a grounded empty/not-found result.            |
| 8. Response feedback                 | No fixture data required.                                                  | Covered by Nigel UI acceptance, not `slcli` provisioning.                   |
| 9. Deployment-state software         | `2025 Q1 validation` returns its populated package set.                    | `empty validation state` returns zero packages.                             |
| 10. Connected assets                 | Primary system returns the DUT and four instruments.                       | Asset from another system is not included.                                  |
| 11. Pending jobs                     | Primary system returns queued, running, and failed jobs.                   | A system with no jobs returns zero.                                         |
| 12. Tag current/history              | Current value `24.8 C`; bounded hour history shows range and upward drift. | History outside the one-hour window is excluded.                            |
| 13. Compliance gaps                  | Product returns three named open gaps with evidence.                       | Not-run condition is not reported as a failed measurement.                  |
| 14. DAQmx version filter             | Three systems have DAQmx later than `20.0`.                                | `20.0` or older and systems without DAQmx are excluded.                     |

For every positive result, acceptance must verify both the raw `slcli -f json`
output and the Nigel answer. Nigel answers must cite the resource names or IDs,
state the applied filters or time range, and distinguish zero results from
missing or unsupported data.

## Provisioning order

Use this order so server IDs can be resolved before dependent resources are
created:

1. Resolve or create the dedicated workspace.
2. Create products and the DUT assets.
3. Create systems and package inventories.
4. Create instrument assets and system-to-asset relationships.
5. Create test results, test steps, and instrument traceability.
6. Create alarms and jobs linked to the primary system.
7. Create feed, packages, and deployment states.
8. Create tag and history samples.
9. Create specifications, condition outcomes, and evidence links.
10. Create DataFrames, notebooks, and supporting files.
11. Run post-install queries and emit the logical-ID map and validation result.

The installer should retry idempotently after a partial failure, but it must
not silently skip a required relationship because the parent resource already
exists.

## Definition of done

The example is ready for use when:

- A clean workspace can be provisioned with one `slcli example install`
  command and produces a complete JSON manifest.
- Reinstalling produces no duplicate logical resources or history samples.
- Cleanup removes only resources owned by the example.
- All required systems, packages, assets, results, feed packages, state
  packages, jobs, alarms, tags, specifications, condition evidence, and
  populated tables are retrievable in the target workspace.
- The 14 `slcli` acceptance targets above pass, except for explicitly declared
  current CLI limitations such as tag-history command availability.
- The same workspace supports a repeatable Nigel prompt run with positive and
  negative cases for every query that is within Nigel's supported tool scope.
- Any unsupported API relationship is reported in the install manifest and in
  the Research validation document; the fixture never masks the limitation
  with duplicated or inferred data.
