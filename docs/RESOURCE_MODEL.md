# SystemLink Resource Model

## Overview

This document illustrates the relationships between SystemLink Enterprise (SLE) resources used in test configurations and deployment scenarios. The resource model organizes resources into tiers based on their functional role and dependencies:

- **Tier 0 (Foundational):** Core infrastructure that everything depends on (Location, Product, System)
- **Tier 1 (Cross-Cutting):** Resources used throughout the model (Asset, Tags, Files, States, Feeds)
- **Tier 2 (Work & Execution):** Test planning and execution management (Test Template, Work Order, Work Item)
- **Tier 3 (Data & Results):** Generated data from test execution (Test Results, Data Tables)
- **Tier 4 (Automation & Visualization):** Event-driven automation and data visualization (Routines, Notebooks, Alarms, Dashboards, Web Apps, Data Spaces)

## Complete SystemLink Resource Hierarchy

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                   COMPLETE SYSTEMLINK RESOURCE HIERARCHY                      │
└──────────────────────────────────────────────────────────────────────────────┘
This section shows the complete resource model in two views:
1. **Tier-by-Tier View**: Resources organized by functional tier (below)
2. **Comprehensive Single Diagram**: All resources in one hierarchical view (see end of this section)


TIER 0: FOUNDATIONAL RESOURCES (Core infrastructure everything depends on)
═══════════════════════════════════════════════════════════════════════════

                    ┌──────────────────────┐
                    │    LOCATION          │
                    │ (Physical Places)    │
                    └────────┬─────────────┘
                             │
                 ┌───────────┴───────────┐
                 │                       │
                 ▼                       ▼
       ┌──────────────────┐  ┌──────────────────────┐
       │     SYSTEM       │  │     ASSET            │
       │  (Test Stand)    │  │  (DUT, Fixture,      │
       │                  │  │   Sensor, etc.)      │
       └──────────────────┘  └──────────────────────┘
       (references Location) (references Location)

         ┌──────────────────────┐
         │     PRODUCT          │
         │  (Model/Spec)        │
         │  (NO location)       │
         └────────┬─────────────┘
                  │
                  ▼
         ┌──────────────────────┐
         │  SPECIFICATIONS      │
         │ (Test Requirements,  │
         │  Compliance Criteria)│
         │ (derived from        │
         │  Product)            │
         └──────────────────────┘


TIER 1: CROSS-CUTTING RESOURCES (Used throughout the model)
═══════════════════════════════════════════════════════════

Cross-cutting resources appear as children/references under multiple parent resources.
Resources are duplicated below to show their usage across different contexts:

┌──────────────────────┐    ┌──────────────────────┐    ┌──────────────────────┐
│      SYSTEM          │    │      ASSET           │    │      PRODUCT         │
│   (Test Stand)       │    │  (DUT, Fixture)      │    │   (Model/Spec)       │
└──────────┬───────────┘    └─────────┬────────────┘    └──────────┬───────────┘
           │                          │                            │
    ┌──────┴──────┐            ┌──────┴──────┐            ┌────────┴────────┐
    │             │            │             │            │                 │
    ▼             ▼            ▼             ▼            ▼                 ▼
┌────────┐  ┌────────┐    ┌────────┐  ┌────────┐   ┌──────────┐      ┌──────────┐
│ Tags   │  │ Files  │    │ Tags   │  │ Files  │   │ Specs    │      │ Files    │
└────────┘  └────────┘    └────────┘  └────────┘   └──────────┘      └──────────┘
  ┌──────────┐       ┌──────────┐
  │ Software │       │  States  │
  └────────┬─┘       └────────┬─┘
           │                  │
      ┌────┴───┐          ┌───┴────┐
      │        │          │        │
      ▼        ▼          ▼        ▼
┌────────┐ ┌────────┐ ┌──────┐ ┌──────────┐
│ Feeds  │ │Packages│ │Feeds │ │ Packages │
└────────┘ └────────┘ └──────┘ └──────────┘

   ┌──────────────────────┐    ┌──────────────────────┐    ┌──────────────────────┐
   │   WORK ITEM          │    │   WORK ORDER         │    │   TEST RESULTS       │
   │  (Test Plan)         │    │ (Time Reservation)   │    │  (Outcomes)          │
   └──────────┬───────────┘    └──────────┬───────────┘    └──────────┬───────────┘
              │                           │                           │
       ┌──────┴──────┐             ┌──────┴──────┐           ┌────────┴────────┐
       │             │             │             │           │                 │
       ▼             ▼             ▼             ▼           ▼                 ▼
    ┌────────┐  ┌────────┐     ┌────────┐  ┌────────┐   ┌──────────┐      ┌──────────┐
    │ Assets │  │ Files  │     │ Assets │  │ Files  │   │ Files    │      │ Specs    │
    └────────┘  └────────┘     └────────┘  └────────┘   └──────────┘      └──────────┘
                ┌────────┐                 ┌────────────┐
                │Systems │                 │ Data Tables│
                └────────┘                 └────────────┘


CROSS-CUTTING RESOURCE DEFINITIONS:
• Assets: Physical test resources (DUTs, Fixtures, Sensors) - belong to Systems/Locations
• Tags: Health monitoring and system status - attached to Systems/Assets
• Files: Test logs, attachments, raw data - attached to Products, Work Items, Test Results
• States: Instrument drivers and test application code - deployed to Systems
• Feeds: Package repositories for software distribution - referenced by Systems
• Specifications: Test requirements and compliance criteria - associated with Products, referenced by Test Results


═══════════════════════════════════════════════════════════════════════════════
        EXHAUSTIVE PARENT/CHILD RESOURCE TREE - ALL SYSTEMLINK RESOURCES
═══════════════════════════════════════════════════════════════════════════════

NOTE: Parent/child relationships reflect how data is referenced and used in the SystemLink data model.
Some relationships represent UI presentation (e.g., Data Spaces is a visualization tool, not a storage container).


