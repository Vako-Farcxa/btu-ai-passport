import { describe, expect, it } from 'vitest'

import { stampFor } from '@/lib/stamps'

describe('badge stamps', () => {
  it('maps the three official badge codes to public stamp art', () => {
    expect(stampFor('BDG-AI-001')?.src).toBe('/stamps/BDG-AI-001.png')
    expect(stampFor('BDG-AI-002')?.src).toBe('/stamps/BDG-AI-002.png')
    expect(stampFor('BDG-AI-003')?.src).toBe('/stamps/BDG-AI-003.png')
  })

  it('leaves other badge labels as text', () => {
    expect(stampFor('Stamp')).toBeNull()
    expect(stampFor('Foundation')).toBeNull()
    expect(stampFor('')).toBeNull()
  })
})
