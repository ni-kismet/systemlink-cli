# Demo Complete Workflow Example

A **comprehensive example** demonstrating the full SystemLink test execution workflow from resource provisioning through test results and data management.

## Overview

This example showcases:
- **Tier 0 (Foundational)**: Locations, products, test systems
- **Tier 1 (Cross-cutting)**: DUTs (devices under test), assets, fixtures, reference equipment
- **Tier 2 (Work & Execution)**: Custom workflows, test templates, work items, work orders
- **Tier 3 (Data & Results)**: Test results, structured data tables, test logs and reports

Perfect for understanding how SystemLink coordinates complex multi-phase test campaigns with complete traceability from planning through data management.

## Resource Hierarchy

```
Location: Production Test Lab
├── Product: Advanced Control System v3.0
│   ├── System: Test Bench 1 → DUT-001
│   ├── System: Test Bench 2 → DUT-002
│   ├── Assets: Reference instruments & data logger
│   │
│   └── Workflow: ACS Validation Workflow
│       └── Test Template: ACS Validation Suite
│           ├── Work Item 1: Validation Run 1 (Unit 001)
│           │   ├── Test Result 1: Voltage Regulation Test
│           │   │   └── Data Table: Voltage measurements (25 rows)
│           │   ├── Test Result 2: Response Time Test
│           │   │   └── Data Table: Step response measurements (5 rows)
│           │   ├── Test Result 3: Thermal Test
│           │   │   └── Data Table: Temperature profile (33 rows)
│           │   └── Files: Test logs, raw data, waveforms
│           │
│           └── Work Item 2: Regression Test (Unit 002)
│               ├── Test Result 4: Voltage Regression Test
│               │   └── Data Table: Regression comparison (5 rows)
│               └── Files: Regression data, comparison report
│
└── Work Order: ACS Validation Campaign
    ├── Schedules: Work Item 1 & 2
    ├── Reserves: Test Bench 1 & 2, DUT-001, DUT-002
    └── Test Result 5: Campaign Summary
        └── Files: Executive report, test matrix
```

## Key Features

### 1. **Custom Workflow** (Tier 2)
- Event-driven execution model with 5 sequential procedures
- Integrates with test template for automated test planning
- Tracks initialization, testing phases, data collection, and cleanup

### 2. **Test Template** (Tier 2)
- Reusable test plan for ACS validation
- Detailed procedures for voltage regulation, response time, and thermal testing
- Explicit acceptance criteria (< 2% ripple, < 100ms response, < 80°C thermal)
- References custom workflow for execution coordination

### 3. **Work Items & Work Order** (Tier 2)
- **Work Item 1**: Validates ACS unit 001 on primary bench (high priority)
- **Work Item 2**: Regression tests ACS unit 002 on secondary bench (medium priority)
- **Work Order**: Coordinates both work items with resource reservation (start: 08:00, end: 12:00)

### 4. **Test Results** (Tier 3)
- **5 result records** capturing execution outcomes:
  - Voltage regulation (Run 1)
  - Response time (Run 1)
  - Thermal performance (Run 1)
  - Voltage regression (Run 2)
  - Campaign summary
- Each result tracks operator, timestamps, measurements, verdict, and linked files

### 5. **Data Tables** (Tier 3)
- **Voltage Regulation**: 25 rows of load sweep data (0A-5A)
- **Response Time**: 5 rows of step response measurements
- **Thermal Profile**: 33 rows of temperature evolution (0-30 minutes)
- **Regression Comparison**: 5 rows comparing Run 1 vs Run 2 across load points
- All structured with proper column definitions, units, and sample data

### 6. **Files & Documentation** (Tier 1 & 3)
- Raw test data (`.csv` files)
- Waveform captures (`.tds` oscilloscope format)
- Test execution logs (`.txt`)
- Campaign reports (`.pdf`, `.xlsx`)
- All properly tagged and cross-referenced to test results

## Installation

### Prerequisites
- SystemLink server (v2024.1 or later)
- Target workspace with product/system/asset management enabled
- SystemLink CLI configured with valid credentials

### Quick Install

```bash
# Provision all resources (dry-run first to verify)
slcli example install demo-complete-workflow -w <workspace> --dry-run

# Actual provisioning
slcli example install demo-complete-workflow -w <workspace>

# Cleanup (removes all tagged resources)
slcli example uninstall demo-complete-workflow -w <workspace> --dry-run
slcli example uninstall demo-complete-workflow -w <workspace>
```

### Expected Output

```
Installation Progress
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Resource Name                  Type        Action    Server ID                      Error
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Production Test Lab            location    create    <location-id>
Advanced Control System v3.0   product     create    <product-id>
Control System Test Bench 1    system      create    <system-id-1>
Control System Test Bench 2    system      create    <system-id-2>
DUT-ACS-001 (Bench 1)          dut         create    <asset-id-1>
DUT-ACS-002 (Bench 2)          dut         create    <asset-id-2>
Reference Voltage Source       asset       create    <asset-id-3>
Data Logger                    asset       create    <asset-id-4>
ACS Validation Workflow        workflow    create    <workflow-id>
ACS Validation Suite           testtemplate create   <template-id>
ACS Validation Run 1 - Unit 001 work_item  create    <work-item-id-1>
ACS Regression Test - Unit 002 work_item   create    <work-item-id-2>
ACS Validation Campaign        work_order  create    <work-order-id>
ACS Run 1 - Result 1           test_result create    <result-id-1>
[... 4 more results ...]
Voltage Regulation Results     data_table  create    <table-id-1>
[... 3 more data tables ...]
voltage_regulation_run1.csv    file        create    <file-id-1>
[... 3 more files ...]

Summary: 20 resources successfully created
Estimated setup time: 10 minutes
```

