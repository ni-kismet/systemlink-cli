import { NgModule } from '@angular/core';
import { RouterModule, Routes } from '@angular/router';

import { AssetsPageComponent } from './features/assets/assets-page.component';
import { DatasetsPageComponent } from './features/datasets/datasets-page.component';
import { HomePageComponent } from './features/home/home-page.component';
import { MasterDetailPageComponent } from './features/master-detail/master-detail-page.component';
import { OperationsPageComponent } from './features/operations/operations-page.component';
import { SettingsPageComponent } from './features/settings/settings-page.component';

const routes: Routes = [
  {
    path: '',
    component: HomePageComponent,
  },
  {
    path: 'datasets',
    component: DatasetsPageComponent,
  },
  {
    path: 'assets',
    component: AssetsPageComponent,
  },
  {
    path: 'master-detail',
    component: MasterDetailPageComponent,
  },
  {
    path: 'operations',
    component: OperationsPageComponent,
  },
  {
    path: 'settings',
    component: SettingsPageComponent,
  },
];

@NgModule({
  imports: [RouterModule.forRoot(routes, { useHash: true })],
  exports: [RouterModule],
})
export class AppRoutingModule {}
