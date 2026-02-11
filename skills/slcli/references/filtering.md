# Filtering Reference

Detailed guide to filtering syntax across slcli command groups.

---

## Convenience filters

Convenience filters are named options that map to common query patterns. When
multiple convenience filters are specified, they are combined with AND logic.

### Test Monitor results

| Flag                   | Match type | Example                    |
| ---------------------- | ---------- | -------------------------- |
| `--status TEXT`        | Exact      | `--status FAILED`          |
| `--program-name TEXT`  | Contains   | `--program-name "SOH_SCT"` |
| `--serial-number TEXT` | Contains   | `--serial-number "1234"`   |
| `--part-number TEXT`   | Contains   | `--part-number "BATT-8"`   |
| `--operator TEXT`      | Contains   | `--operator "xli"`         |
| `--host-name TEXT`     | Contains   | `--host-name "station-01"` |
| `--system-id TEXT`     | Exact      | `--system-id "abc-123"`    |
| `--workspace, -w TEXT` | Name or ID | `--workspace "Production"` |

### Test Monitor products

| Flag                   | Match type | Example                    |
| ---------------------- | ---------- | -------------------------- |
| `--name TEXT`          | Contains   | `--name "Battery"`         |
| `--part-number TEXT`   | Contains   | `--part-number "BATT"`     |
| `--family TEXT`        | Contains   | `--family "Sensors"`       |
| `--workspace, -w TEXT` | Name or ID | `--workspace "Production"` |

### Assets

| Flag                          | Match type     | Example                                          |
| ----------------------------- | -------------- | ------------------------------------------------ |
| `--model TEXT`                | Contains       | `--model "4071"`                                 |
| `--serial-number TEXT`        | Exact          | `--serial-number "01BB877A"`                     |
| `--bus-type CHOICE`           | Exact enum     | `--bus-type PCI_PXI`                             |
| `--asset-type CHOICE`         | Exact enum     | `--asset-type FIXTURE`                           |
| `--calibration-status CHOICE` | Exact enum     | `--calibration-status PAST_RECOMMENDED_DUE_DATE` |
| `--connected`                 | Flag (boolean) | `--connected`                                    |
| `--calibratable`              | Flag (boolean) | `--calibratable`                                 |
| `--workspace, -w TEXT`        | Name or ID     | `--workspace "Production"`                       |

### Systems

| Flag                   | Match type             | Example                        |
| ---------------------- | ---------------------- | ------------------------------ |
| `--alias, -a TEXT`     | Contains               | `--alias "PXI"`                |
| `--state CHOICE`       | Exact enum             | `--state CONNECTED`            |
| `--os TEXT`            | Contains               | `--os "Windows"`               |
| `--host TEXT`          | Contains               | `--host "lab-01"`              |
| `--has-package TEXT`   | Contains (client-side) | `--has-package "DAQmx"`        |
| `--has-keyword TEXT`   | Exact (repeatable)     | `--has-keyword "production"`   |
| `--property TEXT`      | key=value (repeatable) | `--property "location=Austin"` |
| `--workspace, -w TEXT` | Name or ID             | `--workspace "Production"`     |

---

## Advanced filter expressions

Use `--filter` for complex queries that go beyond convenience filters.

### Test Monitor LINQ syntax

Test Monitor uses Dynamic LINQ filter expressions.

```bash
# Status filter
--filter 'status.statusType = "FAILED"'

# Combined filters
--filter 'partNumber.Contains("ABC") and programName = "TestProgram"'

# Date-based filtering
--filter 'startedAt > DateTime(2026, 1, 1)'

# Numeric comparison
--filter 'totalTimeInSeconds > 300'
```

**Important:** Always use parameterized queries with `--substitution`:

```bash
# Good — parameterized
--filter 'programName = @0' --substitution "SOH_SCT_HPPC_0"

# Bad — string interpolation (security risk)
--filter "programName = '${PROGRAM}'"
```

