# OpenAPI Schema Verification Analysis

Date: December 18, 2025  
Source: SystemLink Enterprise OpenAPI Documentation Schemas

## Executive Summary

This document provides authoritative verification of SystemLink resource definitions based on official OpenAPI schemas. **Critical corrections identified** regarding resource purposes and relationships.

---

## CRITICAL CORRECTIONS

### 1. **FEEDS** - MAJOR CORRECTION REQUIRED

**OpenAPI Definition (nifeed.json):**

```
"title": "SystemLink Feed Service",
"description": "Enables hosting a package repository within SystemLink"
```

**Official Purpose:** Package repository hosting (like npm, pip, or apt)

- Stores and distributes software packages (.nipkg, .ipk, .deb files)
- Supports Windows and NI Linux RT platforms
- Enables "define once, deploy many" for software packages
- NOT for real-time data acquisition from sensors

**Current RESOURCE_MODEL.md Definition:**

- ❌ Incorrectly describes Feeds as "Real-time data acquisition from sensors, PLCs"

**Correction Required:**

- Feeds = Package Repository Management
- Data acquisition comes from **Tags** (key-value timeseries data)

---

### 2. **TAGS** - CONFIRMED CORRECT (with refinement)

**OpenAPI Definition (nitag-2.yaml):**

```
"description": "Publish and manage timestamped key-value-pair data."
```

**Official Purpose:** Timestamped key-value pair data storage and retrieval

- Real-time and historical measurement data (temperature, pressure, voltage, etc.)
- Supports aggregate values (min, max, avg, count)
- Subscription-based updates
- Historian for long-term retention (nitaghistorian.yaml)

**Current RESOURCE_MODEL.md Status:** ✓ Correct (measurement data, health monitoring)

---

### 3. **STATES** - CONFIRMED CORRECT

**OpenAPI Definition (nisystemsstate.json):**

```
"title": "SystemLink Systems State Service",
"description": "API for creating and storing systems states."
```

**Official Purpose:** System image and package set definition

- A state = complete configuration/package set for a system
- Can be applied to multiple systems
- NOT status values
- Enables consistent infrastructure configuration

**Current RESOURCE_MODEL.md Status:** ✓ Correct (package/image deployment)

---

## Tier 0: Organizational & Configuration Resources

### Tags

- **Type:** Timestamped key-value data store
- **Purpose:** Transmit and store measurement/health data
- **Scope:** Real-time and historical data management
- **Service:** nitag-2.yaml, nitaghistorian.yaml
- **Key Operations:** publish, query, subscribe, aggregate
- **Retention:** Historic data via Tag Historian service

### States

- **Type:** System configuration package set
- **Purpose:** Define and deploy standardized system configurations
- **Scope:** Infrastructure configuration management
- **Service:** nisystemsstate.json
- **Key Operations:** create, apply, version, history
- **Relationships:** Applied to Systems

### Feeds

- **Type:** Package repository
- **Purpose:** Host and distribute software packages
- **Scope:** Software package management
- **Service:** nifeed.json
- **Platforms:** Windows (.nipkg), NI Linux RT (.ipk, .deb)
- **Key Operations:** create, publish packages, clean, query

### Workspace

- **Type:** Organizational container
- **Purpose:** Multi-tenant isolation and organization
- **Scope:** Workspace scoping for all resources
- **Service:** Multi-service workspace parameter
- **Key Operations:** workspace-level isolation and access control

---

## Tier 1: Infrastructure Resources

### System

**OpenAPI Definition (nisysmgmt.json):**

- Logical container for test infrastructure
- References Location (physical placement)
- Applied State (package configuration)
- Deployed systems can execute jobs
- Health monitoring via alarms

### Asset

**OpenAPI Definition (niresourcemanagement.json):**

- Physical measurement point or unit
- Belongs to a System
- Can have attached monitoring (via Tags, not Feeds)
- Metadata and custom properties

### Location

**OpenAPI Definition (nilocation.json):**

- Physical/organizational location hierarchy
- Parent-child relationships
- Referenced by Systems
- Metadata tracking

### Product

**OpenAPI Definition (niresourcemanagement.json):**

- Device model or specification
- Referenced by Systems and DUTs
- Test configuration reference

### Fixture

**OpenAPI Definition (niresourcemanagement.json):**

- Test equipment or hardware
- Calibration tracking
- References Product, System, Asset
- Reservable for test plans

### DUT (Device Under Test)

**OpenAPI Definition (niresourcemanagement.json):**

- Specific device instance being tested
- References Asset
- State tracking (ready, testing, failed, etc.)

---

## Tier 2: Work & Execution Resources

### Work Order

**OpenAPI Definition (niworkorder-3.json):**

- Work request/scheduling container
- References Test Template, Systems, Products, Assets
- State: DEFINED → REVIEWED → SCHEDULED → IN_PROGRESS → PENDING_APPROVAL → CLOSED
- Generates Work Items/Test Plans

### Test Plan / Work Item

**OpenAPI Definition (niworkorder-3.json):**

- Actual test execution instance
- Derived from Work Order
- References Test Template, Systems, Assets, DUTs
- State: draft → active → completed
- Produces Test Results

### Test Template

**OpenAPI Definition (implicit in niworkorder-3.json):**

- Reusable test definition
- References Systems, Products, Assets, DUTs
- Base for Work Orders

---

