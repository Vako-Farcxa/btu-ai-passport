import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { messages } from '@/i18n/messages'

import VerifyClient from './verify-client'

let locale: 'en' | 'ka' = 'en'

vi.mock('@/components/motion', () => ({
  useSkillMotion: () => undefined,
  useCoverMotion: () => undefined,
  useOpenBookMotion: () => undefined,
}))
vi.mock('@/i18n/use-locale', () => ({
  useLocale: () => [locale, () => undefined],
}))
vi.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(),
}))

const fetchMock = vi.fn()

beforeEach(() => {
  locale = 'en'
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

function submit(code: string) {
  fireEvent.change(screen.getByLabelText(messages.en.codeLabel), {
    target: { value: code },
  })
  fireEvent.click(screen.getByRole('button', { name: messages.en.check }))
}

describe('verify page when the API says slow down', () => {
  it('shows a friendly message with the wait, not an error result', async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 429,
      headers: new Headers({ 'Retry-After': '33' }),
      json: async () => ({ code: 'rate_limited' }),
    })
    render(<VerifyClient />)
    submit('AAAA-BBBB-CCCC-DDDD')
    const alert = await screen.findByRole('alert')
    expect(alert).toHaveTextContent(
      'Too many requests. Please wait 33 seconds and try again.',
    )
    // Not shown as a failed verification.
    expect(screen.queryByText(messages.en.outcomes.error)).toBeNull()
  })

  it('speaks Georgian when the page is in Georgian', async () => {
    locale = 'ka'
    fetchMock.mockResolvedValue({
      ok: false,
      status: 429,
      headers: new Headers({ 'Retry-After': '33' }),
      json: async () => ({ code: 'rate_limited' }),
    })
    render(<VerifyClient />)
    fireEvent.change(screen.getByLabelText(messages.ka.codeLabel), {
      target: { value: 'AAAA-BBBB-CCCC-DDDD' },
    })
    fireEvent.click(screen.getByRole('button', { name: messages.ka.check }))
    expect(await screen.findByRole('alert')).toHaveTextContent(
      messages.ka.rateLimited.replace('{seconds}', '33'),
    )
  })
})
