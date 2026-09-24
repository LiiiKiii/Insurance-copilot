/**
 * i18n public barrel.
 *
 * Re-exports types/constants from `./types` (pure leaf) and the React
 * provider/hook from `./LocaleProvider`. The provider DOES NOT import
 * from this barrel — see `./types.ts` for why (avoids an ESM cycle that
 * Turbopack's SSR pass turns into TDZ errors at prerender time).
 */
export {
  type Locale,
  type MessageKey,
  LOCALES,
  DEFAULT_LOCALE,
  LOCALE_BCP47,
  LOCALE_HTML_LANG,
} from './types'

export { LocaleProvider, useTranslation } from './LocaleProvider'
