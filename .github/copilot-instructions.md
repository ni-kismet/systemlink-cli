# Copilot Project Guidelines for slcli

## General Best Practices

- All code must be PEP8-compliant and pass linting (black, ni-python-styleguide).
- All new and modified code must include comprehensive type hints using `typing` module (Any, Dict, List, Optional, Tuple).
- All public functions and classes must have docstrings following Google docstring format.
- Use environment variables and keyring for all credentials and sensitive data.
- All CLI commands must provide clear help text and validation.
- Use Click for all CLI interfaces (not Typer) with inline @click.option decorators.
- All API interactions must handle errors gracefully and provide user-friendly messages.
- All new features and bugfixes must include or update unit tests.
- All code must be cross-platform (Windows, macOS, Linux) unless otherwise specified.
- All generated, build, and cache files must be excluded via `.gitignore`.

## CLI Architecture & Patterns

### Command Structure
- Use inline @click.option decorators directly on command functions (avoid decorator abstractions)
- All command modules follow the pattern: `register_{module}_commands(cli: Any) -> None`
- All command functions must have complete type annotations: parameters and return types
- Command groups use `@cli.group()` pattern with typed function signatures

### Universal Response Handling
- Use `UniversalResponseHandler` class for consistent response processing across all commands
- Use `handle_api_error(exc)` function for standardized API error handling with appropriate exit codes
- Use `format_success(message, data)` function for consistent success message formatting
- For mock responses in tests, use type annotation pattern: `resp: Any = MockResponse()` for Pylance compatibility

## CLI Best Practices (Based on https://clig.dev)

### Output & Formatting
- All list commands must support `--format/-f` option with `table` (default) and `json` formats
- All list commands must support `--take/-t` option with default of 25 items
- Use `--output/-o` for file path outputs (export, save operations)
- Use `table_utils.output_formatted_list()` for consistent table formatting with box-drawing characters
- Use `cli_utils.paginate_list_output()` for interactive pagination of table results (25 items per page with Y/n prompts)
- Use consistent visual indicators: `✓` for success messages, `✗` for error messages  
- Send all error messages to stderr using `click.echo(..., err=True)`
- For JSON output, display all data at once (no pagination); for table output, use interactive pagination
- Handle empty results gracefully: `[]` for JSON, descriptive message for table format

### Error Handling & Exit Codes
- Use standardized exit codes from the `ExitCodes` class:
  - `SUCCESS = 0`: Successful operation
  - `GENERAL_ERROR = 1`: Generic error
  - `INVALID_INPUT = 2`: Invalid user input or parameters
  - `NOT_FOUND = 3`: Resource not found
  - `PERMISSION_DENIED = 4`: Permission/authorization error
  - `NETWORK_ERROR = 5`: Network connectivity error
- Use `handle_api_error(exc)` function for consistent API error handling with automatic exit code selection
- Use `format_success(message, data)` function for consistent success messages
- Always exit with appropriate codes using `sys.exit(ExitCodes.*)` rather than raising ClickException
- Use `cli_utils.validate_output_format()` to standardize format validation

### Code Organization & Utilities
- Use `cli_utils.py` for common CLI utilities like validation and resource resolution
- Use `table_utils.py` for professional table formatting with box-drawing characters
- Use `universal_handlers.py` for standardized response processing across all commands
- Use `workspace_utils.py` for workspace-specific operations and filtering
- All utility modules must follow the established type annotation patterns

### Mock Response Pattern for Testing
- For test compatibility with type checkers, use: `resp: Any = FilteredResponse()` or `resp: Any = MockResponse()`
- FilteredResponse and MockResponse classes must implement:
  ```python
  def json(self) -> Dict[str, Any]: ...
  @property
  def status_code(self) -> int: ...
  ```

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

## HTTP API Documentation & Validation

### API Client Implementation Guidelines
- All HTTP client calls must include comprehensive type hints based on OpenAPI specifications
- Use `requests.Response` type annotations for all API responses
- Implement response validation using the OpenAPI spec as the source of truth
- Document any discrepancies between OpenAPI spec and actual service behavior in code comments
- All API client functions must handle standard HTTP error codes (400, 401, 403, 404, 500)

