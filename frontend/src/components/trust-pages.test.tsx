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
    'shows the disclaimer and links in %s',
    (locale) => {
      render(<SiteFooter locale={locale} />)
      const copy = trust[locale]
      expect(screen.getByText(copy.disclaimer)).toBeTruthy()
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

  it('does not link to the private repository', () => {
    render(<SiteFooter locale="en" />)
    const hrefs = screen.getAllByRole('link').map((a) => a.getAttribute('href'))
    expect(hrefs.some((href) => href?.includes('github.com'))).toBe(false)
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

  it('renders in Georgian', () => {
    state.locale = 'ka'
    render(<InfoPage page="privacy" />)
    expect(screen.getByRole('heading', { level: 1 }).textContent).toBe(
      trust.ka.pages.privacy.title,
    )
  })

  it('points removal requests to the team when no contact email is set', () => {
    render(<InfoPage page="privacy" />)
    expect(screen.getByText(trust.en.removalWithoutEmail)).toBeTruthy()
    expect(screen.queryByText(/\{removal\}|\{email\}/)).toBeNull()
  })
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
