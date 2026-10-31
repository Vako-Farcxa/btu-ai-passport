import { describe, expect, it, vi } from 'vitest'

import { messages } from '@/i18n/messages'
import { verifyResultSchema } from '@/lib/api/types'
import {
  formatIssuedDate,
  labelsFor,
  newerVersionNotice,
  notFoundNotice,
  pendingNotice,
  presentSkills,
  revokedNotice,
  submitDecision,
} from '@/lib/api/verify'

describe('verify submission', () => {
  it('does not call the API for an empty code and is not not_found', async () => {
    const post = vi.fn()
    const result = await submitDecision('   ', post)
    expect(post).not.toHaveBeenCalled()
    expect(result).toEqual({ kind: 'prompt' })
  })

  it('maps the four outcomes to distinct labels in English and Georgian', () => {
    const codes = ['valid', 'outdated', 'not_found', 'error'] as const
    const english = codes.map((code) => labelsFor(code, 'en'))
    const georgian = codes.map((code) => labelsFor(code, 'ka'))
    expect(new Set(english).size).toBe(4)
    expect(new Set(georgian).size).toBe(4)
    expect(english[1]).toMatch(/outdated version/i)
    expect(georgian[1]).not.toBe(english[1])
  })

  it('keeps skill text returned by the API in both languages', () => {
    const skills = [
      {
        skill: 'მანქანური სწავლება',
        badge: 'ბეჭედი',
        awarded_on: '2025-06-01',
        description: 'აღწერა',
      },
    ]
    expect(presentSkills(skills, 'en')).toEqual(skills)
    expect(presentSkills(skills, 'ka')).toEqual(skills)
  })
})

describe('newer version notice', () => {
  const base = {
    outcome: 'outdated',
    holder_name: 'Nino Beridze',
    version: 1,
    is_latest: false,
    skills: [],
    tx_url: 'https://amoy.polygonscan.com/tx/0x' + '22'.repeat(32),
  }
  const parse = (extra: object) =>
    verifyResultSchema.parse({ ...base, ...extra })

  it('names the newer version and a locale formatted date in English', () => {
    const result = parse({ latest_version: 3, latest_issued_at: '2026-10-28' })
    expect(newerVersionNotice(result, 'en')).toBe(
      'A newer version (v3) of this passport was issued on 28 Oct 2026. Ask the holder for their latest code.',
    )
  })

  it('is written in Georgian with a Georgian date', () => {
    const result = parse({ latest_version: 3, latest_issued_at: '2026-10-28' })
    const note = newerVersionNotice(result, 'ka') ?? ''
    expect(note).toContain('v3')
    expect(note).toContain('2026')
    expect(note).not.toContain('Oct')
    expect(note).not.toContain('newer')
  })

  it('accepts a full timestamp and ignores the time of day', () => {
    expect(formatIssuedDate('2026-10-28T23:30:00Z', 'en')).toBe('28 Oct 2026')
  })

  it('is hidden when an older backend omits the fields', () => {
    expect(newerVersionNotice(parse({}), 'en')).toBeNull()
    expect(newerVersionNotice(parse({ latest_version: null }), 'en')).toBeNull()
  })

  it('formats dates with fixed month names in both languages', () => {
    expect(formatIssuedDate('2025-06-01', 'en')).toBe('1 Jun 2025')
    expect(formatIssuedDate('2025-06-01', 'ka')).toBe('1 ივნ. 2025')
    expect(formatIssuedDate('2026-10-28', 'ka')).toBe('28 ოქტ. 2026')
    expect(formatIssuedDate('2026-02-30', 'en')).toBeNull()
  })

  it('is hidden for a date that does not parse', () => {
    const result = parse({ latest_version: 3, latest_issued_at: 'yesterday' })
    expect(newerVersionNotice(result, 'en')).toBeNull()
  })

  it('is never shown for valid or missing results', () => {
    const valid = verifyResultSchema.parse({
      ...base,
      outcome: 'valid',
      is_latest: true,
    })
    expect(newerVersionNotice(valid, 'en')).toBeNull()
    expect(newerVersionNotice({ outcome: 'not_found' }, 'en')).toBeNull()
  })
})

describe('pending notice', () => {
  it('is null for every other outcome', () => {
    expect(pendingNotice({ outcome: 'error' }, 'en')).toBeNull()
    expect(pendingNotice({ outcome: 'not_found' }, 'ka')).toBeNull()
  })

  it('is the translated sentence for a pending result', () => {
    const result = verifyResultSchema.parse({ outcome: 'pending' })
    expect(pendingNotice(result, 'en')).toBe(messages.en.pendingNotice)
    expect(pendingNotice(result, 'ka')).toBe(messages.ka.pendingNotice)
    expect(messages.ka.pendingNotice).not.toBe(messages.en.pendingNotice)
  })

  it('has the labels the product asked for', () => {
    expect(labelsFor('pending', 'en')).toBe('Pending on-chain confirmation')
    expect(labelsFor('pending', 'ka')).not.toBe(labelsFor('error', 'ka'))
  })

  it('is accepted by the response schema and carries nothing else', () => {
    expect(verifyResultSchema.parse({ outcome: 'pending' })).toEqual({
      outcome: 'pending',
    })
  })
})

describe('revoked notice', () => {
  it('is null for every other outcome', () => {
    expect(revokedNotice({ outcome: 'error' }, 'en')).toBeNull()
    expect(revokedNotice({ outcome: 'not_found' }, 'ka')).toBeNull()
  })

  it('names the date, in both languages', () => {
    const result = verifyResultSchema.parse({
      outcome: 'revoked',
      revoked_at: '2026-10-30T10:00:00+00:00',
    })
    expect(revokedNotice(result, 'en')).toContain('30 Oct 2026')
    expect(revokedNotice(result, 'ka')).toContain('30 ოქტ. 2026')
  })

  it('falls back to a dateless sentence for a missing or broken date', () => {
    for (const revoked_at of [undefined, null, 'not a date']) {
      const result = verifyResultSchema.parse({
        outcome: 'revoked',
        revoked_at,
      })
      expect(revokedNotice(result, 'en')).toBe(messages.en.revokedNoticeNoDate)
    }
  })

  it('has a distinct label from every other outcome', () => {
    for (const locale of ['en', 'ka'] as const) {
      const labels = [
        'valid',
        'outdated',
        'revoked',
        'pending',
        'not_found',
        'error',
      ].map((code) => labelsFor(code as 'valid', locale))
      expect(new Set(labels).size).toBe(6)
    }
  })
})

describe('notFoundNotice', () => {
  it('is only shown for a code that matched nothing', () => {
    expect(
      notFoundNotice(verifyResultSchema.parse({ outcome: 'not_found' }), 'en'),
    ).toBe(messages.en.notFoundNotice)
    expect(
      notFoundNotice(verifyResultSchema.parse({ outcome: 'error' }), 'en'),
    ).toBeNull()
  })
})
