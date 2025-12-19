# SystemLink Resource Model Analysis

Comprehensive OpenAPI schema analysis for SystemLink resource types and their relationships.

---

## Location

**Purpose:** Hierarchical physical location management for organizing test environments, labs, and facilities.

**Tier:** 0 - Foundation (foundational location hierarchy)

**Required Properties:**

- id: string (UUID) - Unique identifier
- name: string - Location name
- workspace: string (UUID) - Workspace ID containing the location
- createdAt: date-time - ISO-8601 timestamp of creation
- createdBy: string (UUID) - User ID who created the location
- updatedAt: date-time - ISO-8601 timestamp of last update
- updatedBy: string (UUID) - User ID who last updated the location
- path: string - Hierarchical path with location IDs (e.g., "/id1/id2/id3")
- pathWithNames: string - Hierarchical path with location names (e.g., "/Lab/Cabinet/MyLocation")
- pathUpdatedAt: date-time - ISO-8601 timestamp of last path update
- pathUpdatedBy: string (UUID) - User ID who last updated the path
- scanCode: string - Barcode/scan code for location identification

**Optional Properties:**

- type: string - Location type/category (e.g., "Calibration lab", "Production floor")
- enabled: boolean (default: true) - Whether location is active
- description: string - Detailed description of the location
- parentId: string (UUID) - Parent location ID for hierarchical organization
- properties: object (string → string) - Custom key-value metadata properties
- keywords: array[string] - Search keywords associated with the location

**Relationships:**

- references: None direct references to other resources
- referenced_by: Asset, DUT, Fixture may reference a location via properties
- constraints:
  - Location hierarchy forms a tree structure (single parent per location)
  - Parent location must exist before creating child locations
  - Cannot create circular parent-child relationships

**States/Enums:**

- enabled: boolean (active or inactive)

---

## Asset

**Purpose:** Physical equipment, devices, or components that can be managed and tracked across locations.

**Tier:** 1 - Core Resources (managed equipment)

**Required Properties:**

- id: string (UUID) - Unique identifier
- name: string - Asset name/identifier
- workspace: string (UUID) - Workspace ID containing the asset

**Optional Properties:**

- type: string - Asset type classification
- description: string - Asset description
- location: string (UUID) - Current location ID (references Location)
- serialNumber: string - Serial number or asset tag
- properties: object (string → string) - Custom metadata properties
- keywords: array[string] - Search keywords

**Relationships:**

- references: Location (via location property)
- referenced_by: TestPlan, WorkOrder, Fixture
- constraints: None specified in schema

**States/Enums:**

- No explicit states defined in the schema

---

## Product

**Purpose:** Definition of products/devices under test including part numbers, families, and specifications.

**Tier:** 1 - Core Resources (product catalog)

**Required Properties:**

- id: string (UUID) - Unique identifier
- partNumber: string - Product part number
- name: string - Product name
- workspace: string (UUID) - Workspace ID containing the product

**Optional Properties:**

- family: string - Product family classification (e.g., "cRIO", "BTS")
- keywords: array[string] - Associated keywords
- properties: object (string → string) - Custom metadata properties
- fileIds: array[string] - Attached file IDs (references File service)
- updatedAt: date-time - Timestamp of last update

**Relationships:**

- references: File (via fileIds)
- referenced_by: TestPlan, TestResult
- constraints: Part number must be unique within workspace

**States/Enums:**

- No explicit states defined

---

## Feed

**Purpose:** Package repository management enabling hosting of software packages within SystemLink.

**Tier:** 1 - Core Resources (package distribution)

**Required Properties:**

- id: string (UUID) - Unique identifier
- name: string (max 100 chars) - Feed name
- platform: enum ["WINDOWS", "NI_LINUX_RT"] - Target platform for packages

**Optional Properties:**

- description: string (max 500 chars) - Feed description
- workspace: string (UUID) - Workspace ID (uses default workspace if not specified)
- updatedAt: date-time - Timestamp of last update
- createdAt: date-time - Timestamp of creation

**Relationships:**

- references: Package (indirect, contains packages)
- referenced_by: System (systems can be connected to feeds)
- constraints:
  - Platform determines package extension (.nipkg for WINDOWS, .ipk/.deb for NI_LINUX_RT)
  - Feed names must be unique within workspace and platform combination

