# Managed-Client Test Minion Implementation Plan

**Status:** Local implementation complete; live interoperability gated
**Date:** September 18, 2026
**Target repository:** `systemlink-cli`

## Decision summary

Add an opt-in Python test client that implements only the minimum SystemLink
Salt minion lifecycle needed by integration tests. The implementation will be
independent of the official NI client source and will not replace the official
managed client.

The existing `slcli` REST client remains the control plane for selecting an
environment, approving a pending key, starting server-side jobs, and observing
systems and jobs. The new test minion is a separate data-plane component that
owns Salt sockets, Salt identity, protocol state, deterministic job handlers,
and reconnect behavior.

This gives tests a real connected managed system without requiring native NI
System API binaries, an installer, or an operating-system service. It does not
make arbitrary third-party Salt clients production-supported.

## Goals

- Provide a Python API that can run a foreground test minion on macOS, Linux,
  and Windows.
- Create or load an isolated RSA minion identity and stable minion ID.
- Complete the pending-key, approval, authentication, publish, presence, job,
  return, reconnect, and cleanup lifecycle.
- Use the existing `slcli` profile and REST authentication model for test
  orchestration.
- Return deterministic fixtures for approved test jobs instead of executing
  arbitrary local commands.
- Make every lifecycle phase observable through structured state and logs that
  redact credentials and private key material.
- Prove behavior first against protocol fixtures and a local SaltMaster test
  environment, then gate live SystemLink tests by environment and credentials.

## Non-goals

The first implementation will not provide:

- NI System API or native device behavior.
- The official `MinionAgent` or any copied official-client source.
- mDNS discovery, grains, beacons, package management, feed installation,
  licensing, or product-specific Salt modules.
- A Windows service, Linux systemd unit, macOS launchd agent, or installer.
- Arbitrary Salt function execution or a general-purpose remote shell.
- A virtual-system shortcut presented as a connected managed system.
- A production support claim for any operating system until the complete
  lifecycle has passed against the supported deployment.

## User-facing shape

Implement the Python library before adding a CLI command. The library should
make the lifecycle usable from pytest, standalone Python scripts, and later a
Click wrapper without coupling protocol state to terminal output.

Example shape:

```python
from slcli.managed_client import TestMinion

with TestMinion(
    master="systemlink.example.com",
    minion_id="slcli-test-001",
    state_dir=".test-state/slcli-test-001",
) as minion:
    minion.start()
    minion.wait_for_state("pending", timeout=30)

    # A separate REST controller approves the pending public key here.
    approve_pending_key(minion.minion_id)

    minion.wait_for_state("connected", timeout=60)
    assert minion.connected
```

The exact public names are provisional. The implementation should expose typed
state, events, timeout errors, and cleanup methods rather than require callers
to parse log text.

The implementation provides an explicit test-only CLI group with foreground
execution and scoped local-state reset:

```text
slcli managed-client run
slcli managed-client reset
```

The command must remain an explicit test feature and must not be confused with
the existing `slcli system` REST commands or with a virtual system.

## Responsibility boundaries

| Concern | Existing `slcli` REST layer | Test minion | SystemLink/SaltMaster |
| --- | --- | --- | --- |
| Select environment | Yes | Uses supplied configuration | No |
| Store API key or OAuth credentials | Yes | No | No |
| Generate Salt RSA identity | No | Yes | No |
| Submit public key | No | `_auth` request | Receives and stores key |
| Approve or reject key | REST adapter | No | Systems Management |
| Request and publish sockets | No | Yes | Salt transport |
| Presence and connection state | Observes through REST | Publishes through Salt lifecycle | Tracks state |
| Receive and return jobs | Queries jobs | Receives and handles jobs | Dispatches jobs |
| Test cleanup | Removes server resources | Stops and clears local state | Removes server-side Salt data |

API credentials and Salt identity must remain separate. A successful REST
request proves neither Salt authentication nor managed-client presence.

## Proposed package layout

Create a focused package under `slcli/managed_client/`:

```text
slcli/managed_client/
    __init__.py          # public TestMinion API
    models.py             # typed configuration, states, events, and errors
    crypto.py             # vetted-library Salt crypto adapter
    protocol.py           # MessagePack frames and Salt envelopes
    transport.py          # request/publish socket lifecycle
    minion.py             # authentication and reconnect state machine
    handlers.py           # deterministic, allowlisted test job handlers
    state.py              # isolated state-directory persistence and cleanup

tests/unit/
    test_managed_client_crypto.py
    test_managed_client_protocol.py
    test_managed_client_state.py
    test_managed_client_handlers.py
    test_managed_client.py
```

Keep the package independent of Click and terminal formatting. Reuse existing
profile and HTTP helpers only in the REST orchestration layer. Do not make the
base CLI import Salt transport code during normal REST command startup.

