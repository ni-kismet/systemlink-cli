import {
  Component,
  ElementRef,
  Inject,
  LOCALE_ID,
  OnDestroy,
  ViewChild,
} from '@angular/core';

import { TableFieldValue, TableRecord, TableRowSelectionEventDetail } from '@ni/nimble-angular/table';
import { BehaviorSubject } from 'rxjs';

interface OperationRow extends TableRecord {
  id: string;
  workItem: string;
  owner: string;
  status: string;
  statusCode: string;
  priority: string;
  due: string;
  [key: string]: TableFieldValue;
}

interface OperationSample {
  id: string;
  workItem: string;
  owner: string;
  status: string;
  statusCode: string;
  priority: string;
  dueAt: string;
}

type DialogElement = HTMLElement & {
  close: () => void;
  show: () => void;
};

const OPERATION_SAMPLES: readonly OperationSample[] = [
  {
    id: 'op-001',
    workItem: $localize`Run release candidate smoke suite`,
    owner: 'J. Lee',
    status: $localize`Ready`,
    statusCode: 'ready',
    priority: $localize`High`,
    dueAt: '2026-10-16T14:00:00Z',
  },
  {
    id: 'op-002',
    workItem: $localize`Approve asset reassignment`,
    owner: 'M. Chen',
    status: $localize`Needs review`,
    statusCode: 'needs-review',
    priority: $localize`Medium`,
    dueAt: '2026-10-16T16:30:00Z',
  },
  {
    id: 'op-003',
    workItem: $localize`Publish nightly results to workspace`,
    owner: 'A. Rivera',
    status: $localize`Queued`,
    statusCode: 'queued',
    priority: $localize`Low`,
    dueAt: '2026-10-17T07:00:00Z',
  },
];

@Component({
  selector: 'sl-operations-page',
  standalone: false,
  templateUrl: './operations-page.component.html',
  styleUrl: './operations-page.component.scss',
})
export class OperationsPageComponent implements OnDestroy {
  private static readonly minQueueWidth = 320;
  private static readonly minDetailWidth = 320;
  private static readonly splitterWidth = 12;
  private static readonly resizeStep = 24;

  readonly rows$: BehaviorSubject<OperationRow[]>;

  selectedOperation: OperationRow;
  lastActionMessage: string | null = null;
  queuePaneWidth = 432;
  isResizing = false;
  isDetailCollapsed = false;

  private dragStartX = 0;
  private dragStartWidth = this.queuePaneWidth;
  private lastExpandedQueueWidth = this.queuePaneWidth;
  private readonly pointerMoveHandler = (event: PointerEvent): void => {
    this.resizeFromPointer(event);
  };
  private readonly pointerUpHandler = (): void => {
    this.stopResize();
  };

  @ViewChild('launchDialog') private launchDialog?: ElementRef<DialogElement>;
  @ViewChild('workspace') private workspace?: ElementRef<HTMLElement>;

  constructor(@Inject(LOCALE_ID) locale: string) {
    const dueFormat = new Intl.DateTimeFormat(locale, {
      dateStyle: 'medium',
      timeStyle: 'short',
    });
    const rows = OPERATION_SAMPLES.map(({ dueAt, ...sample }: OperationSample) => ({
      ...sample,
      due: dueFormat.format(new Date(dueAt)),
    }));
    this.rows$ = new BehaviorSubject<OperationRow[]>(rows);
    this.selectedOperation = rows[0];
  }

  get queuePaneWidthStyle(): string {
    return `${this.queuePaneWidth}px`;
  }

  get detailPaneToggleLabel(): string {
    return this.isDetailCollapsed ? $localize`Show details` : $localize`Hide details`;
  }

  onSelectionChange(event: Event): void {
    const detail = (event as CustomEvent<TableRowSelectionEventDetail>).detail;
    const selectedId = detail.selectedRecordIds[0];
    const selected = this.rows$.value.find((row: OperationRow) => row.id === selectedId);
    if (!selected) {
      return;
    }

    this.selectedOperation = selected;
  }

  openDialog(): void {
    this.launchDialog?.nativeElement.show();
  }

  closeDialog(): void {
    this.launchDialog?.nativeElement.close();
  }

  confirmRun(): void {
    this.lastActionMessage = $localize`${this.selectedOperation.workItem} is queued to run from the hosted workspace.`;
    this.closeDialog();
  }

  toggleDetailPane(event?: Event): void {
    event?.stopPropagation();

    if (this.isDetailCollapsed) {
      this.isDetailCollapsed = false;
      this.queuePaneWidth = this.getClampedQueueWidth(this.lastExpandedQueueWidth);
      return;
    }

    this.lastExpandedQueueWidth = this.queuePaneWidth;
    this.isDetailCollapsed = true;
    this.stopResize();
  }

  startResize(event: PointerEvent): void {
    if (!this.workspace || this.isDetailCollapsed) {
      return;
    }

    event.preventDefault();
    this.isResizing = true;
    this.dragStartX = event.clientX;
    this.dragStartWidth = this.queuePaneWidth;
    document.addEventListener('pointermove', this.pointerMoveHandler);
    document.addEventListener('pointerup', this.pointerUpHandler);
  }

  onSplitterKeydown(event: KeyboardEvent): void {
    if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      this.toggleDetailPane();
      return;
    }

    if (this.isDetailCollapsed) {
      return;
    }

    if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') {
      return;
    }

    event.preventDefault();
    const direction = event.key === 'ArrowLeft' ? -1 : 1;
    this.queuePaneWidth = this.getClampedQueueWidth(
      this.queuePaneWidth + direction * OperationsPageComponent.resizeStep,
    );
  }

  ngOnDestroy(): void {
    this.stopResize();
  }

  private resizeFromPointer(event: PointerEvent): void {
    if (!this.isResizing) {
      return;
    }

    this.queuePaneWidth = this.getClampedQueueWidth(
      this.dragStartWidth + event.clientX - this.dragStartX,
    );
  }

  private stopResize(): void {
    if (!this.isResizing) {
      return;
    }

    this.isResizing = false;
    document.removeEventListener('pointermove', this.pointerMoveHandler);
    document.removeEventListener('pointerup', this.pointerUpHandler);
  }

  private getClampedQueueWidth(width: number): number {
    const workspaceWidth = this.workspace?.nativeElement.getBoundingClientRect().width;
    if (!workspaceWidth) {
      return Math.max(width, OperationsPageComponent.minQueueWidth);
    }

    const maxQueueWidth = workspaceWidth
      - OperationsPageComponent.minDetailWidth
      - OperationsPageComponent.splitterWidth;

    return Math.min(
      Math.max(width, OperationsPageComponent.minQueueWidth),
      Math.max(maxQueueWidth, OperationsPageComponent.minQueueWidth),
    );
  }
}