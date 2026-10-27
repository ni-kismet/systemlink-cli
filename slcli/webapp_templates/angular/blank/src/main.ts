import { registerLocaleData } from '@angular/common';
import { LOCALE_ID, importProvidersFrom } from '@angular/core';
import { bootstrapApplication } from '@angular/platform-browser';
import { loadTranslations } from '@angular/localize';

import localeDe from '@angular/common/locales/de';
import localeEs from '@angular/common/locales/es';
import localeFr from '@angular/common/locales/fr';
import localeJa from '@angular/common/locales/ja';
import localeKo from '@angular/common/locales/ko';
import localeZh from '@angular/common/locales/zh';

import messagesEn from './locale/messages.en.json';
import messagesDe from './locale/messages.de.json';
import messagesEs from './locale/messages.es.json';
import messagesFr from './locale/messages.fr.json';
import messagesJa from './locale/messages.ja.json';
import messagesKo from './locale/messages.ko.json';
import messagesZh from './locale/messages.zh.json';
import { getSystemLinkLanguage } from './app/core/systemlink/systemlink-locale';
import type { SystemLinkLanguage } from './app/core/systemlink/systemlink-locale';

const translations: Record<SystemLinkLanguage, Record<string, string>> = {
  de: messagesDe.translations,
  en: messagesEn.translations,
  es: messagesEs.translations,
  fr: messagesFr.translations,
  ja: messagesJa.translations,
  ko: messagesKo.translations,
  zh: messagesZh.translations,
};

const localeData = {
  de: localeDe,
  es: localeEs,
  fr: localeFr,
  ja: localeJa,
  ko: localeKo,
  zh: localeZh,
};

async function bootstrap(): Promise<void> {
  const language = getSystemLinkLanguage();
  const locale = language === 'en' ? 'en-US' : language;

  loadTranslations({ ...translations.en, ...translations[language] });
  document.documentElement.lang = language;
  if (language !== 'en') {
    registerLocaleData(localeData[language], locale);
  }

  const { AppComponent } = await import('./app/app.component');
  const { AppModule } = await import('./app/app.module');
  await bootstrapApplication(AppComponent, {
    providers: [importProvidersFrom(AppModule), { provide: LOCALE_ID, useValue: locale }],
  });
}

void bootstrap().catch((error: unknown) => {
  console.error(error);
});
