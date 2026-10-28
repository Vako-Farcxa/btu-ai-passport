import { z } from 'zod'

import type { Locale } from '@/i18n/messages'
import { messages } from '@/i18n/messages'

export const COMMENT_MIN = 10
export const COMMENT_MAX = 500

export const flagStatusSchema = z.enum(['open', 'resolved', 'dismissed'])
export type FlagStatus = z.infer<typeof flagStatusSchema>

export const studentFlagSchema = z.object({
  id: z.string(),
  version: z.number().int().positive(),
  comment: z.string(),
  status: flagStatusSchema,
  admin_note: z.string(),
  created_at: z.string(),
  resolved_at: z.string().nullable(),
  unread: z.boolean(),
})

export const studentFlagListSchema = z.object({
  flags: z.array(studentFlagSchema),
  unread: z.number().int().nonnegative(),
})

export type StudentFlag = z.infer<typeof studentFlagSchema>
export type StudentFlagList = z.infer<typeof studentFlagListSchema>

export type FlagErrorCode =
  | 'invalid_comment'
  | 'flag_already_open'
  | 'flag_rate_limited'
  | 'unauthorized'
  | 'domain_not_allowed'
  | 'error'

export class FlagRequestError extends Error {
  readonly code: FlagErrorCode

  constructor(code: FlagErrorCode) {
    super(code)
    this.name = 'FlagRequestError'
    this.code = code
  }
}

/** Trimmed length is what the API checks, so the form counts the same way. */
export function cleanComment(value: string): string {
  return value.normalize('NFC').trim()
}

/** A localized message when the comment is not 10 to 500 characters, else null. */
export function commentProblem(value: string, locale: Locale): string | null {
  const length = cleanComment(value).length
  const copy = messages[locale]
  if (length < COMMENT_MIN) return copy.flagTooShort
  if (length > COMMENT_MAX) return copy.flagTooLong
  return null
}

export function explainFlagError(code: FlagErrorCode, locale: Locale): string {
  const copy = messages[locale]
  if (code === 'invalid_comment') return copy.flagTooShort
  if (code === 'flag_already_open') return copy.flagAlreadyOpen
  if (code === 'flag_rate_limited') return copy.flagRateLimited
  if (code === 'unauthorized') return copy.signInRequired
  if (code === 'domain_not_allowed') return copy.domainNotAllowed
  return copy.flagError
}

function apiBase(): string {
  return process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'
}

function code(value: unknown): FlagErrorCode {
  const found =
    typeof value === 'object' && value !== null
      ? (value as { code?: unknown }).code
      : undefined
  if (
    found === 'invalid_comment' ||
    found === 'flag_already_open' ||
    found === 'flag_rate_limited' ||
    found === 'unauthorized' ||
    found === 'domain_not_allowed'
  ) {
    return found
  }
  return 'error'
}

async function request(
  token: string,
  path: string,
  init?: { method: 'POST'; body?: unknown },
): Promise<unknown> {
  const response = await fetch(`${apiBase()}${path}`, {
    method: init?.method ?? 'GET',
    headers: {
      Authorization: `Bearer ${token}`,
      ...(init?.body === undefined
        ? {}
        : { 'Content-Type': 'application/json' }),
    },
    body: init?.body === undefined ? undefined : JSON.stringify(init.body),
    cache: 'no-store',
  })
  const payload: unknown = await response.json().catch(() => null)
  if (!response.ok) throw new FlagRequestError(code(payload))
  return payload
}

export async function getMyFlags(token: string): Promise<StudentFlagList> {
  return studentFlagListSchema.parse(await request(token, '/me/flags'))
}

export async function markMyFlagsSeen(token: string): Promise<StudentFlagList> {
  return studentFlagListSchema.parse(
    await request(token, '/me/flags/seen', { method: 'POST' }),
  )
}

/** Only the version and the comment go out. The server fills in the IDs and the code. */
export async function createFlag(
  token: string,
  version: number,
  comment: string,
): Promise<StudentFlag> {
  return studentFlagSchema.parse(
    await request(token, '/flags', {
      method: 'POST',
      body: { version, comment: cleanComment(comment) },
    }),
  )
}

/** The newest flag on a version, if any. */
export function flagForVersion(
  flags: StudentFlag[],
  version: number,
): StudentFlag | undefined {
  return flags
    .filter((flag) => flag.version === version)
    .sort((a, b) => b.created_at.localeCompare(a.created_at))[0]
}
