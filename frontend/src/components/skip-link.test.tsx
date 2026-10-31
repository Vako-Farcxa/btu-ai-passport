import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { SkipLink } from '@/components/skip-link'
import { messages } from '@/i18n/messages'

const locale = vi.hoisted(() => ({ current: 'en' as 'en' | 'ka' }))
vi.mock('@/i18n/use-locale', () => ({
  useLocale: () => [locale.current, () => undefined],
}))

afterEach(cleanup)

describe('skip link', () => {
  it.each(['en', 'ka'] as const)(
    'points at the main landmark in %s',
    (code) => {
      locale.current = code
      render(<SkipLink />)
      const link = screen.getByRole('link', {
        name: messages[code].skipToContent,
      })
      expect(link).toHaveAttribute('href', '#main')
      expect(link).toHaveClass('skip-link')
    },
  )
})
