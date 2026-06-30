import { CommonModule } from '@angular/common';
import { Component } from '@angular/core';
import { NavigationEnd, Router, RouterModule } from '@angular/router';

import { NimbleAnchorTabModule, NimbleAnchorTabsModule } from '@ni/nimble-angular';
import { filter } from 'rxjs';

import { AppRoutingModule } from '../../app-routing.module';
import { SystemLinkContextService } from '../systemlink/systemlink-context.service';

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
    AppRoutingModule,
    NimbleAnchorTabsModule,
    NimbleAnchorTabModule,
  ],
  templateUrl: './app-shell.component.html',
  styleUrl: './app-shell.component.scss',
})
export class AppShellComponent {
  readonly tabs: readonly ShellTab[] = [
    { id: 'overview', label: 'Overview', route: '/' },
    { id: 'datasets', label: 'Data Table', route: '/datasets' },
    { id: 'assets', label: 'Drawer Detail', route: '/assets' },
    { id: 'master-detail', label: 'Master Detail', route: '/master-detail' },
    { id: 'operations', label: 'Operations', route: '/operations' },
    { id: 'settings', label: 'Settings', route: '/settings' },
  ];

  activeTabId = 'overview';

  constructor(
    public readonly context: SystemLinkContextService,
    router: Router,
  ) {
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
