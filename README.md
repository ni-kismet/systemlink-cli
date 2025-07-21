# SystemLink CLI

SystemLink CLI (`slcli`) is a cross-platform Python CLI for SystemLink integrators, providing comprehensive management of SystemLink resources via REST APIs.

## Features

- **Secure Authentication**: Credential storage using [keyring](https://github.com/jaraco/keyring) with `login`/`logout` commands
- **Test Plan Templates**: Complete management (list, export, import, delete) with JSON and table output formats
- **Jupyter Notebooks**: Full lifecycle management (list, download, create, update, delete) with workspace filtering
- **Cross-Platform**: Windows, macOS, and Linux support with standalone binaries
- **Professional CLI**: Consistent error handling, colored output, and comprehensive help system
- **Output Formats**: JSON and table output options for programmatic integration and human-readable display
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

### From Source

1. **Install dependencies:**

   ```bash
   poetry install
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

   # View notebooks
   slcli notebook list
   ```

3. **Get help for any command:**
   ```bash
   slcli --help
   slcli templates --help
   slcli notebook --help
   ```

## Development Setup

1. **Install Poetry** (if not already installed):

   ```bash
   pip install poetry
   ```

2. **Install dependencies:**

   ```bash
   poetry install
   ```

## Running

- Run the CLI directly:

  ```bash
  poetry run slcli
  ```

- Or as a Python module:
  ```bash
  poetry run python -m slcli
  ```

## Build a Standalone Binary (Cross-Platform)

### macOS/Linux (Homebrew/PyInstaller)

To build a single-file executable and Homebrew formula:

```bash
poetry run python scripts/build_homebrew.py
```

- This will:
  - Build the PyInstaller binary in `dist/slcli/`
  - Create a tarball `dist/slcli.tar.gz`
  - Generate a Homebrew formula `dist/homebrew-slcli.rb` with the correct SHA256

You can then install locally with:

```bash
brew install ./dist/homebrew-slcli.rb
```

### Windows (Scoop/PyInstaller)

To build a Windows executable and Scoop manifest:

```powershell
poetry run python scripts/build_pyinstaller.py
poetry run python scripts/build_scoop.py
```

- This will:
  - Build `dist/slcli.exe`
  - Generate a Scoop manifest `dist/scoop-slcli.json` with the correct SHA256

You can use the manifest in your own Scoop bucket for easy installation.

### CI/CD Automation

- All builds, tests, and packaging are automated via GitHub Actions for both Homebrew and Scoop.
- Artifacts (`slcli.tar.gz`, `homebrew-slcli.rb`, `slcli.exe`, `scoop-slcli.json`) are uploaded for each build.

## Release Process

### Creating a Release

1. **Update the version** in `pyproject.toml`:

   ```toml
   [tool.poetry]
   version = "0.2.0"  # Update to new version
   ```

2. **Create and push a git tag**:

   ```bash
   git tag v0.2.0
   git push origin v0.2.0
   ```

3. **Automated release workflow** will:
   - Run all tests and linting
   - Build PyInstaller binaries for all platforms
   - Generate Homebrew formula and Scoop manifest
   - Create GitHub release with all artifacts
   - Automatically update the Homebrew tap (`ni-kismet/homebrew-ni`)

### Release Artifacts

Each release automatically generates:

- `slcli.tar.gz` - Source tarball for Homebrew
- `homebrew-slcli.rb` - Homebrew formula
- `slcli.exe` - Windows executable
- `scoop-slcli.json` - Scoop manifest for Windows

### Homebrew Publishing

The release workflow automatically:

- Updates the formula in `ni-kismet/homebrew-ni` tap
- Calculates SHA256 checksums
- Updates version and download URLs
- Commits changes to the tap repository

Users can then install the latest version with:

```bash
brew update
brew upgrade slcli
```

## Testing & Linting

- Run tests:
  ```bash
  poetry run pytest
  ```
- Lint code:
  ```bash
  poetry run ni-python-styleguide lint
  ```

## Contributing

See [the NI Python development wiki](https://dev.azure.com/ni/DevCentral/_wiki/wikis/AppCentral.wiki/?pagePath=/Tools/Python/Tutorials/Making-a-change-to-an-existing-project) for contribution guidelines.

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

### List all test plan templates

```bash
# Table format (default)
slcli templates list

# JSON format for programmatic use
slcli templates list --output json
```

### Export a template to a local JSON file

```bash
slcli templates export --id <template_id> --output template.json
```

### Import a template from a local JSON file

```bash
slcli templates import --file template.json
```

### Delete a template

```bash
slcli templates delete --id <template_id>
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
slcli notebook list --output json

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
slcli notebook list

# Machine-readable JSON
slcli templates list --output json
slcli notebook list --output json
```
