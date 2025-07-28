# SystemLink CLI

SystemLink CLI (`slcli`) is a cross-platform Python CLI for SystemLink integrators, providing comprehensive management of SystemLink resources via REST APIs.

## Features

- **Secure Authentication**: Credential storage using [keyring](https://github.com/jaraco/keyring) with `login`/`logout` commands
- **Test Plan Templates**: Complete management (list, export, import, delete, init) with JSON and table output formats
- **Jupyter Notebooks**: Full lifecycle management (list, download, create, update, delete) with workspace filtering
- **User Management**: Comprehensive user administration (list, get, create, update, delete) with Dynamic LINQ filtering and pagination
- **Workflows**: Full workflow management (list, export, import, delete, init, update) with comprehensive state and action definitions
- **Workspace Management**: Essential workspace administration (list, info, disable) with comprehensive resource details
- **Cross-Platform**: Windows, macOS, and Linux support with standalone binaries
- **Professional CLI**: Consistent error handling, colored output, and comprehensive help system
- **Output Formats**: JSON and table output options for programmatic integration and human-readable display
- **Template Initialization**: Create new template JSON files
- **Extensible Architecture**: Designed for easy addition of new SystemLink resource types
- **Quality Assurance**: Full test suite with CI/CD, linting, and automated packaging

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

   # View workflows
   slcli workflow list

   # View notebooks
   slcli notebook list

   # View users
   slcli user list

   # View workspaces
   slcli workspace list
   ```

3. **Initialize new resources:**

   ```bash
   # Create a new template
   slcli template init --name "My Test Template" --template-group "Production"

   # Create a new workflow
   slcli workflow init --name "My Workflow" --description "Custom workflow"
   ```

4. **Get help for any command:**
   ```bash
   slcli --help
   slcli template --help
   slcli workflow --help
   slcli notebook --help
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
