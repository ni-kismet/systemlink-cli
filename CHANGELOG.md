# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Semantic release automation for version management
- Automated version bumping based on conventional commits
- Enhanced version command that works in both development and built environments
- Graceful error handling for workspace permission errors

### Changed

- Version command now reads from auto-generated `_version.py` in built binaries
- Build process now automatically generates version file during packaging

### Fixed

- Version command now works correctly in PyInstaller-built binaries
- Workspace info command handles permission errors gracefully instead of crashing

## [0.3.1] - 2025-01-XX

### Added

- SystemLink Integrator CLI for managing workflows, templates, notebooks, and workspaces
- Cross-platform support (Windows, macOS, Linux)
- Authentication via API keys stored in system keyring
- JSON and table output formats for list commands
- Comprehensive error handling with user-friendly messages

### Features

- **Workspace Management**: List, disable, and get detailed workspace information
- **Template Management**: List and manage test plan templates
- **Workflow Management**: List and manage SystemLink workflows
- **Notebook Management**: Create, download, delete, and list Jupyter notebooks
- **Authentication**: Secure login/logout with API key storage
