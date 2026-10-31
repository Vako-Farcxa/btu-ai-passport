import { describe, expect, it } from 'vitest'

import {
  isLocale,
  localeForRequest,
  localeFromCookie,
  negotiateLocale,
} from './negotiate'

describe('negotiateLocale', () => {
  it.each([
    ['en-US,en;q=0.9', 'en'],
    ['en', 'en'],
    ['EN-gb', 'en'],
    ['ka', 'ka'],
    ['ka-GE,ka;q=0.9,en;q=0.8', 'ka'],
    ['en;q=0.5, ka;q=0.9', 'ka'],
    ['ka;q=0.2, en;q=0.9', 'en'],
    // The first language the site has: German is skipped, English comes next.
    ['de-DE,de;q=0.9,en;q=0.7', 'en'],
    ['de,ka;q=0.5', 'ka'],
    ['ka;q=0, en', 'en'],
  ] as const)('%s -> %s', (header, expected) => {
    expect(negotiateLocale(header)).toBe(expected)
  })

  it.each([null, undefined, '', '   ', 'fr', 'de-DE,fr;q=0.8', '*', 'kab'])(
    'shows English for %j, never Georgian by accident',
    (header) => {
      expect(negotiateLocale(header)).toBe('en')
    },
  )

  it('reads a joined navigator.languages list the same way', () => {
    expect(negotiateLocale(['de', 'ka', 'en'].join(','))).toBe('ka')
  })
})

describe('the saved choice', () => {
  it('only accepts the two languages', () => {
    expect(isLocale('en')).toBe(true)
    expect(isLocale('ka')).toBe(true)
    expect(isLocale('de')).toBe(false)
    expect(isLocale(undefined)).toBe(false)
    expect(localeFromCookie('ka')).toBe('ka')
    expect(localeFromCookie('xx')).toBeNull()
    expect(localeFromCookie(undefined)).toBeNull()
  })

  it('wins over the browser language, which is the fallback', () => {
    expect(localeForRequest('ka', 'en-US')).toBe('ka')
    expect(localeForRequest('en', 'ka-GE')).toBe('en')
    expect(localeForRequest(undefined, 'ka-GE')).toBe('ka')
    expect(localeForRequest('bogus', 'ka-GE')).toBe('ka')
    expect(localeForRequest(undefined, undefined)).toBe('en')
  })
})
