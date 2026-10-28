import { cleanup, render } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { VerifyResultCard } from '@/components/verify-result'
import { messages, type Locale } from '@/i18n/messages'
import { verifyResultSchema, type VerifyResult } from '@/lib/api/types'

vi.mock('@/components/motion', () => ({
  useResultMotion: () => undefined,
  useSkillMotion: () => undefined,
}))

afterEach(cleanup)

// Values that come from the API. They are data, so they may be in any language.
const DATA = {
  holder: 'Nino Beridze',
  skill: 'Machine Learning',
  badge: 'BDG-AI-001',
  description: 'Use models with a human in the loop.',
}
const TX = 'https://amoy.polygonscan.com/tx/0x' + '11'.repeat(32)

function found(outcome: 'valid' | 'outdated', extra: object = {}) {
  return verifyResultSchema.parse({
    outcome,
    holder_name: DATA.holder,
    version: outcome === 'valid' ? 2 : 1,
    is_latest: outcome === 'valid',
    skills: [
      {
        skill: DATA.skill,
        badge: DATA.badge,
        awarded_on: '2025-06-01',
        description: DATA.description,
      },
    ],
    tx_url: TX,
    ...extra,
  })
}

const VALID = found('valid')
const OUTDATED = found('outdated', {
  latest_version: 3,
  latest_issued_at: '2026-10-28',
})
const RESULTS: Record<string, VerifyResult> = {
  valid: VALID,
  outdated: OUTDATED,
  not_found: { outcome: 'not_found' },
  error: { outcome: 'error' },
}

// Everything a user can read or hear: text, plus aria-label, title and alt values.
function userFacingText(root: HTMLElement): string {
  const parts = [root.textContent ?? '']
  for (const element of root.querySelectorAll('*')) {
    for (const name of ['aria-label', 'title', 'alt', 'placeholder']) {
      const value = element.getAttribute(name)
      if (value) parts.push(value)
    }
  }
  let text = parts.join('\n')
  for (const value of Object.values(DATA)) text = text.split(value).join(' ')
  return text
}

// Latin words that may stay in Georgian: the abbreviations BTU and AI.
function englishWords(text: string): string[] {
  return (text.match(/[A-Za-z]{2,}/g) ?? []).filter(
    (word) => word !== 'BTU' && word !== 'AI',
  )
}

describe('verify result card', () => {
  for (const [name, result] of Object.entries(RESULTS)) {
    it(`has no English text left in Georgian for ${name}`, () => {
      const { container } = render(
        <VerifyResultCard locale="ka" result={result} />,
      )
      expect(englishWords(userFacingText(container))).toEqual([])
    })
  }

  it('is not tested against a blind spot: English really is detected', () => {
    const { container } = render(
      <VerifyResultCard locale="en" result={OUTDATED} />,
    )
    expect(englishWords(userFacingText(container)).length).toBeGreaterThan(5)
  })

  it('labels every status in Georgian', () => {
    for (const [name, result] of Object.entries(RESULTS)) {
      const { getByTestId } = render(
        <VerifyResultCard locale="ka" result={result} />,
      )
      const label = messages.ka.outcomes[result.outcome]
      expect(getByTestId('verify-result')).toHaveAttribute('aria-label', label)
      expect(getByTestId('verify-result')).toHaveTextContent(label)
      cleanup()
      expect(name).toBe(result.outcome)
    }
  })

  it('formats skill dates for the locale and keeps the ISO date machine readable', () => {
    for (const [locale, expected] of [
      ['en', '1 Jun 2025'],
      ['ka', '1 ივნ. 2025'],
    ] as [Locale, string][]) {
      const { container } = render(
        <VerifyResultCard locale={locale} result={VALID} />,
      )
      const time = container.querySelector('time')
      expect(time).toHaveAttribute('datetime', '2025-06-01')
      expect(time?.textContent).toContain(expected)
      expect(time?.textContent).not.toBe('2025-06-01')
      cleanup()
    }
  })

  it('shows the newer version note in Georgian', () => {
    const { getByTestId } = render(
      <VerifyResultCard locale="ka" result={OUTDATED} />,
    )
    expect(getByTestId('newer-notice')).toHaveTextContent('v3')
  })
})

describe('translations', () => {
  it('has the same keys in English and Georgian', () => {
    expect(Object.keys(messages.ka).sort()).toEqual(
      Object.keys(messages.en).sort(),
    )
  })

  it('has no English sentence in the Georgian catalogue', () => {
    const allowed = new Set(['BTU', 'AI', 'ID', 'PDF', 'Google', 'Ctrl', 'C'])
    const strings: string[] = []
    const walk = (value: unknown) => {
      if (typeof value === 'string') strings.push(value)
      else if (value && typeof value === 'object')
        Object.values(value).forEach(walk)
    }
    walk(messages.ka)
    const words = strings
      .join(' ')
      .replace(/\{[a-z]+\}/g, ' ')
      .replace(/btu\.edu\.ge/g, ' ')
      .match(/[A-Za-z]{2,}/g)
    expect((words ?? []).filter((word) => !allowed.has(word))).toEqual([])
  })
})
