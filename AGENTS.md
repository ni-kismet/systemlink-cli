# Agent Guide for SystemLink CLI

These instructions apply to the entire repository. Read `CONTRIBUTING.md` for
the complete contributor requirements and use nearby code and tests as the
source of truth for established implementation patterns.

## Project

SystemLink CLI (`slcli`) is a cross-platform Python CLI for NI SystemLink. It
uses Click, Poetry, requests, keyring, and pytest. Command modules live in
`slcli/*_click.py` and are registered in `slcli/main.py`.

## Working in the Repository

- Start from the command, test, or helper that directly owns the requested
  behavior. Prefer existing local patterns over new abstractions.
- Keep changes focused. Preserve unrelated work in a dirty worktree and never
  revert changes you did not make.
- Give every function complete type annotations and use Google-style docstrings
  for public functions and classes.
- Use Click for CLI interfaces. Keep help text, option names, output formats,
  and exit behavior consistent with neighboring commands.
- Use `make_api_request`, `handle_api_error`, `format_success`, and `ExitCodes`
  where their existing responsibilities apply.
- Parameterize API filters; do not interpolate user input into query strings.
- Keep all supported environments in mind: Windows, macOS, and Linux.

## List Commands

- Support table and JSON output through `--format/-f`.
- Use `--take/-t` with the established default when results are paginated.
- Paginate human-readable table output. Return the complete requested result
  set for JSON output without interactive prompts.
- Render empty JSON results as `[]` and give table users a concise empty-state
  message.

## Tests and Validation

- Add or update focused unit tests for changed behavior, including relevant
  error paths.
- Run the narrowest relevant test immediately after the first implementation
  change, then complete the repository checks before finishing:

  ```bash
  poetry run black .
  poetry run ni-python-styleguide lint
  poetry run mypy slcli tests
  poetry run pytest tests/unit -q
  poetry run pytest
  ```

- Run E2E tests when a change affects live API workflows or integration
  behavior; follow `tests/e2e/README.md` for setup.

## Documentation

- Treat `README.md` as a succinct project overview. Update it only when project
  positioning, installation, quick-start workflows, or documentation navigation
  changes.
- Put detailed command and subcommand documentation in `site/commands.html` or
  the relevant docs-site page. Do not add every command to the README.
- Keep Click help and docstrings accurate whenever behavior changes.
- Add a Towncrier fragment under `newsfragments/` for each pull request, using
  the release-impact type described in `CONTRIBUTING.md`.

## Reviews and Pull Requests

- Use `.github/prompts/pr-review.prompt.md` for the repository's detailed review
  workflow and standards checklist.
- Use `.github/prompts/pr-create.prompt.md` when preparing a pull request.
