import { cleanup, render, screen, within } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { InfoPage } from '@/components/info-page'
import { SiteFooter } from '@/components/site-footer'
import { StatusPage } from '@/components/status-page'
import { trust } from '@/i18n/trust'

const state = vi.hoisted(() => ({ locale: 'en' as 'en' | 'ka' }))

vi.mock('@/i18n/use-locale', () => ({
  useLocale: () => [state.locale, () => undefined],
}))
vi.mock('@/components/motion', () => ({
  useOpenBookMotion: () => undefined,
  useCoverMotion: () => undefined,
}))

afterEach(() => {
  cleanup()
  state.locale = 'en'
})

describe('site footer', () => {
  it.each(['en', 'ka'] as const)(
    'shows the project line, team and links in %s',
    (locale) => {
      render(<SiteFooter locale={locale} />)
      const copy = trust[locale]
      expect(screen.getByText(copy.projectLine)).toBeTruthy()
      expect(screen.getByText(copy.team, { exact: false })).toBeTruthy()
      expect(
        screen.getByRole('link', { name: copy.navAbout }).getAttribute('href'),
      ).toBe('/about')
      expect(
        screen
          .getByRole('link', { name: copy.navPrivacy })
          .getAttribute('href'),
      ).toBe('/privacy')
      expect(
        screen.getByRole('link', { name: copy.navTerms }).getAttribute('href'),
      ).toBe('/terms')
    },
  )

  it('links to the public repository and opens it safely', () => {
    render(<SiteFooter locale="en" />)
    const link = screen.getByRole('link', { name: 'GitHub' })
    expect(link.getAttribute('href')).toBe(
      'https://github.com/Vako-Farcxa/btu-ai-passport',
    )
    expect(link.getAttribute('rel')).toContain('noopener')
  })
})

describe('info pages', () => {
  it.each(['about', 'privacy', 'terms'] as const)(
    'renders %s with every section and the footer',
    (page) => {
      render(<InfoPage page={page} />)
      const copy = trust.en.pages[page]
      expect(screen.getByRole('heading', { level: 1 }).textContent).toBe(
        copy.title,
      )
      for (const section of copy.sections) {
        expect(
          screen.getByRole('heading', { name: section.heading }),
        ).toBeTruthy()
      }
      expect(screen.getByRole('contentinfo')).toBeTruthy()
    },
  )

  it('says anchoring is on a test network on About', () => {
    render(<InfoPage page="about" />)
    const article = screen.getByTestId('info-about')
    expect(
      within(article).getAllByText(/Polygon Amoy test network/).length,
    ).toBeGreaterThan(0)
  })

  it('links to the repository from About', () => {
    render(<InfoPage page="about" />)
    const link = screen
      .getAllByRole('link')
      .find((a) => a.textContent === 'github.com/Vako-Farcxa/btu-ai-passport')
    expect(link?.getAttribute('href')).toBe(
      'https://github.com/Vako-Farcxa/btu-ai-passport',
    )
  })

  it('renders in Georgian', () => {
    state.locale = 'ka'
    render(<InfoPage page="privacy" />)
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe(
      trust.ka.pages.privacy.title,
    )
  })
})

describe('privacy page', () => {
  const EMAIL = 'vpartskhaladze@gmail.com'

  it.each(['en', 'ka'] as const)(
    'has the same sections in %s and links the contact email with mailto',
    (locale) => {
      state.locale = locale
      render(<InfoPage page="privacy" />)
      const copy = trust[locale].pages.privacy
      expect(copy.sections).toHaveLength(trust.en.pages.privacy.sections.length)
      const link = screen.getByRole('link', { name: EMAIL })
      expect(link.getAttribute('href')).toBe(`mailto:${EMAIL}`)
      // A mail link opens the mail app: no new tab.
      expect(link.getAttribute('target')).toBeNull()
    },
  )

  it('says what is shown, where it is stored, and that the hashes hold no personal data', () => {
    render(<InfoPage page="privacy" />)
    const article = screen.getByTestId('info-privacy')
    const text = article.textContent ?? ''
    expect(text).toContain('holder name')
    expect(text).toContain('test sheet')
    expect(text).toContain('fictional')
    expect(text).toContain('Google')
    expect(text).toContain('only your email address and your name')
    expect(text).toContain('Supabase')
    expect(text).toContain('Polygon Amoy')
    expect(text).toMatch(/contains no name, email, skill/)
    expect(text).toMatch(/no analytics, no advertising and no tracking/)
  })

  it.each(['en', 'ka'] as const)(
    'carries no "demo" or "not official" disclaimer in %s',
    (locale) => {
      const copy = trust[locale].pages.privacy
      const text = JSON.stringify(copy)
      expect(text).not.toMatch(/not an official|official BTU|hackathon/i)
      expect(text).not.toMatch(/ოფიციალური|ჰაკათონ/)
      expect(copy.intro).not.toMatch(/demo|დემო/i)
    },
  )
})

describe('status pages', () => {
  it('shows the 404 page with a way home', () => {
    render(<StatusPage kind="not_found" />)
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe(
      trust.en.notFoundTitle,
    )
    expect(
      screen
        .getByRole('link', { name: trust.en.backHome })
        .getAttribute('href'),
    ).toBe('/')
  })

  it('shows the error page and retries', () => {
    const retry = vi.fn()
    render(<StatusPage kind="error" onRetry={retry} />)
    screen.getByRole('button', { name: new RegExp(trust.en.tryAgain) }).click()
    expect(retry).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('alert').textContent).toBe(trust.en.errorBody)
  })
})
