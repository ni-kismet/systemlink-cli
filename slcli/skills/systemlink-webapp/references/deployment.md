# Deployment Reference — slcli webapp commands

## Prerequisites

- `slcli` installed and authenticated (`slcli login` or config file present)
- Angular app built successfully
- Publish path confirmed for the active builder:
  - `dist/<app-name>/browser/` for the application builder
  - `dist/<app-name>/` for the legacy browser builder

---

## Build

```bash
# Run from project root
node_modules/.bin/ng build --configuration production
```

**Do NOT pass `--base-href`.** This would reintroduce a `<base>` element that violates SystemLink's CSP.

Angular may emit different publish roots depending on the active builder.

- `@angular/build:application` emits browser assets under `dist/<app-name>/browser/`
- `@angular-devkit/build-angular:browser` emits browser assets directly under `dist/<app-name>/`

Always inspect the actual build output before publishing. Do not hardcode `/browser/` if the workspace is on the legacy builder.

If `npm run build` fails with `Could not resolve '@ni/nimble-components/dist/esm/...'` while using `@ni/nimble-angular`, switch the workspace to the legacy Angular browser builder before continuing. Do not publish from a half-fixed setup.

### Background build (if terminal has heredoc/interrupt issues)

```bash
nohup node_modules/.bin/ng build --configuration production --output-path dist/<app-name> \
  > /tmp/ng-build.log 2>&1 &
echo "Build PID: $!"
# Check progress:
tail -f /tmp/ng-build.log
```

---

## First deploy (no existing webapp)

```bash
slcli webapp publish <ACTUAL_BUILD_OUTPUT_DIR> --workspace <workspace-name>
```

The command prints the new webapp ID. **Save it** — you need it for every future redeploy and for `slcli webapp open`.

Example output:

```
Created webapp: 3727d9ac-86e1-4d6e-820e-d2630c1b28e9
```

---

## Redeploy (update existing webapp)

```bash
slcli webapp publish <ACTUAL_BUILD_OUTPUT_DIR> --workspace <workspace-name> --id <webapp-id>
```

---

## Open in browser

```bash
slcli webapp open --id <webapp-id>
```

---

## List webapps

```bash
slcli webapp list --workspace <workspace-name>
```

---

## Delete a webapp

```bash
slcli webapp delete --id <webapp-id>
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
- [ ] Build succeeded with no errors (warnings about bundle size are OK if within 2MB error limit)
- [ ] Publish path matches the active builder output

---

## Common deployment errors

### App shows blank/white screen

- Check browser console for NG04002 → `useHash: true` missing
- Check for CSP `base-uri` error → remove `<base>` tag

### API calls fail with status 0 (CORS)

- `basePath` is pointing to a different origin than where the app is served
- Fix: use `window.location.origin + '/service-prefix'`

### API calls return 404 on correct paths

- `basePath` is missing the service prefix (e.g., `/nitag`)
- The generated client's `defaultBasePath` is being overridden by your `Configuration` — make sure your `basePath` value includes the full prefix

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
  { "type": "initial", "maximumWarning": "1MB", "maximumError": "2MB" }
]
```