**States/Enums:**

- platform: ["WINDOWS", "NI_LINUX_RT"]

---

## Tag

**Purpose:** Timestamped key-value pair data for real-time data publishing and monitoring.

**Tier:** 1 - Core Resources (data collection)

**Required Properties:**

- path: string - Tag path/identifier (workspace-scoped unique)
- type: enum [DOUBLE, INT, STRING, BOOLEAN, U_INT64, DATE_TIME] - Data type of tag values
- workspace: string (UUID) - Workspace ID containing the tag

**Optional Properties:**

- keywords: array[string] - Search keywords associated with the tag
- properties: object (string → string) - Custom metadata properties
- lastUpdated: date-time - Timestamp of last value update
- description: string - Tag description

**Relationships:**

- references: Workspace
- referenced_by: Selection (tags grouped into selections)
- constraints:
  - Tag path is case-sensitive
  - Tag data type cannot be changed after creation
  - Tag path is unique within workspace

**States/Enums:**

- type: [DOUBLE, INT, STRING, BOOLEAN, U_INT64, DATE_TIME]

**Properties:**

- current: TimestampedTagValue - Current value with timestamp
- aggregates: V2TagAggregates - min, max, avg (mean), count values

---

## TestResult

**Purpose:** Record of executed test including status, timeline, and associated data.

**Tier:** 2 - Data Records (test execution outcomes)

**Required Properties:**

- id: string (UUID) - Unique identifier
- programName: string - Test program name
- status: StatusObject - Test execution status
- workspace: string (UUID) - Workspace ID

**Optional Properties:**

- systemId: string - System ID where test executed
- hostName: string - Host/machine name
- operator: string - Operator name/ID
- partNumber: string - DUT part number
- serialNumber: string - DUT serial number
- properties: object (string → string) - Custom metadata properties
- keywords: array[string] - Search keywords
- fileIds: array[string] - Attached file IDs
- dataTableIds: array[string] - Attached DataFrame table IDs
- startedAt: date-time - Test start time
- updatedAt: date-time - Last update time
- totalTimeInSeconds: number (double) - Total test execution duration
- statusTypeSummary: object (string → int) - Status counts by type (e.g., FAILED: 5)

**Relationships:**

- references:
  - Product (via partNumber)
  - File (via fileIds)
  - DataFrame (via dataTableIds)
  - System (via systemId)
- referenced_by: TestStep (parent), TestPlan
- constraints: Cannot change test result status after closure

**States/Enums:**

- status: StatusObject with properties:
  - type: string (e.g., PASSED, FAILED, ERROR)
  - message: string

---

## TestStep

**Purpose:** Individual step/substask within a test result showing hierarchical test structure and outcomes.

**Tier:** 2 - Data Records (test execution detail)

**Required Properties:**

- stepId: string - Unique step identifier within result
- resultId: string (UUID) - Parent test result ID
- name: string - Step name
- status: StatusObject - Step execution status

**Optional Properties:**

- parentId: string - Parent step ID (for hierarchical steps)
- children: array[TestStep] - Nested child steps
- data: StepDataObject - Text and parameter outputs from step
- dataModel: string - Data model format (e.g., "TestStand")
- startedAt: date-time - Step start time
- totalTimeInSeconds: number (double) - Step execution duration
- stepType: string - Classification of step (e.g., "NumericLimitTest")
- inputs: array[NamedValueObject] - Input parameters and values
- outputs: array[NamedValueObject] - Output measurements and values
- keywords: array[string] - Search keywords
- properties: object (string → string) - Custom metadata

**Relationships:**

- references: TestResult (parent via resultId)
- referenced_by: Path (step execution patterns)
- constraints:
  - resultId must reference existing TestResult
  - parentId must reference existing step in same result if specified

**States/Enums:**

- status: StatusObject

---

## TestPlan

**Purpose:** Definition and configuration for executing test on DUTs including workflow state management.

**Tier:** 2 - Operational (test execution planning)

**Required Properties:**

- id: string (UUID) - Unique identifier
- name: string (max 200) - Test plan name
- workspace: string (UUID) - Workspace ID

**Optional Properties:**

