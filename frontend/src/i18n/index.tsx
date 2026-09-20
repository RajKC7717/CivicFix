/** Language context: a tiny provider over the hand-written dictionaries. */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { DICTS, LANGUAGE_OPTIONS, type Dict, type LangCode } from './strings'

const STORAGE_KEY = 'nagarnetra.lang'

interface LanguageContextValue {
  lang: LangCode
  setLang: (lang: LangCode) => void
  t: (key: keyof Dict) => string
  /** Pick the right field off an API object that carries per-language labels. */
  pick: (source: { label: string; label_hi?: string; label_mr?: string } | null | undefined) => string
}

const LanguageContext = createContext<LanguageContextValue | null>(null)

function initialLang(): LangCode {
  try {
    const stored = localStorage.getItem(STORAGE_KEY) as LangCode | null
    if (stored && stored in DICTS) return stored
  } catch {
    /* ignore */
  }
  // Follow the browser when we can; Pune defaults to Marathi otherwise.
  const preferred = navigator.languages ?? [navigator.language]
  for (const tag of preferred) {
    const base = tag.slice(0, 2).toLowerCase()
    if (base === 'mr' || base === 'hi' || base === 'en') return base as LangCode
  }
  return 'en'
}

export function LanguageProvider({ children }: { children: ReactNode }) {
  const [lang, setLangState] = useState<LangCode>(initialLang)

  const setLang = useCallback((next: LangCode) => {
    setLangState(next)
    try {
      localStorage.setItem(STORAGE_KEY, next)
    } catch {
      /* ignore */
    }
  }, [])

  useEffect(() => {
    document.documentElement.lang = lang
  }, [lang])

  const value = useMemo<LanguageContextValue>(() => {
    const dict = DICTS[lang]
    return {
      lang,
      setLang,
      t: (key) => dict[key] ?? DICTS.en[key] ?? String(key),
      pick: (source) => {
        if (!source) return ''
        if (lang === 'hi') return source.label_hi || source.label
        if (lang === 'mr') return source.label_mr || source.label
        return source.label
      },
    }
  }, [lang, setLang])

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>
}

export function useI18n(): LanguageContextValue {
  const context = useContext(LanguageContext)
  if (!context) throw new Error('useI18n must be used inside <LanguageProvider>')
  return context
}

export { LANGUAGE_OPTIONS }
export type { Dict, LangCode }