LOCATION (root foundational resource)
├── (Systems have a location - Location is reference parent)
└── (Assets have a location - Location is reference parent)

PRODUCT (root foundational resource)
├── DUTs (Assets of type DUT - reference Product)
├── Specifications (derived from Product)
├── Test Results (reference Product under test)
├── Files (product-related documents)
└── Work Items (reference Product)

SYSTEM (foundational resource - references Location)
├── Software (deployed instruments/drivers - active software configuration)
│   ├── Feeds (packages available for installation)
│   └── Packages (which packages are installed)
├── Assets (system-specific)
│   ├── Tags (asset health monitoring)
│   ├── Files (asset-specific logs, documentation, calibration data)
│   └── Location (reference - where asset is physically located)
├── Tags (system health monitoring)
├── Files (system configuration, logs, test data)
├── Test Results (tests executed on system)
└── Location (reference - where system is physically located)

ASSET (foundational resource - references Location)
├── Tags (asset health monitoring - temperature, pressure, etc.)
├── Files (asset-specific documentation, calibration data)
└── Location (reference - where asset is physically located)

WORKFLOW (optional custom execution logic)
└── (referenced by Test Template)

TEST TEMPLATE
├── Workflow (optional reference to custom execution logic)
└── (populates Work Item with configuration and procedures)

WORK ITEM (Test Plan)
├── Products (devices under test - reference)
├── DUTs/Fixtures (specific asset instances - reference)
├── Systems (test systems - reference and scheduling)
├── Assets (test assets - reference and scheduling)
├── Test Results (generated from execution)
├── Files (attachments, test data, logs)
└── Work Item Schedule (reservation of Systems/Assets at specific time)

WORK ORDER (Time Reservation)
├── Work Items (being scheduled - reference)
├── Files (planning documents)
├── Test Results (reference - associated test results)
└── Planning Schedule (scheduling information for Work Items)

TEST RESULTS (generated from Work Item execution)
├── Files (test logs, TDMS files, attachments, raw data)
├── Product (reference to device under test)
├── Specifications (reference for compliance/pass-fail criteria)
└── Data Tables (structured measurement results)

DATA TABLES (structured test data)
└── (referenced by Test Results, Data Spaces for visualization)

DATA SPACE (visualization and organization tool - NOT storage)
├── Test Results (displayed/visualized)
├── Data Tables (displayed/visualized)
└── Notebooks (reference for analysis results)

FILES (cross-cutting resource - referenced by many)
└── (referenced by: Products, Systems, Assets, Work Items, Work Orders, Test Results, Data Tables, Data Spaces, Notebooks)

TAGS (cross-cutting resource - health monitoring)
└── (referenced by: Systems, Assets)

STATES (collection of feeds and packages that can be deployed to change active software configuration)
├── Feeds (specifies which feeds are included)
└── Packages (specifies which packages from feeds are installed on System)

FEEDS (package repositories - local or remote)
├── Local (SystemLink-hosted package repositories)
└── Remote (external package repositories)
(referenced by States to specify available packages)

ROUTINES (event-driven automation)
├── Notebooks (triggered/executed by Routine)
├── Alarms (created/managed by Routine)
└── (triggered by: Files uploaded, Test Results completed, Tags threshold exceeded, Schedule)

NOTEBOOKS (analysis and data processing)
├── Test Results (input data for analysis)
├── Specifications (analysis rules for compliance checking)
├── Data Tables (input and output data)
├── Files (generated reports and analysis output)
└── Data Space (reference for visualization of results)

ALARMS (notifications and alerts)
└── (triggered by: Routines for Tags threshold violations)

DASHBOARDS (visualization tool - displays data from any resource)
└── (displays: Test Results, Tags, Systems, Assets, Work Orders, Work Items, Data Tables, Notebooks)

WEB APPS (custom applications - independent tools)
└── (access: any resource via API, custom UI for workspace data)

SPECIFICATIONS (test requirements and compliance criteria)
├── Product (parent - associated with specific product)
└── (referenced by Test Results for compliance validation)


COMPLETE HIERARCHY BY TIER:

TIER 0 (Foundational - Core Infrastructure):
  Location
  ├── (reference parent for Systems)
  └── (reference parent for Assets)

  Product
  ├── DUTs (Assets of type DUT)
  ├── Specifications
  ├── Test Results (reference)
  ├── Files
  └── Work Items (reference)

  System (references Location)
  ├── Software (deployed instruments/drivers)
  │   ├── Feeds
  │   └── Packages
  ├── Assets (system-specific)
  ├── Tags
  ├── Files (includes test data)
  ├── Test Results (reference)
  └── Location (reference)

  Specifications (derived from Product)
  └── Product (parent)

TIER 1 (Cross-Cutting - Used Throughout):
  Assets (references Location, belongs to System)
  ├── Tags
  ├── Files
  └── Location (reference)

  Tags (cross-cutting monitoring)
  └── (referenced by Systems, Assets)

  Files (cross-cutting attachment)
  └── (referenced by: Products, Systems, Assets, Work Items, Work Orders, Test Results, Notebooks)

  Software (deployed instruments/drivers)
  ├── Feeds (specifies which feeds included)
  └── Packages (specifies which packages installed)

  Feeds (package repositories)
  └── (referenced by Software - local or remote)
  ├── Assets (reference and scheduling)
  ├── Test Results
  ├── Files
  └── Work Item Schedule

  Work Order
  ├── Work Items (reference)
  ├── Files
  ├── Test Results (reference)
  └── Planning Schedule

TIER 3 (Data & Results):
  Test Results
  ├── Files
  ├── Product (reference)
  ├── Specifications (reference)
  └── Data Tables

  Data Tables
  └── (referenced by Test Results, Data Spaces)

  Data Space (visualization tool)
  ├── Test Results (displayed)
  ├── Data Tables (displayed)
  └── Notebooks (reference)

  Files → see TIER 1 (cross-cutting)

