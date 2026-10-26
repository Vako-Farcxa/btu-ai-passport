'use client'

import { useEffect, useRef, useState } from 'react'

import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { LocaleSwitcher } from '@/components/locale-switcher'
import { SignInButton } from '@/components/sign-in-button'
import { entrance } from '@/components/entrance'
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

const linkClass =
  'underline underline-offset-4 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#10243e]'

export default function PassportPage() {
  const [locale, setLocale] = useLocale()
  const session = useMyPassport()
  const [pdfNotice, setPdfNotice] = useState<string | null>(null)
  const [downloading, setDownloading] = useState<number | null>(null)
  const copy = messages[locale]
  const ref = useRef<HTMLElement | null>(null)

  useEffect(() => {
    document.documentElement.lang = locale
    entrance(ref.current!)
  }, [locale])

  const passport = session.kind === 'ready' ? session.body.passport : null
  const versions = session.kind === 'ready' ? orderedVersions(session.body) : []
  const current = versions.find((version) => version.is_current) ?? versions[0]

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
    <main
      ref={ref}
      className="mx-auto flex w-full max-w-xl flex-1 flex-col gap-8 px-6 py-16 text-[#10243e]"
    >
      <header className="flex flex-col gap-4">
        <LocaleSwitcher locale={locale} onChange={setLocale} />
        <div className="flex flex-col gap-2">
          <p className="text-sm tracking-wide text-[#4d6078]">BTU</p>
          <h1 className="text-3xl font-semibold tracking-tight">
            {copy.passportTitle}
          </h1>
        </div>
      </header>
      {session.kind === 'loading' ? <p role="status">{copy.loading}</p> : null}
      {session.kind === 'signed_out' ? (
        <p role="alert">{copy.signInRequired}</p>
      ) : null}
      {session.kind === 'error' ? (
        <p role="alert">{explainPassportError(session.code, locale)}</p>
      ) : null}
      {session.kind === 'ready' && passport === null ? (
        <p role="status">{copy.emptyPassport}</p>
      ) : null}
      {passport && current ? (
        <section className="flex flex-col gap-6" aria-labelledby="passport-id">
          <p id="passport-id">
            <span className="font-medium">{copy.passportId}</span>
            {': '}
            {passport.passport_id}
          </p>
          <p>
            <span className="font-medium">{copy.currentVersion}</span>
            {': '}
            {current.version}
          </p>
          {pdfNotice ? <p role="alert">{pdfNotice}</p> : null}
          <div className="flex flex-col gap-3">
            <h2 className="text-xl font-semibold">{copy.history}</h2>
            <ol className="flex flex-col gap-4">
              {versions.map((version) => (
                <li
                  key={version.version}
                  className="flex flex-col gap-2 rounded-md border border-[#d5dee8] bg-white p-4"
                >
                  <h3 className="font-medium">
                    {copy.versionLabel} {version.version}
                    {version.is_current ? ` · ${copy.currentVersion}` : ''}
                  </h3>
                  <VersionFacts locale={locale} version={version} />
                  <Button
                    type="button"
                    className="h-10 w-fit bg-[#10243e] px-4 text-white hover:bg-[#1d3a5f] focus-visible:ring-[#10243e]/40"
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
                  </Button>
                </li>
              ))}
            </ol>
          </div>
        </section>
      ) : null}
      {session.kind === 'signed_out' ? (
        <SignInButton
          label={copy.signIn}
          unavailable={copy.signInUnavailable}
        />
      ) : null}
      <a className={linkClass} href="/verify">
        {copy.verifyLink}
      </a>
    </main>
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
      <p>{version.holder_name}</p>
      <p>
        <span className="font-medium">{copy.verificationCode}</span>
        {': '}
        {version.verification_code}
      </p>
      <ul className="flex flex-col gap-2">
        {version.skills.map((skill) => (
          <li
            key={`${skill.skill}-${skill.badge}-${skill.awarded_on ?? 'none'}`}
          >
            <span className="font-medium">{skill.skill}</span>
            {skill.badge ? <span> · {skill.badge}</span> : null}
            <span> · {skill.awarded_on ?? copy.dateUnavailable}</span>
            {skill.description ? (
              <p className="text-sm opacity-80">{skill.description}</p>
            ) : null}
          </li>
        ))}
      </ul>
      {version.anchor.tx_url ? (
        <a className={linkClass} href={version.anchor.tx_url}>
          {copy.transaction}
        </a>
      ) : null}
    </>
  )
}
