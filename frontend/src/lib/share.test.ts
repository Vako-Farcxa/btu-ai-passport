import { describe, expect, it } from 'vitest'

import { codeFromParam, shareLinkFor } from '@/lib/share'

describe('share links', () => {
  it('builds a verify link with the code in the query', () => {
    expect(
      shareLinkFor('https://passport.example', 'A1B2-C3D4-E5F6-G7H8'),
    ).toBe('https://passport.example/verify?code=A1B2-C3D4-E5F6-G7H8')
  })

  it('encodes unusual characters so the link cannot add parameters', () => {
    const link = shareLinkFor('https://passport.example', 'A&b=1 #x')
    expect(link).toBe('https://passport.example/verify?code=A%26b%3D1%20%23x')
    expect(new URL(link).searchParams.get('code')).toBe('A&b=1 #x')
  })

  it('normalises the code from the query', () => {
    expect(codeFromParam('  a1b2-c3d4-e5f6-g7h8 ')).toBe('A1B2-C3D4-E5F6-G7H8')
  })

  it('treats a missing or blank code as empty', () => {
    expect(codeFromParam(null)).toBe('')
    expect(codeFromParam('   ')).toBe('')
  })

  it('caps very long values at the API limit', () => {
    expect(codeFromParam('A'.repeat(200))).toHaveLength(64)
  })
})
