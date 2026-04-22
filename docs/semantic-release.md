# Towncrier Release Setup

This project uses [Towncrier](https://towncrier.readthedocs.io/) plus a small release helper script for changelog-driven version management and releases.

## How It Works

1. **Towncrier Fragments**: Every pull request adds a fragment in `newsfragments/`
2. **Automated Releases**: On push to `main`, the release workflow inspects fragments and computes the next version
3. **Version Management**: The release helper updates `pyproject.toml` and generates `slcli/_version.py`
4. **Changelog**: Towncrier composes and prepends the new release notes to `CHANGELOG.md`

## Fragment Format

Use a Towncrier fragment named after the PR or issue number:

```
poetry run towncrier create 123.patch.md --content "Prefer the new systems search endpoint with fallback."
```

Fragment types map to version bumps as follows:

- `major`: Breaking changes, triggers a major version bump
- `minor`: New features, triggers a minor version bump
- `patch`: Fixes and shipped behavior changes, triggers a patch version bump
- `doc`: Documentation changes, triggers a patch version bump
- `misc`: Other shipped changes, triggers a patch version bump

### Examples

```bash
# Patch release (1.9.3 -> 1.9.4)
poetry run towncrier create 123.patch.md --content "Handle permission errors gracefully in workspace info."

# Minor release (1.9.3 -> 1.10.0)
poetry run towncrier create 124.minor.md --content "Add a new version command."

# Major release (1.9.3 -> 2.0.0)
poetry run towncrier create 125.major.md --content "Redesign the public API surface for system queries."
```

## Workflows

### Towncrier Release Workflow

- **File**: `.github/workflows/semantic-release.yml`
- **Trigger**: Push to `main` branch
- **Actions**: Checks `newsfragments/`, computes the next version, updates version files, builds `CHANGELOG.md`, commits, and tags the release

### Release Build Workflow

- **File**: `.github/workflows/release.yml`
- **Trigger**: New tags created by the Towncrier release workflow
- **Actions**: Builds binaries for all platforms, creates GitHub releases

## Manual Commands

```bash
# Check that the branch includes a fragment
poetry run towncrier check

# Print the next version without changing the repo
poetry run python scripts/towncrier_release.py --next-version

# Preview rendered release notes without writing files
poetry run towncrier build --draft --version 1.10.0

# Apply the release locally (updates versions and CHANGELOG.md)
poetry run python scripts/towncrier_release.py --apply

# Update version file manually from pyproject.toml
poetry run update-version
```

## Configuration

Towncrier configuration is in `pyproject.toml` under `[tool.towncrier]`:

- Fragment directory: `newsfragments/`
- Release files updated automatically: `pyproject.toml`, `slcli/_version.py`, and `CHANGELOG.md`
- Release helper: `scripts/towncrier_release.py`
- Branch: `main`
- Changelog: Generated in `CHANGELOG.md`
