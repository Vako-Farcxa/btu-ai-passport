import { apiBaseUrl } from '@/lib/api/base-url'
import { messages, type Locale } from '@/i18n/messages'
import { formatIssuedDate } from '@/lib/api/verify'
import {
  passportResponseSchema,
  type PassportResponse,
  type PassportVersion,
} from '@/lib/api/types'

export type { PassportResponse } from '@/lib/api/types'

export type PassportErrorCode =
  | 'domain_not_allowed'
  | 'unauthorized'
  | 'pdf_not_ready'
  | 'passport_revoked'
  | 'version_revoked'
  | 'error'

/** What a 403 means: the API sends a code for a revoked passport or version. */
function forbiddenCode(payload: unknown): PassportErrorCode {
  const code =
    typeof payload === 'object' && payload !== null && 'code' in payload
      ? payload.code
      : null
  if (code === 'passport_revoked' || code === 'version_revoked') return code
  return 'domain_not_allowed'
}

export class PassportRequestError extends Error {
  readonly code: PassportErrorCode

  constructor(code: PassportErrorCode) {
    super(code)
    this.name = 'PassportRequestError'
    this.code = code
  }
}

export function explainPassportError(
  code: PassportErrorCode,
  locale: Locale,
): string {
  const copy = messages[locale]
  if (code === 'domain_not_allowed') return copy.domainNotAllowed
  if (code === 'unauthorized') return copy.signInRequired
  if (code === 'pdf_not_ready') return copy.pdfNotReady
  if (code === 'passport_revoked') return copy.passportRevoked
  if (code === 'version_revoked') return copy.versionRevokedPdf
  return copy.passportError
}

export function passportPdfPath(version: number, lang: Locale): string {
  return `/me/passport/versions/${version}/pdf?lang=${lang}`
}

export async function downloadPassportPdf(
  token: string,
  version: number,
  lang: Locale,
): Promise<Blob> {
  const base = apiBaseUrl()
  const response = await fetch(`${base}${passportPdfPath(version, lang)}`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: 'no-store',
  })
  if (response.status === 409) throw new PassportRequestError('pdf_not_ready')
  if (response.status === 403) {
    const payload: unknown = await response.json().catch(() => null)
    throw new PassportRequestError(forbiddenCode(payload))
  }
  if (response.status === 401) throw new PassportRequestError('unauthorized')
  if (!response.ok) throw new PassportRequestError('error')
  return response.blob()
}

export function orderedVersions(body: PassportResponse): PassportVersion[] {
  if (body.passport === null) return []
  return [...body.passport.versions].sort(
    (left, right) => right.version - left.version,
  )
}

export function renderPassportLines(
  body: PassportResponse,
  locale: Locale,
): string[] {
  const copy = messages[locale]
  if (body.passport === null) return [copy.emptyPassport]
  const lines = [copy.passportId, body.passport.passport_id, copy.history]
  for (const version of orderedVersions(body)) {
    lines.push(copy.versionLabel, String(version.version))
    if (version.is_current) lines.push(copy.currentVersion)
    if (version.revoked_at) lines.push(copy.versionRevokedBadge)
    lines.push(
      version.holder_name,
      copy.verificationCode,
      version.verification_code,
    )
    for (const skill of version.skills) {
      lines.push(
        skill.skill,
        skill.badge,
        skill.awarded_on ?? copy.dateUnavailable,
      )
    }
  }
  return lines
}

export async function getMyPassport(token: string): Promise<PassportResponse> {
  const base = apiBaseUrl()
  const response = await fetch(`${base}/me/passport`, {
    headers: { Authorization: `Bearer ${token}` },
    cache: 'no-store',
  })
  const payload: unknown = await response.json().catch(() => null)
  if (response.status === 403)
    throw new PassportRequestError(forbiddenCode(payload))
  if (response.status === 401) throw new PassportRequestError('unauthorized')
  if (!response.ok) throw new PassportRequestError('error')
  return passportResponseSchema.parse(payload)
}

/** The note under a revoked version. Falls back to a dateless sentence. */
export function revokedVersionNote(
  version: PassportVersion,
  locale: Locale,
): string | null {
  if (!version.revoked_at) return null
  const copy = messages[locale]
  const date = formatIssuedDate(version.revoked_at, locale)
  if (date === null) return copy.versionRevokedPdf
  return copy.versionRevokedNote.replace('{date}', date)
}
