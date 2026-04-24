---
name: nipkg-file-package
description: >-
  Build NI Package Manager file packages (.nipkg) for Windows and SystemLink deployment.
  Use when the user asks to assemble a file package, troubleshoot nipkg pack errors,
  choose installation target roots, create control or instructions metadata, or package
  a Python or test application for feed upload. Covers source tree layout, target root
  selection, build script structure, and common NI Package Manager CLI pitfalls.
---

# Building NI File Packages

Use this skill when the task is specifically about assembling or troubleshooting an
NI Package Manager file package.

## When to Use

- Creating a `.nipkg` from a folder of source files
- Building a deployable package for SystemLink feeds
- Choosing the correct `data/<target-root>/...` layout
- Fixing `nipkg pack` validation failures
- Adding package metadata, install scripts, or uninstall scripts

## Core Rules

1. A file package must contain these top-level entries before packing:
   - `debian-binary`
   - `control/`
   - `data/`
2. The control file must include `XB-Plugin: file`.
3. `nipkg pack` takes a source directory and a destination directory.
   - Use: `nipkg pack <source-dir> <destination-dir>`
   - Do not pass a full `.nipkg` file path as the second argument.
4. On Windows, files under `data/` must use NI Package Manager target root names.
   - `ProgramFiles` is valid.
   - `Program Files` is not valid.
5. For `Architecture: windows_all`, do not use 64-bit-only roots such as `ProgramFiles_64`.

## Required Package Layout

```text
<package-root>/
├── debian-binary
├── control/
│   ├── control
│   ├── instructions
│   ├── postinstall.bat        # optional
│   └── preuninstall.bat       # optional
└── data/
    └── ProgramFiles/
        └── NI/
            └── <package-name>/
                ├── main.py
                ├── requirements.txt
                └── ...
```

The `debian-binary` file should contain:

```text
2.0
```

## Minimal Control File

```text
Package: my-package
Version: 1.0.0
Section: test-applications
Architecture: windows_all
Maintainer: Team Name <team@example.com>
XB-Plugin: file
XB-UserVisible: yes
Description: Short description
 Extended description on the following lines.
```

**Note on `Depends`**: Only add `Depends:` entries for packages that are guaranteed to
exist in a registered feed on every target system. `ni-python` is not always available;
if you manage Python installation separately (e.g. via a Salt state), omit that dependency
and handle it through the deployment state instead.

## Minimal Instructions File

```ini
[Instructions]
postinstall=postinstall.bat
preuninstall=preuninstall.bat
```

## Windows Target Roots

Use the root names exactly as NI Package Manager expects under `data/`.

- `ProgramFiles` maps to `%SystemDrive%\Program Files` on 64-bit Windows and is equivalent to `ProgramFiles_64`
- `ProgramFiles_32` maps to `%SystemDrive%\Program Files (x86)`
- `ProgramData` maps to `%SystemDrive%\ProgramData`
- `Documents` maps to `%PUBLIC%\Documents`
- `Desktop` maps to `%PUBLIC%\Desktop`
- `Home` maps to `%PUBLIC%`
- `ProgramMenu` maps to `%ProgramData%\Microsoft\Windows\Start Menu\Programs`
- `Startup` maps to `%ProgramData%\Microsoft\Windows\Start Menu\Programs\StartUp`
- `System` is a toggling root for the Windows system directory

For NI-managed locations, use NIPaths roots prefixed with `ni-paths-`, for example:

- `ni-paths-NIPUBAPPDATADIR`
- `ni-paths-NIPMDIR`
- `ni-paths-NISHAREDDIR`

## Recommended Build Script Pattern

