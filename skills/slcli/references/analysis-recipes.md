# Analysis Recipes

Step-by-step recipes for answering common data analysis questions with `slcli`.
Each recipe maps to a real-world scenario and shows the exact commands needed.

---

## Recipe 1: Operator failure rate analysis

**Question:** Which operators have the highest failure rates and what should they
focus on?

**Steps:**

```bash
# Step 1: Get summary by operator to see total counts per operator
slcli testmonitor result list --summary --group-by operator -f json

# Step 2: Get failed counts per operator
slcli testmonitor result list --status FAILED --summary --group-by operator -f json

# Step 3: Deep-dive into a specific operator's failures
slcli testmonitor result list --operator "xli" --status FAILED -f json --take 500

# Step 4: See which programs the operator fails on most
slcli testmonitor result list --operator "xli" --status FAILED --summary --group-by programName -f json
```

**Post-processing with jq:**

```bash
# Calculate failure rate per operator (combine step 1 and 2 outputs)
slcli testmonitor result list --operator "xli" -f json --take 500 | \
  jq '[group_by(.status.statusType) | .[] | {status: .[0].status.statusType, count: length}]'
```

---

## Recipe 2: Calibration overdue tracking

**Question:** Which assets are most overdue for calibration and what test
capacity is at risk?

**Steps:**

```bash
# Step 1: List all assets past calibration due date
slcli asset list --calibration-status PAST_RECOMMENDED_DUE_DATE -f json --take 100

# Step 2: Get the fleet-wide calibration summary
slcli asset summary -f json

# Step 3: Check assets approaching due date (proactive)
slcli asset list --calibration-status APPROACHING_RECOMMENDED_DUE_DATE -f json

# Step 4: Get calibration history for a specific overdue asset
slcli asset calibration <ASSET_ID> -f json

# Step 5: Check which system the asset belongs to
slcli asset location-history <ASSET_ID> -f json
```

**Post-processing with jq:**

```bash
# Group overdue assets by model
slcli asset list --calibration-status PAST_RECOMMENDED_DUE_DATE -f json --take 200 | \
  jq '[group_by(.modelName) | .[] | {model: .[0].modelName, count: length}] | sort_by(-.count)'

# Find overdue assets in connected systems (blocking test execution)
slcli asset list --calibration-status PAST_RECOMMENDED_DUE_DATE --connected -f json --take 200 | \
  jq 'length'
```

---

## Recipe 3: Test time distribution and bottleneck identification

**Question:** What is the test time distribution across stations and where are
bottlenecks?

**Steps:**

```bash
# Step 1: Get results with execution time, grouped by host
slcli testmonitor result list -f json --take 500 --order-by TOTAL_TIME_IN_SECONDS --descending

# Step 2: Summarize by host to find busiest stations
slcli testmonitor result list --summary --group-by hostName -f json

# Step 3: Drill into slowest host
slcli testmonitor result list --host-name "station-01" -f json --take 200 \
  --order-by TOTAL_TIME_IN_SECONDS --descending
```

**Post-processing with jq:**

```bash
# Calculate average test duration per host
slcli testmonitor result list -f json --take 1000 | \
  jq '[group_by(.hostName) | .[] | {
    host: .[0].hostName,
    count: length,
    avg_seconds: ([.[].totalTimeInSeconds] | add / length),
    max_seconds: ([.[].totalTimeInSeconds] | max)
  }] | sort_by(-.avg_seconds)'

# Find outlier tests (> 2x average duration)
slcli testmonitor result list -f json --take 1000 | \
  jq '(([.[].totalTimeInSeconds] | add / length) * 2) as $threshold |
      [.[] | select(.totalTimeInSeconds > $threshold)] | length'
```

---

## Recipe 4: System capability discovery

**Question:** Which connected systems lack specific measurement capabilities?

**Steps:**

```bash
# Step 1: List all connected systems
slcli system list --state CONNECTED -f json --take 200

# Step 2: Get assets for a specific system
slcli asset list --filter 'ParentId = @0' --substitution "<SYSTEM_ID>" -f json

# Step 3: Generate a hardware report
slcli system report --type HARDWARE -o hardware_report.csv

# Step 4: Check systems with specific packages
slcli system list --has-package "DAQmx" --state CONNECTED -f json
```

**Post-processing with jq:**

```bash
# List connected systems and their OS
slcli system list --state CONNECTED -f json --take 500 | \
  jq '[.[] | {alias, id, os: .grains.kernel}]'
```

---

## Recipe 5: Product yield analysis

**Question:** How many units per product variant are past their first-pass yield
expectations?

**Steps:**

```bash
# Step 1: List products with battery part numbers
slcli testmonitor product list --part-number "BATT" -f json

# Step 2: Get summary for a specific product
slcli testmonitor product list --part-number "BATT-8" --summary -f json

# Step 3: Get pass/fail breakdown for a product
slcli testmonitor result list --part-number "BATT-8" --summary --group-by status -f json

# Step 4: Compare across all battery products
for i in $(seq 0 14); do
  echo "BATT-$i:"
  slcli testmonitor result list --part-number "BATT-$i" --summary --group-by status -f json
done
```

**Post-processing with jq:**

```bash
# Calculate yield rate for a part number
slcli testmonitor result list --part-number "BATT-8" -f json --take 1000 | \
  jq '{
    total: length,
    passed: [.[] | select(.status.statusType == "PASSED")] | length,
    failed: [.[] | select(.status.statusType == "FAILED")] | length
  } | . + {yield_pct: (100 * .passed / .total | round)}'
```

---

## Recipe 6: Test program runtime analysis

