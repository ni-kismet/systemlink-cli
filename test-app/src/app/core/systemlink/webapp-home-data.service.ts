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
          label: 'Hosted origin',
          value: this.context.origin,
          detail: 'Root future SDK clients and direct fetch calls here.',
          tone: 'info',
        },
        {
          label: 'Auth mode',
          value: this.context.authMode,
          detail: 'Swap with --auth when you need API-key-driven development flows.',
          tone: 'warning',
        },
        {
          label: 'Workspace',
          value: this.context.workspaceName,
          detail: 'Publishing help text and starter docs are already aligned to this workspace.',
          tone: 'success',
        },
      ],
      patterns: [
        'Route-level navigation with Nimble anchor tabs',
        'Search-first Nimble table toolbar with concise Search <items> copy',
        'Drawer-based detail inspection from a primary dataset',
        'Master/detail split pane with read-only detail fields until edit mode',
        'Split operations workspace with manual refresh and a confirm dialog',
        'Grouped settings form with theme-aware sections and readonly hosted facts',
      ],
      nextSteps: [
        'Replace one sample page with a real SystemLink query before adding more routes.',
        'Use Nimble buttons for actions and Nimble anchors or route tabs for navigation.',
        'Preserve hosted query parameters if you later add cross-app breadcrumbs.',
      ],
      readinessMessage:
        'This starter keeps hosted routing, Nimble tokens, and sample control text aligned to current Stratus guidance.',
    };
  }
}