TIER 4 (Automation & Visualization):
  Routines
  ├── Notebooks (triggered)
  └── Alarms (created)
  (triggered by: Files, Test Results, Tags, Schedule)

  Notebooks
  ├── Test Results (input)
  ├── Specifications (analysis)
  ├── Data Tables (input/output)
  ├── Files (reports)
  └── Data Space (reference)

  Alarms
  └── (triggered by Routines, Tags - NOT Test Results)

  Dashboards (visualization tool)
  └── (displays any Tier 0-3 resources)

  Web Apps (custom UI tool)
  └── (accesses any resource via API)

  Data Spaces → see TIER 3

  States → deployed to Systems

  Feeds → referenced by Systems

TIER 2 (Work & Execution):
  Workflow (optional)
  └── referenced by Test Template

  Test Template
  ├── Workflow (optional)
  └── populates Work Item

  Work Item (Test Plan)
  ├── Assets
  ├── Files
  └── scheduled via Work Order

  Work Order
  ├── Work Item
  ├── Systems
  └── Assets

TIER 3 (Data & Results):
  Test Results
  ├── Files
  ├── Product (reference)
  ├── Specifications (reference)
  └── Data Tables

  Data Tables
  └── (referenced by Test Results, Data Spaces)

  Data Space (visualization tool)
  ├── Test Results (displayed)
  ├── Data Tables (displayed)
  └── Notebooks (reference)

  Files → see TIER 1 (cross-cutting)

TIER 4 (Automation & Visualization):
  Routines
  ├── Notebooks
  └── Alarms

  Notebooks
  ├── Test Results (input)
  ├── Specifications (analysis)
  ├── Data Tables (input/output)
  ├── Files (reports)
  └── Data Space (storage)

  Alarms
  └── triggered by Routines, Tags (threshold violations)

  Dashboards (independent)
  └── data sources: all Tier 0-3 resources

  Web Apps (independent)
  └── access any resource via API

  Data Spaces → see TIER 3


TIER 2: WORK & EXECUTION RESOURCES (References Tiers 0 & 1)
═══════════════════════════════════════════════════════════

    ┌────────────────────────────────┐
    │    WORKFLOW                    │◄──── Custom actions and state transition logic (optional)
    │ (Work item actions and flow)   │
    └────────┬───────────────────────┘
             │
             │ referenced by
             │
             ▼
    ┌──────────────────────┐
    │   TEST TEMPLATE      │◄──── References Systems, Assets, Test procedures
    │ (Test Definition)    │      Optional: Workflow
    └────────┬─────────────┘
             │
             │ populates
             │
             ▼
    ┌──────────────────────────────┐
    │   WORK ITEM / TEST PLAN      │◄──── Populated by Test Template
    │ (Test Configuration)         │      Reserves Systems & Assets at specific time
    └────────┬─────────────────────┘
             │
             │ scheduled with
             │
             ▼
    ┌──────────────────────┐
    │   WORK ORDER         │◄──── Used to assign work items to lab personnel and track them to completion
    │ (Execution plan)     │
    └──────────────────────┘


TIER 3: DATA & RESULTS RESOURCES (Generated from Tier 2)
═════════════════════════════════════════════════════════

          ┌──────────────────────┐
          │   TEST RESULTS       │◄──── Generated from Work Item execution
          │ (Test Outcomes)      │      Contains pass/fail status, timestamps
          │ (Status & Data)      │
          └────────┬─────────────┘
                   │
          ┌────────┴────────────┐
          │                     │
          ▼                     ▼
┌──────────────────┐  ┌──────────────────┐
│   DATA TABLES    │  │   FILES (via     │
│ (Structured Data)│  │   Test Results)  │
└──────────────────┘  └──────────────────┘


TIER 4: AUTOMATION & VISUALIZATION RESOURCES (Acts on all tiers)
════════════════════════════════════════════════════════════════

      ┌──────────────────────┐
      │    ROUTINES          │◄──── Event-driven automation
      │ (Automation Triggers)│      Triggered by: Files, Test Results, Tags, Schedule
      └─────────┬────────────┘
                │
                │ acts on
                │
      ┌─────────┴─────────┐
      │                   │
      ▼                   ▼
┌──────────┐         ┌──────────┐
│NOTEBOOKS │         │ ALARMS   │
│(Analysis)│         │(Alerts)  │
└──────────┘         └──────────┘


    INDEPENDENT VISUALIZATION & ORGANIZATION RESOURCES:
    ════════════════════════════════════════════════════

┌───────────┐       ┌──────────┐       ┌───────────┐
│DASHBOARDS │       │ WEB APPS │       │DATA SPACES│
│(Visualize)│       │(Custom)  │       │(Viz App)  │
└───────────┘       └──────────┘       └───────────┘


═══════════════════════════════════════════════════════════════════════════════
  COMPREHENSIVE SINGLE DIAGRAM: ALL SYSTEMLINK RESOURCES
