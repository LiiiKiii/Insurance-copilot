'use client'

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from 'react'
import {
  DEFAULT_LOCALE,
  LOCALES,
  LOCALE_HTML_LANG,
  type Locale,
  type MessageKey,
} from './types'
import { messages as zhHK } from './messages.zh-HK'
import { messages as en } from './messages.en'

const TABLES: Record<Locale, Record<MessageKey, string>> = {
  'zh-HK': zhHK,
  en,
}

const STORAGE_KEY = 'ic_locale'

interface LocaleCtxValue {
  locale: Locale
  setLocale: (l: Locale) => void
}

const LocaleCtx = createContext<LocaleCtxValue>({
  locale: DEFAULT_LOCALE,
  setLocale: () => {},
})

function isLocale(value: string | null): value is Locale {
  return value !== null && (LOCALES as readonly string[]).includes(value)
}

function detectInitial(): Locale {
  if (typeof window === 'undefined') return DEFAULT_LOCALE
  try {
    const stored = window.localStorage.getItem(STORAGE_KEY)
    if (isLocale(stored)) return stored
  } catch {
    /* private mode / disabled — fall through to navigator */
  }
  const nav = window.navigator?.language?.toLowerCase() ?? ''
  return nav.startsWith('en') ? 'en' : DEFAULT_LOCALE
}

interface LocaleProviderProps {
  children: ReactNode
}

/**
 * Mounts the locale context. SSR always renders with DEFAULT_LOCALE so the
 * server-rendered HTML matches the client's first paint; the real locale
 * (from localStorage / navigator.language) is applied in a useEffect after
 * mount, avoiding hydration warnings.
 */
export function LocaleProvider({ children }: LocaleProviderProps) {
  const [locale, setLocaleState] = useState<Locale>(DEFAULT_LOCALE)

  useEffect(() => {
    const initial = detectInitial()
    setLocaleState(initial)
    document.documentElement.lang = LOCALE_HTML_LANG[initial]
    document.title = TABLES[initial]['app.metaTitle']
  }, [])

  const setLocale = (next: Locale): void => {
    setLocaleState(next)
    try {
      window.localStorage.setItem(STORAGE_KEY, next)
    } catch {
      /* localStorage unavailable — preference is in-memory only */
    }
    if (typeof document !== 'undefined') {
      document.documentElement.lang = LOCALE_HTML_LANG[next]
      document.title = TABLES[next]['app.metaTitle']
    }
  }

  return <LocaleCtx.Provider value={{ locale, setLocale }}>{children}</LocaleCtx.Provider>
}

interface UseTranslationResult {
  t: (key: MessageKey, vars?: Record<string, string | number>) => string
  locale: Locale
  setLocale: (l: Locale) => void
}

export function useTranslation(): UseTranslationResult {
  const { locale, setLocale } = useContext(LocaleCtx)

  // Memoise per locale so consumers can put `t` in useEffect deps without
  // thrashing every render — t is stable until the user switches language.
  const t = useCallback(
    (key: MessageKey, vars?: Record<string, string | number>): string => {
      const raw = TABLES[locale][key] ?? key
      if (!vars) return raw
      return raw.replace(/\{(\w+)\}/g, (_match, name: string) => {
        const value = vars[name]
        return value === undefined ? `{${name}}` : String(value)
      })
    },
    [locale],
  )

  return { t, locale, setLocale }
}
