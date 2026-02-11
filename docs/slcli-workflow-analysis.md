# slcli Workflow Analysis for AI-Assisted Queries

## Executive Summary

This document analyzes selected workflows from the workflow examples spreadsheet to identify the multi-step processes, data requirements, and new slcli commands needed to enable Copilot to successfully answer complex SystemLink queries. The analysis focuses on high-priority workflows that require cross-service data correlation and proposes new slcli features to support them.

## Analyzed Workflows

### 1. Test Results: "Show me all failed measurements on product XYZ for the last two quarters"

**Priority:** High | **Complexity:** Medium | **Target:** Oct-26

#### Multi-Step Analysis Process

1. **Parse temporal range** - Convert "last two quarters" to date range
2. **Query test results** - Filter by:
   - Part number/product name (fuzzy match if needed)
   - Status = FAILED
   - Date range
3. **Aggregate measurements** - Group by test program, step, measurement
4. **Summarize findings** - Count failures by category
5. **Navigate if requested** - Filter UI grid or export data

#### Data Required

- **From Test Monitor Service:**
  - Results with `partNumber`, `status`, `startedAt`, `programName`
  - Steps with `status`, `name`, `path`, `resultId`
  - Measurements from step outputs/data
  - Count of matching results

- **From Product/Spec Service (optional):**
  - Validate product name, get alternate names/part numbers

#### API Calls Sequence

```bash
# Step 1: Query for failed results in date range
slcli testresult query \
  --filter 'partNumber contains "XYZ" and status.statusType = "FAILED"' \
  --started-after "2025-08-01" \
  --started-before "2026-01-31" \
  --projection "id,partNumber,programName,startedAt,status" \
  --take 1000

# Step 2: For each result, get failed steps/measurements
slcli teststep query \
  --filter 'resultId in ["id1","id2",...] and status.statusType = "FAILED"' \
  --projection "name,path,resultId,outputs,data"

# Step 3: Get measurement paths for product (to understand structure)
slcli testpath query \
  --filter 'partNumber = "XYZ"' \
  --projection "programName,path,pathNames,outputs,measurements"
```

#### Proposed New slcli Commands

```bash
# High-level result analysis command
slcli testresult analyze \
  --product "XYZ" \
  --status failed \
  --since "2 quarters ago" \
  --group-by measurement \
  --output summary

# Simplified measurement query
slcli testmeasurement query \
  --product "XYZ" \
  --status failed \
  --since "2025-08-01" \
  --until "2026-01-31" \
  --format json

# Combined result + step query with aggregation
slcli testresult query-with-steps \
  --filter 'partNumber = "XYZ" and status = "FAILED"' \
  --date-range "2025-08-01:2026-01-31" \
  --include-steps \
  --aggregate-by "path,measurement"
```

---

### 2. Test Results: "What was the SN of the PXI-4071 used to measure DUT SN 1234567?"

**Priority:** High | **Complexity:** Hard | **Target:** (future)

#### Multi-Step Analysis Process

1. **Query test results by DUT serial number**
2. **Get system ID from result** (systemId field)
3. **Query systems service** for system details at test time
4. **Query assets service** for assets in that system
5. **Filter assets** by model "PXI-4071"
6. **Cross-reference with test date** using asset location history
7. **Return asset serial number**

#### Data Required

- **From Test Monitor Service:**
  - Result with `serialNumber = "1234567"`, `systemId`, `startedAt`

- **From Systems Management Service:**
  - System with `id = systemId`, minion details

- **From Asset Service:**
  - Assets with `minionId` = system minion
  - Asset model = "PXI-4071"
  - Asset `locationHistory` overlapping with test date
  - Asset serial number

#### API Call Sequence

```bash
# Step 1: Find test result(s)
slcli testresult query \
  --filter 'serialNumber = "1234567"' \
  --projection "id,systemId,startedAt"

# Step 2: Get system information
slcli system get <systemId> \
  --projection "id,alias,hostname,workspaceId"

# Step 3: Get assets on that system at test time
slcli asset query \
  --filter 'location.minionId = "<minion-id>" and model contains "PXI-4071"' \
  --projection "id,serialNumber,model,location"

# Step 4: Verify asset was there during test (location history)
slcli asset location-history <asset-id> \
  --from "<test-date-minus-buffer>" \
  --to "<test-date-plus-buffer>"
```

