import { Component } from '@angular/core';

interface DeviceRecord {
  id: string;
  name: string;
  summary: string;
  statusColor?: string;
  statusLabel?: string;
  statusCode: string;
  model: string;
  location: string;
  ipAddress: string;
  firmwareVersion: string;
  notes: string;
  systemId: string;
  lastSeen: string;
  calibrationDue: string;
  monitorEnabled: boolean;
}

interface MasterDetailChangeDetail {
  value: string | null;
}

const DEVICE_ROWS: readonly DeviceRecord[] = [
  {
    id: 'daq-001',
    name: 'NI-DAQ-001',
    summary: $localize`USB-6001 · Lab A`,
    statusColor: 'var(--ni-nimble-pass-color)',
    statusLabel: $localize`Connected`,
    statusCode: 'connected',
    model: 'USB-6001',
    location: $localize`Lab A`,
    ipAddress: '192.168.1.101',
    firmwareVersion: '20.0.0',
    notes: $localize`Primary data acquisition unit.`,
    systemId: 'd1',
    lastSeen: '2026-06-05T08:32:00Z',
    calibrationDue: '2026-12-01T00:00:00Z',
    monitorEnabled: true,
  },
  {
    id: 'scope-002',
    name: 'NI-SCOPE-002',
    summary: $localize`PXIe-5162 · Lab B`,
    statusColor: 'var(--ni-nimble-pass-color)',
    statusLabel: $localize`Connected`,
    statusCode: 'connected',
    model: 'PXIe-5162',
    location: $localize`Lab B`,
    ipAddress: '192.168.1.102',
    firmwareVersion: '19.8.4',
    notes: $localize`Scope used for waveform capture on validation racks.`,
    systemId: 'd2',
    lastSeen: '2026-06-05T08:28:00Z',
    calibrationDue: '2026-11-15T00:00:00Z',
    monitorEnabled: true,
  },
  {
    id: 'fgen-003',
    name: 'NI-FGEN-003',
    summary: $localize`PXI-5421 · Storage`,
    statusCode: 'offline',
    model: 'PXI-5421',
    location: $localize`Storage`,
    ipAddress: '192.168.1.121',
    firmwareVersion: '18.4.1',
    notes: $localize`Reserved for system bring-up and factory debug workflows.`,
    systemId: 'd3',
    lastSeen: '2026-06-05T06:14:00Z',
    calibrationDue: '2026-10-09T00:00:00Z',
    monitorEnabled: false,
  },
  {
    id: 'dmm-004',
    name: 'NI-DMM-004',
    summary: $localize`USB-4065 · Lab A`,
    statusColor: 'var(--ni-nimble-pass-color)',
    statusLabel: $localize`Connected`,
    statusCode: 'connected',
    model: 'USB-4065',
    location: $localize`Lab A`,
    ipAddress: '192.168.1.140',
    firmwareVersion: '21.1.0',
    notes: $localize`Bench meter for spot checks during hardware qualification.`,
    systemId: 'd4',
    lastSeen: '2026-06-05T08:20:00Z',
    calibrationDue: '2027-01-07T00:00:00Z',
    monitorEnabled: true,
  },
  {
    id: 'switch-005',
    name: 'NI-SWITCH-005',
    summary: $localize`PXI-2527 · Rack 3`,
    statusColor: 'var(--ni-nimble-warning-color)',
    statusLabel: $localize`Pending changes`,
    statusCode: 'pending-changes',
    model: 'PXI-2527',
    location: $localize`Rack 3`,
    ipAddress: '192.168.1.180',
    firmwareVersion: '17.9.2',
    notes: $localize`Investigate relay drift before the next production release.`,
    systemId: 'd5',
    lastSeen: '2026-06-04T23:19:00Z',
    calibrationDue: '2026-08-21T00:00:00Z',
    monitorEnabled: true,
  },
  {
    id: 'serial-006',
    name: 'NI-SERIAL-006',
    summary: $localize`USB-485/2 · Lab C`,
    statusColor: 'var(--ni-nimble-pass-color)',
    statusLabel: $localize`Connected`,
    statusCode: 'connected',
    model: 'USB-485/2',
    location: $localize`Lab C`,
    ipAddress: '192.168.1.161',
    firmwareVersion: '16.7.3',
    notes: $localize`Serial bridge for firmware provisioning and debug handshakes.`,
    systemId: 'd6',
    lastSeen: '2026-06-05T08:10:00Z',
    calibrationDue: '2026-09-30T00:00:00Z',
    monitorEnabled: false,
  },
];

@Component({
  selector: 'sl-master-detail-page',
  standalone: false,
  templateUrl: './master-detail-page.component.html',
  styleUrl: './master-detail-page.component.scss',
})
export class MasterDetailPageComponent {
  readonly emptyStateMessage = $localize`Adjust the filter or add a real device query to populate this pattern.`;
  readonly devices: DeviceRecord[] = DEVICE_ROWS.map((device: DeviceRecord) => ({ ...device }));

  filteredDevices: readonly DeviceRecord[] = [...this.devices];
  filterTerm = '';

  selectedDeviceId = this.devices[0]?.id ?? '';
  isEditing = false;

  get selectedDevice(): DeviceRecord | null {
    return this.devices.find((device: DeviceRecord) => device.id === this.selectedDeviceId) ?? null;
  }

  applyFilter(): void {
    const search = this.filterTerm.trim().toLowerCase();
    const filtered = this.devices.filter((device: DeviceRecord) => {
      return (
        search.length === 0 ||
        device.name.toLowerCase().includes(search) ||
        device.summary.toLowerCase().includes(search) ||
        device.location.toLowerCase().includes(search) ||
        device.model.toLowerCase().includes(search)
      );
    });

    this.filteredDevices = filtered;
    if (!filtered.some((device: DeviceRecord) => device.id === this.selectedDeviceId)) {
      this.selectedDeviceId = filtered[0]?.id ?? '';
      this.isEditing = false;
    }
  }

  onSelectionChange(event: Event): void {
    const detail = (event as CustomEvent<MasterDetailChangeDetail>).detail;
    if (!detail.value) {
      return;
    }

    this.selectedDeviceId = detail.value;
    this.isEditing = false;
  }

  onSelectedDeviceIdChange(): void {
    this.isEditing = false;
  }

  toggleEditMode(): void {
    if (!this.selectedDevice) {
      return;
    }

    this.isEditing = !this.isEditing;
  }

  saveChanges(): void {
    this.isEditing = false;
  }
}