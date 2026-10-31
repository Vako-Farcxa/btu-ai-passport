import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { messages } from '@/i18n/messages'
import type { PassportState } from '@/lib/api/use-passport'

import PassportPage from './page'

let locale: 'en' | 'ka' = 'en'
let state: PassportState = { kind: 'loading' }

vi.mock('@/components/motion', () => ({
  useSkillMotion: () => undefined,
  useCoverMotion: () => undefined,
  useOpenBookMotion: () => undefined,
}))
vi.mock('@/i18n/use-locale', () => ({
  useLocale: () => [locale, () => undefined],
}))
vi.mock('@/lib/supabase/client', () => ({
  readAccessToken: async () => 'tok',
  signInWithGoogle: vi.fn(),
}))
vi.mock('@/lib/api/use-passport', () => ({
  useMyPassport: () => state,
}))
vi.mock('@/lib/api/use-flags', () => ({
  useMyFlags: () => ({
    flags: [],
    unread: 0,
    failed: false,
    reload: async () => undefined,
    markSeen: async () => undefined,
  }),
}))

afterEach(() => {
  cleanup()
  locale = 'en'
})

const version = (n: number, code: string, revoked_at: string | null) => ({
  version: n,
  issued_at: '2026-10-28T10:00:00Z',
  is_current: n === 2,
  holder_name: 'Nino Beridze',
  verification_code: code,
  skills: [],
  anchor: {
    status: 'confirmed' as const,
    tx_url: 'https://amoy.polygonscan.com/tx/0xabc',
  },
  revoked_at,
})

describe('passport page for a revoked passport', () => {
  it('shows a friendly message and no passport data in English', () => {
    state = { kind: 'error', code: 'passport_revoked' }
    render(<PassportPage />)
    const panel = screen.getByTestId('passport-revoked')
    expect(panel).toHaveTextContent(messages.en.passportRevokedTitle)
    expect(panel).toHaveTextContent(messages.en.passportRevoked)
    expect(screen.queryByText(messages.en.downloadPdf)).toBeNull()
    expect(screen.queryByText(messages.en.domainNotAllowed)).toBeNull()
    expect(screen.queryByText(messages.en.passportError)).toBeNull()
  })

  it('shows the same message in Georgian', () => {
    locale = 'ka'
    state = { kind: 'error', code: 'passport_revoked' }
    render(<PassportPage />)
    expect(screen.getByTestId('passport-revoked')).toHaveTextContent(
      messages.ka.passportRevoked,
    )
  })

  it('keeps other errors as a plain alert', () => {
    state = { kind: 'error', code: 'domain_not_allowed' }
    render(<PassportPage />)
    expect(screen.queryByTestId('passport-revoked')).toBeNull()
    expect(screen.getByRole('alert')).toHaveTextContent(
      messages.en.domainNotAllowed,
    )
  })
})

describe('passport page with one revoked version', () => {
  it('marks it Revoked and removes its PDF and share link, not the others', () => {
    state = {
      kind: 'ready',
      body: {
        passport: {
          passport_id: 'BTU-ABC',
          versions: [
            version(2, 'AAAA-BBBB-CCCC-DDDD', null),
            version(1, 'EEEE-FFFF-GGGG-HHHH', '2026-10-29T08:30:00Z'),
          ],
        },
      },
    }
    render(<PassportPage />)
    const cards = Array.from(document.querySelectorAll('.version-card'))
    expect(cards).toHaveLength(2)
    const [good, revoked] = cards as HTMLElement[]
    expect(good?.textContent).toContain(messages.en.downloadPdf)
    expect(good?.querySelector('.revoked-badge')).toBeNull()
    expect(revoked?.querySelector('.revoked-badge')).toHaveTextContent(
      messages.en.versionRevokedBadge,
    )
    expect(revoked?.textContent).not.toContain(messages.en.downloadPdf)
    expect(revoked?.textContent).not.toContain(messages.en.copyShareLink)
    expect(screen.getByTestId('version-revoked')).toHaveTextContent(
      '29 Oct 2026',
    )
  })
})
