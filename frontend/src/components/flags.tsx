'use client'

import { useEffect, useId, useRef, useState, type FormEvent } from 'react'

import { messages, type Locale } from '@/i18n/messages'
import {
  COMMENT_MAX,
  cleanComment,
  commentProblem,
  createFlag,
  explainFlagError,
  FlagRequestError,
  type StudentFlag,
} from '@/lib/api/flags'
import { readAccessToken } from '@/lib/supabase/client'

function dateText(value: string, locale: Locale): string {
  return new Date(value).toLocaleDateString(locale === 'ka' ? 'ka-GE' : 'en-GB')
}

/** A small modal. Escape and a click outside close it; focus returns to the opener. */
function Modal({
  titleId,
  onClose,
  children,
}: {
  titleId: string
  onClose: () => void
  children: React.ReactNode
}) {
  const ref = useRef<HTMLDivElement>(null)

  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null
    ref.current?.focus()
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => {
      window.removeEventListener('keydown', onKey)
      opener?.focus?.()
    }
  }, [onClose])

  return (
    <div
      className="flag-backdrop"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose()
      }}
    >
      <div
        ref={ref}
        className="flag-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby={titleId}
        tabIndex={-1}
      >
        {children}
      </div>
    </div>
  )
}

/** Comment only. The server knows the passport, the version's code and the student. */
export function FlagDialog({
  version,
  locale,
  onClose,
  onSent,
}: {
  version: number
  locale: Locale
  onClose: () => void
  onSent: () => void
}) {
  const copy = messages[locale]
  const titleId = useId()
  const fieldId = useId()
  const [comment, setComment] = useState('')
  const [touched, setTouched] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [sending, setSending] = useState(false)
  const [sent, setSent] = useState(false)
  const problem = commentProblem(comment, locale)
  const count = cleanComment(comment).length

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setTouched(true)
    setError(null)
    if (problem) return
    setSending(true)
    try {
      const token = await readAccessToken()
      if (!token) {
        setError(copy.signInRequired)
        return
      }
      await createFlag(token, version, comment)
      setSent(true)
      onSent()
    } catch (err) {
      const code = err instanceof FlagRequestError ? err.code : 'error'
      const wait = err instanceof FlagRequestError ? err.retryAfter : null
      setError(explainFlagError(code, locale, wait))
    } finally {
      setSending(false)
    }
  }

  return (
    <Modal titleId={titleId} onClose={onClose}>
      <h2 id={titleId}>
        {copy.flagDialogTitle.replace('{version}', String(version))}
      </h2>
      {sent ? (
        <>
          <p role="status">{copy.flagSent}</p>
          <div className="flag-modal-actions">
            <button type="button" className="flag-button" onClick={onClose}>
              {copy.flagClose}
            </button>
          </div>
        </>
      ) : (
        <form onSubmit={(event) => void onSubmit(event)} noValidate>
          <label htmlFor={fieldId}>{copy.flagCommentLabel}</label>
          <textarea
            id={fieldId}
            rows={5}
            value={comment}
            maxLength={COMMENT_MAX + 200}
            aria-invalid={touched && problem !== null}
            aria-describedby={`${fieldId}-hint`}
            onChange={(event) => setComment(event.target.value)}
            onBlur={() => setTouched(true)}
          />
          <p id={`${fieldId}-hint`} className="flag-hint">
            {copy.flagCommentHint.replace('{count}', String(count))}
          </p>
          {touched && problem ? (
            <p className="flag-error" role="alert">
              {problem}
            </p>
          ) : null}
          {error ? (
            <p className="flag-error" role="alert">
              {error}
            </p>
          ) : null}
          <div className="flag-modal-actions">
            <button
              type="button"
              className="flag-button ghost"
              onClick={onClose}
            >
              {copy.flagCancel}
            </button>
            <button type="submit" className="flag-button" disabled={sending}>
              {sending ? copy.flagSending : copy.flagSubmit}
            </button>
          </div>
        </form>
      )}
    </Modal>
  )
}

