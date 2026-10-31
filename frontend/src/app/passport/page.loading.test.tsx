import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { messages } from '@/i18n/messages'

import PassportPage from './page'

const useMyFlags = vi.fn()

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
  useMyPassport: () => ({ kind: 'loading' }),
}))
vi.mock('@/lib/api/use-flags', () => ({
  useMyFlags: (enabled: boolean) => {
    useMyFlags(enabled)
    return {
      flags: [],
      unread: 0,
      failed: false,
      reload: async () => undefined,
      markSeen: async () => undefined,
    }
  },
}))

afterEach(() => {
  cleanup()
  useMyFlags.mockClear()
})

describe('passport page while loading', () => {
  it('shows placeholder shapes with an accessible status, not a bare line of text', () => {
    render(<PassportPage />)
    const skeleton = screen.getByTestId('passport-skeleton')
    expect(skeleton).toHaveAttribute('aria-busy', 'true')
    expect(screen.getByRole('status')).toHaveTextContent(messages.en.loading)
    // The shapes are decoration for screen readers.
    expect(skeleton.querySelector('.skeleton-block')).toHaveAttribute(
      'aria-hidden',
      'true',
    )
    expect(skeleton.querySelectorAll('.skeleton').length).toBeGreaterThan(0)
  })

  it('asks for the flags at the same time as the passport, not after it', () => {
    render(<PassportPage />)
    // Still loading, yet the flags request is already allowed to start.
    expect(useMyFlags).toHaveBeenCalledWith(true)
    expect(useMyFlags).not.toHaveBeenCalledWith(false)
  })
})
