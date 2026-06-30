# Angular UI Packages — Concise Component Reference

Use this file when you need a quick package-level inventory before choosing components. Load `nimble-angular.md` only after you know which Nimble components you actually need.

## Install recommendation

For new SystemLink webapps, prefer installing the NI Angular UI packages together:

```bash
npm install @ni/nimble-angular @ni/spright-angular @ni/ok-angular
```

Use Nimble as the default foundation, then pull in Spright and OK Angular when the app needs their specialized components.

## Package roles

| Package               | Primary role                                           | When to reach for it                                                                                                       |
| --------------------- | ------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------------------- |
| `@ni/nimble-angular`  | Core SystemLink-aligned component foundation           | Use for the default app shell, tables, buttons, inputs, drawers, banners, dialogs, navigation, and most day-to-day UI work |
| `@ni/spright-angular` | Spright chat, rectangle, and NI-specific icon wrappers | Use for chat experiences, AI/copilot surfaces, and Spright-specific iconography                                            |
| `@ni/ok-angular`      | OK-specific interaction components                     | Use when the design needs OK accordion items, OK search input, or OK button primitives                                     |

## Recommended AppModule example

Use this as a starting point when a SystemLink webapp needs components from all three packages. Trim the imports down to only the modules the feature actually uses.

```typescript
import { NgModule } from "@angular/core";
import { BrowserModule } from "@angular/platform-browser";
import { FormsModule } from "@angular/forms";
import { APP_BASE_HREF } from "@angular/common";

import {
  NimbleThemeProviderModule,
  NimbleButtonModule,
  NimbleBannerModule,
  NimbleDrawerModule,
  NimbleTableModule,
  NimbleTableColumnTextModule,
} from "@ni/nimble-angular";
import { NimbleLabelProviderCoreModule } from "@ni/nimble-angular/label-provider/core";

import { SprightChatConversationModule } from "@ni/spright-angular/chat/conversation";
import { SprightChatInputModule } from "@ni/spright-angular/chat/input";
import { SprightChatMessageInboundModule } from "@ni/spright-angular/chat/message/inbound";
import { SprightChatMessageOutboundModule } from "@ni/spright-angular/chat/message/outbound";

import { OkFvAccordionItemModule } from "@ni/ok-angular/fv/accordion-item";
import { OkFvSearchInputModule } from "@ni/ok-angular/fv/search-input";

import { AppComponent } from "./app.component";

@NgModule({
  declarations: [AppComponent],
  imports: [
    BrowserModule,
    FormsModule,
    NimbleThemeProviderModule,
    NimbleLabelProviderCoreModule,
    NimbleButtonModule,
    NimbleBannerModule,
    NimbleDrawerModule,
    NimbleTableModule,
    NimbleTableColumnTextModule,
    SprightChatConversationModule,
    SprightChatInputModule,
    SprightChatMessageInboundModule,
    SprightChatMessageOutboundModule,
    OkFvAccordionItemModule,
    OkFvSearchInputModule,
  ],
  providers: [{ provide: APP_BASE_HREF, useValue: "/" }],
  bootstrap: [AppComponent],
})
export class AppModule {}
```

Keep imports explicit. Do not use `CUSTOM_ELEMENTS_SCHEMA` as a substitute for importing the right Angular wrapper modules.

## Concise inventory

### `@ni/nimble-angular`

This package is the default baseline. The detailed usage reference lives in [nimble-angular.md](./nimble-angular.md).

Representative components already documented there include:

- `nimble-theme-provider`
- `nimble-table`
- `nimble-table-column-text`
- `nimble-button`
- `nimble-anchor-tabs`
- `nimble-anchor-tab`
- `nimble-text-field`
- `nimble-select`
- `nimble-list-option`
- `nimble-drawer`
- `nimble-spinner`
- `nimble-banner`
- `nimble-dialog`

### `@ni/spright-angular`

Published Angular wrappers currently include:

| Tag                             | Angular symbol                     | Import path                                 | Use                                                                       |
| ------------------------------- | ---------------------------------- | ------------------------------------------- | ------------------------------------------------------------------------- |
| `spright-chat-conversation`     | `SprightChatConversationModule`    | `@ni/spright-angular/chat/conversation`     | Container for chat transcripts                                            |
| `spright-chat-input`            | `SprightChatInputModule`           | `@ni/spright-angular/chat/input`            | Chat composer with send, stop, and error states                           |
| `spright-chat-message`          | `SprightChatMessageModule`         | `@ni/spright-angular/chat/message`          | Generic chat message wrapper; prefer specific message types when possible |
| `spright-chat-message-inbound`  | `SprightChatMessageInboundModule`  | `@ni/spright-angular/chat/message/inbound`  | Inbound assistant or service message block                                |
| `spright-chat-message-outbound` | `SprightChatMessageOutboundModule` | `@ni/spright-angular/chat/message/outbound` | Outbound user message block                                               |
| `spright-chat-message-system`   | `SprightChatMessageSystemModule`   | `@ni/spright-angular/chat/message/system`   | Neutral or system-status message block                                    |
| `spright-chat-message-welcome`  | `SprightChatMessageWelcomeModule`  | `@ni/spright-angular/chat/message/welcome`  | Welcome or zero-state chat surface                                        |
| `spright-rectangle`             | `SprightRectangleModule`           | `@ni/spright-angular/rectangle`             | Basic Spright rectangle primitive                                         |

Published Spright icon directives currently include:

- `spright-icon-nigel-chat` from `@ni/spright-angular/icons/nigel-chat`
- `spright-icon-work-item-calendar-week` from `@ni/spright-angular/icons/work-item-calendar-week`
- `spright-icon-work-item-calipers` from `@ni/spright-angular/icons/work-item-calipers`
- `spright-icon-work-item-forklift` from `@ni/spright-angular/icons/work-item-forklift`
- `spright-icon-work-item-rectangle-check-lines` from `@ni/spright-angular/icons/work-item-rectangle-check-lines`
- `spright-icon-work-item-user-helmet-safety` from `@ni/spright-angular/icons/work-item-user-helmet-safety`
- `spright-icon-work-item-wrench-hammer` from `@ni/spright-angular/icons/work-item-wrench-hammer`

### `@ni/ok-angular`

Published Angular wrappers in `@ni/ok-angular@2.4.0` currently include:

| Tag                         | Angular symbol                | Import path                             | Use                                          |
| --------------------------- | ----------------------------- | --------------------------------------- | -------------------------------------------- |
| `ok-ex-button`              | `OkExButtonModule`            | `@ni/ok-angular/ex/button`              | OK button primitive                          |
| `ok-fv-accordion-item`      | `OkFvAccordionItemModule`     | `@ni/ok-angular/fv/accordion-item`      | OK accordion item for grouped content        |
| `ok-fv-card`                | `OkFvCardModule`              | `@ni/ok-angular/fv/card`                | OK card surface with title and description   |
| `ok-fv-chip-selector`       | `OkFvChipSelectorModule`      | `@ni/ok-angular/fv/chip-selector`       | Multi-value chip selector control            |
| `ok-fv-context-help`        | `OkFvContextHelpModule`       | `@ni/ok-angular/fv/context-help`        | Inline context-help or severity help content |
| `ok-fv-search-input`        | `OkFvSearchInputModule`       | `@ni/ok-angular/fv/search-input`        | OK search input control                      |
| `ok-fv-split-button`        | `OkFvSplitButtonModule`       | `@ni/ok-angular/fv/split-button`        | Split button with primary and menu actions   |
| `ok-fv-split-button-anchor` | `OkFvSplitButtonAnchorModule` | `@ni/ok-angular/fv/split-button-anchor` | Anchor-style split button                    |
| `ok-fv-summary-panel`       | `OkFvSummaryPanelModule`      | `@ni/ok-angular/fv/summary-panel`       | Summary panel container                      |
| `ok-fv-summary-panel-tile`  | `OkFvSummaryPanelTileModule`  | `@ni/ok-angular/fv/summary-panel-tile`  | Summary panel metric or status tile          |

## Selection guidance

- Start with Nimble for the app shell and the majority of controls.
- Add Spright when the app needs chat UI or Spright-specific iconography.
- Add OK Angular when the design specifically benefits from its accordion item, search input, chip selector, split button, summary panel, card, or OK button components.
- Keep imports explicit at the module level; do not use `CUSTOM_ELEMENTS_SCHEMA` as a shortcut for missing wrappers.

## Next step references

- Need exact Nimble templates and patterns: read [nimble-angular.md](./nimble-angular.md)
- Need layout guidance after choosing components: read [layout-patterns.md](./layout-patterns.md)
