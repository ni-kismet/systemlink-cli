const SYSTEMLINK_LANGUAGES = ['fr', 'de', 'ja', 'zh', 'en', 'ko', 'es'] as const;
const SYSTEMLINK_LANGUAGE_STORAGE_KEY = 'language';
const SYSTEMLINK_LEGACY_LANGUAGE_STORAGE_KEY = 'skyline-api-languages';

export type SystemLinkLanguage = (typeof SYSTEMLINK_LANGUAGES)[number];

function toLanguage(locale: string | null | undefined): string {
  return (locale ?? '').split(/[-_]/)[0].trim().toLowerCase();
}

function isSystemLinkLanguage(language: string): language is SystemLinkLanguage {
  return SYSTEMLINK_LANGUAGES.some((supportedLanguage: string) => supportedLanguage === language);
}

function readLocalStorage(key: string): string | null {
  try {
    return globalThis.localStorage?.getItem(key) ?? null;
  } catch {
    return null;
  }
}

export function getSystemLinkLanguage(): SystemLinkLanguage {
  const storedCandidates = [
    readLocalStorage(SYSTEMLINK_LANGUAGE_STORAGE_KEY),
    readLocalStorage(SYSTEMLINK_LEGACY_LANGUAGE_STORAGE_KEY)?.split(',')[0],
  ];
  for (const candidate of storedCandidates) {
    const language = toLanguage(candidate);
    if (isSystemLinkLanguage(language)) {
      return language;
    }
  }

  const browserCandidates = [
    ...(globalThis.navigator?.languages ?? []),
    globalThis.navigator?.language,
    Intl.DateTimeFormat().resolvedOptions().locale,
  ];
  for (const candidate of browserCandidates) {
    const language = toLanguage(candidate);
    if (isSystemLinkLanguage(language)) {
      return language;
    }
  }

  return 'en';
}
