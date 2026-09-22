# Managed-Client Research Answers

**Status:** Research complete for the REST, CI-harness, and dependency questions
**Target repository:** `systemlink-cli`

This note records the evidence used to refine the managed-client test-minion
plan. The sources are the current `systemlink-cli` checkout and the current
Skyline checkout; source behavior is not treated as a production compatibility
claim for every SystemLink deployment.

## Executive conclusions

1. The Systems Management key API is organization-scoped for listing and
   workspace-scoped for approval and managed-system authorization. A full
   test-minion lifecycle needs `system-unmanaged:Read` to inspect keys,
   `system:Create` to approve a pending key, and `system:Delete` to remove an
   already-approved system from its current workspace. The management route
   itself also requires `system:Create`, even for reject and delete actions.
2. `systemlink-cli` has no checked-in SaltMaster or fake-minion harness and its
   E2E tests target configured SystemLink environments. The Skyline harness is
   reusable only through an additional cross-repository checkout and its
   Docker/Elixir setup. A small deterministic fixture server should therefore
   be added for normal Python CI, with optional acceptance coverage against the
   Skyline harness or a named live deployment.
3. `cryptography` covers the standard primitives used by the protocol, but it
   does not expose RSA X9.31 padding. The current SaltMaster implementation
   uses X9.31 for the v3 authentication signature and publish token paths via
   a native NIF on non-Windows systems. Full genuine v3 interoperability is
  therefore blocked until an approved provider or an approved scope reduction
  is identified. MessagePack is not currently a direct or locked dependency.
4. No maintained Python package found provides X9.31 with self-contained,
  cross-platform wheels suitable for this CLI. M2Crypto is OpenSSL-based and
  has recent Windows wheels, but its own documentation calls it maintenance
  mode and its distribution is not a complete macOS/Linux wheel strategy.
  Botan's Python binding supports the needed native-library model, but it
  loads an externally installed shared Botan library and has no normal PyPI
  runtime package. The practical provider is therefore a small, isolated
  `ctypes` adapter over the OpenSSL `libcrypto` already shipped or provisioned
  with each supported CLI build.

## 1. Systems Management key API

### Routes and schemas

The controller in
`SystemsManagementService/SystemsManagementService.WebApi/Controllers/SystemController.cs`
defines these routes:

| Operation | Request | Response | Route-level permission |
| --- | --- | --- | --- |
| `GET /nisysmgmt/v1/get-systems-keys` | None | `GetSystemsKeysResponse` | `system-unmanaged:Read` |
| `POST /nisysmgmt/v1/get-systems-keys` | `{ "systemIds": ["..."] }` | `GetSystemsKeysResponse` | `system-unmanaged:Read` |
| `POST /nisysmgmt/v1/manage-systems-keys` | `ManageKeysRequest` | `204`, or `200` with partial errors | `system:Create` |

`GetSystemsKeysResponse` contains four optional dictionaries keyed by system
ID. Their values are the public key strings:

```json
{
  "systemsPending": { "system-id": "PUBLIC KEY" },
  "systemsDenied": { "system-id": "PUBLIC KEY" },
  "systemsApproved": { "system-id": "PUBLIC KEY" },
  "systemsRejected": { "system-id": "PUBLIC KEY" }
}
```

The response model says a category can be omitted when it has no entries. The
four states mean pending approval, denied because the connecting key does not
match the stored key, approved, and explicitly rejected.

`ManageKeysRequest` has a deprecated `isAsync` Boolean and a `keyActions`
array. Each action has:

```json
{
  "id": "system-id",
  "action": "ACCEPT | REJECT | DELETE",
  "key": "optional public key",
  "workspace": "optional workspace id"
}
```

The optional `key` is checked against the system ID before the action is
performed. The controller remarks state that acceptance adds the system to the
specified workspace and that rejection or deletion disconnects it.

### Scope and least privilege

The `GET` route passes only `AuthResult.Org.Id` to
`MinionsFacade.GetMinionsKeys`, which calls the Salt API with `minions: ["*"]`.
The keyed `POST` route still passes the organization ID and only narrows the
requested system IDs. There is no workspace field in either listing request,
and the response does not return workspace IDs. The API boundary is therefore
organization-scoped and key-state filtered, not workspace-filtered.

For management, the request workspace is validated and is filled from the
authenticated default workspace when omitted. The action-specific checks in
`MinionsFacade.ManageSystemsKeys` are important:

- `ACCEPT` is authorized with `system:Create` in the destination workspace.
- `REJECT` or `DELETE` for an existing managed system is authorized with
  `system:Delete` in that system's current workspace.
- Moving an existing system while accepting it requires delete permission in
  the old workspace as well as create permission in the new workspace.
