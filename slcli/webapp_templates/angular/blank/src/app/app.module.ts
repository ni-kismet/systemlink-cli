import { APP_BASE_HREF, CommonModule } from '@angular/common';
import { CUSTOM_ELEMENTS_SCHEMA, NgModule } from '@angular/core';
import { FormsModule } from '@angular/forms';

import {
  NimbleAnchorTabModule,
  NimbleAnchorTabsModule,
  NimbleBannerModule,
  NimbleButtonModule,
  NimbleCheckboxModule,
  NimbleDialogModule,
  NimbleDrawerModule,
  NimbleListOptionModule,
  NimbleSelectModule,
  NimbleSpinnerModule,
  NimbleSwitchModule,
  NimbleTextAreaModule,
  NimbleTextFieldModule,
  NimbleThemeProviderModule,
} from '@ni/nimble-angular';
import { NimbleChipModule } from '@ni/nimble-angular/chip';
import { NimbleLabelProviderCoreModule } from '@ni/nimble-angular/label-provider/core';
import { NimbleTableModule } from '@ni/nimble-angular/table';
import { NimbleTableColumnTextModule } from '@ni/nimble-angular/table-column/text';

import { AppRoutingModule } from './app-routing.module';
import { AssetsPageComponent } from './features/assets/assets-page.component';
import { DatasetsPageComponent } from './features/datasets/datasets-page.component';
import { HomePageComponent } from './features/home/home-page.component';
import { MasterDetailPageComponent } from './features/master-detail/master-detail-page.component';
import { OperationsPageComponent } from './features/operations/operations-page.component';
import { SettingsPageComponent } from './features/settings/settings-page.component';
import { EmptyStateComponent } from './shared/components/empty-state.component';
import { ErrorBannerComponent } from './shared/components/error-banner.component';
import { LoadingStateComponent } from './shared/components/loading-state.component';

@NgModule({
  declarations: [
    HomePageComponent,
    DatasetsPageComponent,
    AssetsPageComponent,
    MasterDetailPageComponent,
    OperationsPageComponent,
    SettingsPageComponent,
    LoadingStateComponent,
    ErrorBannerComponent,
    EmptyStateComponent,
  ],
  imports: [
    CommonModule,
    FormsModule,
    AppRoutingModule,
    NimbleThemeProviderModule,
    NimbleLabelProviderCoreModule,
    NimbleAnchorTabsModule,
    NimbleAnchorTabModule,
    NimbleBannerModule,
    NimbleButtonModule,
    NimbleCheckboxModule,
    NimbleChipModule,
    NimbleDialogModule,
    NimbleDrawerModule,
    NimbleListOptionModule,
    NimbleSelectModule,
    NimbleSpinnerModule,
    NimbleSwitchModule,
    NimbleTextAreaModule,
    NimbleTextFieldModule,
    NimbleTableModule,
    NimbleTableColumnTextModule,
  ],
  providers: [{ provide: APP_BASE_HREF, useValue: '/' }],
  schemas: [CUSTOM_ELEMENTS_SCHEMA],
})
export class AppModule {}
