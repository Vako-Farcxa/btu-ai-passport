'use client'

import { messages, type Locale } from '@/i18n/messages'

type LocaleSwitcherProps = {
  locale: Locale
  onChange: (locale: Locale) => void
}

export function LocaleSwitcher({ locale, onChange }: LocaleSwitcherProps) {
  const copy = messages[locale]
  return (
    <div className="flex items-center gap-2">
      <span className="text-sm text-[#4d6078]">{copy.language}</span>
      <button
        type="button"
        className="rounded-md px-2 py-1 text-sm underline-offset-4 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#10243e]"
        aria-pressed={locale === 'en'}
        onClick={() => onChange('en')}
      >
        English
      </button>
      <button
        type="button"
        className="rounded-md px-2 py-1 text-sm underline-offset-4 hover:underline focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#10243e]"
        aria-pressed={locale === 'ka'}
        onClick={() => onChange('ka')}
      >
        ქართული
      </button>
    </div>
  )
}