#### Complexity Notes

This is **Hard** because:
- Requires cross-service correlation (Test → System → Asset)
- Needs temporal correlation (asset must be at location during test)
- Location history API may not exist or be performant
- Asset move events may not be tracked historically if asset was removed

#### Proposed New slcli Commands

```bash
# High-level asset correlation command
slcli testresult get-assets <result-id> \
  --filter 'model contains "PXI-4071"' \
  --output json

# Direct query with cross-service join
slcli asset query-for-test \
  --serial-number "1234567" \
  --model "PXI-4071" \
  --output table

# System snapshot at time
slcli system get-snapshot <system-id> \
  --at-time "2025-12-01T10:30:00Z" \
  --include assets

# Unified correlation command
slcli testresult correlate \
  --serial-number "1234567" \
  --show assets,system,conditions
```

---

### 3. Data Spaces: "Remove the selected data points"

**Priority:** High | **Complexity:** Low | **Target:** Oct-26

#### Multi-Step Analysis Process

1. **Get current data space context** - ID of active data space
2. **Get selected data point IDs** from UI selection
3. **Set keyword on data points** - Mark as hidden/removed
4. **Update data space configuration** - Exclude marked points
5. **Check for analytics** - Prompt user about updating analytics

#### Data Required

- **From Data Frame Service:**
  - Data space ID
  - Selected data point IDs or filter criteria
  - Current data space configuration
  - List of analytics using this data space

- **From UI Context:**
  - Active data space
  - Selected rows/points (could be lasso selection or grid selection)

#### API Call Sequence

```bash
# Step 1: Get data space details
slcli dataspace get <dataspace-id> \
  --include-config

# Step 2: Mark data points with keyword
slcli dataframe update-points <dataframe-id> \
  --point-ids "id1,id2,id3" \
  --set-keyword "hidden" \
  --reason "outlier-removed"

# Step 3: Update data space filter
slcli dataspace update <dataspace-id> \
  --exclude-keyword "hidden"

# Step 4: List affected analytics
slcli analytics list \
  --using-dataspace <dataspace-id>
```

#### Proposed New slcli Commands

```bash
# High-level data point management
slcli dataspace remove-points <dataspace-id> \
  --point-ids "id1,id2,id3" \
  --check-analytics \
  --confirm

# Bulk point operations
slcli dataframe set-keyword <dataframe-id> \
  --point-ids "id1,id2,id3" \
  --keyword "removed" \
  --value "true"

# Interactive point management
slcli dataspace manage-points <dataspace-id> \
  --interactive
```

---

### 4. Assets: "Find me a system that has a DMM and a scope"

**Priority:** High | **Complexity:** Medium | **Target:** Oct-26

#### Multi-Step Analysis Process

1. **Query assets for DMMs** - Filter by model/capabilities
2. **Query assets for scopes** - Filter by model/capabilities
3. **Find common minion IDs** - Intersection of asset locations
4. **Query systems** by minion IDs
5. **Return available systems**

#### Data Required

- **From Asset Service:**
  - Assets where `model contains "DMM"` or busType/assetType indicates DMM
  - Assets where `model contains "scope"` or model matches known scope patterns
  - Asset `location.minionId` for each
  - Asset availability status

- **From Systems Management Service:**
  - Systems where `id` in minion IDs
  - System state (connected, available)

#### API Call Sequence

```bash
# Step 1: Find DMMs
slcli asset query \
  --filter 'model contains "DMM" or model contains "407"' \
  --projection "id,model,location.minionId" \
  --take 500

# Step 2: Find scopes
slcli asset query \
  --filter 'model contains "scope" or model contains "5"' \
  --projection "id,model,location.minionId" \
  --take 500

# Step 3: Get systems by minion IDs (intersection)
slcli system list \
  --filter 'id in ["minion1","minion2"]' \
  --projection "id,alias,state"
```

#### Complexity Notes

This is **Medium** because:
- Requires correlating assets across different searches
- Model name matching can be fuzzy (DMM vs 4071 vs PXI-4071)
- Need to compute intersection client-side
- Assets may not have semantic "capabilities" field

