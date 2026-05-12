# Troubleshooting and Hosted Validation

Use this reference only when the task reaches hosted validation or when the deployed app is already failing.

## Hosted validation flow

Validate the published webapp in the hosted SystemLink environment, not just local Angular dev.

1. Open the app in SystemLink and authenticate if prompted.
2. Inspect the page for missing Nimble styling, broken layout, or blank-screen behavior.
3. Check the browser console for blocking runtime errors.
4. Verify the app loads real data and the main interaction path works.
5. Switch the SystemLink shell between light and dark themes and confirm the app updates immediately.

## Required sign-off checks

- App loads in the hosted shell.
- No critical console errors.
- Nimble components render with the expected styling.
- Theme changes propagate to the app in real time.
- Core workflow succeeds with live data.

## Theme validation

Confirm both the attribute and the resolved token values.

```javascript
const provider = document.querySelector("nimble-theme-provider");
const bg = getComputedStyle(provider).getPropertyValue(
  "--ni-nimble-application-background-color",
);
const text = getComputedStyle(provider).getPropertyValue(
  "--ni-nimble-body-font-color",
);
console.log({ bg, text });
```

If the `theme` attribute changes but the colors do not:

- verify theme-aware aliases are defined on `nimble-theme-provider`, not `:root`
- verify the app updates its `[theme]` binding when the parent provider changes
- verify the provider actually wraps the rendered app shell

## High-value console errors

| Error or symptom                          | Likely cause                                          | Fix                                                                              |
| ----------------------------------------- | ----------------------------------------------------- | -------------------------------------------------------------------------------- |
| `$localize is not defined`                | Angular localize polyfill missing                     | Add `@angular/localize/init` to Angular polyfills                                |
| `Could not resolve '@ni/nimble-components/dist/esm/...'` during build | Nimble package layout not bundling under Angular application builder | Install `@angular-devkit/build-angular` and switch `angular.json` back to the legacy browser/dev-server builders |
| NG04002 or blank screen                   | Path routing under SystemLink sub-path                | Use hash routing                                                                 |
| CSP `base-uri` error                      | `<base>` tag present                                  | Remove `<base>` and provide `APP_BASE_HREF` via DI                               |
| CSP `unsafe-inline` error from styles     | Critical CSS inlining injected handlers               | Set `inlineCritical: false`                                                      |
| CORS error or status `0`                  | Wrong origin or service base URL                      | Recompute base URL from `window.location.origin` plus the correct service prefix |
| 404 on API call                           | Wrong client base URL for the chosen service          | Match the SDK's expected service root                                            |
| Unknown `nimble-*` element                | Missing Angular wrapper module import                 | Import the matching `@ni/nimble-angular` module                                  |
| Theme stays light in dark shell           | Theme aliases on `:root` or missing parent-theme sync | Move aliases to `nimble-theme-provider` and verify theme observer logic          |
| Table data appears empty                  | Query projection flattened the response               | Remove `projection` or update the mapping code                                   |
| `InputFieldValidationError` from SDK call | Generated request body shape is wrong                 | Inspect the raw API shape and use direct `fetch` if needed                       |

## Symptom-based quick fixes

### App renders but looks unstyled

- confirm `nimble-theme-provider` is present
- confirm the required Nimble Angular modules are imported
- confirm the app uses Nimble components instead of native HTML controls for primary interactions
- confirm the page is not relying on custom-styled HTML buttons, inputs, or cards where Nimble controls should own the interaction

### App follows the shell theme attribute but colors still look wrong

- inspect resolved token values with `getComputedStyle`
- remove hardcoded colors from component SCSS
- define theme-aware aliases on `nimble-theme-provider`

### SDK client compiles but calls fail at runtime

- verify the actual service base URL
- verify cookie auth versus API-key mode
- verify the generated request body shape matches the real API

### Build fails before the app ever runs

- verify the Angular major matches the installed `@ni/nimble-angular` peer dependency
- verify `@ni/nimble-components`, `@ni/unit-format`, and `@angular/localize` are installed
- if the workspace uses `@angular/build:application` and Nimble imports fail to resolve, move back to `@angular-devkit/build-angular:browser`
- rerun `npm run build` before changing more application code

### Dialogs or advanced overlays do not open

- do not gate `nimble-dialog` with `*ngIf`
- keep the dialog in the DOM and open it imperatively through `ViewChild`

## Pre-publish review checklist

Before publishing or redeploying, verify:

- no hardcoded colors remain in component styles
- Nimble primitives are used for the main controls and data views
- the page reads as a Nimble/SystemLink tool rather than a bespoke HTML dashboard
- `APP_BASE_HREF` is provided and no `<base>` tag exists
- routing uses `useHash: true`
- production build disables `inlineCritical`
- `@angular/localize/init` is present in polyfills
- the build succeeds cleanly

## When to load other references from here

- Need exact Nimble imports or table/dialog examples: read [nimble-angular.md](./nimble-angular.md)
- Need service URL or request-body details: read [systemlink-services.md](./systemlink-services.md)
- Need build, publish, or packaging commands: read [deployment.md](./deployment.md)
