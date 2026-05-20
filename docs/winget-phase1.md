# Winget Phase 1 Bootstrap

This guide bootstraps the first community submission for `NI.SystemLinkCLI`.

## Scope

- Package identifier: `NI.SystemLinkCLI`
- Version: `1.13.19`
- Installer URL: `https://github.com/ni-kismet/systemlink-cli/releases/download/v1.13.19/slcli.zip`
- Installer SHA256: `E9BAC73EFF00538B9AB8572E0BFF31B5225F4B5D21ED9C5167B858976D0C83AF`
- Manifest source in this repo:
  - `scripts/winget/NI.SystemLinkCLI/1.13.19/NI.SystemLinkCLI.yaml`
  - `scripts/winget/NI.SystemLinkCLI/1.13.19/NI.SystemLinkCLI.locale.en-US.yaml`
  - `scripts/winget/NI.SystemLinkCLI/1.13.19/NI.SystemLinkCLI.installer.yaml`

## One-time setup

1. Install WingetCreate.

```powershell
winget install wingetcreate
```

2. Fork and clone the community repo.

```powershell
git clone --filter=blob:none --no-checkout https://github.com/<your-user>/winget-pkgs.git
cd winget-pkgs
git sparse-checkout set manifests/n/NI/SystemLinkCLI
git checkout -b ni-systemlinkcli-1.13.19
```

## Copy manifests

Copy the 3 YAML files into this path inside your fork:

`manifests/n/NI/SystemLinkCLI/1.13.19/`

## Validate locally

```powershell
winget validate manifests/n/NI/SystemLinkCLI/1.13.19
```

Optional sandbox test:

```powershell
powershell .\Tools\SandboxTest.ps1 manifests\n\NI\SystemLinkCLI\1.13.19
```

## Submit PR

```powershell
git add manifests/n/NI/SystemLinkCLI/1.13.19
git commit -m "Add NI.SystemLinkCLI version 1.13.19"
git push --set-upstream origin ni-systemlinkcli-1.13.19
```

Then open a PR to `microsoft/winget-pkgs`.

## Common failure checks

- Hash mismatch: recompute SHA256 from the exact release asset URL.
- Path mismatch: `RelativeFilePath` must stay `slcli/slcli.exe`.
- URL policy: keep direct GitHub release URL under the publisher repository.
- Unattended failure: portable nested installer avoids silent-switch issues.

## Next step (Phase 2)

Automate manifest generation from release version and hash in this repository, then wire it into release workflow as artifact-only generation before enabling auto-submit.
