# CLI Consistency Analysis & Improvement Proposals

**Date**: December 12, 2025  
**Branch**: `analysis/cli-consistency-review`  
**Status**: Proposal for Discussion

## Executive Summary

This document analyzes consistency across all SystemLink CLI commands and proposes improvements. The analysis focuses on:

1. **Flag naming** (--workspace, --id, --name, --filter, etc.)
2. **Resource identification patterns** (by ID vs. by name)
3. **Filtering mechanisms** (--filter vs. specialized filters)
4. **Command structure** (list, get, create, update, delete patterns)

---

## 1. Workspace Specification Inconsistencies

### Current State

| Command                  | Workspace Support                       | Pattern              |
| ------------------------ | --------------------------------------- | -------------------- |
| `feed list`              | `--workspace` (name or ID)              | ✓ Flexible           |
| `feed create`            | `--workspace` (name or ID)              | ✓ Flexible           |
| `file list`              | `--workspace` (name or ID)              | ✓ Flexible           |
| `notebook manage list`   | `--workspace` (name, default "Default") | Name only            |
| `notebook manage create` | `--workspace` (name, default "Default") | Name only            |
| `notebook execute list`  | `--workspace` (name or ID)              | ✓ Flexible           |
| `template list`          | `--workspace` (name or ID)              | ✓ Flexible           |
| `workflow list`          | `--workspace` (name or ID)              | ✓ Flexible           |
| `webapp list`            | `--workspace` (name or ID)              | ✓ Flexible           |
| `dff config list`        | `--workspace` (name or ID)              | ✓ Flexible           |
| `workspace list`         | `--name` filter only                    | ❌ Different pattern |
| `workspace get`          | `--id` OR `--name` (separate flags)     | ❌ Different pattern |

### Issues Identified

1. **Notebook commands** use workspace name only, not ID
2. **Workspace get** uses separate `--id`/`--name` flags instead of unified `--workspace`
3. **Workspace list** uses `--name` for filtering instead of `--workspace`

### Proposal 1: Standardize Workspace Handling

**Rationale**: Users should be able to use workspace names or IDs interchangeably across all commands.

**Changes**:

```bash
# Current (notebook)
slcli notebook manage create --workspace Default --name test.ipynb

# Proposed (allow ID too)
slcli notebook manage create --workspace <id-or-name> --name test.ipynb
slcli notebook manage create --workspace Default --name test.ipynb

# Current (workspace get)
slcli workspace get --id <workspace-id>
slcli workspace get --name "Production"

# Proposed (unified)
slcli workspace get --workspace <id-or-name>
slcli workspace get <workspace-id-or-name>  # positional argument alternative

# Current (workspace list filtering)
slcli workspace list --name Production

# Proposed (consistent with other commands)
slcli workspace list --workspace Production
```

**Impact**:

- Medium breaking change for `workspace get` (flag rename)
- Low breaking change for `workspace list` (can support both during transition)
- Notebook commands enhanced (backward compatible if we still accept names)

---

## 2. Resource Identification Patterns

### Current State

| Command                    | ID Flag           | Name Flag            | Pattern          |
| -------------------------- | ----------------- | -------------------- | ---------------- |
| `feed get`                 | `--id` (required) | ❌                   | ID only          |
| `template export`          | `--id` (required) | ❌                   | ID only          |
| `workflow export`          | `--id` (required) | ❌                   | ID only          |
| `webapp get`               | `--id` (required) | ❌                   | ID only          |
| `notebook manage download` | `--id` (optional) | `--name` (optional)  | ✓ Either         |
| `notebook manage get`      | `--id` (required) | ❌                   | ID only          |
| `workspace get`            | `--id` (optional) | `--name` (optional)  | ✓ Either         |
| `user get`                 | `--id` (optional) | `--email` (optional) | ✓ Either (email) |

### Issues Identified

1. **Inconsistent name support**: Some commands support lookup by name, most don't
2. **User command** uses `--email` as alternative identifier (special case, reasonable)
3. **Notebook download** supports name but **get** doesn't

