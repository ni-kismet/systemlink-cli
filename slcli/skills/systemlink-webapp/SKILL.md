---
name: systemlink-webapp
description: >-
  Build, configure, troubleshoot, and deploy custom Angular web applications
  hosted inside NI SystemLink. Use when the task involves Nimble Angular,
  SystemLink REST or TypeScript clients, hosted routing, CSP, theme sync, or
  `slcli webapp` packaging and publish flows.
argument-hint: >-
  Describe the app or page you want to build and which SystemLink data it
  should show or mutate.
---

# SystemLink WebApps

Use this skill for hosted Angular work inside the SystemLink shell.

## Start here

- Use `slcli webapp new` for the recommended hosted Angular starter.
- Use `slcli webapp init` when you intentionally want the low-level manual path
  with starter prompts and project-scoped skills.
- Keep the first implementation slice small: one route, one data source, one
  loading state, and one error path.

## Progressive loading

| Need | Read |
| --- | --- |
| Package inventory across Nimble, Spright, and OK | [angular-ui-packages.md](../slcli/references/webapp/angular-ui-packages.md) |
| Nimble wrapper modules and template patterns | [nimble-angular.md](../slcli/references/webapp/nimble-angular.md) |
| Layout, split panes, drawers, and page structure | [layout-patterns.md](../slcli/references/webapp/layout-patterns.md) |
| SystemLink service roots, auth modes, and request shapes | [systemlink-services.md](../slcli/references/webapp/systemlink-services.md) |
| Build, publish, and Plugin Manager packaging | [deployment.md](../slcli/references/webapp/deployment.md) |
| Hosted validation and symptom-based fixes | [troubleshooting.md](../slcli/references/webapp/troubleshooting.md) |
| Related CLI command syntax | [commands.md](../slcli/references/commands.md#webapp--web-application-management) |

## Non-negotiables

- Keep `APP_BASE_HREF` in DI and do not add a `<base>` tag.
- Use hash routing for hosted sub-path navigation.
- Disable production `inlineCritical` CSS inlining.
- Prefer `@ni/nimble-angular` wrapper modules over raw custom elements.
- Validate in the hosted SystemLink shell, not only in local Angular dev mode.