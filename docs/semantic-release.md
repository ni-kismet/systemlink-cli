# Semantic Release Setup

This project uses [Python Semantic Release](https://python-semantic-release.readthedocs.io/) for automated version management and releases.

## How It Works

1. **Conventional Commits**: Use conventional commit messages to automatically determine version bumps
2. **Automated Releases**: On push to `main`, the semantic release workflow analyzes commits and creates releases
3. **Version Management**: Automatically updates version in `pyproject.toml` and generates `_version.py`
4. **Changelog**: Automatically generates and updates `CHANGELOG.md`

## Commit Message Format

Use conventional commit format:

```
<type>[optional scope]: <description>

[optional body]

[optional footer(s)]
```

### Types

- `feat`: A new feature (triggers minor version bump)
- `fix`: A bug fix (triggers patch version bump)
- `docs`: Documentation only changes
- `style`: Changes that do not affect the meaning of the code
- `refactor`: A code change that neither fixes a bug nor adds a feature
- `perf`: A code change that improves performance (triggers patch version bump)
- `test`: Adding missing tests or correcting existing tests
- `build`: Changes that affect the build system or external dependencies
- `ci`: Changes to CI configuration files and scripts
- `chore`: Other changes that don't modify src or test files

### Examples

```bash
# Patch release (0.3.1 -> 0.3.2)
git commit -m "fix: handle permission errors gracefully in workspace info"

# Minor release (0.3.1 -> 0.4.0)
git commit -m "feat: add new version command"

# Major release (0.3.1 -> 1.0.0) - requires BREAKING CHANGE footer
git commit -m "feat: redesign API structure

BREAKING CHANGE: API endpoints have been restructured"
```

## Workflows

### Semantic Release Workflow
- **File**: `.github/workflows/semantic-release.yml`
- **Trigger**: Push to `main` branch
- **Actions**: Analyzes commits, bumps version, creates tags, generates changelog

### Release Build Workflow
- **File**: `.github/workflows/release.yml`
- **Trigger**: New tags created by semantic release
- **Actions**: Builds binaries for all platforms, creates GitHub releases

## Manual Commands

```bash
# Dry run to see what would happen
poetry run semantic-release version --noop

# Generate changelog only
poetry run semantic-release changelog

# Manual version bump (for testing)
poetry run semantic-release version

# Update version file manually
poetry run update-version
```

## Configuration

Semantic release configuration is in `pyproject.toml` under `[tool.semantic_release]`:

- Version files: `pyproject.toml` and `slcli/_version.py`
- Build command: Runs `update-version` script to sync version files
- Branch: `main`
- Upload to PyPI: Disabled
- Upload to GitHub Releases: Enabled
- Changelog: Generated in `CHANGELOG.md`
