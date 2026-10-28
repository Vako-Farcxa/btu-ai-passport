import { describe, expect, it } from 'vitest'

import { adminErrorMessage, parseAwardStudents } from '@/lib/api/admin'

describe('parseAwardStudents', () => {
  it('reads one email per line', () => {
    expect(parseAwardStudents('a@btu.edu.ge\n\n  b@btu.edu.ge  ')).toEqual([
      { email: 'a@btu.edu.ge', first_name: '', last_name: '' },
      { email: 'b@btu.edu.ge', first_name: '', last_name: '' },
    ])
  })

  it('reads a name after the email', () => {
    expect(
      parseAwardStudents('nino@btu.edu.ge, Nino Beridze Kapanadze'),
    ).toEqual([
      {
        email: 'nino@btu.edu.ge',
        first_name: 'Nino',
        last_name: 'Beridze Kapanadze',
      },
    ])
  })

  it('splits several emails on one line', () => {
    expect(parseAwardStudents('a@btu.edu.ge; b@btu.edu.ge')).toHaveLength(2)
  })

  it('keeps a line without an email so the server can reject it', () => {
    expect(parseAwardStudents('Nino')).toEqual([
      { email: 'Nino', first_name: '', last_name: '' },
    ])
  })
})

describe('adminErrorMessage', () => {
  it('explains known codes and passes unknown ones through', () => {
    expect(adminErrorMessage('skill_name_taken')).toMatch(/already exists/)
    expect(adminErrorMessage('boom')).toBe('boom')
  })
})