#### Proposed New slcli Commands

```bash
# High-level system search by capability
slcli system find \
  --has-asset "DMM" \
  --has-asset "scope" \
  --available \
  --output table

# Asset-driven system query
slcli system query-by-assets \
  --requires "DMM,scope" \
  --match-all \
  --show-asset-details

# Capability-based search
slcli asset find-systems \
  --with-capabilities "voltage-measurement,waveform-acquisition" \
  --output json

# Combined availability check
slcli system find \
  --has-instrument "DMM" \
  --has-instrument "scope" \
  --available-after "2026-02-10" \
  --available-until "2026-03-10"
```

---

### 5. Systems: "Find me a system with package X installed"

**Priority:** High | **Complexity:** Hard | **Target:** Oct-26

#### Multi-Step Analysis Process

1. **Determine package name** - Exact or fuzzy match
2. **Query systems** - Get all systems (potentially large)
3. **For each system, get software packages** - May require per-system API call
4. **Filter by package name** - Check installed packages
5. **Return matching systems**

#### Data Required

- **From Systems Management Service:**
  - System IDs and metadata
  - System `packages` or `grains.packages` information
  - Package names and versions installed on each system

#### Current API Limitations

- No single query to filter systems by installed package
- May require:
  - Fetching all systems, then fetching packages for each (N+1 query problem)
  - OR new aggregated query API
  - OR CDC/search index on packages

#### API Call Sequence (Current State)

```bash
# Step 1: Get all systems
slcli system list \
  --projection "id,alias,workspaceId" \
  --take 5000

# Step 2: For each system, check packages (expensive!)
for system_id in $(slcli system list --format json | jq -r '.[].id'); do
  slcli system get $system_id --projection "packages" \
    | jq -r '.packages | keys | .[] | select(contains("PackageX"))'
done
```

#### Complexity Notes

This is **Hard** because:
- Performant implementation requires new query API or index
- Package data may be nested in `grains` and not directly queryable
- Large number of systems × packages = expensive operation
- Would benefit from Elasticsearch/CDC index on package data

#### Proposed New APIs & slcli Commands

**New API Requirements:**
- `GET /nisysmgmt/v1/systems/search` with package filter support
- OR `POST /nisysmgmt/v1/systems/query` with packages in projection
- OR new endpoint: `GET /nisysmgmt/v1/systems-by-software?packageName=X`

**New slcli Commands:**

```bash
# High-level system search by software
slcli system find \
  --with-package "DAQmx" \
  --version ">= 22.0" \
  --output table

# Software-specific query
slcli system query-by-software \
  --package-name "DAQmx" \
  --output json

# List systems with software
slcli software find-systems \
  --package "PackageX" \
  --include-version

# Fuzzy package search
slcli system find \
  --with-package-matching "daq.*" \
  --regex
```

---

### 6. Test Results: "Show me what type of test data exists for [Part Number]"

**Priority:** High | **Complexity:** Low | **Target:** Oct-26

#### Multi-Step Analysis Process

1. **Query paths API** for part number
2. **Get unique program names and paths**
3. **Summarize measurement types**
4. **Return structured summary**

#### Data Required

- **From Test Monitor Service (Paths API):**
  - Paths where `partNumber = "<part-number>"`
  - Fields: `programName`, `path`, `pathNames`, `measurements`, `outputs`

#### API Call Sequence

```bash
# Step 1: Query paths for product
slcli testpath query \
  --filter 'partNumber = "ABC123"' \
  --projection "programName,path,pathNames,measurements,outputs" \
  --format json

# Step 2: Summarize (client-side or server-side aggregation)
# Group by programName, collect unique paths
```

#### Proposed New slcli Commands

```bash
# Direct summary command
slcli testpath summary \
  --part-number "ABC123" \
  --output table

# Product test coverage
slcli testresult describe-product \
  --part-number "ABC123" \
  --show tests,measurements,programs

# Structured metadata query
slcli testmetadata get \
  --part-number "ABC123" \
  --format json
```

---

### 7. Alarms: "Recommend a solution for this alarm"

**Priority:** High | **Complexity:** Low | **Target:** Oct-26

