import { useTranslation } from 'react-i18next'

// FR/EN toggle. The active language is persisted by i18next-browser-languagedetector
// (localStorage key ml.lang), so the choice survives reloads.
export default function LanguageSwitcher() {
  const { t, i18n } = useTranslation('common')
  const current = i18n.resolvedLanguage || i18n.language || 'fr'
  const langs = ['fr', 'en']
  return (
    <div className="lang-switch" role="group" aria-label={t('language')}>
      {langs.map((lng) => (
        <button
          key={lng}
          type="button"
          className={current === lng ? 'active' : ''}
          aria-pressed={current === lng}
          onClick={() => i18n.changeLanguage(lng)}
        >
          {lng.toUpperCase()}
        </button>
      ))}
    </div>
  )
}
