# SystemLink CLI

> **[Full documentation →](https://ni-kismet.github.io/systemlink-cli/)**

SystemLink CLI (`slcli`) is a cross-platform Python CLI for SystemLink integrators, providing comprehensive management of SystemLink resources via REST APIs.

## Features

- **20+ resource types** — test results, assets, systems, specifications, work items, notebooks, feeds, tags, files, users, policies, webapps, and more
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

# Create and update specification data with limits and conditions
slcli spec create --product <product> --spec-id VSAT01 --type PARAMETRIC --limit-min 1.2 --limit-max 1.8 \
	--condition '{"name":"Temperature","value":{"conditionType":"NUMERIC","discrete":[25,85],"unit":"C"}}'
slcli spec update --id <spec-id> --version 0 --limit-typical 1.5

# Bulk import create-compatible specs; omitted workspace inherits from the referenced product
slcli spec import --file docs/examples/specifications/import-specs.json

# Compare software and assets between two systems
slcli system compare "PXI Controller A" "PXI Controller B"
slcli system compare sys-id-1 sys-id-2 -f json

# Scaffold the SystemLink Angular starter (AI skills auto-installed)
slcli webapp init ./my-dashboard
# Open the project and follow START_HERE.md or PROMPTS.md

# List and export a hosted dashboard by UID
slcli dashboard list -f table
slcli dashboard export system-health -o system-health.json

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
