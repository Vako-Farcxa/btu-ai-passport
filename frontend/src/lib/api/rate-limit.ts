import { messages, type Locale } from '@/i18n/messages'

const MAX_WAIT_SECONDS = 3600

/**
 * Seconds from a Retry-After header. The API always sends whole seconds, so a date or
 * anything odd gives null and the message just says "a moment".
 */
export function parseRetryAfter(value: string | null): number | null {
  if (value === null || !/^\d{1,6}$/.test(value.trim())) return null
  const seconds = Number(value.trim())
  if (seconds < 1) return null
  return Math.min(seconds, MAX_WAIT_SECONDS)
}

/** The friendly "slow down" sentence, in the reader's language. */
export function rateLimitMessage(
  locale: Locale,
  retryAfter: number | null,
): string {
  const copy = messages[locale]
  if (retryAfter === null) return copy.rateLimitedSoon
  return copy.rateLimited.replace('{seconds}', String(retryAfter))
}

/** The API answered 429: too many requests from this address or account. */
export class RateLimitedError extends Error {
  readonly retryAfter: number | null

  constructor(retryAfter: number | null, locale: Locale = 'en') {
    super(rateLimitMessage(locale, retryAfter))
    this.name = 'RateLimitedError'
    this.retryAfter = retryAfter
  }
}

/**
 * True for the generic 429 from the rate limiter. The flag form's own hourly cap also
 * answers 429 but with its own code and its own message, so it is left to that form.
 */
export function isRateLimited(response: Response, payload?: unknown): boolean {
  if (response.status !== 429) return false
  const code =
    typeof payload === 'object' && payload !== null && 'code' in payload
      ? payload.code
      : null
  return code !== 'flag_rate_limited'
}

export function retryAfterOf(response: Response): number | null {
  return parseRetryAfter(response.headers.get('Retry-After'))
}
