const DEFAULT_PATH = '/passport'
// Any origin works here, it only has to be one no real page can have.
const PROBE_ORIGIN = 'https://safe-next.invalid'
// Control characters (tab, newline, ...) and backslash are dropped by browsers while they
// parse a URL, so "/\t/evil.example" or "/\evil.example" can turn into "//evil.example".
// Refuse them instead of trying to clean them.
const FORBIDDEN = /[\u0000-\u001f\u007f-\u009f\\]/

/**
 * Turns the value of the post-login cookie into a same-site path. Anything that is not a
 * plain path on this site becomes the default page, so the cookie cannot be used as an open
 * redirect after a real sign-in.
 */
export function safeNext(value: string | undefined): string {
  if (!value) return DEFAULT_PATH
  let path: string
  try {
    path = decodeURIComponent(value)
  } catch {
    return DEFAULT_PATH
  }
  if (FORBIDDEN.test(path)) return DEFAULT_PATH
  // Exactly one leading slash: "//host" is a network-path reference to another site.
  if (!path.startsWith('/') || path.startsWith('//')) return DEFAULT_PATH
  let url: URL
  try {
    url = new URL(path, PROBE_ORIGIN)
  } catch {
    return DEFAULT_PATH
  }
  if (url.origin !== PROBE_ORIGIN) return DEFAULT_PATH
  const normalized = `${url.pathname}${url.search}${url.hash}`
  // Normalising ("/a/../..") must not produce a "//" start either.
  if (normalized.startsWith('//')) return DEFAULT_PATH
  return normalized
}