**Question:** Which test programs have the longest runtimes?

**Steps:**

```bash
# Step 1: Summarize by program name
slcli testmonitor result list --summary --group-by programName -f json

# Step 2: Get detailed results for the longest program
slcli testmonitor result list --program-name "SOH_SCT_HPPC" -f json --take 200 \
  --order-by TOTAL_TIME_IN_SECONDS --descending

# Step 3: Compare program variants
slcli testmonitor result list --program-name "SOH_SCT_HPPC_0" -f json --take 100
slcli testmonitor result list --program-name "SOH_SCT_HPPC_5" -f json --take 100
```

**Post-processing with jq:**

```bash
# Top 5 programs by average runtime
slcli testmonitor result list -f json --take 2000 | \
  jq '[group_by(.programName) | .[] | {
    program: .[0].programName,
    count: length,
    avg_seconds: ([.[].totalTimeInSeconds] | add / length | . * 100 | round / 100),
    total_hours: ([.[].totalTimeInSeconds] | add / 3600 | . * 100 | round / 100)
  }] | sort_by(-.avg_seconds) | .[:5]'
```

---

## Recipe 7: Location-based failure analysis

**Question:** Are there facility-specific issues causing higher failure rates?

**Steps:**

```bash
# Step 1: List all systems to understand location naming conventions
slcli system list -f json --take 200 | jq '[.[].alias] | unique'

# Step 2: Get failure counts per system
slcli testmonitor result list --status FAILED --summary --group-by systemId -f json

# Step 3: Get total counts per system for rate calculation
slcli testmonitor result list --summary --group-by systemId -f json

# Step 4: Drill into a system with high failure rate
slcli testmonitor result list --system-id "<SYSTEM_ID>" --status FAILED -f json --take 100
```

---

## Recipe 8: Fixture calibration and capacity planning

**Question:** Which PAtools fixtures need recalibration soon and what capacity
would we lose?

**Steps:**

```bash
# Step 1: List all PAtools fixtures
slcli asset list --filter 'VendorName.Contains("PAtools")' --asset-type FIXTURE -f json

# Step 2: Filter for those approaching calibration due date
slcli asset list --filter 'VendorName.Contains("PAtools")' --asset-type FIXTURE \
  --calibration-status APPROACHING_RECOMMENDED_DUE_DATE -f json

# Step 3: Get overall fixture summary
slcli asset summary -f json
```

**Post-processing with jq:**

```bash
# Count fixtures by calibration status
slcli asset list --filter 'VendorName.Contains("PAtools")' --asset-type FIXTURE -f json --take 100 | \
  jq '[group_by(.calibrationStatus) | .[] | {status: .[0].calibrationStatus, count: length}]'
```

---

## Recipe 9: Product family workload distribution

**Question:** How is test execution distributed across product families?

**Steps:**

```bash
# Step 1: List all products to see families
slcli testmonitor product list -f json --take 100

# Step 2: Summarize by product family
slcli testmonitor product list --summary -f json

# Step 3: Get result volume per part number
slcli testmonitor result list --summary --group-by programName -f json
```

**Post-processing with jq:**

```bash
# Group products by family prefix
slcli testmonitor product list -f json --take 100 | \
  jq '[group_by(.family) | .[] | {family: .[0].family, products: length}] | sort_by(-.products)'

# Get execution volume grouped by part-number prefix
slcli testmonitor result list -f json --take 2000 | \
  jq '[group_by(.partNumber | split("-")[0]) | .[] | {
    family: .[0].partNumber | split("-")[0],
    executions: length,
    total_hours: ([.[].totalTimeInSeconds] | add / 3600 | . * 10 | round / 10)
  }] | sort_by(-.executions)'
```

---

## Recipe 10: Environmental condition failure patterns

**Question:** Are failures concentrated in specific operating condition ranges?

**Steps:**

```bash
# Step 1: Get failed results with properties
slcli testmonitor result list --status FAILED -f json --take 500

# Step 2: Get detailed result with step data for environmental readings
slcli testmonitor result get <RESULT_ID> --include-steps -f json

# Step 3: Compare passed vs. failed property distributions
slcli testmonitor result list --status PASSED -f json --take 500
slcli testmonitor result list --status FAILED -f json --take 500
```

**Post-processing with jq:**

```bash
# Extract temperature and voltage from failed results
slcli testmonitor result list --status FAILED -f json --take 500 | \
  jq '[.[] | select(.properties != null) | {
    partNumber,
    programName,
    properties: (.properties | to_entries | map(select(.key | test("Temp|Volt|Capacity"; "i"))))
  }] | [.[] | select(.properties | length > 0)]'

# Compare property distributions between passed and failed
slcli testmonitor result list --status FAILED --part-number "BATT-8" -f json --take 200 | \
  jq '[.[].totalTimeInSeconds] | {min: min, max: max, avg: (add / length | round)}'
```

---

## General tips

- **Start with `--summary`** to understand data shape before fetching raw records.
- **Use `--group-by`** with `--summary` for aggregation: `status`, `programName`,
  `serialNumber`, `operator`, `hostName`, `systemId`.
- **Chain with `jq`** for complex transformations — always use `-f json`.
- **Use `--take` wisely** — start small (100-500), increase if needed.
- **For rate calculations**, query total count and filtered count separately, then divide.
- **Use `--order-by TOTAL_TIME_IN_SECONDS --descending`** to find slowest tests quickly.
- **Asset `--connected` flag** limits to assets in currently connected systems.
- **System `--has-package`** filter is client-side — use with `--state CONNECTED` to reduce volume.
