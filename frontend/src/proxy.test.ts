import { NextRequest } from 'next/server'
import { describe, expect, it } from 'vitest'

import { config, proxy } from './proxy'

function call(
  path: string,
  headers: Record<string, string> = {},
): { rewrite: string | null; redirect: string | null; status: number } {
  const response = proxy(
    new NextRequest(`http://localhost:3000${path}`, { headers }),
  )
  return {
    rewrite: response.headers.get('x-middleware-rewrite'),
    redirect: response.headers.get('location'),
    status: response.status,
  }
}

const path = (url: string | null) => (url ? new URL(url).pathname : null)

describe('proxy', () => {
  it('serves English copies to English browsers and to requests with no language', () => {
    expect(
      path(call('/verify', { 'accept-language': 'en-US,en;q=0.9' }).rewrite),
    ).toBe('/en/verify')
    expect(path(call('/about').rewrite)).toBe('/en/about')
    expect(path(call('/', { 'accept-language': 'fr' }).rewrite)).toBe('/en')
  })

  it('serves Georgian copies to Georgian browsers', () => {
    expect(
      path(call('/', { 'accept-language': 'ka-GE,ka;q=0.9' }).rewrite),
    ).toBe('/ka')
    expect(path(call('/privacy', { 'accept-language': 'ka' }).rewrite)).toBe(
      '/ka/privacy',
    )
  })

  it('lets the saved language choice win over the browser language', () => {
    expect(
      path(
        call('/verify', {
          'accept-language': 'en-US',
          cookie: 'passport_locale=ka',
        }).rewrite,
      ),
    ).toBe('/ka/verify')
    expect(
      path(
        call('/verify', {
          'accept-language': 'ka',
          cookie: 'passport_locale=en',
        }).rewrite,
      ),
    ).toBe('/en/verify')
    expect(
      path(
        call('/verify', {
          'accept-language': 'ka',
          cookie: 'passport_locale=zz',
        }).rewrite,
      ),
    ).toBe('/ka/verify')
  })

  it('keeps deep admin paths and the query string', () => {
    const { rewrite } = call('/admin/students/BTU-AI-000125?tab=x', {
      'accept-language': 'en',
    })
    expect(path(rewrite)).toBe('/en/admin/students/BTU-AI-000125')
    expect(new URL(rewrite as string).search).toBe('?tab=x')
  })

  it('sends an address that already has a language to the clean address', () => {
    const en = call('/en/verify?code=ABCD')
    expect(en.status).toBe(308)
    expect(en.redirect).toBe('http://localhost:3000/verify?code=ABCD')
    expect(call('/ka').redirect).toBe('http://localhost:3000/')
  })

  it('does not treat a page that merely starts with the letters as a language', () => {
    expect(path(call('/english').rewrite)).toBe('/en/english')
  })

  it('skips Next internals, files and the auth callback in its matcher', () => {
    const pattern = new RegExp(`^${config.matcher[0]}$`)
    for (const hit of ['/', '/verify', '/admin/students/x', '/en/verify']) {
      expect(pattern.test(hit), hit).toBe(true)
    }
    for (const miss of [
      '/_next/static/chunk.js',
      '/auth/callback',
      '/robots.txt',
      '/sitemap.xml',
      '/icon.svg',
      '/opengraph-image',
      '/opengraph-image-1abc',
      '/twitter-image',
      '/docs/screenshots/home.webp',
    ]) {
      expect(pattern.test(miss), miss).toBe(false)
    }
  })
})
