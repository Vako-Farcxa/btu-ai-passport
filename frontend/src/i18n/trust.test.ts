import { describe, expect, it } from 'vitest'

import { messages } from '@/i18n/messages'
import { trust, type InfoPageId } from '@/i18n/trust'

const PAGES: InfoPageId[] = ['about', 'privacy', 'terms']

function strings(value: unknown): string[] {
  if (typeof value === 'string') return [value]
  if (value && typeof value === 'object') {
    return Object.values(value).flatMap(strings)
  }
  return []
}

describe('trust copy', () => {
  it('has the same shape in English and Georgian', () => {
    for (const page of PAGES) {
      const en = trust.en.pages[page]
      const ka = trust.ka.pages[page]
      expect(ka.sections.length).toBe(en.sections.length)
      en.sections.forEach((section, index) => {
        expect(ka.sections[index]?.list).toBe(section.list)
        expect(Boolean(ka.sections[index]?.link)).toBe(Boolean(section.link))
        expect(ka.sections[index]?.body.length).toBe(section.body.length)
      })
    }
    expect(Object.keys(trust.ka).sort()).toEqual(Object.keys(trust.en).sort())
  })

  it('spells the team names the same way everywhere', () => {
    expect(trust.ka.team).toContain('თაზო ფუთურიძე')
    for (const text of strings(trust.ka)) expect(text).not.toContain('ტაზო')
  })

  it('uses no em-dashes anywhere in user-facing text', () => {
    for (const text of [...strings(trust), ...strings(messages)]) {
      expect(text).not.toContain('\u2014')
    }
  })

  it('leaves no Georgian text in English and no English sentences in Georgian', () => {
    for (const text of strings(trust.en)) {
      expect(text).not.toMatch(/[\u10a0-\u10ff]/)
    }
    expect(trust.ka.disclaimer).toMatch(/[\u10a0-\u10ff]/)
  })

  it('says hackathon project and not official in the disclaimer and the landing note', () => {
    expect(trust.en.disclaimer).toMatch(/not an official BTU service/i)
    expect(trust.en.disclaimer).toMatch(/hackathon/i)
    expect(messages.en.landingNote).toMatch(/HACKATHON/)
    expect(messages.ka.landingNote).toContain('ჰაკათონ')
  })

  it('no longer calls anything official', () => {
    for (const text of strings(messages)) {
      expect(text).not.toMatch(/official/i)
      expect(text).not.toContain('ოფიციალურ')
    }
  })

  it('names the Amoy test network and says there is no guarantee', () => {
    expect(trust.en.testnetNote).toMatch(/Polygon Amoy test network/)
    expect(trust.en.testnetNote).toMatch(/no permanence guarantee/)
    expect(trust.ka.testnetNote).toContain('Polygon Amoy')
  })
})
