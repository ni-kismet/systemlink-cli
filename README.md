# SystemLink CLI

SystemLink CLI (`slcli`) is a cross-platform Python CLI for SystemLink integrators, providing comprehensive management of SystemLink resources via REST APIs.

## Features

- **Multi-Platform Support**: Works with both SystemLink Enterprise (SLE) and SystemLink Server (SLS) with automatic platform detection
- **Multi-Profile Support**: Manage multiple SystemLink environments (dev, test, prod) with easy switching between profiles
- **Secure Authentication**: Credential storage in config file with secure permissions, plus legacy keyring support
- **File Management**: Full file lifecycle management (list, upload, download, delete, query) with folder watch feature for automated uploads
- **Function Management**: Complete WebAssembly (WASM) function definition and execution management with metadata-driven organization
- **Test Plan Templates**: Complete management (list, export, import, delete, init) with JSON and table output formats
- **Jupyter Notebooks**: Full lifecycle management (list, download, create, update, delete) with workspace filtering and interface assignment
- **User Management**: Comprehensive user administration (list, get, create, update, delete) with Dynamic LINQ filtering, pagination, and support for service accounts
- **Authorization Management**: Full auth policy and template management (list, get, create, update, delete, diff) with workspace scoping and template-based policy generation
- **Feed Management**: Manage NI Package Manager feeds (list, get, create, delete, package list/upload/delete) with platform-aware behavior for SLE/SLS
- **Workflows**: Full workflow management (list, export, import, delete, init, update) with comprehensive state and action definitions
- **Workspace Management**: Essential workspace administration (list, info, disable) with comprehensive resource details
- **Cross-Platform**: Windows, macOS, and Linux support with standalone binaries
- **Professional CLI**: Consistent error handling, colored output, and comprehensive help system
- **Output Formats**: JSON and table output options for programmatic integration and human-readable display
- **Template Initialization**: Create new template JSON files
- **Local Development Support**: .env file support for configuring service URLs during development
- **Extensible Architecture**: Designed for easy addition of new SystemLink resource types
- **Quality Assurance**: Full test suite with CI/CD, linting, and manual E2E testing

## Installation

### Homebrew (macOS/Linux)

