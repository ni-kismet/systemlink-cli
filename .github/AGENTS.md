# Copilot Agents Guide for SystemLink CLI

**Comprehensive guide for AI agents (Copilot) to conduct professional code reviews on the SystemLink CLI project.**

---

## Table of Contents

1. [Quick Start](#-quick-start)
2. [Slash Command](#-slash-command)
3. [High Standards](#-high-standards)
4. [Review Types](#-review-types)
5. [Complete Checklist](#-complete-checklist)
6. [Command Reference](#-command-reference)
7. [Standards Reference](#-standards-reference)

---

## 🚀 Quick Start

### For New Agents

1. **Read this file** for overview
2. **Use the `/slcli-pr-review` slash command** in Copilot Chat:
   ```bash
   /slcli-pr-review                    # Default: comprehensive review
   /slcli-pr-review cli                # CLI command focus
   /slcli-pr-review api                # API safety & integration
   /slcli-pr-review refactor           # Code reuse & architecture
   /slcli-pr-review e2e                # E2E testing focus
   /slcli-pr-review standard coverage  # With optional focus area
   ```
3. **Follow the checklist** provided by the slash command
4. **Run the commands** listed in the review prompt
5. **Provide detailed feedback** to the developer

### Slash Command Location

File: [`.github/prompts/pr-review.prompt.md`](.github/prompts/pr-review.prompt.md)

---

## 💬 Slash Command

### Usage

In **Copilot Chat**, type:

```
/slcli-pr-review [type] [focus]
```

### Arguments

- `type` (optional): Review type - `standard`, `cli`, `api`, `refactor`, or `e2e`. Default: `standard`
- `focus` (optional): Additional focus area to emphasize

### Examples

```bash
/slcli-pr-review                    # Standard comprehensive review
/slcli-pr-review cli                # CLI-focused review
/slcli-pr-review api                # API-focused review
/slcli-pr-review refactor           # Refactoring-focused review
/slcli-pr-review e2e                # E2E testing-focused review
/slcli-pr-review standard coverage  # Standard review with coverage focus
```

---

## 🏆 High Standards

This project enforces **professional-grade standards** across all code reviews:

### ✅ Test Coverage

- **Minimum 80%** coverage for new code
- **Unit tests** required for all new functionality:
  ```bash
  poetry run pytest tests/unit -q
  ```
- **E2E tests** required for workflows and API integration:
  ```bash
  poetry run pytest tests/e2e/ -n auto --timeout=300
  ```
- **Error paths tested**, not just happy path
- **All tests pass** locally before PR submission

### ✅ Code Reuse & Architecture

- **DRY Principle**: No duplicated logic
- **Utilities properly centralized**:
  - API utilities → `utils.py`
  - CLI utilities → `cli_utils.py`
  - Response handling → `universal_handlers.py`
  - Table output → `table_utils.py`
  - Error handling → `utils.py`
- **Established patterns followed**:
  - CLI registration pattern
  - UniversalResponseHandler for responses
  - handle_api_error() for error handling
  - format_success() for success messages
- **API queries parameterized** (no string interpolation):

  ```python
  # ✅ Good
  "filter": "name == @0",
  "substitutions": [name]

  # ❌ Bad
  "filter": f"name == '{name}'"
  ```

### ✅ Repository Standards

- **Linting passes**: `poetry run ni-python-styleguide lint`
- **Type checking passes**: `poetry run mypy slcli tests`
- **Code formatting clean**: `poetry run black .` (100 char limit)
- **Documentation updated**: README, docstrings, help text
- **CLI standards met**: `--format/-f`, `--help`, proper exit codes
- **Configuration standards**: No hardcoded secrets or URLs
- **Cross-platform compatible**: Windows/macOS/Linux

### ✅ Quality Assurance

- **Full test suite passes** locally and in CI
- **No flaky or intermittent** test failures
- **No coverage regression** in existing code
- **Security standards met**: No hardcoded secrets, parameterized queries
- **Documentation complete**: README updated, docstrings present

---

## 📋 Review Types

### 1. Standard Review (Default)

**When to use:** General PR review covering all aspects

**Focus areas:**

- Testing & QA (unit + E2E)
- Code quality (linting, types, formatting)
- Architecture & design patterns
- Repository standards conformance
- Safety & security
- Documentation

**Approval criteria:**

- All tests pass (unit + E2E)
- Linting, type checking, formatting pass
- ≥80% coverage for new code
- No code duplication
- Architecture patterns followed
- Repository standards met
- Documentation updated

**Key commands:**

```bash
poetry run pytest tests/unit -q
poetry run pytest tests/e2e/ -n auto --timeout=300
poetry run ni-python-styleguide lint
poetry run mypy slcli tests
```

---

### 2. CLI Review

**When to use:** Reviewing CLI command changes, options, help text

**Focus areas:**

- Command structure and registration
- Option naming and consistency
- Help text quality
- Exit codes and error messages
- Table/JSON format support
- User experience

**What to check:**

- [ ] All commands have `--help`
- [ ] Help text is clear and actionable
- [ ] List commands support `--format/-f` with `table`/`json`
- [ ] List commands support `--take/-t` with sensible defaults
- [ ] Error messages are user-friendly
- [ ] Exit codes use `ExitCodes` enum
- [ ] Errors sent to stderr
- [ ] Options use consistent naming
- [ ] Uses `UniversalResponseHandler` for responses
- [ ] Uses `handle_api_error()` for errors
- [ ] Uses `format_success()` for success messages

**Key commands:**

```bash
poetry run pytest tests/unit/test_*_click.py -v
poetry run ni-python-styleguide lint
poetry run mypy slcli tests
```

---

### 3. API Review

**When to use:** Reviewing API integration, query safety, error handling

**Focus areas:**

- Query safety (parameterized vs string interpolation)
- Error handling and exit codes
- API response validation
- Exact-match verification
- Workspace scoping
- Dry-run support

**Critical checks:**

- [ ] **Parameterized queries** (NOT string interpolation):
  ```python
  ✅ "filter": "name == @0", "substitutions": [name]
  ❌ "filter": f"name == '{name}'"
  ```
- [ ] Queries fetch sufficient results for verification
- [ ] Exact-match verification implemented
- [ ] Uses `handle_api_error()` pattern
- [ ] Proper exit codes for errors
- [ ] No N+1 query patterns
- [ ] Workspace scoping correct
- [ ] Resources tagged appropriately

**Key commands:**

```bash
poetry run pytest tests/unit -q
poetry run pytest tests/e2e/ -n auto --timeout=300
poetry run mypy slcli tests
```

---

### 4. Refactoring Review

**When to use:** Reviewing code reuse improvements, architecture changes

**Focus areas:**

- Elimination of code duplication
- Proper utility placement
- Backward compatibility
- Test coverage maintenance
- Code quality improvements

**What to check:**

- [ ] No duplication identified (or minimized)
- [ ] Utilities properly placed:
  - API → `utils.py`
  - CLI → `cli_utils.py`
  - Responses → `universal_handlers.py`
  - Tables → `table_utils.py`
- [ ] Constants defined (not magic strings/numbers)
- [ ] Complex logic extracted to functions
- [ ] Backward compatibility maintained
- [ ] Tests validate both code paths
- [ ] Linting passes
- [ ] Type checking passes

**Key commands:**

```bash
poetry run ni-python-styleguide lint
poetry run mypy slcli tests
poetry run pytest tests/unit -q
poetry run pytest
```

---

### 5. E2E Testing Review

**When to use:** Reviewing end-to-end test quality, test isolation, workflow coverage

**Focus areas:**

- Test isolation and cleanup
- Workflow coverage
- Error scenario testing
- Test execution and performance
- Documentation completeness

**What to check:**

- [ ] Tests are isolated (no side effects)
- [ ] Proper setup/teardown
- [ ] Tests don't depend on execution order
- [ ] Cleanup happens even on failure
- [ ] Workflows tested end-to-end
- [ ] Success and failure scenarios covered
- [ ] Tests run in parallel:
  ```bash
  poetry run pytest tests/e2e/ -n auto --timeout=300
  ```
- [ ] No test interdependencies
- [ ] Tests pass consistently (not flaky)
- [ ] Documentation complete (purpose, setup, requirements)

**Key commands:**

```bash
poetry run pytest tests/e2e/ -n auto --timeout=300
poetry run pytest tests/e2e/ -v  # Without parallelization
```

---

## ✅ Complete Checklist

Use this comprehensive checklist for detailed reviews:

### 📋 Pre-Review Assessment

- [ ] PR title clearly describes the change
- [ ] PR description explains what, why, and how
- [ ] PR is focused (< 400 lines of code changes)
- [ ] All commits have meaningful messages
- [ ] No merge conflicts
- [ ] Branch is up-to-date with `main`

### 🧪 Testing & Quality Assurance

#### Unit Tests

- [ ] All new code has unit tests
- [ ] All modified code has updated tests
- [ ] Tests in appropriate directory: `tests/unit/`
- [ ] Test files follow naming: `test_*_click.py`, `test_*.py`
- [ ] All unit tests pass: `poetry run pytest tests/unit -q`
- [ ] Coverage ≥ 80% for new code
- [ ] Both happy path and error cases tested
- [ ] No flaky tests
- [ ] Mock patterns use `Any` type hints

#### E2E Tests

- [ ] E2E tests added if feature touches API/workflows
- [ ] Tests are properly isolated
- [ ] Setup/teardown and cleanup implemented
- [ ] All E2E tests pass: `poetry run pytest tests/e2e/ -n auto --timeout=300`
- [ ] Tests pass consistently (not flaky)

#### Full Suite

- [ ] All tests pass locally: `poetry run pytest`
- [ ] No new test warnings or deprecations
- [ ] No coverage regression

### 📝 Code Quality & Standards

#### Linting & Formatting

- [ ] Linting passes: `poetry run ni-python-styleguide lint`
- [ ] Code formatted: `poetry run black .` (≤100 chars)
- [ ] No unused imports
- [ ] No debug print statements

#### Type Checking

- [ ] All functions have complete type annotations
- [ ] mypy passes: `poetry run mypy slcli tests`
- [ ] No `# type: ignore` without justification
- [ ] Complex types use type aliases
- [ ] Generic types properly constrained

#### Documentation

- [ ] Public functions have docstrings (Google format)
- [ ] Docstrings explain purpose, parameters, return, exceptions
- [ ] README.md updated if CLI changed
- [ ] Complex algorithms have explanatory comments
- [ ] No stale comments
- [ ] CHANGELOG.md updated

### 🏗️ Architecture & Design

#### Code Reuse

- [ ] No duplicated logic
- [ ] DRY principle followed
- [ ] Utilities properly placed:
  - API utilities → `utils.py`
  - CLI utilities → `cli_utils.py`
  - Response handling → `universal_handlers.py`
  - Table output → `table_utils.py`
- [ ] No copy-paste between modules

#### Design Patterns

- [ ] CLI registration pattern followed
- [ ] `UniversalResponseHandler` used for responses
- [ ] `handle_api_error()` used for errors
- [ ] `format_success()` used for success messages
- [ ] `ExitCodes` enum used
- [ ] List commands support `--format/-f` (table/json)
- [ ] Pagination implemented (25 items/page)
- [ ] JSON shows all results (no pagination)

#### API Integration

- [ ] **Parameterized queries used** (NOT string interpolation)
- [ ] Queries fetch sufficient results
- [ ] Exact-match verification implemented
- [ ] Case-insensitive name matching where appropriate
- [ ] Workspace scoping correct
- [ ] No N+1 query patterns

### 🎯 Repository Standards

#### CLI Standards

- [ ] Commands support `--help`
- [ ] Help text is clear and actionable
- [ ] Options named consistently
- [ ] Validation provides user-friendly errors
- [ ] Cross-platform compatible

#### Error Handling

- [ ] All API calls wrapped in error handling
- [ ] Network errors caught
- [ ] NOT_FOUND returns `ExitCodes.NOT_FOUND`
- [ ] INVALID_INPUT returns `ExitCodes.INVALID_INPUT`
- [ ] PERMISSION errors return `ExitCodes.PERMISSION_DENIED`
- [ ] Errors sent to stderr
- [ ] No stack traces shown to users

#### Configuration & State

- [ ] Configuration via `config.py`
- [ ] No hardcoded URLs/endpoints
- [ ] Credentials via keyring (no plain text)
- [ ] Environment variables documented
- [ ] Backward compatibility maintained

#### Dependency Management

- [ ] No unnecessary new dependencies
- [ ] `pyproject.toml` updated if needed
- [ ] Poetry lock file updated
- [ ] Dependencies actively maintained

### 🔐 Safety & Security

- [ ] No credentials, keys, or secrets hardcoded
- [ ] No secrets in commit history
- [ ] Input validation prevents injection
- [ ] Parameterized queries used
- [ ] Resource deletion safe (exact-match verification)
- [ ] Dry-run mode available for destructive ops
- [ ] Audit logging for critical operations

### 📊 Test Results & Metrics

```bash
# Run all checks
poetry run ni-python-styleguide lint
poetry run black .
poetry run mypy slcli tests
poetry run pytest tests/unit -q
poetry run pytest tests/e2e/ -n auto --timeout=300
```

- [ ] Linting: **PASS** ✓
- [ ] Type checking: **PASS** ✓
- [ ] Unit tests: **PASS** ✓
- [ ] E2E tests: **PASS** ✓
- [ ] Coverage: ≥ 80% for new code
- [ ] Build succeeds: `poetry run build-pyinstaller`

### 📚 Documentation Review

- [ ] README examples accurate
- [ ] CLI help text complete
- [ ] Complex features documented
- [ ] Architecture decisions documented
- [ ] API behavior documented
- [ ] Configuration documented
- [ ] Troubleshooting section if applicable

### ✅ Approval Checklist

Before approving:

1. **All Critical Checks Pass:**

   - [ ] All tests passing (unit + E2E)
   - [ ] Linting passes
   - [ ] Type checking passes
   - [ ] No security issues

2. **All High-Priority Standards Met:**

   - [ ] Appropriate test coverage (≥80%)
   - [ ] No code duplication
   - [ ] Architecture patterns followed
   - [ ] Repository standards met

3. **Review Feedback:**

   - [ ] All comments addressed
   - [ ] Changes make sense
   - [ ] No unresolved discussions

4. **Final Validation:**
   - [ ] Tested locally
   - [ ] Edge cases considered
   - [ ] Cross-platform compatible
   - [ ] No unintended side effects

---

## ⌨️ Command Reference

### Pre-Submission Validation

```bash
# Quick test
poetry run pytest tests/unit -q

# Full validation
poetry run ni-python-styleguide lint && \
poetry run black . && \
poetry run mypy slcli tests && \
poetry run pytest tests/unit -q && \
poetry run pytest tests/e2e/ -n auto --timeout=300
```

### Quality Gates

```bash
# Linting
poetry run ni-python-styleguide lint

# Type checking
poetry run mypy slcli tests

# Unit tests
poetry run pytest tests/unit -q

# E2E tests (parallel)
poetry run pytest tests/e2e/ -n auto --timeout=300

# Full suite
poetry run pytest
```

### Detailed Analysis

```bash
# Coverage report
poetry run pytest --cov=slcli tests/unit --cov-report=html:htmlcov

# Verbose output
poetry run pytest tests/unit -v

# Specific test
poetry run pytest tests/unit/test_workflow_click.py::test_list_workflows -v

# Test discovery
poetry run pytest tests/unit --collect-only
```

### Module-Specific

```bash
# CLI tests
poetry run pytest tests/unit/test_*_click.py -v

# API tests
poetry run pytest tests/unit/test_example_provisioner.py -v

# Configuration tests
poetry run pytest tests/unit/test_config.py -v
```

### Debugging

```bash
# Single test with details
poetry run pytest tests/unit/test_*.py::test_name -v -s

# With debugger
poetry run pytest tests/unit/test_*.py::test_name -v -s --pdb

# Long traceback
poetry run pytest tests/unit/test_*.py::test_name -v --tb=long

# Type hint validation
poetry run mypy slcli/module.py
```

### Build & Install

```bash
# Build binary
poetry run build-pyinstaller

# Install locally
poetry install

# Update dependencies
poetry lock
```

---

## 📚 Standards Reference

### Key Repository Standards

**Framework & Tools:**

- CLI Framework: **Click** (not Typer)
- Testing: **pytest** (unit + E2E in parallel)
- Linting: **ni-python-styleguide** (PEP8)
- Type Checking: **mypy** (strict)
- Formatting: **black** (100 char limit)
- Dependencies: **Poetry**

**Code Organization:**

- API utilities: `utils.py`
- CLI utilities: `cli_utils.py`
- Response handling: `universal_handlers.py`
- Table formatting: `table_utils.py`
- Command modules: `*_click.py`

**CLI Standards:**

- List commands: Support `--format/-f` (table/json)
- Help text: Clear and actionable
- Error messages: User-friendly (not stack traces)
- Exit codes: Use `ExitCodes` enum
- Pagination: 25 items per page (table only)
- JSON: All results (no pagination)

**API Integration Standards:**

- Queries: **Parameterized** (not string interpolation)
- Verification: Exact-match after query
- Error handling: Use `handle_api_error()`
- Success messages: Use `format_success()`
- Dry-run: Where applicable

**Documentation:**

- Docstrings: Google format
- README: Updated for new features
- Help text: Complete and accurate
- Type hints: Complete (no loose Any)

### Exit Codes

```python
SUCCESS = 0              # Successful operation
GENERAL_ERROR = 1       # Generic error
INVALID_INPUT = 2       # Invalid user input
NOT_FOUND = 3          # Resource not found
PERMISSION_DENIED = 4  # Permission/auth error
NETWORK_ERROR = 5      # Network/connectivity error
```

### Common Patterns

**Error Handling:**

```python
try:
    resp = make_api_request("GET", url)
except Exception as exc:
    handle_api_error(exc)  # Exits with appropriate code
```

**Success Messages:**

```python
format_success("Workspace created", {"id": ws_id, "name": ws_name})
# Output: ✓ Workspace created
```

**Response Handler:**

```python
UniversalResponseHandler.handle_list_response(
    resp=resp, data_key="workspaces", item_name="workspace",
    format_output=format_output, formatter_func=workspace_formatter,
    headers=["Name", "ID"], column_widths=[30, 36],
    enable_pagination=True, page_size=take
)
```

### Command Registration

```python
def register_workspace_commands(cli: Any) -> None:
    @cli.group()
    def workspace() -> None: ...

    @workspace.command(name="list")
    @click.option("--format", "-f", type=click.Choice(["table", "json"]), default="table")
    @click.option("--take", "-t", type=int, default=25, show_default=True)
    def list_workspaces(format: str, take: int) -> None: ...
```

---

## 📖 Related Documentation

- **Development Guidelines:** [`copilot-instructions.md`](copilot-instructions.md)
- **Contributing Guide:** [`../CONTRIBUTING.md`](../CONTRIBUTING.md)
- **Architecture Guide:** [`../docs/EXAMPLE_ARCHITECTURE.md`](../docs/EXAMPLE_ARCHITECTURE.md)
- **Resource Model:** [`../docs/RESOURCE_MODEL.md`](../docs/RESOURCE_MODEL.md)
- **Changelog:** [`../CHANGELOG.md`](../CHANGELOG.md)

---

## 🚦 Status

**Created:** December 19, 2025  
**Version:** 1.0  
**Status:** Active & Ready for Use

**Components:**

- ✅ This guide (AGENTS.md)
- ✅ Slash command (`.github/prompts/pr-review.prompt.md`)
- ✅ Development guidelines (`copilot-instructions.md`)
- ✅ Contributing guide (`CONTRIBUTING.md`)

---

## 💡 Pro Tips for Agents

1. **Start with slash command** - Use `/slcli-pr-review [type]` for structured prompts
2. **Use appropriate review type** - Not all PRs need full review
3. **Run commands in order** - Build up validation confidence
4. **Be specific in feedback** - Cite line numbers and examples
5. **Document your reasoning** - Explain why something doesn't meet standards
6. **Verify locally** - Always run checks yourself, don't just review visually
7. **Keep standards consistent** - All PRs held to same high bar
8. **Help developers improve** - Provide guidance, not just criticism

---

## ❓ Quick Reference

| I need to...        | Use...           | Command...                      |
| ------------------- | ---------------- | ------------------------------- |
| Review a PR         | Slash command    | `/slcli-pr-review`              |
| Review CLI changes  | CLI review type  | `/slcli-pr-review cli`          |
| Review API changes  | API review type  | `/slcli-pr-review api`          |
| Check test coverage | Coverage command | `poetry run pytest --cov`       |
| Debug failing test  | Debug command    | `poetry run pytest -v -s --pdb` |
| Validate all checks | Full validation  | See "Pre-Submission Validation" |
| Check standards     | This document    | Section "Standards Reference"   |

---

**Ready to review?** Use the slash command `/slcli-pr-review` and follow the checklist. You've got this! 🚀
