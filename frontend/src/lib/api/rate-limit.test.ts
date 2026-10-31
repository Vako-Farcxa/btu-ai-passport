import { afterEach, describe, expect, it, vi } from 'vitest'

import { fetchAdminFlags, updateAdminFlag } from '@/lib/api/admin'
import { postVerify } from '@/lib/api/client'
import { createFlag, explainFlagError, FlagRequestError } from '@/lib/api/flags'
import {
  downloadPassportPdf,
  explainPassportError,
  getMyPassport,
  PassportRequestError,
} from '@/lib/api/passport'
import {
  isRateLimited,
  parseRetryAfter,
  RateLimitedError,
  rateLimitMessage,
} from '@/lib/api/rate-limit'

vi.mock('@/lib/supabase/client', () => ({
  readAccessToken: async () => 'tok',
}))

afterEach(() => vi.unstubAllGlobals())

function tooMany(retryAfter: string | null = '42', code = 'rate_limited') {
  return {
    ok: false,
    status: 429,
    headers: new Headers(
      retryAfter === null ? {} : { 'Retry-After': retryAfter },
    ),
    json: async () => ({ code }),
  }
}

describe('parseRetryAfter', () => {
  it('reads whole seconds and nothing else', () => {
    expect(parseRetryAfter('42')).toBe(42)
    expect(parseRetryAfter(' 7 ')).toBe(7)
    expect(parseRetryAfter(null)).toBeNull()
    expect(parseRetryAfter('')).toBeNull()
    expect(parseRetryAfter('0')).toBeNull()
    expect(parseRetryAfter('-5')).toBeNull()
    expect(parseRetryAfter('1.5')).toBeNull()
    expect(parseRetryAfter('Wed, 21 Oct 2026 07:28:00 GMT')).toBeNull()
  })

  it('never promises more than an hour', () => {
    expect(parseRetryAfter('999999')).toBe(3600)
  })
})

describe('rateLimitMessage', () => {
  it('is friendly in English and Georgian, with the wait when known', () => {
    expect(rateLimitMessage('en', 42)).toBe(
      'Too many requests. Please wait 42 seconds and try again.',
    )
    expect(rateLimitMessage('ka', 42)).toContain('42')
    expect(rateLimitMessage('ka', 42)).toMatch(/[\u10A0-\u10FF]/)
    expect(rateLimitMessage('en', null)).toMatch(/wait a moment/)
    expect(rateLimitMessage('ka', null)).toMatch(/[\u10A0-\u10FF]/)
    expect(rateLimitMessage('en', 5)).not.toContain('{seconds}')
    expect(rateLimitMessage('ka', 5)).not.toContain('{seconds}')
  })

  it('is the message of the error', () => {
    const error = new RateLimitedError(9)
    expect(error.message).toBe(rateLimitMessage('en', 9))
    expect(error.retryAfter).toBe(9)
    expect(new RateLimitedError(9, 'ka').message).toBe(
      rateLimitMessage('ka', 9),
    )
  })
})

describe('isRateLimited', () => {
  it('is only true for the limiter, not for the flag form hourly cap', () => {
    expect(isRateLimited(new Response(null, { status: 429 }))).toBe(true)
    expect(
      isRateLimited(new Response(null, { status: 429 }), {
        code: 'rate_limited',
      }),
    ).toBe(true)
    expect(
      isRateLimited(new Response(null, { status: 429 }), {
        code: 'flag_rate_limited',
      }),
    ).toBe(false)
    expect(isRateLimited(new Response(null, { status: 500 }))).toBe(false)
  })
})

describe('verify', () => {
  it('turns a 429 into a RateLimitedError with the wait', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(tooMany('30')))
    await expect(postVerify('AAAA-BBBB-CCCC-DDDD')).rejects.toMatchObject({
      name: 'RateLimitedError',
      retryAfter: 30,
    })
  })

  it('copes with a 429 that has no Retry-After header', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(tooMany(null)))
    await expect(postVerify('AAAA-BBBB-CCCC-DDDD')).rejects.toMatchObject({
      retryAfter: null,
    })
  })
})

describe('passport', () => {
  it('reports a 429 on the passport and on the PDF', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(tooMany('12')))
    const error = await getMyPassport('tok').catch((caught: unknown) => caught)
    expect(error).toBeInstanceOf(PassportRequestError)
    expect(error).toMatchObject({ code: 'rate_limited', retryAfter: 12 })
    await expect(downloadPassportPdf('tok', 1, 'en')).rejects.toMatchObject({
      code: 'rate_limited',
      retryAfter: 12,
    })
  })

  it('explains it in both languages', () => {
    expect(explainPassportError('rate_limited', 'en', 12)).toBe(
      rateLimitMessage('en', 12),
    )
    expect(explainPassportError('rate_limited', 'ka', null)).toBe(
      rateLimitMessage('ka', null),
    )
  })
})

describe('flags', () => {
  it('tells the per-minute limit apart from the hourly cap', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(tooMany('20')))
    const error = await createFlag('tok', 1, 'A skill is missing here.').catch(
      (caught: unknown) => caught,
    )
    expect(error).toBeInstanceOf(FlagRequestError)
    expect(error).toMatchObject({ code: 'rate_limited', retryAfter: 20 })

    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(tooMany(null, 'flag_rate_limited')),
    )
    await expect(
      createFlag('tok', 1, 'A skill is missing here.'),
    ).rejects.toMatchObject({ code: 'flag_rate_limited', retryAfter: null })
  })

  it('explains it in both languages', () => {
    expect(explainFlagError('rate_limited', 'en', 20)).toBe(
      rateLimitMessage('en', 20),
    )
    expect(explainFlagError('rate_limited', 'ka', 20)).toBe(
      rateLimitMessage('ka', 20),
    )
  })
})

describe('admin', () => {
  it('turns a 429 into an error the admin pages show as text', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue(tooMany('15')))
    const error = await updateAdminFlag('f1', {
      status: 'resolved',
      admin_note: 'Done.',
    }).catch((caught: unknown) => caught)
    expect(error).toBeInstanceOf(RateLimitedError)
    expect((error as Error).message).toBe(rateLimitMessage('en', 15))
    await expect(fetchAdminFlags()).rejects.toBeInstanceOf(RateLimitedError)
  })
})
