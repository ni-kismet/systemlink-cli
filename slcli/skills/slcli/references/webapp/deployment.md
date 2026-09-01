# Deployment Reference — slcli webapp commands

This is the operational protocol for every webapp create, publish, redeploy,
or update task. Complete target resolution before building or uploading. Keep
the workflow non-interactive by using `--format json`, a bounded `--take`, and
commands that do not prompt for the next page.

## 1. Discover the installed command surface

Reference documentation can lag the installed CLI. Inspect help first:

```bash
slcli config list --format json
slcli webapp publish -h
slcli webapp list -h
```

Use the installed help as authoritative. The current publish command accepts
`--id`, `--name`, and `--workspace`; it does not accept `--format`. The list
command supports `--workspace`, `--filter`, bounded `--take`, and
`--format json` (also `-f json`). Prefer long options in automation after
confirming them with help.

## 2. Resolve profile and workspace

Resolve profile identity and workspace identity independently. A workspace
name or UUID is not a profile name, and a similar profile name is not evidence
that it serves the requested workspace.

```bash
# Find configured profile/workspace mappings.
slcli config list --format json

# Probe each candidate sequentially without changing the persisted profile.
slcli --profile <PROFILE> info --skip-health --format json
slcli --profile <PROFILE> workspace list --format json
```

Use `active_profile_name` from `info` as the effective profile and resolve the
requested workspace by exact name or UUID from the workspace response. Record
both:

```text
PROFILE=<effective profile name>
WORKSPACE_ID=<resolved workspace UUID>
WORKSPACE_NAME=<resolved display name>
WEBAPP_NAME=<intended published name>
```

Use `WORKSPACE_ID` for all commands that accept a workspace. Do not silently
fall back to `Default`.

## 3. Resolve the exact webapp target

Do this before `ng build`, packaging, or any upload. `--filter` is a
case-insensitive substring filter, not an exact-name lookup, so inspect the
bounded JSON result and compare names locally.

```bash
slcli --profile <PROFILE> webapp list \
  --workspace <WORKSPACE_ID> \
  --filter "<WEBAPP_NAME>" \
  --take 10 \
  --format json
```

For shell automation, select exact name matches from the returned JSON rather
than trusting the server-side substring filter:

```bash
slcli --profile <PROFILE> webapp list \
  --workspace <WORKSPACE_ID> --filter "<WEBAPP_NAME>" \
  --take 10 --format json \
  | jq -r --arg name "<WEBAPP_NAME>" \
      '.[] | select(.name == $name) | [.id, .name, .workspace] | @tsv'
```

- One exact match: use its ID for an update. This is the default redeploy path.
- Multiple exact matches: stop and select an ID explicitly; do not guess.
- No exact match: report that publishing with `--name` will create metadata.
  Create only when the user explicitly requested a new webapp or confirms the
  new target. Do not create a duplicate as a fallback for an uncertain lookup.

## 4. Inspect and validate the artifact contract

Before starting local development or building, inspect the project files:

```bash
sed -n '1,220p' package.json
sed -n '1,280p' angular.json
```

Check the `scripts.start` command before adding flags. For example, if it
already contains `ng serve --host 0.0.0.0`, do not append another `--host`.
If `ng serve` rejects `buildOptimizer`, `vendorChunk`, or another legacy
option, remove or migrate that option in the matching Angular configuration
before retrying. Do not hide a builder/configuration error by changing the
publish command.

Run the production build from the Build section below and inspect the actual
output directory before publishing.

Use the directory containing the built `index.html` as the publish source. Do
not assume `/browser/`; the output depends on the configured Angular builder.

Verify the hosted app contract before publishing:

- `src/index.html` has no `<base>` element.
- `APP_BASE_HREF` is provided through DI.
- Router configuration uses `useHash: true`.
- Production optimization sets `inlineCritical: false`.
- Same-origin requests use `credentials: 'include'`.
- Each client base URL includes the full service prefix, such as
  `window.location.origin + '/nitest'`.
- Test Monitor query results use the browser-facing service prefix
  `/nitest/v2/query-results`, never the CLI backend prefix
  `/nitestmonitor/v2/query-results`.
- The resolved workspace UUID is passed into requests or configuration; no
  hardcoded `Default` workspace remains.

## Prerequisites

- `slcli` installed and authenticated (`slcli login` or config file present)
- Profile, workspace UUID, and exact webapp target resolved by the protocol above
- Angular app built successfully
- Publish path confirmed for the active builder:
  - `dist/<app-name>/browser/` for the application builder
  - `dist/<app-name>/` for the legacy browser builder

## Build

```bash
# Run from project root
node_modules/.bin/ng build --configuration production
find dist -type f -name index.html -print
```

**Do NOT pass `--base-href`.** This would reintroduce a `<base>` element that violates SystemLink's CSP.

Angular may emit different publish roots depending on the active builder and `outputPath` shape.

- the generated `slcli webapp new` scaffold keeps browser assets under `dist/<app-name>/`
- some `@angular/build:application` workspaces emit browser assets under `dist/<app-name>/browser/`
- `@angular-devkit/build-angular:browser` emits browser assets directly under `dist/<app-name>/`

Always inspect the actual build output before publishing. Do not hardcode `/browser/` if the workspace is on the legacy builder.

If `npm run build` fails with `Could not resolve '@ni/nimble-components/dist/esm/...'` while using `@ni/nimble-angular`, switch the workspace to the legacy Angular browser builder before continuing. Do not publish from a half-fixed setup.

### Background build (only when a synchronous build cannot be used)

```bash
nohup node_modules/.bin/ng build --configuration production --output-path dist/<app-name> \
  > /tmp/ng-build.log 2>&1 &
echo "Build PID: $!"
# Inspect the log without attaching an interactive tail session:
sed -n '1,220p' /tmp/ng-build.log
```

