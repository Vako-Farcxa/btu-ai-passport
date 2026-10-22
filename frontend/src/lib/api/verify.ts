import { messages, type Locale, type Outcome } from '@/i18n/messages'
import type { Skill } from '@/lib/api/types'

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
