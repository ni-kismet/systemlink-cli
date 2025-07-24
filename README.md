# SystemLink CLI

SystemLink CLI (`slcli`) is a cross-platform Python CLI for SystemLink integrators, providing comprehensive management of SystemLink resources via REST APIs.

## Features

- **Secure Authentication**: Credential storage using [keyring](https://github.com/jaraco/keyring) with `login`/`logout` commands
- **Test Plan Templates**: Complete management (list, export, import, delete, init) with JSON and table output formats
- **Jupyter Notebooks**: Full lifecycle management (list, download, create, update, delete) with workspace filtering
- **Workflows**: Full workflow management (list, export, import, delete, init, update) with comprehensive state and action definitions
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

## Quick Start

1. **Login to SystemLink:**

   ```bash
   slcli login
   ```

2. **List available resources:**

   ```bash
   # View test plan templates
   slcli templates list

   # View workflows
   slcli workflows list

   # View notebooks
   slcli notebook list
   ```

3. **Initialize new resources:**

   ```bash
   # Create a new template
   slcli templates init --name "My Test Template" --template-group "Production"

   # Create a new workflow
   slcli workflows init --name "My Workflow" --description "Custom workflow"
   ```

4. **Get help for any command:**
   ```bash
   slcli --help
   slcli templates --help
   slcli workflows --help
   slcli notebook --help
   ```

## Authentication

Before using SystemLink CLI commands, you need to authenticate with your SystemLink server:

### Login to SystemLink

```bash
slcli login
```

This will securely prompt for your API key and SystemLink URL, then store them using your system's keyring.

### Logout (remove stored credentials)

```bash
slcli logout
```

## Test Plan Template Management

The `templates` command group allows you to manage test plan templates in SystemLink.

### Initialize a new template

Create a new test plan template JSON file with the complete schema structure:

```bash
# Interactive mode (prompts for required fields)
slcli templates init

# Specify required fields directly
slcli templates init --name "Battery Test Template" --template-group "Production Tests"

# Custom output file
slcli templates init --name "My Template" --template-group "Development" --output custom-template.json
```

The `init` command creates a JSON file with:

- Required fields: `name` and `templateGroup`
- Optional fields: `productFamilies`, `partNumbers`, `summary`, `description`, etc.
- Complete `executionActions` examples (JOB, NOTEBOOK, MANUAL actions)
- Property placeholders for customization

### List all test plan templates

```bash
# Table format (default)
slcli templates list

# JSON format for programmatic use
slcli templates list --format json

# Filter by workspace
slcli templates list --workspace "Production Workspace"
```

### Export a template to a local JSON file

```bash
slcli templates export --id <template_id> --output template.json
```

### Import a template from a local JSON file

```bash
slcli templates import --file template.json
```

The import command provides detailed error reporting for partial failures, including specific error types like `WorkspaceNotFoundOrNoAccess`.

### Delete a template

```bash
slcli templates delete --id <template_id>
```

## Workflow Management

The `workflows` command group allows you to manage workflows in SystemLink. All workflow commands use the beta feature flag automatically.

### Initialize a new workflow

Create a new workflow JSON file with a complete state machine structure:

```bash
# Interactive mode (prompts for required fields)
slcli workflows init

# Specify fields directly
slcli workflows init --name "Battery Test Workflow" --description "Workflow for battery testing procedures"

# Custom output file
slcli workflows init --name "My Workflow" --description "Custom workflow" --output custom-workflow.json
```

The `init` command creates a JSON file with:

- Basic workflow metadata: `name` and `description`
- Complete workflow `definition` with states, substates, and actions
- Example state transitions (Created → InProgress → Completed)
- Sample actions (Start, Pause, Resume, Complete, Fail, Abort)

### List all workflows

```bash
# Table format (default)
slcli workflows list

# JSON format for programmatic use
slcli workflows list --format json

# Filter by workspace
slcli workflows list --workspace "Production Workspace"
```

### Export a workflow to a local JSON file

```bash
slcli workflows export --id <workflow_id> --output workflow.json
```

### Import a workflow from a local JSON file

```bash
slcli workflows import --file workflow.json
```

### Update an existing workflow

```bash
slcli workflows update --id <workflow_id> --file updated-workflow.json
```

### Delete a workflow

```bash
slcli workflows delete --id <workflow_id>
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
slcli templates list
slcli workflows list
slcli notebook list

# Machine-readable JSON
slcli templates list --format json
slcli workflows list --format json
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
