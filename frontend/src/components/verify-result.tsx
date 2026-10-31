'use client'

import { useRef } from 'react'

import { useResultMotion } from '@/components/motion'
import { TestnetNote } from '@/components/testnet-note'
import { SkillList } from '@/components/skill-list'
import { messages, type Locale } from '@/i18n/messages'
import type { VerifyResult } from '@/lib/api/types'
import { labelsFor, newerVersionNotice, revokedNotice } from '@/lib/api/verify'
import { explorerTxUrl } from '@/lib/explorer'

const glyphs = {
  valid: '✓',
  outdated: '↺',
  revoked: '✕',
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
  const revoked = revokedNotice(result, locale)
  const found = result.outcome === 'valid' || result.outcome === 'outdated'
  const txUrl = 'tx_url' in result ? explorerTxUrl(result.tx_url) : null

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
      {revoked ? (
        <p className="revoked-notice" data-testid="revoked-notice">
          {revoked}
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
          {txUrl ? (
            <a className="transaction-link" href={txUrl}>
              {copy.transaction}
              <span aria-hidden="true">↗</span>
            </a>
          ) : null}
          <TestnetNote locale={locale} />
        </>
      ) : null}
    </section>
  )
}
