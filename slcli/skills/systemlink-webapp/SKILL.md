---
name: systemlink-webapp
description: >
  Build, configure, troubleshoot, and deploy custom Angular web applications hosted inside NI SystemLink. Use this skill whenever a user wants a frontend app that runs inside SystemLink as a published webapp, uses @ni/nimble-angular, @ni/spright-angular, or @ni/ok-angular, calls SystemLink REST APIs or @ni/systemlink-clients-ts, needs SystemLink-specific Angular setup (hash routing, APP_BASE_HREF, CSP-safe builds, theme sync), or is packaging/publishing with slcli webapp commands. Also use it for troubleshooting hosted webapp issues like CORS/CSP errors, wrong SDK base URLs, theme-token problems, missing Angular wrapper modules, or iframe/sub-path routing failures.
compatibility:
  models: [claude-sonnet-4-5, claude-opus-4, claude-3-7-sonnet]
  tools: [read_file, run_in_terminal, apply_patch, create_file]
---

# SystemLink WebApps

SystemLink webapps are Angular SPAs hosted inside the SystemLink shell and iframe context. The main risks are not generic Angular problems; they are SystemLink-specific integration issues such as CSP, sub-path routing, theme token placement, Nimble wrapper usage, and service base URLs.

Keep the main skill focused on workflow and decision points. Load reference files only when the current task needs that detail.

## Progressive loading

Start here and read no more than one or two reference files until the task is blocked by missing detail.

| Need | Read |
| --- | --- |
| Concise component inventory across Nimble, Spright, and OK Angular | [references/angular-ui-packages.md](./references/angular-ui-packages.md) |
| Nimble Angular modules, wrapper usage, table/dialog/tab patterns | [references/nimble-angular.md](./references/nimble-angular.md) |
| Page layout, spacing, split panes, drawers, accordions | [references/layout-patterns.md](./references/layout-patterns.md) |
| SystemLink SDK base URLs, auth modes, LINQ query patterns | [references/systemlink-services.md](./references/systemlink-services.md) |
| Build, publish, Plugin Manager packaging commands | [references/deployment.md](./references/deployment.md) |
| Hosted validation, console triage, theme checks, recurring failures | [references/troubleshooting.md](./references/troubleshooting.md) |

If the user only wants planning or a first implementation slice, stay in this file.

## First response checklist

Before generating code, clarify only the details that change the implementation:

1. Goal: what the app should show or let the user do.
2. Services: which SystemLink resources it must read or mutate.
3. Starting point: new app, `slcli webapp init` starter, or existing Angular codebase.
4. Auth context: same-origin hosted app versus remote/dev API-key flow.
5. Deployment target: ordinary hosted webapp only, or Plugin Manager package as well.

Do not ask about Angular or Nimble versions unless the user is constrained by an existing project. Default to Angular 20 and the latest compatible `@ni/nimble-angular`.

For new SystemLink apps, recommend installing the NI Angular UI packages together unless the user is intentionally minimizing dependencies. `@ni/nimble-angular` remains the default foundation, `@ni/spright-angular` adds Spright chat and icon components, and `@ni/ok-angular` adds OK-specific controls such as accordion items and search input.

## Recommended workflow

### 1. Bootstrap the right project shape

For a new SystemLink app, prefer:

```bash
slcli webapp init <app-dir>
```

Then generate Angular in that starter directory so the SystemLink scaffolding stays at the project root:

```bash
npx -y @angular/cli@20 new <app-name> --directory . --routing --style=scss --skip-git --no-standalone --defaults --force
npm install @ni/nimble-angular @ni/spright-angular @ni/ok-angular @ni/systemlink-clients-ts
```

Prefer NgModule-based apps for this workflow. The Nimble Angular wrapper modules fit naturally into a centralized `AppModule`, which reduces template surprises and keeps imports explicit.

Recommend installing `@ni/spright-angular` and `@ni/ok-angular` early even if the first slice only uses Nimble. That avoids dependency churn later when the UI needs chat surfaces, product-specific icons, accordion items, or the OK search input.

If the user has not run `slcli webapp init` and explicitly wants a SystemLink-hosted webapp, recommend it first unless they want a manual setup.

### 2. Lock in the non-negotiables early

These decisions prevent the most common hosted-webapp failures:

- Provide `APP_BASE_HREF` via DI and remove any `<base>` tag from `index.html`.
- Use hash routing with `RouterModule.forRoot(..., { useHash: true })`.
- Disable critical CSS inlining in production with `inlineCritical: false`.
- Use `@ni/nimble-angular` wrapper modules, not raw `@ni/nimble-components`, as the default integration path.
- Do not add `CUSTOM_ELEMENTS_SCHEMA` just to silence missing Nimble module imports.
- Put theme-aware color and shadow aliases on `nimble-theme-provider`, not on `:root`.
- Import `@angular/localize/init` in Angular polyfills for both build and test paths.

