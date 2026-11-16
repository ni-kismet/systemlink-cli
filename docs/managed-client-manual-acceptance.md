# Managed-Client Manual Acceptance

Use this checklist for the opt-in managed-client test minion. Run the local
checks on any supported development host. Live checks require a configured
SystemLink environment and an operator who can approve the minion key and
dispatch test jobs.

## Safety and prerequisites

- Use a unique test minion ID and a private, disposable state directory.
- Confirm the Salt master and SystemLink environment are the intended test
  environment. Do not copy API keys or private keys into commands or logs.
- Start in simulated mode. Simulated package jobs only change the minion's
  isolated metadata; they never run host package commands.
- Do not run real package installs or removals on a workstation. Real package
  mutation is for an explicitly approved disposable Debian-family VM only.
- Feed-backed simulated installs fetch `Packages` metadata from enabled mock
  feed URLs. Do not use a feed URL that should not be contacted. The solver
  extra requires the native `solv` binding and `python-debian`; PyPI currently
  publishes `solv` wheels for Linux, so validate feed-backed installs on Linux.

## 1. Local CLI smoke

Install the base managed-client extra in the project environment, then check
the command surface and crypto/protocol smoke test:

```bash
poetry install --extras managed-client
poetry run slcli managed-client --help
poetry run slcli managed-client run --help
poetry run slcli managed-client reset --help
poetry run slcli managed-client smoke
```

Expected: help lists `run` and `reset`, and smoke prints
`Managed-client smoke test passed.`

## 2. Connect and exercise simulated packages

Start the minion in a terminal, leaving `--simulated` at its default:

```bash
poetry run slcli managed-client run \
  --master <test-salt-master> \
  --minion-id <unique-test-minion-id> \
  --state-dir <private-test-state-directory>
```

Approve its pending public key through the separate SystemLink control-plane
workflow. Verify the minion reconnects and reaches connected presence. Check
that its reported identity is Windows/AMD64 and identifies the simulated
minion, not the local workstation.

From the SystemLink test environment, dispatch these allowlisted jobs to that
minion and inspect each Salt return:

1. `pkg.install` for `slcli-acceptance-one=1.0`: succeeds with an empty old
   version and new version `1.0`.
2. Repeat the same install: succeeds with an empty change map.
3. `pkg.install` for `slcli-acceptance-one=2.0` with `test=True`: reports the
   proposed change but leaves the installed version at `1.0`.
4. `pkg.list_pkgs` and `pkg.info_installed`: report `1.0` and architecture
   `all`.
5. `pkg.remove` for the package with `test=True`: reports removal, while
   `pkg.list_pkgs` still reports `1.0`.
6. `pkg.remove` without `test=True`: removes it; `pkg.list_pkgs` and
   `pkg.info_installed` return empty maps.
7. Reinstall `slcli-acceptance-one=1.0`, then stop and restart the minion with
   the same state directory. Confirm it reconnects using the same identity
   and `pkg.list_pkgs` still reports `1.0`. Remove the test package afterward.

No package-manager process should be launched by these simulated jobs.

## 3. Optional mock-feed dependency resolution

On Linux with the solver extra installed, configure a test feed containing
small `Packages.gz` metadata for a package and one dependency. Do not include
or download package archives.

```bash
poetry install --extras managed-client-solver
```

1. Dispatch `pkg.mod_repo` to add the test feed, then `pkg.list_repos` to
   confirm it is listed.
2. Dispatch `pkg.install` for the package. Confirm the return includes both
   the requested package and its dependency.
3. Request a different available version with `test=True`; confirm the proposed
   changes are returned but persistent inventory is unchanged.
4. Disable the feed and confirm it is not queried on the next install.

Expected: only package-index metadata is fetched; no installer or archive
download runs.

## 4. Optional health-tag publishing

Run a newly approved simulated minion with `--health-tags --health-interval 30`.
The Salt master must deliver the intended HTTP endpoint, API key, and optional
CA bundle into the minion state directory. The local slcli profile is not used
for these writes.

Expected: after connection, 13 health tags appear under
`<minion-id>.Health.*`, have current values, and include `slcliMock=true`.
Verify CPU, memory, and disk values are finite and internally consistent.
Stop the minion with Ctrl+C and confirm publishing stops.

## 5. Reset and cleanup

After stopping the minion, run reset without `--yes`, decline the confirmation,
and verify the state remains. Run reset again with `--yes`; verify only the
minion identity/state files are removed and the state directory remains.
Remove the test system and approved key through the environment's normal
control-plane cleanup workflow.

## 6. Host-mode checks

On macOS, `--simulated false` may be used only after confirming that publishing
the host name, model, IP addresses, and resource values to the test environment
is acceptable. Verify the model matches `sysctl -n hw.model` and the vendor is
`Apple`. Package jobs should return
`unsupported-host-package-manager` and must not invoke a package manager.
The refresh job must reach `FAILED` with nonzero return codes for repository and
package inventory reads, whose values are `null`; it must not remain `INPROGRESS`.
Use simulated mode when testing a successful software-inventory refresh on macOS.

For real package-backend acceptance, use an approved disposable Debian-family
VM with `dpkg-query` and `apt-get` installed:

1. Run with `--simulated false`; confirm the minion reports host identity and
   `pkg.list_pkgs` matches `dpkg-query`.
2. Dispatch `pkg.install` with `test=True`; confirm it reports the apt
   simulation without changing inventory.
3. Only with explicit approval, exercise install/remove without `test=True`
   using a disposable package/VM, then confirm reported changes match the
   package inventory.
4. Confirm `pkg.mod_repo` fails as unsupported and `pkg.list_repos` reads
   configured apt sources.
