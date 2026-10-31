import { cleanup, fireEvent, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { messages } from '@/i18n/messages'

import VerifyClient from './verify-client'

let locale: 'en' | 'ka' = 'en'

vi.mock('@/components/motion', () => ({
  useSkillMotion: () => undefined,
  useCoverMotion: () => undefined,
  useOpenBookMotion: () => undefined,
  useResultMotion: () => undefined,
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

function okResponse(holder: string, version = 2) {
  return {
    ok: true,
    status: 200,
    headers: new Headers(),
    json: async () => ({
      outcome: 'valid',
      holder_name: holder,
      version,
      is_latest: true,
      skills: [
        { skill: 'Python', badge: 'BDG-AI-001', awarded_on: '2025-01-15' },
      ],
      tx_url: 'https://amoy.polygonscan.com/tx/0x' + '33'.repeat(32),
      onchain: {
        status: 'verified',
        block_number: 123,
        contract_address: '0x' + 'ab'.repeat(20),
        contract_url:
          'https://amoy.polygonscan.com/address/0x' + 'ab'.repeat(20),
        verification_id_hash: '0x' + '11'.repeat(32),
        content_hash: '0x' + '22'.repeat(32),
      },
    }),
  }
}

describe('verify page while the code input is edited', () => {
  it('keeps the shown result untouched until the next submit', async () => {
    fetchMock
      .mockResolvedValueOnce(okResponse('Ana Kiknadze'))
      .mockResolvedValueOnce(okResponse('Nino Beridze'))
    render(<VerifyClient />)
    submit('AAAA-BBBB-CCCC-DDDD')
    const card = await screen.findByTestId('verify-result')
    expect(card).toHaveTextContent('Ana Kiknadze')
    expect(fetchMock).toHaveBeenCalledTimes(1)

    // Open the "check it yourself" details: a remount of the card would close it again.
    const details = screen.getByTestId('self-verify') as HTMLDetailsElement
    details.open = true

    const input = screen.getByLabelText(messages.en.codeLabel)
    for (const value of ['E', 'EEEE-F', 'EEEE-FFFF-GGGG-HHHH']) {
      fireEvent.change(input, { target: { value } })
      // The very same card element, still showing the first code's holder.
      expect(screen.getByTestId('verify-result')).toBe(card)
      expect(card).toHaveTextContent('Ana Kiknadze')
      expect(card).not.toHaveTextContent('Nino Beridze')
    }
    expect(screen.getByTestId('self-verify')).toBe(details)
    expect(details.open).toBe(true)
    expect((input as HTMLInputElement).value).toBe('EEEE-FFFF-GGGG-HHHH')
    // Typing sent nothing and did not touch the address bar.
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(window.location.search).toBe('')

    // Enter in the field (a form submit) checks the new code.
    fireEvent.submit(input.closest('form') as HTMLFormElement)
    expect(await screen.findByText('Nino Beridze')).toBeInTheDocument()
    expect(fetchMock).toHaveBeenCalledTimes(2)
    expect(
      JSON.parse((fetchMock.mock.calls[1]?.[1] as { body: string }).body),
    ).toEqual({
      code: 'EEEE-FFFF-GGGG-HHHH',
    })
    expect(screen.queryByText('Ana Kiknadze')).toBeNull()
  })

  it('does not show a new result for a code that was only typed, while a check is running', async () => {
    let release: (value: unknown) => void = () => undefined
    fetchMock.mockReturnValueOnce(new Promise((resolve) => (release = resolve)))
    render(<VerifyClient />)
    submit('AAAA-BBBB-CCCC-DDDD')
    fireEvent.change(screen.getByLabelText(messages.en.codeLabel), {
      target: { value: 'ZZZZ-ZZZZ-ZZZZ-ZZZZ' },
    })
    release(okResponse('Ana Kiknadze'))
    expect(await screen.findByText('Ana Kiknadze')).toBeInTheDocument()
    // Still the typed text in the box, and only one request was made.
    expect(
      (screen.getByLabelText(messages.en.codeLabel) as HTMLInputElement).value,
    ).toBe('ZZZZ-ZZZZ-ZZZZ-ZZZZ')
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })
})
