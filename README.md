# SystemLink CLI

> **[Full documentation →](https://ni-kismet.github.io/systemlink-cli/)**

SystemLink CLI (`slcli`) is a cross-platform Python CLI for SystemLink integrators, providing comprehensive management of SystemLink resources via REST APIs.

## Features

- **20+ resource types** — test results, assets, systems, specifications, work items, notebooks, feeds, tags, files, users, policies, webapps, and more
- **Systems state lifecycle** — list saved states, inspect versions, and import or export portable `.sls` content
- **Multi-platform** — supports SystemLink Enterprise (SLE) and SystemLink Server (SLS) with automatic detection
- **Multi-profile** — manage dev, staging, and prod environments with named profiles
- **AI agent skills** — installable skills for most AI agents (Copilot, Codex, etc.) and Claude — including a webapp skill for building Nimble Angular dashboards
- **Demo provisioning** — curated example datasets for training, demos, and evaluation
- **WebApp lifecycle** — scaffold Nimble Angular projects, pack, publish, and manage web applications
- **Professional CLI** — consistent error handling, colored table/JSON output, shell completion

## Quick Install

```bash
# pipx (recommended cross-platform Python install)
pipx install systemlink-cli

# Verify the CLI is on your PATH
slcli --help

# macOS / Linux (Homebrew — https://brew.sh)
brew tap ni-kismet/homebrew-ni && brew install slcli

# Windows (Scoop — https://scoop.sh)
scoop bucket add ni-kismet https://github.com/ni-kismet/scoop-ni && scoop install slcli

# Standalone binary — macOS (no package manager needed)
curl -fsSL https://github.com/ni-kismet/systemlink-cli/releases/latest/download/slcli-macos.tar.gz | tar xz
sudo mv slcli/slcli /usr/local/bin/

# Standalone binary — Linux
curl -fsSL https://github.com/ni-kismet/systemlink-cli/releases/latest/download/slcli-linux.tar.gz | tar xz
sudo mv slcli/slcli /usr/local/bin/

# pip (fallback for virtualenvs, CI, or managed Python workflows)
pip install systemlink-cli
```

## Quick Start

```bash
# Authenticate
slcli login

# Explore resources
slcli testmonitor result list --summary --group-by status
slcli asset list --calibratable --summary
slcli system list --state CONNECTED
slcli spec list --product <product> --workspace all
slcli state list --workspace all --format json

# Inspect and export saved software states
slcli state get <state-id>
slcli state history <state-id>
slcli state export <state-id> --output saved-state.sls


# Scaffold the SystemLink Angular starter (AI skills auto-installed)
slcli webapp init ./my-dashboard
# Open the project and follow START_HERE.md or PROMPTS.md

# Create Plugin Manager packaging config
slcli webapp manifest init ./my-dashboard \
	--description "A dashboard for monitoring fleet health and calibration status." \
	--section Dashboard \
	--maintainer "Your Name <you@example.com>" \
	--license MIT \
	--icon-file ./icon.svg

# Package the app and generate the thin submission manifest.json
slcli webapp pack --config ./my-dashboard/nipkg.config.json

# Or install AI skills manually (use --client claude for Claude)
slcli skill install

# Provision a demo environment
slcli example install demo-complete-workflow --workspace Training
```

## Color Output

slcli auto-detects terminal color support for tables, status lines, and JSON output.

- `SLCLI_COLOR=always` forces color when you want ANSI output even through wrappers or pseudo-terminals.
- `SLCLI_COLOR=never` disables Rich color output explicitly.
- `NO_COLOR=1` also disables color output and takes precedence over auto-detection.

## States

The `state` command group manages software states stored by the SystemLink Systems State service.

```bash
# Discover saved states
slcli state list --workspace all
slcli state get <state-id>
slcli state version <state-id> <version>

# Create or update package/feed states
slcli state create --name "DAQmx 19.5" --distribution WINDOWS --architecture X64 \
	--package '{"name":"ni-daqmx","version":"19.5.0.49152-0+f0"}'
slcli state update <state-id> --description "Validated for production"

# Import, export, or capture .sls content
slcli state import --name "Golden Image" --distribution NI_LINUXRT --architecture ARM --file golden.sls
slcli state replace-content <state-id> --file updated.sls --change-description "Refresh package set"
slcli state export <state-id> --output saved-state.sls
slcli state capture <system-id> --output captured-state.sls

# Inspect history and revert
slcli state history <state-id>
slcli state revert <state-id> <version> --yes
```

## Documentation

| Section                                                                            | Description                                                |
| ---------------------------------------------------------------------------------- | ---------------------------------------------------------- |
| [Getting Started](https://ni-kismet.github.io/systemlink-cli/getting-started.html) | Installation, authentication, profiles, AI integration     |
| [Command Reference](https://ni-kismet.github.io/systemlink-cli/commands.html)      | Complete docs for all command groups and options           |
| [Workflows](https://ni-kismet.github.io/systemlink-cli/workflows.html)             | Building webapps with AI, demo provisioning, multi-env ops |

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, coding standards, and contribution guidelines.

## License

MIT
