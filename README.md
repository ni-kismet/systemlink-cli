# SystemLink CLI

SystemLink CLI (`slcli`) is a cross-platform Python CLI for SystemLink integrators, providing comprehensive management of SystemLink resources via REST APIs.

## Features

- **Secure Authentication**: Credential storage using [keyring](https://github.com/jaraco/keyring) with `login`/`logout` commands
- **Function Management**: Complete WebAssembly (WASM) function definition and execution management with metadata-driven organization
- **Test Plan Templates**: Complete management (list, export, import, delete, init) with JSON and table output formats
- **Jupyter Notebooks**: Full lifecycle management (list, download, create, update, delete) with workspace filtering
- **User Management**: Comprehensive user administration (list, get, create, update, delete) with Dynamic LINQ filtering and pagination
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

Install SystemLink CLI using Homebrew from our official tap:

```bash
# Add the NI developer tools tap
brew tap ni-kismet/homebrew-ni

# Install slcli
brew install slcli
```

### Scoop (Windows)

Install SystemLink CLI using Scoop from our official bucket:

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
   slcli login
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
   slcli notebook list

   # View users
   slcli user list

   # View workspaces
   slcli workspace list

   # View dynamic form field configurations
   slcli dff config list

   # View dynamic form field groups
   slcli dff groups list
   ```

3. **Initialize new resources:**

   ```bash
   # Create a new template
   slcli template init --name "My Test Template" --template-group "Production"

   # Create a new workflow
   slcli workflow init --name "My Workflow" --description "Custom workflow"

   # Launch DFF web editor
   slcli dff edit
   ```

4. **Get help for any command:**
   ```bash
   slcli --help
   slcli template --help
   slcli workflow --help
   slcli notebook --help
   slcli dff --help
   ```

## Authentication

Before using SystemLink CLI commands, you need to authenticate with your SystemLink server:

### Login to SystemLink

```bash
# Interactive login (prompts for URL and API key)
slcli login

# Non-interactive login with flags
slcli login --url "https://your-server.com/api" --api-key "your-api-key"

# Partial flags (will prompt for missing values)
slcli login --url "https://your-server.com/api"
```

**Note**: The CLI automatically converts HTTP URLs to HTTPS for security. SystemLink servers typically require HTTPS for API access.

### Logout (remove stored credentials)

```bash
slcli logout
```

## Test Plan Template Management

The `template` command group allows you to manage test plan templates in SystemLink.

### Initialize a new template

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

### List all test plan templates

```bash
# Table format (default)
slcli template list

# JSON format for programmatic use
slcli template list --format json

# Filter by workspace
slcli template list --workspace "Production Workspace"
```

### Export a template to a local JSON file

```bash
slcli template export --id <template_id> --output template.json
```

### Import a template from a local JSON file

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

### Initialize a new workflow

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

### List all workflows

```bash
# Table format (default)
slcli workflow list

# JSON format for programmatic use
slcli workflow list --format json

# Filter by workspace
slcli workflow list --workspace "Production Workspace"
```

### Export a workflow to a local JSON file

```bash
slcli workflow export --id <workflow_id> --output workflow.json
```

### Import a workflow from a local JSON file

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

## Function Management

The `function` command group provides comprehensive management of WebAssembly (WASM) function definitions and executions in SystemLink. Functions are compiled WebAssembly modules that can be executed remotely with parameters.

**Architecture Overview:**

- **Function Service** (`/nifunction/v1`): Manages function definitions, metadata, and WASM content with interface-based organization
- **Function Execution Service** (`/nifunctionexecution/v1`): Handles function execution requests, both synchronous and asynchronous
- **Interface System**: Functions use an indexed `interface` property containing entrypoint, parameters, and returns schemas for efficient querying
- **Workspace Integration**: Functions are organized within SystemLink workspaces with comprehensive metadata support

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

```bash
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
    --timeout 30 \
    --format json
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

## Notebook Management

The `notebook` command group allows you to manage Jupyter notebooks in SystemLink.

### List all notebooks in a workspace

```bash
# List all notebooks (table format - default)
slcli notebook list

# List notebooks in specific workspace
slcli notebook list --workspace MyWorkspace

# JSON format for programmatic use
slcli notebook list --format json

# Control pagination (table format only)
slcli notebook list --take 50
```

### Download notebook content and/or metadata

```bash
# Download notebook content (.ipynb) by ID:
slcli notebook download --id <notebook_id> --output mynotebook.ipynb

# Download notebook content by name:
slcli notebook download --name MyNotebook --output mynotebook.ipynb

# Download notebook metadata as JSON:
slcli notebook download --id <notebook_id> --type metadata --output metadata.json

# Download both content and metadata:
slcli notebook download --id <notebook_id> --type both --output mynotebook.ipynb
```

### Create a new notebook

```bash
# Create from existing .ipynb file:
slcli notebook create --file mynotebook.ipynb --name MyNotebook
slcli notebook create --file mynotebook.ipynb --workspace MyWorkspace --name MyNotebook

# Create an empty notebook:
slcli notebook create --name MyNotebook
slcli notebook create --workspace MyWorkspace --name MyNotebook
```

### Update notebook metadata and/or content

```bash
# Update metadata only:
slcli notebook update --id <notebook_id> --metadata metadata.json

# Update content only:
slcli notebook update --id <notebook_id> --content mynotebook.ipynb

# Update both metadata and content:
slcli notebook update --id <notebook_id> --metadata metadata.json --content mynotebook.ipynb
```

### Delete a notebook

```bash
slcli notebook delete --id <notebook_id>
```

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

## Dynamic Form Fields (DFF) Management

The `dff` command group allows you to manage dynamic form fields in SystemLink, including configurations, groups, fields, and tables. DFF provides a web-based editor for visual editing of JSON configurations.

### Configuration Management

Manage dynamic form field configurations:

```bash
# List all configurations
slcli dff config list

# JSON format for programmatic use
slcli dff config list --format json

# Filter by workspace
slcli dff config list --workspace "Production Workspace"

# Export a configuration to JSON file
slcli dff config export --id <config_id> --output config.json

# Import a configuration from JSON file
slcli dff config import --file config.json

# Delete a configuration
slcli dff config delete --id <config_id>
```

### Group Management

Manage dynamic form field groups:

```bash
# List all groups
slcli dff groups list

# JSON format for programmatic use
slcli dff groups list --format json

# Filter by workspace
slcli dff groups list --workspace "Production Workspace"

# Export a group to JSON file
slcli dff groups export --id <group_id> --output group.json

# Import a group from JSON file
slcli dff groups import --file group.json

# Delete a group
slcli dff groups delete --id <group_id>
```

### Field Management

Manage individual dynamic form fields:

```bash
# List all fields
slcli dff fields list

# JSON format for programmatic use
slcli dff fields list --format json

# Filter by workspace
slcli dff fields list --workspace "Production Workspace"

# Export a field to JSON file
slcli dff fields export --id <field_id> --output field.json

# Import a field from JSON file
slcli dff fields import --file field.json

# Delete a field
slcli dff fields delete --id <field_id>
```

### Table Management

Manage dynamic form field tables:

```bash
# List all tables
slcli dff tables list

# JSON format for programmatic use
slcli dff tables list --format json

# Filter by workspace
slcli dff tables list --workspace "Production Workspace"

# Export a table to JSON file
slcli dff tables export --id <table_id> --output table.json

# Import a table from JSON file
slcli dff tables import --file table.json

# Delete a table
slcli dff tables delete --id <table_id>
```

### Web Editor

Launch a local web-based editor for visual editing of DFF JSON files:

```bash
# Launch web editor with default settings (port 8080, ./dff_editor directory)
slcli dff edit

# Custom port and directory
slcli dff edit --port 9000 --directory ./my_editor

# Auto-open browser (default: true)
slcli dff edit --open-browser

# Don't auto-open browser
slcli dff edit --no-open-browser
```

The web editor:

- Hosts a local HTTP server for editing DFF configurations
- Provides a simple HTML interface for JSON file management
- Creates standalone editor files in the specified directory
- Automatically opens your default browser to the editor interface
- Allows you to create, edit, and save DFF JSON configurations locally

**Note**: The web editor creates a self-contained directory with all necessary HTML, CSS, and JavaScript files. This directory can be moved or shared independently.

## Workspace Management

SystemLink CLI provides essential workspace management capabilities for viewing and administering workspaces in your SystemLink environment.

### List workspaces

```bash
# List all enabled workspaces
slcli workspace list

# Include disabled workspaces
slcli workspace list --include-disabled

# Filter by workspace name
slcli workspace list --name "Production"

# JSON output for programmatic use
slcli workspace list --format json
```

### Get detailed workspace information

```bash
# Get workspace details by ID
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
slcli notebook list

# Machine-readable JSON
slcli template list --format json
slcli workflow list --format json
slcli notebook list --format json
```

## Flag Conventions

SystemLink CLI uses consistent flag patterns across all commands:

- `--format/-f`: Output format selection (`table` or `json`) for list commands
- `--output/-o`: File path for export/save operations
- `--workspace/-w`: Workspace filtering
- `--id/-i`: Resource identifiers
- `--file/-f`: Input file paths for import operations

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
