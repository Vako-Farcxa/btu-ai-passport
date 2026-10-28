import type { ReactNode } from 'react'

import { BrandMark, Seal } from '@/components/book'
import { Footer } from '@/components/footer'
import { LocaleSwitcher } from '@/components/locale-switcher'
import type { Locale } from '@/i18n/messages'

export function InfoLayout({
  locale,
  onLocale,
  folio,
  chapterLabel,
  chapterBody,
  title,
  children,
}: {
  locale: Locale
  onLocale: (locale: Locale) => void
  folio: string
  chapterLabel: string
  chapterBody: string
  title: string
  children: ReactNode
}) {
  return (
    <main className="desk inner-desk">
      <header className="topbar">
        <BrandMark locale={locale} />
        <LocaleSwitcher locale={locale} onChange={onLocale} />
      </header>
      <div className="open-book">
        <aside className="book-left" aria-label={chapterLabel}>
          <div className="page-number">BTU · 2026</div>
          <div className="chapter-label">{chapterLabel}</div>
          <div className="ornament" aria-hidden="true">
            <span>✦</span>
          </div>
          <p>{chapterBody}</p>
          <Seal locale={locale} />
        </aside>
        <div className="book-right">
          <div className="page-content info-page">
            <h1>{title}</h1>
            {children}
            <span className="folio" aria-hidden="true">
              {folio}
            </span>
          </div>
        </div>
      </div>
      <div className="book-shadow" aria-hidden="true" />
      <Footer locale={locale} />
    </main>
  )
}