### Proposal 2: Support Name Lookup Where Practical

**Rationale**:

- Users often know resource names better than IDs
- API constraints mean some resources don't have unique names
- Trade-off between consistency and API capabilities

**Decision Matrix**:

| Resource | Unique Names?      | Support Name Lookup?          | Reason                        |
| -------- | ------------------ | ----------------------------- | ----------------------------- |
| Feed     | No (per workspace) | ❌ Keep ID only               | Names not globally unique     |
| Template | Yes                | ✓ Add name support            | Names are unique identifiers  |
| Workflow | No (per workspace) | ❌ Keep ID only               | Names not globally unique     |
| Webapp   | No                 | ❌ Keep ID only               | Names not globally unique     |
| Notebook | No (per workspace) | ✓ Keep current (inconsistent) | Already supported in download |
| User     | Email unique       | ✓ Keep email                  | Email is natural identifier   |
| File     | N/A                | ❌ Keep ID only               | No meaningful name field      |

**Proposed Changes**:

```bash
# Add name support to template commands
slcli template export --id <id>           # Current
slcli template export --name "My Template"  # Proposed addition

# Fix notebook inconsistency
slcli notebook manage get --id <id>       # Current
slcli notebook manage get --name "test.ipynb" --workspace Default  # Proposed addition
```

**Non-changes** (keep as-is with justification):

- Feed, workflow, webapp: Names not unique, ID-only appropriate
- File: No meaningful name alternative to ID

---

## 3. Filtering Mechanisms

### Current State

| Command                 | Filter Options                                                     | Pattern              |
| ----------------------- | ------------------------------------------------------------------ | -------------------- |
| `user list`             | `--filter` (LINQ), `--type`, `--sortby`, `--order`                 | ✓ Advanced LINQ      |
| `function manage list`  | `--filter` (LINQ), `--name`, `--workspace`, `--interface-contains` | ✓ LINQ + shortcuts   |
| `file list`             | `--filter` (name search), `--workspace`, `--id-filter`             | Simple search        |
| `file query`            | `--filter` (search expression), `--workspace`, `--order-by`        | ✓ Advanced search    |
| `feed list`             | `--platform`, `--workspace`                                        | ❌ No general filter |
| `template list`         | `--workspace`                                                      | ❌ No general filter |
| `workflow list`         | `--workspace`, `--status`                                          | ❌ No general filter |
| `notebook execute list` | `--workspace`, `--status`, `--notebook-id`                         | ❌ No general filter |

### Issues Identified

1. **Two file commands**: `list` (simple) vs. `query` (advanced) creates confusion
2. **Inconsistent filter support**: Some commands have LINQ, others only specific filters
3. **Status filtering**: Workflow and notebook use `--status`, but not consistently available

### Proposal 3: Standardize Filtering Approach

**Rationale**:

- Advanced LINQ filtering is powerful but complex
- Specific filters (--status, --platform) are more discoverable
- Two-tier approach: common filters + advanced --filter for power users

**Proposed Standard**:

```bash
# Tier 1: Common, specific filters (always available where applicable)
--workspace <id-or-name>    # Workspace filter
--status <status>           # Status filter (where applicable)
--name <pattern>            # Name pattern filter
--type <type>               # Type filter (where applicable)

# Tier 2: Advanced filter (optional, for power users)
--filter <expression>       # LINQ or search expression (API-dependent)
```

**Specific Changes**:

**3a. Merge file commands** (breaking change):

```bash
# Current
slcli file list --filter searchterm        # Simple search
slcli file query --filter 'name:("*test*")'  # Advanced search

# Proposed (single command)
slcli file list --name searchterm          # Common case
slcli file list --filter 'name:("*test*")'  # Advanced case
# Deprecate: slcli file query (redirect to list with warning)
```

**3b. Add --filter to resource lists** where backend supports it:

