import { Injectable } from '@angular/core';

import { SystemLinkContextService } from './systemlink-context.service';

export interface HomeMetric {
  label: string;
  value: string;
  detail: string;
  tone: 'info' | 'success' | 'warning';
}

export interface HomePageModel {
  metrics: HomeMetric[];
  patterns: string[];
  nextSteps: string[];
  readinessMessage: string;
}

@Injectable({ providedIn: 'root' })
export class WebappHomeDataService {
  constructor(private readonly context: SystemLinkContextService) {}

  async load(): Promise<HomePageModel> {
    return {
      metrics: [
        {
          label: $localize`Hosted origin`,
          value: this.context.origin,
          detail: $localize`Root future SDK clients and direct fetch calls here.`,
          tone: 'info',
        },
        {
          label: $localize`Auth mode`,
          value: this.context.authMode,
          detail: $localize`Swap with --auth when you need API-key-driven development flows.`,
          tone: 'warning',
        },
        {
          label: $localize`Workspace`,
          value: this.context.workspaceName,
          detail: $localize`Publishing help text and starter docs are already aligned to this workspace.`,
          tone: 'success',
        },
      ],
      patterns: [
        $localize`Route-level navigation with Nimble anchor tabs`,
        $localize`Search-first Nimble table toolbar with concise Search <items> copy`,
        $localize`Drawer-based detail inspection from a primary dataset`,
        $localize`Master/detail split pane with read-only detail fields until edit mode`,
        $localize`Split operations workspace with manual refresh and a confirm dialog`,
        $localize`Grouped settings form with theme-aware sections and readonly hosted facts`,
      ],
      nextSteps: [
        $localize`Replace one sample page with a real SystemLink query before adding more routes.`,
        $localize`Use Nimble buttons for actions and Nimble anchors or route tabs for navigation.`,
        $localize`Preserve hosted query parameters if you later add cross-app breadcrumbs.`,
      ],
      readinessMessage:
        $localize`This starter keeps hosted routing, Nimble tokens, and sample control text aligned to current Stratus guidance.`,
    };
  }
}
