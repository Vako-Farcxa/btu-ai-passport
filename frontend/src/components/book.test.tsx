import { cleanup, render, screen } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import path from 'node:path'
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
    'gives the home link its name from the visible text in %s',
    (locale) => {
      render(<BrandMark locale={locale} />)
      const link = screen.getByRole('link', {
        name: messages[locale].universityName,
      })
      expect(link).toHaveAttribute('href', '/')
    },
  )

  it('is not hidden with display: none on phones, which would remove its name', () => {
    const css = readFileSync(
      path.resolve(import.meta.dirname, '../app/book.css'),
      'utf8',
    )
    const phone = css.slice(css.indexOf('@media (max-width: 560px)'))
    const rule = /\.brand-word\s*\{([^}]*)\}/.exec(phone)?.[1] ?? ''
    expect(rule).not.toBe('')
    expect(rule).not.toMatch(/display\s*:\s*none/)
    expect(rule).not.toMatch(/visibility\s*:\s*hidden/)
    // Visually hidden instead: one pixel, clipped, still in the accessibility tree.
    expect(rule).toMatch(/clip-path|clip:/)
  })
})
