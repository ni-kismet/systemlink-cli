# Layout Patterns

Guidance for spacing between controls vertically and horizontally within Nimble-based
SystemLink webapps.

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

## Section spacing

Between major sections or groups of controls:

- Use `largePadding` (24px) between distinct content areas.
- Use `standardPadding` (16px) for subsections within a group.