- state: enum [NEW, DEFINED, REVIEWED, SCHEDULED, IN_PROGRESS, PENDING_APPROVAL, CLOSED, CANCELED] - Current state
- description: string (max 10000) - Detailed description
- assignedTo: string (UUID) - User ID assignment
- partNumber: string (max 200) - DUT part number (references Product)
- dutId: string (max 200) - Asset/DUT ID (references Asset)
- dutSerialNumber: string (max 200) - Serial number for test
- testProgram: string (max 200) - Test program name/path
- workOrderId: string (max 200) - Linked work order ID (references WorkOrder)
- estimatedDurationInSeconds: integer - Estimated test runtime
- systemFilter: string (max 10000) - LINQ filter for eligible systems
- dutFilter: string (max 10000) - LINQ filter for eligible DUTs
- executionActions: array[ExecutionDefinition] - Test plan actions/workflows
- fileIds: array[string] - Attached file IDs
- properties: object (string → string) - Custom metadata
- dashboard: DashboardReferenceDefinition - Associated dashboard configuration
- workflowId: string - Associated workflow ID (beta feature)
- templateId: string (max 200) - Source template ID
- createdBy: string (UUID) - User who created test plan
- updatedBy: string (UUID) - User who last updated
- createdAt: date-time - Creation timestamp
- updatedAt: date-time - Last update timestamp

**Relationships:**

- references:
  - Product (via partNumber)
  - Asset (via dutId)
  - WorkOrder (via workOrderId)
  - File (via fileIds)
  - Workflow (via workflowId)
  - System (via systemFilter matching)
- referenced_by: TestResult (executed from)
- constraints:
  - State transitions follow defined workflow (NEW → DEFINED → REVIEWED → SCHEDULED → IN_PROGRESS → PENDING_APPROVAL → CLOSED/CANCELED)
  - Cannot delete test plan after IN_PROGRESS state

**States/Enums:**

- state: [NEW, DEFINED, REVIEWED, SCHEDULED, IN_PROGRESS, PENDING_APPROVAL, CLOSED, CANCELED]

**Execution Actions:**

- NoneExecutionDefinition: No automatic execution
- ManualExecutionDefinition: Manual action trigger
- NotebookExecutionDefinition: Jupyter notebook execution
- JobExecutionDefinition: Systems Management Job execution

---

## TestPlanTemplate

**Purpose:** Reusable template for creating test plans with predefined configurations.

**Tier:** 2 - Operational (test plan templates)

**Required Properties:**

- id: string (UUID) - Unique identifier
- name: string (max 200) - Template name
- templateGroup: string (max 200) - Template grouping/category
- workspace: string (UUID) - Workspace ID

**Optional Properties:**

- productFamilies: array[string] - Applicable product families (e.g., ["cRIO", "BTS"])
- partNumbers: array[string] - Applicable part numbers
- summary: string (max 10000) - Template summary
- description: string (max 10000) - Detailed description
- testProgram: string (max 200) - Default test program name
- estimatedDurationInSeconds: integer - Default estimated duration
- systemFilter: string (max 10000) - Default system filter
- dutFilter: string (max 10000) - Default DUT filter
- executionActions: array[ExecutionDefinition] - Template actions
- fileIds: array[string] - Template file attachments
- properties: object (string → string) - Default properties
- workflowId: string - Associated workflow template

**Relationships:**

- references: File, Workflow
- referenced_by: TestPlan (via templateId)
- constraints:
  - Template names must be unique within workspace
  - Cannot delete template if active test plans reference it

**States/Enums:**

- None (templates are configuration, not state-driven)

---

## WorkOrder

**Purpose:** High-level work request/task for managing test execution workflows and assignments.

**Tier:** 2 - Operational (work management)

**Required Properties:**

- id: string (UUID) - Unique identifier
- name: string (max 200) - Work order name
- type: enum [TEST_REQUEST] - Work order type
- workspace: string (UUID) - Workspace ID

**Optional Properties:**

- state: enum [NEW, DEFINED, REVIEWED, SCHEDULED, IN_PROGRESS, PENDING_APPROVAL, CLOSED, CANCELED] - Current state
- description: string (max 10000) - Detailed description
- assignedTo: string (UUID) - User ID assignment
- requestedBy: string (UUID) - User who requested the work
- earliestStartDate: date-time - Earliest execution date
- dueDate: date-time - Target completion date
- properties: object (string → string) - Custom metadata
- createdBy: string (UUID) - User who created work order
- updatedBy: string (UUID) - User who last updated
- createdAt: date-time - Creation timestamp
- updatedAt: date-time - Last update timestamp

