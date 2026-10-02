import { LOCALE_BCP47, type Locale } from './i18n/types'

export function cn(...classes: (string | boolean | undefined | null)[]): string {
  return classes.filter(Boolean).join(' ')
}

/**
 * HH:MM-style timestamp localised for the given locale (defaults to en).
 */
export function formatDate(date: Date, locale: Locale = 'en'): string {
  return new Intl.DateTimeFormat(LOCALE_BCP47[locale], {
    hour: '2-digit',
    minute: '2-digit',
  }).format(date)
}
