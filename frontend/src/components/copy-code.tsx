'use client'

import { Check, Copy } from 'lucide-react'
import { useRef, useState } from 'react'

import { messages, type Locale } from '@/i18n/messages'
import { copyText } from '@/lib/clipboard'

type State = 'idle' | 'copied' | 'failed'

/** A verification code with a small copy button. Selects the text if copying is refused. */
export function CopyCode({ code, locale }: { code: string; locale: Locale }) {
  const copy = messages[locale]
  const [state, setState] = useState<State>('idle')
  const text = useRef<HTMLSpanElement>(null)
  const timer = useRef<number | undefined>(undefined)

  async function onCopy() {
    window.clearTimeout(timer.current)
    if (await copyText(code)) {
      setState('copied')
      timer.current = window.setTimeout(() => setState('idle'), 2000)
      return
    }
    setState('failed')
    const node = text.current
    const selection = window.getSelection()
    if (node && selection) {
      const range = document.createRange()
      range.selectNodeContents(node)
      selection.removeAllRanges()
      selection.addRange(range)
    }
  }

  return (
    <>
      <span ref={text} className="code-value">
        {code}
      </span>
      <button
        type="button"
        className="copy-code"
        aria-label={copy.copyCode}
        title={copy.copyCode}
        onClick={() => void onCopy()}
      >
        {state === 'copied' ? (
          <Check aria-hidden="true" size={16} />
        ) : (
          <Copy aria-hidden="true" size={16} />
        )}
      </button>
      <span className="copy-feedback" role="status" aria-live="polite">
        {state === 'copied' ? copy.codeCopied : null}
        {state === 'failed' ? copy.copyCodeFailed : null}
      </span>
    </>
  )
}
