# CHANGELOG


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