═══════════════════════════════════════════════════════════════════════════════

                 TIER 0: FOUNDATIONAL
            ┌──────────────────────┐
            │    LOCATION          │
            │ (Physical Places)    │
            └────────┬─────────────┘
                     │
        ┌────────────┴───────────────┐
        │                            │
        ▼                            ▼
  ┌──────────────────┐         ┌──────────────────────┐
  │     SYSTEM       │         │     ASSET            │
  │  (Test Stand)    │         │  (DUT, Fixture)      │
  └──────────────────┘         └──────────────────────┘

      ┌──────────────┐              ┌──────────────────────┐
      │   PRODUCT    │──────────►   │  SPECIFICATIONS      │
      │ (Model/Spec) │   may have   │ (Test Requirements)  │
      └──────────────┘              └──────────────────────┘
      (NO location)

             TIER 1: CROSS-CUTTING
     ┌────────────────────────────────────────────────────────┐
     │      (Used throughout all tiers)                       │
     │  Assets, Tags, Files, Software, States, Feeds          │
     │                                                        │
     │  SOFTWARE (deployed to SYSTEM):                        │
     │    ├── Feeds (package repositories)                    │
     │    └── Packages (installed components)                 │
     │                                                        │
     │  STATES (collection of Feeds & Packages):              │
     │    ├── Feeds (which feeds included)                    │
     │    └── Packages (which packages installed)             │
     └────────────────────────────────────────────────────────┘

             TIER 2: WORK & EXECUTION
      ┌──────────────┐
      │  WORKFLOW    │ (optional execution logic)
      │ (Definition) │
      └────────┬─────┘
               │ referenced by
               │
      ┌────────▼──────────┐
      │  TEST TEMPLATE    │
      │ (Test Definition) │
      └────────┬──────────┘
               │ populates
               │
      ┌────────▼──────────────────┐
      │   WORK ITEM               │
      │  (Test Plan/Config)       │
      └────────┬──────────────────┘
               │ scheduled with
               │
      ┌────────▼──────────────────┐
      │   WORK ORDER              │
      │  (Time Reservation)       │
      └────────┬──────────────────┘
               │ produces
               │
               | TIER 3: DATA & RESULTS
               ▼
      ┌────────────────────┐
      │   TEST RESULTS     │
      │  (Outcomes & Data) │
      └─────────────────┬──┘
                        │
           ┌────────────┼────────────────┐
           │            │                │
           ▼            ▼                ▼
   ┌─────────────┐ ┌────────┐  ┌──────────────┐
   │DATA TABLES  │ │ FILES  │  │ DATA SPACES  │
   │(Structured) │ │(Logs)  │  │(Viz Tool)    │
   └─────────────┘ └────────┘  └──────────────┘

             TIER 4: AUTOMATION & VISUALIZATION
           ┌──────────────┐
           │  ROUTINES    │ (automation triggers)
           │(Event-driven)│
           └────┬──────┬──┘
       triggers │      │ triggers
                │      │
        ┌───────▼──┐  ┌▼────────┐
        │NOTEBOOKS │  │ ALARMS  │ (from Routines & Tags)
        │(Analysis)│  │(Alerts) │
        └──────────┘  └─────────┘

     ┌──────────────────────────────────────────────────────┐
     │  INDEPENDENT VISUALIZATION & UI TOOLS:               │
     │  ├── DASHBOARDS (displays Tiers 0-3 data)            │
     │  ├── WEB APPS (custom UI, accesses any resource)     │
     │  └── DATA SPACES (visualizes Test Results/Data)      │
     └──────────────────────────────────────────────────────┘

KEY RELATIONSHIPS & CONSTRAINTS:
• Location is reference parent for Systems & Assets (defines physical location)
• Product is independent (NO location); Specifications derived from Product
• Software deployed to Systems; contains Feeds & Packages
• States specify which Feeds/Packages are installed on Systems
• Workflow → Test Template → Work Item → Work Order (execution flow)
• Work Order reserves Systems & Assets at specific times for Work Items
• Test Results generated from Work Item execution; reference Products & Specs
• Routines triggered by Files, Test Results, Tags, Schedule
• Routines create/manage Alarms and trigger Notebooks
• Dashboards, Web Apps, Data Spaces are independent visualization tools
• All Tier 4 resources can access data from Tiers 0-3
• Tags for health monitoring (NOT measurement data)
• Files are cross-cutting (attached to multiple resource types)

```

```
┌─────────────────┐ ┌──────────────────┐ ┌──────────────┐
│ DATA TABLES     │ │ FILES            │ │ TEST RESULTS │
│ (Structured     │ │ (Storage).       │ │ (Indexed     │
│ Data)           │ │ (Attachments).   │ │ Results)     │
└─────────────────┘ └──────────────────┘ └──────────────┘