### OpenAPI Specifications (Reference)
- SystemLink DataFrame Service: https://dev-api.lifecyclesolutions.ni.com/nidataframe/swagger/v1/nidataframe.json
- SystemLink Notebook Service: https://dev-api.lifecyclesolutions.ni.com/ninotebook/swagger/v1/ninotebook.yaml
- SystemLink Test Monitor Service: https://dev-api.lifecyclesolutions.ni.com/nitestmonitor/swagger/v2/nitestmonitor-v2.yml
- SystemLink User Service: https://dev-api.lifecyclesolutions.ni.com/niuser/swagger/v1/niuser.yaml
- Work Order Service: https://dev-api.lifecyclesolutions.ni.com/niworkorder/swagger/v1/niworkorder.json
- Notebook Execution Service: https://dev-api.lifecyclesolutions.ni.com/ninbexecution/swagger/v1-ninbexecution.json
- Notebook Execution Artifact Service: https://dev-api.lifecyclesolutions.ni.com/ninbexecution/swagger/v1-ninbartifact.json
- SystemLink Notebook Service: https://dev-api.lifecyclesolutions.ni.com/ninotebook/swagger/v1/ninotebook.yaml

### Implementation Pattern
- Create typed response models based on OpenAPI schemas when implementing new API clients
- Use consistent error handling via `handle_api_error()` for all API interactions
- Add TODO comments when OpenAPI spec doesn't match actual service behavior

## Required Actions After Any Change

 - NOTE: Run linting and mypy after every change and before committing or opening a PR. This ensures type and style checks run locally and match CI expectations. At minimum run these two commands on each change:

   - `poetry run ni-python-styleguide lint`
   - `poetry run mypy slcli tests`

 - Run `poetry run ni-python-styleguide lint` to check for linting and style issues.
 - Run `poetry run black .` to auto-format code to the configured line length (100).
 - Run `poetry run pytest` to ensure all tests pass.
 - During active development (before running the entire test suite), you can run only the unit tests for a fast feedback loop:
   - Quick unit test pass (quiet): `poetry run pytest tests/unit -q`
   - Single test file: `poetry run pytest tests/unit/test_<name>.py -q`
   - Single test function: `poetry run pytest tests/unit/test_<name>.py::test_case -q`
   Always finish by running the full suite (`poetry run pytest`) before committing.
 - If adding or modifying CLI commands, update the `README.md` usage examples if needed.
 - If adding dependencies, update `pyproject.toml` and run `poetry lock`.

 - Run static type checks with mypy to verify type annotations and catch type errors early. Recommended workflow:

   1. Install as a dev dependency:

      ```sh
      poetry add --dev mypy
      ```

   2. Quick run (package + tests):

      ```sh
      poetry run mypy slcli tests
      ```

   3. For strict checking during CI or deeper validation, enable stricter flags or configure in `pyproject.toml` (example below).

  Optional `pyproject.toml` snippet to tune mypy (add under `[tool.mypy]`):

  ```toml
  [tool.mypy]
  python_version = "3.13"
  ignore_missing_imports = true
  disallow_untyped_defs = true
  warn_unused_ignores = true
  ```
- If changing packaging or build scripts, verify `poetry run build-pyinstaller` works and produces a binary in `dist/`.
- Verify all new CLI commands follow the CLI best practices outlined above.

## Pull Request/Commit Requirements

- All code must pass CI (lint, test, build) before merging.
- All new features must be documented in `README.md`.
- All code must be reviewed by at least one other developer.
- All new CLI commands must include JSON output support via `--format/-f` option.
- All error handling must use standardized exit codes and consistent formatting.
 - Every pull request must include a passing lint and mypy run (for example: `poetry run ni-python-styleguide lint` and `poetry run mypy slcli tests`) and include any necessary fixes; CI will enforce these checks.

## Copilot-Specific Instructions

- After making any code change, always:
  1. Run linting and auto-formatting.
  2. Run static type checks with mypy (`poetry run mypy slcli tests`) for quick type validation.
  3. Run unit tests only first for quick validation (`poetry run pytest tests/unit`).
  4. Run the full test suite (`poetry run pytest`).
  5. Report any failures or issues to the user.
- If you add a new CLI command, ensure it:
  - Is covered by a unit test in `tests/unit/`
  - Supports `--format/-f` option with `table` and `json` formats
  - Supports `--take/-t` option with default of 25 items for list commands
  - Uses consistent error handling with appropriate exit codes
  - Follows the success/error message formatting standards
  - Uses `UniversalResponseHandler` for response processing with `enable_pagination=True`
  - Uses `table_utils.output_formatted_list()` for table output
  - Implements interactive pagination for table results (Y/n prompts for next 25 results)
- If you update the CLI interface, update the `README.md` accordingly.
- Never commit or suggest committing files listed in `.gitignore`.
- When implementing list commands, ensure JSON output shows all results (no pagination).
- Use `handle_api_error()` for all API error handling instead of generic Click exceptions.
- Use `format_success()` for all success messages to maintain consistency.
- For type compatibility with Pylance, use `: Any = MockResponse()` pattern for mock responses.

---

These guidelines ensure code quality, maintainability, and a smooth developer experience for all contributors and Copilot.
