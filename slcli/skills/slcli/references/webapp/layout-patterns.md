# Layout Patterns

Guidance for layout, spacing, control text, and navigation patterns within Nimble-based
SystemLink webapps.

## Start with the user's workflow

Before choosing controls or spacing, decide what the user is mainly trying to do on the page.
The bundled webapp starter already includes six route-level patterns. Prefer picking the closest
one and replacing its sample data instead of assembling a new shell from fragments.

| User request sounds like                                                                      | Start from this pattern  | Why this is the right default                                                                                      |
| --------------------------------------------------------------------------------------------- | ------------------------ | ------------------------------------------------------------------------------------------------------------------ |
| "Show me the current state", "landing page", "readiness summary", "overview"                  | Overview route           | Best for orientation, status summaries, lightweight metrics, and links into deeper workflows.                      |
| "List", "browse", "search", "filter", "compare many records"                                  | Filterable dataset route | Keeps the table as the primary surface and puts search/filter actions in the toolbar where users expect them.      |
| "Inspect a record", "preview details", "peek without leaving the list"                        | Drawer-detail route      | Works when the list remains primary and details are secondary, temporary, or read-mostly.                          |
| "Select one item and edit or review it in depth"                                              | Master/detail route      | Fits device-style workflows where the selected item stays in focus and the detail pane is a stable workspace.      |
| "Monitor a queue", "work through operations", "approve/retry/cancel", "live operational work" | Split operations route   | Supports multi-step operational decisions with an active inspector, manual refresh, and confirm actions.           |
| "Configure settings", "preferences", "connection options", "hosted facts"                     | Settings route           | Best for grouped forms, advanced options, and readonly environment facts that should not compete with browse data. |

## Pattern chooser

Use these higher-level starting points when the user request is still vague:

- Orient: choose the overview route when the page mostly explains context, health, or entry points.
- Browse: choose the dataset route when users need to find, sort, filter, or compare many items.
- Inspect: choose the drawer-detail route when users mostly scan a list and occasionally open more detail.
- Work on one item: choose the master/detail route when selection drives a sustained detail or edit task.
- Operate: choose the split operations route when the page supports queue handling, adjudication, or live actions.
- Configure: choose the settings route when the page is mainly about editing preferences or reviewing environment configuration.

## Choosing between the similar patterns

- Drawer-detail versus master/detail: use a drawer when the list stays dominant and the detail view can be dismissed. Use master/detail when the selected record becomes the main workspace.
- Master/detail versus split operations: use master/detail for stable record review or editing. Use split operations when users are processing incoming work, refreshing live state, and confirming actions.
- Overview versus settings: use overview for summaries and navigation into workflows. Use settings for forms, policy choices, and readonly hosted facts.
- Dataset versus overview: use dataset when the page succeeds or fails based on search, filtering, and result density. Use overview when metrics and navigation matter more than row-level exploration.

## Default selection rule

If the request could fit multiple patterns, choose the one that makes the primary object of attention obvious:

- Many records at once: dataset route.
- One selected record: master/detail or drawer-detail.
- A queue of actions: split operations route.
- App or environment configuration: settings route.
- High-level orientation: overview route.

Do not combine multiple starter patterns in the first implementation slice unless the user explicitly asks for a broader shell. Replace one route with a real SystemLink flow, prove it in the hosted shell, then expand.

## Core rules

- Use Nimble components and Nimble design tokens for primary UI. Avoid generic cards as the default page structure for browse, detail, and settings workflows.
- Put toolbars and tab bars in a 40px-tall container with content vertically centered and a `1px solid var(--ni-nimble-divider-background-color)` bottom border.
- Use `nimble-button` for button affordances. If you need clickable list rows or a section rail, style them as navigation rows rather than faux Nimble buttons.
- Keep theme-aware aliases on `nimble-theme-provider`, not on `:root`, so custom colors and surfaces follow the active Nimble theme.

## Spacing tokens

Use Nimble design tokens for consistent spacing between controls.

| Token             | Value | Usage                                                  |
| ----------------- | ----- | ------------------------------------------------------ |
| `smallPadding`    | 4px   | Tight spacing for icon margins and inline element gaps |
| `mediumPadding`   | 8px   | Default spacing between stacked controls               |
| `standardPadding` | 16px  | Section padding and content block margin               |
| `largePadding`    | 24px  | Separation between major layout sections               |

## Control heights