```

---

## Tier-Based Resource Organization

### **TIER 0: Foundational Resources**

Core infrastructure that everything depends on:

| Resource           | Purpose                                   | Dependencies | Used By                                               |
| ------------------ | ----------------------------------------- | ------------ | ----------------------------------------------------- |
| **Location**       | Physical/organizational location          | None         | Systems, Assets (reference parent for location)       |
| **Product**        | Device model/specification (NO location)  | None         | DUTs (Assets), Test Results, Files, Work Items, Specs |
| **Specifications** | Test requirements and compliance criteria | Product      | Test Results, Notebooks (spec compliance analysis)    |
| **System**         | Test stand/test system                    | Location     | Software, Assets, Work Items, Work Orders, Test Temps |

---

### **TIER 1: Cross-Cutting Resources**

Used throughout the model across all functional areas:

| Resource     | Purpose                                                     | Parent/References    | Used By                                                  |
| ------------ | ----------------------------------------------------------- | -------------------- | -------------------------------------------------------- |
| **Asset**    | Physical test resource (DUT, Fixture, measurement point)    | Location (reference) | Work Items, Work Orders, Tags, Files                     |
| **Tags**     | Health monitoring & system status (NOT measurement data)    | Systems, Assets      | Routines, Dashboards, Alarms (threshold violations)      |
| **Files**    | Test logs, attachments, raw data, reports (cross-cutting)   | Multiple parents     | Products, Systems, Assets, Work Items, Test Results, etc |
| **Software** | Deployed instruments/drivers on Systems                     | System (deployed)    | Systems (deployment configuration)                       |
| **States**   | Collection of Feeds & Packages for deployment configuration | System               | Systems (specifies installed packages)                   |
| **Feeds**    | Package repositories (Local: SystemLink, Remote: external)  | Systems, States      | States (specifies which feeds available)                 |

**Note on Tags:** Tags are used for health monitoring and system status tracking (temperature, pressure, uptime, error states). They are NOT intended for test measurement data. Tests should capture measurement data through:

- Test Result files (TDMS, CSV, binary formats)
- Data Tables (structured tabular data)
- Test Results resource (pass/fail status with timestamped data)

**Note on States:** States contain instrument drivers and test application code needed for test execution. They enable standardized, reproducible test environments across multiple systems.

---

### **TIER 2: Work & Execution Resources**

Test planning and execution management:

| Resource          | Purpose                               | Dependencies                             | References/Generates        |
| ----------------- | ------------------------------------- | ---------------------------------------- | --------------------------- |
| **Workflow**      | Custom execution logic (optional)     | None                                     | Referenced by Test Template |
| **Test Template** | Reusable test definition              | Workflow (optional)                      | Populates Work Items        |
| **Work Item**     | Test plan/test configuration          | Test Template, Products, Assets, Systems | Generates Test Results      |
| **Work Order**    | Time reservation for Systems & Assets | Work Items, Systems, Assets              | Enables Test Result Gen.    |

---

### **TIER 3: Data & Results Resources**

Test data and results generated from test execution:

| Resource         | Purpose                           | Dependencies                 | Used By                                       |
| ---------------- | --------------------------------- | ---------------------------- | --------------------------------------------- |
| **Test Results** | Test execution outcomes & data    | Work Item (executed)         | Data Tables, Data Spaces, Notebooks, Routines |
| **Data Tables**  | Structured test measurement data  | Test Results                 | Test Results, Data Spaces, Notebooks          |
| **Data Spaces**  | Data visualization & organization | Test Results, Data Tables    | Notebooks (reference)                         |
| **Files**        | Test logs, raw data, attachments  | Test Results (cross-cutting) | Notebooks, Routines, Dashboards               |

---

### **TIER 4: Automation & Visualization Resources**

Event-driven automation and data visualization:

| Resource        | Purpose                                       | Triggered/Used By                               | Acts On                                 |
| --------------- | --------------------------------------------- | ----------------------------------------------- | --------------------------------------- |
| **Routines**    | Event-driven automation (execute on triggers) | Files, Test Results, Tags (threshold), Schedule | Notebooks, Alarms                       |
| **Notebooks**   | Data analysis and report generation           | Routines (trigger), Test Results (input)        | Files, Data Spaces, Dashboards (output) |
| **Alarms**      | Notifications and alerts                      | Routines, Tags (threshold violations)           | Independent notifications               |
| **Dashboards**  | Data visualization & monitoring (independent) | Any Tier 0-3 resources                          | Visual display only                     |
| **Web Apps**    | Custom applications & UI tools (independent)  | Any resource via REST API                       | Any resource via API                    |
| **Data Spaces** | Data visualization & organization tool        | Test Results, Data Tables, Notebooks            | Visual display only                     |

---

## Detailed Resource Descriptions

### Tier 0: Foundational Resources

#### Location

**Purpose:** Define physical or organizational locations
**Dependencies:** None (root resource)
**Used By:** Systems (for location assignment)
**Properties:**

- Name
- Address (optional)
- City
- State/Province
- Country
- Parent location ID (optional, for hierarchical locations)

**Example:**

```yaml
- type: "location"
  name: "Austin HQ - Building A"
  properties:
    address: "123 Main St"
    city: "Austin"
    state: "TX"
    country: "USA"
  id_reference: "loc_hq_a"
```

---

#### Product

**Purpose:** Define product/device models (abstract specifications)  
**Dependencies:** None (root resource)  
**Used By:** DUTs (specific Asset type), Test Results, Files, Work Items, Specs  
**Note:** Products have NO physical location. Only DUTs (Assets) have locations when deployed to Systems.  
**Properties:**

- Name
- Description
- Category
- Manufacturer

**Example:**

```yaml
- type: "product"
  name: "Demo Widget Pro v2"
  properties:
    description: "Professional widget for testing"
    category: "Industrial Equipment"
    manufacturer: "Demo Inc."
  id_reference: "prod_widget"
```

---

#### Specifications

**Purpose:** Define test requirements and compliance criteria for Products  
**Dependencies:** Product (associated with a specific product model)  
**Used By:** Test Results (reference specs for pass/fail criteria), Notebooks (spec compliance analysis)  
**Scope:** Contains acceptance criteria, tolerance limits, performance requirements  
**Properties:**

- Name
- Product ID (reference)
- Specification document/version
- Test parameters and limits
- Compliance requirements
- Acceptance criteria

**Usage Pattern:**

1. Products have associated Specifications defining test requirements
2. Test Results can reference Specifications for validation
3. Notebooks analyze Test Results against Specifications to determine compliance

**Example:**

```yaml
- type: "specification"
  name: "Demo Widget Pro v2 - Acceptance Criteria"
  properties:
    product_id: "${prod_widget}"
    version: "2.1"
    parameters:
      - name: "max_power_consumption"
        value: "500W"
        tolerance: "+/- 5%"
      - name: "operating_temperature"
        min: "-10C"
        max: "50C"
      - name: "response_time"
        max: "100ms"
    compliance_standard: "IEC 61010-1"
  id_reference: "spec_widget_v2"
```

**Compliance Analysis Workflow:**
Notebooks can be triggered (via Routines) to analyze Test Results against Specifications:

```yaml
# Notebook triggered by test completion
- type: "notebook"
  name: "Spec Compliance Analysis"
  trigger: "test_result_completion"
  inputs:
    - test_result_id: "${result_id}"
    - specification_id: "${spec_widget_v2}"
  outputs:
    - compliance_status: "pass/fail"
    - deviations: "list of out-of-spec parameters"
