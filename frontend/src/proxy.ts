import { NextResponse, type NextRequest } from 'next/server'

import { isLocale, LOCALE_COOKIE, localeForRequest } from '@/i18n/negotiate'

/**
 * Picks the language of the page before it renders. The pages live under `app/[lang]`
 * (one prerendered copy per language), and this rewrites the clean address (`/verify`) to
 * the right copy (`/en/verify` or `/ka/verify`) from the saved `passport_locale` cookie,
 * else the browser's Accept-Language. The server HTML therefore already has the right
 * `<html lang>` and text, with no flash of the other language and no dynamic rendering.
 *
 * An address that already starts with a language is sent to the clean address, so there is
 * one URL per page.
 */
export function proxy(request: NextRequest) {
  const { pathname } = request.nextUrl
  const first = pathname.split('/')[1] ?? ''

  if (isLocale(first)) {
    const url = request.nextUrl.clone()
    url.pathname = pathname.slice(first.length + 1) || '/'
    return NextResponse.redirect(url, 308)
  }

  const locale = localeForRequest(
    request.cookies.get(LOCALE_COOKIE)?.value,
    request.headers.get('accept-language'),
  )
  const url = request.nextUrl.clone()
  url.pathname = `/${locale}${pathname === '/' ? '' : pathname}`
  // The proxy runs in front of Next.js's page cache, so each request still gets its own copy.
  return NextResponse.rewrite(url)
}

export const config = {
  // Everything except API-like routes, Next internals and files with an extension.
  matcher: [
    '/((?!_next/|auth/|robots\\.txt|sitemap\\.xml|opengraph-image|twitter-image|.*\\.[a-zA-Z0-9]+$).*)',
  ],
}