- The HTTP route requires `system:Create` for every management request. The
  integration tests cover pending-key reject/delete behavior under that route
  permission; do not infer that `system:Delete` alone can call the route.

The minimum API-key policy for the complete test lifecycle is consequently:

- `system-unmanaged:Read` to list or poll key states.
- `system:Create` in the test workspace to approve a pending key.
- `system:Delete` in the current test workspace to clean up after approval,
  in addition to the route's `system:Create` requirement.

The relevant source evidence is in:

- `SystemsManagementService/SystemsManagementService.WebApi/Controllers/SystemController.cs`
  (`get-systems-keys` and `manage-systems-keys` routes).
- `SystemsManagementService/SystemsManagementService.WebApi/AppServices/MinionsFacade.cs`
  (`ManageSystemsKeys`, `PartitionUnauthorizedKeyActions`, and
  `GetMinionsKeys`).
- `SystemsManagementService/SystemsManagementService.Infrastructure/Auth/AuthorizationActions.cs`.
- `SystemsManagementService/Tests/SystemsManagementService.Integration.Tests/GetAllSystemsKeysTest.cs`.
- `SystemsManagementService/Tests/SystemsManagementService.Integration.Tests/GetSystemsKeysTest.cs`.
- `SystemsManagementService/Tests/SystemsManagementService.Integration.Tests/ManageSystemKeysTest.cs`.

## 2. CI harness availability

The `systemlink-cli` E2E framework is configured around a real SystemLink
endpoint, API key, workspace, timeout, and cleanup setting. Its documented
configuration is in `tests/e2e/README.md`, and the fixtures in
`tests/e2e/conftest.py` resolve SLE/SLS endpoint configurations. No checked-in
workflow or test fixture in that repository starts SaltMaster, fake-minion, or
the Salt request/publish ports.

Skyline does contain a reusable reference harness:

- `SaltMaster/apps/fake_minion` implements fake-minion lifecycle behavior and
  has v1, v2, and v3 communication-version paths.
- `SaltMaster/apps/salt_master` implements the matching server handlers.
- `SaltMaster/docker-compose.yml` and `SaltMaster/docker-compose.local.yml`
  provide Docker-based local startup.
- `SaltMaster/README.md` and `SaltMaster/apps/fake_minion/README.md` document
  the Elixir applications.

That harness is not directly available to `systemlink-cli` CI. Reusing it
would require checking out Skyline, installing/building Elixir dependencies,
starting Docker Compose, and supplying the harness configuration. It also
includes a native RSA crypto build on non-Windows systems, which makes it a
larger and less portable default CI dependency.

### Recommendation

Add a deterministic, checked-in Python fixture server for the first local
integration tier. It should implement only the v3 request/auth/publish/job/
return/reconnect behavior needed by the test minion and should expose explicit
state assertions rather than attempting to emulate all of Salt. Keep a second,
optional acceptance tier for the Skyline harness or one named SystemLink
deployment. This gives ordinary Python CI a stable oracle without treating a
cross-repository Docker setup as a hidden dependency, while preserving a real
interoperability gate.

## 3. Crypto, MessagePack, license, and size evidence

### Primitive mapping

The current SaltMaster source maps the protocol primitives as follows:

| SaltMaster operation | Python `cryptography` status |
| --- | --- |
| AES-192-CBC with 16-byte IV | Supported by the cipher primitives API |
| HMAC-SHA256 | Supported by the HMAC API |
| RSA public-key encryption/decryption with OAEP | Supported by `OAEP` |
| RSA signatures | Supported through the RSA signing/verification APIs, subject to matching the exact hash/padding contract |
| RSA private-key encryption and public-key decryption with X9.31 | No public `cryptography` padding API |

The v3 auth handler is structurally similar to v2 and includes a nonce. The
accepted response encrypts the shared AES secret with RSA OAEP, but it also
contains a master secret signature produced by
`SaltCrypto.encrypt_rsa_private`. Publish registration sends a token produced
by the same private-key X9.31 operation. The server verifies that token with
public-key X9.31.

`SaltMaster/apps/salt_crypto/lib/rsa_cryptolib.ex` delegates those X9.31
operations to `salt_rsa_crypto_lib`; `SaltMaster/apps/salt_crypto/mix.exs`
builds that native library with `make` on non-Windows platforms. This is not a
primitive supplied by Python `cryptography`, and adding a hand-rolled RSA
padding implementation would violate the no-custom-crypto requirement.

### Dependency and package evidence

- `systemlink-cli/pyproject.toml` directly declares
  `cryptography >=49.0.0`.
- `systemlink-cli/poetry.lock` currently locks `cryptography` at `50.0.1`.
- `msgpack` is not declared directly and has no package block in the current
  lock file. It must be reviewed as a new direct runtime dependency rather
  than assumed to be available through the existing dependency graph.
