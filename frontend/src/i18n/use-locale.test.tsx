import { cleanup, render, screen } from '@testing-library/react'
import { renderToString } from 'react-dom/server'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { LocaleProvider } from '@/components/locale-provider'

import { useLocale } from './use-locale'

function Probe() {
  const [locale] = useLocale()
  return <p data-testid="locale">{locale}</p>
}

afterEach(() => {
  cleanup()
  document.cookie = 'passport_locale=; max-age=0; path=/'
  vi.unstubAllGlobals()
})

describe('useLocale on the server', () => {
  it('renders the language the server picked, so the first paint is not Georgian', () => {
    const html = (locale: 'en' | 'ka') =>
      renderToString(
        <LocaleProvider locale={locale}>
          <Probe />
        </LocaleProvider>,
      )
    expect(html('en')).toContain('>en<')
    expect(html('ka')).toContain('>ka<')
  })

  it('is English when no language was provided', () => {
    expect(renderToString(<Probe />)).toContain('>en<')
  })
})

describe('useLocale in the browser', () => {
  it('prefers the saved choice, then the browser languages in order', () => {
    vi.stubGlobal('navigator', {
      ...window.navigator,
      languages: ['de-DE', 'ka', 'en'],
      language: 'de-DE',
    })
    render(<Probe />)
    expect(screen.getByTestId('locale')).toHaveTextContent('ka')
    cleanup()

    document.cookie = 'passport_locale=en; path=/'
    render(<Probe />)
    expect(screen.getByTestId('locale')).toHaveTextContent('en')
  })

  it('shows English for a browser with no Georgian or English at all', () => {
    vi.stubGlobal('navigator', {
      ...window.navigator,
      languages: ['fr-FR'],
      language: 'fr-FR',
    })
    render(<Probe />)
    expect(screen.getByTestId('locale')).toHaveTextContent('en')
  })
})