Install SystemLink CLI using [Homebrew](https://brew.sh) from our official tap:

```bash
# Add the NI developer tools tap
brew tap ni-kismet/homebrew-ni

# Install slcli
brew install slcli
```

### Scoop (Windows)

Install SystemLink CLI using [Scoop](https://scoop.sh) from our official bucket:

```bash
# Add the NI developer tools bucket
scoop bucket add ni-kismet https://github.com/ni-kismet/scoop-ni

# Install slcli
scoop install slcli
```

### From Source

For development or if Homebrew isn't available:

1. **Install Poetry** (if not already installed):

   ```bash
   pip install poetry
   ```

2. **Install dependencies:**

   ```bash
   poetry install
   ```

3. **Run the CLI:**

   ```bash
   # Run directly
   poetry run slcli

   # Or as a Python module
   poetry run python -m slcli
   ```

## Shell Completion

Enable tab completion for your shell to improve productivity:

```bash
# Install completion for your current shell (auto-detected)
slcli completion --install

# Or specify shell explicitly
slcli completion --shell bash --install
slcli completion --shell zsh --install
slcli completion --shell fish --install
slcli completion --shell powershell --install
```

After installation, restart your shell or source the completion file. See [docs/shell-completion.md](docs/shell-completion.md) for detailed instructions and troubleshooting.

## Quick Start

1. **Login to SystemLink:**

   ```bash
   # First time setup - creates a 'default' profile
   slcli login

   # Or create named profiles for different environments
   slcli login --profile dev
   slcli login --profile prod
   ```

2. **List available resources:**

   ```bash
   # View test plan templates
   slcli template list

   # View function definitions
   slcli function manage list

   # View function executions
   slcli function execute list

   # View workflows
   slcli workflow list

   # View notebooks
   slcli notebook manage list

   # View users
   slcli user list

   # View workspaces
   slcli workspace list

   # View custom field configurations
   slcli customfield list
   ```

# View auth policies and templates

```bash
slcli auth policy list
slcli auth template list
```

## Example Command (demo systems)

Provision complete demo systems for training and evaluation. Example configurations live under `slcli/examples/` (see [slcli/examples/README.md](slcli/examples/README.md)).

```bash
# Discover available examples
slcli example list

# Inspect an example (resources, tags, setup time)
slcli example info demo-complete-workflow

# Install all resources for an example into a workspace (with audit log)
slcli example install demo-complete-workflow --workspace MyWorkspace --audit-log install-log.json

# Dry-run to validate without creating resources
slcli example install demo-complete-workflow --workspace MyWorkspace --dry-run

# Delete previously installed example resources (with audit log)
slcli example delete demo-complete-workflow --workspace MyWorkspace --audit-log delete-log.json
```

Available samples:

- `demo-complete-workflow`: end-to-end workflow with systems, assets, DUTs, plans, and results
- `demo-test-plans`: focused test-plan setup with reusable assets and templates

3. **Initialize new resources:**

   ```bash
   # Create a new template
   slcli template init --name "My Test Template" --template-group "Production"

   # Create a new workflow
   slcli workflow init --name "My Workflow" --description "Custom workflow"

   # Launch custom fields web editor
   slcli customfield edit
   ```

4. **Get help for any command:**
   ```bash
   slcli --help
   slcli config --help
   slcli template --help
   slcli workflow --help
   slcli notebook --help
   slcli customfield --help
   slcli feed --help
   slcli auth policy --help
   slcli auth template --help
   ```

## Auth Policy Management

Manage authorization policies and policy templates for workspace-based access control.

### Policy Commands

```bash
# List all policies (filter by type/name), table or JSON formats
slcli auth policy list --type custom --format table

# Get policy details
slcli auth policy get <policy-id>

# Create policy from template for a workspace
slcli auth policy create <template-id> \
  --name "my-policy" \
  --workspace <workspace-id>

# Update policy (change name/workspace or reapply template)
slcli auth policy update <policy-id> \
  --name "new-name" \
  --workspace <new-workspace-id>

# Compare two policies
slcli auth policy diff <policy-id-1> <policy-id-2>

# Delete policy
slcli auth policy delete <policy-id> --force
```

### Template Commands

```bash
# List policy templates
slcli auth template list

# Get template details
slcli auth template get <template-id>

# Delete template
slcli auth template delete <template-id>
```

### User Integration

Assign policies to users during create/update. Workspace names or IDs are both supported.

```bash
# Create user with single policy
slcli user create --type user \
  --first-name John --last-name Doe \
  --email john@example.com \
  --policy <policy-id>

# Create user with workspace-scoped policies from templates
# Format: workspaceName:templateId or workspaceId:templateId
slcli user create --type user \
  --first-name Jane --last-name Doe \
  --email jane@example.com \
  --workspace-policies "DevWorkspace:template-dev,ProdWorkspace:template-prod"
```

## Feed Management

Manage NI Package Manager feeds for both SystemLink Enterprise (SLE) and SystemLink Server (SLS). Platform detection is automatic, and platform values are case-insensitive.

### Common Commands (SLE example)

```bash
# List feeds
slcli feed list --format table

# Create a feed (wait for completion)
slcli feed create --name my-feed --platform windows --workspace Default

# Show feed details
slcli feed get --id <feed-id> --format json

# List packages in a feed
slcli feed package list --feed-id <feed-id> --format json

# Upload a package and wait for completion
slcli feed package upload --feed-id <feed-id> --file mypkg.nipkg --wait

# Delete a feed and its packages
slcli feed delete --id <feed-id> --yes
```

### SLS-Specific Notes

- Feed and package endpoints use `/nirepo/v1` instead of `/nifeed/v1`.
- Package uploads use the shared package pool before being associated with a feed.
- **Note:** On SLS, package upload commands will block for the initial upload phase even without the `--wait` flag, as the package must be uploaded to the shared pool before being associated with the feed. The `--wait` flag controls waiting for the final association step. On SLE, the upload command returns immediately unless `--wait` is specified.

### Pagination & Formats

- All list commands support `--format` (`table` default, `json`) and `--take` (default 25) for pagination.
- JSON outputs return full results without pagination.

## Authentication

Before using SystemLink CLI commands, you need to authenticate with your SystemLink server.

### Login to SystemLink

```bash
# Interactive login (prompts for profile name, URL, and API key)
slcli login

# Login with a named profile
slcli login --profile dev
slcli login --profile prod --url "https://prod-api.example.com"

# Non-interactive login with all flags
slcli login --profile myprofile --url "https://your-server.com" --api-key "your-api-key" --web-url "https://your-server-web.com"

# Set a default workspace for a profile
slcli login --profile dev --workspace "Development"

# Enable readonly mode (disables all delete/edit commands for safety with AI agents)
slcli login --profile aiagent --readonly
slcli login --profile aiagent --url "https://your-server.com" --api-key "your-api-key" --readonly
```

**Note**: The CLI automatically converts HTTP URLs to HTTPS for security. SystemLink servers typically require HTTPS for API access.

**Readonly Mode**: Use the `--readonly` flag to enable read-only mode on a profile. This disables all mutation operations (create, update, delete, and edit commands), making it safer to use with AI agents or in untrusted environments.

**Alias**: The `slcli login` command is an alias for `slcli config add-profile`. Both commands provide the same functionality.

#### Readonly Mode Protected Operations

When a profile is in readonly mode, the following operations are blocked:

- **Create commands**: Create feeds, tags, workflows, templates, policies, users, notebooks, functions, DataFlow Definitions, webapps
- **Update/Edit commands**: Update profiles, configurations, workflows, notebooks, functions, policies, tags, users, DataFlow Definitions
- **Delete commands**: Delete profiles, feeds, files, webapps, policies, tags, workflows, DataFlow Definitions
- **Other mutations**: Import templates, import workflows, publish webapps, upload packages, disable workspaces

When attempting a protected operation with a readonly profile, the CLI exits with error code 4 (PERMISSION_DENIED) and displays:

```
✗ Cannot <operation>: profile is in readonly mode
Readonly mode disables all mutation operations (create, update, delete, edit) for safety.
```

This makes readonly mode ideal for:

- AI agent safety: Prevent accidental data modification
- Read-only reports: Generate analyses without changing data
- Automated monitoring: Query systems without mutation risk
- Demo/training environments: Allow exploration without modification

### Logout (remove stored credentials)

```bash
# Remove current profile
slcli logout

# Remove a specific profile
slcli logout --profile dev

# Remove all profiles
slcli logout --all --force
```

### Multi-Profile Management

Manage multiple SystemLink environments (development, testing, production) using profiles:

```bash
# List all configured profiles
slcli config list-profiles

# Show current profile
slcli config current-profile

# Add or update a profile (same as slcli login)
slcli config add-profile --profile dev
slcli config add-profile --profile secure --readonly

# Switch to a different profile
slcli config use-profile prod

# View full configuration (with masked API keys)
slcli config view

# Delete a profile
slcli config delete-profile old-profile --force
```

### Using Profiles with Commands

```bash
# Use a specific profile for a single command
slcli --profile prod workspace list
slcli -p dev template list

# Set profile via environment variable
export SLCLI_PROFILE=prod
slcli workspace list  # Uses 'prod' profile
```

### Configuration File

Profiles are stored in `~/.config/slcli/config.json` with secure file permissions (600). You can also:

```bash
# Set custom config location
export SLCLI_CONFIG=/path/to/config.json

# Migrate from legacy keyring storage
slcli config migrate
```

### Environment Variable Overrides

Environment variables take precedence over profile settings:

| Variable             | Description                               |
| -------------------- | ----------------------------------------- |
| `SLCLI_PROFILE`      | Profile to use (default: current profile) |
| `SLCLI_CONFIG`       | Custom config file path                   |
| `SYSTEMLINK_API_URL` | Override API URL                          |
| `SYSTEMLINK_API_KEY` | Override API key                          |
| `SYSTEMLINK_WEB_URL` | Override web UI URL                       |

## Platform Support

SystemLink CLI supports both **SystemLink Enterprise (SLE)** and **SystemLink Server (SLS)**:

| Platform | Notebook Execution | Custom Fields/Templates/Workflows |
| -------- | ------------------ | --------------------------------- |
| **SLE**  | ✓ Full support     | ✓ Full support                    |
| **SLS**  | ✓ Path-based API   | ✗ Not available                   |

### Platform Detection

The CLI automatically detects your platform during `slcli login` by probing endpoints. You can also:

```bash
# View current platform and feature availability
slcli info

# JSON output for scripting
slcli info --format json
```

### Platform-Specific Notes

- **Notebook Execution on SLS**: Uses notebook path (e.g., `_shared/reports/notebook.ipynb`) instead of notebook ID
- **Feature Gating**: Commands for custom fields, templates, workflows, and functions show clear error messages when run on SLS
- **Environment Override**: Set `SYSTEMLINK_PLATFORM=SLE` or `SYSTEMLINK_PLATFORM=SLS` to explicitly specify the platform

## Test Plan Template Management

The `template` command group allows you to manage test plan templates in SystemLink.

### Create a template JSON scaffold

Create a new test plan template JSON file with the complete schema structure:

```bash
# Interactive mode (prompts for required fields)
slcli template init

# Specify required fields directly
slcli template init --name "Battery Test Template" --template-group "Production Tests"

# Custom output file
slcli template init --name "My Template" --template-group "Development" --output custom-template.json
```

The `init` command creates a JSON file with:

- Required fields: `name` and `templateGroup`
- Optional fields: `productFamilies`, `partNumbers`, `summary`, `description`, etc.
- Complete `executionActions` examples (JOB, NOTEBOOK, MANUAL actions)
- Property placeholders for customization

### List test plan templates

```bash
# Table format (default)
slcli template list

# JSON format for programmatic use
slcli template list --format json

# Filter by workspace
slcli template list --workspace "Production Workspace"

# Filter by name/group/description (case-insensitive substring)
slcli template list --filter "battery"
```

### Get or export a template

```bash
# Show details (table)
slcli template get --id <template_id>
slcli template get --name "My Template"

# JSON details
slcli template get --name "My Template" --format json

# Export to JSON file (supports --id or --name)
slcli template export --id <template_id> --output template.json
slcli template export --name "My Template" --output template.json
```

### Import a template from JSON

```bash
slcli template import --file template.json
```

The import command provides detailed error reporting for partial failures, including specific error types like `WorkspaceNotFoundOrNoAccess`.

### Delete a template

```bash
slcli template delete --id <template_id>
```

## Workflow Management

The `workflow` command group allows you to manage workflows in SystemLink. All workflow commands use the beta feature flag automatically.

### Create a workflow JSON skeleton

Create a new workflow JSON file with a complete state machine structure:

```bash
# Interactive mode (prompts for required fields)
slcli workflow init

# Specify fields directly
slcli workflow init --name "Battery Test Workflow" --description "Workflow for battery testing procedures"

# Custom output file
slcli workflow init --name "My Workflow" --description "Custom workflow" --output custom-workflow.json
```

The `init` command creates a JSON file with:

- Basic workflow metadata: `name` and `description`
- Complete workflow `definition` with states, substates, and actions
- Example state transitions (Created → InProgress → Completed)
- Sample actions (Start, Pause, Resume, Complete, Fail, Abort)

### List workflows

```bash
# Table format (default)
slcli workflow list

# JSON format for programmatic use
slcli workflow list --format json

# Filter by workspace
slcli workflow list --workspace "Production Workspace"
```

### Get or export a workflow

```bash
# Show details (table)
slcli workflow get --id <workflow_id>
slcli workflow get --name "Battery Test Workflow"

# JSON details
slcli workflow get --name "Battery Test Workflow" --format json

# Export to JSON file (supports --id or --name)
slcli workflow export --id <workflow_id> --output workflow.json
slcli workflow export --name "Battery Test Workflow" --output workflow.json
```

### Import a workflow from JSON

```bash
slcli workflow import --file workflow.json
```

### Update an existing workflow

```bash
slcli workflow update --id <workflow_id> --file updated-workflow.json
```

### Delete a workflow

```bash
slcli workflow delete --id <workflow_id>
```

### Preview a workflow (Mermaid diagram)

Generate a visual state diagram (Mermaid) for an existing workflow or a local JSON definition:

```bash
# Preview remote workflow in browser (HTML)
slcli workflow preview --id <workflow_id>

# Save raw Mermaid source (.mmd) for a remote workflow
slcli workflow preview --id <workflow_id> --format mmd --output workflow.mmd

# Preview a local JSON file
slcli workflow preview --file my-workflow.json

# Read workflow JSON from stdin
cat my-workflow.json | slcli workflow preview --file - --format mmd --output wf.mmd

# Disable emoji and legend (clean export)
slcli workflow preview --id <workflow_id> --no-emoji --no-legend --format html --output wf.html

# Generate HTML without opening a browser
slcli workflow preview --id <workflow_id> --no-open --output wf.html
```

Options:

- `--id / --file` (mutually exclusive): Choose remote workflow or local JSON (use `-` for stdin)
- `--format`: `html` (default) or `mmd`
- `--output/-o`: Write to file; otherwise HTML opens in browser
- `--no-emoji`: Remove emoji from action labels
- `--no-legend`: Suppress legend block in HTML output
- `--no-open`: Do not open browser when producing HTML without `--output`

Legend (HTML only) explains: action type emojis, privilege sets, truncated notebook IDs, icon class (⚡️), and hidden actions.

## Function Management

The `function` command group provides comprehensive management of WebAssembly (WASM) function definitions and executions in SystemLink. Functions are compiled WebAssembly modules that can be executed remotely with parameters.

**Architecture Overview (Unified v2):**

- **Unified Function Management Service** (`/nifunction/v2`): Single API surface for definitions, metadata, WASM content, and synchronous execution
- **Interface Property**: Indexed JSON (legacy simple entrypoint or HTTP-style `endpoints` with `methods`, `path`, and `description`)
- **Workspace Integration**: Functions belong to SystemLink workspaces with metadata and execution statistics
- **Synchronous HTTP-style Execution**: POST `/functions/{id}/execute` with parameters `{ method, path, headers, body }`

The CLI provides two main command groups:

- `slcli function manage` - Function definition management (create, update, delete, query)
- `slcli function execute` - Function execution management (synchronous execution, list, get, cancel, retry)

### Function Definition Management (`function manage`)

#### List function definitions

```bash
# List all function definitions (table format - default)
slcli function manage list

# Filter by workspace
slcli function manage list --workspace MyWorkspace

# Filter by name pattern (starts with)
slcli function manage list --name "data_"

# Filter by interface content (searches interface property for text)
slcli function manage list --interface-contains "entrypoint"

# Advanced Dynamic LINQ filtering
slcli function manage list --filter 'name.StartsWith("data") && interface.Contains("entrypoint")'

# JSON format for programmatic use
slcli function manage list --format json

# Control pagination
slcli function manage list --take 50
```

#### Get function definition details

```bash
# Get detailed information about a function
slcli function manage get --id <function_id>

# JSON format
slcli function manage get --id <function_id> --format json
```

#### Create a new function definition

```bash
# Simple example using the provided sample WASM file
slcli function manage create \
    --name "Sample Math Calculator - add" \
    --runtime wasm \
    --content ./samples/math.wasm \
    --entrypoint add \
    --workspace "Default" \
    --description "Simple mathematical operations using WebAssembly"

# Create a basic WASM function with interface definition
slcli function manage create \
    --name "Data Processing Function" \
    --runtime wasm \
    --workspace MyWorkspace \
    --description "Processes sensor data and calculates statistics" \
    --version "1.0.0" \
    --entrypoint "main"

# Create with WASM binary from file and schema definitions
slcli function manage create \
    --name "Signal Analyzer" \
    --runtime wasm \
    --content ./signal_analyzer.wasm \
    --workspace "Production Workspace" \
    --description "Analyzes signal patterns and detects anomalies" \
    --entrypoint "analyze_signal" \
    --parameters-schema '{"type": "object", "properties": {"samples": {"type": "array", "items": {"type": "number"}}, "threshold": {"type": "number"}}, "required": ["samples"]}' \
    --returns-schema '{"type": "object", "properties": {"anomalies": {"type": "array"}, "confidence": {"type": "number"}}}'

# Create with custom properties for organization and filtering
slcli function manage create \
    --name "Customer Analytics Engine" \
    --runtime wasm \
    --content ./analytics.wasm \
    --workspace "Analytics Workspace" \
    --description "Customer behavior analysis and prediction" \
    --version "2.1.0" \
    --entrypoint "process_customer_data" \
    --properties '{"category": "analytics", "team": "data-science", "deployment": "production", "compliance": "gdpr"}' \
    --parameters-schema '{"type": "object", "properties": {"customer_id": {"type": "string"}, "timeframe": {"type": "string"}, "metrics": {"type": "array", "items": {"type": "string"}}}, "required": ["customer_id"]}' \
    --returns-schema '{"type": "object", "properties": {"predictions": {"type": "object"}, "confidence_score": {"type": "number"}, "recommendation": {"type": "string"}}}'

# Create with inline interface content (demonstrates interface property structure)
slcli function manage create \
    --name "Mathematical Calculator" \
    --runtime wasm \
    --workspace "Default" \
    --description "High-performance mathematical operations library" \
    --version "1.0.0" \
    --entrypoint "calculate" \
    --parameters-schema '{"type": "object", "properties": {"operation": {"type": "string", "enum": ["add", "subtract", "multiply", "divide"]}, "operands": {"type": "array", "items": {"type": "number"}, "minItems": 2}}, "required": ["operation", "operands"]}' \
    --properties '{"category": "utilities", "team": "platform", "tags": "math,calculator,utility"}'
```

##### Example: Creating a Function with the Sample WASM File

This repository includes a sample WebAssembly function (`samples/math.wasm`) that demonstrates basic mathematical operations. Here's how to create a function using this sample:

````bash
# Create a function using the provided sample WASM file
slcli function manage create \
    --name "Sample Math Functions - fred 1" \
    --runtime wasm \
    --content ./samples/math.wasm \
    --workspace "Default" \
    --description "Sample WebAssembly function with add, multiply_and_add, and execute operations" \
    --version "1.0.0" \
    --entrypoint "execute" \
    --properties '{"category": "samples", "team": "development", "tags": "demo,math,sample", "runtime_type": "wasm"}' \
    --parameters-schema '{"type": "object", "properties": {"a": {"type": "integer", "description": "First operand"}, "b": {"type": "integer", "description": "Second operand"}, "c": {"type": "integer", "description": "Third operand (optional)"}}, "required": ["a", "b"]}' \
    --returns-schema '{"type": "integer", "description": "Computed result"}'

# The math.wasm file exports these functions:
# - add(a, b): Returns a + b
# - multiply_and_add(a, b, c): Returns (a * b) + c
# - execute(): Returns 42 (main entry point)

# After creation, you can execute the function synchronously (HTTP-style parameters):
slcli function execute sync \
    --function-id <function_id_from_above> \
    --method POST \
    --path /invoke \
    -H content-type=application/json \
    --body '{"a":10,"b":5,"c":3}' \
    --timeout 300 --format json

### Initialize a Local Function Template (`function init`)

Bootstrap a local template for building a function from official examples.

```bash
# Prompt for language
slcli function init

# TypeScript (Hono) template into a new folder
slcli function init --language typescript --directory my-ts-func

# Python HTTP template
slcli function init -l python -d my-py-func

# Overwrite non-empty directory
slcli function init -l ts -d existing --force
````

Templates are fetched on-demand from branch `function-examples` of `ni/systemlink-enterprise-examples`:

- TypeScript: `function-examples/typescript-hono-function`
- Python: `function-examples/python-http-function`

Next steps (printed only):

1. Install dependencies / create venv
2. Build (TypeScript: `npm run build` → `dist/main.wasm`)
3. Register with `slcli function manage create --content dist/main.wasm --entrypoint main` (adjust name/workspace)

To supply HTTP-style execution parameters later:

```bash
slcli function execute sync --function-id <id> --method GET --path /
```

#### Enhanced Filtering and Querying

Use interface-based filtering and custom properties for efficient function management based on the function's interface definition:

```bash
# Filter by interface content (searches within the indexed interface property)
slcli function manage list --interface-contains "entrypoint"

# Search for functions with specific entrypoints
slcli function manage list --interface-contains "process_data"

# Advanced Dynamic LINQ filtering using interface properties
slcli function manage list --filter 'interface.entrypoint != null && interface.entrypoint != "" && runtime = "wasm"'

# Filter by custom properties for organizational management
slcli function manage list --filter 'properties.category == "analytics" && properties.deployment == "production"'

# Search for functions by team and performance characteristics
slcli function manage list --filter 'properties.team == "data-science" && properties.accuracy > 0.9'

# Find functions suitable for specific environments
slcli function manage list --filter 'properties.deployment == "production" && properties.compliance == "gdpr"'

# Search within interface content for specific parameter types
slcli function func list --filter 'interface.Contains("customer_id") && interface.Contains("timeframe")'

# Complex filtering combining multiple criteria
slcli function func list \
    --workspace "Analytics Workspace" \
    --name "Customer" \
    --filter 'properties.category == "analytics" && interface.entrypoint != null'

# Find functions with specific runtime and interface characteristics
slcli function func list --filter 'runtime = "wasm" && interface.Contains("parameters") && !string.IsNullOrEmpty(properties.team)'
```

#### Update a function definition

```bash
# Update function metadata
slcli function func update \
    --id <function_id> \
    --name "Updated Function Name" \
    --description "Updated description" \
    --version "1.1.0"

# Update function WASM binary
slcli function func update \
    --id <function_id> \
    --content ./updated_function.wasm

# Update WebAssembly binary
slcli function func update \
    --id <function_id> \
    --content ./updated_math_functions.wasm

# Update parameters schema
slcli function func update \
    --id <function_id> \
    --parameters-schema ./new_params_schema.json

# Update metadata and properties
slcli function func update \
    --id <function_id> \
    --properties '{"deployment": "production", "team": "platform-team", "critical": true}'

# Update workspace and runtime
slcli function func update \
    --id <function_id> \
    --workspace "Production Workspace" \
    --runtime wasm

# Update with custom properties (replaces existing properties)
slcli function func update \
    --id <function_id> \
    --properties '{"deployment": "production", "version": "2.0", "critical": true}'
```

#### Delete a function definition

```bash
# Delete with confirmation prompt
slcli function func delete --id <function_id>

# Delete without confirmation
slcli function func delete --id <function_id> --force
```

#### Complete Workflow Example

Here's a complete example showing how to use the interface-based function system for efficient metadata management:

```bash
# 1. Create a customer analytics function with comprehensive interface definition
slcli function func create \
    --name "Customer Analytics Engine" \
    --runtime wasm \
    --content ./customer_analytics.wasm \
    --workspace "Analytics Workspace" \
    --description "Customer behavior analysis and prediction engine" \
    --version "2.1.0" \
    --entrypoint "analyze_customer_behavior" \
    --properties '{"category": "analytics", "team": "data-science", "deployment": "production", "compliance": "gdpr", "sla": "4h"}' \
    --parameters-schema '{"type": "object", "properties": {"customer_id": {"type": "string"}, "timeframe": {"type": "string", "enum": ["7d", "30d", "90d"]}, "metrics": {"type": "array", "items": {"type": "string"}}}, "required": ["customer_id", "timeframe"]}' \
    --returns-schema '{"type": "object", "properties": {"predictions": {"type": "object"}, "confidence_score": {"type": "number", "minimum": 0, "maximum": 1}, "recommendations": {"type": "array"}}}'

# 2. Create a complementary reporting function for the same team
slcli function func create \
    --name "Customer Report Generator" \
    --runtime wasm \
    --content ./report_generator.wasm \
    --workspace "Analytics Workspace" \
    --description "Generates formatted customer analysis reports" \
    --version "1.0.0" \
    --entrypoint "generate_report" \
    --properties '{"category": "reporting", "team": "data-science", "deployment": "production", "output_format": "pdf"}' \
    --parameters-schema '{"type": "object", "properties": {"analysis_id": {"type": "string"}, "format": {"type": "string", "enum": ["pdf", "html", "json"]}, "include_charts": {"type": "boolean"}}, "required": ["analysis_id"]}' \
    --returns-schema '{"type": "object", "properties": {"report_url": {"type": "string"}, "size_bytes": {"type": "integer"}, "generated_at": {"type": "string", "format": "date-time"}}}'

# 3. Query functions by team and deployment status using interface-based filtering
slcli function func list --filter 'properties.team == "data-science" && properties.deployment == "production"'

# 4. Find functions with specific interface characteristics (customer-related functions)
slcli function func list --filter 'interface.Contains("customer_id") && runtime == "wasm"'

# 5. Search for functions with specific entrypoints
slcli function func list --interface-contains "analyze_customer"

# 6. Execute the analytics function with real parameters
slcli function execute \
    --function-id b7cc0156-931c-472f-a027-d88dc51cb936 \
    --workspace "Analytics Workspace" \
    --parameters '{"functionName": "analyze_customer_behavior", "args": ["CUST-2025-001", "30d", ["engagement", "conversion", "retention"]]}' \
    --timeout 600 \
    --client-request-id "customer-analysis-$(date +%s)"

# 7. Create an asynchronous batch job for multiple customers
slcli function create \
    --function-id b7cc0156-931c-472f-a027-d88dc51cb936 \
    --workspace "Analytics Workspace" \
    --parameters '{"functionName": "batch_analyze", "args": ["BATCH-2025-001", "90d", ["lifetime_value", "churn_risk"]]}' \
    --timeout 3600 \
    --result-cache-period 86400 \
    --client-request-id "batch-analytics-20250805"

# 8. Update function properties when promoting through environments
slcli function func update \
    --id b7cc0156-931c-472f-a027-d88dc51cb936 \
    --properties '{"category": "analytics", "team": "data-science", "deployment": "production", "compliance": "gdpr", "sla": "4h", "monitoring": true, "alerts": "enabled"}'

# 9. Query production functions with monitoring and compliance requirements
slcli function func list --filter 'properties.deployment == "production" && properties.monitoring == true && properties.compliance == "gdpr"'

# 10. Find functions with specific interface capabilities for API documentation
slcli function func list --filter 'interface.Contains("timeframe") && interface.Contains("customer_id") && properties.category == "analytics"'
```

This metadata system enables you to:

- **Organize** functions by category, team, and purpose using custom properties
- **Filter efficiently** using interface-based queries and property filters
- **Track** deployment status and operational metadata
- **Search** using flexible custom properties and interface content
- **Manage** functions across multiple teams and environments

#### Download function source code

```bash
# Download function content with automatic file extension detection
slcli function func download-content --id <function_id>

# Download function content to a specific file
slcli function func download-content --id <function_id> --output my_function.wasm

# Download WebAssembly binary
slcli function func download-content --id <function_id> --output math_functions.wasm
```

_Note: Functions are WebAssembly modules and will be downloaded with the .wasm extension._

### Function Execution Management

Execution now uses an HTTP-style invocation parameters object. The `parameters` field sent to
the execute endpoint has this structure:

```json
{
  "method": "POST", // optional (default POST)
  "path": "/invoke", // optional (default /invoke)
  "headers": {
    // optional headers map
    "content-type": "application/json"
  },
  "body": {
    // JSON object or raw string; if omitted, empty body
    "a": 1,
    "b": 2
  }
}
```

CLI convenience flags build this object automatically:

- `--method` (default POST)
- `--path` (default /invoke)
- `-H/--header key=value` (repeatable)
- `--body` (JSON string, JSON file path, or raw text)
- `--parameters` (raw JSON overrides the above flags). If the provided JSON does **not** contain
  any of `method`, `path`, `headers`, or `body`, the value is wrapped automatically as `{ "body": <value> }` for backward compatibility.

#### JavaScript Fetch Example (Equivalent to CLI)

```javascript
// Synchronous execution (default method POST to /invoke)
await fetch(`/nifunction/v2/functions/${functionId}/execute`, {
  method: "POST",
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify({
    parameters: {
      method: "POST", // optional
      path: "/invoke", // optional
      headers: { "content-type": "application/json" },
      body: { a: 1, b: 2 },
    },
    timeout: 30,
    async: false,
  }),
});
```

#### CLI Equivalent

```bash
slcli function execute sync \
    --function-id <function_id> \
    --method POST \
    --path /invoke \
    -H content-type=application/json \
    --body '{"a":1,"b":2}' \
    --timeout 30 --format json
```

Or with a raw parameters JSON object:

```bash
slcli function execute sync \
    --function-id <function_id> \
    --parameters '{"method":"POST","path":"/invoke","headers":{"content-type":"application/json"},"body":{"a":1,"b":2}}' \
    --timeout 30 --format json
```

Backward compatibility: passing `--parameters '{"a":1,"b":2}'` will be interpreted as body payload.

#### List function executions

```bash
# List all function executions (table format - default)
slcli function list

# Filter by workspace
slcli function list --workspace MyWorkspace

# Filter by status
slcli function list --status SUCCEEDED

# Filter by function ID
slcli function list --function-id <function_id>

# JSON format for programmatic use
slcli function list --format json

# Control pagination
slcli function list --take 50
```

#### Get execution details

```bash
# Get detailed information about an execution
slcli function get --id <execution_id>

# JSON format
slcli function get --id <execution_id> --format json
```

#### Execute a function synchronously

```bash
# Execute a function and wait for the result (basic usage)
# Note: For WASM functions, use functionName + args structure
slcli function execute sync \
    --function-id b7cc0156-931c-472f-a027-d88dc51cb936 \
    --method POST \
    --path /invoke \
    -H content-type=application/json \
    --body '{"samples":[1.0,2.5,3.2,1.8],"threshold":2.0}'

# Execute with parameters from file
# Note: Parameter files should contain the new WASM structure:
# {
#   "functionName": "add",
#   "args": [10, 5]
# }
slcli function execute sync \
    --function-id b7cc0156-931c-472f-a027-d88dc51cb936 \
    --parameters ./execution_params.json \
    --timeout 300

# Execute with comprehensive configuration (matches ExecuteFunctionRequest schema)
slcli function execute sync \
    --function-id b7cc0156-931c-472f-a027-d88dc51cb936 \
    --parameters '{"method":"POST","path":"/invoke","body":{"customerId":"CUST-12345","timeframe":"30d","metrics":["engagement","conversion"]}}' \
    --timeout 1800 \
    --client-request-id "analytics-req-20250805-001"

# JSON format for programmatic integration (returns ExecuteFunctionResponse)
slcli function execute sync \
    --function-id b7cc0156-931c-472f-a027-d88dc51cb936 \
    --parameters '{"method":"POST","path":"/invoke","body":{"op":"multiply","a":4,"b":7}}' \
    --format json

# Execute mathematical function with comprehensive tracking
slcli function execute sync \
    --function-id b7cc0156-931c-472f-a027-d88dc51cb936 \
    --parameters '{"method":"POST","path":"/invoke","body":{"op":"add","a":15,"b":25}}' \
    --timeout 300 \
    --client-request-id "math-calc-$(date +%s)" \
    --format json
```

#### (Removed) Asynchronous execution

Asynchronous execution support has been removed from the CLI. All executions use the synchronous
endpoint; for background workloads, orchestrate via external tooling that schedules synchronous
invocations.

#### Cancel function executions

```bash
# Cancel a single execution
slcli function cancel --id 6d958d07-2d85-4655-90ba-8ff84a0482aa

# Cancel multiple executions (bulk operation)
slcli function cancel \
    --id 6d958d07-2d85-4655-90ba-8ff84a0482aa \
    --id a1b28c37-2d85-4655-90ba-8ff84a0482bb \
    --id f3e45a12-2d85-4655-90ba-8ff84a0482cc

# Cancel executions for cleanup (multiple IDs from execution list)
slcli function cancel \
    --id 6d958d07-2d85-4655-90ba-8ff84a0482aa \
    --id a1b28c37-2d85-4655-90ba-8ff84a0482bb
```

#### Retry failed executions

```bash
# Retry a single failed execution (creates new execution with same parameters)
slcli function retry --id 6d958d07-2d85-4655-90ba-8ff84a0482aa

# Retry multiple failed executions (bulk retry operation)
slcli function retry \
    --id 6d958d07-2d85-4655-90ba-8ff84a0482aa \
    --id a1b28c37-2d85-4655-90ba-8ff84a0482bb

# Retry executions after fixing system issues
slcli function retry \
    --id 6d958d07-2d85-4655-90ba-8ff84a0482aa \
    --id a1b28c37-2d85-4655-90ba-8ff84a0482bb \
    --id f3e45a12-2d85-4655-90ba-8ff84a0482cc
```

### Configuration

#### Using .env file for local development

Create a `.env` file in your working directory to configure service URLs for local development:

```bash
# Function Service URL (for function definition management)
FUNCTION_SERVICE_URL=http://localhost:3000

# Function Execution Service URL (for function execution management)
FUNCTION_EXECUTION_SERVICE_URL=http://localhost:3001

# Common API settings
SYSTEMLINK_API_KEY=your_api_key_here
SLCLI_SSL_VERIFY=false
```

The CLI will automatically load these environment variables from the `.env` file when running commands. You can also set these as regular environment variables in your shell if preferred.

### TLS / System Certificate Trust

`slcli` uses the operating system certificate store by default on supported platforms via the
`truststore` library. Corporate or custom root CAs trusted by Windows (CryptoAPI), macOS
(Keychain), or Linux (distro CA bundle) are automatically honored—no manual `certifi` edits.

Environment controls:

| Variable                   | Effect                                              |
| -------------------------- | --------------------------------------------------- |
| `SLCLI_DISABLE_OS_TRUST=1` | Skip system trust injection (fall back to certifi)  |
| `SLCLI_FORCE_OS_TRUST=1`   | Fail fast if injection fails (abort startup)        |
| `SLCLI_DEBUG_OS_TRUST=1`   | Print traceback on injection failure                |
| `SLCLI_SSL_VERIFY=false`   | Disable TLS verification entirely (NOT recommended) |

Custom CA bundle: set `REQUESTS_CA_BUNDLE` or `SSL_CERT_FILE` to a PEM file. If both a custom
bundle and system injection are present the explicit bundle path wins.

Disable system trust but keep verification:

```bash
SLCLI_DISABLE_OS_TRUST=1 slcli template list
```

Completely disable TLS verification (only for debugging):

```bash
SLCLI_SSL_VERIFY=false slcli template list
```

For strict environments where system trust injection is mandatory:

```bash
SLCLI_FORCE_OS_TRUST=1 slcli template list
```

#### Runtime Certificate Diagnostics (`_ca-info`)

A hidden diagnostic command is available to inspect which certificate authority (CA) source
`slcli` is using at runtime and why:

```bash
slcli _ca-info
```

Typical output fields:

- `CA Source`: One of `system`, `custom-pem`, or `certifi` describing the active trust source
- `System Trust Injected`: `true/false` indicating whether OS trust was successfully injected
- `Reason`: Short explanation for the current state (e.g. custom bundle override, injection disabled)
- `Custom Bundle Path`: Present only when a custom PEM bundle (`REQUESTS_CA_BUNDLE` / `SSL_CERT_FILE`) overrides system trust

Example (system trust active):

```
CA Source: system
System Trust Injected: true
Reason: injected system trust via truststore
```

Example (custom bundle overrides system trust):

```
CA Source: custom-pem
System Trust Injected: false
Reason: custom CA bundle overrides system trust injection
Custom Bundle Path: /etc/ssl/my-corp-root.pem
```

Example (fallback to certifi because injection disabled):

```
CA Source: certifi
System Trust Injected: false
Reason: SLCLI_DISABLE_OS_TRUST set
```

Use this command when troubleshooting TLS failures, validating that corporate roots are in use,
or confirming environment variable effects. It produces no network traffic and is safe to run
any time.

## Test Monitor Management

The `testmonitor` command group provides access to Test Monitor products and test results.

### List products

```bash
# List products (table with pagination)
slcli testmonitor product list

# Filter by product fields (contains match)
slcli testmonitor product list --name "cRIO" --family "cRIO"

# Filter by workspace
slcli testmonitor product list --workspace MyWorkspace

# Dynamic LINQ filter with substitutions
slcli testmonitor product list \
  --filter '(family == @0) && (name.Contains(@1))' \
  --substitution "cRIO" \
  --substitution "9030"

# JSON output (no interactive pagination)
slcli testmonitor product list --format json
```

### List test results

```bash
# List test results (table with pagination)
slcli testmonitor result list

# Filter by status and program name
slcli testmonitor result list --status passed --program-name "Calibration"

# Filter by part number and serial number
slcli testmonitor result list --part-number "cRIO-9030" --serial-number "abc-123"

# Filter by workspace
slcli testmonitor result list --workspace MyWorkspace

# Advanced result and product filters with substitutions
slcli testmonitor result list \
  --filter '(operator == @0) && (totalTimeInSeconds < @1)' \
  --substitution "user1" \
  --substitution 30 \
  --product-filter '(family == @0)' \
  --product-substitution "cRIO"

# JSON output (no interactive pagination)
slcli testmonitor result list --format json
```

## Notebook Management

The `notebook` command group is organized into logical subgroups to mirror function command structure:

- `slcli notebook init` – scaffold a local notebook file.
- `slcli notebook manage <subcommand>` – list, create, update, download, delete remote notebooks, and assign interfaces.
- `slcli notebook execute list` – list notebook execution records (supports --workspace, --notebook-id, --status, --take, --format json|table).

Legacy top-level aliases (e.g. `slcli notebook list`) have been removed; always use the `manage` subgroup for server operations.

### Initialize a local notebook

```bash
# Create a new local notebook file
slcli notebook init --name MyLocalNotebook.ipynb
```

### List notebooks in a workspace

# List notebook executions

```bash
# List recent executions (table with pagination)
slcli notebook execute list

# Filter by workspace
slcli notebook execute list --workspace MyWorkspace

# Filter by notebook ID
slcli notebook execute list --notebook-id 123e4567-e89b-12d3-a456-426614174000

# Filter by status (case-insensitive input mapped to service tokens)
slcli notebook execute list --status timed_out
slcli notebook execute list --status in_progress

# JSON output (no interactive pagination)
slcli notebook execute list --format json --take 100
```

Valid statuses for --status: in_progress, queued, failed, succeeded, canceled, timed_out.

```bash
# List notebooks (table format - default)
slcli notebook manage list

# List notebooks in a specific workspace
slcli notebook manage list --workspace MyWorkspace

# JSON format for programmatic use
slcli notebook manage list --format json

# Control pagination (table output only)
slcli notebook manage list --take 50

# Filter by name/interface (case-insensitive substring)
slcli notebook manage list --filter "Report"
```

### Download notebook content/metadata

```bash
# Download notebook content (.ipynb) by ID
slcli notebook manage download --id <notebook_id> --output mynotebook.ipynb

# Download notebook content by name
slcli notebook manage download --name MyNotebook --output mynotebook.ipynb

# Download notebook metadata as JSON
slcli notebook manage download --id <notebook_id> --type metadata --output metadata.json

# Download both content and metadata
slcli notebook manage download --id <notebook_id> --type both --output mynotebook.ipynb
```

### Create a notebook

```bash
# Create from existing .ipynb file
slcli notebook manage create --file mynotebook.ipynb --name MyNotebook
slcli notebook manage create --file mynotebook.ipynb --workspace MyWorkspace --name MyNotebook

# Create an empty notebook
slcli notebook manage create --name MyNotebook
slcli notebook manage create --workspace MyWorkspace --name MyNotebook
```

### Update notebook metadata and/or content

```bash
# Update metadata only
slcli notebook manage update --id <notebook_id> --metadata metadata.json

# Update content only
slcli notebook manage update --id <notebook_id> --content mynotebook.ipynb

# Update both metadata and content
slcli notebook manage update --id <notebook_id> --metadata metadata.json --content mynotebook.ipynb

# Update interface only
slcli notebook manage update --id <notebook_id> --interface "File Analysis"
```

### Assign an interface to a notebook

Each notebook can be assigned one of the predefined interfaces to indicate where it should appear in SystemLink UI.

```bash
# Set interface
slcli notebook manage set-interface --id <notebook_id> --interface "File Analysis"

# Create notebook with interface
slcli notebook manage create --name MyNotebook --interface "Data Table Analysis"
```

#### Available Interfaces

- Assets Grid
- Data Table Analysis
- Data Space Analysis
- File Analysis
- Periodic Execution
- Resource Changed Routine
- Specification Analysis
- Systems Grid
- Test Data Analysis
- Test Data Extraction
- Work Item Automations
- Work Item Operations
- Work Item Scheduler

### Delete a notebook

```bash
slcli notebook manage delete --id <notebook_id>
```

## WebApp management

Manage static web applications (pack, publish and remote management) using the `webapp` command group.

The `webapp` group provides a small local scaffold and .nipkg packer, and also manages WebApp resources on the SystemLink server.

- `slcli webapp init [--directory PATH] [--force]`
  - Scaffold a sample webapp (`index.html`) in `./app` inside the target directory. Use `--force` to overwrite an existing file.

- `slcli webapp pack <FOLDER> [--output FILE.nipkg]`
  - Pack a folder into a `.nipkg`. The `.nipkg` uses a Debian-style `ar` layout (members: `debian-binary`, `control.tar.gz`, `data.tar.gz`).

- `slcli webapp publish <SOURCE> [--id ID] [--name NAME] [--workspace WORKSPACE]`
  - Publish a `.nipkg` (or folder) to the WebApp service. Provide either `--id` to upload into an existing webapp, or `--name` to create a new resource and upload the content. `--workspace` selects the workspace for newly created webapps.
  - When publishing a folder, the CLI creates a temporary `.nipkg` inside a context-managed temporary directory so the packaged file is available during upload and is cleaned up automatically.

- `slcli webapp list [--workspace WORKSPACE] [--filter FILTER] [--take N] [--format table|json]`
  - List webapps. Defaults to interactive paging for `table` output (25 rows/page) and returns all results for `--format json`.

- `slcli webapp get --id ID`
  - Show webapp metadata.

- `slcli webapp delete --id ID`
  - Delete a webapp.

- `slcli webapp open --id ID`
  - Open a webapp in the browser. The command prefers an explicit web UI URL (from `SYSTEMLINK_WEB_URL` environment variable or combined keyring config), falls back to properties on the webapp resource, and finally falls back to the content endpoint.

Examples

```bash
# Create a scaffold
slcli webapp init --directory ./my-example

# Pack a folder into an explicit output file
slcli webapp pack ./my-example/app --output myapp.nipkg

# Publish a local folder (creates the webapp named MyApp in workspace Default)
slcli webapp publish ./my-example/app --name MyApp --workspace Default

# Publish an already-packed file into an existing webapp id
slcli webapp publish ./myapp.nipkg --id 123e4567-e89b-12d3-a456-426614174000

# List webapps in JSON (returns all matching items)
slcli webapp list --format json

# Filter by name (case-insensitive substring)
slcli webapp list --filter "MyApp"

# Open a published webapp in the browser
slcli webapp open --id 123e4567-e89b-12d3-a456-426614174000
```

Notes

- The packer writes a simple Debian-style `ar` archive and truncates ar member names to 16 bytes; this is adequate for common use-cases but can be extended to support GNU longname tables if needed.
- The `login` command was extended to support storing a combined keyring entry (`SYSTEMLINK_CONFIG`) that includes `api_url`, `api_key`, and `web_url`. The `webapp open` command prefers the explicit `SYSTEMLINK_WEB_URL` environment variable, then the combined keyring entry, and then legacy keyring entries before deriving a best-effort web UI URL from the API base URL.

## User Management

SystemLink CLI provides comprehensive user management capabilities for administering users in your SystemLink environment through the User Service API.

### List users

```bash
# List all users (table format, default)
slcli user list

# JSON format for programmatic use
slcli user list --format json

# Filter users with Dynamic LINQ queries
slcli user list --filter 'firstName.StartsWith("John") && status == "active"'

# Sort by different fields
slcli user list --sortby firstName --order descending

# Limit number of results
slcli user list --take 25

# Filter by account type
slcli user list --type user       # Only regular users
slcli user list --type service    # Only service accounts
slcli user list --type all        # All accounts (default)
```

### Get user details

```bash
# Get user details by ID (table format)
slcli user get --id <user_id>

# Get user details by email (table format)
slcli user get --email "john.doe@example.com"

# JSON output
slcli user get --id <user_id> --format json
slcli user get --email "jane.smith@example.com" --format json
```

### Create a new user

```bash
# Create a basic user
slcli user create --first-name "John" --last-name "Doe" --email "john.doe@example.com"

# Create user with additional details
slcli user create \
  --first-name "Jane" \
  --last-name "Smith" \
  --email "jane.smith@example.com" \
  --niua-id "jane.smith" \
  --accepted-tos \
  --policies "policy1,policy2" \
  --keywords "developer,qa" \
  --properties '{"department": "Engineering", "location": "Austin"}'
```

### Create a service account

Service accounts are designed for API/automation use and don't require email, phone, login, or NIUA ID fields.

```bash
# Create a basic service account
slcli user create --type service --first-name "CI Bot"

# Create service account with custom last name
slcli user create --type service --first-name "Deploy Bot" --last-name "Automation"

# Create service account with policies and properties
slcli user create --type service \
  --first-name "DataSync Service" \
  --policies "policy1,policy2" \
  --keywords "automation,sync" \
  --properties '{"purpose": "data synchronization"}'
```

### Update an existing user

```bash
# Update user's name
slcli user update --id <user_id> --first-name "Jane"

# Update multiple fields
slcli user update --id <user_id> \
  --email "new.email@example.com" \
  --accepted-tos true \
  --policies "policy3,policy4"

# Update custom properties
slcli user update --id <user_id> --properties '{"role": "Senior Developer"}'
```

### Delete a user

```bash
# Delete user (with confirmation prompt)
slcli user delete --id <user_id>
```

## Tag Management

SystemLink CLI provides comprehensive management for SystemLink Tags, allowing you to create, read, update, delete tags and manage their values.

All tag operations are workspace-scoped. You can specify a workspace with `--workspace`/`-w`, or the CLI will attempt to use the default workspace if available.

### List Tags

```bash
# List all tags in default workspace (table format)
slcli tag list

# List tags in a specific workspace
slcli tag list --workspace "Target Workspace"

# Filter by keywords
slcli tag list --keywords "sensor,temperature"

# Filter by path substring
slcli tag list --filter "temperature"

# JSON output
slcli tag list --format json
```

### View Tag Details

```bash
# View tag metadata and current value
slcli tag get "my-tag-path"

# Include aggregate statistics (min, max, avg, count)
slcli tag get "my-tag-path" --include-aggregates
```

### Create Tag

```bash
# Create a DOUBLE tag
slcli tag create "my-tag-path" --type DOUBLE

# Create with keywords and properties
slcli tag create "sensor.temp" --type DOUBLE --keywords "lab,sensor" --properties "location=room1"

# Enable aggregate collection
slcli tag create "sensor.temp" --type DOUBLE --collect-aggregates
```

Supported types: `DOUBLE`, `INT`, `STRING`, `BOOLEAN`, `U_INT64`, `DATE_TIME`

### Update Tag

```bash
# Update keywords
slcli tag update "my-tag-path" --keywords "new-keyword"

# Update properties (merge with existing)
slcli tag update "my-tag-path" --properties "status=active" --merge
```

### Manage Tag Values

```bash
# Set current value
slcli tag set-value "my-tag-path" "42.5"

# Set value with custom timestamp
slcli tag set-value "my-tag-path" "42.5" --timestamp "2024-01-01T12:00:00Z"

# Get current value
slcli tag get-value "my-tag-path"

# Get value with aggregates
slcli tag get-value "my-tag-path" --include-aggregates
```

### Delete Tag

```bash
# Delete a tag
slcli tag delete "my-tag-path"
```

## Custom Fields Management

The `customfield` command group allows you to manage custom fields in SystemLink, including configurations, groups, fields, and tables. Custom fields provide a web-based editor for visual editing of JSON configurations.

### Configuration Management

Manage custom field configurations:

```bash
# List all configurations
slcli customfield list

# JSON format for programmatic use
slcli customfield list --format json

# Filter by workspace
slcli customfield list --workspace "Production Workspace"

# Get a specific configuration
slcli customfield get --id <config_id>

# Export a configuration to JSON file
slcli customfield export --id <config_id> --output config.json

# Create configurations from JSON file
slcli customfield create --file config.json

# Update configurations from JSON file
slcli customfield update --file config.json

# Delete a configuration (recursive by default - deletes dependent groups/fields)
slcli customfield delete --id <config_id>

# Delete multiple configurations
slcli customfield delete --id <config_id1> --id <config_id2>

# Delete groups (standalone or multiple)
slcli customfield delete --group-id <group_id>
slcli customfield delete -g <group_id1> -g <group_id2>

# Delete fields
slcli customfield delete --field-id <field_id>
slcli customfield delete --fid <field_id1> --fid <field_id2>

# Delete mixed types in one command
slcli customfield delete --id <config_id> -g <group_id> --field-id <field_id>

# Non-recursive delete (only deletes specified items, not dependent items)
slcli customfield delete --id <config_id> --no-recursive

# Initialize a new configuration template
slcli customfield init --name "My Config" --workspace "MyWorkspace" --resource-type workorder:workorder
```

### Web Editor

Launch a local web-based editor for visual editing of custom field JSON files:

```bash
# Launch web editor with default settings (port 8080)
slcli customfield edit

# Load a specific configuration by ID from the server
slcli customfield edit --id <configuration-id>

# Custom port
slcli customfield edit --port 9000

# Don't auto-open browser
slcli customfield edit --no-browser
```

The web editor (Monaco-based):

- Hosts a local HTTP server for editing custom field configurations
- Provides a VS Code-like editor with JSON validation, formatting, and find/replace
- Includes a tree view, add dialogs for configurations/groups/fields, and schema validation
- Supports loading/saving to the SystemLink server from the UI
- Supports i18n (internationalization) field editing for multiple locales
- Supports interactive enum value editing for SELECT and MULTISELECT field types

**Note**: The web editor provides a professional editing experience for managing custom field configurations with real-time validation and server integration.

## File Management

SystemLink CLI provides comprehensive file management capabilities for the SystemLink File Service.

### List files

```bash
# List all files
slcli file list

# Filter by workspace
slcli file list --workspace <workspace_id>

# Search for files by name
slcli file list --filter test

# Limit results
slcli file list --take 10

# JSON output
slcli file list --format json
```

### Show file metadata

```bash
# Show metadata for a file
slcli file get <file_id>

# JSON output
slcli file get <file_id> --format json
```

### Upload a file

```bash
# Upload a file
slcli file upload /path/to/myfile.txt

# Upload to a specific workspace
slcli file upload /path/to/myfile.txt --workspace <workspace_id>

# Upload with a custom name
slcli file upload /path/to/myfile.txt --name "custom-name.txt"

# Upload with metadata properties
slcli file upload /path/to/myfile.txt --properties '{"author": "test", "version": "1.0"}'
```

### Download a file

```bash
# Download a file (uses original filename)
slcli file download <file_id>

# Download to a specific location
slcli file download <file_id> --output /path/to/save/file.txt

# Force overwrite existing file
slcli file download <file_id> --force
```

### Delete a file

```bash
# Delete a file (with confirmation)
slcli file delete --id <file_id>

# Delete without confirmation
slcli file delete --id <file_id> --force
```

### Search files with a query

```bash
# Query files by name (wildcard match)
slcli file query --filter 'name:("*test*")'

# Query with ordering
slcli file query --order-by created --descending

# Query within a workspace
slcli file query --workspace <workspace_id> --filter 'extension:("csv")'

# Combine filters
slcli file query --filter 'name:("*report*") AND extension:("pdf")'
```

### Update file metadata

```bash
# Rename a file
slcli file update-metadata <file_id> --name "new-name.txt"

# Add/update a property
slcli file update-metadata <file_id> --add-property "author=John Doe"

# Set multiple properties (replaces existing)
slcli file update-metadata <file_id> --properties '{"key1": "value1", "key2": "value2"}'
```

### Watch a folder and auto-upload new files

The `watch` command monitors a directory and automatically uploads new or modified files:

```bash
# Watch a folder and upload new files
slcli file watch /path/to/watch

# Watch and upload to a specific workspace
slcli file watch /path/to/watch --workspace <workspace_id>

# Watch and move files after upload
slcli file watch /path/to/watch --move-to /path/to/uploaded

# Watch and delete files after upload
slcli file watch /path/to/watch --delete-after-upload

# Watch only specific file patterns
slcli file watch /path/to/watch --pattern "*.csv"

# Watch subdirectories recursively
slcli file watch /path/to/watch --recursive

# Adjust debounce time (wait before uploading)
slcli file watch /path/to/watch --debounce 2.0
```

**Note**: The `watch` command requires the `watchdog` package. Install it with:

```bash
pip install watchdog
```

## Workspace Management

SystemLink CLI provides essential workspace management capabilities for viewing and administering workspaces in your SystemLink environment.

### List workspaces

```bash
# List all enabled workspaces
slcli workspace list

# Include disabled workspaces
slcli workspace list --include-disabled

# Filter by workspace name (case-insensitive substring match)
slcli workspace list --filter "prod"

# Combine filters
slcli workspace list --filter "test" --include-disabled

# JSON output for programmatic use
slcli workspace list --format json

# Limit API results (default: 25, max: 100)
slcli workspace list --take 50
```

### Show workspace details and contents

```bash
# Show workspace details by ID
slcli workspace info --id <workspace_id>

# Get workspace details by name
slcli workspace info --name "Production Workspace"

# JSON output with full workspace contents
slcli workspace info --name "Production Workspace" --format json
```

The info command provides comprehensive workspace details including:

- Workspace properties (ID, name, enabled status, default status)
- Test plan templates in the workspace
- Workflows in the workspace
- Notebooks in the workspace
- Summary counts of all resources

### Disable a workspace

```bash
# Disable a workspace (requires confirmation)
slcli workspace disable --id <workspace_id>
```

**Note**: Workspace creation and duplication are managed through the SystemLink web interface. This CLI provides read-only access and workspace disabling capabilities for administrative purposes.

## Output Formats

SystemLink CLI supports both human-readable table output and machine-readable JSON output for list commands:

### Table Output (Default)

- Colored, formatted tables using GitHub-style formatting
- Pagination support for large result sets
- Truncated text with ellipsis (…) for better readability
- Visual success (✓) and error (✗) indicators

### JSON Output

- Complete data export without pagination
- Perfect for scripting and automation
- Consistent structure across all list commands

```bash
# Human-readable table
slcli template list
slcli workflow list
slcli notebook manage list

# Machine-readable JSON
slcli template list --format json
slcli workflow list --format json
slcli notebook manage list --format json
```

## Flag Conventions

SystemLink CLI uses consistent flag patterns across all commands:

- `--format/-f`: Output format selection (`table` or `json`) for list commands
- `--output/-o`: File path for export/save operations
- `--workspace/-w`: Workspace filtering
- `--id/-i`: Resource identifiers
- `--file`: Input file paths for import operations (shorthand `-f` reserved for `--format`)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, coding standards, and contribution guidelines.

## Testing

### Unit Tests

Run the comprehensive unit test suite:

```bash
poetry run pytest tests/unit/ -v
```

### End-to-End Tests

SystemLink CLI includes an E2E testing framework for local development that validates commands against real SystemLink environments. This provides confidence that the CLI integrates correctly with actual SystemLink APIs during development and before releases.

**Note**: E2E tests are designed for manual execution during development. They are not part of the automated CI/CD pipeline.

#### Quick Setup

Run the interactive setup script:

```bash
python scripts/setup_e2e.py
```

#### Manual Setup

Set environment variables for your dev SystemLink environment:

```bash
export SLCLI_E2E_BASE_URL="https://your-dev-systemlink.domain.com"
export SLCLI_E2E_API_KEY="your-api-key"
export SLCLI_E2E_WORKSPACE="Default"
```

#### Running E2E Tests

```bash
# Run all E2E tests
python tests/e2e/run_e2e.py

# Run specific test categories
poetry run pytest tests/e2e/test_notebook_e2e.py -m e2e -v
poetry run pytest tests/e2e/test_user_e2e.py -m e2e -v
poetry run pytest tests/e2e/test_workspace_e2e.py -m e2e -v

# Run fast tests only (excludes slow/long-running tests)
poetry run pytest tests/e2e/ -m "e2e and not slow" -v
```

For detailed E2E testing documentation, see [tests/e2e/README.md](tests/e2e/README.md).
