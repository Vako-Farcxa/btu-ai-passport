/**
 * Writes a cookie from the browser. Adds Secure whenever the page itself is served over
 * https, so the cookie is never sent over a plain connection. These cookies hold no secrets
 * (a language and a same-site return path) and are read by scripts or by the callback route
 * of this site, so they cannot be HttpOnly.
 */
export function cookieAttributes(maxAgeSeconds: number): string {
  const secure =
    typeof window !== 'undefined' && window.location.protocol === 'https:'
  return `path=/; max-age=${maxAgeSeconds}; SameSite=Lax${secure ? '; Secure' : ''}`
}

export function writeCookie(
  name: string,
  value: string,
  maxAgeSeconds: number,
): void {
  document.cookie = `${name}=${value}; ${cookieAttributes(maxAgeSeconds)}`
}

/** Options for the Supabase session cookies, which scripts must read, so not HttpOnly. */
export function sessionCookieOptions(secure: boolean) {
  return { path: '/', sameSite: 'lax' as const, secure }
}
