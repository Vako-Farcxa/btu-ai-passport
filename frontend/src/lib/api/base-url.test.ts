import { afterEach, describe, expect, it, vi } from 'vitest'

import { apiBaseUrl } from '@/lib/api/base-url'

afterEach(() => vi.unstubAllEnvs())

describe('apiBaseUrl', () => {
  it('uses the configured address without a trailing slash', () => {
    vi.stubEnv('NEXT_PUBLIC_API_URL', 'https://api.example.com//')
    expect(apiBaseUrl()).toBe('https://api.example.com')
  })

  it('falls back to localhost only outside production', () => {
    vi.stubEnv('NEXT_PUBLIC_API_URL', '')
    vi.stubEnv('NODE_ENV', 'development')
    expect(apiBaseUrl()).toBe('http://localhost:8000')
  })

  it('refuses to guess in production', () => {
    vi.stubEnv('NEXT_PUBLIC_API_URL', '')
    vi.stubEnv('NODE_ENV', 'production')
    expect(() => apiBaseUrl()).toThrow(/NEXT_PUBLIC_API_URL/)
  })
})