#### Multi-Step Analysis Process

1. **Get alarm details** - ID, type, severity, tag, message
2. **Use LLM knowledge** - SystemLink alarm patterns (PXI overheating, disk space, etc.)
3. **Optionally search ni.com** or docs
4. **Return recommendation**

#### Data Required

- **From Alarm Service:**
  - Alarm `instanceId`, `alarmId`, `message`, `tagPath`
  - Alarm metadata and recent history
  - Related system information

- **From Tag Service (optional):**
  - Tag value and history

#### API Call Sequence

```bash
# Step 1: Get alarm details
slcli alarm get <instance-id> \
  --format json

# Step 2: Get related tag info (if applicable)
slcli tag get "<tag-path>" \
  --include-value
```

#### Notes

This is **Low** complexity because:
- Primarily relies on LLM's existing knowledge
- Alarm data is already contextual
- May benefit from page context in UI
- No complex cross-service correlation needed

#### Proposed New slcli Commands

```bash
# Alarm troubleshooting helper
slcli alarm diagnose <instance-id> \
  --output markdown

# Get alarm with context
slcli alarm get <instance-id> \
  --include tag,system,history \
  --format json
```

---

## Proposed New slcli Command Groups

### 1. `slcli testresult` enhancements

```bash
# Existing: query, get, list, create, update, delete
# New:
slcli testresult analyze <options>    # High-level analytics
slcli testresult get-assets <id>      # Get assets used in test
slcli testresult correlate <options>  # Cross-service correlation
slcli testresult query-with-steps     # Combined result+step query
slcli testresult describe-product     # Product test summary
```

### 2. `slcli teststep` (new)

```bash
slcli teststep query <options>        # Query steps with filters
slcli teststep get <id>               # Get step details
slcli teststep list                   # List steps for result
```

### 3. `slcli testpath` (new)

```bash
slcli testpath query <options>        # Query paths
slcli testpath summary <options>      # Summarize test coverage
slcli testpath get <id>               # Get path details
```

### 4. `slcli testmeasurement` (new)

```bash
slcli testmeasurement query <options> # Query measurements
slcli testmeasurement analyze         # Analyze measurement trends
```

### 5. `slcli system` enhancements

```bash
# Existing: list, get, disable
# New:
slcli system find <options>           # Find systems by criteria
slcli system get-snapshot <id>        # System state at point in time
slcli system query-by-assets          # Find by asset requirements
slcli system query-by-software        # Find by installed software
```

### 6. `slcli asset` enhancements

```bash
# Existing: get, list, query, create, update, delete
# New:
slcli asset query-for-test <id>       # Assets used in specific test
slcli asset find-systems <options>    # Systems with specific assets
slcli asset location-history <id>     # Location history over time
slcli asset capability-search         # Search by capabilities
```

### 7. `slcli dataspace` (new)

```bash
slcli dataspace get <id>              # Get data space details
slcli dataspace list                  # List data spaces
slcli dataspace remove-points         # Remove/hide data points
slcli dataspace update <id>           # Update configuration
slcli dataspace manage-points         # Interactive point management
```

### 8. `slcli dataframe` (new)

```bash
slcli dataframe get <id>              # Get dataframe details
slcli dataframe query <options>       # Query data points
slcli dataframe set-keyword           # Set keywords on points
slcli dataframe update-points         # Update data point metadata
```

### 9. `slcli alarm` enhancements

```bash
# Existing: (may not exist yet)
# New:
slcli alarm get <id>                  # Get alarm with context
slcli alarm list                      # List alarms with filters
slcli alarm query                     # Query alarms
slcli alarm diagnose <id>             # Get troubleshooting recommendations
slcli alarm history <id>              # Get alarm history
```

---

## API Gaps and Requirements

### Critical Gaps for High-Priority Workflows

1. **Test Monitor Service:**
   - ✅ Results query exists
   - ✅ Steps query exists
   - ✅ Paths query exists
   - ❌ **Missing:** Combined result+steps+measurements query (single call)
   - ❌ **Missing:** Aggregation/grouping support in query API
   - ❌ **Missing:** Statistical summary endpoints

