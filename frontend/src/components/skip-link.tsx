'use client'

import { messages } from '@/i18n/messages'
import { useLocale } from '@/i18n/use-locale'

/** The first tab stop on every page. It jumps past the header to the element with id "main". */
export function SkipLink() {
  const [locale] = useLocale()
  return (
    <a href="#main" className="skip-link">
      {messages[locale].skipToContent}
    </a>
  )
}