## Resource Details

### Foundational Resources
- **Location**: Production Test Lab (Austin, TX)
- **Product**: Advanced Control System v3.0 (part # DCS-3000)
- **Systems**: 
  - Test Bench 1 (CSTB-001) → Primary validation bench
  - Test Bench 2 (CSTB-002) → Regression testing bench

### Test Assets
- **DUT-001**: ACS unit 001 (serial: ACS-SN-20250101-001)
- **DUT-002**: ACS unit 002 (serial: ACS-SN-20250102-002)
- **Reference Equipment**:
  - Reference Voltage Source (GPIB-connected)
  - Data Logger (Ethernet-connected)

### Test Execution Configuration
- **Campaign Duration**: 2 hours (08:00-10:10)
- **DUTs Tested**: 2
- **Test Phases**: 3 (voltage, response time, thermal)
- **Test Results**: 5 (3 for Run 1, 1 for Run 2, 1 summary)
- **Measurements**: 73 total data points across 4 tables

### Acceptance Criteria
- **Voltage Regulation**: Ripple < 2% across 0-5A load range
- **Response Time**: Rise time < 100ms for step input
- **Thermal**: Peak internal temperature < 80°C at full load
- **Campaign**: All measurements pass specification limits

## Data Exploration

After installation, query the resources:

```bash
# List all created locations
slcli location list -w <workspace> --format table

# Find the ACS product
slcli product list -w <workspace> --take 50 | grep "Advanced Control"

# View test systems
slcli system list -w <workspace> | grep "Test Bench"

# Query test results
slcli result list -w <workspace> --take 20

# Export measurement data
slcli datatable export <workspace> <table-id> -o measurements.csv
```

## Workflow Understanding

### Phase 1: Planning (Tier 0-1 Provisioning)
Resources created: Location, Product, Systems, Assets

### Phase 2: Test Planning (Tier 2 Provisioning)
Resources created: Workflow, Test Template, Work Items, Work Order

### Phase 3: Test Execution (Tier 2 Execution)
- Work Order triggers scheduled start at 08:00
- Work Item 1 executes on Bench 1 (08:15-09:30)
- Work Item 2 executes on Bench 2 (09:45-10:10)
- Each item executes 3 test phases with measurements logged

### Phase 4: Results Collection (Tier 3 Population)
- Test Results created as executions complete
- Data Tables populated with measurement data
- Files stored (logs, reports, raw data)
- Campaign Summary aggregates all results

## Use Cases

1. **Learning**: Understand how SystemLink coordinates multi-phase tests with complete traceability
2. **Testing**: Validate test execution workflow in your environment
3. **Template**: Adapt for your own validation campaigns
4. **Benchmarking**: Measure SystemLink performance with realistic workload
5. **Documentation**: Examples for training and integration documentation

## Customization

To adapt for your environment:

1. **Replace Product Names**: Update `Advanced Control System v3.0` to your product
2. **Adjust Test Phases**: Modify workflow procedures and test template phases
3. **Change DUT Count**: Add more work items referencing different DUTs
4. **Scale Results**: Increase test result count to simulate longer campaigns
5. **Update Measurements**: Replace sample data with your actual test specifications

## Files Included

```
demo-complete-workflow/
├── config.yaml          # Complete resource configuration
└── README.md           # This file
```

## Cleanup

Remove all created resources:

```bash
slcli example uninstall demo-complete-workflow -w <workspace>
```

This removes all resources tagged with `slcli-example:demo-complete-workflow`, leaving your workspace clean.

## Troubleshooting

### Resources Already Exist
If you see "skipped" status:
```bash
# List existing resources to verify
slcli location list -w <workspace> | grep "Production Test Lab"

# Either reuse existing IDs or use different resource names
```

### Partial Installation Failure
Resources are created individually. If installation fails mid-way:
```bash
# Check what was created
slcli location list -w <workspace>
slcli product list -w <workspace>
slcli system list -w <workspace>

# Run uninstall to clean up and retry
slcli example uninstall demo-complete-workflow -w <workspace>
slcli example install demo-complete-workflow -w <workspace>
```

### Test Results Not Appearing
Test results are created as part of the provisioning flow:
```bash
# Verify work items were created
slcli workitem list -w <workspace>

# Check for test results
slcli result list -w <workspace>

# If missing, check error messages in installation output
```

## Additional Resources

- **SystemLink API Documentation**: https://dev-api.lifecyclesolutions.ni.com/
- **Test Monitor Specs**: https://dev-api.lifecyclesolutions.ni.com/nitestmonitor/swagger/
- **Work Item API**: https://dev-api.lifecyclesolutions.ni.com/niworkitem/swagger/
- **systemlink-cli GitHub**: https://github.com/ni/systemlink-cli

## Contact & Support

For issues or questions about this example:
- File an issue: [GitHub Issues](https://github.com/ni/systemlink-cli/issues)
- Check existing examples in `slcli/examples/`
- Review the CLI help: `slcli example --help`

---

**Created**: 2025-12-18  
**Format Version**: 1.0  
**Recommended SystemLink Version**: 2024.1+
