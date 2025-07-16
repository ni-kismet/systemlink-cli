# SystemLink CLI

SystemLink CLI (`slcli`) is a cross-platform Python CLI for SystemLink integrators, supporting test plan templates and workflow management via SystemLink REST APIs.

## Features

- Secure credential storage using [keyring](https://github.com/jaraco/keyring)
- Manage SystemLink test plan templates (list, export, import, delete)
- Extensible for additional SystemLink resource types
- User-friendly CLI with help and validation
- Easily packaged as a single binary with PyInstaller
- Full test suite with CI/CD

## Setup

1. **Install Poetry** (if not already installed):

   ```bash
   pip install poetry
   ```

2. **Install dependencies:**

   ```bash
   poetry install
   ```

## Running

- Run the CLI directly:

  ```bash
  poetry run slcli
  ```

- Or as a Python module:
  ```bash
  poetry run python -m slcli
  ```

## Build a Standalone Binary (Cross-Platform)

### macOS/Linux (Homebrew/PyInstaller)

To build a single-file executable and Homebrew formula:

```bash
poetry run python scripts/build_homebrew.py
```

- This will:
  - Build the PyInstaller binary in `dist/slcli/`
  - Create a tarball `dist/slcli.tar.gz`
  - Generate a Homebrew formula `dist/homebrew-slcli.rb` with the correct SHA256

You can then install locally with:

```bash
brew install ./dist/homebrew-slcli.rb
```

### Windows (Scoop/PyInstaller)

To build a Windows executable and Scoop manifest:

```powershell
poetry run python scripts/build_pyinstaller.py
poetry run python scripts/build_scoop.py
```

- This will:
  - Build `dist/slcli.exe`
  - Generate a Scoop manifest `dist/scoop-slcli.json` with the correct SHA256

You can use the manifest in your own Scoop bucket for easy installation.

### CI/CD Automation

- All builds, tests, and packaging are automated via GitHub Actions for both Homebrew and Scoop.
- Artifacts (`slcli.tar.gz`, `homebrew-slcli.rb`, `slcli.exe`, `scoop-slcli.json`) are uploaded for each build.

## Testing & Linting

- Run tests:
  ```bash
  poetry run pytest
  ```
- Lint code:
  ```bash
  poetry run ni-python-styleguide lint
  ```

## Contributing

See [the NI Python development wiki](https://dev.azure.com/ni/DevCentral/_wiki/wikis/AppCentral.wiki/?pagePath=/Tools/Python/Tutorials/Making-a-change-to-an-existing-project) for contribution guidelines.

## Notebook Management

The `notebook` command group allows you to manage Jupyter notebooks in SystemLink.

### List all notebooks in a workspace

```bash
slcli notebook list
slcli notebook list --workspace MyWorkspace
```

### Download notebook content and/or metadata

```bash

# Download notebook content (.ipynb):
slcli notebook download --id <notebook_id> --output mynotebook.ipynb
slcli notebook download --name MyNotebook --output mynotebook.ipynb


# Download notebook metadata as JSON:
slcli notebook download --id <notebook_id> --type metadata --output metadata.json
slcli notebook download --name MyNotebook --type metadata --output metadata.json


# Download both content and metadata:
slcli notebook download --id <notebook_id> --type both --output mynotebook.ipynb
```

### Create a new notebook

```bash

# Create from file:
slcli notebook create --file mynotebook.ipynb --name MyNotebook
slcli notebook create --file mynotebook.ipynb --workspace MyWorkspace --name MyNotebook


# Create an empty notebook:
slcli notebook create --name MyNotebook
slcli notebook create --workspace MyWorkspace --name MyNotebook
```

### Update notebook metadata and/or content

```bash

# Update metadata only:
slcli notebook update --id <notebook_id> --metadata metadata.json


# Update content only:
slcli notebook update --id <notebook_id> --content mynotebook.ipynb


# Update both:
slcli notebook update --id <notebook_id> --metadata metadata.json --content mynotebook.ipynb
```