## Protocol implementation

The protocol must be implemented from observed behavior in the existing
SaltMaster and fake-minion test implementations, not from an assumed generic
Salt contract. The first protocol spike must record the exact wire behavior
before production code is written.

### Required lifecycle

1. Generate or load an RSA key pair and minion ID.
2. Load the configured master endpoint and request-channel settings.
3. Open the request channel and send the Salt `_auth` request.
4. Report a pending state when the public key is not approved.
5. Retry authentication after the REST controller approves the key.
6. Decrypt the master-provided session material.
7. Connect to the publish channel returned by authentication.
8. Send the encrypted minion identity/token required for publish registration.
9. Receive jobs, dispatch only allowlisted test handlers, and send `_return`
   payloads over the request channel.
10. Reconnect after a socket, master, or publish-channel interruption while
    retaining the same identity.
11. Stop sockets, cancel retry tasks, and optionally remove isolated state.

### Wire and cryptography requirements

The implementation must verify, with test vectors or a local protocol oracle:

- MessagePack encoding and framing details.
- Request-channel and publish-channel message envelopes.
- Protocol-version negotiation and version-specific auth behavior.
- AES-192-CBC encryption and HMAC-SHA256 integrity protection.
- RSA OAEP session-secret decryption.
- RSA token/signature operations used by the target Salt protocol, including
  the X9.31 paths used for v3 authentication signatures and publish tokens.
- Nonce, JID, minion ID, and job-return field requirements.
- Publish registration and presence behavior.

Use a maintained cryptography library. Do not implement cryptographic
primitives directly. The repository already declares `cryptography`; the
MessagePack dependency and any primitive not available through the current
dependency set require a separate dependency review before being added. The
current `cryptography` API does not expose RSA X9.31 padding, and the local
SaltMaster uses a native X9.31 NIF. Genuine v3 live interoperability remains
blocked until that requirement has an approved implementation or is explicitly
removed from the acceptance contract. The approved implementation direction is
an isolated provider adapter over OpenSSL `libcrypto` using `ctypes`: OpenSSL
defines the Salt-compatible `RSA_X931_PADDING` operation on macOS, Linux, and
Windows, while the adapter owns library discovery, symbol validation, and
fail-closed behavior. M2Crypto and Botan were evaluated, but M2Crypto does not
provide a complete cross-platform wheel strategy and Botan requires a separate
externally installed shared library. Do not substitute PKCS#1 v1.5 or PSS.

The provider is not accepted on the basis of a local sign/verify round trip
alone. It must match the Salt oracle for both X9.31 private-key signing and
public-key recovery on every supported OS and in the packaged executable.

The first implementation targets protocol v3. Confirm the target deployment's
wire behavior during the protocol spike before accepting live-test results,
but do not add v1 or v2 negotiation to the first milestone. Keep
version-specific code behind an adapter so older-version compatibility can be
added only when a real test requires it.

## State and security model

Each test minion must use an explicit state directory scoped by environment,
profile, and minion ID. Persist only what is needed to reconnect:

- Minion ID.
- RSA private and public key.
- Master identity or key material required by the protocol.
- Minimal protocol metadata needed for recovery.

Requirements:

- Never store API keys in the Salt state directory.
- Never log private keys, API keys, session secrets, or complete encrypted
  payloads.
- Use restrictive file permissions on POSIX and equivalent user-only ACLs on
  Windows.
- Make reset and destructive cleanup explicit.
- Detect a changed master identity and require an explicit reset or approval
  decision instead of silently trusting the new master.
- Scope cleanup to the test minion; do not delete shared Salt or profile state.
- Ensure `stop()` and context-manager cleanup run when job handling fails.

The handler registry must be an explicit allowlist. Initial handlers should be
small deterministic fixtures such as:

- Return a successful fixed value.
- Return a configured fixture payload.
- Return a controlled failure with a known return code.
- Simulate a refresh operation without changing the host.

Unknown functions should return a deterministic unsupported-operation result.
They must not fall through to local shell, Python evaluation, or arbitrary Salt
execution.

## REST orchestration

Keep REST orchestration separate from the minion process. Add a small adapter
only after confirming the endpoint contract and permissions for the target
SystemLink editions. It should use existing profiles and common API error
handling rather than duplicate authentication.

The adapter may need to support:

- Querying systems and pending keys.
- Approving, rejecting, or deleting the test minion key.
- Polling for `CONNECTED`, `DISCONNECTED`, and terminal job states.
- Creating and querying server-side jobs for the test minion.
- Removing the system and associated server-side test data.

Each operation needs a timeout, a bounded polling interval, and a useful error
that identifies whether the failure occurred in REST authentication, Salt
authentication, publish registration, presence, job dispatch, or cleanup.