```

---

#### System

**Purpose:** Define test systems/test stands - the logical container for testing infrastructure  
**Scope:** Represents a complete test station or subsystem  
**Dependencies:**

- Location (required) - where the system is physically located

**Used By:** Assets (measurement points within the system), Test Templates, Work Orders, Work Items  
**Properties:**

- Name
- Description
- Location ID (required reference)
- Serial Number
- Deployed State (packages/drivers installed)
- Status (operational, maintenance, retired)

**Example:**

```yaml
- type: "system"
  name: "Test Stand 1"
  properties:
    description: "RF Test System - Building A"
    location_id: "${loc_hq_a}"
    serial_number: "TS-001"
    deployed_state: "rf_testing_stack"
    status: "operational"
  id_reference: "sys_ts1"
```

---

### Tier 1: Cross-Cutting Resources

#### Asset

**Purpose:** Track system and asset health monitoring data  
**Scope:** Health monitoring and status tracking layer  
**Usage:**

Tags are used for slow-moving health monitoring data:

- System uptime and health status
- Operating temperature ranges
- Power consumption levels
- Device calibration status
- Asset maintenance intervals
- Error and warning states

**Important:** Tags are NOT for test measurement data. Test measurements should be captured through:

- Test Result files (TDMS, CSV, binary formats)
- Data Tables (structured measurement data)
- Test Results resource (pass/fail with timestamped data)

**Create Alerts:** Alarms can be triggered by tag value changes via Routines  
**Visualize:** Monitor tag values on Dashboards  
**Associate with Resources:** Link to Systems/Assets via naming convention or metadata

**Association Mechanism:**

- Naming convention: tags with system/asset prefix identify ownership
- Metadata: linked via properties to specific Systems or Assets

**Example:**

```yaml
# Health monitoring tags
- type: "tag"
  name: "sys_ts1_temperature"
  data_type: "numeric"
  path: "system/test_stand_1/temperature"
  value: 45.2
  unit: "celsius"

- type: "tag"
  name: "asset_fixture_calibration_due"
  data_type: "datetime"
  path: "asset/dmm_100/calibration_due"
  value: "2025-09-15T00:00:00Z"
```

---

#### States

**Purpose:** Define and deploy instrument drivers and test application code to systems  
**Scope:** Configuration management for reproducible test environments  
**Key Concept:**

- A state is a set of instrument drivers and test application packages
- Define once, deploy to multiple systems for standardized environments
- Enables consistent test execution across infrastructure
- NOT for OS dependencies (systems assume base OS is already installed)

**Packages in States:**

- Instrument drivers (NI driver packages)
- Test framework software (LabVIEW, test executables)
- Custom test application code
- Calibration and reference software

**Workflow:**

1. Define a state as a collection of instrument drivers and test packages
2. Apply the state to any system to deploy that software set
3. Reduces setup time and ensures consistency
4. Enables reproducible test environments across multiple test stands

````

**Example:**

```yaml
resources:
  - type: "system"
    name: "Test Stand 1"
    properties:
      deployed_state: "rf_testing_stack"  # Predefined state with RF packages
    ...

  - type: "system"
    name: "Test Stand 2"
    properties:
      deployed_state: "rf_testing_stack"  # Same state applied to different system
    ...
```

---

#### Feeds

**Purpose:** Host and distribute software packages to multiple systems
**Scope:** Package repository management for standardized software deployment
**Key Concept:**

- A feed is a package repository (like apt, npm, or pip)
- Stores software packages (.nipkg for Windows, .ipk/.deb for NI Linux RT)
- Define once, deploy packages to many systems
- NOT for sensor/measurement data (use Tags service instead)
- Enables consistent software across distributed infrastructure

**Properties:**

- Name
- Description
- Platform (Windows, NI Linux RT)
- Workspace
- Packages (stored in feed)
- Jobs (package management operations)

**Workflow:**

1. Create a feed for a specific platform
2. Publish packages (.nipkg, .ipk, .deb) to the feed
3. Systems reference the feed to download packages
4. Package cleanup operations to maintain repository

**Example:**

```yaml
resources:
  - type: "feed"
    name: "RF Testing Software Repository"
    platform: "WINDOWS"
    description: "Package repository for RF test system software"
    workspace: "demo-workspace"
    packages:
      - name: "rf-framework"
        version: "2.1.0"
        file: "rf-framework-2.1.0.nipkg"
      - name: "ni-labview-runtime"
        version: "2024"
        file: "ni-labview-runtime-2024.nipkg"
    ...

# Note: Measurement data acquisition uses Tags service, not Feeds
# Tags example:
  - type: "tag"
    name: "temperature_measurement"
    data_type: "numeric"
    path: "system/asset/temperature"
    aggregates: ["min", "max", "avg"]
```

---

### Tier 2: Work & Execution Resources

#### Work Order

**Purpose:** Reserve Systems and Assets at specific time to enable test execution. Work Orders schedule Work Items (Test Plans) by reserving required resources.
**Dependencies:**

- Work Item (Test Plan to be scheduled)
- Systems, Assets (resources to be reserved)

**Properties:**

- Name/Description
- Status (planned, scheduled, in-progress, completed, cancelled)
- Priority (high, medium, low)
- Scheduled date/time (time reservation)
- Assigned team/person
- Work Item reference
- System/Asset references (reserved resources)
- Expected duration

**Enables:** Test execution by reserving resources for Work Items

**Example:**

```yaml
# Typically created via API/UI, but can be seeded:
- type: "work_order"
  name: "Demo Widget Monthly Test"
  properties:
    description: "Monthly qualification test for Demo Widget Pro"
    status: "scheduled"
    priority: "high"
    scheduled_date: "2025-12-20T09:00:00Z"
    template_id: "${template_demo}"
    systems: ["${sys_ts1}", "${sys_ts2}"]
    products: ["${prod_widget}"]
    expected_duration_hours: 4
  id_reference: "wo_demo_monthly"
  tags: ["demo"]
