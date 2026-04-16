# End-to-End Testing Framework

This directory contains end-to-end (E2E) tests for the SystemLink CLI that run against a real SystemLink dev tier environment.

## Overview

The E2E testing framework validates that CLI commands work correctly against non-mocked SystemLink services. This provides confidence that the CLI integrates properly with the actual SystemLink APIs.

## Test Structure

```
tests/e2e/
├── conftest.py                 # Shared fixtures and configuration
├── test_mcp_e2e.py            # Local MCP streamable HTTP smoke test
├── test_notebook_e2e.py        # Notebook command tests
├── test_user_e2e.py           # User command tests
├── test_dff_e2e.py            # Custom Fields tests
├── test_workspace_e2e.py      # Workspace command tests
├── test_tag_e2e.py            # Tag command tests
├── run_e2e.py                 # E2E test runner
├── e2e_config.json.template   # Configuration template
└── README.md                  # This file
```

## Setup and Configuration

### 1. Environment Variables

Set these environment variables to configure E2E tests:

```bash
export SLCLI_E2E_BASE_URL="https://your-dev-systemlink.domain.com"
export SLCLI_E2E_API_KEY="your-api-key"
export SLCLI_E2E_WORKSPACE="Default"  # Optional, defaults to "Default"
export SLCLI_E2E_TIMEOUT="30"         # Optional, defaults to 30 seconds
export SLCLI_E2E_CLEANUP="true"       # Optional, defaults to true
```

### 2. Configuration File (Alternative)

Copy and customize the configuration template:

```bash
cp tests/e2e/e2e_config.json.template tests/e2e/e2e_config.json
```

Edit `e2e_config.json` with your dev environment details:

```json
{
  "base_url": "https://your-dev-systemlink.domain.com",
  "api_key": "your-api-key",
  "workspace": "Default",
  "timeout": 30,
  "cleanup": true
}
```

The E2E harness also supports a multi-platform config with separate `sle` and
`sls` sections:

```json
{
  "sle": {
    "base_url": "https://dev-api.lifecyclesolutions.ni.com",
    "api_key": "your-sle-api-key",
    "workspace": "Default",
    "test_notebook_id": "<sle-notebook-id>"
  },
  "sls": {
    "base_url": "https://your-sls-server",
    "api_key": "your-sls-api-key",
    "workspace": "Default",
    "test_notebook_path": "_shared/reports/Throughput.ipynb"
  },
  "timeout": 30,
  "cleanup": true
}
```

Notes:

- `test_notebook_path` is used by the SLS notebook execution tests.
- Use `--e2e-platform sle|sls` or `SLCLI_E2E_PLATFORM=sle|sls` to choose which
  platform the generic `cli_runner` and `configured_workspace` fixtures target.
- In `auto` mode, the generic fixtures still prefer SLE when both `sle` and
  `sls` are configured.

**⚠️ Important:** Add `e2e_config.json` to `.gitignore` to avoid committing credentials.

### 3. API Key Setup

The API key should have:

- Access to the configured workspace
- Permissions to create/read/update/delete notebooks
- Access to user management APIs
- Access to workspace management APIs
- Access to Custom Fields (if testing custom fields functionality)

## Running E2E Tests

### Run All E2E Tests

```bash
# Using the test runner
python tests/e2e/run_e2e.py

# Or directly with pytest
poetry run pytest tests/e2e/ -m e2e -v

# Force generic tests to target SystemLink Server
poetry run pytest tests/e2e/ -m e2e --e2e-platform sls -v

# Force generic tests to target SystemLink Enterprise
poetry run pytest tests/e2e/ -m e2e --e2e-platform sle -v
```

### Run The Local MCP Streamable HTTP Smoke Test

The MCP smoke test connects to a locally running streamable HTTP server and exercises the
full MCP tool surface that is expected to work in local environments.

Start the server in one terminal:

```bash
poetry run slcli mcp serve -T streamable-http
```

Run the smoke test in another terminal:

```bash
poetry run pytest tests/e2e/test_mcp_e2e.py -m e2e -v
```

Optional overrides:

