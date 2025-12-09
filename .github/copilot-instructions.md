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

## New CLI Command Checklist

1. Create `slcli/{feature}_click.py` with `register_{feature}_commands(cli)`
2. Add registration call in `main.py`
3. Support `--format/-f` and `--take/-t` for list commands
4. Use `UniversalResponseHandler` for responses
5. Use `handle_api_error()` for all exceptions
6. Create `tests/unit/test_{feature}_click.py`
7. Update `README.md` with usage examples
