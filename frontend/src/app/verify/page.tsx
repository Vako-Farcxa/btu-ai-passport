'use client'

import { BadgeCheck, CircleAlert, History, SearchX } from 'lucide-react'
import { useEffect, useState, type FormEvent, type ReactNode } from 'react'

import { LocaleSwitcher } from '@/components/locale-switcher'
import { Button } from '@/components/ui/button'
import { messages, type Locale, type Outcome } from '@/i18n/messages'
import { useLocale } from '@/i18n/use-locale'
import { postVerify } from '@/lib/api/client'
import { VerifyInputError, type VerifyResult } from '@/lib/api/types'
import { labelsFor, presentSkills, submitDecision } from '@/lib/api/verify'

const icons: Record<Outcome, ReactNode> = {
  valid: <BadgeCheck aria-hidden="true" />,
  outdated: <History aria-hidden="true" />,
  not_found: <SearchX aria-hidden="true" />,
  error: <CircleAlert aria-hidden="true" />,
}

export default function VerifyPage() {
  const [locale, setLocale] = useLocale()
  const [code, setCode] = useState('')
  const [prompt, setPrompt] = useState(false)
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState<VerifyResult | null>(null)
  const copy = messages[locale]

  useEffect(() => {
    document.documentElement.lang = locale
  }, [locale])

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setPrompt(false)
    try {
      const decision = await submitDecision(code, async (value) => {
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
      setResult({ outcome: 'error' })
    }
  }

  return (
    <main className="mx-auto flex w-full max-w-xl flex-1 flex-col gap-8 px-6 py-16 text-[#10243e]">
      <header className="flex flex-col gap-4">
        <LocaleSwitcher locale={locale} onChange={setLocale} />
        <div className="flex flex-col gap-2">
          <p className="text-sm tracking-wide text-[#4d6078]">BTU</p>
          <h1 className="text-3xl font-semibold tracking-tight">
            {copy.title}
          </h1>
          <p className="text-[#4d6078]">{copy.intro}</p>
        </div>
      </header>
      <form
        className="flex flex-col gap-3"
        onSubmit={onSubmit}
        aria-busy={loading}
      >
        <label className="text-sm font-medium" htmlFor="verification-code">
          {copy.codeLabel}
        </label>
        <input
          id="verification-code"
          name="code"
          value={code}
          autoComplete="off"
          spellCheck={false}
          onChange={(event) => setCode(event.target.value)}
          className="h-11 rounded-md border border-[#c5d0dc] bg-white px-3 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#10243e]"
        />
        <Button type="submit" disabled={loading} className="h-11 w-fit px-4">
          {loading ? copy.checking : copy.check}
        </Button>
        {prompt ? (
          <p id="code-hint" role="alert">
            {copy.prompt}
          </p>
        ) : null}
      </form>
      {result ? <VerifyResultView locale={locale} result={result} /> : null}
    </main>
  )
}

function VerifyResultView({
  locale,
  result,
}: {
  locale: Locale
  result: VerifyResult
}) {
  const copy = messages[locale]
  const label = labelsFor(result.outcome, locale)
  return (
    <section
      data-testid="verify-result"
      role="status"
      aria-live="polite"
      aria-label={label}
      className="flex flex-col gap-4 rounded-md border border-[#d5dee8] bg-white p-5"
    >
      <h2 className="flex items-center gap-2 text-xl font-semibold">
        {icons[result.outcome]}
        <span>{label}</span>
      </h2>
      {result.outcome === 'valid' || result.outcome === 'outdated' ? (
        <>
          <p>{result.holder_name}</p>
          <p>{result.is_latest ? copy.latest : copy.notLatest}</p>
          <p>
            {copy.skills} · {result.version}
          </p>
          <ul className="flex flex-col gap-2">
            {presentSkills(result.skills, locale).map((skill) => (
              <li
                key={`${skill.skill}-${skill.badge}-${skill.awarded_on ?? 'none'}`}
              >
                <span className="font-medium">{skill.skill}</span>
                {skill.badge ? <span> · {skill.badge}</span> : null}
                <span> · {skill.awarded_on ?? copy.dateUnavailable}</span>
              </li>
            ))}
          </ul>
          <a
            className="underline underline-offset-4 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-[#10243e]"
            href={result.tx_url}
          >
            {copy.transaction}
          </a>
        </>
      ) : null}
    </section>
  )
}