**Relationships:**

- references: User (assignedTo, requestedBy)
- referenced_by: TestPlan (via workOrderId)
- constraints:
  - State transitions follow same workflow as TestPlan
  - dueDate should be after earliestStartDate if both specified

**States/Enums:**

- state: [NEW, DEFINED, REVIEWED, SCHEDULED, IN_PROGRESS, PENDING_APPROVAL, CLOSED, CANCELED]
- type: [TEST_REQUEST]

---

## Workflow

**Purpose:** State machine definition for managing transitions and actions in work orders and test plans.

**Tier:** 2 - Operational (workflow orchestration)

**Required Properties:**

- id: string (UUID) - Unique identifier
- name: string (max 128) - Workflow name
- workspace: string (UUID) - Workspace ID
- states: array[WorkflowState] - State definitions

**Optional Properties:**

- actions: array[WorkflowAction] - Available actions
- description: string - Workflow description

**WorkflowState:**

- name: string - State name (matches standard states: NEW, DEFINED, REVIEWED, SCHEDULED, IN_PROGRESS, PENDING_APPROVAL, CLOSED, CANCELED)
- displayText: string - UI display name
- dashboardAvailable: boolean - Whether dashboard is available in this state
- defaultSubstate: string - Default substate when entering state
- substates: array[WorkflowSubstate] - Substates within this state

**WorkflowSubstate:**

- name: string - Substate name
- displayText: string - UI display name
- availableActions: array[ActionTransitionDefinition] - Available actions from this substate

**ActionTransitionDefinition:**

- action: string - Action ID
- nextState: string - State to transition to
- nextSubstate: string - Substate to transition to
- showInUI: boolean - Whether to display in UI

**Relationships:**

- references: None (defines structure for other resources)
- referenced_by: TestPlan, WorkOrder
- constraints:
  - State names must use defined set
  - Transitions must form valid directed graph

**States/Enums:**

- Workflow states: [NEW, DEFINED, REVIEWED, SCHEDULED, IN_PROGRESS, PENDING_APPROVAL, CLOSED, CANCELED]

---

## System

**Purpose:** Distributed system/machine that can execute jobs and host test infrastructure.

**Tier:** 1 - Core Resources (system management)

**Required Properties:**

- id: string (UUID) - Unique system identifier
- alias: string - User-friendly system name
- workspace: string (UUID) - Workspace ID

**Optional Properties:**

- createdTimestamp: date-time - Creation time
- lastUpdatedTimestamp: date-time - Last update time
- orgId: string (UUID) - Organization ID
- removed: boolean - Whether system is removed/archived

**System Properties:**

- connected: SystemConnectedStatus - Connection state and timestamp
  - state: enum [CONNECTED, DISCONNECTED, OFFLINE]
  - lastPresentTimestamp: date-time
  - lastUpdatedTimestamp: date-time
- grains: SystemData - Hardware/OS information
  - kernel: string (e.g., "Windows")
  - osversion: string
  - host: string
  - cpuarch: string (e.g., "AMD64")
  - deviceclass: string
- status: SystemData - System status data
  - http_connected: boolean
- packages: SystemData - Installed packages (map of package info)
- feeds: SystemData - Configured package feeds
- keywords: array[string] - Search keywords
- properties: object - System custom properties

**Relationships:**

- references: Workspace, Organization
- referenced_by: TestPlan (via systemFilter), Job, TestResult
- constraints:
  - System alias must be unique within workspace
  - Connected status is managed by system reporting

**States/Enums:**

- connected.state: [CONNECTED, DISCONNECTED, OFFLINE]

---

## DataFrame (Data Table)

**Purpose:** Columnar data storage for storing test results data, measurements, and analysis results.

**Tier:** 2 - Data Records (data storage)

**Required Properties:**

- id: string - Unique table identifier
- workspace: string (UUID) - Workspace ID
- columns: array[HttpColumn] - Column definitions (minimum 1 column)

**HttpColumn (Column Definition):**

