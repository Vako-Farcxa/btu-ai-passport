import { cleanup, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { messages } from '@/i18n/messages'

import PassportPage from './page'

vi.mock('@/components/motion', () => ({
  useSkillMotion: () => undefined,
  useCoverMotion: () => undefined,
  useOpenBookMotion: () => undefined,
}))
vi.mock('@/i18n/use-locale', () => ({
  useLocale: () => ['en', () => undefined],
}))
vi.mock('@/lib/supabase/client', () => ({
  readAccessToken: async () => 'tok',
  signInWithGoogle: vi.fn(),
}))
vi.mock('@/lib/api/use-passport', () => ({
  useMyPassport: () => ({
    kind: 'ready',
    body: {
      passport: {
        passport_id: 'BTU-ABC',
        versions: [
          {
            version: 2,
            issued_at: '2026-10-28T10:00:00Z',
            is_current: true,
            holder_name: 'Nino Beridze',
            verification_code: 'AAAA-BBBB-CCCC-DDDD',
            skills: [],
            anchor: {
              status: 'confirmed',
              tx_url: 'https://amoy.polygonscan.com/tx/0xabc',
            },
          },
          {
            version: 1,
            issued_at: '2026-10-01T10:00:00Z',
            is_current: false,
            holder_name: 'Nino Beridze',
            verification_code: 'EEEE-FFFF-GGGG-HHHH',
            skills: [],
            anchor: { status: 'pending', tx_url: null },
          },
        ],
      },
    },
  }),
}))
vi.mock('@/lib/api/use-flags', () => ({
  useMyFlags: () => ({
    flags: [
      {
        id: 'f1',
        version: 2,
        comment: 'A skill is missing here.',
        status: 'resolved',
        admin_note: 'Fixed.',
        created_at: '2026-10-28T10:00:00Z',
        resolved_at: '2026-10-29T10:00:00Z',
        unread: true,
      },
    ],
    unread: 1,
    failed: false,
    reload: async () => undefined,
    markSeen: async () => undefined,
  }),
}))

afterEach(cleanup)

describe('passport page layout', () => {
  it('puts My flags above the cards, with the status badge across the card header', () => {
    render(<PassportPage />)
    const copy = messages.en
    const myFlags = screen.getByRole('button', {
      name: new RegExp(copy.myFlags),
    })
    const cards = screen
      .getAllByRole('listitem')
      .filter((li) => li.classList.contains('version-card'))
    expect(cards).toHaveLength(2)
    // My flags is on the line above the first card.
    expect(cards[0]).toBeDefined()
    expect(
      myFlags.compareDocumentPosition(cards[0] as HTMLElement) &
        Node.DOCUMENT_POSITION_FOLLOWING,
    ).toBeTruthy()
    // The badge sits in the card header, after the title block (opposite side).
    const head = (cards[0] as HTMLElement).querySelector(
      '.version-head',
    ) as HTMLElement
    expect(head.children[0]).toHaveClass('version-title')
    expect(head.children[1]).toHaveClass('flag-badge')
    // The unread dot is on My flags.
    expect(within(myFlags).getByRole('img')).toBeInTheDocument()
  })

  it('puts Copy share link next to the version number', () => {
    render(<PassportPage />)
    const cards = document.querySelectorAll('.version-card')
    for (const card of cards) {
      const title = card.querySelector('.version-title') as HTMLElement
      expect(title.querySelector('h3')).not.toBeNull()
      expect(
        within(title).getByRole('button', { name: /./ }),
      ).toBeInTheDocument()
    }
  })

  it('keeps the PDF and transaction buttons in one aligned row', () => {
    render(<PassportPage />)
    const actions = document.querySelectorAll('.version-actions')
    const first = actions[0] as HTMLElement
    const pdf = first.querySelector('.primary-button')
    const tx = first.querySelector('a.action-button')
    expect(pdf).not.toBeNull()
    expect(tx).toHaveAttribute('href', 'https://amoy.polygonscan.com/tx/0xabc')
    expect(pdf?.parentElement).toBe(tx?.parentElement)
    // No transaction link outside the actions row.
    expect(document.querySelectorAll('.transaction-link')).toHaveLength(0)
  })

  it('offers Flag an issue unless the version has an open flag', () => {
    render(<PassportPage />)
    const labels = screen
      .getAllByRole('button')
      .map((button) => button.textContent)
      .filter((text) => text === messages.en.flagIssue)
    // Both versions: v2 is resolved (can flag again), v1 has none.
    expect(labels).toHaveLength(2)
  })
})
