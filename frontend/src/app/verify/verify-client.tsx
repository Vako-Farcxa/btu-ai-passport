'use client'

import Link from 'next/link'
import { useSearchParams } from 'next/navigation'
import { useEffect, useRef, useState, type FormEvent } from 'react'

import { OpenBook, PrimaryButton } from '@/components/book'
import { Spinner } from '@/components/ui/spinner'
import { VerifyResultCard } from '@/components/verify-result'
import { messages } from '@/i18n/messages'
import { useLocale } from '@/i18n/use-locale'
import { postVerify } from '@/lib/api/client'
import {
  VerifyInputError,
  VerifyRateLimitError,
  type VerifyResult,
} from '@/lib/api/types'
import { submitDecision } from '@/lib/api/verify'
import { codeFromParam } from '@/lib/share'

export default function VerifyClient() {
  const [locale, setLocale] = useLocale()
  const sharedCode = codeFromParam(useSearchParams().get('code'))
  const [code, setCode] = useState(sharedCode)
  const [prompt, setPrompt] = useState(false)
  const [rateLimited, setRateLimited] = useState(false)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<VerifyResult | null>(null)
  const copy = messages[locale]

  async function check(value: string) {
    setPrompt(false)
    setRateLimited(false)
    try {
      const decision = await submitDecision(value, async (value) => {
        setLoading(true)
        try {
          return await postVerify(value)
        } finally {
          setLoading(false)
        }
      })
      if (decision.kind === 'prompt') {
        setResult(null)
        setPrompt(true)
        return
      }
      setResult(decision.body)
    } catch (error) {
      setResult(null)
      if (error instanceof VerifyInputError) {
        setPrompt(true)
        return
      }
      if (error instanceof VerifyRateLimitError) {
        setRateLimited(true)
        return
      }
      setResult({ outcome: 'error' })
    }
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    void check(code)
  }

  // A shared link (/verify?code=...) is checked once when the page opens.
  const autoChecked = useRef(false)
  useEffect(() => {
    if (autoChecked.current || sharedCode === '') return
    autoChecked.current = true
    void check(sharedCode)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  return (
    <OpenBook
      locale={locale}
      onLocale={setLocale}
      folio={result ? '03' : '02'}
      result={result !== null}
    >
      <div className="verify-page">
        <Link className="back-link" href="/">
          ← {copy.back}
        </Link>
        <span className="eyebrow">{copy.verifyEyebrow}</span>
        <h1 id="page-title">{copy.title}</h1>
        <p className="intro">{copy.intro}</p>
        <form onSubmit={onSubmit} aria-busy={loading}>
          <label htmlFor="verification-code">{copy.codeLabel}</label>
          <input
            id="verification-code"
            name="code"
            value={code}
            autoComplete="off"
            spellCheck={false}
            placeholder="RXRP-F90C-ZRBZ-EP7T"
            aria-invalid={prompt}
            aria-describedby={prompt ? 'code-hint' : undefined}
            onChange={(event) => setCode(event.target.value)}
          />
          <PrimaryButton
            type="submit"
            tone="navy"
            disabled={loading}
            aria-busy={loading}
          >
            {loading ? (
              <>
                <Spinner />
                {copy.checking}
              </>
            ) : (
              copy.check
            )}
          </PrimaryButton>
          {prompt ? (
            <p id="code-hint" role="alert">
              {copy.prompt}
            </p>
          ) : null}
          {rateLimited ? (
            <p
              id="code-rate-limit"
              role="alert"
              className="text-amber-700 text-sm mt-2 font-medium"
            >
              {copy.rateLimited}
            </p>
          ) : null}
        </form>
        {result ? (
          <VerifyResultCard
            key={`${result.outcome}-${code}`}
            locale={locale}
            result={result}
          />
        ) : null}
      </div>
    </OpenBook>
  )
}
