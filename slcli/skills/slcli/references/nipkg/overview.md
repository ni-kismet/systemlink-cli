# Building NI File Packages

Load this overview when the task is specifically about assembling or troubleshooting
an NI Package Manager file package. Use it for package structure, metadata, target
roots, and `nipkg pack` validation behavior.

## When to Use

- Creating a `.nipkg` from a folder of source files
- Building a deployable package for SystemLink feeds
- Choosing the correct `data/<target-root>/...` layout
- Fixing `nipkg pack` validation failures
- Adding package metadata, install scripts, or uninstall scripts

## Core rules

1. A file package must contain `debian-binary`, `control/`, and `data/` before packing.
2. The control file must include `XB-Plugin: file`.
3. `nipkg pack` takes a source directory and a destination directory.
4. On Windows, files under `data/` must use NI Package Manager target root names such as `ProgramFiles`.
5. For `Architecture: windows_all`, do not use 64-bit-only roots such as `ProgramFiles_64`.

## Required package layout

```text
<package-root>/
├── debian-binary
├── control/
│   ├── control
│   ├── instructions
│   ├── postinstall.bat
│   └── preuninstall.bat
└── data/
    └── ProgramFiles/
        └── NI/
            └── <package-name>/
                ├── main.py
                ├── requirements.txt
                └── ...
```

The `debian-binary` file should contain `2.0`.

## Minimal control file

Required fields usually include:

- `Package`
- `Version`
- `Section`
- `Architecture`
- `Maintainer`
- `XB-Plugin: file`
- `XB-UserVisible: yes`
- `Description`

Add `Depends` entries only for packages you know exist in every target feed.

## Minimal instructions file

```ini
[Instructions]
postinstall=postinstall.bat
preuninstall=preuninstall.bat
```

## Windows target roots

Use NI Package Manager root names exactly as expected:

- `ProgramFiles`
- `ProgramFiles_32`
- `ProgramData`
- `Documents`
- `Desktop`
- `Home`
- `ProgramMenu`
- `Startup`
- `System`

For NI-managed locations, use `ni-paths-*` root names such as `ni-paths-NIPUBAPPDATADIR`.

## Recommended build script pattern

A reliable build script should:

- resolve `nipkg.exe`
- clean and recreate `build` and `dist`
- write `debian-binary`
- copy payload files under `data/`
- copy control metadata under `control/`
- run `nipkg pack <source-dir> <destination-dir>`

## Common failures and fixes

- `nipkg is not recognized`
  Use the full path to `nipkg.exe` or add it to `PATH`.
- Destination path invalid
  The second `nipkg pack` argument must be a directory, not a full `.nipkg` file path.
- Unknown root name
  Use `ProgramFiles`, not `Program Files`.
- Root validation failures with `windows_all`
  Avoid `_64`-only roots.
- Missing `ni-python` dependency
  Remove the dependency and provision Python separately.

## Verification steps

1. Run the build script.
2. Confirm a `.nipkg` appears in `dist/`.
3. Unpack it to verify `control/control`, `debian-binary`, and the expected `data/ProgramFiles/...` tree.

## SystemLink context

For SystemLink deployment, file packages are appropriate for payloads that install directly onto the target system, such as Python source, scripts, configuration files, and requirements manifests.

After building the `.nipkg`:

- upload it to a feed with `slcli feed package upload`
- deploy it through SystemLink software deployment

Feed rules to remember:

- feed names must start with an alphabetic character
- upload APIs use multipart field name `package`
- feed registration URLs use `/files`, not `/packages`
- workspace lookup should use `/niuser/v1/workspaces`

## Salt state deployment

If a target system needs prerequisites that are not provided as package dependencies, create a Systems State SLS that installs those prerequisites and then installs the package.

Typical examples:

- installing Python first
- registering the feed
- installing the generated package

## When to branch to another overview

- If the package contains a Python test application, load [../python-test/overview.md](../python-test/overview.md) for the execution and Test Monitor side.
- If package deployment fails because the Systems Management job is stuck, load [../job-debugging/overview.md](../job-debugging/overview.md).
- If packaging is for a hosted webapp, load [../webapp/overview.md](../webapp/overview.md) first and return here only when packaging begins.
