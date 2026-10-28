/**
 * Input rules for the people an admin adds. They give inline messages in the browser; the
 * API applies the same rules again (backend/src/passport_api/validation.py) and is the
 * authority, so keep the two in step.
 */

export const NAME_MIN = 2
export const NAME_MAX = 50
export const EMAIL_LOCAL_MIN = 3

// Latin (with accents) and Georgian letters only. No digits.
const LETTER =
  'A-Za-z\\u00C0-\\u00D6\\u00D8-\\u00F6\\u00F8-\\u024F\\u10A0-\\u10C5\\u10D0-\\u10FA\\u10FD-\\u10FF'
// Words joined by one space, hyphen or apostrophe. No leading, trailing or doubled joiners.
const NAME = new RegExp(`^[${LETTER}]+(?:[ '\\u2019-][${LETTER}]+)*$`)
const EMAIL = /^[^@\s]+@[^@\s]+\.[^@\s]+$/

/** Domains the admin may add. Matches the backend ALLOWED_EMAIL_DOMAINS setting. */
export function allowedEmailDomains(): string[] {
  const raw = process.env.NEXT_PUBLIC_ALLOWED_EMAIL_DOMAINS ?? 'btu.edu.ge'
  const domains = raw
    .split(',')
    .map((part) => part.trim().toLowerCase().replace(/^@/, ''))
    .filter(Boolean)
  return domains.length > 0 ? domains : ['btu.edu.ge']
}

/** Trimmed, NFC, inner whitespace collapsed to one space. */
export function cleanName(value: string): string {
  return value.normalize('NFC').split(/\s+/).filter(Boolean).join(' ')
}

export function cleanEmail(value: string): string {
  return value.normalize('NFC').trim().toLowerCase()
}

/** A message when `value` is not a plausible first or last name, else null. */
export function nameError(value: string, label: string): string | null {
  const name = cleanName(value)
  if (name === '') return `${label} is required.`
  if (name.length < NAME_MIN || name.length > NAME_MAX) {
    return `${label} must be ${NAME_MIN} to ${NAME_MAX} characters.`
  }
  if (!NAME.test(name)) {
    return `${label} can only contain letters (Latin or Georgian), with a hyphen, apostrophe or space between words. No digits or symbols.`
  }
  return null
}

/** A message for the first rule the email breaks, else null. Cleans the value first. */
export function emailError(value: string): string | null {
  const email = cleanEmail(value)
  if (email === '') return 'Email is required.'
  if (!EMAIL.test(email)) return 'Enter a valid email address.'
  const domains = allowedEmailDomains()
  const domain = email.slice(email.lastIndexOf('@') + 1)
  if (!domains.includes(domain)) {
    return `Use a university email (${domains.map((d) => `@${d}`).join(', ')}).`
  }
  const local = email.slice(0, email.lastIndexOf('@'))
  if (local.length < EMAIL_LOCAL_MIN) {
    return `The part before @ needs at least ${EMAIL_LOCAL_MIN} characters.`
  }
  if (!/\p{L}/u.test(local)) {
    return 'The part before @ cannot be only digits. Use the real address of the student.'
  }
  return null
}

export interface PersonInput {
  email: string
  first_name: string
  last_name: string
}

/**
 * Problems in a list of people for an award, one readable line each. Names may be left out
 * (existing students) but a name given must be complete and valid. Duplicate emails are
 * rejected.
 */
export function awardStudentProblems(students: PersonInput[]): string[] {
  const problems: string[] = []
  const seen = new Set<string>()
  for (const student of students) {
    const email = cleanEmail(student.email)
    const who = email || '(no email)'
    const problem = emailError(email)
    if (problem) problems.push(`${who}: ${problem}`)
    if (email && seen.has(email))
      problems.push(`${who}: listed more than once.`)
    seen.add(email)
    if (cleanName(student.first_name) || cleanName(student.last_name)) {
      const nameProblem =
        nameError(student.first_name, 'First name') ??
        nameError(student.last_name, 'Last name')
      if (nameProblem) problems.push(`${who}: ${nameProblem}`)
    }
  }
  return problems
}
