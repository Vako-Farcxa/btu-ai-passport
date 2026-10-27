'use client'

import Link from 'next/link'
import { useState } from 'react'

import { OpenBook, PrimaryButton } from '@/components/book'
import { SignInButton } from '@/components/sign-in-button'
import { SkillList } from '@/components/skill-list'
import { Spinner } from '@/components/ui/spinner'
import { messages, type Locale } from '@/i18n/messages'
import { useLocale } from '@/i18n/use-locale'
import {
  downloadPassportPdf,
  explainPassportError,
  orderedVersions,
  PassportRequestError,
} from '@/lib/api/passport'
import { useMyPassport } from '@/lib/api/use-passport'
import type { PassportVersion } from '@/lib/api/types'
import { readAccessToken } from '@/lib/supabase/client'

export default function PassportPage() {
  const [locale, setLocale] = useLocale()
  const session = useMyPassport()
  const [pdfNotice, setPdfNotice] = useState<string | null>(null)
  const [downloading, setDownloading] = useState<number | null>(null)
  const copy = messages[locale]

  const passport = session.kind === 'ready' ? session.body.passport : null
  const versions = session.kind === 'ready' ? orderedVersions(session.body) : []
  const current = versions.find((version) => version.is_current) ?? versions[0]
  const holder = current?.holder_name

  async function onDownload(version: number) {
    if (downloading !== null) return
      setPdfNotice(null)
      setDownloading(version)
      try {
        const token = await readAccessToken()
        if (!token) {
          setPdfNotice(copy.signInRequired)
          return
        }
        const file = await downloadPassportPdf(token, version, locale)
        const url = URL.createObjectURL(file)
        const link = document.createElement('a')
        link.href = url
        link.download = `passport-v${version}-${locale}.pdf`
        document.body.append(link)
        link.click()
        link.remove()
        window.setTimeout(() => URL.revokeObjectURL(url), 1000)
      } catch (error) {
        const code = error instanceof PassportRequestError ? error.code : 'error'
        setPdfNotice(explainPassportError(code, locale))
      } finally {
        setDownloading(null)
      }
  }

  return (
    <OpenBook locale={locale} onLocale={setLocale} folio="01">
    <Link className="back-link" href="/">
    ← {copy.back}
    </Link>
    <span className="eyebrow">{copy.passportEyebrow}</span>
    <h1 id="page-title">{copy.passportTitle}</h1>
    {holder ? (
      <p className="signed-in">
      <span>{holder}</span>
      <i aria-hidden="true" />
      </p>
    ) : null}
    {session.kind === 'loading' ? (
      <p className="page-status" role="status">
      {copy.loading}
      </p>
    ) : null}
    {session.kind === 'signed_out' ? (
      <p className="page-alert" role="alert">
      {copy.signInRequired}
      </p>
    ) : null}
    {session.kind === 'error' ? (
      <p className="page-alert" role="alert">
      {explainPassportError(session.code, locale)}
      </p>
    ) : null}
    {session.kind === 'ready' && passport === null ? (
      <div className="empty-state">
      <div className="empty-glyph" aria-hidden="true">
      ✦
      </div>
      <p role="status">{copy.emptyPassport}</p>
      <Link className="text-link" href="/verify">
      {copy.verifyLink} <span aria-hidden="true">→</span>
      </Link>
      </div>
    ) : null}
    {passport ? (
      <section className="passport-record" aria-labelledby="passport-id">
      <p id="passport-id" className="meta-line">
      <span className="meta-label">{copy.passportId}</span>
      {': '}
      {passport.passport_id}
      </p>
      {current ? (
        <p className="meta-line">
        <span className="meta-label">{copy.currentVersion}</span>
        {': '}
        {current.version}
        </p>
      ) : null}
      {pdfNotice ? (
        <p className="page-alert" role="alert">
        {pdfNotice}
        </p>
      ) : null}
      <h2>{copy.history}</h2>
      <ol className="version-list">
      {versions.map((version) => (
        <li key={version.version} className="version-card">
        <h3>
        {copy.versionLabel} {version.version}
        {version.is_current ? ` · ${copy.currentVersion}` : ''}
        </h3>
        <VersionFacts locale={locale} version={version} />
        <PrimaryButton
        type="button"
        tone="navy"
        disabled={downloading !== null}
        aria-busy={downloading === version.version}
        onClick={() => void onDownload(version.version)}
        >
        {downloading === version.version ? (
          <>
          <Spinner />
          {copy.preparingPdf}
          </>
        ) : (
          copy.downloadPdf
        )}
        </PrimaryButton>
        </li>
      ))}
      </ol>
      </section>
    ) : null}
    {session.kind === 'signed_out' ? (
      <SignInButton
      label={copy.signIn}
      unavailable={copy.signInUnavailable}
      tone="navy"
      />
    ) : null}
    {session.kind === 'ready' && passport === null ? null : (
      <Link className="text-link page-verify" href="/verify">
      {copy.verifyLink}
      </Link>
    )}
    </OpenBook>
  )
}

function VersionFacts({
  locale,
  version,
}: {
  locale: Locale
  version: PassportVersion
}) {
  const copy = messages[locale]
  return (
    <>
    <p className="meta-line">{version.holder_name}</p>
    <p className="meta-line">
    <span className="meta-label">{copy.verificationCode}</span>
    {': '}
    <span className="code-value">{version.verification_code}</span>
    </p>
    <SkillList skills={version.skills} locale={locale} />
    {version.anchor.tx_url ? (
      <a className="transaction-link" href={version.anchor.tx_url}>
      {copy.transaction}
      <span aria-hidden="true">↗</span>
      </a>
    ) : null}
    </>
  )
}
