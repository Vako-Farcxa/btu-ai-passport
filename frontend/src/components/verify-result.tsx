'use client'

import { useRef } from 'react'

import { useResultMotion } from '@/components/motion'
import { SkillList } from '@/components/skill-list'
import { messages, type Locale } from '@/i18n/messages'
import type { VerifyResult } from '@/lib/api/types'
import { labelsFor, newerVersionNotice } from '@/lib/api/verify'

const glyphs = {
  valid: '✓',
  outdated: '↺',
  not_found: '?',
  error: '!',
} as const

export function VerifyResultCard({
  locale,
  result,
}: {
  locale: Locale
  result: VerifyResult
}) {
  const copy = messages[locale]
  const label = labelsFor(result.outcome, locale)
  const ref = useRef<HTMLElement>(null)
  useResultMotion(ref)
  const notice = newerVersionNotice(result, locale)
  const found = result.outcome === 'valid' || result.outcome === 'outdated'

  return (
    <section
      ref={ref}
      data-testid="verify-result"
      role="status"
      aria-live="polite"
      aria-label={label}
      className={`certificate outcome-${result.outcome}`}
    >
      <div className="certificate-head">
        <div className="valid-icon" aria-hidden="true">
          {glyphs[result.outcome]}
        </div>
        <div>
          <strong>{label}</strong>
          {found ? (
            <span>{result.is_latest ? copy.latest : copy.notLatest}</span>
          ) : null}
        </div>
        <div className="emboss" aria-hidden="true">
          BTU
        </div>
      </div>
      {notice ? (
        <p className="newer-notice" data-testid="newer-notice">
          {notice}
        </p>
      ) : null}
      {found ? (
        <>
          <div className="holder">
            <span>{copy.holderLabel}</span>
            <b>{result.holder_name}</b>
          </div>
          <div className="holder version-line">
            <span>{copy.versionLabel}</span>
            <b>{result.version}</b>
          </div>
          <SkillList skills={result.skills} locale={locale} />
          <a
            className="transaction-link"
            href={result.tx_url}
            target="_blank"
            rel="noopener noreferrer"
          >
            {copy.transaction}
            <span aria-hidden="true">↗</span>
          </a>
          <div
            className="testnet-pill"
            style={{
              marginTop: '0.75rem',
              fontSize: '0.75rem',
              color: '#94a3b8',
              display: 'flex',
              alignItems: 'center',
              gap: '0.35rem',
            }}
          >
            <span style={{ color: '#eab308' }}>✦</span>
            <span>{copy.testnetBadge}</span>
          </div>
        </>
      ) : null}
    </section>
  )
}
