import { messages, type Locale, type Outcome } from '@/i18n/messages'
import type { Skill, VerifyResult } from '@/lib/api/types'

export async function submitDecision<T>(
  code: string,
  post: (code: string) => Promise<T>,
): Promise<{ kind: 'prompt' } | { kind: 'result'; body: T }> {
  if (code.trim() === '') return { kind: 'prompt' }
  const body = await post(code.trim())
  return { kind: 'result', body }
}

export function labelsFor(outcome: Outcome, locale: Locale): string {
  return messages[locale].outcomes[outcome]
}

export function presentSkills(skills: Skill[], locale: Locale): Skill[] {
  return locale === 'en' || locale === 'ka' ? skills : skills
}

// Month names are listed here instead of coming from Intl, because some browsers
// ship no Georgian locale data and would show English months in the Georgian page.
const MONTHS: Record<Locale, string[]> = {
  en: [
    'Jan',
    'Feb',
    'Mar',
    'Apr',
    'May',
    'Jun',
    'Jul',
    'Aug',
    'Sep',
    'Oct',
    'Nov',
    'Dec',
  ],
  ka: [
    'იან',
    'თებ',
    'მარ',
    'აპრ',
    'მაი',
    'ივნ',
    'ივლ',
    'აგვ',
    'სექ',
    'ოქტ',
    'ნოე',
    'დეკ',
  ],
}

/** "28 Oct 2026" or "28 ოქტ. 2026" for a YYYY-MM-DD value, or null if it is not a date. */
export function formatIssuedDate(value: string, locale: Locale): string | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(value)
  if (!match) return null
  const [, year, month, day] = match
  const date = new Date(Date.UTC(Number(year), Number(month) - 1, Number(day)))
  if (
    date.getUTCFullYear() !== Number(year) ||
    date.getUTCMonth() !== Number(month) - 1 ||
    date.getUTCDate() !== Number(day)
  ) {
    return null
  }
  const name = MONTHS[locale][date.getUTCMonth()]
  const dot = locale === 'ka' ? '.' : ''
  return `${date.getUTCDate()} ${name}${dot} ${date.getUTCFullYear()}`
}

/** The "a newer version exists" note, or null when it cannot be shown. */
export function newerVersionNotice(
  result: VerifyResult,
  locale: Locale,
): string | null {
  if (result.outcome !== 'outdated') return null
  if (!result.latest_version || !result.latest_issued_at) return null
  const date = formatIssuedDate(result.latest_issued_at, locale)
  if (date === null) return null
  return messages[locale].newerVersionNotice
    .replace('{version}', String(result.latest_version))
    .replace('{date}', date)
}
