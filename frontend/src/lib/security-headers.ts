type Env = Record<string, string | undefined>

export interface HeaderEntry {
  key: string
  value: string
}

/** The scheme and host of a URL (no path), or null when it is empty or not a URL. */
function originOf(value: string | undefined): string | null {
  const text = value?.trim()
  if (!text) return null
  try {
    const url = new URL(text)
    return url.origin === 'null' ? null : url.origin
  } catch {
    return null
  }
}

/**
 * The Content-Security-Policy for the whole site.
 *
 * - Pages are prerendered and cached (cacheComponents), so a per-request nonce is not
 *   possible. Next.js writes small inline scripts into every page, hence 'unsafe-inline' for
 *   scripts. Everything else stays tight: no eval in production, no plugins, no framing, no
 *   foreign base URL, no foreign form targets, and fetches only to this site, the API and
 *   Supabase.
 * - Google sign-in and the Polygonscan links are plain navigations (a redirect and normal
 *   links), which CSP does not restrict, so they need no entry here.
 */
export function contentSecurityPolicy(env: Env): string {
  const isDev = env.NODE_ENV === 'development'
  const apiOrigin = originOf(env.NEXT_PUBLIC_API_URL)
  const supabaseOrigin = originOf(env.NEXT_PUBLIC_SUPABASE_URL)

  const connect = ["'self'"]
  if (apiOrigin) connect.push(apiOrigin)
  if (supabaseOrigin) connect.push(supabaseOrigin)
  // Local dev: hot reload runs over a websocket.
  if (isDev) connect.push('ws://localhost:*', 'ws://127.0.0.1:*')

  const directives: string[] = [
    "default-src 'self'",
    `script-src 'self' 'unsafe-inline'${isDev ? " 'unsafe-eval'" : ''}`,
    "style-src 'self' 'unsafe-inline'",
    "img-src 'self' data: blob:",
    "font-src 'self' data:",
    `connect-src ${connect.join(' ')}`,
    "object-src 'none'",
    "frame-src 'none'",
    "worker-src 'self' blob:",
    "manifest-src 'self'",
    "base-uri 'self'",
    "form-action 'self'",
    "frame-ancestors 'none'",
  ]
  // Only when the API is https too, so a local http API still works in a production build.
  if (!isDev && (apiOrigin === null || apiOrigin.startsWith('https:'))) {
    directives.push('upgrade-insecure-requests')
  }
  return directives.join('; ')
}

/**
 * Headers for every response. CSP_REPORT_ONLY=1 sends the policy as report-only (browsers
 * log violations in the console but block nothing), a switch to use if a policy ever breaks
 * the live site, without a code change.
 */
export function securityHeaders(env: Env): HeaderEntry[] {
  const reportOnly = env.CSP_REPORT_ONLY === '1'
  return [
    {
      key: reportOnly
        ? 'Content-Security-Policy-Report-Only'
        : 'Content-Security-Policy',
      value: contentSecurityPolicy(env),
    },
    {
      key: 'Strict-Transport-Security',
      value: 'max-age=31536000; includeSubDomains',
    },
    { key: 'X-Content-Type-Options', value: 'nosniff' },
    // The verify address carries ?code=..., so other sites only ever learn the origin.
    { key: 'Referrer-Policy', value: 'strict-origin-when-cross-origin' },
    {
      key: 'Permissions-Policy',
      value:
        'camera=(), microphone=(), geolocation=(), payment=(), usb=(), browsing-topics=()',
    },
    // Old browsers ignore frame-ancestors, they read this one.
    { key: 'X-Frame-Options', value: 'DENY' },
    { key: 'Cross-Origin-Opener-Policy', value: 'same-origin' },
  ]
}
