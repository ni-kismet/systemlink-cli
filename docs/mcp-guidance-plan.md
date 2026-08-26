# MCP Client Guidance Plan

## Goal

Make the slcli MCP server self-describing enough that an MCP host can choose the
right tool, construct valid arguments, and understand the returned data without
requiring a separate slcli skill installation.

The existing slcli skill remains the long-form reference for clients that support
skills. MCP metadata must still stand on its own because clients are not required
to load that skill or read an arbitrary resource.

## Guidance layers

### Server initialization

Use the server name, title, description, version, and `instructions` for short
rules that apply to every tool:

- use `query_*` tools for discovery and `get_*` tools when an identifier is known;
- resolve workspace names to IDs when a service requires an ID;
- treat filters as service-specific and use substitutions for Dynamic LINQ values;
- scope calls to the active slcli profile and workspace;
- treat an empty result as no matching visible data, not proof that a resource does
  not exist.

These instructions must stay concise because they are sent on every connection.

### Tool metadata

Every tool should have:

- a docstring describing what it queries and when to use it;
- typed parameters, defaults, and `Annotated`/`Field` descriptions;
- bounds for pagination and other numeric values;
- `Literal` values for service enums;
- read-only and idempotency annotations where applicable;
- a result contract that identifies the important fields and pagination behavior.

Tool metadata is the primary model-facing contract. Critical routing information
must not exist only in a resource.

### Reference resources

Keep `slcli://capabilities` as a small index. Expose detailed, read-only Markdown
references for topics that are too large for initialization or tool descriptions:

- `slcli://docs/commands`
- `slcli://docs/filtering`

These resources are backed by the packaged slcli skill references, so the MCP
server and the installed skill use the same source material.

### Prompts

Add user-selected prompts only for repeatable workflows, such as investigating
failed test results or reviewing fleet calibration status. Prompts should prepare
a workflow for the user; they should not be used as hidden server instructions.

### Structured outputs

The current tools return JSON text for compatibility with the existing MCP clients.
Their generated output schema therefore describes a string, even when the text
contains a JSON list or object.

Migrate outputs incrementally:

1. define stable Pydantic response models or typed envelopes for high-value query
   tools;
2. preserve a single JSON text representation in `content` while clients migrate;
3. assert both `output_schema` and `structured_content` in tests;
4. migrate less stable upstream payloads only after their service shapes are known.

Do not claim fields in an output schema that the upstream service does not guarantee.

## Implementation status

- [x] Add server initialization guidance and version metadata.
- [x] Add a capabilities index and packaged Markdown reference resources.
- [x] Add read-only/idempotent annotations and richer input metadata to the core
  discovery tools.
- [x] Document the contract and test expectations.
- [x] Migrate the first stable query response (`query_workspaces`) to typed
  structured output.
- [ ] Migrate the remaining stable query responses to typed structured output.
- [x] Add high-value workflow prompts for failed-result investigation and fleet
  calibration review.
- [x] Replace stale MCP examples with the current `query_*`/`get_*` surface.

## Validation requirements

Unit tests should verify server instructions, server version, resource listings,
tool annotations, input schemas, and resource contents. The E2E suite should
continue to verify that a real MCP client can list and call the complete tool
surface over streamable HTTP.
