import { describe, expect, it, vi } from 'vitest'

import { labelsFor, presentSkills, submitDecision } from '@/lib/api/verify'

describe('verify submission', () => {
  it('does not call the API for an empty code and is not not_found', async () => {
    const post = vi.fn()
    const result = await submitDecision('   ', post)
    expect(post).not.toHaveBeenCalled()
    expect(result).toEqual({ kind: 'prompt' })
  })

  it('maps the four outcomes to distinct labels in English and Georgian', () => {
    const codes = ['valid', 'outdated', 'not_found', 'error'] as const
    const english = codes.map((code) => labelsFor(code, 'en'))
    const georgian = codes.map((code) => labelsFor(code, 'ka'))
    expect(new Set(english).size).toBe(4)
    expect(new Set(georgian).size).toBe(4)
    expect(english[1]).toMatch(/outdated version/i)
    expect(georgian[1]).not.toBe(english[1])
  })

  it('keeps skill text returned by the API in both languages', () => {
    const skills = [
      {
        skill: 'მანქანური სწავლება',
        badge: 'ბეჭედი',
        awarded_on: '2025-06-01',
      },
    ]
    expect(presentSkills(skills, 'en')).toEqual(skills)
    expect(presentSkills(skills, 'ka')).toEqual(skills)
  })
})
