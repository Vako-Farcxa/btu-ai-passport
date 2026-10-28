'use client'

import { useSyncExternalStore } from 'react'

import { preferredLocale, type Locale } from '@/i18n/messages'
import { writeCookie } from '@/lib/cookies'

const COOKIE = 'passport_locale'
const EVENT = 'passport-locale'

function readCookie(): Locale | null {
  const row = document.cookie
    .split('; ')
    .find((part) => part.startsWith(`${COOKIE}=`))
  const value = row?.split('=')[1]
  if (value === 'en' || value === 'ka') return value
  return null
}

function readClientLocale(): Locale {
  return readCookie() ?? preferredLocale(window.navigator.language)
}

function subscribe(onChange: () => void) {
  window.addEventListener(EVENT, onChange)
  return () => window.removeEventListener(EVENT, onChange)
}

export function useLocale(): [Locale, (locale: Locale) => void] {
  const locale = useSyncExternalStore(
    subscribe,
    readClientLocale,
    () => 'ka' as const,
  )
  const setLocale = (next: Locale) => {
    writeCookie(COOKIE, next, 31536000)
    document.documentElement.lang = next
    window.dispatchEvent(new Event(EVENT))
  }
  return [locale, setLocale]
}