```bat
@echo off
setlocal enableextensions

set SCRIPT_DIR=%~dp0
set BUILD_DIR=%SCRIPT_DIR%build\nipkg
set DIST_DIR=%SCRIPT_DIR%dist
set DATA_DIR=%BUILD_DIR%\data\ProgramFiles\NI\my-package
set CONTROL_DIR=%BUILD_DIR%\control
set NIPKG_EXE=nipkg

where nipkg >nul 2>nul
if %ERRORLEVEL% NEQ 0 (
    if exist "C:\Program Files\National Instruments\NI Package Manager\nipkg.exe" (
        set NIPKG_EXE=C:\Program Files\National Instruments\NI Package Manager\nipkg.exe
    ) else (
        echo NI Package Manager CLI not found.
        exit /b 1
    )
)

if exist "%BUILD_DIR%" rmdir /s /q "%BUILD_DIR%"
if exist "%DIST_DIR%" rmdir /s /q "%DIST_DIR%"

mkdir "%DATA_DIR%"
mkdir "%CONTROL_DIR%"
mkdir "%DIST_DIR%"
> "%BUILD_DIR%\debian-binary" echo 2.0

REM Copy payload files into %DATA_DIR%
REM Copy control metadata into %CONTROL_DIR%

"%NIPKG_EXE%" pack "%BUILD_DIR%" "%DIST_DIR%"
```

## Common Failures and Fixes

- `nipkg is not recognized`
  - Call `C:\Program Files\National Instruments\NI Package Manager\nipkg.exe` directly or add it to `PATH`.
- `The specified path ... is invalid`
  - The second `nipkg pack` argument should be a destination directory, not a full `.nipkg` filename.
- `Unknown root name: program files`
  - Use `ProgramFiles`, not `Program Files`.
- Root validation failures with `windows_all`
  - Avoid `_64`-only roots such as `ProgramFiles_64`.
- `Required package not found: 'ni-python (>= 3.10)'`
  - Remove the `Depends: ni-python` line from the control file. Install Python via a Salt state or other mechanism instead.

## Verification Steps

1. Run the build script.
2. Confirm a `.nipkg` appears in `dist/`.
3. Unpack it to verify the structure:

```powershell
& "C:\Program Files\National Instruments\NI Package Manager\nipkg.exe" unpack \
  "dist\my-package_1.0.0_windows_all.nipkg" \
  "build\verify-package"
```

4. Check that the unpacked package contains:
   - `control/control`
   - `debian-binary`
   - `data/ProgramFiles/...`

## SystemLink Context

For SystemLink deployment, file packages are appropriate when the application payload is a
set of files to be installed directly onto the test system, such as Python source, batch
scripts, configuration files, and requirements manifests. After building the `.nipkg`, upload
it to a feed with `slcli feed package upload` and deploy it through SystemLink software
deployment.

### Creating and Populating a Feed

**Feed naming rules** — Feed names must start with an alphabetical character and may only
contain alphanumeric characters, spaces, underscores, and hyphens. Names starting with a
digit (e.g. `18650 Battery Test`) are rejected with `InvalidFeedName`. Use a name like
`Battery-Test-18650` instead.

**Creating a feed via API** (when `slcli feed create` returns 400 due to workspace issues):

```python
# POST /nifeed/v1/feeds
body = {
    "name": "Battery-Test-18650",
    "description": "Feed for the test package",
    "platform": "WINDOWS",       # or NI_LINUX_RT
    "workspace": "<workspace-id>",  # UUID from /niuser/v1/workspaces
}
```

**Uploading a package to a feed via API**:

```python
# POST /nifeed/v1/feeds/<FEED_ID>/packages
# multipart/form-data with field name "package" (not "file")
```

**Feed URL for nipkg** — The URI to register on target systems (note: `/files` not `/packages`):
```
https://<server>/nifeed/v1/feeds/<FEED_ID>/files
```

**Workspace ID lookup** — Use `GET /niuser/v1/workspaces` (not `/niauth/v1/workspaces`,
which may 404 on some SLE versions).

## Salt State (SLS) Deployment

