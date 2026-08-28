# SystemLink WebApps

Load this overview when the task is about a custom Angular web application hosted
inside the SystemLink shell. Stay here first, then load only one or two deeper
reference files when the implementation needs them.

## Progressive loading

| Need                                                                | Read                                               |
| ------------------------------------------------------------------- | -------------------------------------------------- |
| Concise component inventory across Nimble, Spright, and OK Angular  | [angular-ui-packages.md](./angular-ui-packages.md) |
| Nimble Angular modules, wrapper usage, table/dialog/tab patterns    | [nimble-angular.md](./nimble-angular.md)           |
| Page layout, spacing, split panes, drawers, accordions              | [layout-patterns.md](./layout-patterns.md)         |
| SystemLink SDK base URLs, auth modes, LINQ query patterns           | [systemlink-services.md](./systemlink-services.md) |
| Build, publish, Plugin Manager packaging commands                   | [deployment.md](./deployment.md)                   |
| Hosted validation, console triage, theme checks, recurring failures | [troubleshooting.md](./troubleshooting.md)         |

If the user only wants planning or a first implementation slice, stay in this file.

## Component-first rule

Before inventing a surface with `div`s, custom borders, or repeated card shells, check whether the
needed primitive already exists in Nimble, Spright, or OK.

- Use package components for interactive or visual surfaces first.
- Use raw HTML mostly for semantic grouping, flex/grid layout, and text structure.
- Do not build custom-styled buttons, inputs, tabs, drawers, search bars, banners, summary tiles,
  or faux cards when a published NI component already covers the job.
- Treat `div` wrappers as layout scaffolding, not as the primary design language.

Start with these references before authoring bespoke UI:

- Nimble Storybook: https://nimble.ni.dev/storybook/index.html
- Nimble Component APIs: https://nimble.ni.dev/storybook/index.html?path=/docs/component-apis--docs
- Nimble Getting Started: https://nimble.ni.dev/storybook/index.html?path=/docs/getting-started--docs

## First response checklist

Before generating code, clarify only the details that change the implementation:

1. Goal: what the app should show or let the user do.
2. Services: which SystemLink resources it must read or mutate.
3. Starting point: new app via `slcli webapp new`, or an existing Angular codebase.
4. Auth context: same-origin hosted app versus remote/dev API-key flow.
5. Deployment target: ordinary hosted webapp only, or Plugin Manager package as well.

Do not ask about Angular or Nimble versions unless the user is constrained by an existing project. Default to Angular 20 and the latest compatible `@ni/nimble-angular`, but verify the installed versions immediately after scaffold instead of assuming the generator produced the expected combination.

For new SystemLink apps, recommend installing the NI UI packages together unless the user is intentionally minimizing dependencies. `@ni/nimble-angular` remains the default foundation, `@ni/spright-angular` adds Spright chat and icon components, and `@ni/ok-angular` is the default entry point for OK surfaces such as accordion items, search input, summary panels, and other OK wrappers. Do not reach for `@ni/ok-components` directly in normal app code.

## Recommended workflow

### 1. Bootstrap the right project shape

For a new SystemLink app, default to the hosted scaffold path:

```bash
slcli webapp new <app-name>
```

Use `slcli webapp new` for new hosted Angular applications. For an existing
Angular codebase, work in place and skip both scaffold commands. The older
`slcli webapp init` command is a compatibility-only manual bootstrap path and
is not a supported starting point for new skill-guided work.

Prefer a hybrid Angular shape for this workflow: standalone root bootstrap with NgModule-managed feature declarations. That keeps the generated app off `@angular/platform-browser-dynamic` while still letting Nimble Angular wrappers live in a centralized `AppModule` for most feature imports.

Immediately after scaffold, inspect `package.json` and `angular.json` before building features. The generator or migrations may leave the workspace on the wrong Angular major or on a builder configuration that does not bundle `@ni/nimble-angular` cleanly.

#### Establish the operator workflow before extending the template

Treat the generated starter screens as a parts bin, not as the application's final information architecture. Before adding API calls, new routes, or visual polish:

