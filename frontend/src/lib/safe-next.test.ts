import { describe, expect, it } from 'vitest'

import { safeNext } from '@/lib/safe-next'

describe('safeNext', () => {
  it('allows same-site paths', () => {
    expect(safeNext('/admin')).toBe('/admin')
    expect(safeNext(encodeURIComponent('/admin/skills'))).toBe('/admin/skills')
  })

  it('falls back to the passport for anything else', () => {
    for (const value of [
      undefined,
      '',
      'https://evil.example',
      '//evil.example',
      '/\\evil.example',
      'admin',
      '%E0%A4%A',
    ]) {
      expect(safeNext(value)).toBe('/passport')
    }
  })
})
