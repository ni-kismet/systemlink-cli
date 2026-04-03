# SystemLink CLI

> **[Full documentation →](https://ni-kismet.github.io/systemlink-cli/)**

SystemLink CLI (`slcli`) is a cross-platform Python CLI for SystemLink integrators, providing comprehensive management of SystemLink resources via REST APIs.

## Features

- **20+ resource types** — test results, assets, systems, work items, notebooks, feeds, tags, files, users, policies, webapps, and more
- **Multi-platform** — supports SystemLink Enterprise (SLE) and SystemLink Server (SLS) with automatic detection
- **Multi-profile** — manage dev, staging, and prod environments with named profiles
- **AI agent skills** — installable skills for most AI agents (Copilot, Codex, etc.) and Claude — including a webapp skill for building Nimble Angular dashboards
- **Demo provisioning** — curated example datasets for training, demos, and evaluation
- **WebApp lifecycle** — scaffold Nimble Angular projects, pack, publish, and manage web applications
- **Professional CLI** — consistent error handling, colored table/JSON output, shell completion

## Quick Install

```bash
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

# pip (Python 3.11+)
pip install systemlink-cli

# Command name after install
slcli --help
```

## Quick Start

```bash
# Authenticate
slcli login

# Explore resources
slcli testmonitor result list --summary --group-by status
slcli asset list --calibratable --summary
slcli system list --state CONNECTED

# Scaffold the SystemLink Angular starter (AI skills auto-installed)
slcli webapp init ./my-dashboard
# Open the project and follow START_HERE.md or PROMPTS.md

# Or install AI skills manually (use --client claude for Claude)
slcli skill install

# Provision a demo environment
slcli example install demo-complete-workflow --workspace Training
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