```bash
# Enhanced feed list
slcli feed list --platform windows --workspace Default
slcli feed list --filter 'name.Contains("prod")'  # If API supports

# Enhanced workflow list
slcli workflow list --status active
slcli workflow list --filter 'status = "active" AND workspace = "<id>"'  # If API supports
```

---

## 4. Command Naming Patterns

### Current State - CRUD Operations

| Resource  | List | Get | Create | Update          | Delete  | Export | Import |
| --------- | ---- | --- | ------ | --------------- | ------- | ------ | ------ |
| Feed      | list | get | create | ❌              | delete  | ❌     | ❌     |
| Template  | list | ❌  | ❌     | ❌              | delete  | export | import |
| Workflow  | list | ❌  | ❌     | update          | delete  | export | import |
| Webapp    | list | get | ❌     | ❌              | delete  | ❌     | ❌     |
| Notebook  | list | get | create | update          | delete  | ❌     | ❌     |
| User      | list | get | create | update          | delete  | ❌     | ❌     |
| File      | list | get | upload | update-metadata | delete  | ❌     | ❌     |
| Function  | list | get | create | update          | delete  | ❌     | ❌     |
| Workspace | list | get | ❌     | ❌              | disable | ❌     | ❌     |

### Issues Identified

1. **Inconsistent get support**: Template/workflow have export but no get
2. **File uses "upload"** instead of "create" (reasonable - domain-specific)
3. **Workspace uses "disable"** instead of "update" (reasonable - limited API)
4. **update-metadata** for files vs. **update** for others

### Proposal 4: Clarify Command Naming Conventions

**Rationale**:

- CRUD pattern is intuitive but not always applicable
- Domain-specific terms (upload, publish, disable) are clearer than generic CRUD
- Consistency with API capabilities is more important than forcing CRUD

**Proposed Guidelines**:

1. **Prefer CRUD when applicable**: list, get, create, update, delete
2. **Use domain terms when clearer**:
   - `upload` for files (not `create`)
   - `publish` for webapps (not `create` or `update`)
   - `disable` for workspaces (not `update`)
3. **Export/Import for portable resources**: Templates, workflows, DFF configs
4. **Don't force get** where export is sufficient

**Specific Recommendations**:

- Keep current naming (it's already pretty good)
- Add `template get` for consistency (show metadata without file export)
- Add `workflow get` for consistency (show metadata without file export)
- Keep `file update-metadata` (distinguishes from content update)

---

## 5. Subcommand Structure

### Current State

| Command Group | Subgroups                              | Pattern              |
| ------------- | -------------------------------------- | -------------------- |
| `notebook`    | `manage`, `execute`                    | ✓ Logical grouping   |
| `function`    | `manage`, `execute`                    | ✓ Logical grouping   |
| `feed`        | `package`                              | ✓ Nested resource    |
| `dff`         | `config`, `groups`, `fields`, `tables` | ✓ Multiple resources |
| `file`        | ❌                                     | Flat structure       |
| `template`    | ❌                                     | Flat structure       |
| `workflow`    | ❌                                     | Flat structure       |
| `webapp`      | ❌                                     | Flat structure       |
| `user`        | ❌                                     | Flat structure       |
| `workspace`   | ❌                                     | Flat structure       |

### Issues Identified

1. **Notebook/function** use subgroups, others don't
2. **Feed** has nested `package` resource
3. **DFF** has multiple resource types (appropriate)

### Proposal 5: Keep Current Subcommand Structure

**Rationale**:

- Subgroups used where there are distinct operation types (manage vs. execute)
- Flat structure is simpler for basic CRUD
- No strong consistency issue here

**Recommendation**: No changes needed. Current structure is justified by use case differences.

---

## 6. Flag Shorthand Consistency

### Current State

| Flag          | Shorthand | Commands                 | Consistency                |
| ------------- | --------- | ------------------------ | -------------------------- |
| `--workspace` | `-w`      | Most commands            | ✓ Consistent               |
| `--format`    | `-f`      | All list commands        | ✓ Consistent               |
| `--take`      | `-t`      | All list commands        | ✓ Consistent               |
| `--id`        | `-i`      | Most commands            | ✓ Consistent               |
| `--name`      | `-n`      | Mixed usage              | ⚠️ Varies                  |
| `--output`    | `-o`      | Export/download commands | ✓ Consistent               |
| `--file`      | `-f`      | Import commands          | ⚠️ Conflicts with --format |

### Issues Identified

1. **`-f` conflict**: Used for both `--format` and `--file`
2. **`-n` usage**: Sometimes name, sometimes notebook-id

### Proposal 6: Resolve Flag Shorthand Conflicts

**Rationale**: Shorthand conflicts cause user errors and confusion.

**Changes**:

```bash
# Current (conflict)
slcli template list --format json -f json  # -f is --format
slcli template import --file template.json -f template.json  # -f is --file

# Proposed (resolved)
slcli template list --format json -f json     # Keep -f for --format (more common)
slcli template import --file template.json    # Remove -f shorthand for --file
slcli workflow import --file workflow.json    # Remove -f shorthand for --file

# Alternative: Use different shorthand
slcli template import --file template.json --input template.json  # Alias
```

**Decision**: Remove `-f` shorthand from `--file` in import commands. `--format` is more frequently used.

---

## 7. Output Format Patterns

### Current State

All list commands support:

- `--format` (`-f`): table | json
- `--take` (`-t`): pagination size

✓ This is **already consistent** across the board.

### Recommendation

**Keep as-is**. This is one of the most consistent aspects of the CLI.

---

## Summary of Recommendations

### High Priority (User-Facing Benefits)

1. **[P1] Standardize workspace handling across all commands**

   - Allow ID or name everywhere
   - Update notebook commands to accept workspace IDs
   - Unify workspace get to use `--workspace` flag

2. **[P1] Resolve `-f` flag conflict**

   - Keep `-f` for `--format` (more common)
   - Remove `-f` shorthand from `--file` in import commands

3. **[P2] Add name lookup to template commands**
   - `template export --name "Template Name"`
   - Makes common operations easier

### Medium Priority (Improved UX)

4. **[P2] Standardize filtering with two-tier approach**

   - Common filters: `--workspace`, `--status`, `--name`, `--type`
   - Advanced filter: `--filter <expression>`
   - Merge `file list` and `file query` (deprecate query)

5. **[P3] Add get commands for template/workflow**
   - `template get --id <id>` for metadata only
   - `workflow get --id <id>` for metadata only
   - Complements existing export functionality

### Low Priority (Nice-to-Have)

6. **[P3] Consistent notebook command behavior**
   - Allow `notebook manage get --name` like download supports
   - Improves internal consistency

---

## Implementation Strategy

### Phase 1: Non-Breaking Enhancements (Safe to implement)

- Add workspace ID support to notebook commands (backward compatible)
- Add `--name` support to template export (backward compatible)
- Add `template get` and `workflow get` commands (new functionality)
- Add `--workspace` filter to workspace list (keep `--name` as alias)

### Phase 2: Breaking Changes (Requires version bump)

- Remove `-f` shorthand from `--file` in import commands
- Rename workspace get flags to unified `--workspace`
- Merge `file list` and `file query` (deprecate query)

### Phase 3: Documentation

- Update README with consistent patterns
- Add migration guide for breaking changes
- Update shell completion

---

## Conclusion

The SystemLink CLI is **largely consistent** in its current form. The main issues are:

1. **Workspace handling** varies (name-only vs. id-or-name)
2. **Flag shorthand conflict** (`-f` for format vs. file)
3. **File commands split** (list vs. query creates confusion)

These can be addressed incrementally with a mix of backward-compatible enhancements and documented breaking changes in a future major version.

**Recommendation**: Implement Phase 1 changes immediately, plan Phase 2 for next major release (2.0), and improve documentation throughout.