2. **Systems Management Service:**
   - ✅ Systems list/get exists
   - ✅ Systems query/search exists
   - ❌ **Missing:** Filter by installed packages in query
   - ❌ **Missing:** System snapshot at historical time
   - ❌ **Missing:** Bulk package information across systems

3. **Asset Service:**
   - ✅ Assets query exists
   - ✅ Assets by minion/location exists
   - ❌ **Missing:** Asset location history API
   - ❌ **Missing:** Asset-to-test correlation endpoint
   - ❌ **Missing:** Capability-based search
   - ⚠️ **Limited:** Fuzzy model name matching

4. **Data Frame Service:**
   - ❓ **Unknown:** Current API capabilities
   - ❌ **Likely Missing:** Bulk point keyword updates
   - ❌ **Likely Missing:** Point filtering/hiding API
   - ❌ **Missing:** Data space configuration management

5. **Alarm Service:**
   - ⚠️ **May exist:** Basic CRUD for alarms
   - ❌ **Missing:** Alarm query with filters
   - ❌ **Missing:** Alarm diagnostics/context enrichment

### Performance Requirements

1. **Pagination:** All query commands must support `--skip` and `--take`
2. **Streaming:** Large result sets should support streaming/cursors
3. **Aggregation:** Server-side aggregation preferred over client-side
4. **Caching:** Consider caching for metadata queries (paths, products)

---

## Implementation Recommendations

### Phase 1: Oct-26 Target (Low Complexity, High Priority)

1. **Test Results Basic Queries:**
   - `slcli testresult query` with comprehensive filters
   - `slcli testpath summary` for product test coverage
   - `slcli teststep query` for step-level analysis

2. **Asset/System Discovery:**
   - `slcli system find --has-asset` (basic implementation using client-side join)
   - `slcli asset query` with enhanced filters

3. **Data Space Management:**
   - `slcli dataspace remove-points` (basic keyword-based hiding)
   - `slcli dataframe set-keyword` for bulk operations

4. **Alarm Context:**
   - `slcli alarm get` with rich context
   - `slcli alarm list` with filters

### Phase 2: Future (Medium-Hard Complexity)

1. **Cross-Service Correlation:**
   - `slcli testresult get-assets` (requires new API or complex orchestration)
   - `slcli asset query-for-test` (reverse lookup)

2. **Historical State:**
   - `slcli system get-snapshot --at-time` (requires historical data)
   - `slcli asset location-history` (requires history tracking)

3. **Advanced Search:**
   - `slcli system query-by-software` (requires CDC/Elasticsearch index)
   - `slcli asset capability-search` (requires capability metadata)

### Phase 3: Advanced Analytics

1. **Statistical Analysis:**
   - `slcli testresult analyze` with grouping/aggregation
   - `slcli testmeasurement analyze` for trends
   - Built-in math/stats capabilities

2. **Unified Queries:**
   - `slcli query` command group for cross-service queries
   - Graph-based querying (follow relationships)

---

## Design Patterns for slcli Commands

### 1. Consistent Filtering

All query commands should support:
- `--filter` - SystemLink filter expression
- `--format` - json, table, csv
- `--projection` - Select specific fields
- `--skip` / `--take` - Pagination
- `--order-by` - Sorting

Example:
```bash
slcli testresult query \
  --filter 'partNumber = "ABC" and status.statusType = "FAILED"' \
  --projection "id,startedAt,operator,systemId" \
  --order-by "startedAt desc" \
  --take 100 \
  --format json
```

### 2. Context-Aware Commands

Commands should infer context when possible:
- Current workspace from profile
- Current data space from UI context
- Recent result IDs from command history

Example:
```bash
# Use current data space from context
slcli dataspace remove-points --selection "current"

# Use last queried result
slcli testresult get-assets --result "last"
```

### 3. Composition and Piping

Enable Unix-style composition:
```bash
# Find systems, then get their assets
slcli system find --has-asset "DMM" --format json \
  | jq -r '.[].id' \
  | xargs -I {} slcli asset query --filter 'location.minionId = "{}"'

# Query results, extract IDs, get steps
slcli testresult query --filter 'status.statusType = "FAILED"' --format json \
  | jq -r '.[].id' \
  | slcli teststep query --result-ids -
```

