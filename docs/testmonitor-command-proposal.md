# Test Monitor Command Proposal: Analysis & Recommendations

**Date:** February 6, 2026  
**Context:** Review of slcli-workflow-analysis.md against current testmonitor implementation

---

## Executive Summary

The current `testmonitor` implementation provides **solid foundational capabilities** that address many workflow requirements. However, the workflow analysis proposes a more granular command structure that doesn't align well with:
1. Current SystemLink API structure
2. Established slcli patterns
3. Actual user workflows

**Recommendation:** Enhance the existing `testmonitor` commands rather than creating separate `testresult`, `teststep`, `testpath`, `testmeasurement` groups.

---

## Current Implementation Assessment

### What We Have (Just Implemented)

#### `slcli testmonitor product list`
**Capabilities:**
- ✅ Filter by name, part-number, family, workspace
- ✅ Dynamic LINQ filter expressions with substitutions
- ✅ Ordering by: ID, PART_NUMBER, NAME, FAMILY, UPDATED_AT
- ✅ Interactive pagination (25 items/page)
- ✅ Table and JSON output formats
- ✅ Workspace resolution (by ID or name)

**Example:**
```bash
slcli testmonitor product list \
  --name "XYZ" \
  --family "TestFamily" \
  --filter "updatedAt > @0" \
  --substitution "2025-08-01" \
  --format json
```

#### `slcli testmonitor result list`
**Capabilities:**
- ✅ Filter by: status, program-name, serial-number, part-number, operator, host-name, system-id, workspace
- ✅ Product filtering via `--product-filter` and `--product-substitution`
- ✅ Dynamic LINQ expressions with full substitution support
- ✅ Ordering by 11 fields (ID, STARTED_AT, UPDATED_AT, PROGRAM_NAME, etc.)
- ✅ Interactive pagination
- ✅ Table and JSON output
- ✅ Status normalization (e.g., "passed" → "PASSED")

**Example:**
```bash
slcli testmonitor result list \
  --status FAILED \
  --part-number "XYZ" \
  --started-after "2025-08-01" \
  --started-before "2026-01-31" \
  --format json
```

---

## Workflow Analysis Proposals vs. Current Implementation

### Workflow 1: "Show me all failed measurements on product XYZ for the last two quarters"

**Workflow Analysis Proposes:**
```bash
# Multiple separate command groups
slcli testresult query --filter '...' --started-after --started-before
slcli teststep query --filter 'resultId in [...]'
slcli testpath query --filter 'partNumber = "XYZ"'
slcli testresult analyze --product "XYZ" --status failed
slcli testmeasurement query --product "XYZ" --status failed
```

**Current Implementation Can Do:**
```bash
# Single, focused command
slcli testmonitor result list \
  --part-number "XYZ" \
  --status FAILED \
  --started-after "2025-08-01" \
  --started-before "2026-01-31" \
  --format json

# For step-level data (proposed enhancement):
slcli testmonitor result list \
  --part-number "XYZ" \
  --status FAILED \
  --started-after "2025-08-01" \
  --include-steps \
  --format json
```

**Assessment:** ✅ Current structure is BETTER
- Fewer commands to learn
- Aligns with API structure (results are primary entity)
- Natural temporal filtering with `--started-after/before`
- Can be enhanced with `--include-steps` flag

---

### Workflow 6: "Show me what type of test data exists for [Part Number]"

**Workflow Analysis Proposes:**
```bash
slcli testpath query --filter 'partNumber = "ABC123"'
slcli testpath summary --part-number "ABC123"
slcli testmetadata get --part-number "ABC123"
```

**Current Implementation Can Do:**
```bash
# Query results to understand test coverage
slcli testmonitor result list \
  --part-number "ABC123" \
  --format json \
  | jq -r '[.[] | {program: .programName, started: .startedAt, status: .status.statusType}] | unique_by(.program)'

# Better: Add a summary flag
slcli testmonitor result list \
  --part-number "ABC123" \
  --summary \
  --format table
```

**Assessment:** ⚠️ Needs enhancement
- Current: Can list results, but no built-in summary
- Proposed: Add `--summary` flag to product/result list
- Don't need separate `testpath` command group

---

## Concrete Counter-Proposal

### Keep Current Structure, Add Enhancements

#### 1. Enhance `testmonitor product list`

**Add flags:**
```bash
slcli testmonitor product list \
  --name "XYZ" \
  --summary              # Show test coverage summary (programs, result counts)
  --show-paths           # Include test paths in output
  --format json
```

**Implementation:** Use POST `/nitestmonitor/v2/query-paths` to get paths matching product criteria, then aggregate data client-side

---

#### 2. Enhance `testmonitor result list`

