import { Component, Input } from '@angular/core';

@Component({
  selector: 'sl-empty-state',
  standalone: false,
  templateUrl: './empty-state.component.html',
  styleUrl: './empty-state.component.scss',
})
export class EmptyStateComponent {
  @Input({ required: true }) message = '';
}
