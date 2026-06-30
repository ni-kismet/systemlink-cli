import { Injectable } from '@angular/core';

import { createEmptyViewState, ViewState } from '../../shared/states/view-state.model';

@Injectable({ providedIn: 'root' })
export class AppViewStateService {
  create<T>(): ViewState<T> {
    return createEmptyViewState<T>();
  }
}
