# Copilot Project Guidelines for slcli

SystemLink CLI (`slcli`) is a cross-platform Python CLI for SystemLink integrators, managing resources via REST APIs. Uses **Click** for CLI, **Poetry** for dependencies, and **keyring** for credential storage.

## Architecture Overview

```
slcli/
├── main.py              # Entry point, registers all command groups
├── *_click.py           # Command modules (workspace_click.py, user_click.py, etc.)
├── utils.py             # Core utilities: ExitCodes, handle_api_error(), format_success()
├── universal_handlers.py # UniversalResponseHandler for consistent response processing
├── cli_utils.py         # Validation, pagination, resource resolution helpers
├── table_utils.py       # Box-drawing table formatting
└── config.py            # Configuration file management (~/.config/slcli/)
```

**Command registration pattern** - each module exports `register_{module}_commands(cli: Any)`:
```python
def register_workspace_commands(cli: Any) -> None:
    @cli.group()
    def workspace() -> None: ...
    
    @workspace.command(name="list")
    @click.option("--format", "-f", type=click.Choice(["table", "json"]), default="table")
    @click.option("--take", "-t", type=int, default=25, show_default=True)
    def list_workspaces(format: str, take: int) -> None: ...
```

## Essential Developer Commands

```bash
# Required after EVERY change (CI enforces these)
poetry run ni-python-styleguide lint   # Linting
poetry run mypy slcli tests            # Type checking
poetry run pytest tests/unit -q        # Quick unit tests
poetry run pytest                      # Full test suite (before commit)

# Formatting (auto-fix)
poetry run black .                     # Line length: 100

# Build binary
poetry run build-pyinstaller           # Output: dist/slcli/
```

## CLI Command Patterns

### Standard Options (all list commands)
- `--format/-f`: `table` (default) or `json`
- `--take/-t`: Default 25 items
- `--output/-o`: File path for export operations

### Response Handling
```python
from .universal_handlers import UniversalResponseHandler, FilteredResponse
from .utils import handle_api_error, format_success, ExitCodes

# List commands
UniversalResponseHandler.handle_list_response(
    resp=resp, data_key="workspaces", item_name="workspace",
    format_output=format_output, formatter_func=workspace_formatter,
    headers=["Name", "ID"], column_widths=[30, 36],
    enable_pagination=True, page_size=take
)

# Error handling - always use handle_api_error(), not ClickException
try:
    resp = make_api_request("GET", url)
except Exception as exc:
    handle_api_error(exc)  # Exits with appropriate ExitCodes.*

# Success messages
format_success("Workspace created", {"id": ws_id, "name": ws_name})  # Outputs: ✓ Workspace created
```

### Exit Codes (`ExitCodes` class in `utils.py`)
- `SUCCESS = 0`, `GENERAL_ERROR = 1`, `INVALID_INPUT = 2`
- `NOT_FOUND = 3`, `PERMISSION_DENIED = 4`, `NETWORK_ERROR = 5`

### Visual Indicators
- Success: `✓`, Error: `✗`
- Errors to stderr: `click.echo(f"✗ Error: {msg}", err=True)`

## Testing Patterns

```python
# tests/unit/test_*_click.py structure
def make_cli() -> click.Group:
    @click.group()
    def test_cli() -> None: pass
    register_workspace_commands(test_cli)
    return test_cli

# Mock pattern for type checker compatibility
def mock_get(*a: Any, **kw: Any) -> Any:
    class R:
        def raise_for_status(self) -> None: pass
        def json(self) -> Any: return {"workspaces": [...]}
    return R()

# FilteredResponse for passing filtered data to handlers
filtered_resp: Any = FilteredResponse({"workspaces": filtered_list})
```

## Type Hints & Style

- **Required**: Full type annotations on all functions (params + return types)
- **Docstrings**: Google format
- **Mock responses**: Use `resp: Any = MockResponse()` for Pylance compatibility
- **Line length**: 100 characters

## API Integration

- Auth stored in keyring under `systemlink-cli` service
- Base URL from `get_base_url()` in `utils.py`
- OpenAPI specs at `https://dev-api.lifecyclesolutions.ni.com/ni*/swagger/`

## New CLI Command Requirements & Checklist

1. **Create Command Module**:  
   - Create `slcli/{feature}_click.py` with `register_{feature}_commands(cli: Any) -> None` function.  
   - All command functions must have complete type annotations (parameters and return types).  
   - Use inline `@click.option` decorators directly on command functions (avoid decorator abstractions).  
   - Command groups use `@cli.group()` pattern with typed function signatures.

2. **Register Command**:  
   - Add registration call in `main.py` to include the new command group.

3. **List Command Requirements**:  
   - Support `--format/-f` option with `table` (default) and `json` formats.  
   - Support `--take/-t` option with default of 25 items.  
   - For table output, use `table_utils.output_formatted_list()` and implement interactive pagination (25 items per page, Y/n prompt for more).  
   - For JSON output, display all results at once (no pagination).  
   - Handle empty results gracefully: `[]` for JSON, descriptive message for table format.

4. **Response Handling**:  
   - Use `UniversalResponseHandler` for consistent response processing across all commands.  
   - Use `handle_api_error(exc)` for standardized API error handling with appropriate exit codes.  
   - Use `format_success(message, data)` for consistent success message formatting.  
   - Always exit with appropriate codes using `sys.exit(ExitCodes.*)` rather than raising ClickException.

5. **Type Annotation Patterns**:  
   - All functions and classes must include comprehensive type hints using the `typing` module (`Any`, `Dict`, `List`, `Optional`, `Tuple`).  
   - For mock responses in tests, use type annotation pattern: `resp: Any = MockResponse()` for Pylance compatibility.  
   - FilteredResponse and MockResponse classes must implement:  
     ```python
     def json(self) -> Dict[str, Any]: ...
     @property
     def status_code(self) -> int: ...
     ```

6. **Testing Requirements**:  
   - Create or update unit tests in `tests/unit/test_{feature}_click.py`.  
   - All new and modified code must include or update unit tests.  
   - For quick feedback, run:  
     - `poetry run pytest tests/unit -q` (all unit tests)  
     - `poetry run pytest tests/unit/test_{feature}_click.py -q` (single test file)  
     - `poetry run pytest tests/unit/test_{feature}_click.py::test_case -q` (single test function)  
   - Always finish by running the full suite: `poetry run pytest`.

7. **Linting & Type Checking**:  
   - Run linting and mypy after every change and before committing or opening a PR:  
     - `poetry run ni-python-styleguide lint`  
     - `poetry run mypy slcli tests`  
   - Run `poetry run black .` to auto-format code to the configured line length (100).

8. **Pull Request Requirements**:  
   - All code must pass CI (lint, test, build) before merging.  
   - All new features must be documented in `README.md`.  
   - All code must be reviewed by at least one other developer.  
   - All new CLI commands must include JSON output support via `--format/-f` option.  
   - All error handling must use standardized exit codes and consistent formatting.  
   - Every pull request must include a passing lint and mypy run (for example: `poetry run ni-python-styleguide lint` and `poetry run mypy slcli tests`) and include any necessary fixes; CI will enforce these checks.

9. **Copilot-Specific Instructions**:  
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

10. **Documentation**:  
    - Update `README.md` with usage examples for all new or modified CLI commands.  
    - Document any discrepancies between OpenAPI spec and actual service behavior in code comments.
