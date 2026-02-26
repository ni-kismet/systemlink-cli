# CHANGELOG


## v0.33.0 (2026-02-26)

### Features

- Add Exercise 7-1 example (Create and Schedule Test Plans)
  ([#66](https://github.com/ni-kismet/systemlink-cli/pull/66),
  [`98887d0`](https://github.com/ni-kismet/systemlink-cli/commit/98887d0bc00a0a5a579d1a5d052895b76a694a7f))

* feat: add exercise 7-1 example

* delete unnecessary docs


## v0.32.0 (2026-02-25)

### Chores

- **release**: 0.32.0
  ([`3233d98`](https://github.com/ni-kismet/systemlink-cli/commit/3233d98945f2d8914b775899f6ae7ce44d8bdb2b))

### Features

- Add comment support ([#65](https://github.com/ni-kismet/systemlink-cli/pull/65),
  [`0507b00`](https://github.com/ni-kismet/systemlink-cli/commit/0507b006096592a4d31b7aa4a361366ea9b958bd))


## v0.31.9 (2026-02-23)

### Bug Fixes

- Add exercise 5-1 example ([#64](https://github.com/ni-kismet/systemlink-cli/pull/64),
  [`f109ce8`](https://github.com/ni-kismet/systemlink-cli/commit/f109ce8df3975312626444f07c8c7acb76c60b8c))

### Chores

- **release**: 0.31.9
  ([`8ed0816`](https://github.com/ni-kismet/systemlink-cli/commit/8ed081616d412aa21d27eed20a8f2a3afdfae259))


## v0.31.8 (2026-02-19)

### Bug Fixes

- Tag datatype detection
  ([`f1f090a`](https://github.com/ni-kismet/systemlink-cli/commit/f1f090a3c8d8a11e0f3fac54f915500b48b249ba))

### Chores

- **release**: 0.31.8
  ([`c03881d`](https://github.com/ni-kismet/systemlink-cli/commit/c03881d794fd4318228a6030d2e375fbff9b9029))


## v0.31.7 (2026-02-19)

### Bug Fixes

- Tag commands without specifying workspace and help formatting
  ([`c4af1ce`](https://github.com/ni-kismet/systemlink-cli/commit/c4af1ce47b515649b5efd53e62f647818db39a8a))

### Chores

- **release**: 0.31.7
  ([`275473e`](https://github.com/ni-kismet/systemlink-cli/commit/275473e673732052ff49772cdceae6981c596635))


## v0.31.6 (2026-02-11)

### Bug Fixes

- Performance improvements, bug fixes, and a new Agent Skills definition for slcli
  ([#63](https://github.com/ni-kismet/systemlink-cli/pull/63),
  [`634fb92`](https://github.com/ni-kismet/systemlink-cli/commit/634fb92ee3f708e8296fa3e4d6efa695a07acf3c))

* chore: staged changes (create PR) — automated

* feat: add skill.md

* lint fix

* fix: Resolve PR feedback - LINQ operators, asset failure handling, testmonitor improvements,
  system list docs

### Chores

- **release**: 0.31.6
  ([`de1f5ef`](https://github.com/ni-kismet/systemlink-cli/commit/de1f5ef9d7801f4917775f16564e228be946dcf7))


## v0.31.5 (2026-02-11)

### Bug Fixes

- Lint fixes
  ([`f553428`](https://github.com/ni-kismet/systemlink-cli/commit/f55342878b06eeb943459fc6f90c077939a59be3))

### Chores

- **release**: 0.31.5
  ([`c4ad9e5`](https://github.com/ni-kismet/systemlink-cli/commit/c4ad9e5a4c8448c62a30a477708c77f8041a304e))


## v0.31.4 (2026-02-11)

### Bug Fixes

- Prevent real HTTP calls in unit tests
  ([`576b3c0`](https://github.com/ni-kismet/systemlink-cli/commit/576b3c091289ebea9bf5f7ac9b6474dd0a11e837))

- Patch get_workspace_map in all *_click modules that import it at module level - Add safety net
  patching of requests.get/post/put/delete globally - Update 3 tests that expect workspace names to
  provide their own mocks

This fixes slow unit test runs on macOS CI where network timeouts caused tests to take 70+ seconds
  instead of ~1 second.

### Chores

- **release**: 0.31.4
  ([`6ccbc5a`](https://github.com/ni-kismet/systemlink-cli/commit/6ccbc5ab37bd2726f8fca07fb48d939c1c262481))


## v0.31.3 (2026-02-11)

### Bug Fixes

- Prevent network calls in unit tests causing macOS CI slowdown
  ([`d63f82c`](https://github.com/ni-kismet/systemlink-cli/commit/d63f82cbcc759026942ae1fa52e6a12ca306fc89))

Root cause: get_workspace_display_name() in workspace_utils.py calls get_workspace_map() which makes
  real HTTP requests. Tests patched the function in module namespaces but workspace_utils imports it
  directly from utils, bypassing those patches.

On macOS CI, TCP connections to localhost:8000 timeout slowly (~75s) instead of failing immediately
  like on Linux, causing 1+ hour test runs.

Fix: Add autouse fixture in conftest.py to patch slcli.workspace_utils.get_workspace_map for all
  unit tests.

### Chores

- **release**: 0.31.3
  ([`92dfd46`](https://github.com/ni-kismet/systemlink-cli/commit/92dfd4603739844e9a71b16b81af87206b7ac208))


## v0.31.2 (2026-02-11)

### Bug Fixes

- Macos slow tests
  ([`5b25bab`](https://github.com/ni-kismet/systemlink-cli/commit/5b25bab201f215fa86d9d943bad20abd7a551b8d))

### Chores

- **release**: 0.31.2
  ([`17d9222`](https://github.com/ni-kismet/systemlink-cli/commit/17d9222d8e9e6642667381bd7e62201c2a267e33))


## v0.31.1 (2026-02-11)

### Bug Fixes

- Test slowdowns
  ([`18317fe`](https://github.com/ni-kismet/systemlink-cli/commit/18317fe168f6def4823261ecdeaf05e1722c756a))

### Chores

- **release**: 0.31.1
  ([`d29f29e`](https://github.com/ni-kismet/systemlink-cli/commit/d29f29e8e9bcfcef9ff9af4d3eca377ce74a9ec0))


## v0.31.0 (2026-02-11)

### Chores

- **release**: 0.31.0
  ([`c1cff7c`](https://github.com/ni-kismet/systemlink-cli/commit/c1cff7c67134a79e83a8c7ef702119eeb8e2ef47))

### Features

- Add system and asset commands ([#62](https://github.com/ni-kismet/systemlink-cli/pull/62),
  [`af15970`](https://github.com/ni-kismet/systemlink-cli/commit/af15970dbae8f8b88cd61c8426885c208376ecb0))

* feat: add asset commands - phase 1 - 3

* feat: add system commands

* fix: address PR review feedback

- Validate property filter keys against safe identifier pattern [A-Za-z0-9_.] - Reject property
  filters without KEY=VALUE format with INVALID_INPUT exit code - Add explanatory comments to all
  bare except clauses - Fix E2E tests to handle both list and dict responses from asset create - Fix
  --model-name assertion in asset create help test - Update asset proposal doc to reflect
  implemented create/update/delete commands - Add unit tests for property filter validation (missing
  =, unsafe key)

* fix: asset create payload and E2E response parsing

- Add default location with assetPresence=UNKNOWN to create payload (required by POST
  /niapm/v1/assets API) - Change model-number and vendor-number from str to int (API expects int32)
  - Fix E2E tests to handle {"assets": [...], "failed": [...]} response wrapper from the create API


## v0.30.0 (2026-02-10)

### Chores

- **release**: 0.30.0
  ([`a2eb2b1`](https://github.com/ni-kismet/systemlink-cli/commit/a2eb2b11a052242a8670ffa93006dfda99e52a84))

### Features

- Test Monitor Phase 2 + summary/grouping
  ([#54](https://github.com/ni-kismet/systemlink-cli/pull/54),
  [`facffc0`](https://github.com/ni-kismet/systemlink-cli/commit/facffc0fbbcebb72883e8ed2a247a5a517055bd7))

* phase 2 changes

* feat: testmonitor summary and grouping options

* Fix testmonitor summary grouping, pagination, and remove dead code (#55)

* Initial plan

* Address PR review comments: fix grouping, pagination, and unused code

Co-authored-by: fredvisser <1458528+fredvisser@users.noreply.github.com>

* Remove redundant parentheses and format code

Co-authored-by: fredvisser <1458528+fredvisser@users.noreply.github.com>

* add checks for excessive results

---------

Co-authored-by: copilot-swe-agent[bot] <198982749+Copilot@users.noreply.github.com> Co-authored-by:
  fredvisser <1458528+fredvisser@users.noreply.github.com>

* Add defensive status handling and truncation warnings to testmonitor summaries (#58)

* Initial plan

* Fix testmonitor status handling, extract group field mapping, add truncation warnings

Co-authored-by: fredvisser <1458528+fredvisser@users.noreply.github.com>

---------

Co-authored-by: copilot-swe-agent[bot] <198982749+Copilot@users.noreply.github.com> Co-authored-by:
  fredvisser <1458528+fredvisser@users.noreply.github.com>

---------

Co-authored-by: Copilot <198982749+Copilot@users.noreply.github.com>


## v0.29.0 (2026-02-10)

### Chores

- **release**: 0.29.0
  ([`44d5632`](https://github.com/ni-kismet/systemlink-cli/commit/44d563215cc62cd8e4cb3fbc4518c7123e16aeb8))

### Features

- Add readonly mode protection for mutation operations
  ([#56](https://github.com/ni-kismet/systemlink-cli/pull/56),
  [`48d6b0f`](https://github.com/ni-kismet/systemlink-cli/commit/48d6b0f9091514053b08a692dee9f894c6d8120a))

* feat: readonly mode

* Refine readonly mode documentation and remove interactive prompt (#57)

* Initial plan

* Address PR review comments on readonly mode documentation and testing

- Updated README.md to say "blocks all mutation operations" instead of "disables all delete/edit
  commands" - Removed interactive readonly prompt from config_click.py to avoid breaking
  non-interactive usage - Updated --readonly help text in main.py and config_click.py to list all
  blocked operations (create, update, delete, import, upload, publish, disable) - Updated utils.py
  error message to list all blocked verbs - Added assertions to
  test_readonly_mode_error_message_content to validate error message content

Co-authored-by: fredvisser <1458528+fredvisser@users.noreply.github.com>

---------

Co-authored-by: copilot-swe-agent[bot] <198982749+Copilot@users.noreply.github.com> Co-authored-by:
  fredvisser <1458528+fredvisser@users.noreply.github.com>

* cleaned up config commands

---------

Co-authored-by: Copilot <198982749+Copilot@users.noreply.github.com>


## v0.28.0 (2026-02-06)

### Chores

- **release**: 0.28.0
  ([`466c1b7`](https://github.com/ni-kismet/systemlink-cli/commit/466c1b7ee852e82d37c1851b224a477ca20a27f0))

### Features

- Add Test Monitor commands with product and result listing
  ([#52](https://github.com/ni-kismet/systemlink-cli/pull/52),
  [`bc61b5a`](https://github.com/ni-kismet/systemlink-cli/commit/bc61b5ad59c30f80c0ff7d678fbd34f8eb710dc2))

* feat: Add Test Monitor commands with product and result listing

- Add testmonitor CLI module with product list and result list commands - Implement interactive
  pagination for table output (25 items per page) - Support comprehensive filtering: name,
  part-number, family, workspace, custom filters - Support Dynamic LINQ filter expressions with
  substitution parameters - Support ordering by various fields with ascending/descending options -
  Implement result-specific filters: status, program-name, serial-number, operator, host-name,
  system-id - Support product filtering for test results queries - Format output as table (default)
  or JSON with proper workspace name resolution - Add 6 comprehensive unit tests with 83% coverage -
  Update README with usage examples and Dynamic LINQ documentation - Update DFF e2e tests to use new
  'customfield' command name

* Refactor Test Monitor commands: eliminate duplication and expand test coverage (#53)

* Initial plan

* refactor: Fix duplicate workspace_map fetch and extract pagination helper

- Fixed duplicate workspace_map fetching in list_products - Extracted interactive pagination logic
  into reusable _handle_interactive_pagination helper - Added explanatory comments to empty except
  clauses

Co-authored-by: fredvisser <1458528+fredvisser@users.noreply.github.com>

* test: Add comprehensive unit test coverage for testmonitor commands

- Add empty results scenario tests for products and results - Add order-by functionality tests - Add
  descending/ascending parameter tests - Add product-filter with product-substitution test - Add
  error handling scenario tests - Coverage increased from 85% to 91%

Co-authored-by: fredvisser <1458528+fredvisser@users.noreply.github.com>

---------

Co-authored-by: copilot-swe-agent[bot] <198982749+Copilot@users.noreply.github.com> Co-authored-by:
  fredvisser <1458528+fredvisser@users.noreply.github.com>

---------

Co-authored-by: Copilot <198982749+Copilot@users.noreply.github.com>


## v0.27.1 (2026-01-30)

### Bug Fixes

- Windows permissions test failure
  ([`9e3bfe9`](https://github.com/ni-kismet/systemlink-cli/commit/9e3bfe908d26203daa3f8d21619cde69817aff6d))

### Chores

- **release**: 0.27.1
  ([`4f6f161`](https://github.com/ni-kismet/systemlink-cli/commit/4f6f161685f63b59b4a6246eaaf1fdc6db649a87))


## v0.27.0 (2026-01-29)

### Chores

- **release**: 0.27.0
  ([`344ae3c`](https://github.com/ni-kismet/systemlink-cli/commit/344ae3caf3aacb5f8d1dc8a1316eef63b95105fc))

### Features

- Implement profile-based configuration management
  ([#51](https://github.com/ni-kismet/systemlink-cli/pull/51),
  [`fa1eab7`](https://github.com/ni-kismet/systemlink-cli/commit/fa1eab75b95f6312f1f19287d97b44ebe786a1d8))

* feat: implement profile-based configuration management

- Add profiles.py module for managing multiple named profiles - Add config CLI commands for profile
  management (list, view, use, delete, migrate) - Update login/logout commands to support --profile
  flag - Add global --profile flag to all commands - Update utils.py functions to check profiles
  before keyring - Fix platform.py get_platform_info() to use profile-aware functions - Update info
  command to display active profile information - Add comprehensive unit tests (22 for profiles, 12
  for config commands) - Update README with profile usage documentation - Maintain backwards
  compatibility with keyring-based auth

Implements kubectl-style multi-profile configuration system with AWS CLI naming conventions.

* fix: address PR review feedback

- Fix URL/workspace truncation with proper ellipsis in list-profiles - Add SYSTEMLINK_WEB_URL to
  environment variables documentation - Mask API keys in 'config view --format json' output (add
  --show-secrets flag) - Fix config path truncation to avoid double pipe character - Remove
  redundant platform variable assignment - Add explanatory comments to all bare except clauses -
  Improve security by preventing accidental API key exposure

Resolves all 15 review comments from copilot-pull-request-reviewer

* Fix PR review feedback round 2: type safety and UX consistency

- Fix type compatibility in list-profiles: convert Profile objects to Dict[str, Any] for
  output_formatted_list - Update return type annotation from 'list' to 'List[str]' for consistency -
  Add --take/-t option to list-profiles command for UX consistency (default=25) - Update add_profile
  docstring to clarify first profile becomes current even with set_current=False - Replace broad
  'except Exception:' with specific exceptions (FileNotFoundError, json.JSONDecodeError, KeyError,
  AttributeError) in profile loading functions

All tests pass (401/401). mypy and linting pass.

* lint fix

* Add migration prompt to login command

- Detect existing keyring credentials when no profiles exist - Prompt user to migrate credentials
  during first login - Offer interactive migration with option to delete keyring entries - Add 2 new
  unit tests for migration prompt scenarios - Update test_login_with_flags to mock keyring (prevent
  false positives)

Addresses minor observation from PR review: 'Consider adding a prompt on first slcli login if
  keyring credentials exist, suggesting migration.'

All 403 unit tests pass. Linting and type checking pass.

* automatically migrate

* lint fix


## v0.26.1 (2026-01-29)

### Bug Fixes

- Update to macos-15-intel runner
  ([`9352a4f`](https://github.com/ni-kismet/systemlink-cli/commit/9352a4f4240e4f9771bb07e1e4a22f8172cbe947))

### Chores

- **release**: 0.26.1
  ([`12bbae3`](https://github.com/ni-kismet/systemlink-cli/commit/12bbae3f8a2f59b6cf1b9c6bd2876445071ab694))


## v0.26.0 (2026-01-29)

### Chores

- **release**: 0.26.0
  ([`50db120`](https://github.com/ni-kismet/systemlink-cli/commit/50db12068b0652695ee1c561737183bb7449af4a))

### Features

- Add legacy mac support ([#50](https://github.com/ni-kismet/systemlink-cli/pull/50),
  [`c5eb9fd`](https://github.com/ni-kismet/systemlink-cli/commit/c5eb9fd12add4fb4bcfa61e67e252f6ca3657fcb))

* feat: add legacy mac support

* review feedback


## v0.25.0 (2026-01-27)

### Chores

- **release**: 0.25.0
  ([`2b40398`](https://github.com/ni-kismet/systemlink-cli/commit/2b403982604293a2b3f0b1871b30bfed539851ed))

### Features

- Simplify DFF editor and add edit functionality
  ([#48](https://github.com/ni-kismet/systemlink-cli/pull/48),
  [`5fbcaac`](https://github.com/ni-kismet/systemlink-cli/commit/5fbcaac9035e2ac11fddb8bc1501b87d2bcb6b84))

* feat: dff editor no longer copies files. Add edit dialog support

* fix: resolve PR review feedback

- Write config to temp directory instead of read-only install location - Remove unused initialFile
  config parameter (not consumed by frontend) - Remove config edit button since edit-config is not
  implemented - All tests passing, linting and type checking clean

* fix: resolve remaining PR review feedback

- Use TemporaryDirectory for config file cleanup - Serve slcli-config.json from temp directory via
  dedicated GET handler - Replace HTML innerHTML with safe DOM API calls in showEditDialog - Add
  aria-labels and title attributes to edit buttons for accessibility - Fix configIdx bug: use stored
  value instead of always using config[0] - All tests passing, linting and type checking clean

* lint fix

* lint fix


## v0.24.3 (2026-01-21)

### Bug Fixes

- Powershell completion script
  ([`772efd5`](https://github.com/ni-kismet/systemlink-cli/commit/772efd508f344290563bdbcff0d3648ec5a56d9d))

### Chores

- **release**: 0.24.3
  ([`bbe496e`](https://github.com/ni-kismet/systemlink-cli/commit/bbe496ed5a0b57e07fc1bf0faeb5ef8e0d8941ce))


## v0.24.2 (2026-01-09)

### Bug Fixes

- Move editorSecret to global scope to fix reference error in dff editor
  ([`cdcbb12`](https://github.com/ni-kismet/systemlink-cli/commit/cdcbb1276a446b3c68d6e516f53eec7c93bf7b2e))

### Chores

- **release**: 0.24.2
  ([`4b704b5`](https://github.com/ni-kismet/systemlink-cli/commit/4b704b50ddd02a9f2e4db71d55e6ae1e8bb3fb68))


## v0.24.1 (2026-01-09)

### Bug Fixes

- Dff editor installer fix ([#47](https://github.com/ni-kismet/systemlink-cli/pull/47),
  [`600fd08`](https://github.com/ni-kismet/systemlink-cli/commit/600fd08dd45f33ad3b06f0ff814a36f5c902fe39))

### Chores

- **release**: 0.24.1
  ([`0e1aed8`](https://github.com/ni-kismet/systemlink-cli/commit/0e1aed8f29230f81cb6267183cb5ff12351e55b9))


## v0.24.0 (2026-01-09)

### Chores

- **release**: 0.24.0
  ([`e9c01b1`](https://github.com/ni-kismet/systemlink-cli/commit/e9c01b157a91825c989796f260a86a315c935137))

- **deps**: Bump urllib3 from 2.6.0 to 2.6.3
  ([#46](https://github.com/ni-kismet/systemlink-cli/pull/46),
  [`9e24760`](https://github.com/ni-kismet/systemlink-cli/commit/9e24760a61143711e7842f3c52d585ab18d68776))

Bumps [urllib3](https://github.com/urllib3/urllib3) from 2.6.0 to 2.6.3. - [Release
  notes](https://github.com/urllib3/urllib3/releases) -
  [Changelog](https://github.com/urllib3/urllib3/blob/main/CHANGES.rst) -
  [Commits](https://github.com/urllib3/urllib3/compare/2.6.0...2.6.3)

--- updated-dependencies: - dependency-name: urllib3 dependency-version: 2.6.3 dependency-type:
  indirect ...

Signed-off-by: dependabot[bot] <support@github.com> Co-authored-by: dependabot[bot]
  <49699333+dependabot[bot]@users.noreply.github.com>

### Features

- Add role by name
  ([`63a1432`](https://github.com/ni-kismet/systemlink-cli/commit/63a1432d18fd091701f8bd651d7716f1a70716fc))


## v0.23.0 (2026-01-07)

### Chores

- **release**: 0.23.0
  ([`a0ec69a`](https://github.com/ni-kismet/systemlink-cli/commit/a0ec69af423ce299a260b248bb09c2ab33b74b7b))

### Features

- Add auth policy management commands + docs
  ([#43](https://github.com/ni-kismet/systemlink-cli/pull/43),
  [`018379d`](https://github.com/ni-kismet/systemlink-cli/commit/018379d08f100589fcfae6704257da8bf6f897f5))

* feat: add policy management commands

* docs: document auth policy management commands and examples

* feat: support workspace name/ID in --workspace-policies option

- Add workspace name resolution using resolve_workspace_id() - Update help text to clarify both name
  and ID are supported - Improve validation with better error messages - Update README examples to
  show workspace name usage - All tests passing (44 user tests)

* fix: Address PR review comments - DRY workspace policy parsing, fix test mocking, add error
  coverage (#44)

* Initial plan

* fix: Address PR review comments - extract helper, fix tests, add error coverage

Co-authored-by: fredvisser <1458528+fredvisser@users.noreply.github.com>

---------

Co-authored-by: copilot-swe-agent[bot] <198982749+Copilot@users.noreply.github.com> Co-authored-by:
  fredvisser <1458528+fredvisser@users.noreply.github.com>

---------

Co-authored-by: Copilot <198982749+Copilot@users.noreply.github.com>


## v0.22.2 (2026-01-06)

### Bug Fixes

- Lowercase boolean tags
  ([`460808b`](https://github.com/ni-kismet/systemlink-cli/commit/460808b755568a5ca5dc6496dba7c42a62b5994f))

### Chores

- **release**: 0.22.2
  ([`5038e2b`](https://github.com/ni-kismet/systemlink-cli/commit/5038e2bf0875b1b63627f8c6b9c2c5bbe7d709ec))


## v0.22.1 (2026-01-06)

### Bug Fixes

- Tag set-value for dates and uint64
  ([`2936df8`](https://github.com/ni-kismet/systemlink-cli/commit/2936df839fbf107b6443cce65a41749964da6fac))

### Chores

- **release**: 0.22.1
  ([`83bacca`](https://github.com/ni-kismet/systemlink-cli/commit/83bacca70842af0d44b0d17a93cecde020fbc4da))


## v0.22.0 (2026-01-06)

### Chores

- **release**: 0.22.0
  ([`8915234`](https://github.com/ni-kismet/systemlink-cli/commit/89152344a7da1035695741a707b22055083a5414))

### Features

- Add tag commands ([#41](https://github.com/ni-kismet/systemlink-cli/pull/41),
  [`38d015f`](https://github.com/ni-kismet/systemlink-cli/commit/38d015f3032e7fa6551bb6a89027eded5f0f345e))

* feat: add tag management commands


## v0.21.0 (2026-01-06)

### Chores

- **release**: 0.21.0
  ([`763a652`](https://github.com/ni-kismet/systemlink-cli/commit/763a6529e43bfca61650979633f29e2e437c1430))

### Features

- Add spec compliance notebook example ([#40](https://github.com/ni-kismet/systemlink-cli/pull/40),
  [`261621c`](https://github.com/ni-kismet/systemlink-cli/commit/261621c3a9131637440243610609cd43ff092edf))

* Add spec-compliance-notebooks example with notebook publishing support

- Create new example 'spec-compliance-notebooks' that publishes three Jupyter notebooks (Spec
  Compliance Calculation, Spec Analysis & Compliance Calculation, Specfile Extraction) to SystemLink
  with File Analysis interface - Move notebooks from Jupyter/ to
  spec-compliance-notebooks/notebooks/ - Enhance example_provisioner._create_file() to support
  notebook creation via file_path and notebook_interface properties - Add
  _create_notebook_from_file() helper to load .ipynb files from example directory and create
  notebooks with interface assignment - Update example_loader and schema to support 'file' resource
  type for notebooks - All unit tests pass; no regressions

* feat: add spec notebook example

* review feedback


## v0.20.1 (2025-12-30)

### Bug Fixes

- Include examples in PyInstaller build ([#39](https://github.com/ni-kismet/systemlink-cli/pull/39),
  [`92ab074`](https://github.com/ni-kismet/systemlink-cli/commit/92ab0747e0d3a4ecf81e96010d02b3ff00b32883))

### Chores

- **release**: 0.20.1
  ([`11dfdd8`](https://github.com/ni-kismet/systemlink-cli/commit/11dfdd8de47deb007a1917e8b9e8592d460448e7))


## v0.20.0 (2025-12-19)

### Chores

- **release**: 0.20.0
  ([`15f37ee`](https://github.com/ni-kismet/systemlink-cli/commit/15f37eed99c0c7b55518179ad96096e72b563930))

### Features

- Add example CLI workflow, schemas, and review guidance
  ([#38](https://github.com/ni-kismet/systemlink-cli/pull/38),
  [`cfdd750`](https://github.com/ni-kismet/systemlink-cli/commit/cfdd75000c545578bf537d036f101a87075d1000))

* Phase 1: Example configuration system - loader, CLI, and demo config

* Add support for new resource types: workflow, work_item, work_order, test_result, data_table,
  file. Create comprehensive demo-complete-workflow example showing full resource hierarchy (Tier
  0-3)

* doc cleanup and initial reviews

* prompt updates

* lint

* remove openapi schema

* readme and example list changes

* fix: Add missing get_base_url mocks and fix mypy type errors in tests

* fix: Add explanatory comments to bare except clauses in example_provisioner.py

- Added comments explaining why exceptions are silently handled in query/getter methods - These
  methods fail gracefully (returning None/empty list) when APIs are unavailable - Addresses Copilot
  PR review comments on 8 bare except clauses across getter methods


## v0.19.1 (2025-12-16)

### Bug Fixes

- Make file delete command consistent with other delete subcommands
  ([#36](https://github.com/ni-kismet/systemlink-cli/pull/36),
  [`f3c765d`](https://github.com/ni-kismet/systemlink-cli/commit/f3c765d499e714f4c4e346bf554367f912c91909))

- Change 'file delete' from positional argument to --id/-i flag - All delete subcommands now use
  consistent --id/-i flag pattern - Update tests to use new flag-based syntax - Update README
  documentation with new command syntax - All tests passing (34 file tests + linting + type
  checking)

### Chores

- **release**: 0.19.1
  ([`e67b303`](https://github.com/ni-kismet/systemlink-cli/commit/e67b3037347f69ecfc51f6abb48734f4a146d832))


## v0.19.0 (2025-12-16)

### Chores

- **release**: 0.19.0
  ([`99391c5`](https://github.com/ni-kismet/systemlink-cli/commit/99391c5bf0f88bf68495a783e5a9dad22466fd0d))

### Features

- Improve workspace list command with pagination and filtering
  ([`1524f82`](https://github.com/ni-kismet/systemlink-cli/commit/1524f8236eec16369c7312768c6f1ee423e740cc))

- Add _fetch_all_workspaces() helper with proper pagination using take=100 and skip - API's max take
  parameter is 100, use skip and totalCount for multi-page retrieval - Add --filter flag for
  case-insensitive substring matching on workspace names - Update disable_workspace and
  get_workspace to use pagination helper - Update _get_workspace_map to use the helper for
  consistency - Documentation updated with new filtering examples

Changes: - slcli/workspace_click.py: Added pagination helper and --filter option - README.md:
  Updated workspace list command examples with new features

Testing: - All 266 unit tests passing - mypy type checking clean - linting clean

### Testing

- Add comprehensive tests for workspace pagination and filtering
  ([`68adf16`](https://github.com/ni-kismet/systemlink-cli/commit/68adf16ea7956feda02f7359aca49816dbb42bc1))

- test_list_workspaces_with_filter: Test --filter flag with substring matching -
  test_list_workspaces_filter_json: Test --filter with JSON output format -
  test_list_workspaces_pagination: Test pagination with skip/totalCount handling -
  test_list_workspaces_filter_case_insensitive: Test case-insensitive filtering

All tests pass (270 total, +4 new tests) mypy: clean linting: clean


## v0.18.0 (2025-12-15)

### Chores

- **release**: 0.18.0
  ([`7a3a971`](https://github.com/ni-kismet/systemlink-cli/commit/7a3a971d6af6461caeeb4d829b7cb18ccf93a4eb))

### Features

- Resolve PR review comments for notebook interface support
  ([`94b39bd`](https://github.com/ni-kismet/systemlink-cli/commit/94b39bd032438a0bbb33f9566f251c7e740ffa01))

- Add interface validation in update command before adding to metadata - Validate interface early in
  create command to fail fast on invalid input - Simplify properties dict creation in list to avoid
  empty dicts - All tests passing (266 passed), mypy clean, lint clean

- Notebook interface support
  ([`f3938c8`](https://github.com/ni-kismet/systemlink-cli/commit/f3938c8a9daf6d7a1c6f8948a09e789644758538))


## v0.17.0 (2025-12-15)

### Chores

- **release**: 0.17.0
  ([`3f2694f`](https://github.com/ni-kismet/systemlink-cli/commit/3f2694fc53c6f5801d1affea1584d3a7737f5e98))

- Refresh CLI help text
  ([`aa9d8f3`](https://github.com/ni-kismet/systemlink-cli/commit/aa9d8f386d95e07ee2b4ddc6dfb07b77ac0295f6))

### Documentation

- **e2e**: Clarify statefulness patterns and parallel safety verification
  ([`de832b3`](https://github.com/ni-kismet/systemlink-cli/commit/de832b342b0c9dc39a0726342f317c9009307698))

- Add parallel e2e test execution guidance with pytest-xdist
  ([`b4d077a`](https://github.com/ni-kismet/systemlink-cli/commit/b4d077a817893acea64888bd7a5d3310c097d576))

- Comprehensive CLI consistency analysis and improvement proposals
  ([`95bafbb`](https://github.com/ni-kismet/systemlink-cli/commit/95bafbb240f10e4664ed690dc4e212a9198d698e))

- Analyzed all commands for consistency in flags, naming, and patterns - Identified 7 key areas with
  specific inconsistencies - Proposed prioritized recommendations with rationale - Outlined 3-phase
  implementation strategy (non-breaking, breaking, docs)

- Update README to match refreshed CLI help text
  ([`8c69cd1`](https://github.com/ni-kismet/systemlink-cli/commit/8c69cd17b399e1f55b92d4bc6c47d38fd14eaaa2))

### Features

- **cli**: Add template/workflow get; support name for export; unify workspace flags; remove -f from
  --file; update notebook help; README updates
  ([`4729569`](https://github.com/ni-kismet/systemlink-cli/commit/4729569b6b5d7648cc4fed40480ac58ea048251c))

### Testing

- Add unit coverage for main auth/info, templates/workflows get/init, notebook update/sync, file
  watch guard, webapp open; fix webapp open test; format + lint
  ([`927892c`](https://github.com/ni-kismet/systemlink-cli/commit/927892c5c1ca107f0fb24d903aec95090f99f272))

- **e2e**: Update workspace e2e for unified --workspace; docs: README for get/export and flags;
  chore: dev install pytest-xdist
  ([`4b75ecb`](https://github.com/ni-kismet/systemlink-cli/commit/4b75ecb6d7cebc3c29bf9e188656a7c7e010eede))


## v0.16.1 (2025-12-13)

### Bug Fixes

- Merge pull request #31 from ni-kismet/fix/feed-package-issues
  ([`b191d93`](https://github.com/ni-kismet/systemlink-cli/commit/b191d93fa9a1aca9393aeb25b1da1c1b40307f30))

Fix feed package upload issues and add E2E tests

### Chores

- **release**: 0.16.1
  ([`74b022a`](https://github.com/ni-kismet/systemlink-cli/commit/74b022aa615bdda5d5efdec108e21545ba161735))


## v0.16.0 (2025-12-12)

### Chores

- **release**: 0.16.0
  ([`81ff4e7`](https://github.com/ni-kismet/systemlink-cli/commit/81ff4e734cec511eb32c546d137565dbee8ad7cb))

### Features

- Mvp feed support
  ([`194cf91`](https://github.com/ni-kismet/systemlink-cli/commit/194cf91f268926a8f47f3ba59ed2242982a0546c))


## v0.15.0 (2025-12-12)

### Bug Fixes

- Address remaining PR review comments
  ([`4cadd1e`](https://github.com/ni-kismet/systemlink-cli/commit/4cadd1e6f3c18eb061e413cf8f8074c73800f13a))

- Fix SLE/SLS URL detection inconsistency in conftest.py - Extract _is_sle_url() helper using same
  patterns as platform.py - Only specific URL patterns (api.systemlink.io,
  *-api.lifecyclesolutions.ni.com) are classified as SLE, matching production detection logic

- Improve info command table formatting - Add detailed comment explaining why table_utils is not
  used (designed for list-style output, not key-value display) - Extract truncate() helper function
  for cleaner code - Use variables for magic numbers (max_value_width, content_width)

- Improve platform detection reliability and address PR feedback
  ([`69c0dc8`](https://github.com/ni-kismet/systemlink-cli/commit/69c0dc89b581dfdcdc3bc29a00d8a06210dd3dc4))

- Add SYSTEMLINK_PLATFORM env var for explicit platform specification - Update detection priority:
  explicit env var > keyring config > URL fallback - Add explicit platform field to e2e config
  template and CLI runner - Add explanatory comment for bare except clause in _get_keyring_config -
  Fix return type annotations (Optional[str]) in test_info_command.py - Update _make_cli_runner to
  pass SYSTEMLINK_PLATFORM when specified

This makes platform detection more reliable by preferring explicit specification over URL pattern
  matching, which is brittle since both SLE and SLS can be installed on arbitrary servers/DNS names.

- Exclude e2e tests from default pytest run
  ([`1e50650`](https://github.com/ni-kismet/systemlink-cli/commit/1e50650cef7362b0483ce14d23d63e718e99bc5f))

Configure pytest to only run unit tests by default: - Add --ignore=tests/e2e to addopts - Set
  testpaths to tests/unit - Add missing pytest markers (sls, sle, file)

E2E tests can still be run explicitly with: poetry run pytest tests/e2e/

- E2e tests for dual SLE/SLS configuration
  ([`8b2289a`](https://github.com/ni-kismet/systemlink-cli/commit/8b2289a33d4f0d2a410ea8ea2de637dea9d7d762))

- Fix credential lookup order: env vars now checked before keyring - Add dynamic platform detection
  from URL for runtime overrides - Fix URL patterns to correctly distinguish SLE cloud from SLS
  on-prem - Fix e2e test fixtures to use correct env var (SYSTEMLINK_API_URL) - Update tests to use
  configured_workspace fixture - Add confirmation input for notebook delete commands in tests -
  Update unit tests for new URL pattern detection

- Address PR review comments and merge with main
  ([`c0b2873`](https://github.com/ni-kismet/systemlink-cli/commit/c0b2873104629205cf85314e320755e7a5646774))

- Remove duplicate is_sls variable in notebook_click.py start command - Fix return type annotation
  in test_info_command.py (Optional[str]) - Add explanatory comment for bare except clause in
  platform.py - Merge with main branch (resolve conflict in conftest.py markers)

### Chores

- **release**: 0.15.0
  ([`0b397b4`](https://github.com/ni-kismet/systemlink-cli/commit/0b397b401e7ad8d315bc579851c0daebbf2e8214))

### Refactoring

- Address remaining PR review feedback
  ([`c4a7b3e`](https://github.com/ni-kismet/systemlink-cli/commit/c4a7b3e7b0d67c8829f227f2cc353429dccacdc0))

- Move 'os' import to module level in platform.py - Rename 'maybe' variable to 'config_url' in
  utils.py for clarity - Update URL encoding comments for accuracy (safe='') - Fix trailing space in
  error message - Remove duplicate API comments in notebook_click.py - Update SLE comment to 'cloud
  and hosted' for accuracy - Extract _build_create_execution_payload helper function - Extract
  _parse_execution_response helper function - Add explicit platform='SLE' to DFF test for clarity -
  Improve retry test assertions with exit code verification - Update configured_workspace fixture
  docstring for clarity


## v0.14.0 (2025-12-10)

### Bug Fixes

- Address PR review feedback
  ([`bbc50ec`](https://github.com/ni-kismet/systemlink-cli/commit/bbc50ec483cb2c1a160b6a6835cd271f63fadaa5))

- Fix --name/--properties priority: --name flag now takes precedence - Add test for --name +
  --properties combination - Update watchdog version constraint to ^6.0.0 - Fix README query filter
  syntax to use search-files format - Fix README --order-by example to use separate flags - Add
  --filter example to file list documentation - Add test for upload nonexistent file error handling
  - Handle duplicate filenames in move-to directory - Add comments to empty except clauses in E2E
  tests

### Chores

- **release**: 0.14.0
  ([`44eb88f`](https://github.com/ni-kismet/systemlink-cli/commit/44eb88f581bacb4c24ebfe4da84c12ea8e936ee7))

- **deps**: Bump urllib3 from 2.5.0 to 2.6.0
  ([`e055ea3`](https://github.com/ni-kismet/systemlink-cli/commit/e055ea329f5f2e8cbb266752bae35cdeb57ace71))

Bumps [urllib3](https://github.com/urllib3/urllib3) from 2.5.0 to 2.6.0. - [Release
  notes](https://github.com/urllib3/urllib3/releases) -
  [Changelog](https://github.com/urllib3/urllib3/blob/main/CHANGES.rst) -
  [Commits](https://github.com/urllib3/urllib3/compare/2.5.0...2.6.0)

--- updated-dependencies: - dependency-name: urllib3 dependency-version: 2.6.0 dependency-type:
  indirect ...

Signed-off-by: dependabot[bot] <support@github.com>

### Features

- Add file management commands
  ([`9e9f6b4`](https://github.com/ni-kismet/systemlink-cli/commit/9e9f6b474a22af26c8744d13015b9801eab36efd))

Add comprehensive file management CLI commands for SystemLink File Service:

Commands: - file list: List files with filtering by workspace, name, extension - file get: Get
  detailed metadata for a single file - file upload: Upload files with optional workspace and
  properties - file download: Download files with force overwrite option - file delete: Delete files
  with confirmation prompt - file query: Query files with search expressions - file update-metadata:
  Update file name and properties - file watch: Watch folder and auto-upload new files (requires
  watchdog)

Features: - Uses performant /search-files endpoint instead of /query-files-linq - Supports workspace
  filtering by name or ID (resolves names to IDs) - Full UUID display in table output (36 chars) -
  Dot file filtering in watch command (ignores .DS_Store etc) - Debounce support in watch command to
  handle file write completion - Move-to or delete-after-upload options in watch command

Tests: - 31 unit tests covering all file commands - 12 E2E tests against dev tier

Dependencies: - watchdog ~=6.0.0 (optional, for watch command)

- **notebook**: Add SLS support for notebook commands and fix e2e test fixtures
  ([`1a50ced`](https://github.com/ni-kismet/systemlink-cli/commit/1a50cedc5181111bd7e48279354a3ccf1f6db4a1))

- Add platform-aware notebook management APIs (SLS uses path-based endpoints) - Add platform-aware
  notebook execution APIs (SLS uses ninbexec/v2) - Fix URL encoding for SLS notebook paths (encode
  all characters including /) - Handle SLS response formats (list vs wrapped object) - Add SLS
  guards for unsupported operations (create, update, delete, retry) - Update e2e config to support
  both SLE and SLS servers simultaneously - Add platform-specific CLI runners and fixtures for e2e
  tests - Fix DFF tests to mock keyring with SLE platform for feature gating - Update
  test_utils.patch_keyring to return SLE platform by default

- Add platform detection and feature gating for SLE/SLS
  ([`3bf8c7c`](https://github.com/ni-kismet/systemlink-cli/commit/3bf8c7c573c9c9daaf766a3b0587b3a404f344f6))

Implements Issue #25 Phase 1 & 2:

## Platform Detection - Auto-detect platform during `slcli login` by probing /niworkorder endpoint -
  URL pattern matching as fallback (*.systemlink.io -> SLE) - Store platform in keyring config

## New Commands - `slcli info`: Shows current config, platform, and feature availability - Supports
  --format table|json

## Feature Gating - Gate SLE-only commands: dff, template, workflow, function - Graceful error
  messages for unavailable features on SLS - Commands still show in --help (not hidden)

## New Module: slcli/platform.py - Platform constants: PLATFORM_SLE, PLATFORM_SLS, PLATFORM_UNKNOWN
  - detect_platform(): Probes endpoints to identify platform - get_platform(): Get stored platform
  from keyring - has_feature(): Check feature availability - require_feature(): Exit gracefully if
  feature unavailable - get_platform_info(): Get full platform details for info command

## Tests - 32 new unit tests for platform detection and feature gating - 100% coverage on
  platform.py module - All 166 tests passing

### Refactoring

- Align CLI commands with best practices
  ([`db257af`](https://github.com/ni-kismet/systemlink-cli/commit/db257af570fce54c38280e295a63286d0f80a3b4))

- Add confirmation prompts to delete commands (notebook, templates, workflows, webapp) - Replace
  raise click.ClickException with sys.exit(ExitCodes.*) for proper exit codes - Hide function
  command from top-level help (still accessible) - Fix -fmt/-f conflict in function execute commands
  (remove -f from format to avoid conflict with --function-id) - Add ExitCodes import to
  workflows_click.py - Update tests to handle confirmation prompts and correct exit codes


## v0.13.0 (2025-12-09)

### Chores

- **release**: 0.13.0
  ([`e162785`](https://github.com/ni-kismet/systemlink-cli/commit/e162785d6763d7bfbe2e8fb857ac6fce55aba195))

### Features

- **user**: Add service account support
  ([`3c9602e`](https://github.com/ni-kismet/systemlink-cli/commit/3c9602e1362df176fcda9c6a9bae948ac733d738))

Add support for service accounts (type: service) to user management commands.

## Changes

### user create - Add --type option (user/service) with interactive prompt - Add --login and --phone
  options for regular users - Service accounts default lastName to 'ServiceAccount' - Validate that
  service accounts cannot have email/phone/niuaId/login

### user list - Add --type filter (all/user/service) to filter by account type - Add ID column to
  table output - Add Type column showing 'User' or 'Service' - Update --filter to search across
  firstName, lastName, and email

### user get - Show 'Service Account Details:' header for service accounts - Display account type in
  output

### user update - Validate that service accounts cannot be updated with email/phone/niuaId/login -
  Add --login, --phone, --niua-id options

## Testing - Add TestServiceAccounts class with 8 new tests - Update existing tests to include
  --type option - All 133 unit tests pass


## v0.12.2 (2025-10-06)

### Bug Fixes

- Add name filter to DFF list command
  ([`98bf939`](https://github.com/ni-kismet/systemlink-cli/commit/98bf939cd110a05c5acbb8784df4fdb3b413d97c))

### Chores

- **release**: 0.12.2
  ([`4149479`](https://github.com/ni-kismet/systemlink-cli/commit/4149479fabe1b8580807776483cd11ac3a24b040))


## v0.12.1 (2025-09-23)

### Bug Fixes

- Webapp list totals
  ([`382f7d8`](https://github.com/ni-kismet/systemlink-cli/commit/382f7d80e26f2ed9e114f3bda15a48d6140efa12))

### Chores

- **release**: 0.12.1
  ([`9d9e30b`](https://github.com/ni-kismet/systemlink-cli/commit/9d9e30bbddf5cbe0465c863c41789162ea6a0a01))


## v0.12.0 (2025-09-23)

### Chores

- **release**: 0.12.0
  ([`1587d87`](https://github.com/ni-kismet/systemlink-cli/commit/1587d8707066075c964bf91e23718e7f65c3d679))

### Features

- Add webapp commands
  ([`4c74f72`](https://github.com/ni-kismet/systemlink-cli/commit/4c74f72560a42e52c8c47391356fe28dd6674dbe))

Add webapp commands


## v0.11.3 (2025-09-22)

### Bug Fixes

- **e2e**: Remove duplicate pytest.fixture decorator
  ([`be9ed09`](https://github.com/ni-kismet/systemlink-cli/commit/be9ed094c3321302d3253c3c04c180f5ba607248))

### Chores

- **release**: 0.11.3
  ([`1857c3a`](https://github.com/ni-kismet/systemlink-cli/commit/1857c3a32d3d9e6e083369cc1a59748b1d177603))

- **types**: Add types-requests and types-tabulate to dev deps for mypy in CI
  ([`191b970`](https://github.com/ni-kismet/systemlink-cli/commit/191b9700a65df02088a999217ba660f2779937b5))

- **lint**: Fix import ordering and docstring/format issues
  ([`f432ef6`](https://github.com/ni-kismet/systemlink-cli/commit/f432ef6e216f59938cdd93e0408f5fcf779dd1c5))


## v0.11.2 (2025-09-10)

### Bug Fixes

- Substate workflow generation
  ([`8b162d4`](https://github.com/ni-kismet/systemlink-cli/commit/8b162d44c6e37e046990fb019b6956a74c2e1140))

### Chores

- **release**: 0.11.2
  ([`f38a9b9`](https://github.com/ni-kismet/systemlink-cli/commit/f38a9b9a91db4d0298269e1c6e78158937796765))


## v0.11.1 (2025-09-10)

### Bug Fixes

- Import error
  ([`7ff4ee2`](https://github.com/ni-kismet/systemlink-cli/commit/7ff4ee2a86aac5c093ea62ab2b465ebbb83d5161))

### Chores

- **release**: 0.11.1
  ([`b4cbe50`](https://github.com/ni-kismet/systemlink-cli/commit/b4cbe50b41fd60f396ec70f39d982ed18f2209ea))


## v0.11.0 (2025-09-09)

### Chores

- **release**: 0.11.0
  ([`e009a28`](https://github.com/ni-kismet/systemlink-cli/commit/e009a28ffeff6d55c0fb18f79f79b8e1f2b2023e))

### Features

- Merge pull request #16 from ni-kismet/users/fvisser/system-cert-store
  ([`e979420`](https://github.com/ni-kismet/systemlink-cli/commit/e979420407ae9ee4484fcf9019c89e30d5c8f6e3))

System trust store integration, diagnostics, and resilient injection


## v0.10.0 (2025-09-03)

### Chores

- **release**: 0.10.0
  ([`ad49d5d`](https://github.com/ni-kismet/systemlink-cli/commit/ad49d5d07f8aba574b96927a6ce0358c6e8486f9))

### Features

- Notebook execution commands
  ([`19562f1`](https://github.com/ni-kismet/systemlink-cli/commit/19562f154168cc2403f708057fb46daa6671f1ef))


## v0.9.0 (2025-09-02)

### Chores

- **release**: 0.9.0
  ([`446252f`](https://github.com/ni-kismet/systemlink-cli/commit/446252fac98d71dcec5baf67c83fb867b9362e9e))

### Features

- Merge pull request #13 from ni-kismet/users/fvisser/workflow-mermaid
  ([`8e56902`](https://github.com/ni-kismet/systemlink-cli/commit/8e56902f909075cdfff2d69c4453c741058406f4))

Add workflow preview command

- Flag consistency
  ([`92cd016`](https://github.com/ni-kismet/systemlink-cli/commit/92cd016cee143b8a6946e17b9f8ed7c08a880223))


## v0.8.0 (2025-08-22)

### Chores

- **release**: 0.8.0
  ([`b764195`](https://github.com/ni-kismet/systemlink-cli/commit/b76419509f3f7b32724dcd29ba6892bbf5d57b1d))

### Features

- Review feedback
  ([`31719bc`](https://github.com/ni-kismet/systemlink-cli/commit/31719bcf1498b5c65b10ab376fec0c411734c33e))


## v0.7.6 (2025-08-04)

### Bug Fixes

- Minor help strings
  ([`aa4b836`](https://github.com/ni-kismet/systemlink-cli/commit/aa4b8368c0f81fd06601098b3d9756e5f8bdf2f1))

### Chores

- **release**: 0.7.6
  ([`c65b127`](https://github.com/ni-kismet/systemlink-cli/commit/c65b12713e428b18032bd76f9f28e12ad88375b0))


## v0.7.5 (2025-08-04)

### Bug Fixes

- Ascii title card
  ([`f051059`](https://github.com/ni-kismet/systemlink-cli/commit/f0510594f4ca8a015829c8dc1eea743194526bc2))

### Chores

- **release**: 0.7.5
  ([`6dc5c02`](https://github.com/ni-kismet/systemlink-cli/commit/6dc5c02899c478e321cc7d764efe83051c639804))


## v0.7.4 (2025-07-31)

### Bug Fixes

- Completion script for older bash environments
  ([`d101c4c`](https://github.com/ni-kismet/systemlink-cli/commit/d101c4cc8ccf577470a2d0da80bc400bf1c1972d))

### Chores

- **release**: 0.7.4
  ([`18e99c8`](https://github.com/ni-kismet/systemlink-cli/commit/18e99c804def868fafc387a40f1ef16b8cafaa33))


## v0.7.3 (2025-07-30)

### Bug Fixes

- Pagination issues across different services
  ([`33bc357`](https://github.com/ni-kismet/systemlink-cli/commit/33bc3575f0471189229186f52dcf375fa4192f4f))

### Chores

- **release**: 0.7.3
  ([`9c5a61e`](https://github.com/ni-kismet/systemlink-cli/commit/9c5a61e513f4942609a28c1909ea986fa968e253))


## v0.7.2 (2025-07-30)

### Bug Fixes

- E2e testing and minor exposed issues
  ([`ad0b9c6`](https://github.com/ni-kismet/systemlink-cli/commit/ad0b9c608763e97dc026c02cdc0c3190bd01c150))

### Chores

- **release**: 0.7.2
  ([`d725647`](https://github.com/ni-kismet/systemlink-cli/commit/d72564774434e2b35ccc85c27ca22d7dc77781e2))


## v0.7.1 (2025-07-29)

### Bug Fixes

- Refactor changes
  ([`cd54fd5`](https://github.com/ni-kismet/systemlink-cli/commit/cd54fd5f2a7bb13f4bf38a82257b74f617c74e29))

### Chores

- **release**: 0.7.1
  ([`b2a3e79`](https://github.com/ni-kismet/systemlink-cli/commit/b2a3e79f385d85ccf6f2934313ddbd77c26e0d54))


## v0.7.0 (2025-07-29)

### Chores

- **release**: 0.7.0
  ([`fd79504`](https://github.com/ni-kismet/systemlink-cli/commit/fd79504248fe4fb099bd530d41a0585af920d2b9))

### Features

- Add dff commands
  ([`657f22c`](https://github.com/ni-kismet/systemlink-cli/commit/657f22cdb957828459e5e0602b8f32af665d37d9))


## v0.6.0 (2025-07-28)

### Chores

- **release**: 0.6.0
  ([`0ec4be0`](https://github.com/ni-kismet/systemlink-cli/commit/0ec4be00093e337537ae5cde36535aeec645c887))

### Features

- Add terminal completion support
  ([`63e450b`](https://github.com/ni-kismet/systemlink-cli/commit/63e450bef1bc53833648f4c0a87540afca12e04b))


## v0.5.0 (2025-07-28)

### Chores

- **release**: 0.5.0
  ([`0a32ec4`](https://github.com/ni-kismet/systemlink-cli/commit/0a32ec405a012db7144a7e7380006df1241f0145))

### Features

- Add user management
  ([`1b383cd`](https://github.com/ni-kismet/systemlink-cli/commit/1b383cdf9ef8f9492650c981c72a51650afaaccd))


## v0.4.2 (2025-07-25)

### Bug Fixes

- Token
  ([`1df6b3a`](https://github.com/ni-kismet/systemlink-cli/commit/1df6b3a5f03f3715ecb29ed4ed144eed94251f90))

### Chores

- **release**: 0.4.2
  ([`e168798`](https://github.com/ni-kismet/systemlink-cli/commit/e168798594f6b069aab39132055572e1ceb95bd8))


## v0.4.1 (2025-07-25)

### Bug Fixes

- Tweak semantic release
  ([`f36aba3`](https://github.com/ni-kismet/systemlink-cli/commit/f36aba31b3727b41fd9f67ab44a4993677a7a3f9))

### Chores

- **release**: 0.4.1
  ([`0722281`](https://github.com/ni-kismet/systemlink-cli/commit/0722281b1721d0519e65e80b7c1d3144a742e216))


## v0.4.0 (2025-07-25)

### Bug Fixes

- Semantic versioning
  ([`49d0b1e`](https://github.com/ni-kismet/systemlink-cli/commit/49d0b1efd5907fa0154fc54edf6a83a7e86f171c))

### Chores

- **release**: 0.4.0
  ([`daaec03`](https://github.com/ni-kismet/systemlink-cli/commit/daaec03249a91044d32f9858569098d0bc4d5f07))

### Features

- Adding semantic release for automated version updates
  ([`c9904a7`](https://github.com/ni-kismet/systemlink-cli/commit/c9904a7f4c101560502dc9dd6d2ebc0026e36c7b))


## v0.3.1 (2025-07-25)


## v0.3.0 (2025-07-25)


## v0.2.3 (2025-07-24)


## v0.2.2 (2025-07-24)


## v0.2.1 (2025-07-24)


## v0.2.0 (2025-07-23)


## v0.1.2 (2025-07-21)


## v0.1.1 (2025-07-21)


## v0.1.0 (2025-07-21)
