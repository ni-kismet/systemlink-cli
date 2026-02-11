## Summary

Performance improvements, bug fixes, and a new Agent Skills definition for `slcli`.

---

### 🚀 Test Monitor performance improvements (`slcli/testmonitor_click.py`)

- **Count-only queries for `--summary`**: Added `_query_counts_by_status()` which uses `returnCount: true` and `take: 0` per status type instead of fetching all results and aggregating client-side. Dramatically reduces data transfer for summary commands.
- **Increased batch size**: Changed `_query_all_results()` page size from 100 → 1000 (API max) for faster full-result queries.
- **Fixed `TIMEDOUT` enum**: API expects `TIMEDOUT` (no underscore), not `TIMED_OUT` as documented. Updated status type list accordingly.

### 🖥️ System list improvements (`slcli/system_click.py`)

- **Default `--take` changed to 100**: More useful default for fleet-level queries.
- **`--take` now applies to JSON output**: Previously JSON ignored the take parameter; now it respects it.
- **Conservative page size (100)**: Reduced internal `_query_all_items()` batch size from 1000 → 100 to avoid HTTP 500 errors from the Systems Management API.

### 🔧 Asset create error handling (`slcli/asset_click.py`)

- **Improved create response parsing**: Now inspects both `assets` and `failed` arrays from the API response.
- **Non-zero exit on failure**: JSON output exits with `GENERAL_ERROR` when the `failed` array is non-empty and no assets were created.
- **User-friendly error messages**: Table output now shows the server-provided error message on creation failure.

### 📘 Agent Skills definition (`skills/slcli/`)

New [Agent Skills](https://agentskills.io/specification) skill definition so AI agents can discover and effectively use `slcli`:

- `skills/slcli/SKILL.md` — Frontmatter + full command reference with quick start, all filter options, and key rules
- `skills/slcli/references/analysis-recipes.md` — 10 step-by-step recipes with `jq` post-processing for common data analysis questions
- `skills/slcli/references/filtering.md` — Comprehensive filtering reference covering LINQ, Asset API expressions, System Management filters, sorting, enums

### 🧪 Test updates

- `tests/unit/test_testmonitor_click.py` — Updated mocks for count-only query approach
- `tests/unit/test_system_click.py` — Updated expectations for new default take (100)
- `tests/e2e/test_asset_e2e.py` — Added `--vendor-name` to create test to satisfy API validation

---

### Files changed

| File | Change |
|------|--------|
| `slcli/testmonitor_click.py` | Count-only queries, batch size increase, TIMEDOUT fix |
| `slcli/system_click.py` | Default take → 100, JSON take support, page size → 100 |
| `slcli/asset_click.py` | Improved create error handling |
| `skills/slcli/SKILL.md` | New Agent Skills definition |
| `skills/slcli/references/analysis-recipes.md` | Analysis recipes for 10 common questions |
| `skills/slcli/references/filtering.md` | Filtering reference guide |
| `tests/unit/test_testmonitor_click.py` | Updated mocks |
| `tests/unit/test_system_click.py` | Updated default take expectations |
| `tests/e2e/test_asset_e2e.py` | Added vendor-name to create test |