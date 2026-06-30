import { Component, ElementRef, OnDestroy, ViewChild } from '@angular/core';

import { TableFieldValue, TableRecord, TableRowSelectionEventDetail } from '@ni/nimble-angular/table';
import { BehaviorSubject } from 'rxjs';

interface OperationRow extends TableRecord {
  id: string;
  workItem: string;
  owner: string;
  status: string;
  priority: string;
  due: string;
  [key: string]: TableFieldValue;
}

type DialogElement = HTMLElement & {
  close: () => void;
  show: () => void;
};

const OPERATION_ROWS: readonly OperationRow[] = [
  {
    id: 'op-001',
    workItem: 'Run release candidate smoke suite',
    owner: 'J. Lee',
    status: 'Ready',
    priority: 'High',
    due: 'Today 14:00',
  },
  {
    id: 'op-002',
    workItem: 'Approve asset reassignment',
    owner: 'M. Chen',
    status: 'Needs review',
    priority: 'Medium',
    due: 'Today 16:30',
  },
  {
    id: 'op-003',
    workItem: 'Publish nightly results to workspace',
    owner: 'A. Rivera',
    status: 'Queued',
    priority: 'Low',
    due: 'Tomorrow 07:00',
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

  readonly rows$ = new BehaviorSubject<OperationRow[]>([...OPERATION_ROWS]);

  selectedOperation: OperationRow = OPERATION_ROWS[0];
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

  get queuePaneWidthStyle(): string {
    return `${this.queuePaneWidth}px`;
  }

  onSelectionChange(event: Event): void {
    const detail = (event as CustomEvent<TableRowSelectionEventDetail>).detail;
    const selectedId = detail.selectedRecordIds[0];
    const selected = OPERATION_ROWS.find((row: OperationRow) => row.id === selectedId);
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
    this.lastActionMessage = `${this.selectedOperation.workItem} is queued to run from the hosted workspace.`;
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