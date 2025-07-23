# Copilot Project Guidelines for slcli

## General Best Practices

- All code must be PEP8-compliant and pass linting (black, ni-python-styleguide).
- All new and modified code must include appropriate docstrings and type hints where possible.
- All public functions and classes must have docstrings.
- Use environment variables and keyring for all credentials and sensitive data.
- All CLI commands must provide clear help text and validation.
- Use Click for all CLI interfaces (not Typer).
- All API interactions must handle errors gracefully and provide user-friendly messages.
- All new features and bugfixes must include or update unit tests.
- All code must be cross-platform (Windows, macOS, Linux) unless otherwise specified.
- All generated, build, and cache files must be excluded via `.gitignore`.

## CLI Best Practices (Based on https://clig.dev)

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

### User Experience
- Show progress for long-running operations when possible
- Use confirmation prompts for destructive operations
- Provide clear, actionable error messages that guide users toward solutions
- Support shell completion where feasible

## Required Actions After Any Change

- Run `poetry run ni-python-styleguide lint` to check for linting and style issues.
- Run `poetry run black .` to auto-format code to the configured line length (100).
- Run `poetry run pytest` to ensure all tests pass.
- If adding or modifying CLI commands, update the `README.md` usage examples if needed.
- If adding dependencies, update `pyproject.toml` and run `poetry lock`.
- If changing packaging or build scripts, verify `poetry run build-pyinstaller` works and produces a binary in `dist/`.
- Verify all new CLI commands follow the CLI best practices outlined above.

## Pull Request/Commit Requirements

- All code must pass CI (lint, test, build) before merging.
- All new features must be documented in `README.md`.
- All code must be reviewed by at least one other developer.
- All new CLI commands must include JSON output support via `--output/-o` option.
- All error handling must use standardized exit codes and consistent formatting.

## Copilot-Specific Instructions

- After making any code change, always:
  1. Run linting and auto-formatting.
  2. Run all unit tests.
  3. Report any failures or issues to the user.
- If you add a new CLI command, ensure it:
  - Is covered by a unit test in `tests/unit/`
  - Supports `--output/-o` option with `table` and `json` formats
  - Uses consistent error handling with appropriate exit codes
  - Follows the success/error message formatting standards
- If you update the CLI interface, update the `README.md` accordingly.
- Never commit or suggest committing files listed in `.gitignore`.
- When implementing list commands, ensure JSON output shows all results (no pagination).
- Use `handle_api_error()` for all API error handling instead of generic Click exceptions.
- Use `format_success()` for all success messages to maintain consistency.

---

These guidelines ensure code quality, maintainability, and a smooth developer experience for all contributors and Copilot.
