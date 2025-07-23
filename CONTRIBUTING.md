# Contributing to SystemLink CLI

Thank you for your interest in contributing to SystemLink CLI! This document provides guidelines and information for contributors.

## Development Setup

1. **Install Poetry** (if not already installed):

   ```bash
   pip install poetry
   ```

2. **Install dependencies:**

   ```bash
   poetry install
   ```

3. **Running the CLI:**

   ```bash
   # Run the CLI directly
   poetry run slcli

   # Or as a Python module
   poetry run python -m slcli
   ```

## Code Quality Requirements

All code must meet the following standards before being merged:

### Linting and Formatting

- All code must be PEP8-compliant and pass linting (black, ni-python-styleguide)
- All new and modified code must include appropriate docstrings and type hints where possible
- All public functions and classes must have docstrings

```bash
# Run linting
poetry run ni-python-styleguide lint

# Auto-format code
poetry run black .
```

### Testing

- All new features and bugfixes must include or update unit tests
- All tests must pass before merging

```bash
# Run all tests
poetry run pytest

# Run tests with coverage
poetry run pytest --cov
```

### CLI Standards

- All CLI commands must provide clear help text and validation
- Use Click for all CLI interfaces (not Typer)
- All API interactions must handle errors gracefully and provide user-friendly messages
- All code must be cross-platform (Windows, macOS, Linux) unless otherwise specified

## CLI Best Practices

Based on [CLI Guidelines](https://clig.dev), SystemLink CLI follows these patterns:

### Output & Formatting

- All list commands must support `--format/-f` option with `table` (default) and `json` formats
- Use `--output` for file path outputs (export, save operations)
- Use consistent visual indicators: `✓` for success messages, `✗` for error messages
- Send all error messages to stderr using `click.echo(..., err=True)`
- For JSON output, display all data at once (no pagination); for table output, retain pagination
- Handle empty results gracefully: `[]` for JSON, descriptive message for table format

### Error Handling & Exit Codes

- Use standardized exit codes from the `ExitCodes` class:
  - `SUCCESS = 0`: Successful operation
  - `GENERAL_ERROR = 1`: Generic error
  - `INVALID_INPUT = 2`: Invalid user input or parameters
  - `NOT_FOUND = 3`: Resource not found
  - `PERMISSION_DENIED = 4`: Permission/authorization error
  - `NETWORK_ERROR = 5`: Network connectivity error
- Use `handle_api_error(exc)` function for consistent API error handling
- Use `format_success(message, data)` function for consistent success messages
- Always exit with appropriate codes using `sys.exit(ExitCodes.*)` rather than raising ClickException

### Command Structure

- All commands must validate required parameters and provide helpful error messages
- Use consistent parameter names across similar commands (e.g., `--workspace`, `--output`)
- Provide sensible defaults and show them in help text with `show_default=True`
- Support both ID and name-based lookups where applicable (e.g., `--id` or `--name`)

## Security

- Use environment variables and keyring for all credentials and sensitive data
- Never commit or suggest committing files listed in `.gitignore`

## Required Actions After Any Change

1. **Run linting and auto-formatting:**

   ```bash
   poetry run ni-python-styleguide lint
   poetry run black .
   ```

2. **Run all tests:**

   ```bash
   poetry run pytest
   ```

3. **If adding or modifying CLI commands:**

   - Update the `README.md` usage examples if needed
   - Ensure it follows the CLI best practices outlined above
   - Ensure it supports JSON output via `--format/-f` option for list commands

4. **If adding dependencies:**

   ```bash
   poetry add <package>
   poetry lock
   ```

5. **If changing packaging or build scripts:**
   ```bash
   poetry run build-pyinstaller
   ```
   Verify it works and produces a binary in `dist/`.

## Build Process

### Building Standalone Binaries

#### macOS/Linux (Homebrew/PyInstaller)

```bash
poetry run python scripts/build_homebrew.py
```

This will:

- Build the PyInstaller binary in `dist/slcli/`
- Create a tarball `dist/slcli.tar.gz`
- Generate a Homebrew formula `dist/homebrew-slcli.rb` with the correct SHA256

You can then install locally with:

```bash
brew install ./dist/homebrew-slcli.rb
```

#### Windows (Scoop/PyInstaller)

```bash
poetry run python scripts/build_pyinstaller.py
poetry run python scripts/build_scoop.py
```

This will:

- Build `dist/slcli.exe`
- Generate a Scoop manifest `dist/scoop-slcli.json` with the correct SHA256

### CI/CD Automation

- All builds, tests, and packaging are automated via GitHub Actions for both Homebrew and Scoop
- Artifacts (`slcli.tar.gz`, `homebrew-slcli.rb`, `slcli.exe`, `scoop-slcli.json`) are uploaded for each build

## Release Process

### Creating a Release

1. **Update the version** in `pyproject.toml`:

   ```toml
   [tool.poetry]
   version = "0.2.0"  # Update to new version
   ```

2. **Create and push a git tag:**

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

## Pull Request Requirements

- All code must pass CI (lint, test, build) before merging
- All new features must be documented in `README.md`
- All code must be reviewed by at least one other developer
- All new CLI commands must include JSON output support via `--format/-f` option
- All error handling must use standardized exit codes and consistent formatting

## Getting Help

For questions about SystemLink CLI development:

1. Check this contributing guide
2. Review existing code patterns in the codebase
3. See [the NI Python development wiki](https://dev.azure.com/ni/DevCentral/_wiki/wikis/AppCentral.wiki/?pagePath=/Tools/Python/Tutorials/Making-a-change-to-an-existing-project) for additional guidelines

## Code Style

- Follow PEP 8 style guidelines
- Use meaningful variable and function names
- Add docstrings to all public functions and classes
- Include type hints where possible
- Keep functions focused and single-purpose
- Use consistent error handling patterns
