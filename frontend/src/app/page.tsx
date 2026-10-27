'use client'

import Link from 'next/link'

import { LandingDesk } from '@/components/book'
import { SignInButton } from '@/components/sign-in-button'
import { messages } from '@/i18n/messages'
import { useLocale } from '@/i18n/use-locale'
import { explainPassportError } from '@/lib/api/passport'
import { useMyPassport } from '@/lib/api/use-passport'

export default function Home() {
  const [locale, setLocale] = useLocale()
  const session = useMyPassport()
  const copy = messages[locale]
  const hasPassport = session.kind === 'ready' && session.body.passport !== null

  return (
    <LandingDesk locale={locale} onLocale={setLocale}>
    <div className="landing-stage">
    <div className="book-cover">
    <div className="cover-border">
    <div className="cover-content">
    <span className="cover-eyebrow">BTU · 2026</span>
    <div className="cover-flourish" aria-hidden="true">
    <i />
    <b>✦</b>
    <i />
    </div>
    <h1>{copy.homeTitle}</h1>
    <p>{copy.homeIntro}</p>
    {session.kind === 'loading' ? (
      <div className="cover-status">
      <span aria-hidden="true" />
      <p role="status">{copy.loading}</p>
      </div>
    ) : null}
    {session.kind === 'error' ? (
      <p role="alert" className="cover-alert">
      {explainPassportError(session.code, locale)}
      </p>
    ) : null}
    {session.kind === 'signed_out' ||
      (session.kind === 'ready' && session.body.passport === null) ? (
        <div className="cover-status">
        <span aria-hidden="true" />
        <p role="status">{copy.emptyPassport}</p>
        </div>
      ) : null}
      {hasPassport ? (
        <Link className="text-link cover-open" href="/passport">
        {copy.openPassport}
        </Link>
      ) : null}
      <SignInButton
      label={copy.signIn}
      unavailable={copy.signInUnavailable}
      />
      <Link className="text-link" href="/verify">
      {copy.verifyLink}
      </Link>
      </div>
      <div className="cover-footer">
      BUSINESS AND TECHNOLOGY UNIVERSITY
      </div>
      </div>
      </div>
      <div className="book-pages" aria-hidden="true" />
      <div className="book-ribbon" aria-hidden="true" />
      </div>
      <p className="landing-note">{copy.landingNote}</p>
      </LandingDesk>
  )
}
