import { afterEach, describe, expect, it, vi } from 'vitest'

import { messages } from '@/i18n/messages'
import {
  commentProblem,
  createFlag,
  explainFlagError,
  flagForVersion,
  getMyFlags,
  markMyFlagsSeen,
  type StudentFlag,
} from '@/lib/api/flags'

afterEach(() => vi.unstubAllGlobals())

const flag = (over: Partial<StudentFlag> = {}): StudentFlag => ({
  id: 'f1',
  version: 2,
  comment: 'A skill is missing here.',
  status: 'open',
  admin_note: '',
  created_at: '2026-10-28T10:00:00Z',
  resolved_at: null,
  unread: false,
  ...over,
})

describe('commentProblem', () => {
  it('counts the trimmed text, 10 to 500', () => {
    expect(commentProblem('short', 'en')).toBe(messages.en.flagTooShort)
    expect(commentProblem('   123456789   ', 'en')).toBe(
      messages.en.flagTooShort,
    )
    expect(commentProblem('1234567890', 'en')).toBeNull()
    expect(commentProblem('x'.repeat(500), 'en')).toBeNull()
    expect(commentProblem('x'.repeat(501), 'en')).toBe(messages.en.flagTooLong)
    expect(commentProblem('', 'ka')).toBe(messages.ka.flagTooShort)
  })
})

describe('explainFlagError', () => {
  it('is localized', () => {
    expect(explainFlagError('flag_already_open', 'en')).toBe(
      messages.en.flagAlreadyOpen,
    )
    expect(explainFlagError('flag_rate_limited', 'ka')).toBe(
      messages.ka.flagRateLimited,
    )
    expect(explainFlagError('error', 'en')).toBe(messages.en.flagError)
  })
})

describe('flagForVersion', () => {
  it('picks the newest flag of that version', () => {
    const older = flag({ id: 'old', created_at: '2026-10-01T00:00:00Z' })
    const newer = flag({ id: 'new' })
    expect(flagForVersion([older, newer], 2)?.id).toBe('new')
    expect(flagForVersion([older, newer], 1)).toBeUndefined()
  })
})

describe('requests', () => {
  it('sends only the version and the trimmed comment, never ids', async () => {
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => flag(),
    })
    vi.stubGlobal('fetch', fetchMock)
    await createFlag('tok', 2, '  A skill is missing here.  ')
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toMatch(/\/flags$/)
    expect(init.method).toBe('POST')
    expect(JSON.parse(init.body as string)).toEqual({
      version: 2,
      comment: 'A skill is missing here.',
    })
    expect((init.headers as Record<string, string>).Authorization).toBe(
      'Bearer tok',
    )
  })

  it('maps API error codes', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue({
        ok: false,
        status: 409,
        json: async () => ({ code: 'flag_already_open' }),
      }),
    )
    await expect(
      createFlag('tok', 2, 'long enough text'),
    ).rejects.toMatchObject({ code: 'flag_already_open' })
  })

  it('reads the list and marks it seen', async () => {
    const body = { flags: [flag({ unread: true })], unread: 1 }
    const fetchMock = vi
      .fn()
      .mockResolvedValue({ ok: true, json: async () => body })
    vi.stubGlobal('fetch', fetchMock)
    expect((await getMyFlags('tok')).unread).toBe(1)
    await markMyFlagsSeen('tok')
    const [url, init] = fetchMock.mock.calls[1] as [string, RequestInit]
    expect(url).toMatch(/\/me\/flags\/seen$/)
    expect(init.method).toBe('POST')
  })
})

describe('flag copy', () => {
  it('has the same keys in English and Georgian, none empty', () => {
    const keys = (obj: object) => Object.keys(obj).sort()
    expect(keys(messages.ka)).toEqual(keys(messages.en))
    expect(keys(messages.ka.flagStatuses)).toEqual(
      keys(messages.en.flagStatuses),
    )
    for (const locale of ['en', 'ka'] as const) {
      const copy = messages[locale]
      for (const [key, value] of Object.entries(copy)) {
        if (key.startsWith('flag') || key.startsWith('myFlags')) {
          expect(JSON.stringify(value)).not.toBe('""')
        }
      }
    }
  })
})
