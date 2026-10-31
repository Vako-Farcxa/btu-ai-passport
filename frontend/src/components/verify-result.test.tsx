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
  revoked: verifyResultSchema.parse({
    outcome: 'revoked',
    revoked_at: '2026-10-30T10:00:00+00:00',
  }),
  pending: { outcome: 'pending' },
  tampered: { outcome: 'tampered' },
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
  // Addresses and hashes are data too.
  text = text.replace(/0x[0-9a-fA-F]+/g, ' ')
  return text
}

// Latin words that may stay in Georgian: BTU and AI, and the Polygon Amoy network name.
function englishWords(text: string): string[] {
  return (text.match(/[A-Za-z]{2,}/g) ?? []).filter(
    (word) =>
      ![
        'BTU',
        'AI',
        'Polygon',
        'Amoy',
        'Polygonscan',
        'anchors',
        'Query',
      ].includes(word),
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

describe('revoked result', () => {
  const REVOKED = verifyResultSchema.parse({
    outcome: 'revoked',
    revoked_at: '2026-10-30T10:00:00+00:00',
  })

  it('says Revoked, with the date, and never looks valid', () => {
    const { getByTestId, queryByText } = render(
      <VerifyResultCard locale="en" result={REVOKED} />,
    )
    const card = getByTestId('verify-result')
    expect(card).toHaveAttribute('aria-label', 'Revoked')
    expect(card).toHaveClass('outcome-revoked')
    expect(card).not.toHaveClass('outcome-valid')
    expect(getByTestId('revoked-notice')).toHaveTextContent('30 Oct 2026')
    expect(queryByText(messages.en.outcomes.valid)).toBeNull()
    expect(queryByText(messages.en.latest)).toBeNull()
  })

  it('shows no holder, skills or transaction link', () => {
    const { container } = render(
      <VerifyResultCard locale="en" result={REVOKED} />,
    )
    expect(container.querySelector('.holder')).toBeNull()
    expect(container.querySelector('.transaction-link')).toBeNull()
    expect(container.textContent).not.toContain(DATA.holder)
  })

  it('shows the date in Georgian', () => {
    const { getByTestId } = render(
      <VerifyResultCard locale="ka" result={REVOKED} />,
    )
    expect(getByTestId('revoked-notice')).toHaveTextContent('30 ოქტ. 2026')
  })

  it('still explains itself when the date is missing', () => {
    const result = verifyResultSchema.parse({ outcome: 'revoked' })
    const { getByTestId } = render(
      <VerifyResultCard locale="en" result={result} />,
    )
    expect(getByTestId('revoked-notice')).toHaveTextContent(
      messages.en.revokedNoticeNoDate,
    )
  })
})

describe('pending result', () => {
  const PENDING = verifyResultSchema.parse({ outcome: 'pending' })

  it('says pending on-chain confirmation, never error, valid or revoked', () => {
    const { getByTestId } = render(
      <VerifyResultCard locale="en" result={PENDING} />,
    )
    const card = getByTestId('verify-result')
    expect(card).toHaveAttribute('aria-label', 'Pending on-chain confirmation')
    expect(card).toHaveClass('outcome-pending')
    expect(card).not.toHaveClass('outcome-error')
    expect(card).not.toHaveClass('outcome-valid')
    expect(card.textContent).not.toMatch(/error|valid|revoked/i)
    expect(getByTestId('pending-notice')).toHaveTextContent(
      /not confirmed yet/i,
    )
  })

  it('says it in Georgian too, with no English left', () => {
    const { getByTestId, container } = render(
      <VerifyResultCard locale="ka" result={PENDING} />,
    )
    expect(getByTestId('verify-result')).toHaveAttribute(
      'aria-label',
      messages.ka.outcomes.pending,
    )
    expect(getByTestId('pending-notice')).toHaveTextContent(
      messages.ka.pendingNotice,
    )
    expect(englishWords(userFacingText(container))).toEqual([])
  })

  it('shows no holder, skills, version or transaction link', () => {
    const { container } = render(
      <VerifyResultCard locale="en" result={PENDING} />,
    )
    expect(container.querySelector('.holder')).toBeNull()
    expect(container.querySelector('.transaction-link')).toBeNull()
    expect(container.querySelector('.testnet-note')).toBeNull()
    expect(container.textContent).not.toContain(DATA.holder)
  })
})

const CONTRACT = '0xf436Ba2A2cd1dc78f1543A1E7e8a9f20B2C40c32'
const CONTRACT_URL = `https://amoy.polygonscan.com/address/${CONTRACT}#readContract`

function onchain(status: 'verified' | 'unavailable', block: number | null) {
  return {
    status,
    block_number: block,
    contract_address: CONTRACT,
    contract_url: CONTRACT_URL,
    verification_id_hash: '0x' + 'ab'.repeat(32),
    content_hash: '0x' + 'cd'.repeat(32),
  }
}

describe('on-chain badge', () => {
  it('says verified with a block link and never claims it when unavailable', () => {
    const verified = found('valid', { onchain: onchain('verified', 51378532) })
    const { getByTestId } = render(
      <VerifyResultCard locale="en" result={verified} />,
    )
    const badge = getByTestId('onchain-badge')
    expect(badge).toHaveAttribute('data-status', 'verified')
    expect(badge).toHaveTextContent('Verified on-chain, block 51378532')
    expect(getByTestId('onchain-block-link')).toHaveAttribute(
      'href',
      'https://amoy.polygonscan.com/block/51378532',
    )
    cleanup()

    const down = found('valid', { onchain: onchain('unavailable', null) })
    const second = render(<VerifyResultCard locale="en" result={down} />)
    const unavailable = second.getByTestId('onchain-badge')
    expect(unavailable).toHaveAttribute('data-status', 'unavailable')
    expect(unavailable).toHaveTextContent(
      'On-chain check unavailable, try later',
    )
    expect(unavailable.textContent).not.toMatch(/verified on-chain/i)
    expect(second.queryByTestId('onchain-block-link')).toBeNull()
    // The database result is still shown.
    expect(second.getByTestId('verify-result')).toHaveTextContent(DATA.holder)
  })

  it('never shows a block for an unavailable check, even if one is sent', () => {
    const odd = found('valid', { onchain: onchain('unavailable', 5) })
    const { queryByTestId } = render(
      <VerifyResultCard locale="en" result={odd} />,
    )
    expect(queryByTestId('onchain-block-link')).toBeNull()
  })

  it('is on outdated results too, and absent from older backends', () => {
    const outdated = found('outdated', {
      latest_version: 3,
      latest_issued_at: '2026-10-28',
      onchain: onchain('verified', 9),
    })
    const first = render(<VerifyResultCard locale="en" result={outdated} />)
    expect(first.getByTestId('onchain-badge')).toBeInTheDocument()
    cleanup()
    const second = render(<VerifyResultCard locale="en" result={VALID} />)
    expect(second.queryByTestId('onchain-badge')).toBeNull()
    expect(second.queryByTestId('self-verify')).toBeNull()
  })

  it('offers a verify-it-yourself link and the values to compare', () => {
    const verified = found('valid', { onchain: onchain('verified', 9) })
    const { getByTestId } = render(
      <VerifyResultCard locale="en" result={verified} />,
    )
    const section = getByTestId('self-verify')
    expect(section).toHaveTextContent(CONTRACT)
    expect(section).toHaveTextContent('0x' + 'ab'.repeat(32))
    expect(section).toHaveTextContent('0x' + 'cd'.repeat(32))
    expect(getByTestId('self-verify-link')).toHaveAttribute(
      'href',
      CONTRACT_URL,
    )
  })

  it.each(['verified', 'unavailable'] as const)(
    'has no English text left in Georgian when %s',
    (status) => {
      const result = found('valid', {
        onchain: onchain(status, status === 'verified' ? 9 : null),
      })
      const { container } = render(
        <VerifyResultCard locale="ka" result={result} />,
      )
      expect(englishWords(userFacingText(container))).toEqual([])
    },
  )

  it('rejects an off-site contract link from the API', () => {
    for (const url of [
      'https://evil.example/address/' + CONTRACT,
      'javascript:alert(1)',
      `http://amoy.polygonscan.com/address/${CONTRACT}`,
      `https://amoy.polygonscan.com/address/${CONTRACT}?x=1`,
    ]) {
      expect(() =>
        found('valid', {
          onchain: { ...onchain('verified', 9), contract_url: url },
        }),
      ).toThrow()
    }
  })
})

describe('tampered result', () => {
  const TAMPERED = verifyResultSchema.parse({
    outcome: 'tampered',
    reason: 'chain_mismatch',
    contract_url: CONTRACT_URL,
  })

  it('says it does not match the blockchain, and never looks valid', () => {
    const { getByTestId } = render(
      <VerifyResultCard locale="en" result={TAMPERED} />,
    )
    const card = getByTestId('verify-result')
    expect(card).toHaveAttribute('aria-label', 'Does not match the blockchain')
    expect(card).toHaveClass('outcome-tampered')
    expect(card).not.toHaveClass('outcome-valid')
    expect(getByTestId('tampered-notice')).toHaveTextContent(
      /may have been changed/,
    )
  })

  it('shows no name, skills, badge or transaction link', () => {
    const withName = verifyResultSchema.parse({
      outcome: 'tampered',
      holder_name: DATA.holder,
      skills: [{ skill: DATA.skill, badge: '', awarded_on: null }],
    })
    const { container, queryByTestId } = render(
      <VerifyResultCard locale="en" result={withName} />,
    )
    expect(container.querySelector('.holder')).toBeNull()
    expect(container.querySelector('.transaction-link')).toBeNull()
    expect(queryByTestId('onchain-badge')).toBeNull()
    expect(container.textContent).not.toContain(DATA.holder)
    expect(container.textContent).not.toContain(DATA.skill)
  })

  it('says it in Georgian with no English left', () => {
    const { getByTestId, container } = render(
      <VerifyResultCard locale="ka" result={TAMPERED} />,
    )
    expect(getByTestId('verify-result')).toHaveAttribute(
      'aria-label',
      messages.ka.outcomes.tampered,
    )
    expect(englishWords(userFacingText(container))).toEqual([])
  })
})

describe('translations', () => {
  it('has the same keys in English and Georgian', () => {
    expect(Object.keys(messages.ka).sort()).toEqual(
      Object.keys(messages.en).sort(),
    )
  })

  it('has no English sentence in the Georgian catalogue', () => {
    // Polygonscan, its function name `anchors` and its Query button are names from a
    // site that has no Georgian interface.
    const allowed = new Set([
      'BTU',
      'AI',
      'ID',
      'PDF',
      'Google',
      'Ctrl',
      'C',
      'Polygon',
      'Amoy',
      'Polygonscan',
      'anchors',
      'Query',
    ])
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

  it.each(['valid', 'outdated'] as const)(
    'tells the reader the anchor is on a test network for %s',
    (outcome) => {
      const { getByTestId } = render(
        <VerifyResultCard locale="en" result={RESULTS[outcome]!} />,
      )
      expect(getByTestId('testnet-note').textContent).toMatch(
        /Polygon Amoy test network/,
      )
    },
  )

  it.each(['not_found', 'error', 'pending'] as const)(
    'shows no test network note when there is no anchor (%s)',
    (outcome) => {
      const { queryByTestId } = render(
        <VerifyResultCard locale="en" result={RESULTS[outcome]!} />,
      )
      expect(queryByTestId('testnet-note')).toBeNull()
    },
  )

  it('never shows an email address, passport id or code', () => {
    const { container } = render(
      <VerifyResultCard locale="en" result={VALID} />,
    )
    expect(container.textContent).not.toMatch(/@|BTU-[A-Z0-9]{6,}/)
  })
})

describe('not found result', () => {
  const NOT_FOUND = verifyResultSchema.parse({ outcome: 'not_found' })

  it.each(['en', 'ka'] as const)(
    'tells the visitor what to try next in %s',
    (locale) => {
      const { getByTestId, container } = render(
        <VerifyResultCard locale={locale} result={NOT_FOUND} />,
      )
      expect(getByTestId('verify-result')).toHaveClass('outcome-not_found')
      expect(getByTestId('not-found-notice')).toHaveTextContent(
        messages[locale].notFoundNotice,
      )
      // Nothing about a holder is invented for a code that matches nobody.
      expect(container.querySelector('.holder')).toBeNull()
    },
  )

  it('does not show the notice for a valid result', () => {
    const { queryByTestId } = render(
      <VerifyResultCard locale="en" result={found('valid')} />,
    )
    expect(queryByTestId('not-found-notice')).toBeNull()
  })
})
