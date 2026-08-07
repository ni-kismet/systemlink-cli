# Demo Test Plans Example

This example provides a complete, ready-to-use setup for demonstrating SystemLink test planning workflows.

## What's Included

The example creates the following resources in your SystemLink workspace:

### Infrastructure

- **Location**: Demo HQ (Austin, TX)
- **Product**: Demo Widget Pro (Industrial Equipment)

### Test Infrastructure

- **Systems**:
  - Test Stand 1 (Serial: TS-001)
  - Test Stand 2 (Serial: TS-002)
- **Assets**:
  - Asset 1 on Test Stand 1 (Serial: ASSET-001)
  - Asset 2 on Test Stand 2 (Serial: ASSET-002)
- **DUTs**:
  - DUT 1 - Model X1 (Serial: DUT-001) on Asset 1
  - DUT 2 - Model X2 (Serial: DUT-002) on Asset 2

### Test Planning

- **Test Template**: Demo Test Template
  - Pre-configured for both test systems
  - Ready to use in test creation workflow

## Setup Time

Approximately **5 minutes** to provision all resources.

## Installation Steps

### 1. Preview the resources

```bash
slcli example info demo-test-plans
```

This shows all 9 resources that will be created.

### 2. Dry-run (validate without creating)

```bash
slcli example install demo-test-plans -w <workspace-id> --dry-run
```

### 3. Install to a workspace

```bash
slcli example install demo-test-plans -w <workspace>
```

Optionally write an audit log with JSON output:

```bash
slcli example install demo-test-plans -w <workspace> --audit-log install-log.json --format json
```

### 4. Verify in SystemLink Web UI

1. Open SystemLink web interface
2. Navigate to **Assets & Test Planning**
3. Verify that locations, products, systems, assets, and DUTs are visible

## Using the Example

Once installed, you can:

1. **Create a test** from the Demo Test Template
2. **Schedule test execution** on Test Stand 1 or Test Stand 2
3. **Run tests** against DUT 1 or DUT 2
4. **Track results** in test history

## Cleanup

To remove all example resources:

```bash
# Preview what would be deleted
slcli example delete demo-test-plans -w <workspace-id> --dry-run

# Delete all demo-tagged resources in a workspace
slcli example delete demo-test-plans -w <workspace>

# Write an audit log of deletion results
slcli example delete demo-test-plans -w <workspace> --audit-log delete-log.json --format json
```

**Important**: Cleanup only deletes resources tagged with "demo". Any resources you created or modified separately will not be deleted.

## Troubleshooting

### Example installation fails

Check that your workspace exists:

```bash
slcli workspace list
```

If no workspace exists, create one:

```bash
slcli workspace create --name "Default workspace"
```

### Resources not visible in web UI

1. Ensure you're viewing the correct workspace
2. Refresh the web browser
3. Check workspace settings: Assets & Test Planning > Settings

### Can't delete resources

1. Verify workspace permissions
2. Confirm resources are tagged for deletion in the config

## Next Steps

After installing this example, consider:

1. Creating additional test templates for different product lines
2. Adding more test systems or DUTs
3. Creating workflows to automate test execution
4. Setting up data logging to track results over time

For more information, see the [SystemLink documentation](https://docs.systemlink.local/).
