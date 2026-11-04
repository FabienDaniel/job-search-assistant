import { i18n } from '@lingui/core'

// Order is the picker's order. Each name is written in its own language.
export const LANGUAGES = [['en', 'English'], ['fr', 'Français']]
const SUPPORTED = LANGUAGES.map(([code]) => code)
const DEFAULT_LOCALE = 'en'
export const LOCALE_KEY = 'jobnavigator_locale'

/** The stored choice if it is supported, else the first browser language we ship, else English. */
export function resolveLocale(stored, browserLanguages = []) {
  if (SUPPORTED.includes(stored)) return stored
  for (const tag of browserLanguages) {
    const base = String(tag).toLowerCase().split('-')[0]
    if (SUPPORTED.includes(base)) return base
  }
  return DEFAULT_LOCALE
}

const readStored = () => { try { return window.localStorage.getItem(LOCALE_KEY) } catch { return null } }

export const currentLocale = () => i18n.locale || DEFAULT_LOCALE

/** Must finish before any screen module is imported: many labels are module-level constants read once at import. */
export async function initI18n() {
  const locale = resolveLocale(readStored(), navigator.languages || [navigator.language])
  const { messages } = await import(`./locales/${locale}.po`)
  i18n.loadAndActivate({ locale, messages })
  document.documentElement.lang = locale
}

/** Reloads so those module-level labels are evaluated again in the new language. */
export function setLocale(locale) {
  if (!SUPPORTED.includes(locale) || locale === currentLocale()) return
  try { window.localStorage.setItem(LOCALE_KEY, locale) } catch { /* the choice lasts until the reload only */ }
  window.location.reload()
}
