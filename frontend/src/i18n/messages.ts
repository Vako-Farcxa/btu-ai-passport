export type Locale = 'en' | 'ka'
export type Outcome = 'valid' | 'outdated' | 'not_found' | 'error'

type Copy = {
  title: string
  intro: string
  codeLabel: string
  check: string
  checking: string
  prompt: string
  latest: string
  notLatest: string
  skills: string
  dateUnavailable: string
  transaction: string
  language: string
  outcomes: Record<Outcome, string>
}

export const messages: Record<Locale, Copy> = {
  en: {
    title: 'Verify a passport',
    intro: 'Enter the verification code from a BTU AI Skills passport.',
    codeLabel: 'Verification code',
    check: 'Check',
    checking: 'Checking',
    prompt: 'Enter a verification code',
    latest: 'This is the latest version',
    notLatest: 'This is not the latest version',
    skills: 'Official skills',
    dateUnavailable: 'Date unavailable',
    transaction: 'Public transaction',
    language: 'Language',
    outcomes: {
      valid: 'Valid',
      outdated: 'Outdated version',
      not_found: 'Not found',
      error: 'Error',
    },
  },
  ka: {
    title: 'პასპორტის შემოწმება',
    intro: 'შეიყვანეთ BTU-ის AI უნარების პასპორტის ვერიფიკაციის კოდი.',
    codeLabel: 'ვერიფიკაციის კოდი',
    check: 'შემოწმება',
    checking: 'მოწმდება',
    prompt: 'შეიყვანეთ ვერიფიკაციის კოდი',
    latest: 'ეს არის უახლესი ვერსია',
    notLatest: 'ეს არ არის უახლესი ვერსია',
    skills: 'ოფიციალური უნარები',
    dateUnavailable: 'თარიღი უცნობია',
    transaction: 'საჯარო ტრანზაქცია',
    language: 'ენა',
    outcomes: {
      valid: 'ვალიდური',
      outdated: 'მოძველებული ვერსია',
      not_found: 'ვერ მოიძებნა',
      error: 'შეცდომა',
    },
  },
}

export function preferredLocale(language: string): Locale {
  const value = language.toLowerCase()
  if (value.startsWith('ka')) return 'ka'
  if (value.startsWith('en')) return 'en'
  return 'ka'
}