```bash
export SLCLI_MCP_E2E_URL="http://127.0.0.1:8000/mcp"
export SLCLI_MCP_E2E_TIMEOUT="5"
export SLCLI_MCP_E2E_USER_ID="<known-user-id>"
export SLCLI_MCP_E2E_TAG_PATH="<known-tag-path>"
export SLCLI_MCP_E2E_SYSTEM_ID="<known-system-id>"
export SLCLI_MCP_E2E_ASSET_ID="<known-asset-id>"
export SLCLI_MCP_E2E_RESULT_ID="<known-result-id>"
export SLCLI_MCP_E2E_ROUTINE_ID="<known-routine-id>"
export SLCLI_MCP_E2E_FILE_ID="<known-file-id>"
export SLCLI_MCP_E2E_NOTEBOOK_ID="<known-notebook-id-or-path>"
export SLCLI_MCP_E2E_FEED_ID="<known-feed-id>"
export SLCLI_MCP_E2E_WEBAPP_ID="<known-webapp-id>"
export SLCLI_MCP_E2E_POLICY_ID="<known-policy-id>"
export SLCLI_MCP_E2E_COMMENT_RESOURCE_TYPE="workitem:workitem"
export SLCLI_MCP_E2E_COMMENT_RESOURCE_ID="<known-resource-id>"
```

Notes:

- This is a smoke test for MCP server stability and invocation breadth, not a
  guarantee that every local environment can return successful results for
  every tool.
- Some detail calls may legitimately return MCP-level errors in sparse,
  partially provisioned, or permission-limited environments; the test still
  verifies that those tools can be invoked without destabilizing the HTTP
  server.
- The test skips only when the local MCP endpoint is unreachable. Other failures
  are treated as real regressions.

### Run Specific Test Categories

```bash
# Notebook tests only
poetry run pytest tests/e2e/test_notebook_e2e.py -m e2e -v

# User management tests only
poetry run pytest tests/e2e/test_user_e2e.py -m e2e -v

# Workspace tests only
poetry run pytest tests/e2e/test_workspace_e2e.py -m e2e -v

# Custom fields tests only
poetry run pytest tests/e2e/test_dff_e2e.py -m e2e -v

# Tag tests only
poetry run pytest tests/e2e/test_tag_e2e.py -m e2e -v
```

### Run SLS-Supported E2E Tests

The only tests that are explicitly marked and curated for SLS today are the
supported SLS subset.

```bash
# Run the supported SLS subset
poetry run pytest tests/e2e/ -m "e2e and not sle" --e2e-platform sls -v

# Run the SLS notebook execution suite directly
poetry run pytest tests/e2e/test_notebook_e2e.py -m "e2e and sls" --e2e-platform sls -v

# Run the SLS notebook execution suite in parallel
poetry run pytest tests/e2e/test_notebook_e2e.py -m "e2e and sls" --e2e-platform sls -n auto -v
```

If you want to run a specific generic suite against SLS, select SLS explicitly:

```bash
# Example: run file E2E tests against SLS
poetry run pytest tests/e2e/test_file_e2e.py -m e2e --e2e-platform sls -v

# Example: run workspace E2E tests against SLS
poetry run pytest tests/e2e/test_workspace_e2e.py -m e2e --e2e-platform sls -v

# Example: run the SLE-only subset against SLE
poetry run pytest tests/e2e/ -m "e2e and sle" --e2e-platform sle -v
```

Tests marked `sle` are skipped automatically when targeting SLS, and tests
marked `sls` are skipped automatically when targeting SLE.

### Run with Different Markers

```bash
# Fast tests only (excludes slow/long-running tests)
poetry run pytest tests/e2e/ -m "e2e and not slow" -v

# Slow tests only
poetry run pytest tests/e2e/ -m "e2e and slow" -v

# Notebook-specific tests
poetry run pytest tests/e2e/ -m "e2e and notebook" -v

# Tag-specific tests
poetry run pytest tests/e2e/ -m "e2e and tag" -v
```

### Parallel Execution

E2E tests can be run in parallel to significantly reduce execution time:

```bash
# Auto-detect CPU count and run in parallel
poetry run pytest tests/e2e/ -n auto

# Run with specific number of workers
poetry run pytest tests/e2e/ -n 4

# Combine with other options
poetry run pytest tests/e2e/ -m "e2e and not slow" -n auto -v
```

