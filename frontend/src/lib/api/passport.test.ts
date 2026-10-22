import { describe, expect, it } from 'vitest'

import { messages } from '@/i18n/messages'
import {
  explainPassportError,
  renderPassportLines,
  type PassportResponse,
} from '@/lib/api/passport'

const otherPassportId = 'BTU-V2W3X4Y5Z6'

const callerOldestFirst: PassportResponse = {
  passport: {
    passport_id: 'BTU-A1B2C3D4E5',
    versions: [
      {
        version: 1,
        issued_at: '2025-01-15T00:00:00Z',
        is_current: false,
        holder_name: 'Nino Beridze',
        verification_code: 'K9M2-N3P4-Q5R6-S7T8',
        skills: [
          { skill: 'Python', badge: 'Foundation', awarded_on: '2025-01-15' },
        ],
        anchor: {
          status: 'confirmed',
          tx_url: 'https://amoy.polygonscan.com/tx/' + '22'.repeat(32),
        },
      },
      {
        version: 2,
        issued_at: '2025-06-01T00:00:00Z',
        is_current: true,
        holder_name: 'Nino Beridze',
        verification_code: 'A1B2-C3D4-E5F6-G7H8',
        skills: [
          {
            skill: 'მანქანური სწავლება',
            badge: 'Stamp',
            awarded_on: '2025-06-01',
          },
        ],
        anchor: {
          status: 'confirmed',
          tx_url: 'https://amoy.polygonscan.com/tx/' + '11'.repeat(32),
        },
      },
    ],
  },
}

describe('passport view', () => {
  it('treats a null passport as empty and shows no passport id', () => {
    const lines = renderPassportLines({ passport: null }, 'en')
    expect(lines).toEqual([messages.en.emptyPassport])
    expect(lines.join('\n')).not.toContain('BTU-')
  })

  it('explains domain_not_allowed in English and Georgian', () => {
    const english = explainPassportError('domain_not_allowed', 'en')
    const georgian = explainPassportError('domain_not_allowed', 'ka')
    expect(english).toMatch(/btu\.edu\.ge/i)
    expect(english).toBe(messages.en.domainNotAllowed)
    expect(georgian).toBe(messages.ka.domainNotAllowed)
    expect(georgian).not.toBe(english)
    expect(english).not.toContain(otherPassportId)
    expect(georgian).not.toContain(otherPassportId)
  })

  it('renders the caller versions newest first and omits another passport id', () => {
    const lines = renderPassportLines(callerOldestFirst, 'ka')
    const text = lines.join('\n')
    expect(text).toContain('BTU-A1B2C3D4E5')
    expect(text).toContain('A1B2-C3D4-E5F6-G7H8')
    expect(text).toContain('K9M2-N3P4-Q5R6-S7T8')
    expect(text.indexOf('A1B2-C3D4-E5F6-G7H8')).toBeLessThan(
      text.indexOf('K9M2-N3P4-Q5R6-S7T8'),
    )
    expect(text).toContain('მანქანური სწავლება')
    expect(text).toContain(messages.ka.passportId)
    expect(text).not.toContain(otherPassportId)
  })
})
