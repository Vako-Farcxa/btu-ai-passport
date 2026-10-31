import { apiBaseUrl } from '@/lib/api/base-url'
import { RateLimitedError, retryAfterOf } from '@/lib/api/rate-limit'
import {
  VerifyInputError,
  verifyResultSchema,
  type VerifyResult,
} from '@/lib/api/types'

export async function postVerify(code: string): Promise<VerifyResult> {
  const base = apiBaseUrl()
  const response = await fetch(`${base}/verify`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code }),
  })
  if (response.status === 429)
    throw new RateLimitedError(retryAfterOf(response))
  const payload: unknown = await response.json()
  if (response.status === 422) {
    throw new VerifyInputError()
  }
  return verifyResultSchema.parse(payload)
}