**Benefits:**

- Reduces test execution time by ~60-70%
- Each worker runs tests in isolation
- Safe for tests that create independent resources

**Requirements:**

- `pytest-xdist` must be installed (included in dev dependencies)
- Tests must be stateless and not depend on execution order
- Each test should clean up its own resources

**Verifying Parallel Safety:**

```bash
# Run tests multiple times in parallel to detect race conditions
poetry run pytest tests/e2e/ -n auto --count=3

# Run with different worker counts to verify isolation
poetry run pytest tests/e2e/ -n 2
poetry run pytest tests/e2e/ -n 4

# Run specific test files in parallel
poetry run pytest tests/e2e/test_notebook_e2e.py -n auto -v
```

If tests fail only in parallel mode, they likely have:

- Shared resource naming conflicts (missing UUID)
- Missing cleanup (resources leak between runs)
- Order dependencies (test A expects test B ran first)

## Test Categories

### ✅ Core Functionality Tests

- User list operations with filtering and pagination
- Workspace read operations
- Basic CLI command validation
- Error handling and edge cases

### 📓 Notebook Tests

- Create, list, download, delete notebooks
- Notebook content validation
- Workspace filtering
- Name vs ID-based operations

### 🔧 Custom Fields Tests

- Configuration CRUD operations
- Groups and fields listing
- Template initialization
- Export/import functionality

### 🏢 Workspace Tests

- Workspace list and read operations
- Permission validation
- Workspace filtering

## Test Markers

The framework uses pytest markers to categorize tests:

- `@pytest.mark.e2e` - All E2E tests
- `@pytest.mark.slow` - Long-running tests
- `@pytest.mark.notebook` - Notebook-related tests
- `@pytest.mark.dff` - Custom Fields tests
- `@pytest.mark.workspace` - Workspace-related tests
- `@pytest.mark.user` - User management tests
- `@pytest.mark.sls` - SystemLink Server-specific tests
- `@pytest.mark.sle` - SystemLink Enterprise-specific tests

## Local Development Integration

### Manual Testing Only

The E2E testing framework is designed for local development and manual testing. Tests are run locally against development SystemLink environments to validate CLI functionality before releases.

### Environment Setup

Configure these environment variables for local E2E testing:

- `SLCLI_E2E_BASE_URL` - Dev environment URL
- `SLCLI_E2E_API_KEY` - Test user API key
- `SLCLI_E2E_WORKSPACE` - Target workspace (default: "Default")
- `SLCLI_E2E_TIMEOUT` - Request timeout in seconds (default: 30)
- `SLCLI_E2E_CLEANUP` - Clean up test resources (default: true)

## Test Design Principles

### 1. Statefulness and Isolation

Tests follow one of two patterns:

#### Pattern A: Read-Only (Fully Stateless)

Tests that only read existing data are inherently stateless and safe for parallel execution:

```python
def test_user_list_basic(self, cli_runner, cli_helper):
    """Read-only test - fully stateless."""
    result = cli_runner(["user", "list", "--format", "json"])
    # No mutations, no cleanup needed
```

#### Pattern B: Self-Contained CRUD Cycles

Tests that create resources must clean up in the same test using unique identifiers:

```python
def test_notebook_create_and_delete_cycle(self, cli_runner, cli_helper):
    """Self-contained test - stateless across test runs."""
    # Use UUID for unique resource names to avoid conflicts
    notebook_name = f"e2e-test-{uuid.uuid4().hex[:8]}.ipynb"

    try:
        # Create resource
        result = cli_runner(["notebook", "create", "--name", notebook_name])
        notebook_id = extract_id(result)

        # Test operations...

        # Always clean up
        cli_runner(["notebook", "delete", "--id", notebook_id])
    finally:
        # Ensure cleanup even on failure
        cleanup_if_exists(notebook_id)
```

**Key Requirements for Parallel Safety:**

- ✅ Use `uuid.uuid4()` or timestamps for unique resource names
- ✅ Clean up resources in the same test (try/finally or fixtures)
- ✅ Don't assume specific resource counts (use relative assertions)
- ✅ Don't depend on test execution order
- ❌ Avoid shared state between tests
- ❌ Don't rely on resources created by other tests

