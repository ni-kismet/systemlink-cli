import { Component } from '@angular/core';

import '@ni/ok-components/dist/esm/fv/master-detail-list';

interface DeviceRecord {
  id: string;
  name: string;
  summary: string;
  statusColor?: string;
  statusLabel?: string;
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
    summary: 'USB-6001 · Lab A',
    statusColor: '#169c44',
    statusLabel: 'Connected',
    model: 'USB-6001',
    location: 'Lab A',
    ipAddress: '192.168.1.101',
    firmwareVersion: '20.0.0',
    notes: 'Primary data acquisition unit.',
    systemId: 'd1',
    lastSeen: '2026-06-05 08:32 UTC',
    calibrationDue: '2026-12-01',
    monitorEnabled: true,
  },
  {
    id: 'scope-002',
    name: 'NI-SCOPE-002',
    summary: 'PXIe-5162 · Lab B',
    statusColor: '#169c44',
    statusLabel: 'Connected',
    model: 'PXIe-5162',
    location: 'Lab B',
    ipAddress: '192.168.1.102',
    firmwareVersion: '19.8.4',
    notes: 'Scope used for waveform capture on validation racks.',
    systemId: 'd2',
    lastSeen: '2026-06-05 08:28 UTC',
    calibrationDue: '2026-11-15',
    monitorEnabled: true,
  },
  {
    id: 'fgen-003',
    name: 'NI-FGEN-003',
    summary: 'PXI-5421 · Storage',
    model: 'PXI-5421',
    location: 'Storage',
    ipAddress: '192.168.1.121',
    firmwareVersion: '18.4.1',
    notes: 'Reserved for system bring-up and factory debug workflows.',
    systemId: 'd3',
    lastSeen: '2026-06-05 06:14 UTC',
    calibrationDue: '2026-10-09',
    monitorEnabled: false,
  },
  {
    id: 'dmm-004',
    name: 'NI-DMM-004',
    summary: 'USB-4065 · Lab A',
    statusColor: '#169c44',
    statusLabel: 'Connected',
    model: 'USB-4065',
    location: 'Lab A',
    ipAddress: '192.168.1.140',
    firmwareVersion: '21.1.0',
    notes: 'Bench meter for spot checks during hardware qualification.',
    systemId: 'd4',
    lastSeen: '2026-06-05 08:20 UTC',
    calibrationDue: '2027-01-07',
    monitorEnabled: true,
  },
  {
    id: 'switch-005',
    name: 'NI-SWITCH-005',
    summary: 'PXI-2527 · Rack 3',
    statusColor: '#ff5f0f',
    statusLabel: 'Pending changes',
    model: 'PXI-2527',
    location: 'Rack 3',
    ipAddress: '192.168.1.180',
    firmwareVersion: '17.9.2',
    notes: 'Investigate relay drift before the next production release.',
    systemId: 'd5',
    lastSeen: '2026-06-04 23:19 UTC',
    calibrationDue: '2026-08-21',
    monitorEnabled: true,
  },
  {
    id: 'serial-006',
    name: 'NI-SERIAL-006',
    summary: 'USB-485/2 · Lab C',
    statusColor: '#169c44',
    statusLabel: 'Connected',
    model: 'USB-485/2',
    location: 'Lab C',
    ipAddress: '192.168.1.161',
    firmwareVersion: '16.7.3',
    notes: 'Serial bridge for firmware provisioning and debug handshakes.',
    systemId: 'd6',
    lastSeen: '2026-06-05 08:10 UTC',
    calibrationDue: '2026-09-30',
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
  readonly devices: DeviceRecord[] = DEVICE_ROWS.map((device: DeviceRecord) => ({ ...device }));

  selectedDeviceId = this.devices[0]?.id ?? '';
  isEditing = false;

  get selectedDevice(): DeviceRecord | null {
    return this.devices.find((device: DeviceRecord) => device.id === this.selectedDeviceId) ?? null;
  }

  onSelectionChange(event: Event): void {
    const detail = (event as CustomEvent<MasterDetailChangeDetail>).detail;
    if (!detail.value) {
      return;
    }

    this.selectedDeviceId = detail.value;
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