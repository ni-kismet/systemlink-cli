import { Component } from '@angular/core';

import { NimbleThemeProviderModule } from '@ni/nimble-angular';

import { ThemeSyncService } from './core/systemlink/theme-sync.service';
import { AppShellComponent } from './core/layout/app-shell.component';

@Component({
  selector: 'app-root',
  standalone: true,
  imports: [NimbleThemeProviderModule, AppShellComponent],
  templateUrl: './app.component.html',
  styleUrl: './app.component.scss',
})
export class AppComponent {
  constructor(public readonly themeSync: ThemeSyncService) {}
}
