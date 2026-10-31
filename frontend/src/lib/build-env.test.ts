import { describe, expect, it } from 'vitest'

import { assertProductionApiUrl } from '@/lib/build-env'

const prod = { VERCEL_ENV: 'production' }

describe('assertProductionApiUrl', () => {
  it('accepts an https API address in production', () => {
    expect(() =>
      assertProductionApiUrl({
        ...prod,
        NEXT_PUBLIC_API_URL: 'https://btu-ai-passport-api.onrender.com',
      }),
    ).not.toThrow()
  })

  it('refuses a missing or blank address in production', () => {
    expect(() => assertProductionApiUrl(prod)).toThrow(/not set/)
    expect(() =>
      assertProductionApiUrl({ ...prod, NEXT_PUBLIC_API_URL: '   ' }),
    ).toThrow(/not set/)
  })

  it('refuses http, garbage and local addresses in production', () => {
    for (const value of [
      'http://api.example.com',
      'ftp://api.example.com',
      'not a url',
      'https://localhost:8000',
      'https://127.0.0.1',
      'javascript:alert(1)',
    ]) {
      expect(
        () => assertProductionApiUrl({ ...prod, NEXT_PUBLIC_API_URL: value }),
        value,
      ).toThrow()
    }
  })

  it('can be switched on outside Vercel', () => {
    expect(() =>
      assertProductionApiUrl({ REQUIRE_PRODUCTION_ENV: '1' }),
    ).toThrow(/not set/)
  })

  it('leaves local and preview builds alone', () => {
    expect(() => assertProductionApiUrl({})).not.toThrow()
    expect(() =>
      assertProductionApiUrl({
        VERCEL_ENV: 'preview',
        NEXT_PUBLIC_API_URL: 'http://localhost:8000',
      }),
    ).not.toThrow()
  })
})
