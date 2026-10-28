'use client'

import Link from 'next/link'
import { useRef, type ButtonHTMLAttributes, type ReactNode } from 'react'

import { messages, type Locale } from '@/i18n/messages'
import { LocaleSwitcher } from '@/components/locale-switcher'
import { useCoverMotion, useOpenBookMotion } from '@/components/motion'

export function BrandMark({ locale }: { locale: Locale }) {
  const name = messages[locale].universityName
  return (
    <Link className="brand-mark" href="/" aria-label={name}>
      <span className="monogram" aria-hidden="true">
        B
      </span>
      <span className="brand-word">
        {locale === 'en' ? name.toUpperCase() : name}
      </span>
    </Link>
  )
}

export function Seal({ locale }: { locale: Locale }) {
  return (
    <div className="seal" aria-hidden="true">
      <span className="seal-ring">BTU</span>
      <span className="seal-stars">✦</span>
      <small>{messages[locale].sealEstablished}</small>
    </div>
  )
}

export function PrimaryButton({
  tone = 'gold',
  children,
  className,
  type = 'button',
  ...props
}: ButtonHTMLAttributes<HTMLButtonElement> & { tone?: 'gold' | 'navy' }) {
  const classes = ['primary-button', tone === 'navy' ? 'navy' : '', className]
    .filter(Boolean)
    .join(' ')
  return (
    <button className={classes} type={type} {...props}>
      <span className="button-label">{children}</span>
      <span aria-hidden="true">→</span>
    </button>
  )
}

export function LandingDesk({
  locale,
  onLocale,
  children,
}: {
  locale: Locale
  onLocale: (locale: Locale) => void
  children: ReactNode
}) {
  const ref = useRef<HTMLElement>(null)
  useCoverMotion(ref)
  return (
    <main ref={ref} className="desk landing">
      <header className="topbar">
        <BrandMark locale={locale} />
        <LocaleSwitcher locale={locale} onChange={onLocale} />
      </header>
      {children}
    </main>
  )
}

export function OpenBook({
  locale,
  onLocale,
  folio,
  result = false,
  children,
}: {
  locale: Locale
  onLocale: (locale: Locale) => void
  folio: string
  result?: boolean
  children: ReactNode
}) {
  const ref = useRef<HTMLElement>(null)
  const copy = messages[locale]
  useOpenBookMotion(ref)
  return (
    <main ref={ref} className="desk inner-desk">
      <header className="topbar">
        <BrandMark locale={locale} />
        <LocaleSwitcher locale={locale} onChange={onLocale} />
      </header>
      <div className={result ? 'open-book result-book' : 'open-book'}>
        <aside className="book-left" aria-label={copy.chapter}>
          <div className="page-number">BTU · 2026</div>
          <div className="chapter-label">{copy.chapter}</div>
          <div className="ornament" aria-hidden="true">
            <span>✦</span>
          </div>
          <p>{copy.chapterBody}</p>
          <Seal locale={locale} />
        </aside>
        <div className="book-right">
          <div className="page-content">
            {children}
            <span className="folio" aria-hidden="true">
              {folio}
            </span>
          </div>
        </div>
      </div>
      <div className="book-shadow" aria-hidden="true" />
    </main>
  )
}
