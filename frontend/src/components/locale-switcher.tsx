'use client'

import { messages, type Locale } from '@/i18n/messages'

type LocaleSwitcherProps = {
  locale: Locale
  onChange: (locale: Locale) => void
}

export function LocaleSwitcher({ locale, onChange }: LocaleSwitcherProps) {
  const copy = messages[locale]
  return (
    <div className="language-switcher" role="group" aria-label={copy.language}>
    <span>{copy.language}</span>
    <span className="dot" aria-hidden="true">
    ·
    </span>
    <button
    type="button"
    className={locale === 'en' ? 'active' : undefined}
    aria-pressed={locale === 'en'}
    onClick={() => onChange('en')}
    >
    English
    </button>
    <span className="dot" aria-hidden="true">
    ·
    </span>
    <button
    type="button"
    className={locale === 'ka' ? 'active' : undefined}
    aria-pressed={locale === 'ka'}
    onClick={() => onChange('ka')}
    >
    ქართული
    </button>
    </div>
  )
}
