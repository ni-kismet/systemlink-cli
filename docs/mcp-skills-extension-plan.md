# Hosting the bundled slcli skill over MCP

**Decision date:** 2026-09-16
**Status:** Implemented
**Scope:** Publish the existing `slcli` Agent Skill from the existing `slcli-mcp` server.

## Recommendation

Implement the final `io.modelcontextprotocol/skills` extension as a thin adapter over the already-packaged [`slcli/skills/slcli`](../slcli/skills/slcli) directory. Publish one static, digest-backed skill at `skill://slcli/SKILL.md`; expose its instructions, references, and helper scripts through `resources/read`; implement `skills/list`, `skills/get`, and `resources/directory/read`; and advertise `{ "directoryRead": true }` from `server/discover`. Exclude the internal `evals/` tree from the published skill namespace.

Keep the filesystem installer and recommend the local skill when both local and MCP origins are available. Remove the three experimental `slcli://` resources when the extension ships; initialization instructions and tool metadata remain available to clients that do not support Skills. Do not invent an archive, cache, watcher, database, or dynamic provider: the final extension defines individual resources, the release bundle is static, and the SDK's Skills convenience API is not released.

Target MCP protocol revision `2026-07-28` or later. The extension is Final via [SEP-2640](https://modelcontextprotocol.io/seps/2640-skills-extension), and the [stable specification](https://github.com/modelcontextprotocol/ext-skills/blob/main/specification/stable/skills.mdx) targets that revision. This supersedes pre-final proposals and `2025-11-25` assumptions.

**Critical product constraint:** server support alone produces no skill behavior in an unsupported client. Extensions are opt-in on both sides. The current [official client matrix](https://modelcontextprotocol.io/extensions/client-matrix) lists only partial Skills support for ChatGPT, fast-agent, and MCP Inspector, and none for VS Code GitHub Copilot, Claude, Cursor, Goose, or other named clients. The first release therefore targets Inspector verification and protocol conformance, is enabled by default, and is documented as experimental. It makes no end-user activation claim.

## Primary sources

- [Official Skills overview](https://modelcontextprotocol.io/extensions/skills/overview)
- [Stable Skills extension specification](https://github.com/modelcontextprotocol/ext-skills/blob/main/specification/stable/skills.mdx)
- [Final SEP-2640](https://modelcontextprotocol.io/seps/2640-skills-extension)
- [Extension client matrix](https://modelcontextprotocol.io/extensions/client-matrix)
- [ext-skills implementation registry](https://github.com/modelcontextprotocol/ext-skills/blob/main/docs/implementations.md)
- [Agent Skills format specification](https://agentskills.io/specification)
- [Python MCP SDK v2.1.1 source](https://github.com/modelcontextprotocol/python-sdk/tree/v2.1.1)
- [Python MCP SDK releases](https://github.com/modelcontextprotocol/python-sdk/releases)
- [Open Python SDK Skills PR #3485](https://github.com/modelcontextprotocol/python-sdk/pull/3485)

## Current state

### Repository and packaging

- [`pyproject.toml`](../pyproject.toml) declares optional and development `mcp >=2,<3`; [`poetry.lock`](../poetry.lock) and installed distribution metadata resolve `mcp 2.1.1`.
- Poetry includes `slcli/skills` in wheels/sdists; [`scripts/build_pyinstaller.py`](../scripts/build_pyinstaller.py) places it at the frozen `skills` root.
- [`slcli/skill_click.py`](../slcli/skill_click.py) copies skills into personal, project, or explicit locations and writes `.slcli-version`; [`tests/unit/test_skill_click.py`](../tests/unit/test_skill_click.py) covers it.
- [`slcli/mcp_server.py`](../slcli/mcp_server.py) locates packaged references in source, one-file, and frozen layouts.

### Bundled skill inventory

The inventory below counts the publishable source files under `slcli/skills/slcli` on the decision date. It excludes generated and ignored runtime artifacts such as `__pycache__/` and `*.pyc`:

| Area | Files | Bytes |
| --- | ---: | ---: |
| `SKILL.md` | 1 | 12,901 |
| `references/` | 21 | 240,777 |
| `scripts/` | 9 | 93,773 |
| `evals/` | 9 | 48,500 |
| **Total** | **40** | **395,951** |

This is safely below the extension's portable ceiling of 512 resources and 16 MiB per skill.
The manifest can therefore be complete and static rather than `"dynamic"`.

All nine script-like files are Python files under [`slcli/skills/slcli/scripts`](../slcli/skills/slcli/scripts). None has an executable bit or shebang. Agent Skills permits scripts, but MCP does not transport executable bits and requires explicit per-skill approval before host-side execution. Clients may not support Python execution.

The [`SKILL.md`](../slcli/skills/slcli/SKILL.md) satisfies Agent Skills rules: directory and `name` are `slcli`; the name is valid; YAML frontmatter has `name` and non-empty `description`; extra `argument-hint` is allowed and must pass through verbatim; references are relative. There are no nested skills.

`evals/` is conforming supporting content but adds 9 files/48,500 bytes to each manifest and approval change. It is internal validation material, is not referenced by `SKILL.md`, and will remain in the packaged filesystem skill while being excluded from the MCP resource namespace. The published manifest therefore contains 31 source files totaling 347,451 bytes. Generated Python cache files are not skill content in either distribution and must never enter the manifest.

### Existing MCP resources

The current server exposes exactly these custom resources, tested in [`tests/unit/test_mcp_server.py`](../tests/unit/test_mcp_server.py):

- `slcli://capabilities`, an inline tool-selection index.
- `slcli://docs/commands`, backed by `references/commands.md`.
- `slcli://docs/filtering`, backed by `references/filtering.md`.

These are ordinary resources, not Agent Skills. Remove all three when the extension ships rather than maintaining parallel resource namespaces. Unsupported clients continue to receive critical routing guidance through initialization instructions and tool metadata, while the filesystem installer remains the recommended long-form guidance path.

## SDK capability audit

The audit is against installed/pinned `mcp 2.1.1`, whose metadata is at [`.venv/lib/python3.11/site-packages/mcp-2.1.1.dist-info/METADATA`](../.venv/lib/python3.11/site-packages/mcp-2.1.1.dist-info/METADATA), not repository main.

| Required surface | MCP 2.1.1 status | Consequence |
| --- | --- | --- |
| `server/discover` | **Yes** | Low-level `Server` registers a default handler and advertises modern versions. |
| Extension capability advertisement | **Yes** | `MCPServer(extensions=[...])` applies `Extension.settings()` under `capabilities.extensions`. |
| `resources/read` | **Yes** | `MCPServer.resource()`/`add_resource()` and the built-in resource handler serve files. |
| `skills/list` | **No native Skills API** | Add an extension `MethodBinding` and local Pydantic request/result models. |
| `skills/get` | **No native Skills API** | Add an extension `MethodBinding` and local models. |
| `resources/directory/read` | **No native directory API** | Add an optional extension `MethodBinding`; advertise `directoryRead: true`. |
| Custom request handlers | **Yes** | `Extension.methods()` is the preferred high-level route; low-level `Server.add_request_handler()` also exists. |
| Required revision | **Yes** | SDK 2.x supports `2026-07-28` and earlier revisions from one server. Skills calls remain modern-extension behavior. |

Installed [`extension.py`](../.venv/lib/python3.11/site-packages/mcp/server/extension.py) defines `Extension`/`MethodBinding`; [`mcpserver/server.py`](../.venv/lib/python3.11/site-packages/mcp/server/mcpserver/server.py) registers methods/settings; [`lowlevel/server.py`](../.venv/lib/python3.11/site-packages/mcp/server/lowlevel/server.py) owns discovery, custom handlers, resource reads, and advertisement.

The [implementation registry](https://github.com/modelcontextprotocol/ext-skills/blob/main/docs/implementations.md) marks Python support in progress. Open [PR #3485](https://github.com/modelcontextprotocol/python-sdk/pull/3485) proposes `Skills`, wire models, validation, helpers, and conformance but leaves filesystem discovery/indexing/caching to higher layers. Neither 2.1.1 nor current 2.2.0 includes it as of this date.

## Gap analysis

1. The server does not declare `io.modelcontextprotocol/skills` in `server/discover`.
2. It has no `skills/list` or `skills/get` handlers or extension wire models.
3. It serves only two of the 40 skill files and only under custom `slcli://` URIs.
4. It has no `skill://` resolver, complete SHA-256/size manifest, MIME map, or scoped directory reads.
5. Tests cover normal resources, prompts, tools, discovery, legacy initialization, and transports, but not Skills schemas, manifests, traversal, or negotiation.
6. Filesystem installation reaches unsupported clients and remains the recommended path until host support matures.
7. A server cannot make an unsupported host register, approve, activate, resolve, verify, or execute a skill.

## Proposed architecture

### One project-owned extension adapter

Add one private `SlcliSkillsExtension(Extension)` near the MCP server. It should:

- set `identifier = "io.modelcontextprotocol/skills"`;
- return `{ "directoryRead": true }` from `settings()`;
- bind `skills/list`, `skills/get`, and `resources/directory/read` only for
  `2026-07-28` and later;
- contribute or register every regular bundled skill file as a resource;
- omit paths under `evals/` from the published virtual skill directory;
- omit generated or ignored files, including `__pycache__/` and `*.pyc`;
- use one immutable in-memory catalog built from packaged files at server startup.

Keep code in the existing MCP module unless one companion module is materially clearer. One skill/provider needs no hierarchy.

### Static catalog and URI resolution

Locate the root with the existing source/frozen pattern. Build the virtual directory from an explicit publish policy: `SKILL.md`, files under `references/`, and Python source files directly under `scripts/`. Exclude `evals/`, cache directories, bytecode, hidden files, and all other generated artifacts. Sort POSIX-relative paths, read raw bytes once, and produce:

- skill URI `skill://slcli/SKILL.md`;
- verbatim YAML frontmatter parsed with already-installed PyYAML;
- one manifest item per file with URI, `sha256:<lowercase hex>`, and raw byte length;
- a URI-to-bytes/MIME map and a directory-to-direct-children map.

Reject symlinks, non-regular files, dot segments, backslashes, decoded traversal, unknown entries, and directory reads against files with `-32602`. Never accept a client filesystem path; no profile, user configuration, secret, or API key enters the namespace.

Validate the entire catalog before serving any request. A missing, malformed, oversized, or unsafe skill fails server startup rather than silently disabling the advertised extension.

Map Markdown/JSON/SVG/HTML/Python MIME types explicitly. Directories use `inode/directory` and no trailing slash.

### Wire behavior

- `skills/list`: return one atomic entry, `resultType: "complete"`, required `ttlMs`/`cacheScope`, and no cursor unless needed.
- `skills/get`: accept only `skill://slcli/SKILL.md`; return the same entry and cache fields.
- `resources/read`: return exact manifested bytes; decode text as UTF-8 and use blob representation for binary.
- `resources/directory/read`: return sorted direct children with `resultType: "complete"`; support every namespace directory.
- Existing prompts continue unchanged; the three `slcli://` resources are removed.

The server computes metadata but does not own host approval, activation, cache, origin labels, verification, or execution.

## Phased implementation

### Phase 0: dependency gate

1. Retain a tested MCP 2.x floor with `Extension`, `MethodBinding`, discovery, and the modern wire.
2. Recheck Python SDK PR #3485 and the latest release immediately before implementation.
3. If native support ships, use its models/validation/`Skills`; otherwise use 2.1.1 hooks.

**Exit criteria:** one dependency/version decision is recorded; no code targets an unreleased API.

### Phase 1: catalog and validation

1. Add local wire models matching the stable TypeScript shapes exactly.
2. Build the deterministic static catalog from the packaged skill root.
3. Validate name/frontmatter, complete manifest, limits, containment, and types at startup.

**Exit criteria:** tests prove 31 entries/347,451 bytes, matching hashes/frontmatter, `evals/` and Python-cache exclusion, fail-fast startup, and unsafe-input rejection.

### Phase 2: extension handlers and resources

1. Register the extension and all three methods.
2. Serve all `skill://slcli/...` files through normal resource reads.
3. Remove all `slcli://` resources while preserving tool, prompt, and initialization behavior.

**Exit criteria:** modern tests pass for discovery, methods, resources, directories, errors, caching, and capabilities; existing tools, prompts, initialization guidance, and filesystem installation remain unchanged, while the experimental `slcli://` resources are intentionally removed.

### Phase 3: package and interoperability validation

1. Build wheel, sdist, and PyInstaller artifacts; inspect their skill trees.
2. Run the official SEP-2640 server conformance scenarios when published in a released harness.
3. Exercise MCP Inspector 2.6+ verification and one second implementation from the
   [registry](https://github.com/modelcontextprotocol/ext-skills/blob/main/docs/implementations.md).

**Exit criteria:** source, wheel, and frozen servers return identical bytes/manifests; conformance passes.

### Phase 4: adoption decision

Promote MCP delivery only when supported clients implement discovery, approval, activation, verified reads, and origin handling. Until then it is enabled by default but explicitly experimental and validated only as a protocol endpoint.

**Exit criteria:** named supported clients and tested versions are documented; filesystem install
remains available for every unsupported client.

## Testing and validation plan

- Unit-test exact `server/discover` capabilities and the absence of advertisement on legacy wire.
- Test method schemas, cache fields, equality, unknown URI `-32602`, and request `_meta`.
- Hash each file against `resources/read`; compare parsed frontmatter field-for-field.
- Test direct-child/nested/empty/error directory cases, order, MIME types, and slash rules.
- Test encoded traversal, backslashes, symlinks, outside paths, `__pycache__`, and bytecode; assert no user config is read.
- Extend [`tests/unit/test_mcp_server.py`](../tests/unit/test_mcp_server.py) and [`tests/e2e/test_mcp_e2e.py`](../tests/e2e/test_mcp_e2e.py); keep protocol tests account-independent.
- Build artifacts and compare file count, manifest, and digests across source/wheel/frozen layouts.
- Run repository formatting, style, typing, unit, full pytest, and targeted MCP E2E checks.

## Migration and backward compatibility

- Keep `slcli skill install`/`.slcli-version` unchanged; local copies update only when requested.
- Treat MCP and installed skills as separate origins even when identical; recommend the local origin when both are present.
- Remove all three experimental `slcli://` URIs in the same release as the Skills extension.
- Do not redirect schemes: identity, metadata, digests, and approval bind to exact URIs.
- Version content with `slcli`; manifest changes correctly invalidate content-bound approval.
- If a future Python SDK release ships the API in PR #3485, replace local wire models and bindings
  with official equivalents behind unchanged `skill://` URIs and response semantics.

## Ranked concerns and risks

1. **Client support (external).** Resolved operationally by targeting Inspector/conformance, labeling the feature experimental, and making no activation claim.
2. **Remote execution trust.** Accepted: publish the nine Python helpers unchanged and rely on the host's mandatory per-skill execution approval and origin handling.
3. **Pre-native SDK APIs.** Resolved with a small local adapter against stable wire shapes, replaced by official APIs when released.
4. **Packaging mismatch.** Mitigated by computing metadata from served bytes and verifying source, wheel, sdist, and frozen layouts.
5. **Traversal/disclosure.** Mitigated by resolving only the indexed virtual namespace and failing startup on invalid content.
6. **Duplicate local and MCP skills.** Resolved by preserving origin and recommending the local skill when both are available.
7. **Eval-file churn.** Resolved by excluding `evals/` from the MCP namespace and manifest.
8. **Custom-resource compatibility.** Accepted as an experimental-interface break; remove all `slcli://` resources when Skills ships.

## Go/no-go criteria

Proceed now against protocol revision `2026-07-28` using the stable schemas and local SDK extension hooks. Ship enabled by default and experimental after Inspector/conformance validation. Continue recommending the filesystem skill for normal use, and do not claim automatic availability in VS Code GitHub Copilot or another client until the matrix and an end-to-end test confirm it.