'use client'

import Link from 'next/link'
import { useState } from 'react'

import { OpenBook, PrimaryButton } from '@/components/book'
import { SignInButton } from '@/components/sign-in-button'
import { CopyCode } from '@/components/copy-code'
import { FlagBadge, FlagDialog, MyFlags } from '@/components/flags'
import { ShareLinkButton } from '@/components/share-link-button'
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
import { flagForVersion } from '@/lib/api/flags'
import { useMyFlags } from '@/lib/api/use-flags'
import { useMyPassport } from '@/lib/api/use-passport'
import type { PassportVersion } from '@/lib/api/types'
import { readAccessToken } from '@/lib/supabase/client'

export default function PassportPage() {
  const [locale, setLocale] = useLocale()
  const session = useMyPassport()
  const [pdfNotice, setPdfNotice] = useState<string | null>(null)
  const [downloading, setDownloading] = useState<number | null>(null)
  const [flagging, setFlagging] = useState<number | null>(null)
  const copy = messages[locale]

  const passport = session.kind === 'ready' ? session.body.passport : null
  const versions = session.kind === 'ready' ? orderedVersions(session.body) : []
  const current = versions.find((version) => version.is_current) ?? versions[0]
  const holder = current?.holder_name
  const myFlags = useMyFlags(passport !== null)

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
          <div className="flags-bar">
            <MyFlags
              flags={myFlags.flags}
              unread={myFlags.unread}
              failed={myFlags.failed}
              locale={locale}
              onOpened={() => void myFlags.markSeen()}
            />
          </div>
          <ol className="version-list">
            {versions.map((version) => {
              const flag = flagForVersion(myFlags.flags, version.version)
              return (
                <li key={version.version} className="version-card">
                  <div className="version-head">
                    <div className="version-title">
                      <h3>
                        {copy.versionLabel} {version.version}
                        {version.is_current ? ` · ${copy.currentVersion}` : ''}
                      </h3>
                      <ShareLinkButton
                        code={version.verification_code}
                        locale={locale}
                      />
                    </div>
                    {flag ? (
                      <FlagBadge
                        flag={flag}
                        locale={locale}
                        onOpened={() => void myFlags.markSeen()}
                      />
                    ) : null}
                  </div>
                  <VersionFacts locale={locale} version={version} />
                  <div className="version-actions">
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
                    {version.anchor.tx_url ? (
                      <a className="action-button" href={version.anchor.tx_url}>
                        {copy.transaction}
                        <span aria-hidden="true">↗</span>
                      </a>
                    ) : null}
                    {flag?.status === 'open' ? null : (
                      <button
                        type="button"
                        className="flag-link"
                        onClick={() => setFlagging(version.version)}
                      >
                        {copy.flagIssue}
                      </button>
                    )}
                  </div>
                </li>
              )
            })}
          </ol>
          {flagging !== null ? (
            <FlagDialog
              version={flagging}
              locale={locale}
              onClose={() => setFlagging(null)}
              onSent={() => void myFlags.reload()}
            />
          ) : null}
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
        <CopyCode code={version.verification_code} locale={locale} />
      </p>
      <SkillList skills={version.skills} locale={locale} />
    </>
  )
}
