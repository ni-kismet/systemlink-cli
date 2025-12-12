# NI Package Manager Feed Commands - Implementation Plan

## Overview

This document outlines the implementation plan for NI Package Manager feed management commands in the SystemLink CLI (`slcli`). The commands support both SystemLink Enterprise (SLE) and SystemLink Server (SLS) platforms.

## API Endpoints

| Platform | Base URL     | Swagger                                                     |
| -------- | ------------ | ----------------------------------------------------------- |
| SLE      | `/nifeed/v1` | `https://dev-api.lifecyclesolutions.ni.com/nifeed/swagger/` |
| SLS      | `/nirepo/v1` | See SLS OpenAPI specification                               |

## MVP Implementation (Completed)

### Feed Commands (`slcli feed`)

| Command          | Description                      | Status         |
| ---------------- | -------------------------------- | -------------- |
| `feed list`      | List all feeds                   | ✅ Implemented |
| `feed get`       | Get feed details by ID or name   | ✅ Implemented |
| `feed create`    | Create a new feed                | ✅ Implemented |
| `feed delete`    | Delete a feed                    | ✅ Implemented |
| `feed replicate` | Replicate packages between feeds | ✅ Implemented |

### Package Commands (`slcli feed package`)

| Command          | Description                  | Status         |
| ---------------- | ---------------------------- | -------------- |
| `package list`   | List packages in a feed      | ✅ Implemented |
| `package upload` | Upload a package to a feed   | ✅ Implemented |
| `package delete` | Delete a package from a feed | ✅ Implemented |

### Job Commands (`slcli feed job`)

| Command    | Description                | Status         |
| ---------- | -------------------------- | -------------- |
| `job list` | List feed jobs             | ✅ Implemented |
| `job get`  | Get job details            | ✅ Implemented |
| `job wait` | Wait for a job to complete | ✅ Implemented |

### Key Features

- **Case-insensitive platform values**: The CLI accepts `windows`, `WINDOWS`, `Windows`, `ni-linux-rt`, `NI_LINUX_RT`, etc. and normalizes to the correct format for each platform.
- **`--wait` flag**: Async operations (replicate, upload, delete) support `--wait` to poll until completion.
- **Platform abstraction**: Package upload handles SLS's shared pool → feed reference pattern transparently.

---

## Remaining Work

### Phase 2: Update Management

| Command             | Description                                     | Priority |
| ------------------- | ----------------------------------------------- | -------- |
| `feed update check` | Check for available updates from upstream feeds | High     |
| `feed update apply` | Apply updates from upstream feeds               | High     |
| `feed update list`  | List pending updates                            | Medium   |

**Implementation Notes:**

- SLE uses `/nifeed/v1/feeds/{id}/check-updates` and `/nifeed/v1/feeds/{id}/apply-updates`
- SLS uses `/nirepo/v1/feeds/{id}/updates` (GET to check, POST to apply)
- Both return job IDs for async processing

### Phase 3: Package Download

| Command                 | Description                    | Priority |
| ----------------------- | ------------------------------ | -------- |
| `feed package download` | Download a package from a feed | Medium   |

**Implementation Notes:**

- SLE: `GET /nifeed/v1/packages/{id}/content`
- SLS: `GET /nirepo/v1/packages/{id}/content`
- Support `--output` flag for custom download path
- Show download progress bar

### Phase 4: Feed Cleanup

| Command      | Description                               | Priority |
| ------------ | ----------------------------------------- | -------- |
| `feed clean` | Remove unused/orphaned packages from feed | Low      |

**Implementation Notes:**

- SLE: `POST /nifeed/v1/feeds/{id}/clean`
- SLS: May differ, needs investigation
- Returns job ID, should support `--wait`

### Phase 5: Advanced Features

| Command               | Description                  | Priority |
| --------------------- | ---------------------------- | -------- |
| `feed package search` | Search packages across feeds | Low      |
| `feed export`         | Export feed configuration    | Low      |
| `feed import`         | Import feed configuration    | Low      |

---

## Testing Plan

### Unit Tests (Completed for MVP)

- ✅ `tests/unit/test_feed_click.py` - Core command testing
- Platform normalization tests
- Wait/polling tests
- Error handling tests

### E2E Tests (Completed)

- ✅ `tests/e2e/test_feed_e2e.py`
  - SLE: list feeds, create feed, get feed, list packages (empty), delete feed
  - Uses workspace from config and platform auto-detection

### Integration Tests (TODO)

- Test with actual NI packages
- Test cross-platform replication
- Test large file uploads
- Test job timeout handling

---

## Technical Notes

### Platform Differences

| Feature           | SLE                      | SLS                      |
| ----------------- | ------------------------ | ------------------------ |
| Platform values   | `WINDOWS`, `NI_LINUX_RT` | `windows`, `ni-linux-rt` |
| Package upload    | Direct to feed           | Shared pool → reference  |
| Workspace support | Full                     | Limited/None             |
| Job polling       | `/jobs/{id}`             | `/jobs/{id}`             |

### Error Handling

- All commands use `handle_api_error()` for consistent error formatting
- Exit codes follow `ExitCodes` enum
- Platform-specific errors include platform name for clarity

### Configuration

Feed commands use the same authentication as other CLI commands:

- Credentials stored in keyring under `systemlink-cli` service
- Base URL from `~/.config/slcli/config.json`

---

## Documentation Updates Needed

1. Update `README.md` with feed command examples
2. Add feed commands to CLI reference
3. Document platform-specific behaviors
4. Add troubleshooting section for common issues

---

## Timeline Estimate

| Phase                      | Effort   | Dependencies           |
| -------------------------- | -------- | ---------------------- |
| Phase 2: Update Management | 2-3 days | MVP complete           |
| Phase 3: Package Download  | 1-2 days | MVP complete           |
| Phase 4: Feed Cleanup      | 1 day    | MVP complete           |
| Phase 5: Advanced Features | 3-5 days | Phases 2-4             |
| E2E Tests                  | 2-3 days | Test environment setup |

---

## Open Questions

1. **SLS Package Pool**: Does the shared pool require explicit cleanup, or is it managed automatically?
2. **Feed Permissions**: How are feed-level permissions handled differently between SLE and SLS?
3. **Rate Limiting**: Are there rate limits on package upload/download operations?
4. **Binary Size**: How does including feed commands affect the PyInstaller binary size?