Do not create a virtual system as part of the managed-client path. A separate
virtual-system fixture can remain useful for REST-only tests, but it must have
different names, APIs, and acceptance tests.

## Implementation phases

### Phase 0: Protocol and contract spike

Deliverables:

- Confirm the target SaltMaster uses protocol v3 and record its exact
  frame/envelope behavior.
- Capture minimal request, auth, publish, job, and return fixtures from a
  local protocol oracle or a checked-in fixture server that reproduces the
  target v3 behavior.
- Confirm the key-approval REST endpoint, permissions, and response states.
- Determine whether the current dependency set can provide every crypto
  primitive without unsafe custom code.
- Decide whether the X9.31 operations used by the target v3 deployment can be
  supplied by an approved library or whether the live acceptance scope must be
  reduced.
- Add or select a deterministic Python fixture server for normal CI; keep the
  Skyline SaltMaster/fake-minion harness as an optional cross-repository
  interoperability tier.
- Decide whether MessagePack should become a direct runtime dependency and
  whether it belongs in the optional `managed-client` extra.

Exit criteria:

- A documented wire contract and test vectors exist.
- No protocol assumption remains that is contradicted by the local server
  implementation.
- Dependency additions and their licensing/support implications are known.

### Phase 1: Pure protocol components

Implement `models.py`, `crypto.py`, and `protocol.py` with no sockets or Click.
Add unit tests for valid and invalid frames, envelope integrity, nonce handling,
key loading, and version-specific schemas.

Exit criteria:

- Unit tests pass with deterministic vectors.
- Malformed, truncated, tampered, and unsupported messages fail safely.
- Secrets do not appear in exception messages or test output.

### Phase 2: Transport and lifecycle state machine

Implement request/publish connections, authentication, pending state, publish
registration, job receipt, job return, reconnect, timeout, and cleanup.

Exit criteria:

- A local protocol oracle can drive the client from new to pending to connected.
- A dropped request or publish socket triggers bounded reconnect attempts.
- A reconnect preserves the minion identity and does not create a duplicate
  identity.
- Shutdown is deterministic and leaves no background thread or task.

### Phase 3: Deterministic job handlers

Implement the allowlisted fixture handlers and the exact job-return schema.
Include controlled success, failure, unsupported-function, and malformed-job
cases.

Exit criteria:

- Every supported fixture produces a stable return payload.
- Unknown or malformed jobs cannot execute arbitrary local behavior.
- Job failures are represented in the protocol result without killing the
  minion unless the protocol requires it.

### Phase 4: REST approval and integration harness

Add a test-oriented REST adapter using the existing profile and request
infrastructure. Build an orchestration fixture that starts the minion, waits
for pending state, approves its key, waits for connected presence, dispatches a
fixture job, verifies the result, and cleans up.

Exit criteria:

- The complete lifecycle passes against a deterministic local fixture server;
  interoperability coverage against the Skyline SaltMaster-compatible
  environment is separately selectable.
- The same test can run against a configured SystemLink environment without
  embedding credentials in source control.
- REST-only, virtual-system, and managed-client tests are independently
  selectable.

### Phase 5: Click wrapper and packaging

The stable local Python API now has an explicit `managed-client` command group
with foreground `run` and scoped `reset` commands. The command imports the
managed-client implementation lazily, keeps REST approval separate, and fails
closed when the required v3 X9.31 operation has no approved adapter.

The managed-client dependency remains optional, and no service managers or
installers are included. PyInstaller and other distribution paths should be
evaluated only after the foreground lifecycle is reliable on each claimed OS.

Do not add service managers or installers in this phase. PyInstaller and other
distribution paths should be evaluated only after the foreground lifecycle is
reliable on each claimed OS.

## Test matrix and acceptance criteria

### Unit tests

- Key generation, loading, and stable identity.
- MessagePack frame parsing and rendering.
- Clear and encrypted envelope handling.
- Authentication response parsing for the selected protocol version.
- Job dispatch and exact return payloads.
- State transitions, retry limits, timeout errors, and cleanup.
- File permission and secret-redaction behavior where the platform permits it.

### Local integration tests

Validate the following lifecycle against the local SaltMaster-compatible
environment:

1. Clean start creates a pending key.
2. Key approval leads to authenticated publish registration.
3. The system becomes connected and presence timestamps advance.
4. A server-side fixture job reaches the test minion and returns the expected
   result.
5. A temporary connection interruption recovers with the same identity.
6. Stale presence becomes disconnected according to the server contract.
7. Stop and removal leave no stale process, socket, or server-side test state.
8. Clearing state and registering again is deterministic.

### Live environment tests

Gate these tests behind explicit configuration and credentials. They must verify
the same lifecycle against a supported SystemLink deployment and record the
SystemLink edition, SaltMaster version, protocol version, and operating system.

### Operating-system matrix

