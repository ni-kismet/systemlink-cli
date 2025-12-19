# SystemLink Resource Relationships - OpenAPI Verification

**Date:** December 18, 2025  
**Source:** OpenAPI Schemas + SystemLink Enterprise User Manual

---

## CRITICAL FINDINGS

### 1. Data Spaces - NOT A RESOURCE CONTAINER

**Actual Definition:** Data visualization and analysis application/interface  
**Confirmed By:** User Manual Section "Interacting with Data in a Data Space"

Data Spaces is a **web application interface** for:

- Visualizing parametric test data
- Plotting time-series data from Data Tables
- Analyzing Test Results statistically
- Creating custom analysis scripts
- Annotating results with keywords

**It is NOT a resource/container** - it's a visualization tool that DISPLAYS data from Test Results and Data Tables.

---

## VERIFIED RESOURCE RELATIONSHIPS

### Systems (nisysmgmt.json)

**References (confirmed in OpenAPI):**

- **Assets** - via system ID references
- **Test Results** - via systemId field in test results
- **States** - via `feeds.data` and packages configuration
- **Feeds** - via `feeds.data` dictionary (package feeds)
- **Tags** - via properties and naming conventions
- **Jobs** - created for system operations
- **Files** - attached via properties/metadata
- **Locations** - via properties (not enforced schema relationship)
- **Comments** - via workspace-scoped comment service

**System Properties (from QuerySystemsRequest filter documentation):**

```json
{
  "id": "system-id",
  "alias": "friendly-name",
  "connected.data.state": "CONNECTED|DISCONNECTED",
  "grains.data": {}, // system metadata
  "packages.data": {}, // installed packages
  "feeds.data": {}, // configured feeds
  "keywords.data": [],
  "properties.data": {} // custom metadata including location
}
```

---

### Assets (niresourcemanagement.json - Resource Groups)

**Asset Types Confirmed:**

- DUT (Device Under Test)
- FIXTURE (Test Equipment)
- Generic Asset (measurement points, equipment)

**Note:** The OpenAPI uses "Resource Groups" which can represent Assets, and assets can have `type` property

**References:**

- **Locations** - via parent hierarchy
- **Files** - via attachments
- **Tags** - via naming convention or metadata properties
- **Comments** - via workspace-scoped comment service

**Asset Type Determination:**

- Type is determined by `type` property in Resource Group
- Can be: "DUT", "Fixture", "Power Supply", "Sensor", etc. (string-based, not enum)

---

### Locations (nilocation.json)

**Hierarchy Confirmed:**

- **Parent Relationship:** `parentId` field (UUID reference to parent location)
- **Path:** Automatically constructed paths: `/parent-id/child-id/grandchild-id`
- **PathWithNames:** Human-readable: `/Lab/Cabinet/My Location`

**Properties:**

```json
{
  "id": "location-uuid",
  "name": "Location Name",
  "parentId": "parent-location-uuid", // CAN BE NULL for root
  "path": "/uuid1/uuid2/uuid3",
  "pathWithNames": "/Lab/Building1/Floor2",
  "enabled": true,
  "type": "Calibration lab", // custom type string
  "scanCode": "barcode-value",
  "properties": {}, // custom metadata
  "keywords": []
}
```

---

### Feeds (nifeed.json)

**References:**

- **Packages** - contains array of packages (`.nipkg`, `.ipk`, `.deb` files)
- **Jobs** - package management operations (cleanup, publish, update)

**Feed Schema:**

```json
{
  "id": "feed-uuid",
  "name": "Software Repository Name",
  "platform": "WINDOWS|NI_LINUX_RT",
  "workspace": "workspace-uuid",
  "packages.data": {
    "package-name": { "version": "1.0.0" }
  }
}
```

**NOT CONFIRMED:** Direct reference from Feeds to systems (feeds are downloaded by systems, not pushed)

---

### States (nisystemsstate.json)

**References:**

- **Packages** - state defines list of packages to install
- **Feeds** - states reference feeds as package sources

**State Schema:**

```json
{
  "id": "state-uuid",
  "name": "RF Testing Stack",
  "packages": [{ "name": "rf-framework", "version": "2.1.0" }],
  "feeds": ["feed-id-1", "feed-id-2"] // where to download packages
}
```

---

### Work Orders (niworkorder-3.json)

**References Confirmed:**

- **Work Items (Test Plans)** - workOrderId field in test plans
- **Files** - fileIdsFromTemplate array
- **Test Results** - via test plans that execute
- **Comments** - via workspace comment service

**Properties:**

```json
{
  "id": "wo-uuid",
  "name": "Weekly Qualification Test",
  "state": "DEFINED|REVIEWED|SCHEDULED|IN_PROGRESS|CLOSED",
  "workspace": "workspace-uuid"
}
```

---

### Work Items / Test Plans (niworkorder-3.json)

**References Confirmed:**

- **Test Results** - test plans produce test results when executed
- **Files** - `fileIdsFromTemplate` array
- **Comments** - via workspace comment service
- **Test Plan Templates** - `templateId` field
- **Workflows** - `workflowId` field (beta feature)

**Key Properties:**

```json
{
  "id": "testplan-uuid",
  "templateId": "template-uuid", // instantiated from
  "workflowId": "workflow-uuid", // custom workflow
  "workOrderId": "workorder-uuid",
  "systemId": "system-uuid", // where test runs
  "dutId": "asset-uuid", // what's being tested
  "fixtureIds": ["fixture1-uuid", "fixture2-uuid"],
  "state": "NEW|DEFINED|REVIEWED|SCHEDULED|IN_PROGRESS|CLOSED",
  "substate": "custom-substate", // from workflow
  "plannedStartDateTime": "ISO-8601",
  "estimatedEndDateTime": "ISO-8601",
  "fileIdsFromTemplate": ["file1", "file2"]
}
```

