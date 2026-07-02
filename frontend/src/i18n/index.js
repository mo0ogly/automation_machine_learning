// i18n bootstrap. Loads every locale JSON under ./locales/{lng}/{ns}.json and wires
// react-i18next. FR is the source of truth (the app was authored in French), so it is
// the fallback. Language is detected from localStorage (key ml.lang) then the browser,
// and persisted back to localStorage on change.
import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import LanguageDetector from 'i18next-browser-languagedetector';

// Vite: eagerly bundle all namespace files. Path shape: ./locales/<lng>/<ns>.json
const modules = import.meta.glob('./locales/*/*.json', { eager: true });

const resources = {};
for (const path in modules) {
  const match = path.match(/\.\/locales\/([^/]+)\/([^/]+)\.json$/);
  if (!match) continue;
  const [, lng, ns] = match;
  resources[lng] = resources[lng] || {};
  resources[lng][ns] = modules[path].default || modules[path];
}

// Under Vitest (MODE === 'test'), pin the language to fr instead of letting the
// detector fall through to jsdom's default navigator locale (en-US) — existing
// tests assert on the original French copy.
const isTest = import.meta.env.MODE === 'test';

i18n
  .use(LanguageDetector)
  .use(initReactI18next)
  .init({
    resources,
    lng: isTest ? 'fr' : undefined,
    fallbackLng: 'fr',
    supportedLngs: ['fr', 'en'],
    defaultNS: 'common',
    detection: {
      order: ['localStorage', 'navigator'],
      lookupLocalStorage: 'ml.lang',
      caches: isTest ? [] : ['localStorage'],
    },
    interpolation: {
      escapeValue: false, // React already escapes
    },
  });

export default i18n;
