'use client'

import Link from 'next/link'

import { OpenBook } from '@/components/book'
import { useLocale } from '@/i18n/use-locale'
import { trust } from '@/i18n/trust'

export function StatusPage({
  kind,
  onRetry,
}: {
  kind: 'not_found' | 'error'
  onRetry?: () => void
}) {
  const [locale, setLocale] = useLocale()
  const copy = trust[locale]
  const missing = kind === 'not_found'

  return (
    <OpenBook
      locale={locale}
      onLocale={setLocale}
      folio={missing ? '404' : '!'}
    >
      <div className="status-page" data-testid={`status-${kind}`}>
        <span className="eyebrow">{missing ? '404' : 'BTU · 2026'}</span>
        <h1>{missing ? copy.notFoundTitle : copy.errorTitle}</h1>
        <p className="intro" role={missing ? undefined : 'alert'}>
          {missing ? copy.notFoundBody : copy.errorBody}
        </p>
        <div className="status-actions">
          {!missing && onRetry ? (
            <button type="button" className="primary-button" onClick={onRetry}>
              <span className="button-label">{copy.tryAgain}</span>
              <span aria-hidden="true">→</span>
            </button>
          ) : null}
          <Link className="text-link" href="/">
            {copy.backHome}
          </Link>
        </div>
      </div>
    </OpenBook>
  )
}
