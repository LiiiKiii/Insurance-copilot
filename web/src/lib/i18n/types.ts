/**
 * Pure-data leaf module for the i18n package — types + constants only.
 *
 * IMPORTANT: this file MUST NOT import from `./index` or `./LocaleProvider`.
 * `LocaleProvider.tsx` and the barrel `index.ts` import their
 * types/constants from HERE so we don't form an import cycle
 * (i18n/index → LocaleProvider → i18n/index) which Turbopack's SSR pass
 * resolves with TDZ errors at prerender time.
 */
import { messages as en } from './messages.en'

export type Locale = 'en'

export const LOCALES: readonly Locale[] = ['en'] as const
export const DEFAULT_LOCALE: Locale = 'en'

/** Compile-time set of every key declared in the canonical (en) catalogue. */
export type MessageKey = keyof typeof en

/** Map our `Locale` to a BCP 47 tag suitable for `Intl.DateTimeFormat` etc. */
export const LOCALE_BCP47: Record<Locale, string> = {
  en: 'en-US',
}

/** Mirror of the value used in <html lang="..."> for each locale. */
export const LOCALE_HTML_LANG: Record<Locale, string> = {
  en: 'en',
}
