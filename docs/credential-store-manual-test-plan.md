# Credential Store Manual E2E Plan

## Coverage

Run the API-key flow on macOS and Windows for each release candidate that changes
credential storage. Run it on Linux when validating or shipping Linux
OS-credential-store support; Linux uses a separate Secret Service backend and
is not covered by the macOS or Windows runs.

Run the PKCE flow as well when the test SystemLink environment has a configured
public OAuth client. The unit suite covers token parsing and mocked storage,
but this plan verifies native-store integration with a live authenticated
command.

## Prerequisites

- A disposable SystemLink test environment and an API key permitted to run
  `slcli info`.
- A native user session with the OS credential store available and unlocked.
- The project environment installed with `poetry install`.
- A fresh temporary config path for each run. Do not use a production slcli
  config or a profile containing credentials you need to keep.
- Ensure `SLCLI_API_KEY`, `SYSTEMLINK_API_KEY`, `SLCLI_API_URL`,
   `SYSTEMLINK_API_URL`, `SLCLI_WEB_URL`, and `SYSTEMLINK_WEB_URL` are unset so
   the authenticated command must use the test profile and its stored
   credential.

Set `SLCLI_CONFIG` to a new config file under a temporary directory. On
macOS/Linux:

```sh
export SLCLI_CONFIG="$(mktemp -d)/config.json"
```

On Windows PowerShell:

```powershell
$testConfigDir = Join-Path $env:TEMP ([guid]::NewGuid().ToString())
New-Item -ItemType Directory -Path $testConfigDir | Out-Null
$env:SLCLI_CONFIG = Join-Path $testConfigDir "config.json"
```

## API-Key Flow

Perform these steps on each required OS. Enter the API key at the hidden prompt;
do not pass it as a command-line argument.

1. Add a profile to the isolated config. Replace the URL with the disposable
   environment's API URL:

   ```sh
   poetry run slcli login --profile cred-e2e --url https://<test-api-url> --web-url https://<test-web-url> --credential-store os
   ```

2. Confirm the command reports a successful profile save. Inspect the temporary
   `config.json`: `credential-store` must be `os`, and the profile must contain
   neither `api-key` nor `pkce-credentials`. Record the profile `id` for the
   native-store checks below; do not record the secret. If prompted for a
   default workspace, press Enter to skip it.

3. Run `poetry run slcli info`. It must complete its authenticated health check
   without an API-key override. This verifies a real read from the selected
   native store, not merely a successful write.

4. Confirm the native store contains the account
   `profile:<id>:api-key` in service `systemlink-cli`:
   - macOS: `security find-generic-password -s systemlink-cli -a "profile:<id>:api-key"`.
   - Windows: open **Credential Manager > Windows Credentials** and locate the
     generic credential for service `systemlink-cli` and account
     `profile:<id>:api-key`.
   - Linux: open the desktop Secret Service/keyring UI and locate service
     `systemlink-cli` with account `profile:<id>:api-key`.

5. Remove the profile with `poetry run slcli logout --profile cred-e2e --force`.
   Confirm the profile and `pending-credential-deletions` are absent from the
   temporary config.

6. Verify the native-store account is gone without displaying its secret:
   - macOS: `security find-generic-password -s systemlink-cli -a "profile:<id>:api-key"`
     must return a not-found result.
   - Windows: refresh Credential Manager and confirm the matching generic
     credential is absent.
   - Linux: refresh the Secret Service UI and confirm the matching item is
     absent.

## Cleanup-Only Recovery

This check verifies that stale replacement credentials can be retried without
removing the live profile. It may be run on macOS and Windows and on Linux when
Linux store support is in scope.

1. Create the `cred-e2e` OS-backed profile above and note its ID.
2. In the disposable config only, add a `pending-credential-deletions` entry
   with the same profile name, `store: "os"`, `auth-mode: "api-key"`, and an
   unused ID such as `stale-manual-test-id`.
3. Run `poetry run slcli config cleanup`.
4. Confirm the pending entry is removed while `cred-e2e` remains configured
   with its original ID and `credential-store: os`.
5. Run `poetry run slcli info` again; it must still authenticate. Then run the
   API-key flow's logout and native-store absence checks to remove the actual
   test credential.

## PKCE Flow (When Available)

Repeat the API-key flow with a separate profile and a test public client:

```sh
poetry run slcli login --profile cred-e2e-pkce --url https://<test-api-url> --web-url https://<test-web-url> --auth pkce --client-id <test-client-id> --credential-store os
```

Complete the browser sign-in. Confirm the temporary profile has
`credential-store: os` and no `pkce-credentials`; verify an authenticated
`poetry run slcli info` succeeds. Under service `systemlink-cli`, Credential
Manager stores a `profile:<id>:pkce:active` account containing the active
generation ID and separate accounts named
`profile:<id>:pkce:<generation>:access-token`,
`profile:<id>:pkce:<generation>:refresh-token`, and
`profile:<id>:pkce:<generation>:access-expires-at` for fields present in the
bundle. Confirm these accounts exist without opening or displaying their
values. Log out that profile and confirm the active pointer, generation
accounts, and profile metadata are absent. Never query or print a stored token
value.

## Results

Record the OS/version, Python version, CLI commit, API-key flow result, PKCE
result (or why it was unavailable), cleanup-only result, and logout/store
absence result. Do not include API keys, access tokens, refresh tokens, or
screenshots that reveal credential values.