When the target system needs prerequisites (e.g. Python) that are not available as nipkg
dependencies, create a Salt state file (`deploy/install.sls`) and apply it through
SystemLink Systems Manager. A typical SLS for a Python test package covers:

1. **Download and install Python** — use the official Windows installer with `/quiet`,
   `InstallAllUsers=1`, `PrependPath=1`. For `TargetDir`, pass the full
   `key=value` as one quoted argument when using `Program Files`:
   ```yaml
   install-python:
     cmd.run:
       - name: >-
           "C:\Windows\Temp\python-3.12.9-amd64.exe"
           /quiet
           InstallAllUsers=1
           PrependPath=1
           "TargetDir=C:\Program Files\Python312"
           Include_launcher=1
       - shell: cmd
       - unless: >-
           powershell -Command "$r64 = Get-ChildItem 'HKLM:\SOFTWARE\Python\PythonCore' -ErrorAction SilentlyContinue; if ($r64) { exit 0 }; $r32 = Get-ChildItem 'HKLM:\SOFTWARE\WOW6432Node\Python\PythonCore' -ErrorAction SilentlyContinue; if ($r32) { exit 0 }; if (Test-Path 'C:\Program Files\Python312\python.exe') { exit 0 }; exit 1"
   ```
   **Critical**: In SystemLink/Salt `cmd.run` contexts, keep `TargetDir` as a single
   quoted argument (for example `"TargetDir=C:\Program Files\Python312"`) and verify
   install path checks.

2. **Add Python to PATH** — `win_path.exists` for both the install dir and `Scripts\`.

3. **Register the SystemLink feed** — prefer `module.run` / `pkg.mod_repo` over
   `pkgrepo.managed`. On some SystemLink-managed systems the nipkg `pkg` module
   requires `alias` as a positional argument; `pkgrepo.managed` passes it as a keyword
   and raises `TypeError: get_repo() missing 1 required positional argument: 'alias'`.
   Use the nested list syntax to avoid this:
   ```yaml
   add-my-feed:
     module.run:
       - pkg.mod_repo:
         - alias: My-Feed-Name
         - uri: "https://<server>/nifeed/v1/feeds/<FEED_ID>/files"
         - enabled: true
         - compressed: false
         - trusted: true
       - require:
         - cmd: install-python
   ```
   The `require` reference type for this state is `module` (not `pkgrepo`):
   ```yaml
   install-my-package:
     pkg.installed:
       - require:
         - module: add-my-feed
   ```

4. **Install the nipkg** — use `pkg.installed` (not `cmd.run` with `nipkg install`).
   Pin versions and set `install_recommends`:
   ```yaml
   packages:
     pkg.installed:
       - install_recommends: true
       - pkgs:
         - my-package: 1.0.0
       - require:
         - module: my-feed-state-id
   ```

   **Important**: Always use `module.run`/`pkg.mod_repo` and `pkg.installed` for feed
   registration and package installation. These are the native Salt states that SystemLink
   expects. Using `cmd.run` with `nipkg.exe` directly bypasses Salt's package management
   and won't be tracked properly by SystemLink Systems Manager.

5. **Create venv and install pip deps** — always pass `--clear` to `python -m venv` to
   rebuild a broken or partially-created venv from a previous failed run. Use
   `python -m ensurepip --upgrade` before `pip install` in case the venv was created
   without pip. Use `python -m pip install` (not `pip.exe`) so the venv's pip is used:
   ```yaml
   create-venv:
     cmd.run:
       - name: >-
           "C:\Program Files\Python312\python.exe" -m venv
           --clear
           "C:\Program Files\NI\my-package\venv"
       - require:
         - pkg: install-my-package

   ensure-venv-pip:
     cmd.run:
       - name: >-
           "C:\Program Files\NI\my-package\venv\Scripts\python.exe"
           -m ensurepip --upgrade
       - unless: powershell -Command "Test-Path 'C:\Program Files\NI\my-package\venv\Scripts\pip.exe'"
       - require:
         - cmd: create-venv

   install-pip-deps:
     cmd.run:
       - name: >-
           "C:\Program Files\NI\my-package\venv\Scripts\python.exe"
           -m pip install --no-cache-dir
           -r "C:\Program Files\NI\my-package\requirements.txt"
       - require:
         - cmd: ensure-venv-pip
   ```

   **Note**: Do NOT add an `unless` guard to `create-venv`. Always rebuild the venv on
   every state apply to recover from broken states. If the venv directory exists but
   `python.exe` or `pip.exe` is missing (e.g. from a previous aborted install), the
   `unless` guard will skip creation and subsequent steps will fail silently.

## Auto-Versioning Build Script Pattern

Use an incrementing build counter stored in `package/build_number.txt` alongside a base
version in `package/version.txt`. This produces short, valid Debian version strings
(`major.minor.patch.build`) that NI Package Manager and SystemLink accept reliably.

**Why not timestamps?** A timestamp-based suffix like `1.0.0.20260420083348` exceeds the
length that SystemLink's `pkg.installed` Salt state can resolve correctly. The feed lookup
fails silently and the state reports the package as not found. Always use a short numeric
build counter instead.

### File layout

```text
package/
├── version.txt        # base version, e.g. "1.0.1"  (edit when bumping major/minor/patch)
├── build_number.txt   # next build number to use, e.g. "0"  (auto-incremented by build script)
├── control
├── instructions
├── postinstall.bat
└── preuninstall.bat
```

If your build script stamps versions through `control.template`, keep
`control.template` in source control as the input template and write the stamped
result to `control` during the build.

### Build script snippet

```bat
set SCRIPT_DIR=%~dp0
set CONTROL_DIR=%SCRIPT_DIR%build\nipkg\control
set DEPLOY_SLS=%SCRIPT_DIR%deploy\install.sls
set VERSION_FILE=%SCRIPT_DIR%package\version.txt
set BUILD_NUMBER_FILE=%SCRIPT_DIR%package\build_number.txt
set BASE_VERSION=
set NEXT_BUILD=

