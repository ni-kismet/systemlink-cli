import { Component } from '@angular/core';

import { ThemeSyncService } from './core/systemlink/theme-sync.service';

@Component({
  selector: 'app-root',
  standalone: false,
  templateUrl: './app.component.html',
  styleUrl: './app.component.scss',
})
export class AppComponent {
  constructor(public readonly themeSync: ThemeSyncService) {}
}
