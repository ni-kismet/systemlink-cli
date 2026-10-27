import { AfterViewInit, Component, Inject, LOCALE_ID, OnInit, ViewChild } from '@angular/core';

import { NimbleTableDirective, TableFieldValue, TableRecord } from '@ni/nimble-angular/table';

interface DatasetRow extends TableRecord {
  id: string;
  suite: string;
  status: string;
  statusCode: string;
  branch: string;
  owner: string;
  duration: string;
  started: string;
  [key: string]: TableFieldValue;
}

interface DatasetSample {
  id: string;
  suite: string;
  statusCode: 'passed' | 'warning' | 'failed';
  branch: string;
  owner: string;
  durationSeconds: number;
  startedAt: string;
}

const DATASET_SAMPLES: readonly DatasetSample[] = [
  {
    id: 'run-001',
    suite: $localize`Production smoke`,
    statusCode: 'passed',
    branch: 'main',
    owner: 'A. Rivera',
    durationSeconds: 724,
    startedAt: '2026-06-17T09:15:00Z',
  },
  {
    id: 'run-002',
    suite: $localize`Calibration retest`,
    statusCode: 'warning',
    branch: 'release/3.4',
    owner: 'J. Lee',
    durationSeconds: 1107,
    startedAt: '2026-06-17T08:40:00Z',
  },
  {
    id: 'run-003',
    suite: $localize`End-of-line batch`,
    statusCode: 'failed',
    branch: 'main',
    owner: 'M. Chen',
    durationSeconds: 1615,
    startedAt: '2026-06-17T07:58:00Z',
  },
  {
    id: 'run-004',
    suite: $localize`Firmware validation`,
    statusCode: 'passed',
    branch: 'feature/fw-sync',
    owner: 'R. Patel',
    durationSeconds: 2051,
    startedAt: '2026-06-16T16:22:00Z',
  },
  {
    id: 'run-005',
    suite: $localize`Functional sweep`,
    statusCode: 'passed',
    branch: 'main',
    owner: 'S. Kim',
    durationSeconds: 523,
    startedAt: '2026-06-16T15:05:00Z',
  },
  {
    id: 'run-006',
    suite: $localize`Thermal soak`,
    branch: 'main',
    owner: 'A. Rivera',
    statusCode: 'warning',
    durationSeconds: 2642,
    startedAt: '2026-06-16T13:49:00Z',
  },
];

@Component({
  selector: 'sl-datasets-page',
  standalone: false,
  templateUrl: './datasets-page.component.html',
  styleUrl: './datasets-page.component.scss',
})
export class DatasetsPageComponent implements AfterViewInit, OnInit {
  private readonly allRows: readonly DatasetRow[];
  filteredRows: readonly DatasetRow[] = [];

  searchTerm = '';
  statusFilter = '';
  filteredCount = 0;

  @ViewChild('datasetTable', { read: NimbleTableDirective })
  private datasetTable?: NimbleTableDirective<DatasetRow>;

  constructor(@Inject(LOCALE_ID) locale: string) {
    const dateFormat = new Intl.DateTimeFormat(locale, {
      dateStyle: 'medium',
      timeStyle: 'short',
    });
    const durationFormat = new Intl.NumberFormat(locale, {
      style: 'unit',
      unit: 'minute',
      unitDisplay: 'short',
      maximumFractionDigits: 1,
    });
    const statusLabels: Record<DatasetSample['statusCode'], string> = {
      passed: $localize`Passed`,
      warning: $localize`Warning`,
      failed: $localize`Failed`,
    };

    this.allRows = DATASET_SAMPLES.map((sample: DatasetSample) => ({
      id: sample.id,
      suite: sample.suite,
      status: statusLabels[sample.statusCode],
      statusCode: sample.statusCode,
      branch: sample.branch,
      owner: sample.owner,
      duration: durationFormat.format(sample.durationSeconds / 60),
      started: dateFormat.format(new Date(sample.startedAt)),
    }));
    this.filteredRows = [...this.allRows];
    this.filteredCount = this.allRows.length;
  }

  ngOnInit(): void {
    this.applyFilters();
  }

  ngAfterViewInit(): void {
    this.scheduleRender();
  }

  applyFilters(): void {
    const search = this.searchTerm.trim().toLowerCase();
    const filtered = this.allRows.filter((row: DatasetRow) => {
      const matchesSearch =
        search.length === 0 ||
        row.suite.toLowerCase().includes(search) ||
        row.owner.toLowerCase().includes(search) ||
        row.branch.toLowerCase().includes(search);
      const matchesStatus =
        this.statusFilter.length === 0 || row.statusCode === this.statusFilter;
      return matchesSearch && matchesStatus;
    });

    this.filteredRows = filtered;
    this.filteredCount = filtered.length;
    this.scheduleRender();
  }

  clearFilters(): void {
    this.searchTerm = '';
    this.statusFilter = '';
    this.applyFilters();
  }

  private async renderRows(): Promise<void> {
    if (!this.datasetTable) {
      return;
    }

    await this.datasetTable.setData(this.filteredRows);
  }

  private scheduleRender(): void {
    window.requestAnimationFrame(() => {
      void this.renderRows();
    });
  }
}