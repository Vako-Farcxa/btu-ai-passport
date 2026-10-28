/** Only same-site paths, so the post-login cookie cannot be used as an open redirect. */
export function safeNext(value: string | undefined): string {
  if (!value) return '/passport'
  let path: string
  try {
    path = decodeURIComponent(value)
  } catch {
    return '/passport'
  }
  if (!path.startsWith('/') || path.startsWith('//') || path.includes('\\')) {
    return '/passport'
  }
  return path
}
