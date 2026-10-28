import { describe, expect, it } from 'vitest'

import {
  EDUCATION_LEVELS,
  PROGRAMS_BY_LEVEL,
  programsForLevel,
} from '@/lib/btu-programs'

describe('btu programs', () => {
  it('has programs for every level, without duplicates inside a level', () => {
    for (const level of EDUCATION_LEVELS) {
      const programs = PROGRAMS_BY_LEVEL[level]
      expect(programs.length).toBeGreaterThan(0)
      expect(new Set(programs).size).toBe(programs.length)
    }
  })

  it('depends on the level', () => {
    expect(programsForLevel("Master's")).toContain(
      'Information Systems Management - DevOps',
    )
    expect(programsForLevel("Bachelor's")).not.toContain(
      'Information Systems Management - DevOps',
    )
    expect(programsForLevel('')).toEqual([])
    expect(programsForLevel('Nonsense')).toEqual([])
  })
})