set /p BASE_VERSION=<"%VERSION_FILE%"
set /p NEXT_BUILD=<"%BUILD_NUMBER_FILE%"
if "%BASE_VERSION%"=="" (
    echo Failed to read package\version.txt.
    exit /b 1
)
if "%NEXT_BUILD%"=="" set NEXT_BUILD=0
set PACKAGE_VERSION=%BASE_VERSION%.%NEXT_BUILD%
set /a WRITE_BUILD=%NEXT_BUILD%+1
echo %WRITE_BUILD%>"%BUILD_NUMBER_FILE%"
echo Version for this build: %PACKAGE_VERSION%

REM Stamp version into control file
powershell -NoProfile -Command ^
  "$p='%CONTROL_DIR%\control.template'; $o='%CONTROL_DIR%\control'; (Get-Content -Raw $p) -replace '(?m)^Version:\s*.*$','Version: %PACKAGE_VERSION%' | Set-Content -Encoding ASCII $o"

REM Stamp version into deploy\install.sls (keeps SLS in sync with feed)
powershell -NoProfile -Command ^
  "$p='%DEPLOY_SLS%'; (Get-Content -Raw $p) -replace '(?m)^\s*-\s*my-package:\s*.*$','      - my-package: %PACKAGE_VERSION%' | Set-Content -Encoding ASCII $p"
```

### Workflow

1. On the first build: `version.txt` = `1.0.1`, `build_number.txt` = `0` → produces `1.0.1.0`, writes `1` back.
2. On the next build: reads `1`, produces `1.0.1.1`, writes `2` back, and so on.
3. To bump major/minor/patch: edit `version.txt` and reset `build_number.txt` to `0`.
4. Commit both files so the counter is shared across machines / CI runs.

## Complete Working SLS Example

The following SLS is the verified working pattern for deploying a Python test package
to a SystemLink-managed Windows target. Copy and adapt it for new tests.

```yaml
# ---------- 1. Install Python 3.12.9 ----------

