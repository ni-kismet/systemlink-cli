New logins store API keys and PKCE credentials in the operating system's credential store by default, with an explicit file-store option and a warned file fallback when OS storage is unavailable. Add `slcli config secure` for existing plaintext profiles.

Remove legacy global keyring reads and `slcli config migrate`; users who relied only on those entries, or on older per-token PKCE credentials, must run `slcli login` again to configure a profile.

Remove the `SYSTEMLINK_API_URL`, `SYSTEMLINK_API_KEY`, and `SYSTEMLINK_WEB_URL` environment aliases; use `SLCLI_API_URL`, `SLCLI_API_KEY`, and `SLCLI_WEB_URL` instead. Replace the `SYSTEMLINK_PLATFORM` override with `SLCLI_PLATFORM`.

Credential replacement, logout, and profile deletion retain retryable cleanup records for written or partially written OS credentials when cleanup fails. Credential changes, profile switching, and background configuration updates share a cross-process lock. Recovery errors identify abandoned credential IDs. Use `slcli config cleanup` to retry interrupted cleanup without deleting active profiles. Atomic configuration saves preserve symlinked paths.

To remove obsolete macOS Keychain items manually, run `security delete-generic-password -s systemlink-cli -a <ACCOUNT>` for each of `SYSTEMLINK_API_KEY`, `SYSTEMLINK_API_URL`, `SYSTEMLINK_WEB_URL`, and `SYSTEMLINK_CONFIG`.