```

---

#### Work Item / Test Plan

**Purpose:** Test configuration instance populated by Test Template. Contains test procedures, parameters, and configuration. Scheduled via Work Order to reserve Systems and Assets at specific time.
**Dependencies:**

- Test Template (populates Work Item with configuration and procedures)
- Optional: Workflow (custom execution logic referenced by Test Template)

**Scheduled Via:**

- Work Order (reserves Systems & Assets at specific time for this Work Item)

**Properties:**

- Name/Description
- Status (draft, active, paused, completed, failed)
- Planned start date/time (scheduling)
- Start/End time (actual execution)
- Assigned Assets (test targets)
- Test procedures/steps
- Expected outcome/pass criteria
- Workflow reference (optional, beta feature for custom test execution)
- Actual results (filled during/after execution)

**Workflow Integration (Beta Feature):**

Test Plans can optionally reference custom Workflow definitions that define event-driven test execution logic. This enables:

- Custom test sequencing beyond predefined templates
- Event-based triggering and step execution
- Dynamic workflow logic for complex test scenarios

**Generates:** Test Results

**Example:**

```yaml
# Created from work order with optional custom workflow:
- type: "work_item"
  name: "Test Demo Widget Stand 1 - Run 1"
  properties:
    description: "Execute demo test plan on Stand 1"
    status: "draft"
    test_template_id: "${template_demo}"
    system_id: "${sys_ts1}"
    asset_ids: ["${asset_1}"]
    planned_start_date: "2025-12-20T09:00:00Z"
    procedures:
      - step: 1
        description: "Setup DUT on fixture"
        expected_duration_minutes: 5
      - step: 2
        description: "Run voltage sweep test"
        expected_duration_minutes: 10
      - step: 3
        description: "Verify results against spec"
        expected_duration_minutes: 5
    workflow_id: "${custom_workflow}" # Optional beta feature
  id_reference: "wi_demo_s1_r1"
  tags: ["demo"]
```

---

#### Test Results

**Purpose:** Record outcomes and data from executed work items
**Dependencies:**

- Work Item (source)
- Asset/DUT (tested resources)

**Properties:**

- Test name
- Timestamp/date range
- Start/End time
- Status (passed, failed, incomplete)
- Measurements/data points
- Pass/fail criteria results
- Notes/anomalies
- Operator/system that created results

**Stored In:** Data Space, Data Tables

**Example:**

```yaml
# Typically created by test execution system:
# Test Results can reference work items and store data
- test_result_id: "tr_demo_s1_r1_20251218"
  work_item_id: "${wi_demo_s1_r1}"
  dut_id: "${dut_1}"
  asset_id: "${asset_1}"
  timestamp: "2025-12-18T10:30:00Z"
  status: "passed"
  measurements:
    - parameter: "Voltage Output"
      value: 4.95
      unit: "V"
      lower_limit: 4.5
      upper_limit: 5.5
      status: "pass"
    - parameter: "Current Draw"
      value: 2.3
      unit: "A"
      lower_limit: 2.0
      upper_limit: 3.0
      status: "pass"
  overall_status: "passed"
```

---

### Tier 3: Data & Storage Resources

#### Data Tables

**Purpose:** Store structured test data in tabular format
**Contains:** Rows and columns of typed data
**Properties:**

- Name
- Columns (with types: number, string, timestamp, etc.)
- Row data
- Workspace reference

**Example:**

```yaml
# Created by test execution system
# Data Table: "Widget Voltage Test Results"
# Columns: timestamp, dut_id, system_id, voltage_mv, current_ma, status
# Rows:
#   2025-12-18T10:30:00Z, dut_1, sys_ts1, 4950, 2300, PASS
#   2025-12-18T10:32:00Z, dut_2, sys_ts2, 4920, 2280, PASS
#   2025-12-18T10:34:00Z, dut_1, sys_ts1, 4980, 2310, PASS
```

---

#### Files

**Purpose:** Store test logs, attachments, and file data
**Contains:**

- Test logs
- Waveforms
- Images
- Attachments
- Raw data exports

**Properties:**

- Filename
- Content type
- Size
- Creation date
- Data space reference
- Associated work item/test result

**Example:**

```yaml
# Files created during test execution
# - test_log_20251218_103000.txt (test execution log)
# - voltage_sweep_raw_data.csv (raw measurements)
# - setup_photo_20251218.jpg (test setup image)
# - final_report.pdf (test report)
```

---

## API Resource Reference

This table maps resources to their typical SLE API endpoints and operations:
This table maps resources to their typical SLE API endpoints and operations:

```
RESOURCE OPERATIONS MATRIX:
═══════════════════════════

Resource          API Endpoint                    Create  Read   Update  Delete
─────────────────────────────────────────────────────────────────────────────
Location          /niuser/v1/locations              ✓      ✓      ✓       ✓
Product           /niworkorder/v1/products          ✓      ✓      ✓       ✓
System            /niworkorder/v1/systems           ✓      ✓      ✓       ✓
Fixture           /niworkorder/v1/fixtures          ✓      ✓      ✓       ✓
Asset             /niworkorder/v1/assets            ✓      ✓      ✓       ✓
DUT               /niworkorder/v1/duts              ✓      ✓      ✓       ✓
TestTemplate      /niworkorder/v1/test-templates    ✓      ✓      ✓       ✓
WorkOrder         /niworkorder/v1/work-orders       ✓      ✓      ✓       ✓
WorkItem          /niworkorder/v1/work-items        ✓      ✓      ✓       ✓
TestResults       /niworkorder/v1/test-results      ✓      ✓      —       —
DataSpace         /nidataspace/v1/data-spaces       ✓      ✓      ✓       ✓
DataTable         /nidataspace/v1/data-tables       ✓      ✓      ✓       ✓
Files             /nidataspace/v1/files             ✓      ✓      ✓       ✓
Tags              /niuser/v1/tags                   ✓      ✓      ✓       ✓
States            /niworkorder/v1/states            ○      ✓      ○       ○
Feeds             /niuser/v1/feeds                  ✓      ✓      ✓       ✓