### 2. Resilience

- Tests handle environment variations gracefully
- Partial failures don't break entire test suite
- Retry logic for transient network issues

### 3. Real-world Scenarios

- Tests simulate actual user workflows
- Both success and error paths validated
- Edge cases and boundary conditions tested

## Fixtures and Utilities

### Core Fixtures

- `e2e_config` - Test configuration
- `cli_runner` - Execute CLI commands
- `cli_helper` - Common test operations
- `temp_workspace` - Isolated test workspace
- `temp_file` - Temporary file management

### Test Data Fixtures

- `sample_notebook_content` - Valid notebook JSON
- `sample_dff_config` - Custom Fields configuration template

### Helper Classes

- `CLITestHelper` - Assert success/failure, parse JSON, find resources

## Troubleshooting

### Common Issues

1. **Authentication Failures**
   - Verify credentials are correct
   - Check if test user account is active
   - Ensure user has required permissions

2. **Network/Connectivity Issues**
   - Verify dev environment URL is accessible
   - Check firewall/VPN requirements
   - Increase timeout values if needed

3. **Permission Errors**
   - Verify test user has workspace access
   - Check API permissions for user role
   - Ensure workspace exists and is accessible

4. **Test Data Conflicts**
   - Enable cleanup to remove test artifacts
   - Use unique names with UUID suffixes
   - Check for leftover data from previous runs

5. **Interactive Pagination Issues**
   - E2E tests automatically disable interactive pagination
   - CLI detects non-interactive environments (pytest, automated testing, piped output)
   - Set `SLCLI_NON_INTERACTIVE=true` to force non-interactive mode
   - Use `--format json` to avoid pagination entirely

6. **Custom Fields Configuration Creation Failures**
   - Custom Fields API requires workspace IDs, not workspace names
   - Use `slcli workspace list --format json` to get workspace IDs
   - Verify all required fields are present in configuration JSON
   - Check that `resourceType` values are valid (use `slcli customfield init --help`)

7. **Custom Fields Export/Import Structure Issues**
   - Export commands return data with `configurations` (plural) key
   - Import commands expect same structure with `configurations` array
   - Single configuration get commands also return `configurations` array
   - Always check for array structure, not single object structure

### Debug Mode

Run tests with additional debugging:

```bash
# Verbose output with full tracebacks
poetry run pytest tests/e2e/ -v --tb=long -s

# Stop on first failure
poetry run pytest tests/e2e/ -x

# Run specific test with debugging
poetry run pytest tests/e2e/test_notebook_e2e.py::TestNotebookE2E::test_notebook_create_and_delete_cycle -v -s
```

### Custom Fields Debugging

For Custom Fields tests, common issues and solutions:

```bash
# Test custom fields configuration creation manually
poetry run slcli customfield create --file /path/to/config.json

# Check workspace ID (custom fields require IDs, not names)
poetry run slcli workspace list --format json | jq '.[] | select(.name=="Default") | .id'

# Verify custom fields export structure
poetry run slcli customfield export --id <config-id> --output /tmp/export.json
cat /tmp/export.json | jq keys  # Should show "configurations", "groups", "fields"

# Test resource type validation
poetry run slcli customfield init --help  # Shows valid resource types
```

## Best Practices

### For Test Authors

1. **Use descriptive test names** that explain the scenario
2. **Include cleanup logic** in finally blocks or fixtures
3. **Test both success and failure cases**
4. **Use unique identifiers** to avoid conflicts
5. **Add appropriate markers** for test categorization
6. **Keep tests independent** - don't rely on other test state

### For Environment Setup

1. **Use dedicated test workspace** to isolate test data
2. **Create service account** for consistent test user
3. **Monitor test data accumulation** and implement cleanup
4. **Rotate test credentials** regularly
5. **Set up monitoring** for test environment health

## Future Enhancements

- **Performance benchmarking** - Track command execution times
- **Parallel test execution** - Speed up test runs
- **Test data seeding** - Pre-populate test environment
- **Cross-environment testing** - Test against multiple dev tiers
- **Integration with test management tools** - Better reporting and tracking
