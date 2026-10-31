import { describe, expect, it } from 'vitest'

import { contentSecurityPolicy, securityHeaders } from '@/lib/security-headers'

const production = {
  NODE_ENV: 'production',
  NEXT_PUBLIC_API_URL: 'https://btu-ai-passport-api-qo4p.onrender.com/',
  NEXT_PUBLIC_SUPABASE_URL: 'https://abcd1234.supabase.co',
}

function directive(policy: string, name: string): string[] {
  const found = policy
    .split('; ')
    .find((part) => part === name || part.startsWith(`${name} `))
  return found ? found.split(' ').slice(1) : []
}

describe('contentSecurityPolicy', () => {
  const policy = contentSecurityPolicy(production)

  it('allows fetches only to this site, the API and Supabase', () => {
    expect(directive(policy, 'connect-src')).toEqual([
      "'self'",
      'https://btu-ai-passport-api-qo4p.onrender.com',
      'https://abcd1234.supabase.co',
    ])
  })

  it('forbids framing, plugins, foreign base URLs and form targets', () => {
    expect(directive(policy, 'frame-ancestors')).toEqual(["'none'"])
    expect(directive(policy, 'object-src')).toEqual(["'none'"])
    expect(directive(policy, 'frame-src')).toEqual(["'none'"])
    expect(directive(policy, 'base-uri')).toEqual(["'self'"])
    expect(directive(policy, 'form-action')).toEqual(["'self'"])
    expect(directive(policy, 'default-src')).toEqual(["'self'"])
  })

  it('never allows eval or remote scripts in production', () => {
    const scripts = directive(policy, 'script-src')
    expect(scripts).toEqual(["'self'", "'unsafe-inline'"])
    expect(policy).not.toContain('unsafe-eval')
    expect(policy).not.toMatch(/\*(?!:)/)
  })

  it('upgrades insecure requests when the API is https', () => {
    expect(policy).toContain('upgrade-insecure-requests')
  })

  it('does not upgrade requests to a local http API', () => {
    const local = contentSecurityPolicy({
      ...production,
      NEXT_PUBLIC_API_URL: 'http://localhost:8000',
    })
    expect(local).not.toContain('upgrade-insecure-requests')
    expect(directive(local, 'connect-src')).toContain('http://localhost:8000')
  })

  it('adds eval and websockets in development only', () => {
    const dev = contentSecurityPolicy({
      ...production,
      NODE_ENV: 'development',
    })
    expect(directive(dev, 'script-src')).toContain("'unsafe-eval'")
    expect(directive(dev, 'connect-src')).toContain('ws://localhost:*')
    expect(dev).not.toContain('upgrade-insecure-requests')
  })

  it('ignores a missing or broken address instead of throwing', () => {
    const bare = contentSecurityPolicy({
      NODE_ENV: 'production',
      NEXT_PUBLIC_API_URL: 'not a url',
    })
    expect(directive(bare, 'connect-src')).toEqual(["'self'"])
  })
})

describe('securityHeaders', () => {
  const headers = securityHeaders(production)
  const byKey = new Map(headers.map((entry) => [entry.key, entry.value]))

  it('sends every header the audit asked for', () => {
    expect(byKey.get('Content-Security-Policy')).toBeDefined()
    expect(byKey.get('Strict-Transport-Security')).toMatch(/^max-age=\d{8,}/)
    expect(byKey.get('X-Content-Type-Options')).toBe('nosniff')
    expect(byKey.get('Referrer-Policy')).toBe('strict-origin-when-cross-origin')
    expect(byKey.get('Permissions-Policy')).toContain('camera=()')
    expect(byKey.get('X-Frame-Options')).toBe('DENY')
  })

  it('can send the policy as report-only', () => {
    const reportOnly = securityHeaders({ ...production, CSP_REPORT_ONLY: '1' })
    const keys = reportOnly.map((entry) => entry.key)
    expect(keys).toContain('Content-Security-Policy-Report-Only')
    expect(keys).not.toContain('Content-Security-Policy')
  })

  it('has no duplicate headers', () => {
    expect(new Set(headers.map((entry) => entry.key)).size).toBe(headers.length)
  })
})
