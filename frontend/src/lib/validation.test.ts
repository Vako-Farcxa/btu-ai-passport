import { describe, expect, it } from 'vitest'

import {
  awardStudentProblems,
  cleanEmail,
  cleanName,
  emailError,
  nameError,
} from '@/lib/validation'

describe('nameError', () => {
  it.each([
    'Nino',
    'ნინო',
    'გიორგი',
    'Mary-Jane',
    "O'Brien",
    'O\u2019Neil',
    'Anna Maria',
    'José',
    '  Luka  ',
    'ნინო-მარიამ',
    'Ab',
  ])('accepts %s', (name) => {
    expect(nameError(name, 'First name')).toBeNull()
  })

  it.each([
    '',
    '   ',
    '1',
    '1 1',
    'A',
    'ა',
    'Nino2',
    'R2D2',
    '123',
    '-Nino',
    'Nino-',
    'Ni--no',
    "Ni''no",
    'Nino!',
    'Nino_Beridze',
    'a'.repeat(51),
  ])('rejects "%s"', (name) => {
    expect(nameError(name, 'First name')).not.toBeNull()
  })

  it('says which field is wrong', () => {
    expect(nameError('', 'Last name')).toBe('Last name is required.')
    expect(nameError('1 1', 'First name')).toContain('First name')
  })

  it('cleans spaces', () => {
    expect(cleanName('  Ana \t Maria ')).toBe('Ana Maria')
  })
})

describe('emailError', () => {
  it('lowercases and trims', () => {
    expect(cleanEmail('  Nino.Beridze@BTU.edu.ge ')).toBe(
      'nino.beridze@btu.edu.ge',
    )
    expect(emailError('  Nino.Beridze@BTU.edu.ge ')).toBeNull()
  })

  it.each(['111@btu.edu.ge', '12345678@btu.edu.ge'])(
    'rejects digit-only %s',
    (email) => {
      expect(emailError(email)).toMatch(/only digits/)
    },
  )

  it.each(['1@btu.edu.ge', 'ab@btu.edu.ge'])('rejects short %s', (email) => {
    expect(emailError(email)).toMatch(/at least 3/)
  })

  it('rejects other domains and bad formats', () => {
    expect(emailError('nino@gmail.com')).toMatch(/university email/)
    expect(emailError('nino@btu.edu.ge.evil.com')).toMatch(/university email/)
    expect(emailError('nino')).toMatch(/valid email/)
    expect(emailError('nino@')).toMatch(/valid email/)
    expect(emailError('ni no@btu.edu.ge')).toMatch(/valid email/)
    expect(emailError('')).toMatch(/required/)
  })

  it.each(['nino.beridze@btu.edu.ge', 'abc@btu.edu.ge', 'user123@btu.edu.ge'])(
    'accepts %s',
    (email) => {
      expect(emailError(email)).toBeNull()
    },
  )
})

describe('awardStudentProblems', () => {
  it('passes valid people, with or without names', () => {
    expect(
      awardStudentProblems([
        { email: 'nino@btu.edu.ge', first_name: '', last_name: '' },
        { email: 'tamar@btu.edu.ge', first_name: 'Tamar', last_name: 'Ch' },
      ]),
    ).toEqual([])
  })

  it('flags fake rows, half names and duplicates', () => {
    const problems = awardStudentProblems([
      { email: '111@btu.edu.ge', first_name: '1', last_name: '1' },
      { email: 'nino@btu.edu.ge', first_name: 'Nino', last_name: '' },
      { email: 'luka@btu.edu.ge', first_name: '', last_name: '' },
      { email: 'LUKA@btu.edu.ge', first_name: '', last_name: '' },
    ])
    expect(problems.some((p) => p.startsWith('111@btu.edu.ge'))).toBe(true)
    expect(problems.some((p) => p.includes('Last name is required'))).toBe(true)
    expect(problems.some((p) => p.includes('more than once'))).toBe(true)
  })
})
