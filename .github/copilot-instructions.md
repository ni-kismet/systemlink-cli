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

## Required Actions After Any Change

- Run `poetry run ni-python-styleguide lint` to check for linting and style issues.
- Run `poetry run black .` to auto-format code to the configured line length (100).
- Run `poetry run pytest` to ensure all tests pass.
- If adding or modifying CLI commands, update the `README.md` usage examples if needed.
- If adding dependencies, update `pyproject.toml` and run `poetry lock`.
- If changing packaging or build scripts, verify `poetry run build-pyinstaller` works and produces a binary in `dist/`.

## Pull Request/Commit Requirements

- All code must pass CI (lint, test, build) before merging.
- All new features must be documented in `README.md`.
- All code must be reviewed by at least one other developer.

## Copilot-Specific Instructions

- After making any code change, always:
  1. Run linting and auto-formatting.
  2. Run all unit tests.
  3. Report any failures or issues to the user.
- If you add a new CLI command, ensure it is covered by a unit test in `tests/unit/`.
- If you update the CLI interface, update the `README.md` accordingly.
- Never commit or suggest committing files listed in `.gitignore`.

---

These guidelines ensure code quality, maintainability, and a smooth developer experience for all contributors and Copilot.