**Add flags:**
```bash
slcli testmonitor result list \
  --part-number "XYZ" \
  --status FAILED \
  --started-after "2025-08-01" \
  --started-before "2026-01-31" \
  --include-steps        # Include step data in response
  --include-measurements # Include measurement data
  --group-by program     # Group results by program name
  --summary              # Show aggregated summary
  --format json
```

**Additional temporal filters:**
```bash
# Natural language date support
--since "2 quarters ago"
--since "last week"
--since "yesterday"
```

**Implementation:**
- `--include-steps`: Use POST `/nitestmonitor/v2/query-steps` with filter `resultId == @0` for each result
- `--include-measurements`: Parse measurements from step `outputs` field (part of step data)
- `--group-by`: Client-side grouping of results using POST `/nitestmonitor/v2/query-result-values` for efficient distinct value queries
- `--summary`: Aggregate counts by status, program, etc. using client-side processing

---

#### 3. Add `testmonitor product get` command

**Purpose:** Get detailed product information including test coverage

```bash
slcli testmonitor product get <id> \
  --show-results         # Include recent results
  --show-coverage        # Include test coverage stats
  --format json
```

**Output example:**
```json
{
  "id": "prod-123",
  "name": "Product XYZ",
  "partNumber": "XYZ-001",
  "family": "TestFamily",
  "workspace": "ws-456",
  "coverage": {
    "programs": ["Calibration", "Functional Test"],
    "totalResults": 1250,
    "passRate": 0.95,
    "lastTested": "2026-02-05T10:30:00Z"
  },
  "recentResults": [...]
}
```

---

#### 4. Add `testmonitor result get` command

**Purpose:** Get detailed result with steps and measurements

```bash
slcli testmonitor result get <id> \
  --include-steps \
  --include-measurements \
  --format json
```

**Output example:**
```json
{
  "id": "result-789",
  "status": {"statusType": "PASSED", "statusName": "Passed"},
  "programName": "Calibration",
  "partNumber": "XYZ-001",
  "serialNumber": "SN123456",
  "startedAt": "2026-02-05T10:30:00Z",
  "updatedAt": "2026-02-05T10:35:42Z",
  "systemId": "sys-abc",
  "hostName": "test-station-01",
  "operator": "engineer@company.com",
  "totalTimeInSeconds": 342.5,
  "workspace": "f94b178e-288c-4101-afb1-833992413aa7",
  "steps": [
    {
      "name": "DMM Voltage Test",
      "stepType": "NumericLimitTest",
      "stepId": "step-001",
      "resultId": "result-789",
      "path": ["Setup", "DMM Tests", "Voltage"],
      "status": {"statusType": "PASSED", "statusName": "Passed"},
      "totalTimeInSeconds": 5.2,
      "outputs": [
        {"name": "Voltage", "value": 5.01}
      ],
      "dataModel": "TestStand"
    }
  ]
}
```

**Note:** Measurements are stored in the `outputs` array of each step, not as a separate entity.

---

#### 5. Keep Command Structure Simple

**Proposed structure:**
```
slcli testmonitor
├── product
│   ├── list [current, enhanced with --summary, --show-paths]
│   └── get [new: detailed product info]
└── result
    ├── list [current, enhanced with --include-steps, --group-by, --summary]
    └── get [new: detailed result with steps/measurements]
```

**NOT creating separate:**
- ❌ `testresult` (redundant with `testmonitor result`)
- ❌ `teststep` (accessed via `result get --include-steps`)
- ❌ `testpath` (accessed via `product list --show-paths`)
- ❌ `testmeasurement` (accessed via `result get --include-measurements`)

---

## Rationale for Simplified Structure

### 1. Aligns with API Structure
The SystemLink Test Monitor API v2 is organized around four primary entities:
- **Products** - Test specifications and metadata (part numbers, families, properties)
- **Results** - Individual test executions (status, timestamps, system info)
- **Steps** - Test execution steps within results (measurements, status, hierarchy)
- **Paths** - Unique measurement paths across test programs

While steps and paths have their own query endpoints, they are **conceptually nested**:
- Steps belong to results (accessed via `resultId` filter)
- Paths are derived from products (accessed via `partNumber` filter)
- Measurements are stored in step `outputs` field (not a separate entity)

This supports our simplified CLI structure where steps are accessed via `result get --include-steps`

### 2. Matches User Mental Model
Users think in terms of:
- "List all failed tests for this product" → `result list`
- "What products do we test?" → `product list`
- "Show me details of this test run" → `result get`

They don't think:
- "Query test steps" (steps are part of results)
- "Query test paths" (paths are product metadata)
- "Query measurements" (measurements are in steps)

### 3. Reduces Command Explosion
Workflow analysis proposes:
- `testresult` (7 subcommands)
- `teststep` (3 subcommands)
- `testpath` (3 subcommands)
- `testmeasurement` (2 subcommands)
= **15 new commands**