- A cached `msgpack 1.1.2` macOS arm64 wheel is 85,064 bytes and declares
  `License-Expression: Apache-2.0`.
- A cached `cryptography 50.0.1` macOS arm64 wheel is 4,010,153 bytes and
  declares `License-Expression: Apache-2.0 OR BSD-3-Clause`. The installed
  distribution is larger than the wheel because it is expanded and includes
  compiled/runtime metadata; the wheel size is the useful packaging comparison.

The size measurements are local wheel evidence, not a guarantee for every
Python version and operating-system tag. License metadata is also not the same
as NI dependency approval; the MessagePack package still needs the repository's
normal dependency and legal review.

### Third-party X9.31 options

| Option | Exact X9.31 capability | Cross-platform distribution | Decision |
| --- | --- | --- | --- |
| `cryptography` | No public X9.31 padding object. It exposes PSS and PKCS#1 v1.5 only. | Strong: maintained project with bundled OpenSSL wheels for the supported Python platforms. | Keep for OAEP, AES, HMAC, and ordinary RSA; it cannot satisfy the v3 X9.31 gate. |
| PyCryptodome | Its documented RSA signature APIs expose PSS and PKCS#1 v1.5, not X9.31. | Strong wheel coverage, including Windows, macOS, and Linux. | Reject: good packaging does not compensate for the missing wire primitive. |
| M2Crypto | OpenSSL/SWIG binding with low-level RSA access, so X9.31 may be reachable through its OpenSSL layer. | Recent PyPI wheels are Windows-focused; other platforms depend on a source build and local OpenSSL. The project describes itself as maintenance mode and recommends `cryptography` for new applications. | Reject as the CLI runtime dependency: incomplete wheel story and higher ABI risk. |
| Botan Python binding | Botan implements EMSA-X9.31 and the binding's `PKSign` accepts named native padding schemes. | The binding is a Python file that searches for `botan-3.dll`, `libbotan-3.dylib`, or `libbotan-3.so`; the shared Botan library must be installed or bundled separately. Botan builds on macOS, Linux, and Windows, but this is an additional native packaging project. | Keep as a fallback/reference provider, not the first dependency. |
| Direct OpenSSL `libcrypto` via `ctypes` | OpenSSL defines `RSA_X931_PADDING` and the Salt-compatible `RSA_private_encrypt` / `RSA_public_decrypt` operations. | OpenSSL is available on all target OSes, but library discovery and bundling must be implemented for each packaged build. The provider can use the same OpenSSL family already used by `cryptography` only if symbol/loading compatibility is verified. | Recommended, behind a provider interface and capability check. |

The OpenSSL low-level RSA functions are deprecated as of OpenSSL 3.0, but the
X9.31 padding constant and operations remain present in the compatibility API.
The adapter must therefore pin and test the supported OpenSSL ABI, fail closed
when the symbols are unavailable, and never fall back to a different padding
scheme. This is a better interoperability tradeoff than adding a second full
crypto library solely to reach one legacy Salt primitive.

The provider acceptance test must sign and recover the same digest bytes with a
Salt-compatible oracle on macOS, Linux, and Windows. It must exercise both
private-key X9.31 signing and public-key X9.31 recovery, PEM key loading,
OpenSSL 1.1-compatible and OpenSSL 3.x library layouts, and the packaged
PyInstaller executable where applicable. A fixture-only round trip is not
enough to approve live interoperability.

### Decision

Use MessagePack only behind the managed-client feature boundary and add it as a
direct dependency only after approval. Use `cryptography` for the standard
primitives. Add a small OpenSSL `libcrypto` provider behind the existing crypto
adapter interface for X9.31, with explicit per-platform loading and a hard
failure when the required symbols are absent. Do not claim genuine v3 live
interoperability until the provider passes the cross-platform Salt oracle test
and the packaged executable test. A fixture server may test the rest of the
state machine, but it cannot remove this live-interop blocker.

## Plan changes

The implementation plan should therefore record these resolved decisions:

- Key listing is organization-scoped; approval targets a workspace; cleanup of
  an approved system needs `system:Delete` in addition to the management route's
  `system:Create` permission.
- Normal CI needs a deterministic Python fixture server. Skyline SaltMaster is
  an optional cross-repository interoperability tier, not an existing
  `systemlink-cli` CI fixture.
- MessagePack is a new dependency subject to approval. `cryptography` does not
  satisfy the full v3 crypto contract because X9.31 is not exposed publicly.
- Protocol v3 remains the first target. The approved direction for the X9.31
  decision is a provider interface backed by OpenSSL `libcrypto` via `ctypes`,
  with M2Crypto and Botan retained as evaluated alternatives rather than runtime
  dependencies.