## Tier 3: Data & Storage Resources

### Test Results

**OpenAPI Definition (nitestmonitor-v2.yml):**

- Test execution outcomes (pass/fail)
- Time-stamped measurements
- References Work Items
- Indexed for searching/filtering
- Can be associated with Products for specification compliance

### Test Steps

**OpenAPI Definition (nitestmonitor-v2.yml):**

- Sub-execution units within Test Results
- Individual step measurements
- Pass/fail status per step

### Data Tables / DataFrame

**OpenAPI Definition (nidataframe.json):**

- Columnar data storage (like CSV with typed columns)
- Supports structured data from multiple formats
- References Test Results

### Data Space

**OpenAPI Definition (implicit in test monitoring):**

- Data organization container
- References Data Tables, Files, Test Results

### Files

**OpenAPI Definition (nifile.yaml):**

- File storage and attachment management
- Associated with Test Results, Data Spaces
- Supports various formats

---

## Resource Relationships Summary

```
TIER 0 (Organizational)
├── Tags (measurement data) → Subscribe, publish, aggregate
├── States (package sets) → Apply to Systems
├── Feeds (package repos) → Distribute software
└── Workspace → Scopes all resources

TIER 1 (Infrastructure)
├── Location (physical hierarchy)
│   └── System (test stand, requires Location)
│       ├── Applied State (configuration)
│       ├── Assets (measurement points)
│       └── Fixtures (test equipment)
├── Product (device model)
│   ├── Referenced by Systems, DUTs
│   └── References Fixtures
└── DUT (device under test)
    └── References Asset

TIER 2 (Work)
├── Test Template (reusable definition)
│   └── Used by Work Orders
├── Work Order (scheduling)
│   └── Generates Test Plans
└── Test Plan (actual execution)
    └── Produces Test Results

TIER 3 (Data)
├── Test Results (outcomes)
│   └── Contains Test Steps
├── Data Tables (structured data)
├── Files (attachments)
└── Data Space (organization)
```

---

## Key Constraints & Validation Rules (from OpenAPI specs)

1. **Workspace Scoping:** All resources must specify workspace (or default workspace used)
2. **ID Generation:** All primary resources use UUID (globally unique)
3. **Name Uniqueness:** Resource names must be unique within workspace scope
4. **State Machines:** Work Orders and Test Plans follow defined state transitions
5. **Immutability:** Data type definitions in DataFrames are immutable after creation
6. **Audit Trails:** createdBy/updatedBy, createdAt/updatedAt on all major resources
7. **Location Hierarchy:** Single parent per Location (tree structure)
8. **Platform Specificity:** Feeds are platform-specific (Windows vs NI Linux RT)

---

## Data Type Mappings

### Tags Service

- Supports: numeric, boolean, string, datetime data types
- Aggregates: min, max, average, count, median, range
- Subscriptions: real-time updates via WebSocket

### DataFrame Service

- Column types: int, float, string, datetime, boolean
- Strict type checking (immutable after creation)
- Supports large datasets with chunked ingestion

### Test Monitor Service

- Measurement data: numeric with units/precision
- Pass/Fail status: boolean enums
- Timestamps: ISO-8601 format

---

## Required Changes to RESOURCE_MODEL.md

1. **Feeds Definition:** Change from "real-time data acquisition from sensors" to "package repository hosting"
2. **Data Acquisition Source:** Clarify that measurement data comes from Tags service
3. **Relationship Diagram:** Update Tier 0 to show Feeds ≠ data source
4. **Example Configurations:** Update examples to reflect correct Feed usage (packages, not sensor data)

---

## Verification Status

| Resource     | OpenAPI Spec              | Current Doc      | Status              |
| ------------ | ------------------------- | ---------------- | ------------------- |
| Tags         | nitag-2.yaml              | ✓ Correct        | ✅ Verified         |
| States       | nisystemsstate.json       | ✓ Correct        | ✅ Verified         |
| Feeds        | nifeed.json               | ❌ Incorrect     | 🔴 Needs Correction |
| Workspace    | Multi-service             | ✓ Correct        | ✅ Verified         |
| System       | nisysmgmt.json            | ✓ Mostly correct | ⚠️ Needs refinement |
| Asset        | niresourcemanagement.json | ✓ Correct        | ✅ Verified         |
| Location     | nilocation.json           | ✓ Correct        | ✅ Verified         |
| Product      | niresourcemanagement.json | ✓ Correct        | ✅ Verified         |
| Fixture      | niresourcemanagement.json | ✓ Correct        | ✅ Verified         |
| DUT          | niresourcemanagement.json | ✓ Correct        | ✅ Verified         |
| Work Order   | niworkorder-3.json        | ✓ Correct        | ✅ Verified         |
| Test Plan    | niworkorder-3.json        | ✓ Correct        | ✅ Verified         |
| Test Results | nitestmonitor-v2.yml      | ✓ Correct        | ✅ Verified         |
| DataFrame    | nidataframe.json          | ✓ Correct        | ✅ Verified         |

---

## Conclusion

The user's initial correction about Feeds was **partially inaccurate**. While the official manual may use imprecise language about "data sources," the **OpenAPI schema definitively confirms** that Feeds are for **package repository hosting**, not real-time sensor data acquisition.

Tags are the actual mechanism for measurement data. This is a critical distinction that must be corrected in RESOURCE_MODEL.md.