Our proposal:
- Enhance `testmonitor product list`
- Enhance `testmonitor result list`
- Add `testmonitor product get`
- Add `testmonitor result get`
= **2 new commands + enhancements to existing 2**

### 4. Follows Established Patterns

Similar commands in slcli:
```bash
# File service - single group, simple verbs
slcli file list
slcli file get <id>
slcli file upload

# Tag service - single group
slcli tag list
slcli tag get <path>
slcli tag create

# Notebook service - single group
slcli notebook list
slcli notebook get <id>
slcli notebook execute
```

We should follow this pattern:
```bash
slcli testmonitor product list
slcli testmonitor product get <id>
slcli testmonitor result list
slcli testmonitor result get <id>
```

---

## Addressing Specific Workflow Requirements

### Workflow 1: Failed measurements on product XYZ

**Using enhanced commands:**
```bash
# Get all failed results with steps
slcli testmonitor result list \
  --part-number "XYZ" \
  --status FAILED \
  --started-after "2025-08-01" \
  --include-steps \
  --format json \
  > failed-results.json

# Analyze measurements (Copilot can parse JSON)
# Or add summary flag:
slcli testmonitor result list \
  --part-number "XYZ" \
  --status FAILED \
  --started-after "2025-08-01" \
  --summary \
  --format table
```

**Summary output example:**
```
Product: XYZ
Period: 2025-08-01 to 2026-01-31
Failed Results: 45

Top Failed Steps:
  DMM Voltage Test: 23 failures
  Frequency Response: 15 failures
  Power Supply Test: 7 failures

Programs:
  Calibration: 30 failures
  Functional Test: 15 failures
```

---

### Workflow 6: Test data types for product

**Using enhanced commands:**
```bash
# Product summary with test coverage
slcli testmonitor product list \
  --name "ABC123" \
  --summary \
  --show-paths \
  --format table

# Or get specific product
slcli testmonitor product get <id> \
  --show-coverage \
  --format json
```

**Output example:**
```
Product: ABC123 (Part: ABC123-REV2)
Workspace: Production

Test Coverage:
  Programs: Calibration, Functional Test, Burn-In
  Paths: 156 unique measurement paths
  Results: 2,340 total (95% pass rate)
  Last Tested: 2026-02-05

Common Measurements:
  - Voltage (DC, AC)
  - Current
  - Resistance
  - Frequency Response
  - Power Consumption
```

---

## Implementation Priority

### Phase 1: Immediate (with current PR)
- ✅ `testmonitor product list` (done)
- ✅ `testmonitor result list` (done)
- ✅ Comprehensive filtering (done)
- ✅ Dynamic LINQ support (done)

### Phase 2: Short-term (next sprint)
- 🔨 Add `testmonitor product get <id>`
- 🔨 Add `testmonitor result get <id>`
- 🔨 Add `--include-steps` flag to `result get`
- 🔨 Add `--include-measurements` flag to `result get`

### Phase 3: Medium-term
- 🔨 Add `--summary` flag to `product list` and `result list`
- 🔨 Add `--group-by` flag to `result list`
- 🔨 Add `--show-paths` flag to `product list`
- 🔨 Add `--show-coverage` flag to `product get`
- 🔨 Natural language date parsing ("2 quarters ago", "last week")

### Phase 4: Future Enhancements
- 🔨 Client-side aggregation and analytics
- 🔨 Export capabilities (CSV, Excel)
- 🔨 Statistical analysis (pass rates, trends)
- 🔨 Cross-reference with assets/systems (when APIs available)

---

## API Requirements

### Existing APIs (Available Now)

**Product APIs:**
- ✅ POST `/nitestmonitor/v2/query-products` - Query products with filters
- ✅ GET `/nitestmonitor/v2/products/{productId}` - Get single product by ID
- ✅ POST `/nitestmonitor/v2/products` - Create/update products
- ✅ POST `/nitestmonitor/v2/update-products` - Batch update products
- ✅ POST `/nitestmonitor/v2/delete-products` - Batch delete products
- ✅ POST `/nitestmonitor/v2/query-product-values` - Query distinct field values

**Result APIs:**
- ✅ POST `/nitestmonitor/v2/query-results` - Query results with filters (supports continuation tokens)
- ✅ GET `/nitestmonitor/v2/results/{resultId}` - Get single result by ID
- ✅ POST `/nitestmonitor/v2/results` - Create results
- ✅ POST `/nitestmonitor/v2/update-results` - Batch update results
- ✅ POST `/nitestmonitor/v2/delete-results` - Batch delete results
- ✅ POST `/nitestmonitor/v2/query-result-values` - Query distinct field values