Legend:
  ✓ = Supported operation
  ○ = Configuration/reference only
  — = Not applicable
```

---

## Resource Provisioning in Example Configs

The example configuration system in slcli primarily manages Tier 1 (Infrastructure) and Tier 2 (Work) resources:

### Provisionable Resources (Phase 1 Focus)

```
example install <example_name> -w <workspace-id>
  └─ Creates in sequence:
     1. Location
     2. Product
     3. System
     4. Fixture (optional)
     5. Asset
     6. DUT
     7. Test Template
     8. Work Order (optional)
     9. Work Item (optional)

example delete <example_name> -w <workspace-id>
  └─ Deletes in reverse order:
     1. Work Item
     2. Work Order
     3. Test Template
     4. DUT
     5. Fixture
     6. Asset
     7. System
     8. Product
     9. Location
```

---

## Tier 4: Automation & Applications Resources

These resources provide event-driven automation and data visualization capabilities:

### Routines

**Purpose:** Create and manage event-driven automation that responds to SystemLink events and triggers actions
**Scope:** Automation layer for system integration and workflow orchestration
**Event Types Supported:**

- File events (upload, modification)
- Test Result events (completion, status changes)
- Test Plan events (start, completion)
- Tag events (value updates)
- Scheduled events (date/time)
- Manual triggers

**Actions Triggered:**

- Execute Notebooks
- Create Alarms
- Publish to message queues
- Invoke custom webhooks

**Properties:**

- Name
- Description
- Event type and filter criteria
- Trigger conditions
- Associated action(s)
- Enabled/disabled status

**Used By:** Automation workflows, integration scenarios

**Example:**

```yaml
# Routine triggered by test completion
- type: "routine"
  name: "Alert on Test Failure"
  properties:
    description: "Create alarm when test results show failure"
    event_type: "test_result"
    trigger_condition: "status == 'failed'"
    action: "create_alarm"
    severity: "high"
    message: "Automated test failed - review results"
```

---

### Notebooks

**Purpose:** Execute custom analysis, data processing, and visualization scripts
**Triggered By:** Routines (via file events, test results, scheduled events)
**Access:** Can read/write all workspace data via REST APIs
**Properties:**

- Name
- Description
- Code/scripts
- Execution schedule (optional)
- Input parameters (optional)

---

### Alarms

**Purpose:** Create notifications and alerts for system events and conditions
**Triggered By:** Routines, Test Results, Tag value changes
**Properties:**

- Title
- Description
- Severity (critical, high, medium, low)
- Trigger source (routine, test, tag)
- Resolution actions
- Notification targets

---

### Dashboards

**Purpose:** Visualize test data and system status across multiple resources
**Data Sources:** Can reference and display:

- Test Plans (status, progress)
- Test Results (pass/fail rates, trends)
- Systems (availability, health)
- Assets (status, calibration)
- Tags (measurement values, trends)
- Alarms (active, acknowledged)
- Products (quality metrics)
- Work Orders (status, queue)
- DataFrames/Data Tables (custom analytics)
- Workspaces (overall statistics)
- Notebooks (execution status, results)

**Used By:** Decision makers, operators, quality engineers

---

### Web Apps

**Purpose:** Host arbitrary web applications and interfaces pulling data from SystemLink
**Integration:** Applications access SystemLink resources via REST APIs
**Properties:**

- Application name
- Hosted web content (HTML, CSS, JavaScript)
- Configuration parameters
- API credential management

---

### Data Spaces (Visualization Interface)

**Purpose:** Provide a data visualization and exploration interface for test results and analytics
**Note:** Data Spaces is a visualization application, not a resource container. It provides:

- Interactive data exploration
- Custom data visualization
- Report generation
- Collaboration features

Test results and data are stored in Data Tables and Files (Tier 3), while Data Spaces provides the interface for analyzing and visualizing that data.

**Example Workflow:**

```
Test Results (Tier 3) ──→ Store in Data Tables/Files
                              ↓
                        Data Spaces Interface
                              ↓
                        Visualization & Analysis
```

---

### System-Generated Resources (Tier 3)

These are created by the SLE system during test execution, not by example provisioning:

- **Test Results** - Generated when work items complete
- **Data Tables** - Populated with test result summaries
- **Files** - Test logs, waveforms, and reports

---

## Multi-Example Coordination

When multiple examples are provisioned into the same workspace, the tag-based filtering ensures safety:

```
Workspace contains:
  ├─ Example: "demo-test-plans"
  │   ├─ Location [tag: demo]
  │   ├─ System [tag: demo]
  │   ├─ Asset [tag: demo]
  │   └─ DUT [tag: demo]
  │
  ├─ Example: "supply-chain-tracking"
  │   ├─ Location [tag: supply-chain]
  │   ├─ System [tag: supply-chain]
  │   ├─ Asset [tag: supply-chain]
  │   └─ DUT [tag: supply-chain]
  │
  ├─ Production Systems
  │   ├─ Location [tag: production]
  │   ├─ System [tag: production]
  │   └─ DUT [tag: production]
  │
  └─ Shared Infrastructure
      ├─ Tags [shared across all]
      ├─ States [shared across all]
      └─ Feeds [shared across all]

Operation: Delete demo-test-plans
  └─ Only deletes resources with tag "demo"
     (preserves all other examples and production)
```

---

```
Tag-Based Filtering:
───────────────────

resources:
  - type: location
    tags: ["demo"]        ← Marked for cleanup
  - type: system
    tags: ["demo"]        ← Marked for cleanup
  - type: system
    tags: ["production"]  ← NOT cleaned up (different tag)

cleanup:
  filter_tags: ["demo"]   ← Only delete resources with "demo" tag
```

This ensures that:

- Demo resources can be safely deleted
- Production resources are never accidentally deleted
- Multiple example configs can coexist without conflicts
````
