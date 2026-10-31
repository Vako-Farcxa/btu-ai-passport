import { cleanup, render, screen } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { messages } from '@/i18n/messages'

import { BrandMark } from './book'

vi.mock('@/components/motion', () => ({
  useCoverMotion: () => undefined,
  useOpenBookMotion: () => undefined,
}))

afterEach(cleanup)

describe('BrandMark', () => {
  it.each(['en', 'ka'] as const)(
    'names the home link in %s even when the visible text is hidden by CSS',
    (locale) => {
      render(<BrandMark locale={locale} />)
      const link = screen.getByRole('link', {
        name: messages[locale].universityName,
      })
      expect(link).toHaveAttribute('href', '/')
      expect(link).toHaveAttribute(
        'aria-label',
        messages[locale].universityName,
      )
    },
  )
})