- Linux: first implementation and CI target if the local SaltMaster harness is
  available.
- Windows: foreground process and state/ACL validation before service work.
- macOS: foreground process only until registration, presence, jobs, reconnect,
  and cleanup pass against a real supported deployment.

Passing REST tests on macOS does not establish managed-client support there.

## Failure diagnostics

Expose structured phase information for at least:

```text
INITIALIZING
AUTHENTICATING
PENDING_APPROVAL
APPROVED_RECONNECTING
CONNECTING_PUBLISH
CONNECTED
RUNNING_JOB
RECONNECTING
STOPPING
FAILED
```

Every failure should include a phase, safe endpoint information, retry count,
and actionable next step. Examples:

- REST authentication failed: check the selected profile and permissions.
- Salt authentication pending: approve the public key through the REST
  controller.
- Publish connection failed: check the master-provided port and firewall.
- No presence: inspect publish registration and server-side stale timeout.
- Job timed out: distinguish dispatch failure from handler failure.
- Master identity changed: reset the isolated state explicitly.

Do not treat a process that is alive as connected. Report process health and
SystemLink connection state independently.

## Risks and mitigations

| Risk | Mitigation |
| --- | --- |
| Incomplete Salt compatibility | Use exact local protocol fixtures and a real integration gate before broadening support. |
| Incorrect crypto implementation | Use maintained libraries, test vectors, and a dependency spike before coding. |
| API key mistaken for Salt identity | Keep REST and Salt phases separate in the API, logs, and documentation. |
| Arbitrary code execution through test jobs | Use an allowlisted deterministic handler registry. |
| Duplicate or stale identities | Persist stable per-run identity and provide explicit reset. |
| TLS verification bypass | Reuse existing trust configuration and preserve certificate verification. |
| Cross-platform filesystem differences | Abstract state permissions and test POSIX and Windows behavior separately. |
| Unsupported macOS managed mode | Keep it experimental until the complete live lifecycle passes. |
| Dependency or package-size growth | Keep the managed-client package optional and review every new runtime dependency. |
| Cleanup removes shared state | Scope state and server cleanup by profile and minion ID. |

## Resolved implementation decisions

- **Protocol:** Target v3 for the first implementation. Do not implement v1/v2
  negotiation until a real acceptance target requires it. Treat X9.31 as an
  explicit live-interoperability gate.
- **Acceptance sequence:** Prove the lifecycle against a local protocol oracle
  first, then gate live acceptance on one explicitly named SystemLink
  deployment.
- **Packaging:** Ship the Python API behind an optional `managed-client` extra
  so normal REST users do not pay managed-client transport dependency costs.
  MessagePack remains subject to dependency approval.
- **REST permissions:** Use `system-unmanaged:Read` for key polling,
  `system:Create` for the management route and pending-key approval, and
  `system:Delete` for cleanup of an already-approved system in its current
  workspace. Key listing is organization-scoped and does not return workspace
  IDs; approval assigns the destination workspace.
- **Local harness:** Add a deterministic Python fixture server for normal CI;
  the Skyline fake-minion/SaltMaster harness is optional cross-repository
  coverage rather than an existing `systemlink-cli` CI dependency.
- **Operating systems:** Make Linux the first CI and acceptance target. Keep
  Windows and macOS experimental and foreground-only until the complete
  lifecycle passes on each OS.

## Research questions before implementation

1. Which named SystemLink deployment, edition, SaltMaster build, and operating
  environment will serve as the first live acceptance target, and which
  team-owned credentials and reset procedure are available for it?
2. Which REST API operation, request and response schema, workspace scope, and
  least-privilege permission set are required to list, approve, reject, and
  remove the v3 test-minion key in that target deployment?
3. Does CI have access to a SaltMaster-compatible fake-minion/SaltMaster
  harness that reproduces the target v3 wire contract, or should this
  repository add a small deterministic fixture server covering authentication,
  publish registration, jobs, returns, reconnect, and cleanup?
4. Can the currently declared `cryptography` package plus an approved
  MessagePack package implement every v3 primitive and framing requirement
  without custom cryptography, and what dependency, license, and package-size
  evidence supports that choice?

## Definition of done

The first implementation is complete when:

- The Python API runs a deterministic test minion without official-client
  source or native NI binaries.
- Pending-key approval, connected presence, fixture job execution, reconnect,
  and cleanup pass in the local integration environment.
- REST credentials and Salt private keys are isolated and redacted.
- Unit and integration tests cover success, failure, malformed input, timeout,
  reconnect, and cleanup paths.
- Linux, Windows, and macOS support status is documented from actual test
  evidence rather than inferred from Python portability.
- The base REST CLI still starts without requiring managed-client configuration.
- Any new dependency, public command, or packaging change has been reviewed
  under the repository's normal contribution process.