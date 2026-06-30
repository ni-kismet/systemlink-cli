# SystemLink Python Test Application

Load this overview when the task is about a Python-based device test application
that integrates with SystemLink. Stay in this file until the task reaches packaging,
then load [../nipkg/overview.md](../nipkg/overview.md) only for the package structure,
control metadata, or deployment layout.

## When to Use

- Creating a new Python test application for an electronic or mechanical device
- Integrating an existing test script with SystemLink results, work items, and assets
- Setting up test result reporting with steps, measurements, limits, and inputs/outputs
- Packaging a test application as a `.nipkg` for feed deployment
- Creating work item templates for test scheduling

## Prerequisites

- Python 3.10+
- `nisystemlink-clients` as the primary communication layer
- SystemLink server with Test Monitor, Asset Management, Work Order, and File services
- Valid API key with appropriate permissions for dev-mode runs

## Procedure

Follow these phases in order when creating a new test application.

### Phase 1: Project setup

Create a structure like:

```text
tests/<PART_NUMBER>/
├── config.py
├── initialization.py
├── execution.py
├── simulator.py
├── main.py
├── requirements.txt
├── build_nipkg.bat
├── package/
│   ├── control
│   ├── instructions
│   ├── postinstall.bat
│   └── preuninstall.bat
└── deploy/
    ├── work-item-template.json
    └── workflow.json
```

Rules:

- Put credentials behind CLI args, environment variables, or auto-discovery.
- Never hard-code API keys.
- Keep `PRODUCT_SPECS` defaults in code so incomplete product properties do not block execution.

### Phase 2: Initialization

Initialization should:

1. Accept the work item ID.
2. Query the work item.
3. Resolve the product by part number.
4. Resolve spec properties, with fallback to `PRODUCT_SPECS`.
5. Resolve the DUT from the work item resources.
6. Resolve the system ID or local minion ID.
7. Check fixture calibration status.
8. Read work item properties used as test parameters.
9. Validate required inputs.
10. Show an operator summary in interactive mode.

### Phase 2a: System ID resolution

The system ID links results and files to the correct test system.

- On managed systems where configuration is `None`, read the local minion ID from disk.
- In developer mode, use the assigned system resource from the work item.
- Fall back cleanly if the local read fails.

### Phase 3: Test execution

Execution should:

1. Create a RUNNING result before any steps execute.
2. Transition the work item to `IN_PROGRESS`.
3. Execute steps sequentially.
4. Upload files.
5. Update the result with final status and uploaded file IDs.
6. Transition the work item to `PENDING_APPROVAL`, not `CLOSED`.

### Phase 3a: Step creation

Critical SDK rules for `CreateStepRequest`:

- `step_id` is required and should be `str(uuid.uuid4())`.
- `result_id` is required.
- `name` is required.
- Use `NamedValue` objects for `inputs` and `outputs`.
- Use `StepData` with `Measurement` objects for parametric data.
- Use `Status(status_type=StatusType.PASSED)` style enums, not raw strings.

### Phase 3b: File upload

Critical `FileClient.upload_file()` rules:

- Pass a `BinaryIO` object, not a path.
- The return value is a file ID string.
- `metadata` should be a `dict[str, str]`.
- Always write log files with `encoding="utf-8"`.

### Phase 4: Result and step schema

Minimum result expectations:

- set `status` to RUNNING at creation time
- include program, operator, serial, part number, host name, and workspace when available
- include `workItemId` in result properties
- set `system_id` when it can be resolved

Minimum step expectations:

- provide `step_id`, `result_id`, and `name`
- include `status`, `step_type`, and data payloads where relevant
- store useful `step.*`, `input.*`, and `output.*` properties

### Phase 5: SDK usage

All SystemLink communication should use `nisystemlink-clients`.

Common verified import paths include:

- `nisystemlink.clients.core.HttpConfiguration`
- `nisystemlink.clients.testmonitor.TestMonitorClient`
- `nisystemlink.clients.product.ProductClient`
- `nisystemlink.clients.work_item.WorkItemClient`
- `nisystemlink.clients.assetmanagement.AssetManagementClient`
- `nisystemlink.clients.file.FileClient`

SDK gotchas:

- `CreateStepRequest` requires `step_id`.
- `upload_file()` returns a string file ID.
- `get_configuration()` returning `None` is valid on managed systems.
- Measurement and limit values should often be passed as strings.
- Product properties may be incomplete and need fallbacks.
- Work item state transitions should use `IN_PROGRESS` and `PENDING_APPROVAL`.

### Phase 6: Packaging and deployment

Package the test application as a `.nipkg` file package for feed distribution.
Load [../nipkg/overview.md](../nipkg/overview.md) when you need:

- required `debian-binary`, `control`, and `data` layout
- valid Windows target root names
- control file fields and instructions format
- build script structure
- common `nipkg pack` failure modes

Test-app specifics not covered there:

- `postinstall.bat` should create a Python virtual environment and install `requirements.txt`.
- `preuninstall.bat` should remove the virtual environment.
- Upload packages with `slcli feed package upload`.
- If Python is not preinstalled on targets, pair the package with a Systems State deployment SLS.

### Phase 7: Work item template and workflow

Create and publish a workflow plus a work item template.

Workflow guidance:

- Model the lifecycle through states like `NEW`, `DEFINED`, `REVIEWED`, `SCHEDULED`, `IN_PROGRESS`, `PENDING_APPROVAL`, and `CLOSED`.
- Keep valid actions explicit in the workflow JSON.
- Import with `slcli workitem workflow import` and update with `slcli workitem workflow update`.

Template guidance:

- Use `partNumbers`, not `partNumberFilter`.
- Associate the workflow through `workflowId`.
- Add `executionActions` so tests start automatically when the work item starts.