/** The status of a flag on a version. Opens the comment, the reply and the dates. */
export function FlagBadge({
  flag,
  locale,
  onOpened,
}: {
  flag: StudentFlag
  locale: Locale
  onOpened: () => void
}) {
  const copy = messages[locale]
  const [open, setOpen] = useState(false)
  const label = copy.flagBadgeLabel
    .replace('{version}', String(flag.version))
    .replace('{status}', copy.flagStatuses[flag.status])

  return (
    <>
      <button
        type="button"
        className={`flag-badge ${flag.status}`}
        aria-label={label}
        aria-haspopup="dialog"
        onClick={() => {
          setOpen(true)
          if (flag.unread) onOpened()
        }}
      >
        {flag.unread ? (
          <i className="unread-dot" role="img" aria-label={copy.newReply} />
        ) : null}
        {copy.flagStatuses[flag.status]}
      </button>
      {open ? (
        <FlagDetails
          flag={flag}
          locale={locale}
          onClose={() => setOpen(false)}
        />
      ) : null}
    </>
  )
}

function FlagDetails({
  flag,
  locale,
  onClose,
}: {
  flag: StudentFlag
  locale: Locale
  onClose: () => void
}) {
  const copy = messages[locale]
  const titleId = useId()
  return (
    <Modal titleId={titleId} onClose={onClose}>
      <h2 id={titleId}>
        {copy.flagDetailsTitle.replace('{version}', String(flag.version))}
      </h2>
      <p className={`flag-state ${flag.status}`}>
        {copy.flagStatuses[flag.status]}
      </p>
      <FlagEntry flag={flag} locale={locale} />
      <div className="flag-modal-actions">
        <button type="button" className="flag-button" onClick={onClose}>
          {copy.flagClose}
        </button>
      </div>
    </Modal>
  )
}

function FlagEntry({ flag, locale }: { flag: StudentFlag; locale: Locale }) {
  const copy = messages[locale]
  return (
    <dl className="flag-entry">
      <dt>{copy.flagYourComment}</dt>
      <dd>
        {flag.comment}
        <span className="flag-date">
          {copy.flagSentOn.replace('{date}', dateText(flag.created_at, locale))}
        </span>
      </dd>
      <dt>{copy.flagReplyTitle}</dt>
      <dd>
        {flag.status === 'open'
          ? copy.flagNoReply
          : flag.admin_note || copy.flagStatuses[flag.status]}
        {flag.resolved_at ? (
          <span className="flag-date">
            {copy.flagAnsweredOn.replace(
              '{date}',
              dateText(flag.resolved_at, locale),
            )}
          </span>
        ) : null}
      </dd>
    </dl>
  )
}

/** "My flags": a link with an unread dot that opens the list. Opening marks replies seen. */
export function MyFlags({
  flags,
  unread,
  failed,
  locale,
  onOpened,
}: {
  flags: StudentFlag[]
  unread: number
  failed: boolean
  locale: Locale
  onOpened: () => void
}) {
  const copy = messages[locale]
  const [open, setOpen] = useState(false)
  const titleId = useId()

  return (
    <>
      <button
        type="button"
        className="my-flags-link"
        aria-haspopup="dialog"
        onClick={() => {
          setOpen(true)
          if (unread > 0) onOpened()
        }}
      >
        {copy.myFlags}
        {unread > 0 ? (
          <i className="unread-dot" role="img" aria-label={copy.newReply} />
        ) : null}
      </button>
      {open ? (
        <Modal titleId={titleId} onClose={() => setOpen(false)}>
          <h2 id={titleId}>{copy.myFlagsTitle}</h2>
          {failed ? (
            <p className="flag-error" role="alert">
              {copy.flagLoadError}
            </p>
          ) : null}
          {flags.length === 0 && !failed ? (
            <p role="status">{copy.myFlagsEmpty}</p>
          ) : (
            <ul className="flag-list">
              {flags.map((flag) => (
                <li key={flag.id}>
                  <p className="flag-list-head">
                    <strong>
                      {copy.versionLabel} {flag.version}
                    </strong>
                    <span className={`flag-state ${flag.status}`}>
                      {copy.flagStatuses[flag.status]}
                    </span>
                  </p>
                  <FlagEntry flag={flag} locale={locale} />
                </li>
              ))}
            </ul>
          )}
          <div className="flag-modal-actions">
            <button
              type="button"
              className="flag-button"
              onClick={() => setOpen(false)}
            >
              {copy.flagClose}
            </button>
          </div>
        </Modal>
      ) : null}
    </>
  )
}