Multiple substitutions are positional:

```bash
--filter 'programName = @0 and operator = @1' \
  --substitution "SOH_SCT_HPPC_0" \
  --substitution "xli"
```

### Product filtering with `--product-filter`

Filter results by properties of their associated product:

```bash
slcli testmonitor result list \
  --product-filter 'family = @0' \
  --product-substitution "Battery"
```

### Asset API expression syntax

Asset filtering uses the Asset API expression language:

```bash
# Property access with methods
--filter 'ModelName.Contains("PXI")'

# Exact match
--filter 'SerialNumber = "01BB877A"'

# Combined with logical operators
--filter 'BusType = "PCI_PXI" and CalibrationStatus = "OK"'

# Vendor filtering
--filter 'VendorName.Contains("PAtools")'

# Combined with convenience filters
slcli asset list --asset-type FIXTURE --filter 'VendorName.Contains("PAtools")'
```

### Systems Management filter syntax

System filtering uses nested property access:

```bash
# Connection state (nested property)
--filter 'connected.data.state = "CONNECTED"'

# OS filtering
--filter 'grains.data.kernel = "Windows"'

# Combined
--filter 'connected.data.state = "CONNECTED" and grains.data.kernel = "Windows"'

# Alias matching
--filter 'alias.Contains("PXI")'
```

---

## Sorting

Most list commands support `--order-by` and `--descending / --ascending`.

### Test Monitor result sort fields

`ID`, `STARTED_AT`, `UPDATED_AT`, `PROGRAM_NAME`, `SYSTEM_ID`, `HOST_NAME`,
`OPERATOR`, `SERIAL_NUMBER`, `PART_NUMBER`, `TOTAL_TIME_IN_SECONDS`, `PROPERTIES`

Default: `STARTED_AT` descending.

```bash
# Slowest tests first
slcli testmonitor result list --order-by TOTAL_TIME_IN_SECONDS --descending

# Oldest first
slcli testmonitor result list --order-by STARTED_AT --ascending
```

---

## Aggregation with --summary

The `--summary` flag returns aggregate counts instead of individual records.
Combine with `--group-by` for grouped aggregation.

```bash
# Total counts by status
slcli testmonitor result list --summary --group-by status -f json

# Counts by operator
slcli testmonitor result list --summary --group-by operator -f json

# Filtered summary — failures by program
slcli testmonitor result list --status FAILED --summary --group-by programName -f json

# Product summary
slcli testmonitor product list --summary -f json
```

Available `--group-by` values: `status`, `programName`, `serialNumber`,
`operator`, `hostName`, `systemId`.

---

## Pagination

- **Table output**: Paginated interactively (default 25 rows, Y/n prompt for next page).
- **JSON output**: Returns all results up to `--take` limit in a single array.
- **`--take, -t`**: Controls maximum items. Default 25 for most commands, 100 for systems.

```bash
# Get exactly 500 results as JSON
slcli testmonitor result list -f json --take 500

# Get first 10 in table
slcli testmonitor result list --take 10
```

---

## Enum values reference

### Status types (Test Monitor)

`PASSED`, `FAILED`, `RUNNING`, `ERRORED`, `TERMINATED`, `TIMEDOUT`, `WAITING`,
`SKIPPED`, `CUSTOM`

### Calibration status (Assets)

`OK`, `APPROACHING_RECOMMENDED_DUE_DATE`, `PAST_RECOMMENDED_DUE_DATE`,
`OUT_FOR_CALIBRATION`

### Asset types

`GENERIC`, `DEVICE_UNDER_TEST`, `FIXTURE`, `SYSTEM`

### Bus types (Assets)

`BUILT_IN_SYSTEM`, `PCI_PXI`, `USB`, `GPIB`, `VXI`, `SERIAL`, `TCP_IP`, `CRIO`

### System states

`CONNECTED`, `DISCONNECTED`, `VIRTUAL`, `APPROVED`
