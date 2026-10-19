import { CommonModule } from '@angular/common';
import { Component } from '@angular/core';
import { NavigationEnd, Router, RouterModule } from '@angular/router';

import { NimbleAnchorTabModule, NimbleAnchorTabsModule } from '@ni/nimble-angular';
import { filter } from 'rxjs';

interface ShellTab {
  id: string;
  label: string;
  route: string;
}

@Component({
  selector: 'sl-app-shell',
  standalone: true,
  imports: [
    CommonModule,
    RouterModule,
    NimbleAnchorTabsModule,
    NimbleAnchorTabModule,
  ],
  templateUrl: './app-shell.component.html',
  styleUrl: './app-shell.component.scss',
})
export class AppShellComponent {
  readonly tabs: readonly ShellTab[] = [
    { id: 'overview', label: $localize`Overview`, route: '/' },
    { id: 'datasets', label: $localize`Data Table`, route: '/datasets' },
    { id: 'assets', label: $localize`Drawer Detail`, route: '/assets' },
    { id: 'master-detail', label: $localize`Master Detail`, route: '/master-detail' },
    { id: 'operations', label: $localize`Operations`, route: '/operations' },
    { id: 'settings', label: $localize`Settings`, route: '/settings' },
  ];

  activeTabId = 'overview';

  constructor(router: Router) {
    this.updateActiveTab(router.url);
    router.events
      .pipe(filter((event): event is NavigationEnd => event instanceof NavigationEnd))
      .subscribe((event: NavigationEnd) => {
        this.updateActiveTab(event.urlAfterRedirects);
      });
  }

  private updateActiveTab(url: string): void {
    const path = url.split('?')[0] || '/';
    const active = this.tabs.find((tab: ShellTab) => {
      if (tab.route === '/') {
        return path === '/';
      }

      return path === tab.route || path.startsWith(`${tab.route}/`);
    });

    this.activeTabId = active?.id ?? 'overview';
  }
}
