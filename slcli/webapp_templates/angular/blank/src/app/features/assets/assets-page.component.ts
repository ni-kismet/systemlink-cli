import { AfterViewInit, Component, ElementRef, ViewChild } from '@angular/core';

import {
  NimbleTableDirective,
  TableFieldValue,
  TableRecord,
  TableRowSelectionEventDetail,
} from '@ni/nimble-angular/table';

interface AssetRow extends TableRecord {
  id: string;
  name: string;
  type: string;
  status: string;
  location: string;
  owner: string;
  calibrated: string;
  [key: string]: TableFieldValue;
}

type DrawerElement = HTMLElement & {
  show: () => void;
  close: () => void;
};

const ASSET_ROWS: readonly AssetRow[] = [
  {
    id: 'asset-001',
    name: 'PXIe-5162-01',
    type: 'Oscilloscope',
    status: 'Calibrated',
    location: 'Lab A',
    owner: 'J. Lee',
    calibrated: '2026-05-18',
  },
  {
    id: 'asset-002',
    name: 'USB-4065-03',
    type: 'DMM',
    status: 'Due soon',
    location: 'Lab B',
    owner: 'S. Kim',
    calibrated: '2025-07-02',
  },
  {
    id: 'asset-003',
    name: 'PXI-5421-02',
    type: 'Function generator',
    status: 'Out of service',
    location: 'Repair queue',
    owner: 'R. Patel',
    calibrated: '2025-03-11',
  },
  {
    id: 'asset-004',
    name: 'cDAQ-9178-11',
    type: 'CompactDAQ',
    status: 'Calibrated',
    location: 'Rack 3',
    owner: 'M. Chen',
    calibrated: '2026-04-24',
  },
];

@Component({
  selector: 'sl-assets-page',
  standalone: false,
  templateUrl: './assets-page.component.html',
  styleUrl: './assets-page.component.scss',
})
export class AssetsPageComponent implements AfterViewInit {
  selectedAsset: AssetRow | null = ASSET_ROWS[0] ?? null;

  @ViewChild('assetTable', { read: NimbleTableDirective })
  private assetTable?: NimbleTableDirective<AssetRow>;
  @ViewChild('detailDrawer') private detailDrawer?: ElementRef<DrawerElement>;

  ngAfterViewInit(): void {
    window.requestAnimationFrame(() => {
      void this.assetTable?.setData(ASSET_ROWS);
    });
  }

  onSelectionChange(event: Event): void {
    const detail = (event as CustomEvent<TableRowSelectionEventDetail>).detail;
    const selectedId = detail.selectedRecordIds[0];
    const asset = ASSET_ROWS.find((row: AssetRow) => row.id === selectedId) ?? null;
    if (!asset) {
      return;
    }

    this.selectedAsset = asset;
    this.detailDrawer?.nativeElement.show();
  }

  closeDrawer(): void {
    this.detailDrawer?.nativeElement.close();
  }
}