**Step APIs:**
- ✅ POST `/nitestmonitor/v2/query-steps` - Query steps with filters (supports continuation tokens)
- ✅ GET `/nitestmonitor/v2/results/{resultId}/steps/{stepId}` - Get single step
- ✅ POST `/nitestmonitor/v2/steps` - Create steps
- ✅ POST `/nitestmonitor/v2/update-steps` - Batch update steps
- ✅ POST `/nitestmonitor/v2/delete-steps` - Batch delete steps
- ✅ POST `/nitestmonitor/v2/query-step-values` - Query distinct field values

**Path APIs:**
- ✅ GET `/nitestmonitor/v2/paths` - List paths with query parameters
- ✅ GET `/nitestmonitor/v2/paths/{pathId}` - Get single path by ID
- ✅ POST `/nitestmonitor/v2/query-paths` - Query paths with filters

### Implementation Notes

**For `testmonitor result get --include-steps`:**
- Use POST `/nitestmonitor/v2/query-steps` with filter: `resultId == @0`
- All steps for a result can be retrieved in a single query
- Steps support filtering by: name, stepType, stepId, parentId, path, totalTimeInSeconds, status, etc.

**For `testmonitor product get --show-coverage`:**
- Use POST `/nitestmonitor/v2/query-paths` with filter: `partNumber == @0`
- Use POST `/nitestmonitor/v2/query-results` with product filter to get result counts
- Client-side aggregation of pass rates, program names, and statistics

**For `testmonitor result list --summary`:**
- Query results normally
- Client-side aggregation by status, program name, etc.
- Use POST `/nitestmonitor/v2/query-result-values` to get distinct values for grouping

**For `testmonitor product list --show-paths`:**
- Use POST `/nitestmonitor/v2/query-paths` after product query
- Match products to paths by partNumber field
- Display common measurement paths

### No New APIs Required

All proposed enhancements can be implemented using existing Test Monitor v2 APIs through:
- **Query APIs:** Full Dynamic LINQ filtering with continuation token pagination
- **Value query APIs:** Efficient distinct value queries for grouping/summary
- **Client-side processing:** Aggregation, grouping, and statistical analysis
- **Multiple queries:** Combine product, result, step, and path queries as needed

---

## Comparison Table

| Capability | Workflow Analysis | Counter-Proposal | Assessment |
|-----------|------------------|------------------|------------|
| List products | `testresult query` + `testpath query` | `testmonitor product list` | ✅ Simpler |
| List results | `testresult query` | `testmonitor result list` | ✅ Equivalent |
| Get result details | `testresult get <id>` | `testmonitor result get <id>` | ✅ Equivalent |
| Include steps | `teststep query --filter resultId` | `result get --include-steps` | ✅ More intuitive |
| Product summary | `testpath summary` + `testmetadata get` | `product get --show-coverage` | ✅ Simpler |
| Measurements | `testmeasurement query` | `result get --include-measurements` | ✅ Logical grouping |
| Failed analysis | `testresult analyze` | `result list --summary` | ✅ Integrated |
| Cross-service | `testresult get-assets` | Future enhancement | ⚠️ API gap |

---

## Recommendation Summary

### ✅ Accept Current Implementation
The current `testmonitor` structure is **well-designed** and aligns with:
- SystemLink API organization
- User mental models
- Established slcli patterns

### 🔨 Enhance with Flags
Add capabilities through **flags** rather than new command groups:
- `--summary` for aggregated views
- `--include-steps` for nested data
- `--include-measurements` for measurement data
- `--show-coverage` for test coverage
- `--group-by` for organization

### ❌ Reject Command Explosion
Do NOT create separate:
- `testresult` (redundant)
- `teststep` (nested entity)
- `testpath` (product metadata)
- `testmeasurement` (nested entity)

### 🎯 Focus on User Workflows
Design commands around:
1. **Discovery:** "What products/results exist?"
2. **Filtering:** "Show me failed tests for product X"
3. **Detail:** "Show me everything about this result"
4. **Analysis:** "Summarize results by program/status"

---

## Conclusion

The current `testmonitor` implementation provides a **strong foundation** that can be enhanced to meet all workflow requirements **without creating command bloat**. By adding flags like `--include-steps`, `--summary`, and `--show-coverage`, we can provide the same capabilities with a much simpler, more intuitive command structure.

**Next Steps:**
1. ✅ Merge current PR with `product list` and `result list`
2. 🔨 Implement `product get` and `result get` commands
3. 🔨 Add enhancement flags (`--include-steps`, `--summary`, etc.)
4. 🔨 Add natural language date parsing
5. 📊 Gather user feedback on command structure

This approach keeps the CLI **simple, powerful, and maintainable** while fully satisfying the workflow analysis requirements.