| Token               | Value | Usage                           |
| ------------------- | ----- | ------------------------------- |
| `controlHeight`     | 32px  | Standard height for controls    |
| `controlSlimHeight` | 24px  | Compact control variants        |
| `labelHeight`       | 16px  | Height of labels above controls |

## Control text

- Labels should be present and use sentence case.
- Placeholders should be examples or concise descriptions, not the only source of meaning for dense forms.
- Prefer `readonly` to `disabled` for non-editable text values that users may still need to review or copy.
- Reserve `disabled` for temporarily unavailable actions or controls, not for stable hosted facts.

## Vertical stacking

When stacking controls vertically, such as text fields, number fields, and checkboxes:

- Use `mediumPadding` (8px) as the gap between controls in a flex column.
- Use `standardPadding` (16px) for content padding around the group.
- Labels above controls add `labelHeight` (16px) to the effective row height.

```html
<div
  style="display: flex; flex-direction: column; gap: var(--ni-nimble-medium-padding);"
>
  <nimble-text-field>Label 1</nimble-text-field>
  <nimble-text-field>Label 2</nimble-text-field>
</div>
```

## Horizontal layout

When placing controls side by side:

- Use `mediumPadding` (8px) or `standardPadding` (16px) as the gap.
- Prefer CSS grid with equal columns for aligned layouts.

```html
<div
  style="display: grid; grid-template-columns: 1fr 1fr; gap: var(--ni-nimble-medium-padding);"
>
  <nimble-checkbox>Option A</nimble-checkbox>
  <nimble-checkbox>Option B</nimble-checkbox>
</div>
```

## Filter, query, and search

- For browse tables larger than roughly 25 rows, put a text filter in the toolbar with a `Search <items>` placeholder.
- Add column or secondary filters for enumerated fields such as status, type, or owner.
- Keep the table as the primary information surface; do not wrap the whole workflow in a card just to contain the controls.
- Query builders or advanced filter panels are only worth the complexity when the dataset is substantially larger or the filtering model is genuinely compound.

## Accordion content

Inside accordion item content panels:

- Use `flex-direction: column` with `mediumPadding` (8px) gap between controls.
- Indent content by the icon width plus padding so it aligns with the header text.
- Use `standardPadding` (16px) for bottom padding before the next section.

## Tabs in side panels

When using tabs inside a dense side panel or details pane:

- Use `padding: 15px 30px 30px 15px` on the tab control container.
- Use `padding: 20px 0 0 15px` on the active tab panel content region.
- Let the tab panel container own scrolling.
- Avoid forcing nested form or content blocks to `height: 100%`; it tends to distort vertical
  spacing between controls.
- Inside the active tab panel, keep stacked controls on a `mediumPadding` (8px) gap unless a
  tighter layout is explicitly needed.

```html
<div style="padding: 15px 30px 30px 15px;">
  <nimble-tabs>
    <nimble-tab id="details">Details</nimble-tab>
    <nimble-tab id="settings">Settings</nimble-tab>
  </nimble-tabs>
  <div
    style="padding: 20px 0 0 15px; overflow: auto; display: flex; flex-direction: column; gap: var(--ni-nimble-medium-padding);"
  >
    <nimble-text-field>Label 1</nimble-text-field>
    <nimble-text-field>Label 2</nimble-text-field>
  </div>
</div>
```

## Links and navigation

- Links navigate. Buttons act.
- Use route tabs, `nimble-anchor`, or other anchors for navigation flows that change location.
- Use `nimble-button` for mutations, dialog launches, refreshes, exports, and other in-place actions.
- Same-app tab switches, drawers, and modals should not be modeled as breadcrumb changes.

## Section spacing

Between major sections or groups of controls:

- Use `largePadding` (24px) between distinct content areas.
- Use `standardPadding` (16px) for subsections within a group.

## Refresh controls

- Static overview, configuration, or reference pages generally do not need polling.
- Add a manual refresh control when the view reflects live operational data that may change outside the current session.
- Pair refresh with a mode selector only when users genuinely need to switch between automatic and manual refresh behavior.

## Breadcrumbs

- Breadcrumbs should represent cross-app or cross-workspace hierarchy, not local tab state.
- If the app is opened from a parent SystemLink experience, preserve breadcrumb context through query parameters when routing deeper into the app.
- Avoid rewriting breadcrumb state during same-app tab switches, drawer opens, or in-page filtering.