1. Write the primary user job in one sentence.
2. Define the decision the user must make and the evidence needed to make it.
3. Keep one primary workflow and one dominant results surface in the first viewport.
4. Put filters and the primary action next to that results surface.
5. Remove starter routes, tabs, dashboards, cards, status panels, and placeholder content that do not support the job.
6. Keep loading, error, and empty states inside the same workflow rather than creating separate decorative panels for them.
7. Use summary metrics only when they answer a decision the user cannot answer from the main result.

Prefer this compact hierarchy:

- context and purpose
- filters and primary action
- evidence
- supporting detail

Avoid repeating the product identity in both the application shell and page header. Avoid stacking multiple headings, status blocks, KPI cards, and toolbars before the user reaches the main evidence.

After defining the workflow, aggressively prune the starter template. Remove routes, navigation tabs, feature folders, sample UI, demo data, mock handlers, unused state branches, styles, assets, and package dependencies that do not support the job. Keep only the smallest coherent flow and its necessary loading, empty, error, and successful-completion states. Do not keep a generated screen merely because it demonstrates a Nimble pattern, and do not fill every route before the primary workflow is deliberate and working. Remove corresponding route entries, imports, and navigation items, then run the production build so dead template assumptions are caught early.

Validate the composition with populated and empty/error states at desktop and mobile widths. The design is ready when a user can identify the page's purpose, find the main control, and reach the evidence without passing through unrelated starter UI.

For the currently supported path, standardize on:

- Angular 20.x
- Node 24+
- `@ni/nimble-angular` 33.5.x
- `@ni/nimble-components` 35.12.x
- `@ni/unit-format` 1.0.5+
- `@ni/spright-angular` 9.5.x
- `@ni/ok-angular` 2.5.4+
- `@ni/systemlink-clients-ts` 3.0.2
- `@angular/build` for the hosted application builder
- `@angular/localize` installed and added to build polyfills

If the scaffold or a migrated workspace fails to bundle Nimble with `Could not resolve '@ni/nimble-components/dist/esm/...'` while using `@angular/build:application`, switch `angular.json` back to the legacy Angular builders:

- `@angular-devkit/build-angular:browser`
- `@angular-devkit/build-angular:dev-server`
- `@angular-devkit/build-angular:extract-i18n`

Also add `@angular-devkit/build-angular` back to `devDependencies` before switching those builders. The hosted scaffold now standardizes on `@angular/build`, so the legacy builders are not present unless you reinstall them explicitly.

This fallback is not optional when the Nimble packages fail under the application builder. Fix the builder mismatch before implementing more UI.

Install `@ni/spright-angular` and `@ni/ok-angular` early when the first slice
needs chat surfaces, product-specific icons, or OK wrappers. This avoids
dependency churn later without requiring a legacy bootstrap path.

### 2. Lock in the non-negotiables early

These decisions prevent the most common hosted-webapp failures:

- Provide `APP_BASE_HREF` via DI and remove any `<base>` tag from `index.html`.
- Use hash routing with `RouterModule.forRoot(..., { useHash: true })`.
- Disable critical CSS inlining in production with `inlineCritical: false`.
- Use `@ni/nimble-angular` wrapper modules, not raw `@ni/nimble-components`, as the default integration path.
- Do not add `CUSTOM_ELEMENTS_SCHEMA` just to silence missing Nimble module imports.
- Put theme-aware color and shadow aliases on `nimble-theme-provider`, not on `:root`.
- Import `@angular/localize/init` in Angular build polyfills.
- Import Nimble fonts once in the root `src/styles.scss` with `@use '@ni/nimble-angular/styles/fonts' as *;`.
- Run a production build immediately after setup changes. Do not postpone the first `npm run build` until after the UI is implemented.

### 3. Choose the default UI patterns

Use SystemLink-appropriate layout defaults instead of inventing page structure from scratch:

- Use `nimble-table` for primary list/browse/search datasets.
- Keep list/detail views visible together with a split-pane when selection drives preview.
- Use drawers or collapsible side panels for settings and filters.
- Use accordions for grouped fields and advanced configuration.
- Use cards sparingly for summaries, not as the default editing or data layout.
- Prefer NI summary-panel, accordion, table, drawer, tab, banner, and search components before composing a new surface from plain `div`s.

Treat Nimble alignment as a requirement, not a style preference:

- Use Nimble controls for primary actions, selection, inputs, status, and data display.
- Prefer OK and Spright components when they provide a better fit than generic layout wrappers.
- Use raw HTML elements mostly for semantic grouping, layout wrappers, and text structure.
- Do not build custom-styled buttons, inputs, dropdowns, tabs, or pseudo-cards when Nimble already provides the interaction primitive.
- Prefer Nimble spacing, borders, focus states, and theme tokens over bespoke visual treatments.
- If an NI component exists for the surface, use it instead of styling a `div` to imitate it.
- If a page starts to look like a generic marketing dashboard instead of a SystemLink tool, pull it back toward table/list-detail, drawers, banners, tabs, and structured metadata panels.

### 4. Integrate SystemLink APIs the low-risk way

Always prefer `@ni/systemlink-clients-ts` first. Only generate a new client when the needed service is not already covered.

Default rules:

- Build clients at runtime from `window.location.origin`.
- For same-origin hosted apps, use cookie auth with `credentials: 'include'`.
- For remote/dev flows, collect an API key from the user and send it as `x-ni-api-key`.
- Never hardcode hostnames or credentials in source code.
- Treat generated SDK request shapes as fallible; if the SDK body shape is wrong, fall back to direct `fetch`.

### 5. Build the smallest useful vertical slice first

When the user asks for implementation, prefer one working slice over a full app shell rewrite:

- one route
- one data query
- one table or detail view
- one loading state
- one error banner
- one settings/control path only if required

For a new app, the first vertical slice should also prove the setup:

- scaffold completes
- Angular and NI package versions are compatible
- the app builds successfully
- one Nimble-based route renders
- one real SystemLink query works in the hosted shell

### 6. Publish or package only after the hosted constraints are covered

For ordinary hosted deployment, build and publish after the routing, CSP, theme, and client setup are in place.

For Plugin Manager packaging, use `slcli webapp manifest init` to generate `nipkg.config.json`, then `slcli webapp pack` to create the `.nipkg`.

### 7. Validate in the hosted environment, not only local dev

Local Angular dev mode does not reproduce the SystemLink shell, iframe, auth, or theme propagation behavior. Hosted validation is required.

Always verify:

- the app renders without layout breakage
- the browser console is clear of blocking errors
- the correct SystemLink data loads
- light/dark theme switching updates the app in real time
- the page still reads as a Nimble/SystemLink experience rather than a custom HTML dashboard

## Minimal implementation checklist

Before you consider a SystemLink webapp slice correct, confirm all of the following:

- Angular 20 workspace created in the intended starter directory.
- Generated template was pruned to the primary user job rather than retained as a multi-route showcase.
- Primary user job, decision evidence, dominant results surface, and compact page hierarchy are explicit.
- Populated, empty, and error states have been checked at desktop and mobile widths.
- Every retained route, component, dependency, asset, and style supports a real user workflow or required application state.
- Angular and NI package versions verified after scaffold, not assumed.
- `@ni/nimble-components`, `@ni/unit-format`, `@angular/localize`, and `@angular/build` installed when using `@ni/nimble-angular`.
- `angular.json` uses builders that are known to bundle Nimble successfully.
- `AppModule` provides `APP_BASE_HREF`.
- `index.html` does not contain a `<base>` element.
- Router uses `useHash: true`.
- Production build disables `inlineCritical`.
- Root `src/styles.scss` imports `@use '@ni/nimble-angular/styles/fonts' as *;`.
- Nimble Angular modules are imported explicitly.
- Primary interaction controls use Nimble wrappers rather than custom HTML surrogates.
- When Nimble lacks a needed surface, check `angular-ui-packages.md` and the Nimble Storybook before creating a bespoke `div`-based substitute.
- No hardcoded colors in component SCSS.
- Theme-aware aliases live on `nimble-theme-provider`.
- API client uses the correct SystemLink service base URL.
- `npm run build` passes before publish.
- Hosted deployment is validated after publish.

## Default implementation stance

Use these defaults unless the user asks for a different tradeoff:

- Angular 20
- NgModule-based app
- `@ni/nimble-angular`
- `@ni/nimble-components`
- `@ni/unit-format`
- `@ni/spright-angular`
- `@ni/ok-angular`
- `@ni/systemlink-clients-ts`
- table-first data presentation
- same-origin cookie auth
- long-form CLI flags in examples and commands
- Nimble-first interaction design with minimal bespoke chrome
