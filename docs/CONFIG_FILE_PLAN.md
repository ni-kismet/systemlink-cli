# Configuration File Migration Plan

## Overview

Migrate from keyring-based credential storage to an AWS CLI-style configuration file approach, enabling multi-profile support for dev/test/prod environments with optional default workspace filtering.

## Current State

### Authentication Storage
- **Location**: System keyring via `keyring` library
- **Service name**: `systemlink-cli`
- **Keys stored**:
  - `SYSTEMLINK_API_KEY` - API key
  - `SYSTEMLINK_API_URL` - API base URL  
  - `SYSTEMLINK_CONFIG` - Combined JSON config (api_url, api_key, web_url, platform)
- **Environment overrides**: `SYSTEMLINK_API_URL`, `SYSTEMLINK_API_KEY`, `SYSTEMLINK_WEB_URL`

### Files Affected
- `slcli/main.py` - login/logout commands
- `slcli/utils.py` - `get_base_url()`, `get_http_configuration()`, `get_web_url()`, `_get_keyring_config()`
- `slcli/platform.py` - Platform detection
- Most `*_click.py` files - Use workspace filtering

---

## Proposed Design

### Configuration File Location

```
~/.config/slcli/config.json
```

Following XDG Base Directory spec (already used for `config.json` in `config.py`).

### Configuration File Format (JSON)

```json
{
  "current-profile": "dev",
  "profiles": {
    "dev": {
      "server": "https://dev-api.lifecyclesolutions.ni.com",
      "web-url": "https://dev.lifecyclesolutions.ni.com",
      "api-key": "dev-api-key-here",
      "platform": "SLE",
      "workspace": "Development"
    },
    "test": {
      "server": "https://test-api.example.com",
      "web-url": "https://test.example.com",
      "api-key": "test-api-key-here"
    },
    "prod": {
      "server": "https://prod-api.example.com",
      "web-url": "https://prod.example.com",
      "api-key": "prod-api-key-here"
    }
  }
}
```

**Note**: Using JSON format to avoid adding PyYAML dependency.

---

## CLI Commands

### Profile Management Commands

```bash
# List all profiles (show current with asterisk)
slcli config list-profiles
# Output:
#   CURRENT   NAME    SERVER                                     WORKSPACE
#   *         dev     https://dev-api.lifecyclesolutions.ni.com  Development
#             test    https://test-api.example.com               -
#             prod    https://prod-api.example.com               -

# Show current profile
slcli config current-profile

# Switch profile
slcli config use-profile test

# View full config
slcli config view
slcli config view --format json

# Set specific values
slcli config set profiles.dev.workspace "My Workspace"
slcli config set current-profile prod

# Unset values
slcli config unset profiles.dev.workspace

# Delete a profile
slcli config delete-profile test
```

### Modified Login Command

```bash
# Interactive login (creates or updates profile)
slcli login
# Prompts for:
#   Profile name: [default]
#   API URL: [https://demo-api.lifecyclesolutions.ni.com]
#   API Key: ****
#   Web URL: [https://demo.lifecyclesolutions.ni.com]
#   Default workspace (optional): []
#   Set as current profile? [Y/n]

# Non-interactive with profile name
slcli login --profile prod --url https://prod-api.example.com --api-key xxx

# Update existing profile
slcli login --profile dev --workspace "New Default Workspace"

# Shorthand
slcli login -p prod --url https://prod-api.example.com --api-key xxx
```

### Logout Command

```bash
# Remove a specific profile
slcli logout --profile dev
slcli logout -p dev

# Remove current profile
slcli logout

# Remove all profiles (with confirmation)
slcli logout --all
```

### Runtime Profile Override

```bash
# Override profile for single command
slcli --profile prod workspace list
slcli -p prod workspace list

# Environment variable override (highest priority)
SLCLI_PROFILE=prod slcli workspace list

# Legacy env vars still work for backwards compatibility
SYSTEMLINK_API_URL=... SYSTEMLINK_API_KEY=... slcli workspace list
```

---

## Default Workspace Behavior

### How It Works

1. **Profile has default workspace**: Commands filter by that workspace automatically
2. **Profile has no default workspace**: Commands show all workspaces (current behavior)
3. **User specifies `--workspace`**: Overrides profile default
4. **User specifies `--all-workspaces`**: Ignores profile default, shows all

### Command Changes

All list commands get a new `--all-workspaces` / `-A` flag:

```bash
# Uses profile default workspace
slcli workflow list

# Override with specific workspace
slcli workflow list --workspace "Production"

# Show all workspaces (ignore profile default)
slcli workflow list --all-workspaces
slcli workflow list -A
```

### Affected Commands

Commands that currently support `--workspace` filtering:
- `slcli customfield list`
- `slcli workflow list`
- `slcli template list`
- `slcli notebook list`
- `slcli file list`
- `slcli feed list`
- `slcli webapp list`
- `slcli tag list`

---

## Implementation Phases

### Phase 1: Core Config Infrastructure (Week 1)

1. **Create `slcli/profiles.py`** - New profile management module
   - `ProfileConfig` class - Load/save/validate config
   - `Profile` dataclass - Profile definition
   - `get_current_profile()` - Get active profile
   - `get_profile(name)` - Get specific profile
   - `set_current_profile(name)` - Switch profile
   - Migration from keyring to config file

2. **Add config commands** in `slcli/config_click.py`
   - `slcli config list-profiles`
   - `slcli config current-profile`
   - `slcli config use-profile <name>`
   - `slcli config view`
   - `slcli config set <key> <value>`
   - `slcli config unset <key>`
   - `slcli config delete-profile <name>`