### 4. Smart Defaults

- Default to current workspace
- Default date ranges (e.g., "last week", "yesterday")
- Default to interactive mode when ambiguous
- Default output format based on terminal (table) vs pipe (json)

### 5. Fuzzy Matching

Support fuzzy matching where appropriate:
- Product names: "XYZ" matches "Product-XYZ-Rev2"
- Asset models: "DMM" matches "PXI-4071", "NI-4065"
- Package names: "daq" matches "NI-DAQmx"

Use `--exact` flag to disable fuzzy matching.

---

## Copilot Integration Strategy

### Tool Design Principles

1. **Atomic Operations:** Each slcli command does one thing well
2. **Composable:** Commands can be chained/piped
3. **Informative Output:** JSON output includes metadata for reasoning
4. **Error Handling:** Clear error messages with suggestions
5. **Dry Run:** Support `--dry-run` to show what would happen

### Context Passing

Copilot should maintain context across tool calls:
- Store result IDs, system IDs from previous queries
- Remember current workspace, profile
- Track data spaces, products being analyzed

### Multi-Step Workflows

For hard queries, Copilot should:
1. Break query into steps
2. Execute each step with slcli
3. Correlate results client-side when needed
4. Summarize findings in natural language

Example workflow for "asset used in test":
```python
# Copilot reasoning:
# 1. Get test result by SN
result = slcli_testresult_query(filter='serialNumber = "1234567"')
result_id = result[0]['id']
system_id = result[0]['systemId']
test_date = result[0]['startedAt']

# 2. Get system details
system = slcli_system_get(system_id)
minion_id = system['id']

# 3. Get assets on system
assets = slcli_asset_query(filter=f'location.minionId = "{minion_id}" and model contains "PXI-4071"')

# 4. Verify asset was there at test time (if history API exists)
for asset in assets:
    history = slcli_asset_location_history(asset['id'], from=test_date_minus_day, to=test_date_plus_day)
    if overlaps(history, test_date):
        return asset['serialNumber']
```

---

## Appendix: OpenAPI Service Coverage

### Available Services (from attached docs)

1. **nitestmonitor** - Test Monitor Service (v2)
   - Results, Steps, Products, Paths
   - Query, Get, Create, Update, Delete operations
   - Filter, projection, pagination support

2. **nisysmgmt** - Systems Management Service
   - Systems (minions), packages, grains
   - Query, get, update operations
   - Limited package querying

3. **nialarm** - Alarm Service
   - Alarm instances, definitions
   - Query, get, acknowledge, clear operations

4. **nidataframe** - Data Frame Service
   - Data frames (likely data spaces)
   - Needs further investigation of capabilities

5. **nifile** - File Service
   - File upload, download, metadata
   - May be used for test data files

6. **ninotebook** - Notebook Service
   - Notebook execution
   - Could be used for analysis workflows

7. **niasset** (inferred from code search)
   - Asset query, create, update
   - Utilization, calibration
   - Location management

### Service Gaps

- **No unified query service** for cross-service joins
- **No graph query API** for relationship traversal
- **Limited aggregation** across services
- **No standardized "correlate" endpoints**

---

## Conclusion

Enabling Copilot to answer complex SystemLink queries requires:

1. **New slcli command groups:** testresult, teststep, testpath, testmeasurement, dataspace, dataframe, enhanced system/asset/alarm commands

2. **New API capabilities:**
   - Cross-service correlation endpoints
   - Historical state/snapshot APIs
   - Software/package filtering in systems queries
   - Asset location history
   - Data space point management

3. **Implementation phases:**
   - **Phase 1 (Oct-26):** Low-complexity commands using existing APIs + client-side correlation
   - **Phase 2 (Future):** Medium-complexity with new APIs for common patterns
   - **Phase 3 (Advanced):** Hard queries with graph traversal and analytics

4. **Design patterns:**
   - Consistent filtering, pagination, output formats
   - Context-aware defaults
   - Composable/pipeable commands
   - Fuzzy matching where appropriate

The analysis shows that many high-priority, low-complexity workflows can be implemented immediately with existing APIs, while harder workflows requiring cross-service correlation will need new APIs or client-side orchestration in Copilot's reasoning layer.
