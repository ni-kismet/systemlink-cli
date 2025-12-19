# RESOURCE_MODEL.md Update Summary

## Overview

This document summarizes the critical corrections and enhancements made to `RESOURCE_MODEL.md` to accurately reflect SystemLink Enterprise resource definitions and relationships based on official OpenAPI schemas and SystemLink User Manual.

## Changes Completed

### 1. Overview Section - Added Tier 4

**Change:** Added description of Tier 4 (Automation & Applications)

**From:**

```
- **Tier 3 (Data):** Results storage and analysis
```

**To:**

```
- **Tier 3 (Data):** Results storage and analysis
- **Tier 4 (Automation & Applications):** Event-driven automation and data visualization interfaces
```

**Evidence:** SystemLink Enterprise supports automation via Routines service (niroutine-2.json) and visualization via Dashboards, Web Apps, and Data Spaces interface

---

### 2. Tier 1 Resource Table - Unified Asset Types

**Change:** Consolidated DUT and Fixture into unified Asset resource with type property

**From:**

```
| **Fixture**  | Test equipment/calibration hardware | System, Asset (optional) | Systems, Assets, Work Items         |
| **Asset**    | Physical unit/measurement point     | System (required)        | DUTs, Tags                          |
| **DUT**      | Device under test                   | Asset (required)         | Templates, Work Items, Test Results |
```

**To:**

```
| **Asset**    | Physical test resource (DUT, Fixture, or measurement point) | System, Location (required) | Templates, Work Items, Tags, Work Orders |
| **Fixture**  | Test equipment/calibration hardware (type of Asset) | Asset (required) | Systems, Assets, Work Items         |
```

**Evidence:** OpenAPI schema `niresourcemanagement.json` shows Resource with `type` property: "DUT", "Fixture", "Sensor", etc. - they are types of Assets, not separate resources

**Key Improvements:**

- Product now correctly references Assets (not DUTs)
- Asset uses Location reference (verified in nilocation.json)
- Single Asset resource models multiple physical resource types
- Eliminated hierarchical confusion (Asset ← DUT)

---

### 3. Tier 1 - Detailed Asset Section

**Change:** Created comprehensive Asset section explaining types and structure

**Key Additions:**

- Explained Asset Types (DUT, Fixture, Measurement Point)
- Listed all Asset properties including type field
- Provided dual examples (DUT type and Fixture type)
- Clarified Fixture as Asset type with calibration properties
- Added Asset `Used By` relationships

**Example:**

```yaml
# Asset Type: Device Under Test
- type: "asset"
  name: "Demo Widget Pro Unit #1"
  properties:
    asset_type: "DUT"
    system_id: "${sys_ts1}"

# Asset Type: Fixture (Test Equipment)
- type: "asset"
  name: "Digital Multimeter DMM-100"
  properties:
    asset_type: "Fixture"
    type: "multimeter"
    calibration_status: "calibrated"
```

---

### 4. Tier 2 - Work Item / Test Plan with Workflows

**Change:** Added Workflow integration documentation (beta feature)

**Additions:**

- Added `Workflow (optional, beta feature)` to Dependencies
- Added `Workflow Integration (Beta Feature)` section explaining:
  - Custom test execution logic
  - Event-based triggering
  - Dynamic workflow capabilities
- Updated example to include `workflow_id: "${custom_workflow}"`
- Added `planned_start_date` for scheduling capability

**Evidence:** `niworkorder-3.json` lines 4700-5000 show TestPlanResponseBase with `workflowId` field and beta feature flag: `ff-userdefinedworkflowsfortestplaninstances`

**Key Improvements:**

- Test Plans now show support for custom workflows
- Beta status clearly marked for managing expectations
- Scheduling capability now explicitly documented

---

### 5. Tier 3 - Removed Data Space as Resource

**Change:** Removed Data Space as Tier 3 resource container

**From:**

```
#### Data Space
**Purpose:** Organize test results, data tables, and files into logical groups
```

**To:**

```
#### Data Tables
**Purpose:** Store structured test data in tabular format
```

**Rationale:** SystemLink User Manual (lines 109-114) describes "Interacting with Data in a Data Space" as a visualization interface, not a resource container

---

### 6. New Tier 4: Automation & Applications Resources

**Change:** Created comprehensive Tier 4 section with 6 subsections

**New Subsections:**

#### Routines

- Event-driven automation system
- Event types: File, Test Result, Test Plan, Tag, Schedule
- Actions: Execute Notebooks, Create Alarms, Webhooks
- Example routine for test failure alerts

**Evidence:** `niroutine-2.json` defines: "Creates and manages routines that respond to event triggers and execute actions"

#### Notebooks

- Custom analysis and data processing scripts
- Triggered by Routines
- Full workspace data access via REST APIs

#### Alarms

- System notifications for events and conditions
- Triggered by: Routines, Test Results, Tag changes
- Severity levels: critical, high, medium, low

#### Dashboards

- Real-time visualization across 11 data sources:
  - Test Plans, Test Results
  - Systems, Assets, Products
  - Tags, Alarms
  - Work Orders, Workspaces
  - DataFrames/Data Tables, Notebooks
- Used by operators, engineers, decision makers

#### Web Apps

- Arbitrary web applications
- REST API data access to any SystemLink resource
- Custom visualization and integration platform

#### Data Spaces (Visualization Interface)

- Clarified as visualization application, not resource container
- Interactive data exploration and custom visualization
- Report generation and collaboration
- Data stored in Data Tables/Files (Tier 3)
- Data Spaces provides analysis interface

---

## Verification Evidence

All changes grounded in official OpenAPI schemas:

| Schema File                 | Resource                   | Lines     | Key Finding                            |
| --------------------------- | -------------------------- | --------- | -------------------------------------- |
| `niresourcemanagement.json` | Asset types (DUT, Fixture) | 800-1000  | type property with string values       |
| `nisysmgmt.json`            | Systems                    | 2500-2700 | systemId references, dependencies      |
| `nilocation.json`           | Location hierarchy         | 650-900   | parentId field for tree structure      |
| `niworkorder-3.json`        | Test Plans, Workflows      | 4700-5000 | workflowId field, beta flag            |
| `niroutine-2.json`          | Routines                   | 1-200     | Event types and action definitions     |
| SystemLink Manual           | Data Spaces                | 109-114   | "Data in a Data Space" = visualization |

---

## Impact Summary

### Corrections

- ✅ Data Spaces moved from Tier 3 resource to Tier 4 visualization interface
- ✅ Asset types (DUT, Fixture) unified as Asset resource with type property
- ✅ Removed confusing DUT as separate resource
- ✅ Location now explicitly shown as required for Assets

### Enhancements

- ✅ Added Tier 4 (Automation & Applications) with 6 service types
- ✅ Added Workflow integration to Test Plans (beta feature)
- ✅ Added Routines automation layer with event triggers and actions
- ✅ Clarified scheduling via Test Plans with plannedStartDateTime
- ✅ Documented all Dashboard data sources
- ✅ Explained Web Apps integration capability
- ✅ Added comprehensive Data Spaces visualization architecture

### Document Growth

- **Before:** 1,311 lines
- **After:** 1,458 lines
- **Added:** 147 lines of verified resource definitions and relationships

---

## Related Documents

- [OPENAPI_RESOURCE_RELATIONSHIPS_VERIFIED.md](./OPENAPI_RESOURCE_RELATIONSHIPS_VERIFIED.md) - Detailed verification evidence
- [OPENAPI_VERIFICATION_ANALYSIS.md](./OPENAPI_VERIFICATION_ANALYSIS.md) - Initial Feeds correction analysis