3. **Update `slcli/utils.py`**
   - Modify `get_base_url()` to use new config
   - Modify `get_http_configuration()` to use new config
   - Modify `get_web_url()` to use new config
   - Keep environment variable overrides
   - Add `get_default_workspace()` function

### Phase 2: Update Login/Logout (Week 1-2)

1. **Modify `slcli login`**
   - Add `--profile` / `-p` option
   - Add `--workspace` option (default workspace)
   - Interactive profile naming
   - Write to config file instead of keyring

2. **Modify `slcli logout`**
   - Add `--profile` / `-p` option
   - Add `--all` option
   - Remove from config file

3. **Add migration command**
   - `slcli config migrate` - Migrate keyring credentials to config file
   - Auto-detect and offer migration on first use

### Phase 3: Default Workspace Support (Week 2)

1. **Add `--all-workspaces` flag** to all list commands
   - Create shared decorator or utility
   - Update all `*_click.py` modules

2. **Update workspace filtering logic**
   - Check for profile default workspace
   - Respect `--all-workspaces` flag
   - Respect explicit `--workspace` override

3. **Update `slcli info` command**
   - Show current profile name
   - Show default workspace (if set)

### Phase 4: Documentation & Testing (Week 2-3)

1. **Update documentation**
   - README.md - New authentication section
   - Add docs/PROFILES.md guide
   - Update CLI help text

2. **Add tests**
   - Unit tests for profiles module
   - Unit tests for profile switching
   - Integration tests for workspace filtering
   - Migration tests

3. **Backwards compatibility testing**
   - Environment variable overrides still work
   - Graceful handling of missing config file

---

## File Changes Summary

### New Files
- `slcli/profiles.py` - New profile management module
- `slcli/config_click.py` - Config CLI commands
- `docs/PROFILES.md` - Documentation
- `tests/unit/test_profiles.py` - Tests

### Modified Files
- `slcli/main.py` - Login/logout commands, add --profile to CLI group
- `slcli/utils.py` - Credential retrieval functions
- `slcli/cli_utils.py` - Add workspace filtering helpers
- All `*_click.py` files - Add --all-workspaces flag
- `README.md` - Update authentication docs
- `.github/copilot-instructions.md` - Update guidelines

---

## Security Considerations

### Config File Permissions
```python
# Set restrictive permissions on config file (600 - owner read/write only)
import os
import stat
config_path.chmod(stat.S_IRUSR | stat.S_IWUSR)
```

### Sensitive Data Warning
- Config file contains API keys in plain text
- Document this clearly in help text
- Consider optional keyring integration for API keys only
- Add warning if file permissions are too open

### Migration Security
- Offer to delete keyring entries after migration
- Don't leave credentials in both places

---

## Backwards Compatibility

### Environment Variables (Highest Priority)
```python
# Always check env vars first
SYSTEMLINK_API_URL  # Override API URL
SYSTEMLINK_API_KEY  # Override API key  
SYSTEMLINK_WEB_URL  # Override web URL
SLCLI_PROFILE       # Override profile selection
```

### Keyring Fallback
```python
# If config file doesn't exist, check keyring (migration period)
def get_base_url():
    # 1. Environment variable
    # 2. Config file (new)
    # 3. Keyring (legacy fallback)
    # 4. Default localhost
```

### Grace Period
- Support both keyring and config file for 2-3 releases
- Show deprecation warning when using keyring
- Auto-migrate option during login

---

## Example User Workflows

### Setting Up Multiple Environments
```bash
# Add dev environment
slcli login --profile dev
# Enter API URL: https://dev-api.example.com
# Enter API key: ****
# Enter Web URL: https://dev.example.com
# Default workspace: Development
# Set as current profile? Y

# Add production environment
slcli login --profile prod
# Enter API URL: https://prod-api.example.com
# Enter API key: ****
# Default workspace: (leave empty)
# Set as current profile? N

# List profiles
slcli config list-profiles
#   CURRENT   NAME    SERVER                        WORKSPACE
#   *         dev     https://dev-api.example.com   Development
#             prod    https://prod-api.example.com  -
```

### Switching Profiles
```bash
# Switch to production
slcli config use-profile prod

# Run command in different profile without switching
slcli --profile dev workflow list
slcli -p dev workflow list
```

### Working with Default Workspace
```bash
# List workflows (uses profile default workspace "Development")
slcli workflow list
# Shows only Development workspace workflows

# Override with specific workspace
slcli workflow list --workspace "Testing"

# Show all workspaces
slcli workflow list --all-workspaces
```

---

## Open Questions

1. ~~**YAML vs JSON**~~: Using JSON to avoid new dependency. ✓

2. **API Key Storage**: Store in config file (like kubectl) or still use keyring for keys only?
   - Recommend: Config file for simplicity, with proper file permissions and warnings.

3. **Workspace resolution**: Workspace by name or ID in config?
   - Recommend: Support both, resolve at runtime (current behavior).

4. **Config file location override**: Support `SLCLI_CONFIG` env var?
   - Recommend: Yes, for CI/CD flexibility.

5. **Default profile behavior**: If no current-profile set, error or use first profile?
   - Recommend: Error with helpful message to run `slcli config use-profile`.

---

## Dependencies

### Current
- `keyring` - Will become optional/deprecated

### Recommendation
- Use JSON format (no new dependencies)
- Keep `keyring` as optional for secure API key storage (advanced users)
