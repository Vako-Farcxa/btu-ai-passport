'use client'

import { useRef } from 'react'

import { useResultMotion } from '@/components/motion'
import { TestnetNote } from '@/components/testnet-note'
import { SkillList } from '@/components/skill-list'
import { messages, type Locale } from '@/i18n/messages'
import type { Onchain, VerifyResult } from '@/lib/api/types'
import {
  labelsFor,
  newerVersionNotice,
  notFoundNotice,
  pendingNotice,
  revokedNotice,
  tamperedNotice,
} from '@/lib/api/verify'
import {
  explorerBlockUrl,
  explorerContractUrl,
  explorerTxUrl,
} from '@/lib/explorer'

const glyphs = {
  valid: '✓',
  outdated: '↺',
  revoked: '✕',
  pending: '…',
  tampered: '!',
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
  const pending = pendingNotice(result, locale)
  const tampered = tamperedNotice(result, locale)
  const notFound = notFoundNotice(result, locale)
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
      {pending ? (
        <p className="pending-notice" data-testid="pending-notice">
          {pending}
        </p>
      ) : null}
      {tampered ? (
        <p className="tampered-notice" data-testid="tampered-notice">
          {tampered}
        </p>
      ) : null}
      {notFound ? (
        <p className="pending-notice" data-testid="not-found-notice">
          {notFound}
        </p>
      ) : null}
      {revoked ? (
        <p className="revoked-notice" data-testid="revoked-notice">
          {revoked}
        </p>
      ) : null}
      {found && result.onchain ? (
        <OnchainBadge onchain={result.onchain} locale={locale} />
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
          {result.onchain ? (
            <SelfVerify onchain={result.onchain} locale={locale} />
          ) : null}
          <TestnetNote locale={locale} />
        </>
      ) : null}
    </section>
  )
}

/** Says whether the contract was read and agreed. Never "verified" unless it was. */
function OnchainBadge({
  onchain,
  locale,
}: {
  onchain: Onchain
  locale: Locale
}) {
  const copy = messages[locale]
  const verified = onchain.status === 'verified'
  const blockNumber = verified ? (onchain.block_number ?? null) : null
  const blockUrl = blockNumber === null ? null : explorerBlockUrl(blockNumber)
  const title =
    verified && blockNumber !== null
      ? copy.onchainVerifiedAtBlock.replace('{block}', String(blockNumber))
      : verified
        ? copy.onchainVerified
        : copy.onchainUnavailable
  return (
    <div
      className={`onchain-badge ${verified ? 'onchain-verified' : 'onchain-unavailable'}`}
      data-testid="onchain-badge"
      data-status={onchain.status}
    >
      <strong>
        <span aria-hidden="true">{verified ? '✓' : '…'}</span> {title}
      </strong>
      <p>{verified ? copy.onchainVerifiedNote : copy.onchainUnavailableNote}</p>
      {blockUrl ? (
        <a href={blockUrl} data-testid="onchain-block-link">
          {copy.onchainBlockLink} {blockNumber}
          <span aria-hidden="true">↗</span>
        </a>
      ) : null}
    </div>
  )
}

/** The steps anyone can repeat on Polygonscan without trusting this site. */
function SelfVerify({ onchain, locale }: { onchain: Onchain; locale: Locale }) {
  const copy = messages[locale]
  const contractUrl = explorerContractUrl(onchain.contract_url)
  return (
    <details className="self-verify" data-testid="self-verify">
      <summary>{copy.selfVerifyTitle}</summary>
      <p>{copy.selfVerifyIntro}</p>
      <dl>
        <dt>{copy.selfVerifyContract}</dt>
        <dd>
          <code>{onchain.contract_address}</code>
        </dd>
        <dt>{copy.selfVerifyKey}</dt>
        <dd>
          <code>{onchain.verification_id_hash}</code>
        </dd>
        <dt>{copy.selfVerifyExpect}</dt>
        <dd>
          <code>{onchain.content_hash}</code>
        </dd>
      </dl>
      {contractUrl ? (
        <a href={contractUrl} data-testid="self-verify-link">
          {copy.selfVerifyOpen}
          <span aria-hidden="true">↗</span>
        </a>
      ) : null}
    </details>
  )
}