- name: string (max 256) - Unique column name within table
- dataType: enum [INT32, BOOL, INT64, FLOAT32, FLOAT64, STRING, TIMESTAMP] - Column data type
- columnType: enum [NORMAL, INDEX, NULLABLE] (default: NORMAL) - Column classification
- properties: object (string → string) - Column metadata

**Column Types:**

- INDEX: Unique value per row (one per table, must be INT32, INT64, or TIMESTAMP)
- NULLABLE: Can contain null values
- NORMAL: Regular column (default)

**Optional Properties:**

- name: string (max 256) - Table name (auto-assigned from ID if not provided)
- properties: object (string → string) - Table metadata
- testResultId: string - Associated TestResult ID
- createdAt: date-time - Creation timestamp
- metadataModifiedAt: date-time - Metadata change timestamp
- metadataRevision: integer - Metadata version number
- rowsModifiedAt: date-time - Data modification timestamp
- rowCount: integer - Number of rows in table
- supportsAppend: boolean - Whether table accepts new rows

**Data Format:**

- DataFrame object with columns array and data array (2D array of values)
- Values encoded as strings per column type rules
- TIMESTAMP format: ISO-8601 with UTC and millisecond precision
- BOOL: "true" or "false" (case-insensitive)
- Null values: represented as null in JSON

**Relationships:**

- references: TestResult (via testResultId)
- referenced_by: TestResult (via dataTableIds)
- constraints:
  - Exactly one INDEX column required per table
  - Column names must be unique within table
  - Maximum 256 chars per column name
  - Cannot change column data types after creation

**States/Enums:**

- dataType: [INT32, BOOL, INT64, FLOAT32, FLOAT64, STRING, TIMESTAMP]
- columnType: [NORMAL, INDEX, NULLABLE]

---

## ResourceGroup

**Purpose:** Hierarchical resource allocation and management for controlling resource access and limits.

**Tier:** 1 - Core Resources (resource management)

**Required Properties:**

- id: string (UUID) - Unique identifier
- name: string - Resource group name
- workspace: string (UUID) - Workspace ID

**Optional Properties:**

- type: string - Resource type classification (e.g., "Power (kW)")
- description: string - Detailed description
- parent: string (UUID) - Parent resource group ID (hierarchical)
- desiredState: enum [OFFLINE, PENDING_OFFLINE, ONLINE, DISABLED] - Requested state
- currentState: enum [OFFLINE, PENDING_OFFLINE, ONLINE, DISABLED] - Actual state
- behavior: enum [ACQUISITION, RELEASE, BIDIRECTIONAL] - Resource access pattern
- limits: array[ResourceGroupLimit] - Resource allocation limits
- properties: object (string → string) - Custom metadata
- createdBy: string (UUID) - User ID
- updatedBy: string (UUID) - User ID
- createdAt: date-time - Timestamp
- updatedAt: date-time - Timestamp

**ResourceGroupLimit:**

- severity: enum [MODERATE, HIGH, CRITICAL] - Limit criticality
- direction: enum [ACQUISITION, RELEASE] - Limit direction
- limit: number (double) - Limit value

**Relationships:**

- references: Parent ResourceGroup (hierarchical)
- referenced_by: Child ResourceGroups
- constraints:
  - Forms tree hierarchy (single parent per group)
  - No circular parent-child relationships allowed
  - State transitions: OFFLINE ↔ ONLINE → DISABLED or PENDING_OFFLINE

**States/Enums:**

- desiredState: [OFFLINE, PENDING_OFFLINE, ONLINE, DISABLED]
- currentState: [OFFLINE, PENDING_OFFLINE, ONLINE, DISABLED]
- behavior: [ACQUISITION, RELEASE, BIDIRECTIONAL]
- limits.severity: [MODERATE, HIGH, CRITICAL]

---

## DUT (Device Under Test)

**Purpose:** Represents a specific device/unit being tested, usually identified by serial number and part number.

**Tier:** 1 - Core Resources (test subject)

**Required Properties:**

- id: string (UUID) - Unique identifier
- partNumber: string - DUT part number (references Product)
- serialNumber: string - Unique serial number

**Optional Properties:**

- workspace: string (UUID) - Workspace ID
- location: string (UUID) - Current location (references Location)
- status: string - Current status (e.g., "AVAILABLE", "IN_TEST", "FAILED")
- properties: object (string → string) - Custom metadata
- keywords: array[string] - Search keywords
- assignedTo: string (UUID) - User/system assignment
- createdAt: date-time - Timestamp
- updatedAt: date-time - Timestamp

