# Credential Store Proposal: Move Secrets Out of `config.json`

**Status:** Implemented. New profiles use the OS credential store by default;
login warns and falls back to file storage when that store is unavailable.

**Date:** September 29, 2026
**Context:** API keys are stored in plaintext in `~/.config/slcli/config.json` (mode `0600`). Move them to the OS credential store without making profile setup harder and without repeated macOS Keychain prompts, including after updates.

---

## Goals

1. No plaintext API keys or tokens in `config.json` by default.
2. Profile setup stays as it is today: `slcli login`, `config use`, `config list`, `--profile`, `SLCLI_PROFILE`.
3. No Keychain prompts on macOS during normal use, after `slcli` updates, or after Python upgrades.
4. CI and headless use keep working (`SLCLI_API_KEY` and friends).
5. Remove legacy keyring credential support (`SYSTEMLINK_API_KEY`, `SYSTEMLINK_API_URL`, `SYSTEMLINK_WEB_URL`, `SYSTEMLINK_CONFIG` entries).

## Decisions

| Topic | Decision |
|---|---|
| macOS trust model | **Accepted.** Items are created and read through `/usr/bin/security`. Any process running as the same user can read them without a prompt. That is equivalent to today's `0600` file against same-user processes, but the secret is encrypted at rest, locked with the keychain, and kept out of `~/.config` (backups, dotfile syncs, screen shares, `cat`). |
| Legacy keyring entries | **Removed as part of this plan** (Phase 1). No runtime fallback, no migration command. |
| Crypto dependency | **None.** Envelope encryption (a master key in the keyring plus an encrypted file) was rejected: it adds `cryptography` and custom crypto code for little benefit once reads are lazy and per-profile. |

---

## Why macOS Prompts Today

A macOS keychain item has an access list that names the programs allowed to read it without asking. Programs are identified by their code signature.

- **PyInstaller binary (Homebrew/tarball):** it is ad-hoc signed (`codesign_identity=None` in `slcli.spec`), so every release counts as a new program. "Always Allow" is lost on each update.
- **pip/pipx/poetry installs:** the trusted program is the Python interpreter. Python upgrades (for example through Homebrew) trigger the prompts again.
- **One prompt per item:** PKCE reads `access-token`, `access-expires-at`, and `refresh-token` as separate items today.
- **Legacy fallback reads:** `utils.py` and `platform.py` read legacy keyring entries on every run when a profile is missing a value.

**Fix:** do all macOS keychain access through `/usr/bin/security`. It is signed by Apple and its identity is stable, and items it creates trust it by default. This is the approach zalando/go-keyring takes on macOS. Write secrets through `security -i` on stdin so they never appear in `argv`.

---

## Design

### 1. Separate secrets from profile data

`config.json` stays the source of truth for everything that isn't secret. Each profile gains a stable `id` and a `credential-store` field:

```json
{
  "current-profile": "dev",
  "profiles": {
    "dev": {
      "id": "6f1c0e0a-2d7e-4f4b-9f55-0b7b6a2f3c11",
      "server": "https://dev-api.example.com",
      "web-url": "https://dev.example.com",
      "credential-store": "os",
      "workspace": "Development"
    }
  }
}
```

- Keyring service is `systemlink-cli`. Accounts are `profile:<id>:api-key` or
  `profile:<id>:pkce:active` and
  `profile:<id>:pkce:<generation>:<field>` for Windows PKCE fields.
- Keying by `id` instead of name:
  - A profile rename doesn't need a secret move.
  - Separate configs selected through `SLCLI_CONFIG` (for example e2e) can't overwrite each other's secrets. PKCE keys by profile name today, so it has this collision problem.
- `config list`, `config use`, `config current`, and `config view` (without `--show-secrets`) never touch the store.

### 2. Credential store module: `slcli/credentials.py`

Small interface: `get(profile)`, `set(profile, secret)`, `delete(profile)`, `describe()`.

