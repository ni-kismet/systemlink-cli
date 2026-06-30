import { Component } from '@angular/core';

import { SystemLinkContextService } from '../../core/systemlink/systemlink-context.service';

type SettingsSectionId =
  | 'profile'
  | 'security'
  | 'notifications'
  | 'integrations'
  | 'advanced';

interface SettingsSectionGroup {
  title: string;
  items: { id: SettingsSectionId; label: string }[];
}

@Component({
  selector: 'sl-settings-page',
  standalone: false,
  templateUrl: './settings-page.component.html',
  styleUrl: './settings-page.component.scss',
})
export class SettingsPageComponent {
  readonly sectionGroups: readonly SettingsSectionGroup[] = [
    {
      title: 'Account',
      items: [
        { id: 'profile', label: 'Profile' },
        { id: 'security', label: 'Security' },
      ],
    },
    {
      title: 'Workspace',
      items: [
        { id: 'notifications', label: 'Notifications' },
        { id: 'integrations', label: 'Integrations' },
        { id: 'advanced', label: 'Advanced' },
      ],
    },
  ];

  activeSection: SettingsSectionId = 'notifications';
  ownerName = 'Jordan Lee';
  ownerEmail = 'jordan.lee@ni.com';
  resultRetention = '30';
  defaultWorkspace = 'primary';
  defaultView = 'queue';
  notificationMode = 'daily';
  publishAudience = 'workspace';
  notifyOnFailure = true;
  notifyOnPass = false;
  slackEnabled = true;
  requireApproval = true;
  webhookEnabled = false;
  integrationEndpoint = 'https://hooks.slack.com/services/example';
  automationWindow = 'guarded';
  saveMessageOpen = false;

  constructor(public readonly context: SystemLinkContextService) {}

  get activeSectionTitle(): string {
    switch (this.activeSection) {
      case 'profile':
        return 'Profile';
      case 'security':
        return 'Security';
      case 'notifications':
        return 'Notifications';
      case 'integrations':
        return 'Integrations';
      case 'advanced':
        return 'Advanced';
      default:
        return 'Settings';
    }
  }

  selectSection(sectionId: SettingsSectionId): void {
    this.activeSection = sectionId;
  }

  save(): void {
    this.saveMessageOpen = true;
    window.setTimeout(() => {
      this.saveMessageOpen = false;
    }, 3000);
  }
}