# Nimble Angular — Template & Usage Reference

If you need a quick inventory across `@ni/nimble-angular`, `@ni/spright-angular`, and `@ni/ok-angular` before picking components, read [angular-ui-packages.md](./angular-ui-packages.md) first. This file stays focused on Nimble-specific usage patterns once you already know you need Nimble components.

## Contents

- [Wrapper-first rule](#wrapper-first-rule)
- [Fonts](#fonts)
- [nimble-theme-provider](#nimble-theme-provider)
- [nimble-table](#nimble-table)
- [nimble-table-column-text](#nimble-table-column-text)
- [nimble-button](#nimble-button)
- [nimble-anchor](#nimble-anchor)
- [nimble-anchor-tabs + nimble-anchor-tab](#nimble-anchor-tabs--nimble-anchor-tab)
- [nimble-text-field](#nimble-text-field)
- [nimble-select + nimble-list-option](#nimble-select--nimble-list-option)
- [nimble-drawer](#nimble-drawer)
- [nimble-spinner](#nimble-spinner)
- [nimble-banner](#nimble-banner)
- [nimble-dialog](#nimble-dialog)
- [Layout patterns](#layout-patterns)

## Wrapper-first rule

When building Angular apps with Nimble, use `@ni/nimble-angular` wrapper modules as the default integration path.

- Import the needed Angular module for each Nimble control instead of registering raw custom elements from `@ni/nimble-components`.
- Do not add `CUSTOM_ELEMENTS_SCHEMA` just to silence unknown Nimble elements in templates. That usually hides a missing module import and weakens Angular's template validation.
- If a Nimble icon or control is unknown, first look for the matching module in `@ni/nimble-angular` and import it.
- If a Nimble wrapper does not exist, check `angular-ui-packages.md` and the Nimble Storybook before creating a custom HTML substitute.
- Prefer a published NI component over styling a `div` to mimic the same interaction or surface.

## Fonts

Nimble requires the Source Sans Pro font family. Without this import, all Nimble components render with fallback system fonts (Arial) and the UI will not match the SystemLink design system.

Import the fonts **once** in the root `src/styles.scss`:

```scss
@use '@ni/nimble-angular/styles/fonts' as *;
```

This registers `@font-face` declarations for Source Sans Pro (Regular, Light, SemiBold) and Source Code Pro, loading `.woff2` files bundled in `@ni/nimble-tokens`.

In the same global stylesheet, prefer token-backed font shorthands over hard-coded font stacks:

```scss
body {
  font: var(--ni-nimble-body-font);
  color: var(--ni-nimble-body-font-color);
  background: var(--ni-nimble-application-background-color);
}
```

To use Nimble design tokens (colors, font sizes, spacing) in component SCSS files, also import:

```scss
@use '@ni/nimble-angular/styles/tokens' as *;

.my-element {
  font-family: $ni-nimble-body-font-family;
  font-size: $ni-nimble-body-font-size;
  color: $ni-nimble-body-font-color;
}
```

Do not duplicate the fonts import in component SCSS — it belongs only in the global `styles.scss`.

## nimble-theme-provider

Wrap your entire app. Always place at the root component level.

```html
<nimble-theme-provider [theme]="currentTheme">
  <router-outlet></router-outlet>
</nimble-theme-provider>
```

Themes: `light`, `dark`, `color` (high contrast).

For SystemLink-hosted apps, do not hard-code `theme="light"` unless the user explicitly wants a fixed theme. The common pattern is:

1. Detect initial theme from `?theme=...`, then the parent frame's `nimble-theme-provider`, then local storage, then system preference
2. If the app is hosted in a same-origin iframe, watch the parent provider's `theme` attribute with `MutationObserver` and update `currentTheme`
3. Define theme-aware CSS aliases such as colors and shadows on `nimble-theme-provider`, not on `:root`, so token resolution follows the active Nimble theme

When debugging theme mismatches, inspect resolved token values on the provider with `getComputedStyle(provider).getPropertyValue('--ni-nimble-application-background-color')` rather than only checking the `theme` attribute.

---

## nimble-table

Displays tabular data. Current wrappers support both `[data$]` for straightforward observable-backed tables and `NimbleTableDirective.setData()` for local filtered arrays or post-view-init updates.

### Module

```typescript
import { NimbleTableDirective, NimbleTableModule } from "@ni/nimble-angular/table";
```

### Row type requirement

Your row type must satisfy `TableRecord`. Add an index signature:

```typescript
interface MyRow {
  id: string;
  name: string;
  value: string | undefined;
  [key: string]: TableFieldValue | undefined; // required for TableRecord compatibility
}
```

### Template

```html
<nimble-table
  [data$]="rows$"
  id-field-name="id"
  selection-mode="single"
  (selection-change)="onSelectionChange($event)"
>
  <nimble-table-column-text field-name="name" column-id="col-name"
    >Name</nimble-table-column-text
  >

  <nimble-table-column-text field-name="value" column-id="col-value"
    >Value</nimble-table-column-text
  >
</nimble-table>
```

### Component wiring

```typescript
import { AfterViewInit, ViewChild } from '@angular/core';
import {
  NimbleTableDirective,
  TableFieldValue,
  TableRecord,
  TableRowSelectionEventDetail,
} from '@ni/nimble-angular/table';
import { BehaviorSubject } from 'rxjs';

rows$ = new BehaviorSubject<MyRow[]>([]);

@ViewChild(NimbleTableDirective) private table?: NimbleTableDirective<MyRow>;

onSelectionChange(event: CustomEvent<TableRowSelectionEventDetail>): void {
  const selectedId = event.detail.selectedRecordIds[0];
  // ...
}

async ngAfterViewInit(): Promise<void> {
  await this.table?.setData(rows);
}
```

- The current event detail type is not generic.
- Selection changes expose `selectedRecordIds`, not `selectedRecords`.
- Do not force `nimble-table` to `display: block`; Nimble's default host display is part of the virtualization contract.
- Prefer `setData()` when you already have a concrete array after filtering or after view initialization. Use `[data$]` when an observable is the natural source of truth.

---

## nimble-table-column-text

Simple string column. Import: `NimbleTableColumnTextModule` from `@ni/nimble-angular/table-column/text`.

```html
<nimble-table-column-text field-name="myField" column-id="col-1">
  Column Header
</nimble-table-column-text>
```

---

## nimble-button

```typescript
import { NimbleButtonModule } from "@ni/nimble-angular";
```

```html
<!-- Default -->
<nimble-button (click)="doSomething()">Click Me</nimble-button>

<!-- Accent/primary style -->
<nimble-button
  appearance="block"
  appearance-variant="accent"
  (click)="doSomething()"
>
  Primary Action
</nimble-button>

<!-- Ghost / low-emphasis -->
<nimble-button appearance="ghost" (click)="cancel()">Cancel</nimble-button>
```

> **Note:** `appearance="accent"` is NOT valid. Use `appearance="block" appearance-variant="accent"`.

Use Nimble buttons for actions, confirmations, refreshes, exports, and dialog launches. Do not style native `<button>` elements to mimic Nimble buttons.

---

## nimble-anchor

```typescript
import { NimbleAnchorModule } from "@ni/nimble-angular";
```

```html
<nimble-anchor href="/specifications/123">View specification</nimble-anchor>
```

Use anchors for navigation. If the interaction changes route or location, prefer `nimble-anchor` or `nimble-anchor-tab` over a button.

---

## nimble-anchor-tabs + nimble-anchor-tab

Use for top-level page navigation. Bind `[activeid]` from component state; update it by tracking `NavigationEnd` router events.

```typescript
import {
  NimbleAnchorTabsModule,
  NimbleAnchorTabModule,
} from "@ni/nimble-angular";
```

```html
<nimble-anchor-tabs [activeid]="activeTabId">
  <nimble-anchor-tab id="catalog" nimbleRouterLink="/catalog"
    >Catalog</nimble-anchor-tab
  >
  <nimble-anchor-tab id="installed" nimbleRouterLink="/installed"
    >Installed</nimble-anchor-tab
  >
  <nimble-anchor-tab id="settings" nimbleRouterLink="/settings"
    >Settings</nimble-anchor-tab
  >
</nimble-anchor-tabs>
```

Track active tab in the component (see `SKILL.md → Step 9` for full `NavigationEnd` subscription pattern).

> Do not use `<nimble-tabs>` + `<nimble-tab-panel>` for navigation — that pattern is for tabbed content within a single page, not routing.

---

## nimble-text-field

```typescript
import { NimbleTextFieldModule } from "@ni/nimble-angular";
```

```html
<!-- Basic -->
<nimble-text-field
  [(ngModel)]="filterValue"
  placeholder="Search items"
  (ngModelChange)="onFilterChange()"
>
  Filter
</nimble-text-field>

<!-- With icon prefix (slot="start") -->
<nimble-text-field
  placeholder="Search…"
  [(ngModel)]="searchTerm"
  (ngModelChange)="applyFilters()"
>
  <nimble-icon-magnifying-glass slot="start"></nimble-icon-magnifying-glass>
</nimble-text-field>
```

Use the text inside the element as the control's primary label. Do not add a separate HTML `<label>` element for the basic Nimble control label unless you have a specific accessibility or layout need that cannot be expressed with Nimble's built-in labeling pattern.

Prefer concise placeholders such as `Search runs` or `Search devices` for toolbar filters. For non-editable text fields, use `[readonly]="true"` or a stateful readonly binding instead of disabling the control.

Import icon modules from the **main `@ni/nimble-angular` barrel** — icon-specific sub-paths do not exist:

```typescript
import { NimbleIconMagnifyingGlassModule } from "@ni/nimble-angular";
```

> Use `(ngModelChange)` rather than `(change)` for reactive value handling. `(change)` fires on blur only; `(ngModelChange)` fires on every keystroke.

---

## nimble-select + nimble-list-option

```typescript
import { NimbleSelectModule, NimbleListOptionModule } from "@ni/nimble-angular";
```

```html
<!-- Basic -->
<nimble-select [(ngModel)]="selectedType" (ngModelChange)="onTypeChange()">
  Type
  <nimble-list-option value="">All types</nimble-list-option>
  <nimble-list-option value="DOUBLE">Double</nimble-list-option>
  <nimble-list-option value="STRING">String</nimble-list-option>
  <nimble-list-option value="BOOLEAN">Boolean</nimble-list-option>
</nimble-select>

<!-- With built-in filter (useful for long lists) -->
<nimble-select filter-mode="standard" [(ngModel)]="selectedWorkspace">
  Workspace
  <nimble-list-option *ngFor="let ws of workspaces" [value]="ws.id"
    >{{ ws.name }}</nimble-list-option
  >
</nimble-select>
```

Use the slotted text content as the select label instead of pairing the control with a separate HTML `<label>` for the primary label.

> Use `filter-mode="standard"` to add a built-in text filter to the dropdown — no custom search logic needed for long option lists.

If a select needs to remain visible but non-editable, use `appearance-readonly` / `appearanceReadOnly` rather than a nonexistent `readonly` input.

---

## nimble-drawer

Side panel for details or config. Control with `#drawerRef` template variable.

```typescript
import { NimbleDrawerModule } from "@ni/nimble-angular";
```

```html
<nimble-drawer #detailDrawer location="right">
  <h3 slot="header">Detail</h3>
  <div>{{ selectedItem?.name }}</div>
  <nimble-button slot="footer" (click)="detailDrawer.hide()"
    >Close</nimble-button
  >
</nimble-drawer>

<nimble-button (click)="detailDrawer.show()">Open Detail</nimble-button>
```

---

## nimble-spinner

```typescript
import { NimbleSpinnerModule } from "@ni/nimble-angular";
```

```html
<nimble-spinner *ngIf="loading"></nimble-spinner>
```

---

## nimble-banner

For in-page error/warning/info messages.

```typescript
import { NimbleBannerModule } from "@ni/nimble-angular";
```

```html
<nimble-banner *ngIf="error" severity="error" [open]="!!error">
  {{ error }}
</nimble-banner>
```

---

## nimble-dialog

**Critical:** never put `*ngIf` on a `nimble-dialog`. The `*ngIf="false"` removes the element from the DOM, making `@ViewChild` return `undefined` and `.show()` impossible to invoke.

```typescript
import { NimbleDialogModule } from "@ni/nimble-angular";
```

```html
<!-- Keep the dialog always in the DOM -->
<nimble-dialog #confirmDialog>
  <span slot="title">Confirm Action</span>
  <span slot="subtitle">This cannot be undone.</span>

  <p>Are you sure you want to proceed?</p>

  <!-- Multiple slot="footer" elements are displayed side by side -->
  <nimble-button slot="footer" (click)="closeDialog()">Cancel</nimble-button>
  <nimble-button
    slot="footer"
    appearance="block"
    appearance-variant="accent"
    (click)="confirm()"
    >Confirm</nimble-button
  >
</nimble-dialog>
```

```typescript
import { ElementRef, ViewChild } from '@angular/core';

@ViewChild('confirmDialog') private dialogEl?: ElementRef;

openDialog(): void  { this.dialogEl?.nativeElement.show(); }
closeDialog(): void { this.dialogEl?.nativeElement.close(); }
```

**Available slots:** `title` (required text), `subtitle` (optional descriptive text), `footer` (action buttons — multiple allowed).

---

## Layout patterns

Nimble doesn't ship a grid/layout component. Use flexbox in SCSS:

```scss
// component.scss
:host {
  display: flex;
  flex-direction: column;
  height: 100%;
  padding: 16px;
  box-sizing: border-box;
}

.toolbar {
  display: flex;
  gap: 8px;
  align-items: flex-end;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

.table-container {
  flex: 1;
  min-height: 0; // important — lets flex child shrink below its content height
}

nimble-table {
  height: 100%;
}
```

### Clickable card / list-row pattern

For any clickable tile or row, use Nimble tokens directly (not the `--sl-app-color-border` alias which is for dividers):

```scss
.card {
  border: 1px solid var(--ni-nimble-card-border-color);
  background: var(--ni-nimble-section-background-color);
  border-radius: var(--ni-nimble-small-padding, 4px);
  cursor: pointer;
  // Transition both shadow and border for a polished hover
  transition:
    box-shadow var(--ni-nimble-medium-delay, 0.15s) ease,
    border-color var(--ni-nimble-medium-delay, 0.15s) ease;

  &:hover {
    box-shadow: var(
      --ni-nimble-elevation-2-box-shadow,
      0 2px 8px rgba(0, 0, 0, 0.12)
    );
    border-color: var(--ni-nimble-border-hover-color);
  }
}

// For equal-height cards in a CSS grid, the host element must fill the cell:
:host {
  display: flex;
  height: 100%;
}

.card {
  flex: 1; // fills the :host flex container
}

.card-body {
  flex: 1; // pushes footer to the bottom
}

.card-description {
  flex: 1; // equalises description height across cards
}
```