download-python-installer:
  file.managed:
    - name: 'C:\Windows\Temp\python-3.12.9-amd64.exe'
    - source: 'https://www.python.org/ftp/python/3.12.9/python-3.12.9-amd64.exe'
    - skip_verify: True
    - unless: >-
        powershell -Command "& 'C:\Program Files\Python312\python.exe' --version 2>&1 | Select-String -Quiet '3.12.9'"

install-python:
  cmd.run:
    - name: >-
        "C:\Windows\Temp\python-3.12.9-amd64.exe"
        /quiet
        InstallAllUsers=1
        PrependPath=1
        "TargetDir=C:\Program Files\Python312"
        Include_launcher=1
    - shell: cmd
    - unless: >-
        powershell -Command "$r64 = Get-ChildItem 'HKLM:\SOFTWARE\Python\PythonCore' -ErrorAction SilentlyContinue; if ($r64) { exit 0 }; $r32 = Get-ChildItem 'HKLM:\SOFTWARE\WOW6432Node\Python\PythonCore' -ErrorAction SilentlyContinue; if ($r32) { exit 0 }; if (Test-Path 'C:\Program Files\Python312\python.exe') { exit 0 }; exit 1"
    - require:
      - file: download-python-installer

add-python-to-path:
  win_path.exists:
    - name: 'C:\Program Files\Python312'
    - require:
      - cmd: install-python

add-python-scripts-to-path:
  win_path.exists:
    - name: 'C:\Program Files\Python312\Scripts'
    - require:
      - cmd: install-python

# ---------- 2. Register feed and install the test package ----------

add-my-test-feed:
  module.run:
    - pkg.mod_repo:
      - alias: My-Test-Feed
      - uri: "https://<server>/nifeed/v1/feeds/<FEED_ID>/files"
      - enabled: true
      - compressed: false
      - trusted: true
    - require:
      - cmd: install-python

install-my-test-package:
  pkg.installed:
    - install_recommends: true
    - pkgs:
      - my-package: 1.0.1.0
    - require:
      - module: add-my-test-feed

# ---------- 3. Create venv ----------

create-venv:
  cmd.run:
    - name: >-
        "C:\Program Files\Python312\python.exe" -m venv
        --clear
        "C:\Program Files\NI\my-package\venv"
    - require:
      - pkg: install-my-test-package

ensure-venv-pip:
  cmd.run:
    - name: >-
        "C:\Program Files\NI\my-package\venv\Scripts\python.exe"
        -m ensurepip --upgrade
    - unless: powershell -Command "Test-Path 'C:\Program Files\NI\my-package\venv\Scripts\pip.exe'"
    - require:
      - cmd: create-venv

install-pip-deps:
  cmd.run:
    - name: >-
        "C:\Program Files\NI\my-package\venv\Scripts\python.exe"
        -m pip
        install --no-cache-dir
        -r "C:\Program Files\NI\my-package\requirements.txt"
    - require:
      - cmd: ensure-venv-pip