| Platform | Backend | Notes |
|---|---|---|
| macOS | `/usr/bin/security` subprocess | Read: `find-generic-password -s systemlink-cli -a <account> -w`. Write: `add-generic-password -U` via `security -i` on stdin. Delete: `delete-generic-password`. |
| Windows | `keyring` → Credential Manager (DPAPI) | No prompts. Each PKCE field is stored separately to stay within the 2560-byte blob limit. |
| Linux | `keyring` → Secret Service | Uses `file` when no D-Bus or unlocked collection is available (headless, WSL, containers). |
| Any | `file` | Plaintext in `config.json` (today's behavior). Explicit opt-in or fallback. |

Behavior:

- **Lazy:** read only when an API call needs the credential.
- **Cached:** at most one read per profile per process. This also covers the long-running MCP server.
- **Clear errors:**
  - Locked keychain (for example over SSH): suggest `security unlock-keychain` or `SLCLI_API_KEY`.
  - Missing Secret Service: suggest `--credential-store file`.
  - Missing item: suggest `slcli login --profile <name>`.
- `keyring` import or backend failures must never break commands that don't need a credential.

### 3. Resolution order

Unchanged from the user's point of view:

1. `SLCLI_API_KEY` / `SYSTEMLINK_API_KEY` env (the store is never touched)
2. Active profile:
   1. plaintext `api-key` in `config.json`, if present (backward compatibility)
   2. otherwise the credential store per `credential-store`
3. Error with guidance

The same order applies to URL and web URL, minus the store step (they aren't secrets). All legacy keyring steps are removed.

### 4. Profile management UX

- **Login:** `slcli login --profile dev --url … --api-key …` is unchanged; the key goes to the OS store.
  - New option `--credential-store os|file`, defaulting to `SLCLI_CREDENTIAL_STORE`, then `os`.
  - If the OS store isn't usable, it falls back to `file` and prints a one-line warning.
- **View:** `config view` shows `API Key: stored in macOS Keychain` (or Credential Manager / Secret Service / config file) without reading the secret. `--show-secrets` reads it.
- **Hand edits:** adding `"api-key": "…"` to `config.json` keeps working.
- **`slcli config secure [--profile NAME | --all]`:** moves plaintext keys into the OS store and removes them from the file.
- **Plaintext hint:** one line on stderr, TTY only, rate-limited (once per day, tracked in `settings`), suggesting `slcli config secure`.
- **Lifecycle:** `config delete`, `slcli logout`, and `slcli logout --all` delete the profile's stored secrets. Rename keeps the `id`.
- **Source visibility:** `slcli info` and `config view` show where each value came from (env, OS store, config file). This closes the existing source-visibility gap.

### 5. PKCE consolidation

- Store PKCE credentials as one JSON item on macOS and Linux. On Windows, write
  `access-token`, `refresh-token`, and `access-expires-at` under a new generation
  ID, then switch the active-generation account only after all fields succeed.
  Reassemble the JSON at the credential-store interface and delete the prior
  generation after the switch.
- Stop writing the obsolete `session-key` and `session-expires-at` items, and delete them on logout.

### 6. Legacy keyring removal

Remove in Phase 1:

| Location | Remove |
|---|---|
| `slcli/utils.py` | `_get_keyring_config()` and the keyring fallback steps in `get_base_url_resolution`, `get_web_url_resolution`, `get_auth_resolution`, plus docstrings |
| `slcli/platform.py` | `_get_keyring_config()` and the stored-platform fallback |
| `slcli/profiles.py` | `migrate_from_keyring()` and `has_keyring_credentials()` |
| `slcli/config_click.py` | `config migrate` command |
| `slcli/main.py` | login auto-migration prompt; legacy entry cleanup in `logout --all` |
| `describe_config_source` | `keyring:` source label |
| Docs | `site/commands.html`, `slcli/skills/slcli/references/commands.md`, README mentions |
| Tests | legacy keyring tests; shared keyring mocks move to a fake credential store |

Users who still depend only on legacy entries will see "API key not found… run `slcli login`". Automatic migration on login has shipped since profile support (#51), so this should be rare. The Towncrier removal fragment should include manual cleanup:

```bash
# macOS
security delete-generic-password -s systemlink-cli -a SYSTEMLINK_API_KEY
security delete-generic-password -s systemlink-cli -a SYSTEMLINK_API_URL
security delete-generic-password -s systemlink-cli -a SYSTEMLINK_WEB_URL
security delete-generic-password -s systemlink-cli -a SYSTEMLINK_CONFIG

# Windows (PowerShell)
cmdkey /delete:SYSTEMLINK_API_KEY@systemlink-cli
```

Confirm the exact Windows target names before publishing: `keyring` stores them as `<username>@<service>`.

---

## Rollout

| Phase | Scope | Default for new profiles |
|---|---|---|
| **1-3** | Implemented: OS-store default, warned file fallback, explicit file selection, secure migration command, profile source display, platform-appropriate PKCE storage, and removal of legacy global keyring reads and migration. | `os` |
| **4 (optional)** | Developer ID signing and notarization of the macOS PyInstaller binary with a stable identifier. This is not part of the credential-store implementation. | — |

## Testing

- **Unit:** fake credential store fixture; `/usr/bin/security` backend tested with a mocked `subprocess.run` (argument shape, stdin payload, exit codes 44 "not found" and 36/51 "locked / interaction not allowed"); fallback when `keyring` raises `NoKeyringError`; resolution order including env override and plaintext compatibility; `config secure`; delete, logout, and rename lifecycle.
- **E2E:** one login → command → logout run per platform in CI. Confirm no secret remains in `config.json` and the store item is removed.
- **Manual (macOS):** install release N, log in, upgrade to N+1, run commands, and confirm there are no prompts. Repeat with a pipx install across a Python upgrade.

## Open Questions

1. Linux fallback: should falling back to `file` warn every time or once per profile?
2. Is Phase 4 (Developer ID signing) worth doing for Gatekeeper alone?
