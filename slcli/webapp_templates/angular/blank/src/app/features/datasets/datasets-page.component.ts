import { AfterViewInit, Component, OnInit, ViewChild } from '@angular/core';

import { NimbleTableDirective, TableFieldValue, TableRecord } from '@ni/nimble-angular/table';

interface DatasetRow extends TableRecord {
  id: string;
  suite: string;
  status: string;
  branch: string;
  owner: string;
  duration: string;
  started: string;
  [key: string]: TableFieldValue;
}

const DATASET_ROWS: readonly DatasetRow[] = [
  {
    id: 'run-001',
    suite: 'Production smoke',
    status: 'Passed',
    branch: 'main',
    owner: 'A. Rivera',
    duration: '12m 04s',
    started: '2026-06-17 09:15',
  },
  {
    id: 'run-002',
    suite: 'Calibration retest',
    status: 'Warning',
    branch: 'release/3.4',
    owner: 'J. Lee',
    duration: '18m 27s',
    started: '2026-06-17 08:40',
  },
  {
    id: 'run-003',
    suite: 'End-of-line batch',
    status: 'Failed',
    branch: 'main',
    owner: 'M. Chen',
    duration: '26m 55s',
    started: '2026-06-17 07:58',
  },
  {
    id: 'run-004',
    suite: 'Firmware validation',
    status: 'Passed',
    branch: 'feature/fw-sync',
    owner: 'R. Patel',
    duration: '34m 11s',
    started: '2026-06-16 16:22',
  },
  {
    id: 'run-005',
    suite: 'Functional sweep',
    status: 'Passed',
    branch: 'main',
    owner: 'S. Kim',
    duration: '08m 43s',
    started: '2026-06-16 15:05',
  },
  {
    id: 'run-006',
    suite: 'Thermal soak',
    status: 'Warning',
    branch: 'main',
    owner: 'A. Rivera',
    duration: '44m 02s',
    started: '2026-06-16 13:49',
  },
];

@Component({
  selector: 'sl-datasets-page',
  standalone: false,
  templateUrl: './datasets-page.component.html',
  styleUrl: './datasets-page.component.scss',
})
export class DatasetsPageComponent implements AfterViewInit, OnInit {
  filteredRows: readonly DatasetRow[] = [...DATASET_ROWS];

  searchTerm = '';
  statusFilter = '';
  filteredCount = DATASET_ROWS.length;

  @ViewChild('datasetTable', { read: NimbleTableDirective })
  private datasetTable?: NimbleTableDirective<DatasetRow>;

  ngOnInit(): void {
    this.applyFilters();
  }

  ngAfterViewInit(): void {
    this.scheduleRender();
  }

  applyFilters(): void {
    const search = this.searchTerm.trim().toLowerCase();
    const filtered = DATASET_ROWS.filter((row: DatasetRow) => {
      const matchesSearch =
        search.length === 0 ||
        row.suite.toLowerCase().includes(search) ||
        row.owner.toLowerCase().includes(search) ||
        row.branch.toLowerCase().includes(search);
      const matchesStatus = this.statusFilter.length === 0 || row.status === this.statusFilter;
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