If you need the exact module patterns or template wiring, load [references/nimble-angular.md](./references/nimble-angular.md).
If you need a concise package-level inventory before choosing components, load [references/angular-ui-packages.md](./references/angular-ui-packages.md).

### 3. Choose the default UI patterns

Use SystemLink-appropriate layout defaults instead of inventing page structure from scratch:

- Use `nimble-table` for primary list/browse/search datasets.
- Keep list/detail views visible together with a split-pane when selection drives preview.
- Use drawers or collapsible side panels for settings and filters.
- Use accordions for grouped fields and advanced configuration.
- Use cards sparingly for summaries, not as the default editing or data layout.

Load [references/layout-patterns.md](./references/layout-patterns.md) when the task turns into page composition, spacing, or shell layout work.

### 4. Integrate SystemLink APIs the low-risk way

Always prefer `@ni/systemlink-clients-ts` first. Only generate a new client when the needed service is not already covered.

Default rules:

- Build clients at runtime from `window.location.origin`.
- For same-origin hosted apps, use cookie auth with `credentials: 'include'`.
- For remote/dev flows, collect an API key from the user and send it as `x-ni-api-key`.
- Never hardcode hostnames or credentials in source code.
- Treat generated SDK request shapes as fallible; if the SDK body shape is wrong, fall back to direct `fetch`.

Load [references/systemlink-services.md](./references/systemlink-services.md) when you need actual base URLs, request bodies, or auth examples.

### 5. Build the smallest useful vertical slice first

When the user asks for implementation, prefer one working slice over a full app shell rewrite:

- one route
- one data query
- one table or detail view
- one loading state
- one error banner
- one settings/control path only if required

This keeps context narrow and usually reveals the real integration blockers faster than broad scaffolding.

### 6. Publish or package only after the hosted constraints are covered

For ordinary hosted deployment, build and publish after the routing, CSP, theme, and client setup are in place.

For Plugin Manager packaging, use `slcli webapp manifest init` to generate `nipkg.config.json`, then `slcli webapp pack` to create the `.nipkg`.

Load [references/deployment.md](./references/deployment.md) when the task reaches build, publish, redeploy, or packaging.

### 7. Validate in the hosted environment, not only local dev

Local Angular dev mode does not reproduce the SystemLink shell, iframe, auth, or theme propagation behavior. Hosted validation is required.

Always verify:

- the app renders without layout breakage
- the browser console is clear of blocking errors
- the correct SystemLink data loads
- light/dark theme switching updates the app in real time

Load [references/troubleshooting.md](./references/troubleshooting.md) for the hosted validation flow and symptom-based fixes.

## Minimal implementation checklist

Before you consider a SystemLink webapp slice correct, confirm all of the following:

- Angular 20 workspace created in the intended starter directory.
- `AppModule` provides `APP_BASE_HREF`.
- `index.html` does not contain a `<base>` element.
- Router uses `useHash: true`.
- Production build disables `inlineCritical`.
- Nimble Angular modules are imported explicitly.
- No hardcoded colors in component SCSS.
- Theme-aware aliases live on `nimble-theme-provider`.
- API client uses the correct SystemLink service base URL.
- Hosted deployment is validated after publish.

## Default implementation stance

Use these defaults unless the user asks for a different tradeoff:

- Angular 20
- NgModule-based app
- `@ni/nimble-angular`
- `@ni/spright-angular`
- `@ni/ok-angular`
- `@ni/systemlink-clients-ts`
- table-first data presentation
- same-origin cookie auth
- long-form CLI flags in examples and commands

## Common mistakes to prevent up front

- Treating the app like a normal root-hosted Angular SPA instead of an iframe/sub-path app.
- Checking only the `theme` attribute instead of verifying resolved Nimble tokens.
- Putting theme-aware aliases on `:root`.
- Overriding SDK base URLs with incomplete service prefixes.
- Using raw HTML controls where Nimble primitives should define the interaction model.
- Loading too much reference material before the task requires it.

## When to escalate into the references

- The user asks which components are available across the NI Angular UI packages: load [references/angular-ui-packages.md](./references/angular-ui-packages.md).
- The user asks for exact Angular module imports or Nimble template syntax: load [references/nimble-angular.md](./references/nimble-angular.md).
- The user asks for layout or interaction structure: load [references/layout-patterns.md](./references/layout-patterns.md).
- The task depends on a specific SystemLink API request shape or service root: load [references/systemlink-services.md](./references/systemlink-services.md).
- The task reaches build, publish, redeploy, or packaging: load [references/deployment.md](./references/deployment.md).
- The hosted app is already broken or needs final verification: load [references/troubleshooting.md](./references/troubleshooting.md).
