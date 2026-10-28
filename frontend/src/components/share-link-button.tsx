'use client'

import { useRef, useState } from 'react'

import { messages, type Locale } from '@/i18n/messages'
import { shareLinkFor } from '@/lib/share'

type State = 'idle' | 'copied' | 'failed'

export function ShareLinkButton({
  code,
  locale,
}: {
  code: string
  locale: Locale
}) {
  const copy = messages[locale]
  const [state, setState] = useState<State>('idle')
  const [link, setLink] = useState('')
  const timer = useRef<number | undefined>(undefined)

  async function onCopy() {
    const url = shareLinkFor(window.location.origin, code)
    setLink(url)
    window.clearTimeout(timer.current)
    try {
      await navigator.clipboard.writeText(url)
      setState('copied')
      timer.current = window.setTimeout(() => setState('idle'), 2500)
    } catch {
      setState('failed')
    }
  }

  return (
    <>
      <button
        type="button"
        className="text-link share-link"
        onClick={() => void onCopy()}
      >
        {copy.copyShareLink}
      </button>
      <p className="share-link-note" role="status" aria-live="polite">
        {state === 'copied' ? copy.shareLinkCopied : null}
        {state === 'failed' ? `${copy.shareLinkFailed} ${link}` : null}
      </p>
    </>
  )
}
