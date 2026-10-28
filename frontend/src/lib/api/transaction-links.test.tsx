import { cleanup, render } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { VerifyResultCard } from '@/components/verify-result'
import {
  passportResponseSchema,
  verifyResultSchema,
  type VerifyResult,
} from '@/lib/api/types'

vi.mock('@/components/motion', () => ({
  useResultMotion: () => undefined,
  useSkillMotion: () => undefined,
}))

afterEach(cleanup)

const GOOD = 'https://amoy.polygonscan.com/tx/0x' + '11'.repeat(32)
const BAD = [
  'javascript:alert(1)',
  'http://amoy.polygonscan.com/tx/0x' + '11'.repeat(32),
  'https://evil.example/tx/0x' + '11'.repeat(32),
  'https://amoy.polygonscan.com@evil.example/tx/0x' + '11'.repeat(32),
]

function verifyBody(txUrl: string) {
  return {
    outcome: 'valid',
    holder_name: 'Ada',
    version: 1,
    is_latest: true,
    skills: [],
    tx_url: txUrl,
  }
}

function passportBody(txUrl: string | null) {
  return {
    passport: {
      passport_id: 'BTU-X',
      versions: [
        {
          version: 1,
          issued_at: '2026-01-01',
          is_current: true,
          holder_name: 'Ada',
          verification_code: 'ABC',
          skills: [],
          anchor: { status: 'confirmed', tx_url: txUrl },
        },
      ],
    },
  }
}

describe('transaction links from the API', () => {
  it('accepts an Amoy explorer link', () => {
    expect(verifyResultSchema.safeParse(verifyBody(GOOD)).success).toBe(true)
    expect(passportResponseSchema.safeParse(passportBody(GOOD)).success).toBe(
      true,
    )
    expect(passportResponseSchema.safeParse(passportBody(null)).success).toBe(
      true,
    )
  })

  it.each(BAD)('refuses %s in a verify response', (value) => {
    expect(verifyResultSchema.safeParse(verifyBody(value)).success).toBe(false)
  })

  it.each(BAD)('refuses %s in a passport response', (value) => {
    expect(passportResponseSchema.safeParse(passportBody(value)).success).toBe(
      false,
    )
  })

  it.each(BAD)('never renders %s as a link', (value) => {
    // Even if a bad value got past the schema, the card must not link to it.
    const result = { ...verifyBody(value) } as unknown as VerifyResult
    const { container } = render(
      <VerifyResultCard locale="en" result={result} />,
    )
    expect(container.querySelector('a.transaction-link')).toBeNull()
    expect(container.innerHTML).not.toContain('evil.example')
    expect(container.innerHTML).not.toContain('javascript:')
  })

  it('renders the good link', () => {
    const result = verifyResultSchema.parse(verifyBody(GOOD))
    const { container } = render(
      <VerifyResultCard locale="en" result={result} />,
    )
    expect(
      container.querySelector('a.transaction-link')?.getAttribute('href'),
    ).toBe(GOOD)
  })
})
