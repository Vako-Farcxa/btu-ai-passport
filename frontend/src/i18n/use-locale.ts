'use client'

import { createContext, useContext, useSyncExternalStore } from 'react'

import type { Locale } from '@/i18n/messages'
import {
  LOCALE_COOKIE as COOKIE,
  localeFromCookie,
  negotiateLocale,
} from '@/i18n/negotiate'
import { writeCookie } from '@/lib/cookies'

const EVENT = 'passport-locale'

/**
 * The language the server rendered this request in (decided in `proxy.ts` from the saved
 * choice or Accept-Language). It is the snapshot React hydrates with, so the first paint
 * and the server HTML agree. Without a provider (tests, error pages) it is English.
 */
export const ServerLocaleContext = createContext<Locale>('en')

function readCookie(): Locale | null {
  const row = document.cookie
    .split('; ')
    .find((part) => part.startsWith(`${COOKIE}=`))
  return localeFromCookie(row?.split('=')[1])
}

function readClientLocale(): Locale {
  const languages = window.navigator.languages
  return (
    readCookie() ??
    negotiateLocale(
      languages.length > 0 ? languages.join(',') : window.navigator.language,
    )
  )
}

function subscribe(onChange: () => void) {
  window.addEventListener(EVENT, onChange)
  return () => window.removeEventListener(EVENT, onChange)
}

export function useLocale(): [Locale, (locale: Locale) => void] {
  const serverLocale = useContext(ServerLocaleContext)
  const locale = useSyncExternalStore(
    subscribe,
    readClientLocale,
    () => serverLocale,
  )
  const setLocale = (next: Locale) => {
    writeCookie(COOKIE, next, 31536000)
    document.documentElement.lang = next
    window.dispatchEvent(new Event(EVENT))
  }
  return [locale, setLocale]
}
