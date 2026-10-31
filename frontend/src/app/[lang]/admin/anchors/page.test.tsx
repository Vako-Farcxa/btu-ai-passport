import {
  cleanup,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import * as api from '@/lib/api/admin'

import AdminAnchorsPage from './page'

vi.mock('@/lib/api/admin', async () => {
  const actual =
    await vi.importActual<typeof import('@/lib/api/admin')>('@/lib/api/admin')
  return {
    ...actual,
    fetchAdminPendingVersions: vi.fn(),
    retryAdminAnchor: vi.fn(),
  }
})

const row = (
  id: string,
  status: api.AdminVersionPending['anchor_status'],
  extra: Partial<api.AdminVersionPending> = {},
): api.AdminVersionPending => ({
  version_id: id,
  passport_id: `BTU-${id}`,
  holder_name: `Student ${id}`,
  version_number: 1,
  anchor_status: status,
  issued_at: '2026-10-30T10:00:00Z',
  tx_hash: null,
  anchor_attempts: 0,
  anchor_last_error: null,
  anchor_submitted_at: null,
  anchor_next_attempt_at: null,
  ...extra,
})

beforeEach(() => {
  vi.mocked(api.fetchAdminPendingVersions).mockReset()
  vi.mocked(api.retryAdminAnchor).mockReset()
  vi.mocked(api.fetchAdminPendingVersions).mockResolvedValue({
    versions: [
      row('p', 'pending', { anchor_attempts: 1 }),
      row('r', 'retrying', {
        anchor_attempts: 2,
        anchor_last_error: 'rpc_unreachable',
        anchor_next_attempt_at: '2026-10-31T12:30:00Z',
      }),
      row('f', 'failed_permanent', {
        anchor_attempts: 6,
        anchor_last_error: 'slot_conflict',
      }),
    ],
  })
})
afterEach(cleanup)

const rowFor = (name: string) =>
  screen.getByText(name).closest('tr') as HTMLElement

describe('admin anchor monitor', () => {
  it('shows each version with its status, attempts and a plain reason', async () => {
    render(<AdminAnchorsPage />)
    await screen.findByText('Student p')
    expect(within(rowFor('Student p')).getByText('Pending')).toBeVisible()
    expect(within(rowFor('Student r')).getByText('Retrying')).toBeVisible()
    expect(
      within(rowFor('Student f')).getByText('Needs attention'),
    ).toBeVisible()
    expect(rowFor('Student f')).toHaveTextContent('6 attempts')
    expect(rowFor('Student p')).toHaveTextContent('1 attempt')
    expect(
      within(rowFor('Student f')).getByTestId('anchor-error'),
    ).toHaveTextContent(/different content/)
    expect(
      within(rowFor('Student r')).getByTestId('anchor-error'),
    ).toHaveTextContent(/could not be reached/)
    expect(rowFor('Student r')).toHaveTextContent(/Next try after/)
    expect(screen.getByText('1 needs attention')).toBeVisible()
  })

  it('offers Retry anchoring for retrying and failed versions, not for pending ones', async () => {
    render(<AdminAnchorsPage />)
    await screen.findByText('Student p')
    expect(
      within(rowFor('Student p')).queryByRole('button', {
        name: 'Retry anchoring',
      }),
    ).toBeNull()
    expect(
      within(rowFor('Student r')).getByRole('button', {
        name: 'Retry anchoring',
      }),
    ).toBeEnabled()
    expect(
      within(rowFor('Student f')).getByRole('button', {
        name: 'Retry anchoring',
      }),
    ).toBeEnabled()
  })

  it('retries one version, reports the result and reloads the queue', async () => {
    vi.mocked(api.retryAdminAnchor).mockResolvedValue({ status: 'confirmed' })
    render(<AdminAnchorsPage />)
    await screen.findByText('Student f')
    fireEvent.click(
      within(rowFor('Student f')).getByRole('button', {
        name: 'Retry anchoring',
      }),
    )
    await waitFor(() => expect(api.retryAdminAnchor).toHaveBeenCalledWith('f'))
    expect(await screen.findByTestId('anchor-notice')).toHaveTextContent(
      'Anchored and confirmed',
    )
    await waitFor(() =>
      expect(api.fetchAdminPendingVersions).toHaveBeenCalledTimes(2),
    )
  })

  it('says why when the retry still fails', async () => {
    vi.mocked(api.retryAdminAnchor).mockResolvedValue({
      status: 'failed_permanent',
      error: 'slot_conflict',
    })
    render(<AdminAnchorsPage />)
    await screen.findByText('Student f')
    fireEvent.click(
      within(rowFor('Student f')).getByRole('button', {
        name: 'Retry anchoring',
      }),
    )
    expect(await screen.findByTestId('anchor-notice')).toHaveTextContent(
      /Still failing/,
    )
  })

  it('shows the error when another run holds the lock', async () => {
    vi.mocked(api.retryAdminAnchor).mockRejectedValue(
      new Error('Another anchoring run is in progress. Try again in a minute.'),
    )
    render(<AdminAnchorsPage />)
    await screen.findByText('Student r')
    fireEvent.click(
      within(rowFor('Student r')).getByRole('button', {
        name: 'Retry anchoring',
      }),
    )
    expect(await screen.findByText(/Another anchoring run/)).toBeVisible()
  })

  it('shows the empty state when everything is confirmed', async () => {
    vi.mocked(api.fetchAdminPendingVersions).mockResolvedValue({ versions: [] })
    render(<AdminAnchorsPage />)
    expect(
      await screen.findByText(/fully confirmed on the blockchain/),
    ).toBeVisible()
  })

  it('shows a load error', async () => {
    vi.mocked(api.fetchAdminPendingVersions).mockRejectedValue(
      new Error('Failed to load pending versions: Bad Gateway'),
    )
    render(<AdminAnchorsPage />)
    expect(await screen.findByText(/Bad Gateway/)).toBeVisible()
  })
})