**Relationships:**

- references:
  - Product (via partNumber)
  - Location (via location)
  - Asset (may be related)
- referenced_by: TestPlan, TestResult
- constraints:
  - Serial number must be unique within workspace
  - partNumber must reference valid Product

**States/Enums:**

- status: [AVAILABLE, IN_TEST, FAILED, MAINTENANCE, RETIRED] (inferred from test context)

---

## Fixture

**Purpose:** Test infrastructure equipment that supports DUT testing and measurement.

**Tier:** 1 - Core Resources (test infrastructure)

**Required Properties:**

- id: string (UUID) - Unique identifier
- name: string - Fixture name
- type: string - Fixture type/classification

**Optional Properties:**

- workspace: string (UUID) - Workspace ID
- location: string (UUID) - Current location (references Location)
- description: string - Fixture description
- serialNumber: string - Fixture serial number
- status: string - Current status
- properties: object (string → string) - Custom metadata
- keywords: array[string] - Search keywords
- calibrationDueDate: date-time - Next calibration date
- createdAt: date-time - Timestamp
- updatedAt: date-time - Timestamp

**Relationships:**

- references: Location (via location)
- referenced_by: TestPlan (via fixture references in configuration)
- constraints:
  - Fixture must be available (not in maintenance) to be assigned to test

**States/Enums:**

- status: [AVAILABLE, IN_USE, MAINTENANCE, CALIBRATION_DUE, OFFLINE]

---

## Selection

**Purpose:** Grouping mechanism for selecting multiple tags to operate on collectively.

**Tier:** 1 - Utility (tag grouping)

**Required Properties:**

- id: string (UUID) - Unique identifier
- name: string - Selection name

**Optional Properties:**

- description: string - Selection description
- tags: array[Tag] - Tags included in selection
- workspace: string (UUID) - Workspace ID
- createdAt: date-time - Timestamp
- updatedAt: date-time - Timestamp

**Relationships:**

- references: Tag (collection of tags)
- referenced_by: Subscription
- constraints:
  - Selection must contain at least one tag
  - Tags within selection must be in same workspace

**States/Enums:**

- None

---

## Path

**Purpose:** Pattern or sequence of test steps executed in test execution records.

**Tier:** 2 - Data Records (test pattern analysis)

**Required Properties:**

- id: string (UUID) - Path identifier
- path: string - Path representation (step sequence)
- programName: string - Test program name
- partNumber: string - DUT part number

**Optional Properties:**

- pathNames: array[string] - Ancestor step names in path
- inputs: object - Input parameters (name → ValueSummary)
- outputs: object - Output measurements (name → ValueSummary)
- measurements: object - Measurement data (name → object)

**ValueSummary:**

- type: enum [NUMBER, STRING] - Value type
- min: number - Minimum value (if type is NUMBER)
- max: number - Maximum value (if type is NUMBER)

**Relationships:**

- references: TestResult (via steps), Product (via partNumber)
- referenced_by: Analysis and reporting
- constraints:
  - Path must correspond to actual executed steps in TestResult

**States/Enums:**

- None

---

## Job

**Purpose:** Systems Management Job definition for executing remote commands on systems.

**Tier:** 1 - Execution (system commands)

**Required Properties:**

- functions: array[string] - Salt job functions to execute
- arguments: array[array] - Arguments per function
- metadata: object - Job metadata (optional)

**Optional Properties:**

- queued: boolean - Whether job is queued
- refresh_minion_cache: object - Cache refresh configuration
- user_id: string - User ID
- user_login: string - User login name

**Relationships:**

- references: System (target systems)
- referenced_by: TestPlan (JobExecutionDefinition)
- constraints:
  - Functions must be valid Salt functions
  - Arguments array length must match functions array length

**States/Enums:**

- Job states: [NEW, QUEUED, RUNNING, COMPLETED, FAILED, CANCELED]

---

## Package

**Purpose:** Software package contained within a Feed.

**Tier:** 1 - Artifacts (package distribution)

**Required Properties:**

- id: string (UUID) - Unique identifier
- name: string - Package name
- feedId: string (UUID) - Parent feed ID