```

**Key rules from testing:**
- Pass `TargetDir` as one quoted key/value argument when using `Program Files`
  (`"TargetDir=C:\Program Files\Python312"`) and keep explicit registry/path checks
  in `unless` guards.
- `unless` guards for Python install must check the registry AND the file path; using
  only `python --version` can match the Salt minion's bundled Python, not the system one.
- The `require` type for `pkg.installed` after `module.run` is `module:`, not `pkgrepo:`.
- Never use `pkgrepo.managed` on a nipkg-backed system — it calls `pkg.get_repo(alias=...)`
  as a keyword, but nipkg expects `alias` as a positional argument and raises a TypeError.
- `create-venv` has no `unless` guard — always rebuild. A partial venv from a prior
  aborted run has no `python.exe` or `pip.exe` but passes a `Test-Path` guard.


### SLS Requirements for SystemLink Import

**The SLS file MUST be valid YAML.** SystemLink's `import-state` endpoint validates the
file server-side and rejects anything that is not parseable as YAML.

- **No Jinja templates**: `{% set %}`, `{{ variable }}`, and Jinja filters are **not
  supported**. Hardcode all values (Python version, paths, URLs) directly.
- **Validate locally** before uploading: `python -c "import yaml; yaml.safe_load(open('install.sls'))"`
- **Salt state functions that work**: `cmd.run`, `file.managed`, `file.serialize`,
  `file.absent`, `win_path.exists`, `system.reboot`, `module.run`, `pkg.installed`
  — any valid Salt state module is accepted as long as the YAML parses.

### Uploading States to SystemLink

The SystemLink Systems State API (`/nisystemsstate/v1/`) provides two ways to create states:

#### Option 1: JSON API — Package/Feed States Only

`POST /nisystemsstate/v1/states` with a JSON body. This only supports `packages` and
`feeds` arrays for package/feed-only workflows. Use this when the state only needs to
install nipkg packages. For custom SLS uploads, continue using the verified
`module.run` + `pkg.mod_repo` pattern.

```python
state = {
    "name": "My State",
    "description": "...",
    "distribution": "WINDOWS",   # or NI_LINUXRT, ANY
    "architecture": "X64",       # or ARM, X86, ANY
    "feeds": [],
    "packages": [{"name": "my-package", "version": "1.0.0", "installRecommends": True}],
}
```

#### Option 2: Import State — Arbitrary SLS Content

`POST /nisystemsstate/v1/import-state` with `multipart/form-data`. This accepts any
valid YAML SLS file with custom Salt states (cmd.run, file.managed, etc.). States
created this way have `containsExtraOperations: true` in the response.

Required form fields:
- `Name` (string) — must be unique within the workspace
- `Distribution` (string) — `WINDOWS`, `NI_LINUXRT`, `NI_LINUXRT_NXG`, or `ANY`
- `Architecture` (string) — `X64`, `ARM`, `X86`, or `ANY`
- `File` (binary) — the `.sls` file
- `Description` (string, optional)

#### Option 3: Replace State Content

`POST /nisystemsstate/v1/replace-state-content` with `multipart/form-data`. Updates
an existing state's SLS content.

Required form fields:
- `Id` (string) — the state ID to update
- `File` (binary) — the new `.sls` file
- `ChangeDescription` (string, optional)

### Common API Pitfalls

- **Cloudflare blocks Python's default `urllib` User-Agent** on some SystemLink Enterprise
  instances. Set `User-Agent: SystemLink-CLI/1.0` or similar on all requests.
- **State names must be unique per workspace**. A duplicate name returns HTTP 409 Conflict.
  Delete the existing state first or use `replace-state-content` to update it.
- **Authentication**: Use the `x-ni-api-key` header. On SLE instances the API URL may
  differ from the web URL (e.g. `demo-api.example.com` vs `demo.example.com`).
- **Credential discovery**: Use `nisystemlink.clients.core.HttpConfigurationManager` to
  read the active slcli profile credentials, including keys stored in the OS credential
  manager:
  ```python
  from nisystemlink.clients.core import HttpConfigurationManager
  mgr = HttpConfigurationManager()
  cfg = mgr.get_configuration()
  server = cfg.server_uri
  api_key = cfg.api_keys["x-ni-api-key"]
  ```

### Upload Script Pattern

A reusable `deploy/upload_state.py` script should:

1. Auto-detect credentials from `HttpConfigurationManager` or slcli config
2. Accept `--server` and `--api-key` overrides
3. Set `User-Agent: SystemLink-CLI/1.0` on all requests
4. Use `import-state` for SLS files with custom states (cmd.run, file.managed, etc.)
5. Use `POST /states` JSON API for simple package-only states
