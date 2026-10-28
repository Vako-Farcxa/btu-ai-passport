const LOCAL_API_URL = 'http://localhost:8000'

/**
 * Where the backend lives. In production the address must be set at build time through
 * NEXT_PUBLIC_API_URL: there is deliberately no localhost fallback there, so a missing
 * variable fails loudly instead of sending real users' requests to a dead address.
 */
export function apiBaseUrl(): string {
  const configured = process.env.NEXT_PUBLIC_API_URL?.trim()
  if (configured) return configured.replace(/\/+$/, '')
  if (process.env.NODE_ENV === 'production') {
    throw new Error('NEXT_PUBLIC_API_URL is not set')
  }
  return LOCAL_API_URL
}