**Scheduling Confirmed:**

- Systems can be scheduled (via test plans assigned to systemId)
- Assets can be scheduled (via test plans assigned to dutId/fixtureIds)

---

### Products (niapm-2.json - Asset Performance Management)

**References Confirmed:**

- **Test Results** - via partNumber field in test results
- **Files** - product documentation/attachments
- **Specs** - specification compliance module
- **Work Items** - via partNumber linkage
- **DUTs** - DUTs test specific product models

**Product Schema:**

```json
{
  "id": "product-uuid",
  "name": "Demo Widget Pro",
  "partNumber": "156502A-11L", // KEY LINKAGE FIELD
  "specifications": ["spec1-id", "spec2-id"]
}
```

---

### Test Results (nitestmonitor-v2.yml)

**References Confirmed:**

- **Test Steps** - array of steps within result
- **Files** - attached files array
- **Data Tables** - parametric data references
- **Comments** - via workspace comment service

**Test Result Schema:**

```json
{
  "id": "result-uuid",
  "programName": "Battery Cycle Test",
  "serialNumber": "SN12345",
  "partNumber": "156502A-11L", // links to Product
  "status": "PASSED|FAILED|RUNNING|ERRORED",
  "started": "ISO-8601",
  "updated": "ISO-8601",
  "testSteps": [], // array of step objects
  "fileIds": ["file1-uuid", "file2-uuid"],
  "properties": {} // custom metadata
}
```

---

### Notebooks / Scripts (ninotebook.yaml, v1-ninbexecution-3.json)

**Triggers Confirmed (via Routines - niroutine-2.json):**

**Event Types for Routine Triggers:**

1. **File Events:**
   - File upload
   - File metadata change
2. **Test Result Events:**

   - Test result created
   - Test result updated
   - Test result deleted

3. **Work Item Events:**

   - Test plan state changed
   - Test plan created/updated

4. **Tag Events:**

   - Tag value updated (for Alarms)

5. **Schedule Events:**
   - Specific date and time (cron-like)

**Manual Triggers:**

- From Files app - analyze/convert files
- From Schedule app - automatically schedule systems/assets

**Notebook Execution:**

```json
{
  "notebookId": "notebook-uuid",
  "trigger": "FILE_UPLOADED|TEST_RESULT_CREATED|SCHEDULED",
  "parameters": {},
  "workspace": "workspace-uuid"
}
```

---

### Alarms (nialarm.json)

**Triggers:**

- **Via Routines** - Tag value updates trigger routine → routine creates alarm
- Tag-based threshold conditions

**Alarm Schema:**

```json
{
  "id": "alarm-uuid",
  "tagPath": "system/asset/temperature",
  "condition": "value > 85",
  "severity": "CRITICAL|WARNING|INFO",
  "message": "Temperature exceeded threshold"
}
```

---

### Dashboards (Implicit - no dedicated API)

**Data Sources Confirmed (from User Manual):**

- Test Plans
- Alarms
- Assets
- DataFrames (Data Tables)
- Products
- Systems
- Tags
- Test Results
- Work Orders
- Workspaces
- Notebooks (output visualization)

**Note:** Dashboards use Grafana with custom data source plugins for each SystemLink service

---

### Web Apps (niapp.yaml)

**Purpose:** Host arbitrary web application content  
**Data Access:** Can pull from any SystemLink resource via REST APIs

**Web App Schema:**

```json
{
  "id": "webapp-uuid",
  "name": "Custom Analysis Tool",
  "url": "https://app-url/",
  "description": "Custom web application"
}
```

---

## CORRECTED HIERARCHY

```
TIER 0: ORGANIZATIONAL & CROSS-CUTTING
├── Tags (measurement data - key-value timeseries)
├── States (system configurations - package sets)
├── Feeds (package repositories - software distribution)
└── Workspace (tenant isolation)

TIER 1: INFRASTRUCTURE & PHYSICAL
├── Location (hierarchical, parentId relationships)
├── Product (partNumber linkage to results/specs)
├── System (references Location, States, Feeds, Tags, Jobs, Files)
├── Asset (type: DUT|Fixture|Other, references Location, Tags, Files)
└── Fixture (type of Asset)

TIER 2: WORK & EXECUTION
├── Test Template
├── Work Order (references Work Items, Files, Test Results)
├── Work Item/Test Plan (references Template, Workflow, System, DUT, Fixtures)
└── Workflow (custom state machine for test plans)

TIER 3: DATA & STORAGE
├── Test Results (contains Test Steps, references Files, Data Tables)
├── Test Steps (within Test Results)
├── Data Tables (structured parametric data)
└── Files (attachments, logs)

TIER 4: AUTOMATION & VISUALIZATION
├── Routines (event triggers → actions on Notebooks, Alarms)
├── Notebooks (analysis scripts, triggered or manual)
├── Alarms (triggered by Tag updates via Routines)
├── Dashboards (visualization interface - NOT a resource)
├── Data Spaces (visualization app - NOT a resource/container)
└── Web Apps (custom web content)
```

---

## KEY CORRECTIONS TO RESOURCE_MODEL.MD

1. **Data Spaces** → Change from "resource container" to "visualization application"
2. **Feeds** → Already corrected (package repos, not sensor data)
3. **Asset Types** → Add DUT, Fixture as Asset types (not separate resources)
4. **Location Hierarchy** → Emphasize parentId relationships
5. **Scheduling** → Systems and Assets ARE schedulable via Test Plans
6. **Workflows** → Add as beta feature for custom Test Plan state machines
7. **Routines** → Add as automation trigger mechanism
8. **Alarms** → Clarify triggered via Routines from Tag updates