**Optional Properties:**

- version: string - Package version
- description: string - Package description
- size: integer - Package file size (bytes)
- updatedAt: date-time - Last update timestamp
- createdAt: date-time - Creation timestamp

**Relationships:**

- references: Feed (parent)
- referenced_by: System (installed packages)
- constraints:
  - Package name must be unique within feed
  - Must conform to platform-specific format (.nipkg, .ipk, .deb)

**States/Enums:**

- None (packages are artifacts)

---

## Selection (Tag Selection)

**Purpose:** Named collection of tags for bulk operations and monitoring.

**Tier:** 1 - Utility (tag grouping)

**Required Properties:**

- id: string (UUID) - Unique identifier
- workspace: string (UUID) - Workspace ID

**Optional Properties:**

- name: string - Selection name
- description: string - Description
- tags: array[Tag] - Included tags

**Relationships:**

- references: Tag (collection of multiple tags)
- referenced_by: Subscription (subscriptions monitor selections)
- constraints:
  - All tags must be in same workspace
  - Selection can be empty

**States/Enums:**

- None

---

## Resource Hierarchy and Tiers

### Tier 0: Foundation

- **Location** - Foundational physical hierarchy

### Tier 1: Core Resources

- **Asset** - Physical equipment
- **Product** - Product definitions/catalog
- **System** - Computing systems/machines
- **Feed** - Package repositories
- **Tag** - Time-series data points
- **DUT** - Device under test
- **Fixture** - Test infrastructure equipment
- **ResourceGroup** - Resource allocation hierarchy
- **Job** - Remote execution definitions
- **Package** - Software artifacts
- **Selection** - Tag groupings (utility)

### Tier 2: Data & Operations

- **TestResult** - Recorded test execution
- **TestStep** - Individual test steps
- **TestPlan** - Test execution definition
- **TestPlanTemplate** - Test plan template
- **WorkOrder** - Work management
- **Workflow** - State machine definition
- **DataFrame** - Data table storage
- **Path** - Test pattern analysis

---

## Cross-Resource Relationships Summary

### Reference Graph (simplified)

```
Location
├─ Asset
├─ DUT
└─ Fixture

Product
├─ TestPlan (via partNumber)
└─ TestResult (via partNumber)

System
├─ TestPlan (via systemFilter)
├─ TestResult (via systemId)
└─ Job (execution target)

Feed
└─ Package

Tag
└─ Selection

TestPlan
├─ TestResult (execution creates)
├─ WorkOrder (via workOrderId)
├─ Product (via partNumber)
├─ Asset (via dutId)
└─ Workflow (execution model)

TestResult
├─ TestStep (hierarchical children)
├─ DataFrame (via dataTableIds)
└─ Path (pattern analysis)

WorkOrder
└─ TestPlan (linked work items)

ResourceGroup
└─ ResourceGroup (hierarchical parent/child)

Workflow
├─ TestPlan (defines states)
└─ WorkOrder (defines states)
```

---

## State Transition Rules

### Standard Workflow States

All state-driven resources (TestPlan, WorkOrder, Workflow) follow this state machine:

```
NEW → DEFINED → REVIEWED → SCHEDULED → IN_PROGRESS → PENDING_APPROVAL → CLOSED
                                    ↓
                                CANCELED
```

**State Descriptions:**

- **NEW**: Initial state, freshly created
- **DEFINED**: Requirements/specifications defined
- **REVIEWED**: Reviewed and approved for execution
- **SCHEDULED**: Scheduled for execution
- **IN_PROGRESS**: Currently executing
- **PENDING_APPROVAL**: Awaiting approval to close
- **CLOSED**: Completed successfully
- **CANCELED**: Terminated without completion

### ResourceGroup States

```
OFFLINE ↔ ONLINE
  ↓         ↓
PENDING_OFFLINE OR DISABLED
```

### System Connection States

```
CONNECTED ↔ DISCONNECTED → OFFLINE
```

---

## Constraints and Validation Rules

### Universal Constraints

1. **Workspace Scoping**: All resources must belong to a workspace; workspace ID is required
2. **ID Uniqueness**: IDs (UUIDs) are globally unique within the system
3. **Name Uniqueness**: Names must be unique within scope (workspace for most resources)
4. **Timestamp Format**: All timestamps use ISO-8601 format with UTC
5. **Audit Trail**: createdBy, updatedBy, createdAt, updatedAt tracked on major resources

