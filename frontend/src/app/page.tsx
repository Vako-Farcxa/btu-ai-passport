'use client'

import { useEffect, useRef } from 'react'

import { LocaleSwitcher } from '@/components/locale-switcher'
import { SignInButton } from '@/components/sign-in-button'
import { entrance } from '@/components/entrance'
import { messages } from '@/i18n/messages'
import { useLocale } from '@/i18n/use-locale'
import { explainPassportError } from '@/lib/api/passport'
import { useMyPassport } from '@/lib/api/use-passport'

const linkClass =
  'underline underline-offset-4 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#10243e]'

export default function Home() {
  const [locale, setLocale] = useLocale()
  const session = useMyPassport()
  const copy = messages[locale]
  const ref = useRef<HTMLElement | null>(null)

  useEffect(() => {
    document.documentElement.lang = locale
    entrance(ref.current!)
  }, [locale])

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
            {copy.homeTitle}
          </h1>
          <p className="text-[#4d6078]">{copy.homeIntro}</p>
        </div>
      </header>
      {session.kind === 'loading' ? <p role="status">{copy.loading}</p> : null}
      {session.kind === 'error' ? (
        <p role="alert">{explainPassportError(session.code, locale)}</p>
      ) : null}
      {session.kind === 'ready' && session.body.passport === null ? (
        <p role="status">{copy.emptyPassport}</p>
      ) : null}
      {session.kind === 'ready' && session.body.passport !== null ? (
        <a className={linkClass} href="/passport">
          {copy.openPassport}
        </a>
      ) : null}
      <SignInButton label={copy.signIn} unavailable={copy.signInUnavailable} />
      <a className={linkClass} href="/verify">
        {copy.verifyLink}
      </a>
    </main>
  )
}
