import {
  AfterViewInit,
  Component,
  ElementRef,
  Inject,
  LOCALE_ID,
  ViewChild,
} from '@angular/core';

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
  statusCode: string;
  location: string;
  owner: string;
  calibrated: string;
  calibratedAt: number;
  [key: string]: TableFieldValue;
}

interface AssetSample extends TableRecord {
  id: string;
  name: string;
  type: string;
  status: string;
  statusCode: string;
  location: string;
  owner: string;
  calibratedAt: string;
  [key: string]: TableFieldValue;
}

type DrawerElement = HTMLElement & {
  show: () => void;
  close: () => void;
};

const ASSET_SAMPLES: readonly AssetSample[] = [
  {
    id: 'asset-001',
    name: 'PXIe-5162-01',
    type: $localize`Oscilloscope`,
    status: $localize`Calibrated`,
    statusCode: 'calibrated',
    location: $localize`Lab A`,
    owner: 'J. Lee',
    calibratedAt: '2026-05-18T00:00:00Z',
  },
  {
    id: 'asset-002',
    name: 'USB-4065-03',
    type: 'DMM',
    status: $localize`Due soon`,
    statusCode: 'due-soon',
    location: $localize`Lab B`,
    owner: 'S. Kim',
    calibratedAt: '2025-07-02T00:00:00Z',
  },
  {
    id: 'asset-003',
    name: 'PXI-5421-02',
    type: $localize`Function generator`,
    status: $localize`Out of service`,
    statusCode: 'out-of-service',
    location: $localize`Repair queue`,
    owner: 'R. Patel',
    calibratedAt: '2025-03-11T00:00:00Z',
  },
  {
    id: 'asset-004',
    name: 'cDAQ-9178-11',
    type: $localize`CompactDAQ`,
    status: $localize`Calibrated`,
    statusCode: 'calibrated',
    location: $localize`Rack 3`,
    owner: 'M. Chen',
    calibratedAt: '2026-04-24T00:00:00Z',
  },
];

@Component({
  selector: 'sl-assets-page',
  standalone: false,
  templateUrl: './assets-page.component.html',
  styleUrl: './assets-page.component.scss',
})
export class AssetsPageComponent implements AfterViewInit {
  readonly assets: readonly AssetRow[];
  selectedAsset: AssetRow | null = null;

  @ViewChild('assetTable', { read: NimbleTableDirective })
  private assetTable?: NimbleTableDirective<AssetRow>;
  @ViewChild('detailDrawer') private detailDrawer?: ElementRef<DrawerElement>;

  constructor(@Inject(LOCALE_ID) locale: string) {
    const dateFormat = new Intl.DateTimeFormat(locale, {
      dateStyle: 'medium',
      timeZone: 'UTC',
    });
    this.assets = ASSET_SAMPLES.map(({ calibratedAt, ...asset }: AssetSample) => {
      const calibratedDate = new Date(calibratedAt);
      return {
        ...asset,
        calibrated: dateFormat.format(calibratedDate),
        calibratedAt: calibratedDate.getTime(),
      };
    });
    this.selectedAsset = this.assets[0] ?? null;
  }

  get drawerTitle(): string {
    return this.selectedAsset?.name ?? $localize`Asset detail`;
  }

  ngAfterViewInit(): void {
    window.requestAnimationFrame(() => {
      void this.assetTable?.setData(this.assets);
    });
  }

  onSelectionChange(event: Event): void {
    const detail = (event as CustomEvent<TableRowSelectionEventDetail>).detail;
    const selectedId = detail.selectedRecordIds[0];
    const asset = this.assets.find((row: AssetRow) => row.id === selectedId) ?? null;
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