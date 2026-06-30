import { Injectable, NgZone } from '@angular/core';

export type NimbleTheme = 'light' | 'dark' | 'color';

@Injectable({ providedIn: 'root' })
export class ThemeSyncService {
  private readonly autoSync = true;
  private readonly observerTarget = this.resolveParentThemeProvider();
  private observer?: MutationObserver;
  private themeValue: NimbleTheme = this.resolveInitialTheme();

  constructor(private readonly zone: NgZone) {
    if (this.autoSync && this.observerTarget) {
      this.observer = new MutationObserver(() => {
        const parentTheme = this.readTheme(this.observerTarget?.getAttribute('theme'));
        if (!parentTheme) {
          return;
        }
        this.zone.run(() => {
          this.themeValue = parentTheme;
        });
      });

      this.observer.observe(this.observerTarget, {
        attributes: true,
        attributeFilter: ['theme'],
      });
    }
  }

  get theme(): NimbleTheme {
    return this.themeValue;
  }

  private resolveInitialTheme(): NimbleTheme {
    return this.resolveThemeFromQuery() ?? this.readTheme(this.observerTarget?.getAttribute('theme')) ?? this.resolveSystemTheme();
  }

  private resolveThemeFromQuery(): NimbleTheme | null {
    const query = new URLSearchParams(window.location.search);
    return this.readTheme(query.get('theme'));
  }

  private resolveParentThemeProvider(): Element | null {
    try {
      if (window.parent === window) {
        return null;
      }
      return window.parent.document.querySelector('nimble-theme-provider');
    } catch {
      return null;
    }
  }

  private resolveSystemTheme(): NimbleTheme {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
  }

  private readTheme(value: string | null | undefined): NimbleTheme | null {
    if (value === 'light' || value === 'dark' || value === 'color') {
      return value;
    }
    return null;
  }
}
