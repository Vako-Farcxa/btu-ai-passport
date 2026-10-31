'use client'

import type { ReactNode } from 'react'

import type { Locale } from '@/i18n/messages'
import { ServerLocaleContext } from '@/i18n/use-locale'

/** Hands the language the server rendered with to every page, for the first paint. */
export function LocaleProvider({
  locale,
  children,
}: {
  locale: Locale
  children: ReactNode
}) {
  return (
    <ServerLocaleContext.Provider value={locale}>
      {children}
    </ServerLocaleContext.Provider>
  )
}