### Resource-Specific Constraints

**Location**

- Hierarchical: Single parent per location, no circular relationships
- Parent must exist before child creation

**TestPlan**

- Cannot delete after IN_PROGRESS
- State transitions follow standard workflow
- DUT must exist (if dutId specified)
- Product must exist (if partNumber specified)

**TestResult**

- Status is immutable after CLOSED state
- TestStep.resultId must reference valid TestResult
- dataTableIds must reference existing DataFrames

**DataFrame**

- Exactly one INDEX column required
- Column names must be unique within table
- Column data types are immutable
- NULLABLE columns can omit values when appending

**Tag**

- Tag path must be unique within workspace
- Data type is immutable after creation
- Path is case-sensitive

**ResourceGroup**

- Circular parent-child relationships prohibited
- Type inheritance from parent (if not explicitly set)

**System**

- Alias must be unique within workspace
- Connection state automatically managed
- Properties reflect actual system state

**Feed**

- Platform determines compatible package types
- Name unique within (workspace, platform) combination

---

## Search and Filter Capabilities

### FilteredResponse Pattern

Most list operations support:

- **Pagination**: take/skip or continuationToken
- **Filtering**: Query filters (often LINQ-based)
- **Sorting**: orderBy field with ascending/descending
- **Projection**: Select specific fields
- **Count**: Optional total count return

### Common Filter Operators

- `=` (equals)
- `!=` (not equals)
- `>`, `<`, `>=`, `<=` (comparisons)
- `.Contains()` (array membership)
- `AND`, `OR` (logical operators)
- Glob wildcards in paths

### Tag Query Filter Example

```
(path = "*.System.Health.*") OR keywords.Contains("critical")
```

### System Filter Example (LINQ)

```
properties.data["Lab"] = "Battery Pack Lab" AND grains.data["kernel"] = "Windows"
```

---

## Data Type Mappings

### Tag Data Types

- **DOUBLE**: 64-bit floating point
- **INT**: Signed integer (varies)
- **STRING**: Text string
- **BOOLEAN**: True/false
- **U_INT64**: 64-bit unsigned integer
- **DATE_TIME**: ISO-8601 timestamp

### DataFrame Column Types

- **INT32**: 32-bit signed integer
- **INT64**: 64-bit signed integer
- **BOOL**: Boolean
- **FLOAT32**: 32-bit IEEE 754 floating point
- **FLOAT64**: 64-bit IEEE 754 floating point
- **STRING**: Text string
- **TIMESTAMP**: UTC timestamp (millisecond precision, ISO-8601)

---

## Notes and Observations

1. **Workspace Multi-tenancy**: All resources are workspace-scoped, enabling isolated environments
2. **Audit Compliance**: Major resources track creation/update audit trail (user + timestamp)
3. **Flexible Metadata**: Custom properties and keywords on most resources enable extensibility
4. **Hierarchical Organization**: Location and ResourceGroup support hierarchical structures
5. **Type Safety**: Data types are strictly enforced in DataFrame columns
6. **Workflow-Driven**: TestPlan, WorkOrder, and Workflow form a consistent state machine pattern
7. **Async Operations**: Some operations (like job execution) return continuation tokens for polling
8. **Null Handling**: NULLABLE column type explicit; most properties default to null when not specified
9. **Historical Data**: TestResult and TestStep form permanent audit records
10. **Real-time Capability**: Tag service supports real-time value updates with aggregates (min/max/avg/count)

---

## Analysis Methodology

This analysis was extracted from 8 OpenAPI specification files:

1. niresourcemanagement.json - ResourceGroup and hierarchy
2. nisysmgmt.json - System and Job definitions
3. nifeed.json - Feed and Package management
4. nitag-2.yaml - Tag service and Selection
5. niworkorder-3.json - WorkOrder, TestPlan, TestPlanTemplate, Workflow
6. nitestmonitor-v2.yml - TestResult, TestStep, Product, Path definitions
7. nidataframe.json - DataFrame/DataTable definitions
8. nilocation.json - Location management

All information extracted from schema definitions, required/optional property lists, enum values, and relationship references within the specifications. No external assumptions or inferences beyond the schemas themselves.
