import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
} from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { FlagBadge, FlagDialog, MyFlags } from '@/components/flags'
import { messages } from '@/i18n/messages'
import type { StudentFlag } from '@/lib/api/flags'

vi.mock('@/lib/supabase/client', () => ({
  readAccessToken: async () => 'tok',
}))
const fetchMock = vi.fn()

beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
})

const flag = (over: Partial<StudentFlag> = {}): StudentFlag => ({
  id: 'f1',
  version: 2,
  comment: 'A skill is missing here.',
  status: 'open',
  admin_note: '',
  created_at: '2026-10-28T10:00:00Z',
  resolved_at: null,
  unread: false,
  ...over,
})

describe('FlagDialog', () => {
  it('asks only for a comment and checks its length', async () => {
    const onSent = vi.fn()
    render(
      <FlagDialog version={2} locale="en" onClose={() => {}} onSent={onSent} />,
    )
    expect(screen.getAllByRole('textbox')).toHaveLength(1)
    expect(screen.queryByLabelText(/passport|code|email/i)).toBeNull()

    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: 'short' },
    })
    fireEvent.click(
      screen.getByRole('button', { name: messages.en.flagSubmit }),
    )
    expect(await screen.findByRole('alert')).toHaveTextContent(
      messages.en.flagTooShort,
    )
    expect(fetchMock).not.toHaveBeenCalled()

    fetchMock.mockResolvedValue({ ok: true, json: async () => flag() })
    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: 'The Python skill is missing.' },
    })
    fireEvent.click(
      screen.getByRole('button', { name: messages.en.flagSubmit }),
    )
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(url).toMatch(/\/flags$/)
    // Only the version and the comment are sent. The server knows the rest.
    expect(JSON.parse(init.body as string)).toEqual({
      version: 2,
      comment: 'The Python skill is missing.',
    })
    expect(await screen.findByText(messages.en.flagSent)).toBeInTheDocument()
    expect(onSent).toHaveBeenCalled()
  })

  it('shows a localized message when the API refuses', async () => {
    fetchMock.mockResolvedValue({
      ok: false,
      status: 429,
      json: async () => ({ code: 'flag_rate_limited' }),
    })
    render(
      <FlagDialog
        version={1}
        locale="ka"
        onClose={() => {}}
        onSent={() => {}}
      />,
    )
    fireEvent.change(screen.getByRole('textbox'), {
      target: { value: 'ეს არის საკმარისად გრძელი ტექსტი' },
    })
    fireEvent.click(
      screen.getByRole('button', { name: messages.ka.flagSubmit }),
    )
    expect(await screen.findByRole('alert')).toHaveTextContent(
      messages.ka.flagRateLimited,
    )
  })

  it('closes with Escape', () => {
    const onClose = vi.fn()
    render(
      <FlagDialog
        version={1}
        locale="en"
        onClose={onClose}
        onSent={() => {}}
      />,
    )
    fireEvent.keyDown(window, { key: 'Escape' })
    expect(onClose).toHaveBeenCalled()
  })
})

describe('FlagBadge', () => {
  it('opens the comment, the reply and the dates, and reports an unread reply', () => {
    const onOpened = vi.fn()
    render(
      <FlagBadge
        locale="en"
        onOpened={onOpened}
        flag={flag({
          status: 'resolved',
          admin_note: 'Added the missing skill.',
          resolved_at: '2026-10-29T09:00:00Z',
          unread: true,
        })}
      />,
    )
    const badge = screen.getByRole('button', { name: /Flag resolved/ })
    expect(
      screen.getByRole('img', { name: messages.en.newReply }),
    ).toBeVisible()
    fireEvent.click(badge)
    const dialog = screen.getByRole('dialog')
    expect(dialog).toHaveTextContent('A skill is missing here.')
    expect(dialog).toHaveTextContent('Added the missing skill.')
    expect(dialog).toHaveTextContent('Answered')
    expect(onOpened).toHaveBeenCalledTimes(1)
  })

  it('says there is no reply yet on an open flag and has no dot', () => {
    const onOpened = vi.fn()
    render(<FlagBadge locale="en" onOpened={onOpened} flag={flag()} />)
    expect(screen.queryByRole('img')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: /Flag open/ }))
    expect(screen.getByRole('dialog')).toHaveTextContent(
      messages.en.flagNoReply,
    )
    expect(onOpened).not.toHaveBeenCalled()
  })
})

describe('MyFlags', () => {
  it('shows an unread dot and marks replies seen when opened', () => {
    const onOpened = vi.fn()
    render(
      <MyFlags
        flags={[flag({ status: 'dismissed', unread: true })]}
        unread={1}
        failed={false}
        locale="en"
        onOpened={onOpened}
      />,
    )
    const link = screen.getByRole('button', { name: /My flags/ })
    expect(
      screen.getByRole('img', { name: messages.en.newReply }),
    ).toBeVisible()
    fireEvent.click(link)
    expect(onOpened).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('dialog')).toHaveTextContent('Version 2')
  })

  it('has no dot when everything is read, and says when empty', () => {
    const onOpened = vi.fn()
    render(
      <MyFlags
        flags={[]}
        unread={0}
        failed={false}
        locale="en"
        onOpened={onOpened}
      />,
    )
    expect(screen.queryByRole('img')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: /My flags/ }))
    expect(screen.getByRole('dialog')).toHaveTextContent(
      messages.en.myFlagsEmpty,
    )
    expect(onOpened).not.toHaveBeenCalled()
  })
})
