import { Component, Input } from '@angular/core';

@Component({
  selector: 'sl-error-banner',
  standalone: false,
  templateUrl: './error-banner.component.html',
  styleUrl: './error-banner.component.scss',
})
export class ErrorBannerComponent {
  @Input({ required: true }) message = '';
}
