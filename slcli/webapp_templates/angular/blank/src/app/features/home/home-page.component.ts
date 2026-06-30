import { Component, OnInit } from '@angular/core';

import { AppViewStateService } from '../../core/state/app-view-state.service';
import {
  HomePageModel,
  WebappHomeDataService,
} from '../../core/systemlink/webapp-home-data.service';
import { ViewState } from '../../shared/states/view-state.model';

@Component({
  selector: 'sl-home-page',
  standalone: false,
  templateUrl: './home-page.component.html',
  styleUrl: './home-page.component.scss',
})
export class HomePageComponent implements OnInit {
  state: ViewState<HomePageModel>;

  constructor(
    private readonly dataService: WebappHomeDataService,
    appViewState: AppViewStateService,
  ) {
    this.state = appViewState.create<HomePageModel>();
  }

  ngOnInit(): void {
    void this.reload();
  }

  async reload(): Promise<void> {
    this.state = { ...this.state, isLoading: true, error: null };
    try {
      const value = await this.dataService.load();
      this.state = { value, isLoading: false, error: null };
    } catch (error: unknown) {
      const message = error instanceof Error ? error.message : 'Failed to load sample data.';
      this.state = { ...this.state, isLoading: false, error: message };
    }
  }
}
