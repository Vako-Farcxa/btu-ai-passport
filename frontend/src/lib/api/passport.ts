import { apiBaseUrl } from '@/lib/api/base-url'
import { messages, type Locale } from '@/i18n/messages'
import {
  passportResponseSchema,
  type PassportResponse,
  type PassportVersion,
} from '@/lib/api/types'

export type { PassportResponse } from '@/lib/api/types'

export type PassportErrorCode =
  'domain_not_allowed' | 'unauthorized' | 'pdf_not_ready' | 'error'

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
  if (response.status === 403)
    throw new PassportRequestError('domain_not_allowed')
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
    throw new PassportRequestError('domain_not_allowed')
  if (response.status === 401) throw new PassportRequestError('unauthorized')
  if (!response.ok) throw new PassportRequestError('error')
  return passportResponseSchema.parse(payload)
}
