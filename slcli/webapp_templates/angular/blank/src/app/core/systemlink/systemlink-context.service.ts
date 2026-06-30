import { Injectable } from '@angular/core';

export type AuthMode = 'same-origin' | 'api-key';

@Injectable({ providedIn: 'root' })
export class SystemLinkContextService {
  readonly appName = '{{APP_NAME}}';
  readonly publishName = '{{PUBLISH_NAME}}';
  readonly workspaceName = '{{WORKSPACE_NAME}}';
  readonly authMode: AuthMode = '{{AUTH_MODE}}';

  get origin(): string {
    return window.location.origin;
  }

  buildApiUrl(servicePath: string): string {
    return `${this.origin}/${servicePath.replace(/^\/+/, '')}`;
  }

  buildRequestInit(init: RequestInit = {}): RequestInit {
    const headers = new Headers(init.headers ?? {});
    if (this.authMode === 'api-key') {
      const apiKey = window.localStorage.getItem('slcli.webapp.apiKey');
      if (apiKey) {
        headers.set('x-ni-api-key', apiKey);
      }
    }

    return {
      ...init,
      credentials: this.authMode === 'same-origin' ? 'include' : init.credentials,
      headers,
    };
  }
}
