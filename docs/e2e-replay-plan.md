# Migration E2E Record/Replay

Usage: [Record and Replay Migration Tests](../tests/e2e/README.md#record-and-replay-migration-tests).
Implementation: `tests/replay/`.

## Problem

The SLS→SLE migration E2E tests need a SystemLink Server (SLS) source and a
SystemLink Enterprise (SLE) destination. The shared SLS demo server is being
decommissioned, and a local SLS VM is slow to provision and unreliable, so it
can't gate pre-submit. We still want the tests to exercise real server behavior,
not invented fakes.

Constraints:

- **Real data only.** Every replayed response must come from a real server.
- **Reviewable.** Tapes live in a public repo, so they must be readable, diffable,
  free of credentials, and limited to test-owned data.
- **Editable.** Someone can hand-edit a tape, for example to grow a large case.
- **Cross-process.** Migrations run in Prefect worker processes, so in-process
  `requests` mocking doesn't see every call.
- **No leaked state.** Workspaces can't be deleted on the dev tier, so tests may
  only use a fixed set of workspace names.

## Proposal

A small HTTP record/replay engine (`tests/replay/`) that sits in front of each
side:

- **Per-side modes.** The source and destination each run `live`, `record`, or
  `replay`. Pre-submit default: replayed source, live destination. Retiring SLS
  doesn't block us, and SLE is still tested for real.
- **Local fake server.** In replay, slcli profiles point at a localhost HTTP
  server that serves the tape. Every process, Prefect workers included, uses it
  unchanged. In record, the same server proxies to the real upstream and writes
  what it sees.
- **YAML tapes.** One tape per test module per side:
  `request: "METHOD /path?query"`, an optional body, and the response.
  - Headers and credentials are dropped, and the upstream URL is stored as
    `{{base_url}}`.
  - Optional `note:` fields explain hand edits.
- **Matching.** Method, path, query (order-insensitive), and body. Volatile
  migration timestamps are masked. A miss returns HTTP 598 and fails the test
  with a list of the unmatched requests.
- **Recorded generated values.** The product's random migration IDs are recorded
  in the tape's `generated:` section and played back in replay. The product's
  UUIDv4 validation stays intact, with no fake IDs.
- **Determinism from scoping, not faking.**
  - Tests use fixed workspaces (`E2EWorkspace`) and ownership-filtered cleanup,
    and discovery is limited to fixture workspaces.
  - Derived IDs (Test Monitor steps) are uuid5 of their inputs.
  - Pagination stops on short pages.
- **Safe recording.** A module's tape is only rewritten if all of its tests
  passed.
- **Disclosure.** Source tapes are committed. Destination tapes are gitignored
  to limit accidental disclosure of test tier data.

## Alternatives considered

| Option | Why not (for now) |
| ------ | ----------------- |
| Keep a shared or local SLS server | Being decommissioned; the VM is flaky and slow to set up. |
| `vcrpy` / `pytest-recording` | In-process only, so it misses Prefect workers. A proxy wrapping it was prototyped side by side. It worked, but it added a dependency and an extra layer, and its cassette format is noisier to read and edit. |
| `responses` / `requests-mock` | Hand-written fakes break the real-data constraint and have the same in-process limit. |
| Replay both sides only | Supported, but SLE is available and live testing there catches regressions. |

## Risks and follow-ups

- Pre-existing data in the source Default workspace can still show up in some
  queries and cause non-deterministic tapes.
- Next steps:
  - Move other E2E SLS modules onto tapes.
  - Consider recording timestamps instead of masking them.
