import { describe, expect, it } from 'vitest'

import { safeNext } from '@/lib/safe-next'

describe('safeNext', () => {
  it('allows same-site paths', () => {
    expect(safeNext('/admin')).toBe('/admin')
    expect(safeNext(encodeURIComponent('/admin/skills'))).toBe('/admin/skills')
    expect(safeNext('/verify?code=ABC-123')).toBe('/verify?code=ABC-123')
    expect(safeNext(encodeURIComponent('/verify?code=ABC#top'))).toBe(
      '/verify?code=ABC#top',
    )
    expect(safeNext('/')).toBe('/')
  })

  it('falls back to the passport for anything else', () => {
    for (const value of [
      undefined,
      '',
      'https://evil.example',
      'http://evil.example/passport',
      '//evil.example',
      '/\\evil.example',
      'admin',
      '%E0%A4%A',
    ]) {
      expect(safeNext(value)).toBe('/passport')
    }
  })

  it('rejects schemes and scheme-like values', () => {
    for (const value of [
      'javascript:alert(1)',
      '/javascript:alert(1)\n',
      'data:text/html,hi',
      'mailto:a@b.c',
      ' https://evil.example',
      'HTTPS://evil.example',
    ]) {
      expect(safeNext(value)).toBe('/passport')
    }
  })

  it('rejects encoded and obfuscated double slashes and backslashes', () => {
    for (const value of [
      '%2F%2Fevil.example',
      '%2f%2fevil.example',
      '/%5Cevil.example',
      '/%5cevil.example',
      '%5C%5Cevil.example',
      '/\\/evil.example',
    ]) {
      expect(safeNext(value), value).toBe('/passport')
    }
  })

  it('rejects tabs, newlines and other control characters that browsers strip', () => {
    for (const value of [
      '/\t/evil.example',
      '/%09/evil.example',
      '/\n/evil.example',
      '/%0A/evil.example',
      '/%0d%0a/evil.example',
      '/\r/evil.example',
      '/%00/evil.example',
      '/%7F/evil.example',
      '/%C2%85/evil.example',
      '\t//evil.example',
      '/admin\n',
    ]) {
      expect(safeNext(value), value).toBe('/passport')
    }
  })

  it('keeps the result on this site after normalising dot segments', () => {
    expect(safeNext('/a/../admin')).toBe('/admin')
    expect(safeNext('/../../admin')).toBe('/admin')
    expect(safeNext('/.//evil.example')).toBe('/passport')
    expect(safeNext('/a/..//evil.example')).toBe('/passport')
  })

  it('does not decode twice into something unsafe', () => {
    // Decoded once this is "/%2F%2Fevil.example", a plain path on this site.
    expect(safeNext('%2F%252F%252Fevil.example')).toBe('/%2F%2Fevil.example')
  })
})