Prefer a synchronous command. If the terminal tool moves a command to the
background, retain the opaque terminal ID it returns and use that ID with the
terminal-output tool when notified. Do not substitute a shell PID, invent a
terminal ID, or poll with `sleep`; terminate an abandoned long-running process
with its terminal ID.

---

## 5. Publish and capture deployment metadata

### First deploy (no existing webapp)

```bash
slcli --profile <PROFILE> webapp publish <ACTUAL_BUILD_OUTPUT_DIR> \
  --name "<WEBAPP_NAME>" --workspace <WORKSPACE_ID>
```

The command creates webapp metadata and uploads the content. Capture the
returned webapp ID and published URL. Immediately after a successful upload,
record the current UTC time as the observed publish timestamp. Save the ID for
every future redeploy and for `slcli webapp open`.

Example output:

```
✓ Published webapp content
  Webapp ID: 3727d9ac-86e1-4d6e-820e-d2631c0b28e9
  Source: <PACKAGED_SOURCE_PATH>
  Published URL: https://systemlink.example.com/webapps/coffee-tasting
```

### Redeploy (update existing webapp)

```bash
slcli --profile <PROFILE> webapp publish <ACTUAL_BUILD_OUTPUT_DIR> \
  --id <WEBAPP_ID>
```

When updating an existing webapp, use the exact ID from target resolution. Do
not pass a name and hope the service finds the intended existing resource.

After publishing, fetch deployment metadata explicitly:

```bash
slcli --profile <PROFILE> webapp get --id <WEBAPP_ID> --format json
```

Record the ID, URL, and workspace returned by the publish or metadata response.
Record the UTC time immediately after the successful upload and label it as an
observed publish timestamp because the CLI does not return one.

## 6. Validate at three levels

### Level 1: deployment metadata

Use `webapp get` to confirm that the intended ID exists and belongs to the
resolved workspace. Confirm the returned name and URL before opening it.

### Level 2: authenticated CLI/API behavior

Run a small, bounded query through the authenticated CLI against the resolved
workspace and every resource service the app requires. For a Test Monitor app,
for example:

```bash
slcli --profile <PROFILE> testmonitor result list \
  --workspace <WORKSPACE_ID> --take 1 --format json
```

This validates credentials and resource scope, but it does not prove that the
hosted bundle uses the same URL, request body, or browser auth mode.

### Level 3: authenticated browser behavior

Open the published URL in a browser that is logged in to the same SystemLink
server. Check the main route, a real data request, hash navigation, Nimble
styling, theme switching, and the browser console. A URL that responds or
redirects is only a reachability signal. If the browser redirects to login or
returns 401, report exactly:

```text
deployment reachable, interactive hosted validation pending.
```

Do not call browser validation complete until the app has been tested in an
authenticated hosted session.

---

## Open in browser

```bash
slcli --profile <PROFILE> webapp open --id <WEBAPP_ID>
```

---

## List webapps

```bash
slcli --profile <PROFILE> webapp list \
  --workspace <WORKSPACE_ID> --take 10 --format json
```

---

## Delete a webapp

```bash
slcli --profile <PROFILE> webapp delete --id <WEBAPP_ID>
```

---

## Deployment checklist

Before publishing, verify:

- [ ] `index.html` has **no** `<base href>` tag
- [ ] `app.module.ts` provides `{ provide: APP_BASE_HREF, useValue: '/' }`
- [ ] `app-routing.module.ts` uses `useHash: true`
- [ ] `angular.json` has `inlineCritical: false` in production optimization
- [ ] `angular.json` uses a builder that bundles `@ni/nimble-angular` successfully
- [ ] `basePath` is `window.location.origin + '/<service-prefix>'` (not just origin)
- [ ] `credentials: 'include'` (or equivalent) set on API client
- [ ] Test Monitor uses `/nitest/v2/query-results`, not `/nitestmonitor/v2/query-results`
- [ ] Resolved workspace UUID is propagated instead of `Default`
- [ ] Exact webapp ID is selected before an update
- [ ] Build succeeded with no errors
- [ ] Publish path matches the active builder output
- [ ] Deployment metadata, authenticated CLI behavior, and hosted browser behavior were checked

## Common deployment errors

### App shows blank/white screen

- Check browser console for NG04002 -> `useHash: true` missing
- Check for CSP `base-uri` error -> remove `<base>` tag

### API calls fail with status 0 (CORS)

- `basePath` is pointing to a different origin than where the app is served
- Fix: use `window.location.origin + '/service-prefix'`

### API calls return 404 on correct paths

- `basePath` is missing the service prefix (for example, `/nitag`)
- The generated client's `defaultBasePath` is being overridden by your `Configuration` -> make sure your `basePath` value includes the full prefix
- Test Monitor requests must use `/nitest/v2/query-results`, not `/nitestmonitor/v2/query-results`

### Styles look broken or CSP reports `unsafe-inline`

- Beasties CSS inliner is injecting `onload` handlers
- Fix: set `inlineCritical: false` in angular.json

### Nimble packages fail to resolve during build

- You may be on `@angular/build:application` with a Nimble package layout that esbuild does not resolve cleanly
- Fix: install `@angular-devkit/build-angular` and switch to the legacy browser/dev-server builders in `angular.json`

### "Budget exceeded" build error

Increase error limits in `angular.json`:

```json
"budgets": [
  { "type": "initial", "maximumWarning": "1.25MB", "maximumError": "2MB" }
]
```

The bundled `slcli webapp new` starter already ships six route-level patterns, so `1.25MB`
is the expected warning threshold for the generated scaffold. Treat repeated warnings above that
level as a sign that the starter content or added dependencies need review.
