import {
  VerifyInputError,
  VerifyRateLimitError,
  verifyResultSchema,
  type VerifyResult,
} from '@/lib/api/types'

export async function postVerify(code: string): Promise<VerifyResult> {
  const base = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'
  const response = await fetch(`${base}/verify`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ code }),
  })
  if (response.status === 429) {
    throw new VerifyRateLimitError()
  }
  const payload: unknown = await response.json()
  if (response.status === 422) {
    throw new VerifyInputError()
  }
  return verifyResultSchema.parse(payload)
}
