import { importProvidersFrom } from '@angular/core';
import { bootstrapApplication } from '@angular/platform-browser';

import { AppComponent } from './app/app.component';
import { AppModule } from './app/app.module';

bootstrapApplication(AppComponent, {
  providers: [importProvidersFrom(AppModule)],
}).catch((error: unknown) => {
  console.error(error);
});
